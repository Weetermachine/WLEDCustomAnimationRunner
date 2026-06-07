"""Flag Shimmer animation + DDP transport for a 1378-LED WLED strip.

When the animation stops we simply stop sending DDP packets; WLED falls back
to its own playlist after its DDP timeout (~2500 ms).
"""
import socket
import threading
import time

from strip_colors import stripColors

DDP_PORT = 4048
DDP_DATA_TYPE_RGB = 0x01
DDP_DEST = 0x01
MAX_PIXELS_PER_PACKET = 160          # 160 px * 3 bytes = 480 bytes payload
MAX_PAYLOAD = MAX_PIXELS_PER_PACKET * 3

NUM_LEDS = len(stripColors)
TARGET_FPS = 30.0


def _build_bright_seq():
    """11 brightness levels, ping-ponging 0 -> 10 -> 0."""
    step = 256 // 13  # 19
    levels = [i * step for i in range(11)]          # 0 .. 190  (11 values)
    return levels + levels[-2:0:-1]                 # ping-pong, 20 values


BRIGHT_SEQ = _build_bright_seq()
SEQ_LEN = len(BRIGHT_SEQ)


class Animator:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._ddp_seq = 0

        # live settings (updated by the scheduler/API)
        self.wled_ip = "192.168.50.250"
        self.speed = 1.0
        self.master_brightness = 255

    # -- settings ----------------------------------------------------------
    def update_settings(self, wled_ip=None, speed=None, master_brightness=None):
        with self._lock:
            if wled_ip is not None:
                self.wled_ip = wled_ip
            if speed is not None:
                self.speed = max(0.5, min(3.0, float(speed)))
            if master_brightness is not None:
                self.master_brightness = max(0, min(255, int(master_brightness)))

    def is_running(self):
        return self._running

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            t = self._thread
            running = self._running
        if not running:
            return
        self._stop.set()
        if t is not None:
            t.join(timeout=2.0)
        self._running = False

    # -- DDP ---------------------------------------------------------------
    def _send_frame(self, sock, pixels, ip):
        total = len(pixels)
        offset = 0
        while offset < total:
            chunk = pixels[offset:offset + MAX_PAYLOAD]
            is_last = (offset + len(chunk)) >= total
            header = bytearray(10)
            header[0] = 0x41 if is_last else 0x01
            header[1] = self._ddp_seq & 0xFF
            header[2] = DDP_DATA_TYPE_RGB
            header[3] = DDP_DEST
            header[4:8] = offset.to_bytes(4, "big")       # byte offset
            header[8:10] = len(chunk).to_bytes(2, "big")  # payload length
            try:
                sock.sendto(bytes(header) + chunk, (ip, DDP_PORT))
            except OSError:
                pass
            offset += len(chunk)
        self._ddp_seq = (self._ddp_seq + 1) & 0xFF

    # -- animation loop ----------------------------------------------------
    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        frame_time = 1.0 / TARGET_FPS
        counter = 0.0
        next_t = time.monotonic()
        try:
            while not self._stop.is_set():
                with self._lock:
                    speed = self.speed
                    mb = self.master_brightness
                    ip = self.wled_ip

                ci = int(counter)
                buf = bytearray(NUM_LEDS * 3)
                for i in range(NUM_LEDS):
                    b = BRIGHT_SEQ[(i + ci) % SEQ_LEN]
                    if mb != 255:
                        b = b * mb // 255
                    color = stripColors[i]
                    o = i * 3
                    if color == "RED":
                        buf[o] = b
                    elif color == "WHITE":
                        buf[o] = b
                        buf[o + 1] = b
                        buf[o + 2] = b
                    else:  # BLUE
                        buf[o + 2] = b

                self._send_frame(sock, bytes(buf), ip)

                counter += speed
                next_t += frame_time
                sleep = next_t - time.monotonic()
                if sleep > 0:
                    self._stop.wait(sleep)
                else:
                    # we fell behind; resync the clock
                    next_t = time.monotonic()
        finally:
            sock.close()
            self._running = False


# single shared instance
animator = Animator()

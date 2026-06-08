"""DDP transport + animation runner for a 1378-LED WLED strip.

This module owns the network transport (DDP over UDP), the 30 FPS pacing, and
the background thread lifecycle. The actual per-frame pixels come from a
pluggable animation looked up in the `animations` registry, so adding effects
never touches this file.

When the animation stops we simply stop sending DDP packets; WLED falls back to
its own playlist after its DDP timeout (~2500 ms).
"""
import socket
import threading
import time

import animations
from animations import AnimationContext
from strip_colors import stripColors

DDP_PORT = 4048
DDP_DATA_TYPE_RGB = 0x01
DDP_DEST = 0x01
MAX_PIXELS_PER_PACKET = 160          # 160 px * 3 bytes = 480 bytes payload
MAX_PAYLOAD = MAX_PIXELS_PER_PACKET * 3

NUM_LEDS = len(stripColors)
TARGET_FPS = 30.0


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
        self.animation_key = animations.default_key()
        self.animation_params = {}   # {animation_key: {param_key: value}}

    # -- settings ----------------------------------------------------------
    def update_settings(self, wled_ip=None, speed=None, master_brightness=None,
                        animation=None, animation_params=None):
        with self._lock:
            if wled_ip is not None:
                self.wled_ip = wled_ip
            if speed is not None:
                self.speed = max(0.5, min(3.0, float(speed)))
            if master_brightness is not None:
                self.master_brightness = max(0, min(255, int(master_brightness)))
            if animation is not None and animations.get(animation) is not None:
                self.animation_key = animation
            if animation_params is not None:
                self.animation_params = dict(animation_params)

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
        ctx = AnimationContext(NUM_LEDS, stripColors)
        next_t = time.monotonic()

        current_key = None
        spec = None
        gen = None
        frame = 0
        blank = bytes(NUM_LEDS * 3)

        try:
            while not self._stop.is_set():
                with self._lock:
                    ctx.speed = self.speed
                    ctx.brightness = self.master_brightness
                    ip = self.wled_ip
                    key = self.animation_key
                    params_store = self.animation_params.get(key)

                # (Re)resolve the animation when the selection changes.
                if key != current_key:
                    spec = animations.get(key) or animations.get(animations.default_key())
                    current_key = key
                    frame = 0
                    gen = spec.fn(ctx) if spec and spec.kind == "generator" else None

                # Refresh params every frame so color edits apply live.
                if spec is not None:
                    ctx.params = animations.merged_params(spec, params_store)

                if spec is None:
                    buf = blank
                elif spec.kind == "generator":
                    try:
                        buf = next(gen)
                    except StopIteration:
                        buf = blank
                else:  # stateless frame function
                    buf = spec.fn(frame, NUM_LEDS, ctx)

                self._send_frame(sock, buf, ip)
                frame += 1

                next_t += frame_time
                sleep = next_t - time.monotonic()
                if sleep > 0:
                    self._stop.wait(sleep)
                else:
                    next_t = time.monotonic()
        finally:
            sock.close()
            self._running = False


def _downsample(buf, samples, n_leds):
    """Pick `samples` evenly-spaced LEDs from a frame -> flat [r,g,b,...]."""
    out = []
    for s in range(samples):
        i = (s * (n_leds - 1) // (samples - 1)) if samples > 1 else 0
        o = i * 3
        out.extend((buf[o], buf[o + 1], buf[o + 2]))
    return out


def render_preview(key, params=None, frames=60, samples=220, speed=1.0, brightness=255):
    """Render an animation off-network into downsampled frames for the UI canvas.

    Uses the exact same animation code the strip runs, so the preview never
    drifts from reality.
    """
    spec = animations.get(key) or animations.get(animations.default_key())
    if spec is None:
        return {"samples": 0, "frames": []}

    ctx = AnimationContext(NUM_LEDS, stripColors)
    ctx.speed = max(0.5, min(3.0, float(speed)))
    ctx.brightness = max(0, min(255, int(brightness)))
    ctx.params = animations.merged_params(spec, params)

    out = []
    gen = spec.fn(ctx) if spec.kind == "generator" else None
    for f in range(frames):
        ctx.params = animations.merged_params(spec, params)
        if spec.kind == "generator":
            try:
                buf = next(gen)
            except StopIteration:
                buf = bytes(NUM_LEDS * 3)
        else:
            buf = spec.fn(f, NUM_LEDS, ctx)
        out.append(_downsample(buf, samples, NUM_LEDS))
    return {"samples": samples, "frames": out}


# single shared instance
animator = Animator()

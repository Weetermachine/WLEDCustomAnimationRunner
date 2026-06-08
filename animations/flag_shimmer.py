"""Flag Shimmer — the original effect, as a stateful generator.

A brightness wave (11 levels, ping-ponging 0->10->0) scrolls across the strip's
pre-mapped RED/WHITE/BLUE layout. Generator style lets the scroll phase
accumulate smoothly even as the speed multiplier changes live.
"""
from animations import animation


def _build_bright_seq():
    step = 256 // 13  # 19
    levels = [i * step for i in range(11)]      # 0 .. 190  (11 values)
    return levels + levels[-2:0:-1]             # ping-pong, 20 values


BRIGHT_SEQ = _build_bright_seq()
SEQ_LEN = len(BRIGHT_SEQ)


@animation("flag_shimmer", "Flag Shimmer", default=True)
def flag_shimmer(ctx):
    phase = 0.0
    while True:
        ci = int(phase)
        mb = ctx.brightness
        colors = ctx.colors
        buf = bytearray(ctx.n_leds * 3)
        for i in range(ctx.n_leds):
            b = BRIGHT_SEQ[(i + ci) % SEQ_LEN]
            if mb != 255:
                b = b * mb // 255
            c = colors[i]
            o = i * 3
            if c == "RED":
                buf[o] = b
            elif c == "WHITE":
                buf[o] = b
                buf[o + 1] = b
                buf[o + 2] = b
            else:  # BLUE
                buf[o + 2] = b
        yield bytes(buf)
        phase += ctx.speed

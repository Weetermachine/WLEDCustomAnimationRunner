"""Rainbow Scroll — a stateless frame function example.

Demonstrates the `render(frame, n_leds, ctx)` style: a pure function of the
frame index. Ignores the RED/WHITE/BLUE map and paints a moving hue gradient.
"""
import colorsys

from animations import animation

# Precompute a 256-entry hue lookup so the per-LED loop stays cheap at 30 FPS.
_HUE = [tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h / 256, 1.0, 1.0)) for h in range(256)]


@animation("rainbow", "Rainbow Scroll")
def rainbow(frame, n_leds, ctx):
    shift = int(frame * ctx.speed * 2)
    mb = ctx.brightness
    buf = bytearray(n_leds * 3)
    for i in range(n_leds):
        r, g, b = _HUE[((i * 256 // n_leds) + shift) % 256]
        if mb != 255:
            r = r * mb // 255
            g = g * mb // 255
            b = b * mb // 255
        o = i * 3
        buf[o] = r
        buf[o + 1] = g
        buf[o + 2] = b
    return bytes(buf)

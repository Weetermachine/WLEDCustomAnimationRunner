"""Gradient Scroll — a two-color animation with user-pickable colors.

Demonstrates the params system: two color pickers blend into a smooth gradient
that scrolls along the strip. Defaults to Old Glory red/blue.
"""
from animations import animation, hex_rgb


@animation(
    "gradient_scroll",
    "Gradient Scroll",
    params=[
        {"key": "color_a", "label": "Color A", "type": "color", "default": "#b22234"},
        {"key": "color_b", "label": "Color B", "type": "color", "default": "#3c3b6e"},
    ],
)
def gradient_scroll(frame, n_leds, ctx):
    ra, ga, ba = hex_rgb(ctx.params.get("color_a", "#b22234"))
    rb, gb, bb = hex_rgb(ctx.params.get("color_b", "#3c3b6e"))
    mb = ctx.brightness
    shift = frame * ctx.speed
    buf = bytearray(n_leds * 3)
    for i in range(n_leds):
        # position 0..1 along the strip, scrolling over time
        t = ((i + shift) % n_leds) / n_leds
        # ping-pong so the gradient blends A->B->A with no hard seam
        tt = 1.0 - abs(2.0 * t - 1.0)
        r = int(ra + (rb - ra) * tt)
        g = int(ga + (gb - ga) * tt)
        b = int(ba + (bb - ba) * tt)
        if mb != 255:
            r = r * mb // 255
            g = g * mb // 255
            b = b * mb // 255
        o = i * 3
        buf[o] = r
        buf[o + 1] = g
        buf[o + 2] = b
    return bytes(buf)

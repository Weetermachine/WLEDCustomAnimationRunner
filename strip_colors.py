"""PLACEHOLDER strip_colors.py

The real 1378-element color map is provided separately and should overwrite
this file. This placeholder generates a runnable flag-like pattern so the app
boots and animates during development. Each element is 'RED', 'WHITE', or
'BLUE'.
"""

NUM_LEDS = 1378


def _placeholder_pattern():
    colors = []
    # Rough repeating red/white/blue banding so something visible renders.
    band = (["BLUE"] * 60) + ((["RED"] * 12 + ["WHITE"] * 12) * 8)
    while len(colors) < NUM_LEDS:
        colors.extend(band)
    return colors[:NUM_LEDS]


stripColors = _placeholder_pattern()

assert len(stripColors) == NUM_LEDS, f"expected {NUM_LEDS} LEDs, got {len(stripColors)}"

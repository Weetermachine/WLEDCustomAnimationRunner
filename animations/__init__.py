"""Pluggable animation registry.

Add a new animation by dropping a module in this package and decorating a
function with @animation(...). Two styles are supported and auto-detected:

1. Stateless frame function:
       @animation("my_fx", "My Effect")
       def my_fx(frame, n_leds, ctx) -> bytes: ...
   Called once per frame with a monotonically increasing integer `frame`.

2. Stateful generator (note `yield`):
       @animation("my_fx", "My Effect")
       def my_fx(ctx):
           while True:
               ...
               yield buf            # bytes of length n_leds * 3

In both cases the function returns/yields a bytes buffer of length
n_leds * 3 (RGB). `ctx` is a live AnimationContext: ctx.speed and
ctx.brightness are updated by the runtime every frame, so read them inside
the loop to respond to settings/scheduler changes.
"""
import importlib
import inspect
import pkgutil
import threading

_REGISTRY = {}
_loaded = False
_load_lock = threading.Lock()


class AnimationContext:
    """Mutable per-run state handed to every animation."""

    __slots__ = ("n_leds", "colors", "speed", "brightness", "params")

    def __init__(self, n_leds, colors):
        self.n_leds = n_leds
        self.colors = colors      # the stripColors map (list of 'RED'/'WHITE'/'BLUE')
        self.speed = 1.0          # 0.5 - 3.0
        self.brightness = 255     # 0 - 255 master brightness
        self.params = {}          # user-configurable params (see @animation params=)


class AnimationSpec:
    def __init__(self, key, label, fn, kind, default, params):
        self.key = key
        self.label = label
        self.fn = fn
        self.kind = kind          # 'generator' | 'frame'
        self.default = default
        self.params = params      # list of param descriptors (see below)


def animation(key, label, default=False, params=None):
    """Register an animation.

    params (optional) is a list of descriptors that the UI renders as controls,
    e.g. a color picker:
        params=[{"key": "color_a", "label": "Color A",
                 "type": "color", "default": "#b22234"}]
    Supported types: "color" (hex string), "number", "text". The chosen values
    arrive in ctx.params keyed by each descriptor's "key".
    """
    def deco(fn):
        kind = "generator" if inspect.isgeneratorfunction(fn) else "frame"
        _REGISTRY[key] = AnimationSpec(key, label, fn, kind, default, params or [])
        return fn
    return deco


def hex_rgb(value):
    """'#rrggbb' (or 'rrggbb') -> (r, g, b). Falls back to black on bad input."""
    try:
        s = str(value).lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError):
        return (0, 0, 0)


def merged_params(spec, overrides):
    """Defaults from the spec, overlaid with user overrides."""
    merged = {p["key"]: p["default"] for p in spec.params}
    if overrides:
        merged.update({k: v for k, v in overrides.items() if k in merged})
    return merged


def ensure_loaded():
    """Import every submodule once so their @animation registrations run."""
    global _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        import animations as pkg
        for mod in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{__name__}.{mod.name}")
        _loaded = True


def list_animations():
    ensure_loaded()
    return [
        {"key": s.key, "label": s.label, "default": s.default, "params": s.params}
        for s in _REGISTRY.values()
    ]


def get(key):
    ensure_loaded()
    return _REGISTRY.get(key)


def default_key():
    ensure_loaded()
    for s in _REGISTRY.values():
        if s.default:
            return s.key
    return next(iter(_REGISTRY), None)

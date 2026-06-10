"""RGB ↔ RS 16-bit HSL face color conversion (uses Draw3D palette)."""

from __future__ import annotations

from src.rs2.palette import build_palette, hsl_to_rgb

_PALETTE: list[int] | None = None
_RGB_CACHE: dict[tuple[int, int, int], int] = {}


def _palette() -> list[int]:
    global _PALETTE
    if _PALETTE is None:
        _PALETTE = build_palette()
    return _PALETTE


def rgb_to_rs_hsl(r: int, g: int, b: int) -> int:
    """Map sRGB to nearest RS model face color (16-bit HSL index)."""
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    key = (r >> 3, g >> 3, b >> 3)
    cached = _RGB_CACHE.get(key)
    if cached is not None:
        return cached

    target = (r << 16) | (g << 8) | b
    palette = _palette()
    best_hsl = 0
    best_dist = float("inf")

    for index in range(65536):
        prgb = palette[index] & 0xF8F8FF
        dr = ((target >> 16) & 0xFF) - ((prgb >> 16) & 0xFF)
        dg = ((target >> 8) & 0xFF) - ((prgb >> 8) & 0xFF)
        db = (target & 0xFF) - (prgb & 0xFF)
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best_hsl = index << 8

    _RGB_CACHE[key] = best_hsl
    return best_hsl


def rs_hsl_to_rgb(hsl: int) -> tuple[int, int, int]:
    return hsl_to_rgb(hsl, _palette())


# Default RS-style browns/greys for untextured props.
DEFAULT_WEAPON_COLOR = rgb_to_rs_hsl(120, 110, 95)
DEFAULT_OBJECT_COLOR = rgb_to_rs_hsl(96, 88, 72)
DEFAULT_GREY = rgb_to_rs_hsl(128, 128, 128)

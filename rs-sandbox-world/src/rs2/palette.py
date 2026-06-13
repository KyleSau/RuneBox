"""RS HSL palette generation (matches Draw3D.setBrightness)."""

from __future__ import annotations


def _set_gamma(rgb: int, brightness: float) -> int:
    r = ((rgb >> 16) & 0xFF) / 256.0
    g = ((rgb >> 8) & 0xFF) / 256.0
    b = (rgb & 0xFF) / 256.0
    r = r ** brightness
    g = g ** brightness
    b = b ** brightness
    ir = int(r * 256.0)
    ig = int(g * 256.0)
    ib = int(b * 256.0)
    return (ir << 16) + (ig << 8) + ib


def build_palette(brightness: float = 0.8) -> list[int]:
    palette = [0] * 65536
    offset = 0
    for y in range(512):
        hue = (y // 8) / 64.0 + 0.0078125
        saturation = (y & 7) / 8.0 + 0.0625
        for x in range(128):
            lightness = x / 128.0
            r = g = b = lightness
            if saturation != 0.0:
                q = lightness * (1.0 + saturation) if lightness < 0.5 else (lightness + saturation) - (lightness * saturation)
                p = 2.0 * lightness - q
                t = hue + (1.0 / 3.0)
                if t > 1.0:
                    t -= 1.0
                d11 = hue - (1.0 / 3.0)
                if d11 < 0.0:
                    d11 += 1.0

                if 6.0 * t < 1.0:
                    r = p + (q - p) * 6.0 * t
                elif 2.0 * t < 1.0:
                    r = q
                elif 3.0 * t < 2.0:
                    r = p + (q - p) * ((2.0 / 3.0) - t) * 6.0
                else:
                    r = p

                if 6.0 * hue < 1.0:
                    g = p + (q - p) * 6.0 * hue
                elif 2.0 * hue < 1.0:
                    g = q
                elif 3.0 * hue < 2.0:
                    g = p + (q - p) * ((2.0 / 3.0) - hue) * 6.0
                else:
                    g = p

                if 6.0 * d11 < 1.0:
                    b = p + (q - p) * 6.0 * d11
                elif 2.0 * d11 < 1.0:
                    b = q
                elif 3.0 * d11 < 2.0:
                    b = p + (q - p) * ((2.0 / 3.0) - d11) * 6.0
                else:
                    b = p

            rgb = (int(r * 256) << 16) + (int(g * 256) << 8) + int(b * 256)
            rgb = _set_gamma(rgb, brightness)
            if rgb == 0:
                rgb = 1
            palette[offset] = rgb
            offset += 1
    return palette


def hsl_to_rgb(hsl: int, palette: list[int] | None = None) -> tuple[int, int, int]:
    if palette is None:
        palette = build_palette()
    # RS face colours are a full 16-bit HSL index into the 65536-entry palette
    # (hue << 10 | saturation << 7 | lightness). Indexing must use the whole
    # value; shifting it discards saturation/lightness and greys colours out.
    index = hsl & 0xFFFF
    rgb = palette[index] & 0xF8F8FF
    return (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF


_SRGB_TO_LINEAR: list[int] | None = None


def srgb_to_linear_lut() -> list[int]:
    """glTF COLOR_0 is linear; RS Draw3D palette entries are sRGB-like."""
    global _SRGB_TO_LINEAR
    if _SRGB_TO_LINEAR is None:
        _SRGB_TO_LINEAR = []
        for value in range(256):
            c = value / 255.0
            c = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            _SRGB_TO_LINEAR.append(max(0, min(255, round(c * 255.0))))
    return _SRGB_TO_LINEAR


def srgb8_to_linear8(value: int) -> int:
    return srgb_to_linear_lut()[value & 0xFF]


def srgb_rgba_to_linear8(rgba: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    lut = srgb_to_linear_lut()
    return (lut[rgba[0] & 0xFF], lut[rgba[1] & 0xFF], lut[rgba[2] & 0xFF], rgba[3])

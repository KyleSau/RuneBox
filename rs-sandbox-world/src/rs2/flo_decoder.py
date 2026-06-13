"""Decode flo.dat floor colour / texture definitions (FloType)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.rs2.buffer import Buffer


@dataclass
class FloType:
    id: int
    rgb: int = 0
    texture_id: int = -1
    occludes: bool = True
    hue: int = 0
    saturation: int = 0
    lightness: int = 0
    chroma: int = 0
    luminance: int = 0
    hsl: int = 0


def decimate_hsl(hue: int, saturation: int, lightness: int) -> int:
    if lightness > 179:
        saturation //= 2
    if lightness > 192:
        saturation //= 2
    if lightness > 217:
        saturation //= 2
    if lightness > 243:
        saturation //= 2
    return ((hue // 4) << 10) + ((saturation // 32) << 7) + (lightness // 2)


def _set_color(flo: FloType, rgb: int) -> None:
    red = ((rgb >> 16) & 0xFF) / 256.0
    green = ((rgb >> 8) & 0xFF) / 256.0
    blue = (rgb & 0xFF) / 256.0
    min_c = min(red, green, blue)
    max_c = max(red, green, blue)
    h = 0.0
    s = 0.0
    l = (min_c + max_c) / 2.0
    if min_c != max_c:
        if l < 0.5:
            s = (max_c - min_c) / (max_c + min_c)
        else:
            s = (max_c - min_c) / (2.0 - max_c - min_c)
        if red == max_c:
            h = (green - blue) / (max_c - min_c)
        elif green == max_c:
            h = 2.0 + ((blue - red) / (max_c - min_c))
        else:
            h = 4.0 + ((red - green) / (max_c - min_c))
    h /= 6.0
    flo.hue = int(h * 256.0)
    flo.saturation = int(s * 256.0)
    flo.lightness = int(l * 256.0)
    flo.saturation = max(0, min(255, flo.saturation))
    flo.lightness = max(0, min(255, flo.lightness))
    if l > 0.5:
        flo.luminance = int((1.0 - l) * s * 512.0)
    else:
        flo.luminance = int(l * s * 512.0)
    if flo.luminance < 1:
        flo.luminance = 1
    flo.chroma = int(h * flo.luminance)
    hue = flo.hue + random.randint(0, 15) - 8
    hue = max(0, min(255, hue))
    saturation = flo.saturation + random.randint(0, 47) - 24
    saturation = max(0, min(255, saturation))
    lightness = flo.lightness + random.randint(0, 47) - 24
    lightness = max(0, min(255, lightness))
    flo.hsl = decimate_hsl(hue, saturation, lightness)


def _read_flo(flo_id: int, buf: Buffer) -> FloType:
    flo = FloType(id=flo_id)
    while True:
        code = buf.read_u8()
        if code == 0:
            break
        if code == 1:
            flo.rgb = buf.read_u24()
            _set_color(flo, flo.rgb)
        elif code == 2:
            flo.texture_id = buf.read_u8()
        elif code == 3:
            pass
        elif code == 5:
            flo.occludes = False
        elif code == 6:
            buf.read_string()
        elif code == 7:
            saved = (flo.hue, flo.saturation, flo.lightness, flo.chroma)
            rgb = buf.read_u24()
            _set_color(flo, rgb)
            flo.hue, flo.saturation, flo.lightness, flo.chroma = saved
            flo.luminance = flo.chroma
        else:
            break
    return flo


def decode_flo_types(data: bytes) -> list[FloType]:
    buf = Buffer(data)
    count = buf.read_u16()
    return [_read_flo(i, buf) for i in range(count)]


def load_flo_types(cache) -> list[FloType]:
    from src.cache.file_archive import FileArchive

    raw = cache.read_archive(2)
    if not raw:
        return []
    arch = FileArchive.load(raw)
    data = arch.read("flo.dat")
    if not data:
        return []
    return decode_flo_types(data)

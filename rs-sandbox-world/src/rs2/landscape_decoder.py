"""Decode 317/377 region landscape maps (idx4 ``l{rx}_{ry}`` object placements).

Ports SceneBuilder.readLocs for a full 64×64 region file (no 8×8 chunk filter).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.rs2.buffer import Buffer
from src.rs2.loc_decoder import loc_display_name, loc_examine_text, loc_is_interactable, loc_menu_name

REGION_SIZE = 64
MAX_LOC_ID = 65535
MAX_OBJECTS = 25000


@dataclass
class LandscapeLoc:
    id: int
    x: int
    z: int
    plane: int
    kind: int
    rotation: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "z": self.z,
            "plane": self.plane,
            "kind": self.kind,
            "rot": self.rotation,
        }


def decode_landscape(data: bytes, region_x: int, region_y: int) -> list[LandscapeLoc] | None:
    """Parse object placements from decrypted ``l{rx}_{ry}`` bytes.

    Returns ``None`` if the stream does not look like a valid landscape file.
    """
    if not data:
        return None

    buf = Buffer(data)
    loc_id = -1
    objects: list[LandscapeLoc] = []

    try:
        while True:
            delta_id = buf.read_usmart()
            if delta_id == 0:
                break
            loc_id += delta_id
            if loc_id < 0 or loc_id > MAX_LOC_ID:
                return None

            loc_data = 0
            while True:
                delta_data = buf.read_usmart()
                if delta_data == 0:
                    break
                loc_data += delta_data - 1

                loc_z = loc_data & 0x3F
                loc_x = (loc_data >> 6) & 0x3F
                loc_level = loc_data >> 12
                loc_info = buf.read_u8()
                loc_kind = loc_info >> 2
                loc_rotation = loc_info & 0x3

                if loc_x >= REGION_SIZE or loc_z >= REGION_SIZE or loc_level >= 4:
                    return None
                if loc_kind > 22:
                    return None

                objects.append(
                    LandscapeLoc(
                        id=loc_id,
                        x=loc_x,
                        z=loc_z,
                        plane=loc_level,
                        kind=loc_kind,
                        rotation=loc_rotation,
                    )
                )
                if len(objects) > MAX_OBJECTS:
                    return None
    except IndexError:
        return None

    trailing = len(data) - buf.position
    if trailing > 0:
        return None

    return objects


def landscape_summary(
    objects: list[LandscapeLoc],
    region_x: int,
    region_y: int,
    loc_types: dict | None = None,
) -> dict:
    out_objects: list[dict] = []
    for o in objects:
        d = o.to_dict()
        if loc_types and o.id in loc_types:
            loc = loc_types[o.id]
            d["sizeX"] = loc.size_x
            d["sizeZ"] = loc.size_z
            d["menuName"] = loc_menu_name(loc) or ""
            d["name"] = loc_display_name(loc, kind=o.kind)
            d["examine"] = loc_examine_text(loc)
            d["interactable"] = loc_is_interactable(loc)
            d["actions"] = [a for a in (loc.actions or []) if a]
            d["debugName"] = loc.debug_name or ""
        else:
            d.setdefault("name", f"Object ({o.id})")
        out_objects.append(d)
    return {
        "regionX": region_x,
        "regionY": region_y,
        "originX": region_x * REGION_SIZE,
        "originY": region_y * REGION_SIZE,
        "count": len(objects),
        "objects": out_objects,
    }

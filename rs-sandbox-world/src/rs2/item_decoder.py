"""Item/object definition decoder (matches ObjType.read)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer


@dataclass
class ItemDefinition:
    id: int
    name: str | None = None
    examine: str | None = None
    model_id: int = 0
    male_model_id0: int = -1
    male_model_id1: int = -1
    male_model_id2: int = -1
    female_model_id0: int = -1
    female_model_id1: int = -1
    female_model_id2: int = -1
    src_color: list[int] | None = None
    dst_color: list[int] | None = None
    cost: int = 1
    stackable: bool = False
    members: bool = False
    scale_x: int = 128
    scale_y: int = 128
    scale_z: int = 128
    unknown_opcodes: list[int] = field(default_factory=list)

    def ground_model_ids(self) -> list[int]:
        ids = [self.model_id] if self.model_id > 0 else []
        return ids

    def worn_model_ids(self) -> list[int]:
        ids: list[int] = []
        for mid in (
            self.male_model_id0,
            self.male_model_id1,
            self.male_model_id2,
            self.female_model_id0,
            self.female_model_id1,
            self.female_model_id2,
        ):
            if mid > 0 and mid not in ids:
                ids.append(mid)
        return ids

    @staticmethod
    def _worn_slot_map(model0: int, model1: int, model2: int) -> dict[str, int | None]:
        """Worn model slots: body (primary), arms (secondary), extra (tertiary)."""
        return {
            "body": model0 if model0 > 0 else None,
            "arms": model1 if model1 > 0 else None,
            "extra": model2 if model2 > 0 else None,
        }

    def worn_models(self) -> dict[str, dict[str, int | None]]:
        return {
            "male": self._worn_slot_map(
                self.male_model_id0, self.male_model_id1, self.male_model_id2
            ),
            "female": self._worn_slot_map(
                self.female_model_id0, self.female_model_id1, self.female_model_id2
            ),
        }

    def recolor_pairs(self) -> list[dict[str, int]]:
        if not self.src_color or not self.dst_color:
            return []
        return [{"src": s, "dst": d} for s, d in zip(self.src_color, self.dst_color)]

    def to_dict(self) -> dict:
        worn = self.worn_models()
        return {
            "itemId": self.id,
            "name": self.name,
            "examine": self.examine,
            "modelId": self.model_id,
            "groundModelIds": self.ground_model_ids(),
            "wornModelIds": self.worn_model_ids(),
            "worn": worn,
            "recolors": self.recolor_pairs() or None,
            "cost": self.cost,
            "stackable": self.stackable,
            "members": self.members,
            "unknownOpcodes": self.unknown_opcodes or None,
        }


def decode_item(buf: Buffer) -> ItemDefinition:
    item = ItemDefinition(id=-1)
    while True:
        code = buf.read_u8()
        if code == 0:
            return item
        if code == 1:
            item.model_id = buf.read_u16()
        elif code == 2:
            item.name = buf.read_string()
        elif code == 3:
            item.examine = buf.read_string()
        elif code in (4, 5, 6, 8, 9, 10):
            buf.read_u16()
        elif code == 7:
            val = buf.read_u16()
            if val > 32767:
                val -= 0x10000
        elif code == 11:
            item.stackable = True
        elif code == 12:
            item.cost = buf.read_u32()
        elif code == 16:
            item.members = True
        elif code == 23:
            item.male_model_id0 = buf.read_u16()
            buf.read_u8()
        elif code == 24:
            item.male_model_id1 = buf.read_u16()
        elif code == 25:
            item.female_model_id0 = buf.read_u16()
            buf.read_u8()
        elif code == 26:
            item.female_model_id1 = buf.read_u16()
        elif 30 <= code < 35:
            buf.read_string()
        elif 35 <= code < 40:
            buf.read_string()
        elif code == 40:
            count = buf.read_u8()
            item.src_color = [buf.read_u16() for _ in range(count)]
            item.dst_color = [buf.read_u16() for _ in range(count)]
        elif code in (78, 79, 90, 91, 92, 93, 95, 97, 98):
            buf.read_u16()
        elif 100 <= code < 110:
            buf.read_u16()
            buf.read_u16()
        elif code == 110:
            item.scale_x = buf.read_u16()
        elif code == 111:
            item.scale_z = buf.read_u16()
        elif code == 112:
            item.scale_y = buf.read_u16()
        elif code == 113:
            buf.read_u8()
        elif code == 114:
            buf.read_u8()
        elif code == 115:
            buf.read_u8()
        else:
            item.unknown_opcodes.append(code)
            return item

"""NPC definition decoder (matches NPCType.read)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer


@dataclass
class NPCDefinition:
    id: int
    name: str | None = None
    examine: str | None = None
    model_ids: list[int] | None = None
    head_model_ids: list[int] | None = None
    seq_stand_id: int = -1
    seq_walk_id: int = -1
    seq_turn_around_id: int = -1
    seq_turn_left_id: int = -1
    seq_turn_right_id: int = -1
    level: int = -1
    size: int = 1
    color_src: list[int] | None = None
    color_dst: list[int] | None = None
    scale_xy: int = 128
    scale_z: int = 128
    options: list[str | None] = field(default_factory=lambda: [None] * 5)
    unknown_opcodes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "npcId": self.id,
            "name": self.name,
            "examine": self.examine,
            "modelIds": self.model_ids,
            "headModelIds": self.head_model_ids,
            "standAnimation": self.seq_stand_id,
            "walkAnimation": self.seq_walk_id,
            "turnAroundAnimation": self.seq_turn_around_id,
            "turnLeftAnimation": self.seq_turn_left_id,
            "turnRightAnimation": self.seq_turn_right_id,
            "combatLevel": self.level,
            "size": self.size,
            "recolors": (
                [{"src": s, "dst": d} for s, d in zip(self.color_src, self.color_dst)]
                if self.color_src and self.color_dst
                else None
            ),
            "scaleXY": self.scale_xy,
            "scaleZ": self.scale_z,
            "options": self.options,
            "unknownOpcodes": self.unknown_opcodes or None,
        }


def decode_npc(buf: Buffer) -> NPCDefinition:
    npc = NPCDefinition(id=-1)
    while True:
        code = buf.read_u8()
        if code == 0:
            return npc
        if code == 1:
            count = buf.read_u8()
            npc.model_ids = [buf.read_u16() for _ in range(count)]
        elif code == 2:
            npc.name = buf.read_string()
        elif code == 3:
            npc.examine = buf.read_string()
        elif code == 12:
            npc.size = buf.read_i8()
        elif code == 13:
            npc.seq_stand_id = buf.read_u16()
        elif code == 14:
            npc.seq_walk_id = buf.read_u16()
        elif code == 17:
            npc.seq_walk_id = buf.read_u16()
            npc.seq_turn_around_id = buf.read_u16()
            npc.seq_turn_left_id = buf.read_u16()
            npc.seq_turn_right_id = buf.read_u16()
        elif 30 <= code < 40:
            text = buf.read_string()
            if text.lower() == "hidden":
                text = None
            npc.options[code - 30] = text
        elif code == 40:
            count = buf.read_u8()
            npc.color_src = [buf.read_u16() for _ in range(count)]
            npc.color_dst = [buf.read_u16() for _ in range(count)]
        elif code == 60:
            count = buf.read_u8()
            npc.head_model_ids = [buf.read_u16() for _ in range(count)]
        elif code in (90, 91, 92):
            buf.read_u16()
        elif code == 93:
            pass
        elif code == 95:
            npc.level = buf.read_u16()
        elif code == 97:
            npc.scale_xy = buf.read_u16()
        elif code == 98:
            npc.scale_z = buf.read_u16()
        elif code == 99:
            pass
        elif code == 100:
            buf.read_u8()
        elif code == 101:
            buf.read_u8()
        elif code == 102:
            buf.read_u16()
        elif code == 103:
            buf.read_u16()
        elif code == 106:
            buf.read_u16()
            buf.read_u16()
            override_count = buf.read_u8()
            for _ in range(override_count + 1):
                val = buf.read_u16()
                if val == 65535:
                    continue
        elif code == 107:
            pass
        else:
            npc.unknown_opcodes.append(code)
            # Unknown opcode — cannot safely skip payload; stop to avoid corrupt reads.
            return npc

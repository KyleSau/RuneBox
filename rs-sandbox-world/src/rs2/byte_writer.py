"""Write helpers matching the Java Buffer smart encoding."""

from __future__ import annotations


class ByteWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write_u8(self, value: int) -> None:
        self.data.append(value & 0xFF)

    def write_u16(self, value: int) -> None:
        self.data.append((value >> 8) & 0xFF)
        self.data.append(value & 0xFF)

    def write_smart(self, value: int) -> None:
        if -64 <= value <= 63:
            self.write_u8(value + 64)
        else:
            self.write_u16(value + 49152)

    def extend(self, chunk: bytes | bytearray) -> None:
        self.data.extend(chunk)

    def __bytes__(self) -> bytes:
        return bytes(self.data)

    def __len__(self) -> int:
        return len(self.data)

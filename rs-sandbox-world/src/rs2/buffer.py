"""Binary buffer reader matching the Java Buffer class."""

from __future__ import annotations


class Buffer:
    def __init__(self, data: bytes | bytearray):
        self.data = data
        self.position = 0

    def read_u8(self) -> int:
        value = self.data[self.position]
        self.position += 1
        return value

    def read_u16(self) -> int:
        value = (self.data[self.position] << 8) | self.data[self.position + 1]
        self.position += 2
        return value

    def read_i8(self) -> int:
        value = self.data[self.position]
        self.position += 1
        if value >= 128:
            value -= 256
        return value

    def read_u32(self) -> int:
        value = int.from_bytes(self.data[self.position : self.position + 4], "big")
        self.position += 4
        return value

    def read_u24(self) -> int:
        value = (
            (self.data[self.position] << 16)
            | (self.data[self.position + 1] << 8)
            | self.data[self.position + 2]
        )
        self.position += 3
        return value

    def read_smart(self) -> int:
        if self.data[self.position] < 128:
            return self.read_u8() - 64
        return self.read_u16() - 49152

    def read_usmart(self) -> int:
        if self.data[self.position] < 128:
            return self.read_u8()
        return self.read_u16() - 32768

    def write_u8(self, value: int) -> None:
        self.data[self.position] = value & 0xFF
        self.position += 1

    def write_u16_le(self, value: int) -> None:
        self.data[self.position] = value & 0xFF
        self.data[self.position + 1] = (value >> 8) & 0xFF
        self.position += 2

    def write_u32(self, value: int) -> None:
        self.data[self.position] = (value >> 24) & 0xFF
        self.data[self.position + 1] = (value >> 16) & 0xFF
        self.data[self.position + 2] = (value >> 8) & 0xFF
        self.data[self.position + 3] = value & 0xFF
        self.position += 4

    def write_u32_le(self, value: int) -> None:
        self.data[self.position] = value & 0xFF
        self.data[self.position + 1] = (value >> 8) & 0xFF
        self.data[self.position + 2] = (value >> 16) & 0xFF
        self.data[self.position + 3] = (value >> 24) & 0xFF
        self.position += 4

    def read_string(self) -> str:
        start = self.position
        while self.data[self.position] != ord("\n"):
            self.position += 1
        result = self.data[start : self.position].decode("latin-1")
        self.position += 1
        return result

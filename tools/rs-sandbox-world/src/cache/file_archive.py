"""Jagex FileArchive decoder — Python fallback when Java bridge is unavailable."""

from __future__ import annotations

import bz2
from dataclasses import dataclass


def _decompress_bzip2(src: bytes, offset: int, length: int) -> bytes:
    payload = b"BZh1" + src[offset : offset + length]
    return bz2.decompress(payload)


@dataclass
class FileArchive:
    data: bytes
    file_count: int
    file_hash: list[int]
    file_size_inflated: list[int]
    file_size_deflated: list[int]
    file_offset: list[int]
    unpacked: bool

    @classmethod
    def load(cls, src: bytes) -> "FileArchive":
        pos = 0
        unpacked_size = int.from_bytes(src[pos : pos + 3], "big")
        pos += 3
        packed_size = int.from_bytes(src[pos : pos + 3], "big")
        pos += 3

        if packed_size != unpacked_size:
            data = _decompress_bzip2(src, 6, packed_size)
            buffer = data
            pos = 0
            unpacked = True
        else:
            data = src
            buffer = src
            # Java keeps buffer.position at 6 after reading the two size fields.
            pos = 6
            unpacked = False

        file_count = int.from_bytes(buffer[pos : pos + 2], "big")
        pos += 2

        file_hash: list[int] = []
        file_size_inflated: list[int] = []
        file_size_deflated: list[int] = []
        file_offset: list[int] = []

        # Java: offset = buffer.position + (fileCount * 10) before reading entries.
        data_start = pos + file_count * 10

        for _ in range(file_count):
            file_hash.append(int.from_bytes(buffer[pos : pos + 4], "big", signed=True))
            pos += 4
            file_size_inflated.append(int.from_bytes(buffer[pos : pos + 3], "big"))
            pos += 3
            file_size_deflated.append(int.from_bytes(buffer[pos : pos + 3], "big"))
            pos += 3

        offset = data_start
        for i in range(file_count):
            file_offset.append(offset)
            offset += file_size_deflated[i]

        return cls(
            data=buffer if unpacked else src,
            file_count=file_count,
            file_hash=file_hash,
            file_size_inflated=file_size_inflated,
            file_size_deflated=file_size_deflated,
            file_offset=file_offset,
            unpacked=unpacked,
        )

    def _hash_name(self, name: str) -> int:
        value = 0
        for ch in name.upper():
            # Java FileArchive uses 32-bit signed int overflow.
            value = (value * 61 + ord(ch) - 32) & 0xFFFFFFFF
            if value >= 0x80000000:
                value -= 0x100000000
        return value

    def read(self, name: str) -> bytes | None:
        target = self._hash_name(name)
        for i in range(self.file_count):
            if self.file_hash[i] != target:
                continue
            dst = bytearray(self.file_size_inflated[i])
            if not self.unpacked:
                raw = _decompress_bzip2(
                    self.data,
                    self.file_offset[i],
                    self.file_size_deflated[i],
                )
                dst[: len(raw)] = raw
            else:
                start = self.file_offset[i]
                end = start + self.file_size_inflated[i]
                dst[:] = self.data[start:end]
            return bytes(dst)
        return None

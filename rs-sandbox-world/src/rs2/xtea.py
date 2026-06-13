"""Standard RS XTEA block decrypt (128-bit key, 32 rounds)."""

from __future__ import annotations

import struct
from typing import Sequence

_DELTA = 0x9E3779B9
_ROUNDS = 32


def decrypt_block(v0: int, v1: int, key: Sequence[int]) -> tuple[int, int]:
    """Decrypt one 64-bit block. Key is four 32-bit unsigned ints."""
    if len(key) != 4:
        raise ValueError("XTEA key must have exactly 4 integers")
    k0, k1, k2, k3 = (int(x) & 0xFFFFFFFF for x in key)
    sum_ = (_DELTA * _ROUNDS) & 0xFFFFFFFF
    y = v0 & 0xFFFFFFFF
    z = v1 & 0xFFFFFFFF
    for _ in range(_ROUNDS):
        z = (z - (((y << 4 ^ y >> 5) + y) ^ (sum_ + (k3, k2, k1, k0)[sum_ >> 11 & 3]))) & 0xFFFFFFFF
        sum_ = (sum_ - _DELTA) & 0xFFFFFFFF
        y = (y - (((z << 4 ^ z >> 5) + z) ^ (sum_ + (k0, k1, k2, k3)[sum_ & 3]))) & 0xFFFFFFFF
    return y, z


def decrypt(data: bytes, key: Sequence[int]) -> bytes:
    """Decrypt ``data`` in place semantics; length must be a multiple of 8."""
    if len(data) % 8:
        raise ValueError(f"XTEA ciphertext length must be multiple of 8, got {len(data)}")
    out = bytearray(len(data))
    for offset in range(0, len(data), 8):
        v0, v1 = struct.unpack_from(">II", data, offset)
        d0, d1 = decrypt_block(v0, v1, key)
        struct.pack_into(">II", out, offset, d0, d1)
    return bytes(out)

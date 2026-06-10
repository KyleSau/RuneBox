"""RS biquad-style sound filter (ports SoundFilter.java)."""

from __future__ import annotations

import math

from src.rs2.buffer import Buffer
from src.rs2.sound_envelope import SoundEnvelope


class SoundFilter:
    coefficient: list[list[float]] = [[0.0] * 8, [0.0] * 8]
    coefficient16: list[list[int]] = [[0] * 8, [0] * 8]
    unity: float = 0.0
    unity16: int = 0

    def __init__(self) -> None:
        self.pairs = [0, 0]
        self.frequencies = [[[0] * 4 for _ in range(2)] for _ in range(2)]
        self.ranges = [[[0] * 4 for _ in range(2)] for _ in range(2)]
        self.unities = [0, 0]

    def gain(self, direction: int, pair: int, delta: float) -> float:
        g = self.ranges[direction][0][pair] + (
            delta * (self.ranges[direction][1][pair] - self.ranges[direction][0][pair])
        )
        g *= 0.001525879
        return 1.0 - math.pow(10.0, -g / 20.0)

    def normalize(self, f: float) -> float:
        return (32.7032 * math.pow(2.0, f) * 3.141593) / 11025.0

    def phase(self, direction: int, pair: int, delta: float) -> float:
        f1 = self.frequencies[direction][0][pair] + (
            delta * (self.frequencies[direction][1][pair] - self.frequencies[direction][0][pair])
        )
        f1 *= 0.0001220703
        return self.normalize(f1)

    def evaluate(self, direction: int, delta: float) -> int:
        if direction == 0:
            u = self.unities[0] + (self.unities[1] - self.unities[0]) * delta
            u *= 0.003051758
            SoundFilter.unity = math.pow(0.1, u / 20.0)
            SoundFilter.unity16 = int(SoundFilter.unity * 65536.0)

        if self.pairs[direction] == 0:
            return 0

        u = self.gain(direction, 0, delta)
        SoundFilter.coefficient[direction][0] = -2.0 * u * math.cos(self.phase(direction, 0, delta))
        SoundFilter.coefficient[direction][1] = u * u

        for pair in range(1, self.pairs[direction]):
            g = self.gain(direction, pair, delta)
            a = -2.0 * g * math.cos(self.phase(direction, pair, delta))
            b = g * g
            SoundFilter.coefficient[direction][pair * 2 + 1] = (
                SoundFilter.coefficient[direction][pair * 2 - 1] * b
            )
            SoundFilter.coefficient[direction][pair * 2] = (
                SoundFilter.coefficient[direction][pair * 2 - 1] * a
                + SoundFilter.coefficient[direction][pair * 2 - 2] * b
            )
            for j in range(pair * 2 - 1, 1, -1):
                SoundFilter.coefficient[direction][j] += (
                    SoundFilter.coefficient[direction][j - 1] * a
                    + SoundFilter.coefficient[direction][j - 2] * b
                )
            SoundFilter.coefficient[direction][1] += (
                SoundFilter.coefficient[direction][0] * a + b
            )
            SoundFilter.coefficient[direction][0] += a

        if direction == 0:
            for l in range(self.pairs[0] * 2):
                SoundFilter.coefficient[0][l] *= SoundFilter.unity

        for pair in range(self.pairs[direction] * 2):
            SoundFilter.coefficient16[direction][pair] = int(
                SoundFilter.coefficient[direction][pair] * 65536.0
            )

        return self.pairs[direction] * 2

    def read(self, buf: Buffer, envelope: SoundEnvelope) -> None:
        count = buf.read_u8()
        self.pairs[0] = count >> 4
        self.pairs[1] = count & 0xF

        if count != 0:
            self.unities[0] = buf.read_u16()
            self.unities[1] = buf.read_u16()
            migration = buf.read_u8()

            for direction in range(2):
                for pair in range(self.pairs[direction]):
                    self.frequencies[direction][0][pair] = buf.read_u16()
                    self.ranges[direction][0][pair] = buf.read_u16()

            for direction in range(2):
                for pair in range(self.pairs[direction]):
                    bit = 1 << ((direction * 4) + pair)
                    if migration & bit:
                        self.frequencies[direction][1][pair] = buf.read_u16()
                        self.ranges[direction][1][pair] = buf.read_u16()
                    else:
                        self.frequencies[direction][1][pair] = self.frequencies[direction][0][pair]
                        self.ranges[direction][1][pair] = self.ranges[direction][0][pair]

            if migration != 0 or self.unities[1] != self.unities[0]:
                envelope.read_shape(buf)
        else:
            self.unities[0] = 0
            self.unities[1] = 0

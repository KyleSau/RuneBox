"""RS sound envelope (ports SoundEnvelope.java)."""

from __future__ import annotations

from src.rs2.buffer import Buffer


class SoundEnvelope:
    def __init__(self) -> None:
        self.length = 0
        self.shape_delta: list[int] = []
        self.shape_peak: list[int] = []
        self.start = 0
        self.end = 0
        self.form = 0
        self.threshold = 0
        self.position = 0
        self.delta = 0
        self.amplitude = 0
        self.ticks = 0

    def read(self, buf: Buffer) -> None:
        self.form = buf.read_u8()
        self.start = buf.read_u32()
        self.end = buf.read_u32()
        self.read_shape(buf)

    def read_shape(self, buf: Buffer) -> None:
        self.length = buf.read_u8()
        self.shape_delta = []
        self.shape_peak = []
        for _ in range(self.length):
            self.shape_delta.append(buf.read_u16())
            self.shape_peak.append(buf.read_u16())

    def reset(self) -> None:
        self.threshold = 0
        self.position = 0
        self.delta = 0
        self.amplitude = 0
        self.ticks = 0

    def evaluate(self, delta: int) -> int:
        if self.ticks >= self.threshold:
            self.amplitude = self.shape_peak[self.position] << 15
            self.position += 1
            if self.position >= self.length:
                self.position = self.length - 1
            self.threshold = int((self.shape_delta[self.position] / 65536.0) * delta)
            if self.threshold > self.ticks:
                self.delta = (
                    (self.shape_peak[self.position] << 15) - self.amplitude
                ) // (self.threshold - self.ticks)
        self.amplitude += self.delta
        self.ticks += 1
        return (self.amplitude - self.delta) >> 15

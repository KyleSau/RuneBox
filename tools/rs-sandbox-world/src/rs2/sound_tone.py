"""RS procedural sound tone (ports SoundTone.java)."""

from __future__ import annotations

import math
import random

from src.rs2.buffer import Buffer
from src.rs2.sound_envelope import SoundEnvelope
from src.rs2.sound_filter import SoundFilter

_TMP_PHASES = [0] * 5
_TMP_DELAYS = [0] * 5
_TMP_VOLUMES = [0] * 5
_TMP_SEMITONES = [0] * 5
_TMP_STARTS = [0] * 5


class SoundTone:
    buffer: list[int] = []
    noise: list[int] = []
    sin: list[int] = []

    @classmethod
    def init(cls) -> None:
        cls.noise = []
        for _ in range(32768):
            cls.noise.append(1 if random.random() > 0.5 else -1)
        cls.sin = []
        for j in range(32768):
            cls.sin.append(int(math.sin(j / 5215.1903) * 16384.0))
        cls.buffer = [0] * (22050 * 10)

    def __init__(self) -> None:
        self.harmonic_volume = [0] * 5
        self.harmonic_semitone = [0] * 5
        self.harmonic_delay = [0] * 5
        self.frequency_base: SoundEnvelope | None = None
        self.amplitude_base: SoundEnvelope | None = None
        self.frequency_mod_rate: SoundEnvelope | None = None
        self.frequency_mod_range: SoundEnvelope | None = None
        self.amplitude_mod_rate: SoundEnvelope | None = None
        self.amplitude_mod_range: SoundEnvelope | None = None
        self.release: SoundEnvelope | None = None
        self.attack: SoundEnvelope | None = None
        self.reverb_delay = 0
        self.reverb_volume = 100
        self.filter = SoundFilter()
        self.filter_range = SoundEnvelope()
        self.length = 500
        self.start = 0

    def generate_samples(self, sample_count: int, length: int) -> list[int]:
        buf = SoundTone.buffer
        for sample in range(sample_count):
            buf[sample] = 0

        if length < 10:
            return buf

        samples_per_step = sample_count / float(length)

        self.frequency_base.reset()
        self.amplitude_base.reset()

        frequency_start = 0
        frequency_duration = 0
        frequency_phase = 0

        if self.frequency_mod_rate is not None:
            self.frequency_mod_rate.reset()
            self.frequency_mod_range.reset()
            frequency_start = int(
                (self.frequency_mod_rate.end - self.frequency_mod_rate.start)
                * 32.768
                / samples_per_step
            )
            frequency_duration = int(
                self.frequency_mod_rate.start * 32.768 / samples_per_step
            )

        amplitude_start = 0
        amplitude_duration = 0
        amplitude_phase = 0

        if self.amplitude_mod_rate is not None:
            self.amplitude_mod_rate.reset()
            self.amplitude_mod_range.reset()
            amplitude_start = int(
                (self.amplitude_mod_rate.end - self.amplitude_mod_rate.start)
                * 32.768
                / samples_per_step
            )
            amplitude_duration = int(
                self.amplitude_mod_rate.start * 32.768 / samples_per_step
            )

        for harmonic in range(5):
            if self.harmonic_volume[harmonic] != 0:
                _TMP_PHASES[harmonic] = 0
                _TMP_DELAYS[harmonic] = int(self.harmonic_delay[harmonic] * samples_per_step)
                _TMP_VOLUMES[harmonic] = (self.harmonic_volume[harmonic] << 14) // 100
                _TMP_SEMITONES[harmonic] = int(
                    (self.frequency_base.end - self.frequency_base.start)
                    * 32.768
                    * math.pow(1.0057929410678534, self.harmonic_semitone[harmonic])
                    / samples_per_step
                )
                _TMP_STARTS[harmonic] = int(
                    self.frequency_base.start * 32.768 / samples_per_step
                )

        for sample in range(sample_count):
            frequency = self.frequency_base.evaluate(sample_count)
            amplitude = self.amplitude_base.evaluate(sample_count)

            if self.frequency_mod_rate is not None:
                rate = self.frequency_mod_rate.evaluate(sample_count)
                range_ = self.frequency_mod_range.evaluate(sample_count)
                frequency += self._generate_wave(
                    self.frequency_mod_rate.form, frequency_phase, range_
                ) >> 1
                frequency_phase += ((rate * frequency_start) >> 16) + frequency_duration

            if self.amplitude_mod_rate is not None:
                rate = self.amplitude_mod_rate.evaluate(sample_count)
                range_ = self.amplitude_mod_range.evaluate(sample_count)
                amplitude = (
                    amplitude
                    * (
                        (
                            self._generate_wave(
                                self.amplitude_mod_rate.form, amplitude_phase, range_
                            )
                            >> 1
                        )
                        + 32768
                    )
                    >> 15
                )
                amplitude_phase += ((rate * amplitude_start) >> 16) + amplitude_duration

            for harmonic in range(5):
                if self.harmonic_volume[harmonic] != 0:
                    position = sample + _TMP_DELAYS[harmonic]
                    if position < sample_count:
                        buf[position] += self._generate_wave(
                            self.frequency_base.form,
                            _TMP_PHASES[harmonic],
                            (amplitude * _TMP_VOLUMES[harmonic]) >> 15,
                        )
                        _TMP_PHASES[harmonic] += (
                            ((frequency * _TMP_SEMITONES[harmonic]) >> 16) + _TMP_STARTS[harmonic]
                        )

        if self.release is not None:
            self.release.reset()
            self.attack.reset()
            counter = 0
            muted = True
            for sample in range(sample_count):
                release_value = self.release.evaluate(sample_count)
                attack_value = self.attack.evaluate(sample_count)
                if muted:
                    threshold = self.release.start + (
                        (self.release.end - self.release.start) * release_value
                    ) >> 8
                else:
                    threshold = self.release.start + (
                        (self.release.end - self.release.start) * attack_value
                    ) >> 8
                counter += 256
                if counter >= threshold:
                    counter = 0
                    muted = not muted
                if muted:
                    buf[sample] = 0

        if self.reverb_delay > 0 and self.reverb_volume > 0:
            start = int(self.reverb_delay * samples_per_step)
            for sample in range(start, sample_count):
                buf[sample] += (buf[sample - start] * self.reverb_volume) // 100

        if self.filter.pairs[0] > 0 or self.filter.pairs[1] > 0:
            self.filter_range.reset()
            range_ = self.filter_range.evaluate(sample_count + 1)
            forward = self.filter.evaluate(0, range_ / 65536.0)
            backward = self.filter.evaluate(1, range_ / 65536.0)

            if sample_count >= forward + backward:
                index = 0
                interval = backward
                if interval > sample_count - forward:
                    interval = sample_count - forward

                while index < interval:
                    sample_val = (buf[index + forward] * SoundFilter.unity16) >> 16
                    for offset in range(forward):
                        sample_val += (
                            buf[index + forward - 1 - offset]
                            * SoundFilter.coefficient16[0][offset]
                        ) >> 16
                    for offset in range(index):
                        sample_val -= (
                            buf[index - 1 - offset] * SoundFilter.coefficient16[1][offset]
                        ) >> 16
                    buf[index] = sample_val
                    range_ = self.filter_range.evaluate(sample_count + 1)
                    index += 1

                interval = 128
                while True:
                    if interval > sample_count - forward:
                        interval = sample_count - forward
                    while index < interval:
                        sample_val = (buf[index + forward] * SoundFilter.unity16) >> 16
                        for offset in range(forward):
                            sample_val += (
                                buf[index + forward - 1 - offset]
                                * SoundFilter.coefficient16[0][offset]
                            ) >> 16
                        for offset in range(backward):
                            sample_val -= (
                                buf[index - 1 - offset]
                                * SoundFilter.coefficient16[1][offset]
                            ) >> 16
                        buf[index] = sample_val
                        range_ = self.filter_range.evaluate(sample_count + 1)
                        index += 1
                    if index >= sample_count - forward:
                        break
                    forward = self.filter.evaluate(0, range_ / 65536.0)
                    backward = self.filter.evaluate(1, range_ / 65536.0)
                    interval += 128

                while index < sample_count:
                    sample_val = 0
                    for offset in range(index + forward - sample_count, forward):
                        sample_val += (
                            buf[index + forward - 1 - offset]
                            * SoundFilter.coefficient16[0][offset]
                        ) >> 16
                    for offset in range(backward):
                        sample_val -= (
                            buf[index - 1 - offset] * SoundFilter.coefficient16[1][offset]
                        ) >> 16
                    buf[index] = sample_val
                    self.filter_range.evaluate(sample_count + 1)
                    index += 1

        for sample in range(sample_count):
            if buf[sample] < -32768:
                buf[sample] = -32768
            if buf[sample] > 32767:
                buf[sample] = 32767

        return buf

    def _generate_wave(self, form: int, phase: int, amplitude: int) -> int:
        if form == 1:
            return amplitude if (phase & 0x7FFF) < 16384 else -amplitude
        if form == 2:
            return (SoundTone.sin[phase & 0x7FFF] * amplitude) >> 14
        if form == 3:
            return (((phase & 0x7FFF) * amplitude) >> 14) - amplitude
        if form == 4:
            return SoundTone.noise[(phase // 2607) & 0x7FFF] * amplitude
        return 0

    def read(self, buf: Buffer) -> None:
        self.frequency_base = SoundEnvelope()
        self.frequency_base.read(buf)
        self.amplitude_base = SoundEnvelope()
        self.amplitude_base.read(buf)

        if buf.read_u8() != 0:
            buf.position -= 1
            self.frequency_mod_rate = SoundEnvelope()
            self.frequency_mod_rate.read(buf)
            self.frequency_mod_range = SoundEnvelope()
            self.frequency_mod_range.read(buf)
        else:
            self.frequency_mod_rate = None
            self.frequency_mod_range = None

        if buf.read_u8() != 0:
            buf.position -= 1
            self.amplitude_mod_rate = SoundEnvelope()
            self.amplitude_mod_rate.read(buf)
            self.amplitude_mod_range = SoundEnvelope()
            self.amplitude_mod_range.read(buf)
        else:
            self.amplitude_mod_rate = None
            self.amplitude_mod_range = None

        if buf.read_u8() != 0:
            buf.position -= 1
            self.release = SoundEnvelope()
            self.release.read(buf)
            self.attack = SoundEnvelope()
            self.attack.read(buf)
        else:
            self.release = None
            self.attack = None

        for i in range(10):
            volume = buf.read_usmart()
            if volume == 0:
                break
            self.harmonic_volume[i] = volume
            self.harmonic_semitone[i] = buf.read_smart()
            self.harmonic_delay[i] = buf.read_usmart()

        self.reverb_delay = buf.read_usmart()
        self.reverb_volume = buf.read_usmart()
        self.length = buf.read_u16()
        self.start = buf.read_u16()
        self.filter = SoundFilter()
        self.filter_range = SoundEnvelope()
        self.filter.read(buf, self.filter_range)

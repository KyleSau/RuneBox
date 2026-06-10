"""RS sound track: procedural synth + WAV output (ports SoundTrack.java)."""

from __future__ import annotations

import struct

from src.rs2.buffer import Buffer
from src.rs2.sound_tone import SoundTone

_WAVE_BYTES = bytearray(441000)


class SoundTrack:
    tracks: dict[int, SoundTrack] = {}
    delays: dict[int, int] = {}

    def __init__(self) -> None:
        self.tones: list[SoundTone | None] = [None] * 10
        self.loop_begin = 0
        self.loop_end = 0

    @classmethod
    def unpack(cls, data: bytes) -> None:
        SoundTone.init()
        cls.tracks.clear()
        cls.delays.clear()
        buf = Buffer(data)
        while True:
            sound_id = buf.read_u16()
            if sound_id == 65535:
                return
            track = SoundTrack()
            track.read(buf)
            cls.tracks[sound_id] = track
            cls.delays[sound_id] = track.trim()

    @classmethod
    def generate_wav(cls, sound_id: int, loop_count: int = 1) -> bytes | None:
        track = cls.tracks.get(sound_id)
        if track is None:
            return None
        pcm_len = track._synthesize(loop_count)
        if pcm_len <= 0:
            return None
        return track._build_wav(pcm_len)

    def read(self, buf: Buffer) -> None:
        for tone in range(10):
            if buf.read_u8() != 0:
                buf.position -= 1
                self.tones[tone] = SoundTone()
                self.tones[tone].read(buf)
            else:
                self.tones[tone] = None
        self.loop_begin = buf.read_u16()
        self.loop_end = buf.read_u16()

    def trim(self) -> int:
        start = 9999999
        for tone in self.tones:
            if tone is not None and (tone.start // 20) < start:
                start = tone.start // 20
        if self.loop_begin < self.loop_end and (self.loop_begin // 20) < start:
            start = self.loop_begin // 20
        if start == 9999999 or start == 0:
            return 0
        for tone in self.tones:
            if tone is not None:
                tone.start -= start * 20
        if self.loop_begin < self.loop_end:
            self.loop_begin -= start * 20
            self.loop_end -= start * 20
        return start

    def _synthesize(self, loop_count: int) -> int:
        duration = 0
        for tone in self.tones:
            if tone is not None and (tone.length + tone.start) > duration:
                duration = tone.length + tone.start
        if duration == 0:
            return 0

        sample_count = (22050 * duration) // 1000
        loop_start = (22050 * self.loop_begin) // 1000
        loop_stop = (22050 * self.loop_end) // 1000

        if loop_start < 0 or loop_stop < 0 or loop_stop > sample_count or loop_start >= loop_stop:
            loop_count = 0

        total_sample_count = sample_count + (loop_stop - loop_start) * (loop_count - 1)

        for sample in range(44, total_sample_count + 44):
            _WAVE_BYTES[sample] = 128

        for tone in self.tones:
            if tone is None:
                continue
            tone_sample_count = (tone.length * 22050) // 1000
            start = (tone.start * 22050) // 1000
            samples = tone.generate_samples(tone_sample_count, tone.length)
            for sample in range(tone_sample_count):
                idx = sample + start + 44
                _WAVE_BYTES[idx] = (_WAVE_BYTES[idx] + (samples[sample] >> 8)) & 0xFF

        if loop_count > 1:
            loop_start += 44
            loop_stop += 44
            sample_count += 44
            total_sample_count += 44
            end_offset = total_sample_count - sample_count
            for sample in range(sample_count - 1, loop_stop - 1, -1):
                _WAVE_BYTES[sample + end_offset] = _WAVE_BYTES[sample]
            for loop in range(1, loop_count):
                offset = (loop_stop - loop_start) * loop
                for sample in range(loop_start, loop_stop):
                    _WAVE_BYTES[sample + offset] = _WAVE_BYTES[sample]
            total_sample_count -= 44

        return total_sample_count

    def _build_wav(self, pcm_len: int) -> bytes:
        # RS synth is 8-bit unsigned (silence = 128). Browsers handle 16-bit PCM
        # more reliably than 8-bit WAV in <audio>, so expand before writing the header.
        u8 = _WAVE_BYTES[44 : 44 + pcm_len]
        pcm16 = bytearray(pcm_len * 2)
        for i, sample in enumerate(u8):
            s16 = (sample - 128) * 256
            if s16 < -32768:
                s16 = -32768
            elif s16 > 32767:
                s16 = 32767
            struct.pack_into("<h", pcm16, i * 2, s16)
        data_len = len(pcm16)
        out = bytearray(44 + data_len)
        struct.pack_into("<I", out, 0, 0x46464952)  # RIFF
        struct.pack_into("<I", out, 4, 36 + data_len)
        struct.pack_into("<I", out, 8, 0x45564157)  # WAVE
        struct.pack_into("<I", out, 12, 0x20746D66)  # fmt
        struct.pack_into("<I", out, 16, 16)
        struct.pack_into("<H", out, 20, 1)  # PCM
        struct.pack_into("<H", out, 22, 1)  # mono
        struct.pack_into("<I", out, 24, 22050)
        struct.pack_into("<I", out, 28, 22050)
        struct.pack_into("<H", out, 32, 2)  # block align
        struct.pack_into("<H", out, 34, 16)  # 16-bit
        struct.pack_into("<I", out, 36, 0x61746164)  # data
        struct.pack_into("<I", out, 40, data_len)
        out[44:] = pcm16
        return bytes(out)

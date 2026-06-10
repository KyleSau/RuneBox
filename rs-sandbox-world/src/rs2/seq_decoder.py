"""Decode RS animation data: sequences (seq.dat), skeletons and frame
transforms (on-demand frame archive). Ports SeqType.java, SeqSkeleton.java and
SeqTransform.java from the 317 client.

A *sequence* (SeqType) is a list of frame transform ids + durations. A *frame
file* (read via ``CacheReader.read_animation``) contains one skeleton plus many
transforms, each tagged with its global transform id. A *transform* lists, per
skeleton base, the x/y/z parameters; the base's type (0 base, 1 translate,
2 rotate, 3 scale, 5 alpha) and labels say how to apply them to a model's
labelled vertices.
"""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass, field

from src.rs2.buffer import Buffer


def _maybe_gunzip(data: bytes) -> bytes:
    """Frame files come back gzip-compressed from read_animation; decompress."""
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            return gzip.decompress(data)
        except Exception:
            return zlib.decompress(data, 47)
    return data

OP_BASE = 0
OP_TRANSLATE = 1
OP_ROTATE = 2
OP_SCALE = 3
OP_ALPHA = 5


@dataclass
class SeqType:
    frame_count: int = 0
    transform_ids: list[int] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)
    loop_frame_count: int = -1


@dataclass
class SeqSkeleton:
    base_types: list[int]
    base_labels: list[list[int]]


@dataclass
class SeqTransform:
    skeleton: SeqSkeleton
    delay: int
    bases: list[int]
    x: list[int]
    y: list[int]
    z: list[int]


def decode_seq_types(seq_dat: bytes) -> dict[int, SeqType]:
    buf = Buffer(seq_dat)
    count = buf.read_u16()
    seqs: dict[int, SeqType] = {}
    for i in range(count):
        seqs[i] = _decode_seq(buf)
    return seqs


def _decode_seq(buf: Buffer) -> SeqType:
    seq = SeqType()
    while True:
        code = buf.read_u8()
        if code == 0:
            break
        if code == 1:
            n = buf.read_u8()
            seq.frame_count = n
            seq.transform_ids = [0] * n
            seq.durations = [0] * n
            for f in range(n):
                seq.transform_ids[f] = buf.read_u16()
                aux = buf.read_u16()  # auxiliary transform id (unused here)
                if aux == 65535:
                    aux = -1
                seq.durations[f] = buf.read_u16()
        elif code == 2:
            seq.loop_frame_count = buf.read_u16()
        elif code == 3:
            n = buf.read_u8()
            for _ in range(n):
                buf.read_u8()
        elif code == 4:
            pass
        elif code == 5:
            buf.read_u8()
        elif code == 6:
            buf.read_u16()
        elif code == 7:
            buf.read_u16()
        elif code == 8:
            buf.read_u8()
        elif code == 9:
            buf.read_u8()
        elif code == 10:
            buf.read_u8()
        elif code == 11:
            buf.read_u8()
        elif code == 12:
            buf.read_u32()
        else:  # pragma: no cover - defensive
            raise ValueError(f"unrecognised seq code {code}")
    if seq.frame_count == 0:
        seq.frame_count = 1
        seq.transform_ids = [-1]
        seq.durations = [-1]
    return seq


def _decode_skeleton(buf: Buffer) -> SeqSkeleton:
    length = buf.read_u8()
    base_types = [buf.read_u8() for _ in range(length)]
    base_labels: list[list[int]] = []
    for _ in range(length):
        count = buf.read_u8()
        base_labels.append([buf.read_u8() for _ in range(count)])
    return SeqSkeleton(base_types, base_labels)


def unpack_transforms(src: bytes, out: dict[int, SeqTransform]) -> None:
    """Unpack every transform in one frame file into ``out`` keyed by global id.
    Ports SeqTransform.unpack."""
    src = _maybe_gunzip(src)
    offsets = Buffer(src)
    offsets.position = len(src) - 8

    header = Buffer(src)
    tran1 = Buffer(src)
    tran2 = Buffer(src)
    delay = Buffer(src)
    skel = Buffer(src)

    pos = 0
    header.position = pos
    pos += offsets.read_u16() + 2
    tran1.position = pos
    pos += offsets.read_u16()
    tran2.position = pos
    pos += offsets.read_u16()
    delay.position = pos
    pos += offsets.read_u16()
    skel.position = pos

    skeleton = _decode_skeleton(skel)

    frame_count = header.read_u16()
    for _ in range(frame_count):
        transform_id = header.read_u16()
        d = delay.read_u8()
        base_count = header.read_u8()

        bases: list[int] = []
        xs: list[int] = []
        ys: list[int] = []
        zs: list[int] = []
        last_base = -1

        for base in range(base_count):
            flags = tran1.read_u8()
            if flags <= 0:
                continue

            if skeleton.base_types[base] != OP_BASE:
                # Insert any skipped ORIGIN bases.
                for cur in range(base - 1, last_base, -1):
                    if skeleton.base_types[cur] == OP_BASE:
                        bases.append(cur)
                        xs.append(0)
                        ys.append(0)
                        zs.append(0)
                        break

            default = 128 if skeleton.base_types[base] == OP_SCALE else 0
            bases.append(base)
            xs.append(tran2.read_smart() if (flags & 1) else default)
            ys.append(tran2.read_smart() if (flags & 2) else default)
            zs.append(tran2.read_smart() if (flags & 4) else default)
            last_base = base

        out[transform_id] = SeqTransform(skeleton, d, bases, xs, ys, zs)


def load_all_transforms(read_animation, max_files: int = 5000) -> dict[int, SeqTransform]:
    """Iterate the frame archive, unpacking every file into a global id->transform
    map. ``read_animation`` is ``CacheReader.read_animation``."""
    out: dict[int, SeqTransform] = {}
    misses = 0
    for file_id in range(max_files):
        try:
            data = read_animation(file_id)
        except Exception:
            data = None
        if not data:
            misses += 1
            if misses > 64:
                break
            continue
        misses = 0
        try:
            unpack_transforms(data, out)
        except Exception:
            continue
    return out

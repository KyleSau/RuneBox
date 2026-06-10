"""Classic Jagex FileStore reader — Python fallback when Java bridge is unavailable."""

from __future__ import annotations

from pathlib import Path


class FileStore:
    BUF = bytearray(520)

    def __init__(self, dat_path: Path, idx_path: Path, store_id: int, max_file_size: int = 700_000):
        self.dat_path = dat_path
        self.idx_path = idx_path
        self.store_id = store_id
        self.max_file_size = max_file_size

    def read(self, file_id: int) -> bytes | None:
        idx = self.idx_path.open("rb")
        dat = self.dat_path.open("rb")
        try:
            idx.seek(file_id * 6)
            header = idx.read(6)
            if len(header) < 6:
                return None

            size = (header[0] << 16) | (header[1] << 8) | header[2]
            sector = (header[3] << 16) | (header[4] << 8) | header[5]

            if size <= 0 or size > self.max_file_size:
                return None
            if sector <= 0:
                return None

            data = bytearray(size)
            position = 0
            part = 0

            while position < size:
                dat.seek(sector * 520)
                chunk = dat.read(520)
                if len(chunk) < 8:
                    return None

                sector_file = (chunk[0] << 8) | chunk[1]
                sector_part = (chunk[2] << 8) | chunk[3]
                next_sector = (chunk[4] << 16) | (chunk[5] << 8) | chunk[6]
                sector_store = chunk[7]

                if sector_file != file_id or sector_part != part or sector_store != self.store_id:
                    return None

                available = min(512, size - position)
                data[position : position + available] = chunk[8 : 8 + available]
                position += available
                part += 1
                sector = next_sector
                if sector == 0 and position < size:
                    return None

            return bytes(data)
        finally:
            idx.close()
            dat.close()

    def file_count(self) -> int:
        return self.idx_path.stat().st_size // 6

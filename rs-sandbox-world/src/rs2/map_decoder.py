"""Decode 317/377 region terrain maps (idx4 ``m{rx}_{ry}`` files)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer

REGION_SIZE = 64
PLANE_COUNT = 4
CORNER_GRID = REGION_SIZE + 1

# Jagex procedural height constants (Scene/Region class).
_HEIGHT_SEED_X = 932731
_HEIGHT_SEED_Y = 556238


def _noise(x: int, y: int) -> int:
    n = (x + y * 57) & 0xFFFFFFFF
    n = (n << 13) ^ n
    n = (n * n * 15731 + 789221) & 0x7FFFFFFF
    return (n >> 13) & 255


def calculate_vertex_height(world_x: int, world_y: int) -> int:
    """Procedural height for opcode-0 tiles on plane 0."""
    a = _noise(world_x - 1, world_y - 1) + _noise(world_x + 1, world_y - 1)
    a += _noise(world_x - 1, world_y + 1) + _noise(world_x + 1, world_y + 1)
    b = _noise(world_x - 1, world_y) + _noise(world_x + 1, world_y)
    b += _noise(world_x, world_y - 1) + _noise(world_x, world_y + 1)
    c = _noise(world_x, world_y)
    return a // 16 + b // 8 + c // 4


@dataclass
class TileData:
    height: int = 0
    settings: int = 0
    overlay_id: int = -1
    overlay_path: int = 0
    overlay_rotation: int = 0
    underlay_id: int = -1

    @property
    def blocked(self) -> bool:
        # Plane 0 settings bit 0 = clipped / non-walkable in 317 collision.
        return bool(self.settings & 1)


@dataclass
class RegionMap:
    region_x: int
    region_y: int
    tiles: list[list[list[TileData]]] = field(default_factory=list)
    source: str = "terrain"

    @property
    def origin_x(self) -> int:
        return self.region_x * REGION_SIZE

    @property
    def origin_y(self) -> int:
        return self.region_y * REGION_SIZE

    def plane(self, z: int = 0) -> list[list[TileData]]:
        return self.tiles[z]

    def height_at(self, local_x: int, local_y: int, plane: int = 0) -> int:
        return self.tiles[plane][local_x][local_y].height

    def blocked_at(self, local_x: int, local_y: int, plane: int = 0) -> bool:
        return self.tiles[plane][local_x][local_y].blocked

    def heights_grid(self, plane: int = 0) -> list[list[int]]:
        return [[self.tiles[plane][x][y].height for y in range(REGION_SIZE)] for x in range(REGION_SIZE)]

    def corner_heights_grid(self, plane: int = 0) -> list[list[int]]:
        """65×65 heightmap corners — tile (x,z).height is the SW vertex."""
        tiles = self.plane(plane)
        grid: list[list[int]] = [[0] * CORNER_GRID for _ in range(CORNER_GRID)]
        for gx in range(REGION_SIZE):
            for gz in range(REGION_SIZE):
                grid[gx][gz] = tiles[gx][gz].height
        for gz in range(REGION_SIZE):
            grid[REGION_SIZE][gz] = tiles[REGION_SIZE - 1][gz].height
        for gx in range(REGION_SIZE):
            grid[gx][REGION_SIZE] = tiles[gx][REGION_SIZE - 1].height
        grid[REGION_SIZE][REGION_SIZE] = tiles[REGION_SIZE - 1][REGION_SIZE - 1].height
        return grid

    def settings_grid(self, plane: int = 0) -> list[list[int]]:
        return [[self.tiles[plane][x][y].settings for y in range(REGION_SIZE)] for x in range(REGION_SIZE)]

    def blocked_grid(self, plane: int = 0) -> list[list[bool]]:
        return [[self.tiles[plane][x][y].blocked for y in range(REGION_SIZE)] for x in range(REGION_SIZE)]

    def to_summary_dict(self, *, plane: int = 0) -> dict:
        return {
            "regionX": self.region_x,
            "regionY": self.region_y,
            "regionId": (self.region_x << 8) | self.region_y,
            "size": REGION_SIZE,
            "plane": plane,
            "originX": self.origin_x,
            "originY": self.origin_y,
            "source": self.source,
            "heights": [self.corner_heights_grid(p) for p in range(PLANE_COUNT)],
            "settings": self.settings_grid(plane),
            "blocked": self.blocked_grid(plane),
        }


def decode_terrain_map(data: bytes, region_x: int, region_y: int) -> RegionMap:
    """Decode gzip-decompressed ``m{rx}_{ry}`` terrain bytes."""
    buf = Buffer(data)
    x_off = region_x * REGION_SIZE
    y_off = region_y * REGION_SIZE
    heights: list[list[list[int]]] = [
        [[0] * REGION_SIZE for _ in range(REGION_SIZE)] for _ in range(PLANE_COUNT)
    ]
    tiles: list[list[list[TileData]]] = [
        [[TileData() for _ in range(REGION_SIZE)] for _ in range(REGION_SIZE)]
        for _ in range(PLANE_COUNT)
    ]

    for plane in range(PLANE_COUNT):
        for x in range(REGION_SIZE):
            for y in range(REGION_SIZE):
                tile = tiles[plane][x][y]
                while True:
                    opcode = buf.read_u8()
                    if opcode == 0:
                        if plane == 0:
                            h = calculate_vertex_height(_HEIGHT_SEED_X + x + x_off, _HEIGHT_SEED_Y + y + y_off)
                            heights[plane][x][y] = -h * 8
                        else:
                            heights[plane][x][y] = heights[plane - 1][x][y] - 240
                        tile.height = heights[plane][x][y]
                        break
                    if opcode == 1:
                        h = buf.read_u8()
                        if h == 1:
                            h = 0
                        if plane == 0:
                            heights[plane][x][y] = -h * 8
                        else:
                            heights[plane][x][y] = heights[plane - 1][x][y] - h * 8
                        tile.height = heights[plane][x][y]
                        break
                    if opcode <= 49:
                        tile.overlay_id = buf.read_i8()
                        tile.overlay_path = (opcode - 2) // 4
                        tile.overlay_rotation = (opcode - 2) & 3
                        continue
                    if opcode <= 81:
                        tile.settings = opcode - 49
                        continue
                    tile.underlay_id = opcode - 81

    return RegionMap(region_x=region_x, region_y=region_y, tiles=tiles, source="terrain")

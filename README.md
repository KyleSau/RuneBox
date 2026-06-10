<img width="1448" height="1086" alt="e7aecd28-e838-415d-9a40-46397d2b6320" src="https://github.com/user-attachments/assets/233c8ba2-321d-4d60-a13e-90d6506265ea" />
# RuneBox

A browser-based **RuneScape sandbox** built on a live game cache. Explore NPCs, objects, and scenery as GLB models, edit tile worlds, play chess with animated NPC pieces, customize characters, and clone NPCs with per-part recolours — all synthesized on demand in Python.

![RuneBox chess sandbox](showcase.png)

## Getting Started

### 1. Download a game cache (not included)

RuneBox does **not** ship Jagex game data. You need a local cache extract.

1. Go to **[OpenRS2 Archives](https://archive.openrs2.org/caches)**
2. Pick a build — **revision 377** is what this project was developed against (317 and 474 also work for many features)
3. Download as **flatfile** (not the .dat/idx version)
4. Extract the archive

You should get a folder containing `main_file_cache.dat` and `main_file_cache.idx0`–`idx4` (sometimes inside a nested `cache/` subfolder).

### 2. Place the cache in the project

Copy the cache files into **`cache/`** at the repo root:

```text
RuneBox/
  cache/
    main_file_cache.dat
    main_file_cache.idx0
    main_file_cache.idx1
    main_file_cache.idx2
    main_file_cache.idx3
    main_file_cache.idx4
```

RuneBox also checks `rs-sandbox-world/cache/` if the root folder is empty.

If your OpenRS2 download has an extra wrapper directory, copy only the inner files that contain `main_file_cache.dat`. You can also set `RS_CACHE` in `.env` to point at any cache directory.

### 4. Install and run

```bash
cd rs-sandbox-world
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m src.cli.serve_viewer
```

Open **http://127.0.0.1:8848**

Verify the cache is detected:

```bash
python -m src.cli.cache_status
```

### 5. Explore

| Mode | What it does |
|------|----------------|
| **Browse** | NPCs, objects, locations, spot anims from cache |
| **World** | Tile editor, place scenery/NPCs, walk around, combat |
| **Chess** | 8×8 board with RS NPC pieces, capture combat choreography |
| **Creator** | Human character builder (idk kits) or **clone NPC** with model parts & recolours |
| **Rave** | Dance floor zone with stage video |

## Project layout

```text
cache/              # Your OpenRS2 flatfile extract (contents gitignored)
rs-sandbox-world/   # Python cache pipeline + web viewer
  src/              # Cache I/O, model decode, GLB export, CLI
  web/              # Three.js viewer (rs_viewer.html)
showcase.png
```

## Requirements

- Python 3.11+
- An OpenRS2 flatfile cache in `cache/`
- Optional: Java 17+ and Maven with `RS_JAVA_CLIENT_DIR` set for the Java cache bridge

## License

Game assets (models, textures, sounds) belong to Jagex Ltd. This project is a fan sandbox / tooling exercise — not affiliated with or endorsed by Jagex.

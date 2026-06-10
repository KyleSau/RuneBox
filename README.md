# RuneBox

A browser-based **RuneScape 317 sandbox** built on a live 377 cache dump. Explore NPCs, objects, and scenery as GLB models, edit tile worlds, play chess with animated NPC pieces, customize characters, and clone NPCs with per-part recolours — all synthesized on demand in Python.

![RuneBox chess sandbox](showcase.png)

## Quick start

### 1. Cache (local, not in repo)

Download or copy an **OpenRS2 revision 377** cache into the repo root, e.g.:

```text
cache-runescape-live-en-b377-2006-05-02-00-00-00-openrs2#657/
  cache/
```

The viewer auto-detects this path. You can also pass `--cache` to the server CLI.

### 2. Run the web viewer

```bash
cd tools/rs-sandbox-world
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m src.cli.serve_viewer
```

Open **http://127.0.0.1:8848**

### 3. Modes

| Mode | What it does |
|------|----------------|
| **Browse** | NPCs, objects, locations, spot anims from cache |
| **World** | Tile editor, place scenery/NPCs, walk around, combat |
| **Chess** | 8×8 board with RS NPC pieces, capture combat choreography |
| **Creator** | Human character builder (idk kits) or **clone NPC** with model parts & recolours |
| **Rave** | Dance floor zone with stage video |

## Project layout

```text
tools/rs-sandbox-world/   # Main app: Python cache pipeline + web viewer
  src/                    # Cache I/O, model decode, GLB export, CLI
  web/                    # Three.js viewer (rs_viewer.html)
tools/ai-backends/        # Optional text-to-mesh backends (Hunyuan3D, TripoSR)
showcase.png              # Screenshot for GitHub
```

## Local reference material (gitignored)

These folders are useful locally but not shipped in the repo:

- `RuneScape-317-client/` — 317 client for Java cache bridge
- `elvarg-rsps-master/` — RSPS reference
- `apollo-kotlin-experiments/` — Apollo/Kotlin experiments
- `concepts/` — design notes

## Requirements

- Python 3.11+
- Optional: Java 17+ and Maven (for Java cache bridge via `RuneScape-317-client`)
- A 377-format cache directory (see above)

## License

Game assets (models, textures, sounds) belong to Jagex Ltd. This project is a fan sandbox / tooling exercise — not affiliated with or endorsed by Jagex.

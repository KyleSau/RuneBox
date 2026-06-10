"""HTML gallery for generated candidates."""

from __future__ import annotations

import html
import json
from pathlib import Path

from src.config import DEFAULT_DEV_MODEL_ID
from src.quality.metrics import discover_candidates


def build_gallery(root: Path, out_path: Path) -> Path:
    root = root.resolve()
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_base = out_path.parent

    candidates = discover_candidates(root)
    entries: list[dict] = []
    for cand in candidates:
        entry = _load_entry(cand, html_base)
        if entry:
            entries.append(entry)

    entries.sort(
        key=lambda e: (
            -(e.get("iconScore") or e.get("styleScore") or 0),
            e.get("name", ""),
        )
    )
    out_path.write_text(_render_html(entries, root), encoding="utf-8")
    return out_path


def _load_entry(cand_dir: Path, html_base: Path) -> dict | None:
    meta_path = cand_dir / "metadata.json"
    if not meta_path.is_file():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    quality_path = cand_dir / "quality_score.json"
    style_score = None
    icon_score = None
    warnings: list[str] = []
    icon_warnings: list[str] = []
    if quality_path.is_file():
        q = json.loads(quality_path.read_text(encoding="utf-8"))
        style_score = q.get("styleScore", {}).get("score")
        warnings = q.get("styleScore", {}).get("warnings", [])
        icon_score = q.get("iconScore", {}).get("score")
        icon_warnings = q.get("iconScore", {}).get("warnings", [])

    preview = cand_dir / "previews" / "preview.png"
    preview_rel = _rel_link(preview, html_base) if preview.is_file() else ""

    preview_raw = cand_dir / "previews" / "preview_raw.png"
    preview_raw_rel = _rel_link(preview_raw, html_base) if preview_raw.is_file() else ""
    if not preview_raw_rel and meta.get("previewRaw"):
        raw_path = Path(meta["previewRaw"])
        if raw_path.is_file():
            preview_raw_rel = _rel_link(raw_path, html_base)

    concept = cand_dir / "concept" / "concept.png"
    concept_rel = _rel_link(concept, html_base) if concept.is_file() else ""

    icons = {}
    for size in (128, 64, 32):
        p = cand_dir / "previews" / f"icon_{size}.png"
        if p.is_file():
            icons[size] = _rel_link(p, html_base)

    use_cmd = (
        f"python -m src.text2rs dev use-candidate "
        f"\"{cand_dir}\" --model-id {DEFAULT_DEV_MODEL_ID}"
    )

    repair_actions = meta.get("repairActions") or []

    return {
        "name": cand_dir.name,
        "dir": str(cand_dir),
        "prompt": meta.get("userPrompt", ""),
        "backend": meta.get("backend", ""),
        "conceptBackend": meta.get("conceptBackend"),
        "target": meta.get("target", ""),
        "archetype": meta.get("archetype"),
        "faceCount": meta.get("faceCount"),
        "vertexCount": meta.get("vertexCount"),
        "uniqueColors": _unique_colors(cand_dir, meta),
        "styleScore": style_score,
        "iconScore": icon_score,
        "warnings": warnings,
        "iconWarnings": icon_warnings,
        "repairActions": repair_actions,
        "previewRel": preview_rel,
        "previewRawRel": preview_raw_rel,
        "conceptRel": concept_rel,
        "icons": icons,
        "encodedGzip": meta.get("encodedGzip"),
        "encodedDat": meta.get("encodedDat"),
        "normalizedJson": meta.get("normalizedJson"),
        "useCandidateCmd": use_cmd,
    }


def _unique_colors(cand_dir: Path, meta: dict) -> int | None:
    qpath = cand_dir / "quality_score.json"
    if qpath.is_file():
        q = json.loads(qpath.read_text(encoding="utf-8"))
        return q.get("metrics", {}).get("unique_face_colors")
    return None


def _rel_link(path: Path, base: Path) -> str:
    try:
        return html.escape(str(path.resolve().relative_to(base.resolve())).replace("\\", "/"))
    except ValueError:
        return html.escape(str(path.resolve()))


def _render_html(entries: list[dict], root: Path) -> str:
    cards = "\n".join(_card(e) for e in entries)
    title = html.escape(root.name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Text2RS Gallery — {title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; background: #1a1a1e; color: #e8e8ec; }}
    h1 {{ font-size: 1.4rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1rem; }}
    .card {{ background: #252530; border-radius: 8px; padding: 1rem; border: 1px solid #333; }}
    .card img {{ max-width: 100%; height: auto; background: #111; border-radius: 4px; }}
    .images {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem; }}
    .images img {{ width: 100%; }}
    .icons {{ display: flex; gap: 0.5rem; align-items: flex-end; margin: 0.5rem 0; }}
    .icons img {{ width: 64px; height: 64px; object-fit: contain; background: #111; border-radius: 4px; }}
    .icons img.small {{ width: 32px; height: 32px; }}
    .img-label {{ font-size: 0.7rem; color: #888; text-align: center; }}
    .score {{ font-size: 1.1rem; font-weight: bold; color: #7dd3fc; }}
    .score.low {{ color: #f87171; }}
    .icon-score {{ font-size: 1rem; color: #a5f3fc; }}
    .meta {{ font-size: 0.85rem; color: #aaa; margin: 0.4rem 0; }}
    .prompt {{ font-size: 0.95rem; margin: 0.5rem 0; }}
    .warnings {{ font-size: 0.8rem; color: #fbbf24; }}
    .repair {{ font-size: 0.8rem; color: #86efac; }}
    code {{ display: block; font-size: 0.75rem; background: #111; padding: 0.5rem; border-radius: 4px;
            overflow-x: auto; margin-top: 0.5rem; white-space: pre-wrap; word-break: break-all; }}
    .paths {{ font-size: 0.7rem; color: #666; margin-top: 0.4rem; }}
  </style>
</head>
<body>
  <h1>Text2RS Gallery</h1>
  <p class="meta">{len(entries)} candidates · root: {html.escape(str(root))}</p>
  <div class="grid">
{cards}
  </div>
</body>
</html>
"""


def _card(entry: dict) -> str:
    style_score = entry.get("styleScore")
    icon_score = entry.get("iconScore")
    score_cls = "score" + (" low" if style_score is not None and style_score < 50 else "")
    style_txt = f"{style_score}/100" if style_score is not None else "—"
    icon_txt = f"{icon_score}/100" if icon_score is not None else "—"
    icon_cls = "icon-score" + (" low" if icon_score is not None and icon_score < 50 else "")

    warnings = (entry.get("warnings") or []) + (entry.get("iconWarnings") or [])
    warn_html = "<br>".join(html.escape(f"• {w}") for w in warnings[:6])
    repair = entry.get("repairActions") or []
    repair_html = "<br>".join(html.escape(f"• {a}") for a in repair[:5])

    preview = entry.get("previewRel") or ""
    preview_raw = entry.get("previewRawRel") or ""
    concept = entry.get("conceptRel") or ""
    icons = entry.get("icons") or {}

    if preview_raw and preview:
        img = f"""      <div class="images">
        <div><div class="img-label">raw AI</div><img src="{preview_raw}" alt="raw preview"></div>
        <div><div class="img-label">repaired</div><img src="{preview}" alt="preview"></div>
      </div>"""
    elif concept and preview:
        img = f"""      <div class="images">
        <div><div class="img-label">concept</div><img src="{concept}" alt="concept"></div>
        <div><div class="img-label">model</div><img src="{preview}" alt="preview"></div>
      </div>"""
    elif preview:
        img = f'<img src="{preview}" alt="preview">'
    elif concept:
        img = f'<img src="{concept}" alt="concept">'
    else:
        img = "<p>No preview</p>"

    icon_row = ""
    if icons:
        parts = []
        for size, label, cls in ((128, "128", ""), (64, "64", ""), (32, "32", "small")):
            if size in icons:
                parts.append(
                    f'<div><div class="img-label">{label}</div>'
                    f'<img class="{cls}" src="{icons[size]}" alt="icon {size}"></div>'
                )
        if parts:
            icon_row = f'<div class="icons">{"".join(parts)}</div>'

    concept_line = ""
    if entry.get("conceptBackend"):
        concept_line = f"<br>concept backend: {html.escape(str(entry.get('conceptBackend')))}"
    archetype_line = ""
    if entry.get("archetype"):
        archetype_line = f"<br>archetype: {html.escape(str(entry.get('archetype')))}"

    return f"""    <div class="card">
      {img}
      {icon_row}
      <div class="{score_cls}">RS Style Score: {style_txt}</div>
      <div class="{icon_cls}">Icon Readability: {icon_txt}</div>
      <div class="prompt">{html.escape(entry.get('prompt', ''))}</div>
      <div class="meta">
        backend: {html.escape(str(entry.get('backend', '')))} ·
        target: {html.escape(str(entry.get('target', '')))}{concept_line}{archetype_line}<br>
        verts: {entry.get('vertexCount', '—')} ·
        faces: {entry.get('faceCount', '—')} ·
        colors: {entry.get('uniqueColors', '—')}
      </div>
      {"<div class='repair'>" + repair_html + "</div>" if repair_html else ""}
      {"<div class='warnings'>" + warn_html + "</div>" if warn_html else ""}
      <code>{html.escape(entry.get('useCandidateCmd', ''))}</code>
      <div class="paths">{html.escape(entry.get('dir', ''))}</div>
    </div>"""

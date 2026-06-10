"""Prompt templates for RS-style 3D generation and 2D concepts."""

from __future__ import annotations

NEGATIVE_GUIDANCE = (
    "Avoid: modern RS3 cosmetic overload, particle spam, tiny noisy details, high-poly realism, "
    "complex transparent materials, realistic scratches, PBR metalness, photorealism, dramatic lighting, "
    "scene backgrounds, people, hands, text, logos."
)

_CONCEPT_NEGATIVE = (
    "Avoid: modern RS3 cosmetic overload, particle spam, tiny noisy details, high-poly realism, "
    "complex transparent materials, realistic scratches, PBR metalness, photorealism, dramatic lighting, "
    "scene backgrounds, people, hands, text, logos."
)

_TEMPLATES: dict[str, str] = {
    "weapon": (
        "Create a low-poly 2005 RuneScape-style game model of: {description}. "
        "The model should have a chunky readable silhouette, simple flat colors, triangular faces, "
        "no realistic PBR texture detail, no particles, no excessive glow, and should look good from "
        "an isometric MMORPG camera. Keep it suitable for conversion into an old RuneScape 317/377 item model."
    ),
    "shield": (
        "Create a low-poly 2005 RuneScape-style shield of: {description}. "
        "Flat colors, bold silhouette, readable from isometric view, suitable for a 317/377 equipment model."
    ),
    "helmet": (
        "Create a low-poly 2005 RuneScape-style helmet/headgear of: {description}. "
        "Simple geometry, flat colors, readable from isometric MMORPG camera."
    ),
    "body": (
        "Create a low-poly 2005 RuneScape-style torso armor piece of: {description}. "
        "Chunky shapes, flat colors, suitable for old-school MMORPG body slot geometry."
    ),
    "legs": (
        "Create a low-poly 2005 RuneScape-style leg armor piece of: {description}. "
        "Simple silhouette, flat colors, suitable for 317/377 leg slot geometry."
    ),
    "object": (
        "Create a low-poly 2005 RuneScape-style ground object of: {description}. "
        "Simple flat colors, triangular faces, readable from isometric camera, no photorealism."
    ),
    "npc": (
        "Create a low-poly 2005 RuneScape-style humanoid NPC creature of: {description}. "
        "Chunky limbs, flat colors, readable silhouette from isometric MMORPG camera."
    ),
    "mount": (
        "Create a low-poly 2005 RuneScape-style mount/creature of: {description}. "
        "Large readable silhouette, flat colors, suitable for old-school MMORPG models."
    ),
}

_CONCEPT_TEMPLATES: dict[str, str] = {
    "weapon": (
        "A single low-poly 2005 RuneScape-style game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Orthographic 3/4 view. "
        "Chunky readable silhouette. "
        "Simple flat colors. "
        "Triangular low-poly facets. "
        "No character, no hands, no environment, no text, no logo. "
        "No particles, no glow spam, no photorealistic texture, no modern RS3 cosmetic overload."
    ),
    "item": (
        "A single low-poly 2005 RuneScape-style game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Orthographic 3/4 view. "
        "Chunky readable silhouette. "
        "Simple flat colors. "
        "Triangular low-poly facets. "
        "No character, no hands, no environment, no text, no logo. "
        "No particles, no glow spam, no photorealistic texture, no modern RS3 cosmetic overload."
    ),
    "shield": (
        "A single low-poly 2005 RuneScape-style shield game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Front-facing or slight 3/4 orthographic view. "
        "Chunky readable silhouette. "
        "Simple flat colors. "
        "Triangular low-poly facets. "
        "No character, no hands, no environment, no text, no logo. "
        "No particles, no glow spam, no photorealistic texture, no modern RS3 cosmetic overload."
    ),
    "helmet": (
        "A single low-poly 2005 RuneScape-style helmet game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Orthographic 3/4 view. "
        "Chunky readable silhouette, simple flat colors, triangular low-poly facets. "
        "No character, no hands, no environment, no text, no logo."
    ),
    "body": (
        "A single low-poly 2005 RuneScape-style torso armor game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Orthographic 3/4 view. Simple flat colors, chunky silhouette."
    ),
    "legs": (
        "A single low-poly 2005 RuneScape-style leg armor game asset of: {description}. "
        "Centered on a plain white or transparent background. "
        "Orthographic 3/4 view. Simple flat colors, chunky silhouette."
    ),
    "object": (
        "A single low-poly 2005 RuneScape-style environmental prop of: {description}. "
        "Centered on plain white or transparent background. "
        "Orthographic 3/4 view. "
        "Simple flat colors, chunky silhouette, readable from an isometric MMORPG camera. "
        "No characters, no environment, no text, no photorealism, no particle effects."
    ),
    "npc": (
        "A single low-poly 2005 RuneScape-style creature model concept of: {description}. "
        "Centered on plain white or transparent background. "
        "Side or 3/4 view. "
        "Simple flat colors, chunky silhouette, readable from an isometric MMORPG camera. "
        "No rider, no environment, no text, no photorealism."
    ),
    "mount": (
        "A single low-poly 2005 RuneScape-style creature model concept of: {description}. "
        "Centered on plain white or transparent background. "
        "Side or 3/4 view. "
        "Simple flat colors, chunky silhouette, readable from an isometric MMORPG camera. "
        "No rider, no environment, no text, no photorealism."
    ),
}


def _normalize_target(target: str) -> str:
    key = target.lower().strip()
    if key == "item":
        return "weapon"
    return key


def build_prompt(description: str, target: str) -> str:
    key = _normalize_target(target)
    template = _TEMPLATES.get(key, _TEMPLATES["object"])
    body = template.format(description=description.strip())
    return f"{body}\n\n{NEGATIVE_GUIDANCE}"


def build_concept_prompt(description: str, target: str) -> str:
    key = target.lower().strip()
    if key == "item":
        key = "item"
    template = _CONCEPT_TEMPLATES.get(key, _CONCEPT_TEMPLATES.get(_normalize_target(target), _CONCEPT_TEMPLATES["object"]))
    body = template.format(description=description.strip())
    return f"{body}\n\n{_CONCEPT_NEGATIVE}"


def list_targets() -> list[str]:
    return sorted(set(_TEMPLATES) | {"item"})

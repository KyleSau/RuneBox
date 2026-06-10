"""Default player appearance + recolour helpers (ports Game.java design code).

A Player model is assembled from 7 identity-kit body parts (head, jaw, torso,
arms, hands, legs, feet) chosen per gender, recoloured by 5 design colours.
``designPartColor`` / ``designHairColor`` are copied verbatim from the client.
"""

from __future__ import annotations

# Game.designPartColor: [part][choice] -> HSL. Part order: 0 hair, 1 torso,
# 2 legs, 3 feet, 4 skin (the 5 colour cyclers in the design screen).
DESIGN_PART_COLOR: list[list[int]] = [
    [6798, 107, 10283, 16, 4797, 7744, 5799, 4634, 33697, 22433, 2983, 54193],
    [8741, 12, 64030, 43162, 7735, 8404, 1701, 38430, 24094, 10153, 56621, 4783, 1341, 16578, 35003, 25239],
    [25238, 8742, 12, 64030, 43162, 7735, 8404, 1701, 38430, 24094, 10153, 56621, 4783, 1341, 16578, 35003],
    [4626, 11146, 6439, 12, 4758, 10270],
    [4550, 4537, 5681, 5673, 5790, 6806, 8076, 4574],
]

DESIGN_HAIR_COLOR: list[int] = [
    9104, 10275, 7595, 3610, 7975, 8526, 918, 38802, 24466, 10145, 58654, 5027, 1457, 16565, 34991, 25486,
]

# Number of identity-kit body parts assembled into a player.
KIT_PARTS = 7

# Classic 317 default player animations, in the exact order the appearance block
# sends them (Game/PlayerEntity.readAppearance, matched by Elvarg's appendAppearance):
#   stand 808, stand-turn 823, walk 819, walk-180 820, walk-left 821, walk-right 822, run 824.
DEFAULT_SEQ_STAND = 808
DEFAULT_SEQ_TURN = 823
DEFAULT_SEQ_WALK = 819
DEFAULT_SEQ_TURN_AROUND = 820
DEFAULT_SEQ_TURN_LEFT = 821
DEFAULT_SEQ_TURN_RIGHT = 822
DEFAULT_SEQ_RUN = 824


def default_kits(idks, male: bool) -> list[int]:
    """First non-selectable kit per body part (ports Game.validateCharacterDesign).

    ``idks`` is the decoded IdkType list. Returns 7 kit indices (or -1).
    """
    offset = 0 if male else 7
    kits = [-1] * KIT_PARTS
    for part in range(KIT_PARTS):
        for kit, idk in enumerate(idks):
            if idk.selectable or idk.type != (part + offset):
                continue
            kits[part] = kit
            break
    return kits


def design_recolor(idks, kit_indices, colors) -> dict[int, int]:
    """Combined HSL recolour map for an assembled player.

    Merges each chosen kit's own colorSrc->colorDst pairs with the 5 design
    colours (Game.java: designPartColor / designHairColor). ``colors`` is a list
    of 5 choice indices (0 = default, leaves that colour unchanged).
    """
    recolor: dict[int, int] = {}
    for kit in kit_indices:
        if kit is None or kit < 0 or kit >= len(idks):
            continue
        idk = idks[kit]
        for src, dst in zip(idk.color_src, idk.color_dst):
            if src != 0:
                recolor[src] = dst

    for part in range(5):
        choice = colors[part] if part < len(colors) else 0
        if not choice:
            continue
        palette = DESIGN_PART_COLOR[part]
        if 0 <= choice < len(palette):
            recolor[palette[0]] = palette[choice]
        if part == 1 and choice < len(DESIGN_HAIR_COLOR):
            recolor[DESIGN_HAIR_COLOR[0]] = DESIGN_HAIR_COLOR[choice]
    return recolor


def kit_model_ids(idks, kit_indices) -> list[int]:
    """Concatenate body-part model ids for the assembled player."""
    ids: list[int] = []
    for kit in kit_indices:
        if kit is None or kit < 0 or kit >= len(idks):
            continue
        idk = idks[kit]
        if idk.model_ids:
            ids.extend(idk.model_ids)
    return ids

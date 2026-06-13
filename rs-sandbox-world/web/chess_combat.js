/**
 * Chess capture combat — material damage, Elvarg-style spells, teleports, deaths.
 */

/** Standard piece values shown as hit damage. King is never captured. */
export const PIECE_VALUE = { P: 1, N: 3, B: 3, R: 5, Q: 9 };

/** 317 client cycle (~20ms). Chess choreography waits use these tick counts. */
export const CYCLE_MS = 20;
export const COMBAT_TICKS = {
  /** Ticks from attack start until the hitmark appears (317-style connect frame). */
  MELEE_HIT: 6,
  HITMARK_HOLD: 4,
  DEATH_HOLD: 10,
  POST_CAPTURE: 2,
  TELEPORT: 14,
  CAST_WINDUP: 8,
};

/** 317 / Elvarg animation sequence ids. */
export const SEQ = {
  cast_wave: 727,
  cast_fire_blast: 711,
  cast_ice_barrage: 1979,
  attack_2h: 407,
  attack_slash: 390,
  attack_punch: 422,
  attack_whip: 1658,
  attack_kick: 2339,
  imp_punch: 169,
  death_imp: 172,
  death_human: 836,
  death_golem: 6260,
  teleport_start: 714,
  teleport_end: 715,
};

/** Elvarg CombatSpells gfx (wind wave / fire wave / fire blast / ice barrage). */
export const CHESS_SPELLS = {
  wind_wave: {
    anim: 'cast_wave',
    start: { id: 158, h: 'MIDDLE' },
    proj: { id: 159 },
    end: { id: 160, h: 'HIGH' },
  },
  fire_wave: {
    anim: 'cast_wave',
    start: { id: 155, h: 'MIDDLE' },
    proj: { id: 156 },
    end: { id: 157, h: 'HIGH' },
  },
  fire_blast: {
    anim: 'cast_fire_blast',
    start: { id: 129, h: 'HIGH' },
    proj: { id: 130 },
    end: { id: 131, h: 'HIGH' },
  },
  ice_barrage: {
    anim: 'cast_ice_barrage',
    start: null,
    proj: null,
    end: { id: 369, h: 'LOW' },
    castSound: 1111,
    impactSound: 1125,
  },
};

export const TELEPORT_GFX = 308;

export function pieceDamage(type) {
  return PIECE_VALUE[type] ?? 1;
}

export function bishopSpell(color) {
  return color === 'w' ? CHESS_SPELLS.wind_wave : CHESS_SPELLS.fire_wave;
}

/** Chebyshev distance between two board squares (king moves). */
export function chessChebyshev(fromSq, toSq) {
  const f1 = fromSq.charCodeAt(0) - 97;
  const r1 = parseInt(fromSq[1], 10) - 1;
  const f2 = toSq.charCodeAt(0) - 97;
  const r2 = parseInt(toSq[1], 10) - 1;
  return Math.max(Math.abs(f1 - f2), Math.abs(r1 - r2));
}

/** Which capture choreography to run for each piece type. */
export function captureStyle(type, color) {
  if (type === 'B') return 'bishop_spell';
  if (type === 'Q') return 'queen_spell';
  if (type === 'N') return 'knight_slide_melee';
  if (type === 'R') return 'rook_slide_melee';
  if (type === 'K') return 'king_melee';
  if (type === 'P' && color === 'b') return 'imp_melee';
  if (type === 'P') return 'pawn_melee';
  return 'melee';
}

/** Extra baked clips per piece (seq id, clip name). */
export function animsForPiece(type, color) {
  const list = [];
  const setDeath = (seq) => {
    const i = list.findIndex(([, n]) => n === 'death');
    if (i >= 0) list[i] = [seq, 'death'];
    else list.push([seq, 'death']);
  };

  list.push([SEQ.teleport_start, 'teleport_start']);
  list.push([SEQ.teleport_end, 'teleport_end']);
  list.push([SEQ.death_human, 'death']);

  if (type === 'B') {
    list.push([SEQ.cast_wave, 'cast_wave']);
  } else if (type === 'Q') {
    list.push([SEQ.cast_ice_barrage, 'cast_ice_barrage']);
    list.push([SEQ.attack_whip, 'attack_whip']);
  } else if (type === 'N' || type === 'R') {
    list.push([SEQ.attack_2h, 'attack_2h']);
    // death_golem (6260) not in all caches — keep death_human from defaults
  } else if (type === 'K') {
    list.push([SEQ.attack_kick, 'attack']);
  } else if (type === 'P' && color === 'b') {
    list.push([SEQ.imp_punch, 'attack']);
    setDeath(SEQ.death_imp);
  } else if (type === 'P') {
    list.push([SEQ.attack_punch, 'attack']);
  } else {
    list.push([SEQ.attack_slash, 'attack']);
  }

  return list;
}

export function npcAnimUrl(npcId, type, color) {
  const anims = animsForPiece(type, color);
  const q = anims.map(([seq, name]) => `${seq}:${name}`).join(',');
  return `/api/npc/${npcId}.glb?anims=${encodeURIComponent(q)}&t=${Date.now()}`;
}

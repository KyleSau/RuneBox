/**
 * Chess capture combat — material damage, Elvarg-style spells, teleports, deaths.
 */

/** Standard piece values shown as hit damage. King is never captured. */
export const PIECE_VALUE = { P: 1, N: 3, B: 3, R: 5, Q: 9 };

/** 317 / Elvarg animation sequence ids. */
export const SEQ = {
  cast_wave: 727,
  cast_fire_blast: 711,
  attack_2h: 407,
  attack_slash: 390,
  imp_punch: 169,
  death_imp: 172,
  death_human: 836,
  death_golem: 6260,
  teleport_start: 714,
  teleport_end: 715,
};

/** Elvarg CombatSpells gfx (wind wave / fire wave / fire blast). */
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
};

export const TELEPORT_GFX = 308;

export function pieceDamage(type) {
  return PIECE_VALUE[type] ?? 1;
}

export function bishopSpell(color) {
  return color === 'w' ? CHESS_SPELLS.wind_wave : CHESS_SPELLS.fire_wave;
}

/** Which capture choreography to run for each piece type. */
export function captureStyle(type, color) {
  if (type === 'B') return 'bishop_spell';
  if (type === 'N') return 'knight_teleport_melee';
  if (type === 'R') return 'rook_teleport_melee';
  if (type === 'Q') return 'queen_spell';
  if (type === 'P' && color === 'b') return 'imp_melee';
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
    list.push([SEQ.cast_fire_blast, 'cast_fire_blast']);
  } else if (type === 'N' || type === 'R') {
    list.push([SEQ.attack_2h, 'attack_2h']);
    if (type === 'R') setDeath(SEQ.death_golem);
  } else if (type === 'P' && color === 'b') {
    list.push([SEQ.imp_punch, 'attack']);
    setDeath(SEQ.death_imp);
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

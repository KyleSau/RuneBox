/**
 * RS Sandbox chess board: 8x8 checker tiles, NPC pieces, chess.js rules.
 * Captures run combat choreography (damage splats, spells, teleports, deaths).
 */
import { Chess } from 'https://esm.sh/chess.js@1.0.0-beta.8';
import {
  PIECE_VALUE,
  TELEPORT_GFX,
  bishopSpell,
  captureStyle,
  npcAnimUrl,
  pieceDamage,
  CHESS_SPELLS,
  COMBAT_TICKS,
  CYCLE_MS,
  chessChebyshev,
} from './chess_combat.js';

const WALK_TIME = 0.6;

/** NPC ids from the 377 cache (see /api/npcs.json). */
export const CHESS_NPCS = {
  w: { K: 212, Q: 2578, R: 3027, B: 2712, N: 19, P: 160 },
  b: { K: 2590, Q: 1359, R: 3026, B: 172, N: 178, P: 1531 },
};

const LIGHT = '#f2f2f2';
const DARK = '#0a0a0a';
const SELECT = '#caa54a';
const LAST = '#4a6a9a';

export function createChessWorld(ctx) {
  const {
    THREE, worldGroup, loader, applyWire, tuneClipInterp,
    tileToScene, tileMeshes, tileBaseColor, GRID, TILE,
    worldStatusEl, fx,
  } = ctx;

  let active = false;
  let busy = false;
  let chess = new Chess();
  let boardOx = 2;
  let boardOz = 2;
  let selectedSq = null;
  let lastMove = null;
  let turn = 'w';
  const capturedCount = { w: 0, b: 0 };
  /** @type {Map<string, PieceEntry>} */
  const pieces = new Map();
  const mixers = [];
  const anims = [];
  const pickRay = new THREE.Raycaster();

  function pieceForObject(obj) {
    let n = obj;
    while (n) {
      for (const [, p] of pieces) {
        if (n === p.obj) return p;
      }
      n = n.parent;
    }
    return null;
  }

  function sqToTile(sq) {
    const file = sq.charCodeAt(0) - 97;
    const rank = parseInt(sq[1], 10) - 1;
    return { x: boardOx + file, z: boardOz + rank };
  }

  function tileToSq(tx, tz) {
    const file = tx - boardOx;
    const rank = tz - boardOz;
    if (file < 0 || file > 7 || rank < 0 || rank > 7) return null;
    return String.fromCharCode(97 + file) + (rank + 1);
  }

  function pickPiece(ndc, camera) {
    if (!active || !pieces.size || busy) return null;
    pickRay.setFromCamera(ndc, camera);
    const roots = [];
    for (const [, p] of pieces) {
      if (!p.offBoard) roots.push(p.obj);
    }
    const hits = pickRay.intersectObjects(roots, true);
    if (!hits.length) return null;
    const best = pieceForObject(hits[0].object);
    if (!best) return null;
    const { x, z } = sqToTile(best.sq);
    return {
      obj: best.obj,
      sq: best.sq,
      color: best.color,
      type: best.type,
      npcId: CHESS_NPCS[best.color][best.type],
      tx: x,
      tz: z,
    };
  }

  function getPieceLabel(pick) {
    if (!pick) return '';
    const rank = pick.type === 'K' ? 'King' : pick.type === 'Q' ? 'Queen' : pick.type === 'R' ? 'Rook'
      : pick.type === 'B' ? 'Bishop' : pick.type === 'N' ? 'Knight' : 'Pawn';
    const side = pick.color === 'w' ? 'White' : 'Black';
    return `${side} ${rank}`;
  }

  function isBoardTile(tx, tz) {
    return tx >= boardOx && tx < boardOx + 8 && tz >= boardOz && tz < boardOz + 8;
  }

  function tileKey(tx, tz) { return tx * GRID + tz; }

  function paintTile(tx, tz, color) {
    const m = tileMeshes[tileKey(tx, tz)];
    if (m) {
      m.material.map = null;
      m.material.color.set(color);
      m.material.needsUpdate = true;
    }
  }

  function refreshBoardColors() {
    for (let f = 0; f < 8; f++) {
      for (let r = 0; r < 8; r++) {
        const tx = boardOx + f;
        const tz = boardOz + r;
        const sq = String.fromCharCode(97 + f) + (r + 1);
        let c = (f + r) % 2 === 0 ? LIGHT : DARK;
        if (sq === selectedSq) c = SELECT;
        else if (lastMove && (sq === lastMove.from || sq === lastMove.to)) c = LAST;
        paintTile(tx, tz, c);
      }
    }
  }

  function pieceRotY(color) {
    return color === 'w' ? 0 : Math.PI;
  }

  function faceToward(obj, tx, tz) {
    const to = tileToScene(tx, tz);
    const dx = to.x - obj.position.x;
    const dz = to.z - obj.position.z;
    if (Math.abs(dx) + Math.abs(dz) > 0.5) {
      obj.rotation.y = Math.atan2(dx, dz);
    }
  }

  function setupMixer(gltf, entry) {
    entry.actions = {};
    entry.current = null;
    entry.oneShot = null;
    if (!gltf.animations?.length) {
      entry.mixer = null;
      return;
    }
    entry.mixer = new THREE.AnimationMixer(entry.obj);
    mixers.push(entry.mixer);
    entry.mixer.addEventListener('finished', (e) => {
      const a = e.action;
      if (a === entry.actions?.idle) return;
      if (entry.oneShot === a) {
        entry.oneShot = null;
        restoreIdle(entry, 0.1);
      }
    });
    for (const clip of gltf.animations) {
      tuneClipInterp(clip);
      const action = entry.mixer.clipAction(clip);
      const loop = clip.name === 'idle';
      action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, loop ? Infinity : 1);
      action.clampWhenFinished = !loop;
      entry.actions[clip.name] = action;
    }
    const idle = entry.actions.idle || entry.actions[Object.keys(entry.actions)[0]];
    if (idle) {
      idle.play();
      entry.current = idle;
    }
  }

  function restoreIdle(entry, fade = 0.12) {
    const idle = entry?.actions?.idle;
    if (!idle || !entry?.mixer) return;
    for (const [name, act] of Object.entries(entry.actions)) {
      if (name === 'idle' || act === idle) continue;
      act.fadeOut(fade);
      act.stop();
    }
    idle.reset();
    idle.setLoop(THREE.LoopRepeat, Infinity);
    idle.clampWhenFinished = false;
    idle.fadeIn(fade).play();
    entry.current = idle;
    entry.oneShot = null;
  }

  function playAnim(entry, name, { fade = 0.12 } = {}) {
    return new Promise(resolve => {
      const action = entry.actions?.[name];
      if (!action || !entry.mixer) {
        resolve();
        return;
      }
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        entry.mixer.removeEventListener('finished', onFinished);
        clearTimeout(fallback);
        resolve();
      };
      const onFinished = (e) => {
        if (e.action !== action) return;
        finish();
      };
      const isLoop = action.loop === THREE.LoopRepeat;
      if (!isLoop) {
        entry.mixer.addEventListener('finished', onFinished);
        entry.oneShot = action;
      }
      if (entry.current && entry.current !== action) entry.current.fadeOut(fade);
      action.reset().fadeIn(fade).play();
      entry.current = action;
      if (isLoop) {
        finish();
        return;
      }
      const durMs = Math.max(50, action.getClip().duration * 1000 + 80);
      const fallback = setTimeout(finish, durMs);
    });
  }

  /** One-shot clip, then return to idle stand. */
  async function playAnimOnce(entry, name, opts) {
    await playAnim(entry, name, opts);
    restoreIdle(entry, opts?.fade ?? 0.12);
  }

  function waitMs(ms) {
    return fx?.delay ? fx.delay(ms) : new Promise(r => setTimeout(r, ms));
  }

  async function waitTicks(ticks) {
    if (fx?.waitTicks) return fx.waitTicks(ticks);
    return waitMs(ticks * CYCLE_MS);
  }

  function commitAttackerMove(attacker, move) {
    pieces.delete(move.from);
    pieces.set(move.to, attacker);
    attacker.sq = move.to;
    attacker.obj.userData.chess.sq = move.to;
  }

  async function slidePieceTo(entry, tx, tz, { fromTx, fromTz, commit = true } = {}) {
    let dist = 1;
    if (fromTx != null && fromTz != null) {
      dist = Math.max(1, Math.max(Math.abs(tx - fromTx), Math.abs(tz - fromTz)));
    }
    await animateObj(entry.obj, tx, tz, WALK_TIME * dist);
    restoreIdle(entry);
    if (commit && entry.sq) {
      const fromSq = entry.sq;
      const toSq = tileToSq(tx, tz);
      if (toSq && fromSq !== toSq) {
        pieces.delete(fromSq);
        pieces.set(toSq, entry);
        entry.sq = toSq;
        entry.obj.userData.chess.sq = toSq;
      }
    }
  }

  function loadNpc(id, type, color) {
    const url = npcAnimUrl(id, type, color);
    return new Promise((resolve, reject) => {
      loader.load(url, gltf => resolve(gltf), undefined, reject);
    });
  }

  function spawnPiece(sq, color, type) {
    const id = CHESS_NPCS[color][type];
    const { x, z } = sqToTile(sq);
    return loadNpc(id, type, color).then(gltf => {
      const obj = gltf.scene;
      applyWire(obj);
      obj.scale.setScalar(0.55);
      obj.position.copy(tileToScene(x, z));
      obj.position.y = 0;
      obj.rotation.y = pieceRotY(color);
      obj.userData.chess = { sq, color, type };
      worldGroup.add(obj);
      const entry = { sq, color, type, obj, offBoard: false };
      setupMixer(gltf, entry);
      pieces.set(sq, entry);
      return obj;
    });
  }

  function animateObj(obj, toX, toZ, dur, onDone) {
    return new Promise(resolve => {
      anims.push({
        obj,
        from: obj.position.clone(),
        to: tileToScene(toX, toZ),
        t: 0,
        dur: dur || 0.28,
        onDone: () => { onDone?.(); resolve(); },
      });
    });
  }

  function sidelineTile(color) {
    const n = capturedCount[color]++;
    return { x: boardOx - 1, z: boardOz + Math.min(n, 7) };
  }

  async function relocateCaptured(victim) {
    const { x, z } = sidelineTile(victim.color);
    victim.offBoard = true;
    await animateObj(victim.obj, x, z, WALK_TIME * 0.6);
    restoreIdle(victim);
  }

  async function teleportTo(entry, tx, tz) {
    const pos = tileToScene(tx, tz);
    const yaw = entry.obj.rotation.y;
    if (fx?.spawnGfx) fx.spawnGfx(entry.obj.position.clone(), TELEPORT_GFX, 'HIGH', yaw);
    await playAnim(entry, 'teleport_start');
    entry.obj.position.copy(pos);
    if (fx?.spawnGfx) fx.spawnGfx(pos, TELEPORT_GFX, 'HIGH', yaw);
    await playAnim(entry, 'teleport_end');
    restoreIdle(entry);
  }

  async function spawnHitmark(victim, dmg) {
    if (fx?.spawnHit) fx.spawnHit(victim.obj, dmg);
    await waitTicks(COMBAT_TICKS.HITMARK_HOLD);
  }

  async function playVictimDeath(victim) {
    await playAnim(victim, 'death');
    await waitTicks(COMBAT_TICKS.DEATH_HOLD);
    await relocateCaptured(victim);
  }

  async function applyMeleeHit(victim, dmg) {
    pieces.delete(victim.sq);
    await spawnHitmark(victim, dmg);
    await playVictimDeath(victim);
  }

  /**
   * Tick-based melee capture: face → attack → hit on connect tick → death → walk onto square.
   */
  async function meleeCaptureSequence(attacker, victim, move, {
    animName = 'attack',
    hitTicks = COMBAT_TICKS.MELEE_HIT,
    moveAfter = true,
  } = {}) {
    const dmg = pieceDamage(victim.type);
    const capTile = sqToTile(move.to);
    const fromTile = sqToTile(move.from);
    const vTile = sqToTile(victim.sq);
    faceToward(attacker.obj, vTile.x, vTile.z);
    const attackDone = playAnim(attacker, animName);
    await waitTicks(hitTicks);
    await applyMeleeHit(victim, dmg);
    await attackDone;
    restoreIdle(attacker);
    if (moveAfter && move.from !== move.to) {
      await slidePieceTo(attacker, capTile.x, capTile.z, {
        fromTx: fromTile.x, fromTz: fromTile.z, commit: true,
      });
    }
  }

  /** Pawn / imp: face → punch → hitmark → death → walk onto captured square. */
  async function pawnCapture(attacker, victim, move) {
    await meleeCaptureSequence(attacker, victim, move, { animName: 'attack' });
  }

  /** King: face → kick → hitmark → death → walk onto captured square. */
  async function kingCapture(attacker, victim, move) {
    await meleeCaptureSequence(attacker, victim, move, { animName: 'attack' });
  }

  async function castSpellAtTarget(attacker, victim, spell) {
    const vTile = sqToTile(victim.sq);
    faceToward(attacker.obj, vTile.x, vTile.z);
    const from = attacker.obj.position.clone();
    const to = victim.obj.position.clone();
    const yaw = attacker.obj.rotation.y;
    if (spell.castSound != null && fx?.playSfx) fx.playSfx(spell.castSound, from);
    await playAnimOnce(attacker, spell.anim);
    if (fx?.castSpellAt) {
      await fx.castSpellAt(from, to, spell, yaw);
    } else {
      await waitTicks(30);
    }
  }

  /** Bishop: spell → hitmark/death on impact → teleport onto captured square. */
  async function bishopCapture(attacker, victim, move) {
    const spell = bishopSpell(attacker.color);
    const dmg = pieceDamage(victim.type);
    const toTile = sqToTile(move.to);
    await castSpellAtTarget(attacker, victim, spell);
    await applyMeleeHit(victim, dmg);
    commitAttackerMove(attacker, move);
    await teleportTo(attacker, toTile.x, toTile.z);
  }

  /** Queen ranged: ice barrage + sounds → hitmark/death → teleport to square. */
  async function queenRangedCapture(attacker, victim, move) {
    const spell = CHESS_SPELLS.ice_barrage;
    const dmg = pieceDamage(victim.type);
    const toTile = sqToTile(move.to);
    await castSpellAtTarget(attacker, victim, spell);
    await applyMeleeHit(victim, dmg);
    commitAttackerMove(attacker, move);
    await teleportTo(attacker, toTile.x, toTile.z);
  }

  /** Queen adjacent: slide onto square → whip → hitmark/death. */
  async function queenMeleeCapture(attacker, victim, move) {
    const capTile = sqToTile(move.to);
    const fromTile = sqToTile(move.from);
    const vTile = sqToTile(victim.sq);
    faceToward(attacker.obj, vTile.x, vTile.z);
    if (move.from !== move.to) {
      await slidePieceTo(attacker, capTile.x, capTile.z, {
        fromTx: fromTile.x, fromTz: fromTile.z, commit: false,
      });
      faceToward(attacker.obj, vTile.x, vTile.z);
    }
    const whip = attacker.actions?.attack_whip ? 'attack_whip' : 'attack';
    await meleeCaptureSequence(attacker, victim, move, {
      animName: whip,
      moveAfter: true,
    });
  }

  async function queenCapture(attacker, victim, move) {
    const dist = chessChebyshev(move.from, move.to);
    if (dist > 1) return queenRangedCapture(attacker, victim, move);
    return queenMeleeCapture(attacker, victim, move);
  }

  /** Knight/Rook: slide to square → 2h attack on tile → hitmark/death (stay put). */
  async function slideMeleeCapture(attacker, victim, move) {
    const capTile = sqToTile(move.to);
    const fromTile = sqToTile(move.from);
    const vTile = sqToTile(victim.sq);
    await slidePieceTo(attacker, capTile.x, capTile.z, {
      fromTx: fromTile.x, fromTz: fromTile.z, commit: false,
    });
    faceToward(attacker.obj, vTile.x, vTile.z);
    const atkName = attacker.actions?.attack_2h ? 'attack_2h' : 'attack';
    await meleeCaptureSequence(attacker, victim, move, {
      animName: atkName,
      moveAfter: true,
    });
  }

  async function impMeleeCapture(attacker, victim, move) {
    return pawnCapture(attacker, victim, move);
  }

  async function meleeCapture(attacker, victim, move) {
    return pawnCapture(attacker, victim, move);
  }

  async function playCapture(attacker, victim, move) {
    const style = captureStyle(attacker.type, attacker.color);
    try {
      if (style === 'bishop_spell') await bishopCapture(attacker, victim, move);
      else if (style === 'queen_spell') await queenCapture(attacker, victim, move);
      else if (style === 'knight_slide_melee' || style === 'rook_slide_melee') {
        await slideMeleeCapture(attacker, victim, move);
      } else if (style === 'king_melee') await kingCapture(attacker, victim, move);
      else if (style === 'imp_melee') await impMeleeCapture(attacker, victim, move);
      else if (style === 'pawn_melee') await pawnCapture(attacker, victim, move);
      else await meleeCapture(attacker, victim, move);
    } finally {
      restoreIdle(attacker);
      await waitTicks(COMBAT_TICKS.POST_CAPTURE);
    }
  }

  function castlingRookSquares(move) {
    if (move.flags.includes('k')) {
      return move.color === 'w' ? { from: 'h1', to: 'f1' } : { from: 'h8', to: 'f8' };
    }
    if (move.flags.includes('q')) {
      return move.color === 'w' ? { from: 'a1', to: 'd1' } : { from: 'a8', to: 'd8' };
    }
    return null;
  }

  function victimSquare(move) {
    if (!move.captured) return null;
    if (move.flags.includes('e')) {
      return move.to[0] + (move.color === 'w' ? '5' : '4');
    }
    return move.to;
  }

  async function movePieceVisual(fromSq, toSq) {
    const p = pieces.get(fromSq);
    if (!p) return;
    const fromT = sqToTile(fromSq);
    const { x, z } = sqToTile(toSq);
    pieces.delete(fromSq);
    pieces.set(toSq, p);
    p.sq = toSq;
    p.obj.userData.chess.sq = toSq;
    const dist = Math.max(1, Math.max(Math.abs(x - fromT.x), Math.abs(z - fromT.z)));
    await animateObj(p.obj, x, z, WALK_TIME * dist);
    restoreIdle(p);
  }

  function removePiece(sq) {
    const p = pieces.get(sq);
    if (!p) return;
    pieces.delete(sq);
    if (p.mixer) {
      const i = mixers.indexOf(p.mixer);
      if (i >= 0) mixers.splice(i, 1);
    }
    worldGroup.remove(p.obj);
    p.obj.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach(m => m.dispose());
      }
    });
  }

  async function applyMove(move) {
    if (busy) return;
    busy = true;
    lastMove = { from: move.from, to: move.to };

    const attacker = pieces.get(move.from);
    const vSq = victimSquare(move);
    const victim = vSq ? pieces.get(vSq) : null;
    const castle = castlingRookSquares(move);

    try {
      if (victim && move.captured) {
        await playCapture(attacker, victim, move);
      } else if (move.promotion) {
        await movePieceVisual(move.from, move.to);
        removePiece(move.to);
        await spawnPiece(move.to, move.color, 'Q');
      } else {
        await movePieceVisual(move.from, move.to);
      }

      if (castle) {
        await movePieceVisual(castle.from, castle.to);
      }
    } catch (e) {
      console.warn('Chess capture anim failed', e);
      if (victim && move.captured) removePiece(vSq);
      if (move.promotion) {
        removePiece(move.to);
        await spawnPiece(move.to, move.color, 'Q');
      } else {
        await movePieceVisual(move.from, move.to);
      }
      if (castle) await movePieceVisual(castle.from, castle.to);
    }

    turn = chess.turn();
    selectedSq = null;
    refreshBoardColors();
    setStatus();
    busy = false;
  }

  function setStatus() {
    if (!worldStatusEl) return;
    let msg = `Chess — ${turn === 'w' ? 'White' : 'Black'} to move.`;
    if (chess.isCheckmate()) msg = chess.turn() === 'w' ? 'Checkmate! Black wins.' : 'Checkmate! White wins.';
    else if (chess.isDraw()) msg = 'Draw.';
    else if (chess.isCheck()) msg += ' Check!';
    worldStatusEl.textContent = msg;
  }

  async function setupBoard() {
    chess = new Chess();
    turn = 'w';
    selectedSq = null;
    lastMove = null;
    busy = false;
    capturedCount.w = 0;
    capturedCount.b = 0;
    for (const [, p] of pieces) removePiece(p.sq);
    pieces.clear();
    mixers.length = 0;

    refreshBoardColors();

    const order = [
      ['a8','b8','c8','d8','e8','f8','g8','h8'],
      ['a7','b7','c7','d7','e7','f7','g7','h7'],
      ['a2','b2','c2','d2','e2','f2','g2','h2'],
      ['a1','b1','c1','d1','e1','f1','g1','h1'],
    ];
    const back = ['R','N','B','Q','K','B','N','R'];
    const tasks = [];
    for (let i = 0; i < 8; i++) {
      tasks.push(spawnPiece(order[0][i], 'b', back[i]));
      tasks.push(spawnPiece(order[1][i], 'b', 'P'));
      tasks.push(spawnPiece(order[2][i], 'w', 'P'));
      tasks.push(spawnPiece(order[3][i], 'w', back[i]));
    }
    await Promise.all(tasks);
    active = true;
    setStatus();
  }

  function handleClick(tx, tz) {
    if (!active || busy) return false;
    const sq = tileToSq(tx, tz);
    if (!sq) return false;

    const piece = chess.get(sq);
    const moving = chess.turn();

    if (!selectedSq) {
      if (piece && piece.color === moving) {
        selectedSq = sq;
        refreshBoardColors();
        worldStatusEl.textContent = `Selected ${sq}. Click destination.`;
      }
      return true;
    }

    if (sq === selectedSq) {
      selectedSq = null;
      refreshBoardColors();
      setStatus();
      return true;
    }

    const from = selectedSq;
    const fromPiece = chess.get(from);

    // Castling: king selected, click friendly rook (chess.js needs king destination square).
    if (fromPiece?.type === 'k' && piece?.type === 'r' && fromPiece.color === moving && piece.color === moving) {
      const kf = from.charCodeAt(0) - 97;
      const rf = sq.charCodeAt(0) - 97;
      const rank = from[1];
      const tryCastle = (destFile) => {
        const dest = String.fromCharCode(97 + destFile) + rank;
        try {
          return chess.move({ from, to: dest });
        } catch (_) {
          return null;
        }
      };
      let move = null;
      if (rf > kf) move = tryCastle(kf + 2);
      else if (rf < kf) move = tryCastle(kf - 2);
      if (move) {
        applyMove(move);
        return true;
      }
    }

    if (piece && piece.color === moving) {
      selectedSq = sq;
      refreshBoardColors();
      return true;
    }

    let move = null;
    try {
      move = chess.move({ from, to: sq, promotion: 'q' });
    } catch (_) {
      move = null;
    }
    if (!move) {
      worldStatusEl.textContent = 'Illegal move.';
      return true;
    }
    applyMove(move);
    return true;
  }

  function update(dt) {
    for (let i = anims.length - 1; i >= 0; i--) {
      const a = anims[i];
      a.t += dt;
      const u = Math.min(1, a.t / a.dur);
      a.obj.position.lerpVectors(a.from, a.to, u);
      if (u >= 1) {
        a.onDone?.();
        anims.splice(i, 1);
      }
    }
    for (const m of mixers) m.update(dt);
    fx?.updateHits?.();
  }

  function resetBoardTiles() {
    if (!tileBaseColor) return;
    for (let f = 0; f < 8; f++) {
      for (let r = 0; r < 8; r++) {
        const tx = boardOx + f;
        const tz = boardOz + r;
        paintTile(tx, tz, tileBaseColor(tx, tz));
      }
    }
  }

  function dispose() {
    active = false;
    busy = false;
    selectedSq = null;
    fx?.clearHits?.();
    for (const [, p] of [...pieces]) removePiece(p.sq);
    pieces.clear();
    mixers.length = 0;
    anims.length = 0;
    resetBoardTiles();
  }

  function forEachPiece(fn) {
    for (const [, p] of pieces) {
      if (!p.offBoard) fn(p.obj, p);
    }
  }

  return {
    setupBoard,
    handleClick,
    pickPiece,
    getPieceLabel,
    forEachPiece,
    isBoardTile,
    isActive: () => active,
    isBusy: () => busy,
    update,
    dispose,
    PIECE_VALUE,
  };
}

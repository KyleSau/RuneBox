/**
 * Rave zone east of the chess board — dance floor, spotlights, YouTube stage cube.
 */
import { createYoutubeCube, parseYoutubeInput } from './youtube_cube.js';

/** Chess board occupies tiles (2–9, 2–9); rave sits directly east. */
export const RAVE_FLOOR_OX = 11;
export const RAVE_FLOOR_OZ = 2;
export const RAVE_FLOOR_W = 8;
export const RAVE_FLOOR_H = 8;

/** Default: https://www.youtube.com/watch?v=5lthiQoQiRA&t=324s */
export const RAVE_DEFAULT_YOUTUBE_ID = '5lthiQoQiRA';
export const RAVE_DEFAULT_YOUTUBE_START = 324;

export function createRaveWorld(ctx) {
  const {
    THREE, worldGroup, tileToScene, tileMeshes, GRID, TILE,
    cssScene, overlayRoot, audioCtx, getOccluders, getPlayer, createYoutubeCube: makeCube,
  } = ctx;

  const mkCube = makeCube || createYoutubeCube;

  let active = false;
  let raveGroup = null;
  let spotlights = [];
  let spotTargets = [];
  let stageCube = null;
  let youtubeId = RAVE_DEFAULT_YOUTUBE_ID;
  let youtubeStart = RAVE_DEFAULT_YOUTUBE_START;
  let hueT = 0;
  let floorTiles = [];
  let beamGroup = null;

  const FLOOR_DARK = '#120818';
  const FLOOR_LIGHT = '#1e1030';

  function paintTile(tx, tz, color) {
    const m = tileMeshes[tx * GRID + tz];
    if (m) {
      m.material.map = null;
      m.material.color.set(color);
      m.material.needsUpdate = true;
    }
  }

  function paintDanceFloor() {
    floorTiles = [];
    for (let x = 0; x < RAVE_FLOOR_W; x++) {
      for (let z = 0; z < RAVE_FLOOR_H; z++) {
        const tx = RAVE_FLOOR_OX + x;
        const tz = RAVE_FLOOR_OZ + z;
        paintTile(tx, tz, (x + z) % 2 === 0 ? FLOOR_DARK : FLOOR_LIGHT);
        const m = tileMeshes[tx * GRID + tz];
        if (m?.material) {
          m.material.emissive = m.material.emissive || new THREE.Color();
          m.material.emissiveIntensity = 1;
          floorTiles.push(m);
        }
      }
    }
  }

  function resetFloorTiles() {
    if (!ctx.tileBaseColor) return;
    for (let x = 0; x < RAVE_FLOOR_W; x++) {
      for (let z = 0; z < RAVE_FLOOR_H; z++) {
        paintTile(RAVE_FLOOR_OX + x, RAVE_FLOOR_OZ + z, ctx.tileBaseColor(RAVE_FLOOR_OX + x, RAVE_FLOOR_OZ + z));
        const m = tileMeshes[(RAVE_FLOOR_OX + x) * GRID + (RAVE_FLOOR_OZ + z)];
        if (m?.material) {
          m.material.emissive?.setHex(0x000000);
          m.material.emissiveIntensity = 0;
        }
      }
    }
    for (let x = RAVE_FLOOR_OX - 1; x <= RAVE_FLOOR_OX + RAVE_FLOOR_W; x++) {
      paintTile(x, RAVE_FLOOR_OZ - 2, ctx.tileBaseColor(x, RAVE_FLOOR_OZ - 2));
      paintTile(x, RAVE_FLOOR_OZ - 1, ctx.tileBaseColor(x, RAVE_FLOOR_OZ - 1));
    }
  }

  function isInZone(tx, tz) {
    return tx >= RAVE_FLOOR_OX && tx < RAVE_FLOOR_OX + RAVE_FLOOR_W &&
      tz >= RAVE_FLOOR_OZ && tz < RAVE_FLOOR_OZ + RAVE_FLOOR_H;
  }

  function isPlayerInZone(player) {
    if (!player) return false;
    const rsX = player.position.x + ctx.HALF;
    const rsZ = player.position.z + ctx.HALF;
    return isInZone(Math.floor(rsX / TILE), Math.floor(rsZ / TILE));
  }

  function buildStage() {
    raveGroup = new THREE.Group();
    const cx = RAVE_FLOOR_OX + RAVE_FLOOR_W / 2;
    const cz = RAVE_FLOOR_OZ - 1.5;
    const center = tileToScene(cx, cz);

    const deckTop = 18;
    const riserH = deckTop;
    const screenW = TILE * 5.2;
    const screenH = TILE * 2.9;
    const screenDepth = TILE * 0.35;
    // BoxGeometry is center-origin: lift center so the screen sits on the riser.
    const screenCenterY = deckTop + screenH * 0.5 + 6;

    const riser = new THREE.Mesh(
      new THREE.BoxGeometry(TILE * 6.5, riserH, TILE * 2.2),
      new THREE.MeshStandardMaterial({ color: 0x1a1028, roughness: 0.85, metalness: 0.2 }),
    );
    riser.position.set(center.x, riserH / 2, center.z - TILE * 0.15);
    raveGroup.add(riser);

    const stage = new THREE.Mesh(
      new THREE.BoxGeometry(TILE * (RAVE_FLOOR_W + 0.5), 6, TILE * 2.6),
      new THREE.MeshStandardMaterial({ color: 0x120818, roughness: 0.9, metalness: 0.15 }),
    );
    stage.position.set(center.x, 3, center.z + TILE * 0.55);
    raveGroup.add(stage);

    const truss = new THREE.Mesh(
      new THREE.BoxGeometry(TILE * 6, 10, TILE * 1),
      new THREE.MeshStandardMaterial({ color: 0x0a0610, roughness: 0.95 }),
    );
    truss.position.set(center.x, screenCenterY + screenH * 0.5 + 12, center.z - TILE * 0.2);
    raveGroup.add(truss);

    stageCube = mkCube(
      { THREE, overlayRoot: ctx.overlayRoot, audioCtx, getPlayer: ctx.getPlayer },
      {
        position: new THREE.Vector3(center.x, screenCenterY, center.z - TILE * 0.35),
        rotationY: 0,
        width: screenW,
        height: screenH,
        depth: screenDepth,
        youtubeId,
        startSeconds: youtubeStart,
        audioMaxDist: 1800,
      },
    );
    raveGroup.add(stageCube.group);

    for (const sx of [-1, 1]) {
      const spk = new THREE.Mesh(
        new THREE.BoxGeometry(TILE * 1.1, 28, TILE * 1.1),
        new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.9 }),
      );
      spk.position.set(center.x + sx * TILE * 3.4, 14, center.z + TILE * 0.45);
      raveGroup.add(spk);
    }

    worldGroup.add(raveGroup);
  }

  function addSpot(pos, target, hue, intensity = 18, distance = 1400, angle = Math.PI / 4) {
    const t = new THREE.Object3D();
    t.position.copy(target);
    worldGroup.add(t);
    spotTargets.push(t);
    const light = new THREE.SpotLight(0xff0088, intensity, distance, angle, 0.45, 1.2);
    light.position.copy(pos);
    light.target = t;
    light.castShadow = false;
    worldGroup.add(light);
    spotlights.push({ light, baseHue: hue, sweep: false });

    const beamLen = pos.distanceTo(target);
    const beamGeo = new THREE.ConeGeometry(Math.tan(angle) * beamLen * 0.42, beamLen, 10, 1, true);
    const beamMat = new THREE.MeshBasicMaterial({
      color: 0xff44aa,
      transparent: true,
      opacity: 0.07,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    });
    const beam = new THREE.Mesh(beamGeo, beamMat);
    beam.position.copy(pos);
    beam.lookAt(target);
    beam.rotateX(Math.PI / 2);
    if (!beamGroup) {
      beamGroup = new THREE.Group();
      worldGroup.add(beamGroup);
    }
    beamGroup.add(beam);
    spotlights[spotlights.length - 1].beam = beam;
    spotlights[spotlights.length - 1].beamMat = beamMat;
  }

  function buildSpotlights() {
    spotlights = [];
    spotTargets = [];
    const floorCx = RAVE_FLOOR_OX + RAVE_FLOOR_W / 2;
    const floorCz = RAVE_FLOOR_OZ + RAVE_FLOOR_H / 2;
    const center = tileToScene(floorCx, floorCz);
    center.y = 0;
    const stageCenter = tileToScene(floorCx, RAVE_FLOOR_OZ - 1.5);
    stageCenter.y = 200;

    // Corner beams onto the dance floor.
    const corners = [
      [RAVE_FLOOR_OX, RAVE_FLOOR_OZ],
      [RAVE_FLOOR_OX + RAVE_FLOOR_W - 1, RAVE_FLOOR_OZ],
      [RAVE_FLOOR_OX, RAVE_FLOOR_OZ + RAVE_FLOOR_H - 1],
      [RAVE_FLOOR_OX + RAVE_FLOOR_W - 1, RAVE_FLOOR_OZ + RAVE_FLOOR_H - 1],
    ];
    corners.forEach(([tx, tz], i) => {
      const pos = tileToScene(tx, tz);
      pos.y = 140;
      const tgt = center.clone();
      tgt.y = 2;
      addSpot(pos, tgt, i * 0.25, 22, 1200);
    });

    // Mid-edge beams (extra rave coverage).
    const edges = [
      [floorCx, RAVE_FLOOR_OZ],
      [floorCx, RAVE_FLOOR_OZ + RAVE_FLOOR_H - 1],
      [RAVE_FLOOR_OX, floorCz],
      [RAVE_FLOOR_OX + RAVE_FLOOR_W - 1, floorCz],
    ];
    edges.forEach(([tx, tz], i) => {
      const pos = tileToScene(tx, tz);
      pos.y = 120;
      const tgt = center.clone();
      tgt.y = 4;
      addSpot(pos, tgt, 0.15 + i * 0.12, 16, 1000, Math.PI / 3.5);
    });

    // Stage wash from truss.
    for (const sx of [-0.35, 0, 0.35]) {
      const pos = new THREE.Vector3(stageCenter.x + sx * TILE * 4, 95, stageCenter.z - TILE * 0.5);
      const tgt = stageCenter.clone();
      tgt.y = 200;
      addSpot(pos, tgt, 0.55 + sx, 14, 900, Math.PI / 5);
    }

    // Sweeper beams along the long sides (animate in update).
    for (const side of [-1, 1]) {
      const pos = tileToScene(RAVE_FLOOR_OX + RAVE_FLOOR_W / 2 + side * 4.5, floorCz);
      pos.y = 100;
      const tgt = center.clone();
      tgt.y = 8;
      addSpot(pos, tgt, side * 0.3, 18, 1100);
      spotlights[spotlights.length - 1].sweep = true;
      spotlights[spotlights.length - 1].sweepPhase = side > 0 ? 0 : Math.PI;
    }

    const wash = new THREE.PointLight(0x8844ff, 8, 900);
    wash.position.set(center.x, 100, center.z);
    worldGroup.add(wash);
    spotlights.push({ light: wash, baseHue: 0.5, wash: true });

    const floorGlow = new THREE.PointLight(0xff2288, 6, 550);
    floorGlow.position.set(center.x, 40, center.z);
    worldGroup.add(floorGlow);
    spotlights.push({ light: floorGlow, baseHue: 0.85, wash: true, pulse: true });
  }

  function setup() {
    active = true;
    paintDanceFloor();
    for (let x = RAVE_FLOOR_OX - 1; x <= RAVE_FLOOR_OX + RAVE_FLOOR_W; x++) {
      paintTile(x, RAVE_FLOOR_OZ - 1, '#2a1840');
      paintTile(x, RAVE_FLOOR_OZ - 2, '#1a1028');
    }
    buildStage();
    buildSpotlights();
  }

  function update(dt, camera, listenerPos, listenerForward, playerRoot) {
    if (!active) return;
    hueT += dt * 0.35;
    for (let i = 0; i < floorTiles.length; i++) {
      const m = floorTiles[i];
      const h = (hueT * 0.2 + i * 0.09) % 1;
      m.material.emissive.setHSL(h, 0.95, 0.12 + Math.sin(hueT * 2.8 + i) * 0.06);
    }
    for (const s of spotlights) {
      const h = (s.baseHue + hueT * 0.15) % 1;
      s.light.color.setHSL(h, 1, s.wash ? 0.5 : 0.58);
      if (s.beamMat) {
        s.beamMat.color.setHSL(h, 1, 0.55);
        s.beamMat.opacity = 0.05 + Math.sin(hueT * 2.5 + s.baseHue * 5) * 0.04;
      }
      if (s.sweep && s.light.target) {
        const base = tileToScene(RAVE_FLOOR_OX + RAVE_FLOOR_W / 2, RAVE_FLOOR_OZ + RAVE_FLOOR_H / 2);
        base.y = 6;
        s.light.target.position.x = base.x + Math.sin(hueT * 1.4 + (s.sweepPhase || 0)) * TILE * 2.5;
        s.light.target.position.z = base.z + Math.cos(hueT * 1.1 + (s.sweepPhase || 0)) * TILE * 2;
      }
      if (!s.wash) {
        s.light.intensity = 14 + Math.sin(hueT * 2.2 + s.baseHue * 6) * 8;
      } else if (s.pulse) {
        s.light.intensity = 4 + Math.sin(hueT * 3) * 3;
      }
    }
    if (stageCube && camera) {
      const occluders = getOccluders?.(stageCube.group) || [];
      const pl = playerRoot ?? getPlayer?.();
      stageCube.update(camera, listenerPos, listenerForward, occluders, pl);
    }
  }

  function dispose() {
    active = false;
    if (stageCube) {
      stageCube.dispose();
      stageCube = null;
    }
    if (raveGroup) {
      worldGroup?.remove(raveGroup);
      raveGroup.traverse(o => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) o.material.dispose?.();
      });
      raveGroup = null;
    }
    for (const t of spotTargets) worldGroup?.remove(t);
    spotTargets = [];
    for (const s of spotlights) {
      if (s.light.parent) s.light.parent.remove(s.light);
      if (s.beam?.geometry) s.beam.geometry.dispose();
      if (s.beamMat) s.beamMat.dispose();
    }
    spotlights = [];
    if (beamGroup) {
      worldGroup?.remove(beamGroup);
      beamGroup = null;
    }
    floorTiles = [];
    resetFloorTiles();
  }

  function setYoutubeId(id, startSec = youtubeStart) {
    const parsed = parseYoutubeInput(id);
    if (parsed.id) youtubeId = parsed.id;
    else if (id) youtubeId = id;
    const start = parsed.start > 0 ? parsed.start : startSec;
    if (start != null) youtubeStart = start;
    stageCube?.setYoutubeId(youtubeId, youtubeStart);
  }

  return {
    setup,
    update,
    dispose,
    isActive: () => active,
    isInZone,
    isPlayerInZone,
    setYoutubeId,
    floorCenter: () => ({
      x: RAVE_FLOOR_OX + Math.floor(RAVE_FLOOR_W / 2),
      z: RAVE_FLOOR_OZ + Math.floor(RAVE_FLOOR_H / 2),
    }),
  };
}

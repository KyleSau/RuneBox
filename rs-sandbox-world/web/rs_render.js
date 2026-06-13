/**
 * Shared RuneScape → three.js material setup (317 face priority + model layers).
 * Used by rs_viewer.html and RuneChess board.js — keep copies in sync.
 */

/** Matches mesh_assembly.MODEL_LAYER_STRIDE — stacked component model draw order. */
export const MODEL_LAYER_STRIDE = 12;

const OPAQUE_RENDER_BASE = 100;
const TRANSPARENT_RENDER_BASE = 2100;

export function rsModelLayer(priority) {
  return Math.floor(priority / MODEL_LAYER_STRIDE);
}

export function rsFacePriority(priority) {
  return priority % MODEL_LAYER_STRIDE;
}

/** Effective sort key for draw order (layer-major, then face priority). */
export function rsRenderOrder(priority, transparent) {
  const key = rsModelLayer(priority) * MODEL_LAYER_STRIDE + rsFacePriority(priority);
  return transparent ? TRANSPARENT_RENDER_BASE + key : OPAQUE_RENDER_BASE + key;
}

export function geometryHasVertexAlpha(geometry) {
  const col = geometry?.attributes?.color;
  if (!col || col.itemSize < 4) return false;
  const arr = col.array;
  const scale = (col.normalized && arr instanceof Uint8Array) ? (1 / 255) : 1;
  for (let i = 3; i < arr.length; i += col.itemSize) {
    if (arr[i] * scale < 0.98) return true;
  }
  return false;
}

function inheritRsMaterialMeta(src, dst) {
  if (src?.name) dst.name = src.name;
  return dst;
}

export function rsMaterialFlags(name, geometry) {
  const pMatch = /_p(\d+)/.exec(name || '');
  const aMatch = /_a(\d+)/.exec(name || '');
  const priority = pMatch ? parseInt(pMatch[1], 10) : 0;
  const transparent = aMatch !== null || geometryHasVertexAlpha(geometry);
  return { priority, transparent };
}

export function enableMorphMaterials(mesh) {
  const hasMorph = mesh.morphTargetInfluences && mesh.morphTargetInfluences.length > 0;
  if (!hasMorph) return;
  const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  for (const m of mats) {
    if (!m) continue;
    m.morphTargets = true;
    m.needsUpdate = true;
  }
}

function materialUsesAlphaCutout(m) {
  return !!(m && (m.alphaTest > 0 || m.alphaMode === 'MASK'));
}

/** Opaque RS texture pass (not the _a<N> translucent faceAlpha pass). */
function isRsOpaqueTextureMaterial(name) {
  return !!(name && name.includes('_tex_') && !/_a\d+/.test(name));
}

function forceRsTextureCutout(m, THREE) {
  if (!m?.map || !isRsOpaqueTextureMaterial(m.name)) return;
  m.alphaTest = m.alphaTest > 0 ? m.alphaTest : 0.02;
  m.transparent = false;
  m.depthWrite = true;
  m.side = THREE.DoubleSide;
  m.polygonOffset = true;
  m.polygonOffsetFactor = -1;
  m.polygonOffsetUnits = -3;
  // RS model UVs often exceed 0–1; repeat (317 Draw3D) not clamp-to-edge.
  m.map.wrapS = THREE.RepeatWrapping;
  m.map.wrapT = THREE.RepeatWrapping;
  m.map.minFilter = THREE.NearestFilter;
  m.map.magFilter = THREE.NearestFilter;
  m.map.needsUpdate = true;
  m.needsUpdate = true;
}

function applyAlphaCutoutMaterial(src, THREE, { wireframe = false, morphTargets = false, vertexColors = true } = {}) {
  const basic = new THREE.MeshBasicMaterial({
    map: src.map || null,
    vertexColors,
    transparent: false,
    alphaTest: src.alphaTest > 0 ? src.alphaTest : 0.02,
    depthWrite: true,
    depthTest: true,
    side: THREE.DoubleSide,
    wireframe,
    morphTargets,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -3,
  });
  if (basic.map) {
    basic.map.wrapS = THREE.RepeatWrapping;
    basic.map.wrapT = THREE.RepeatWrapping;
    basic.map.magFilter = THREE.NearestFilter;
    basic.map.minFilter = THREE.NearestFilter;
    basic.map.needsUpdate = true;
  }
  return inheritRsMaterialMeta(src, basic);
}

/** 317 faceAlpha pass — vertex COLOR_0 alpha scales texture or HSL (Draw3D alpha blend). */
function applyRsBlendMaterial(src, THREE, { wireframe = false, morphTargets = false, vertexColors = true } = {}) {
  const basic = new THREE.MeshBasicMaterial({
    map: src.map || null,
    vertexColors,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    depthTest: true,
    side: THREE.DoubleSide,
    wireframe,
    morphTargets,
  });
  if (basic.map) {
    basic.map.wrapS = THREE.RepeatWrapping;
    basic.map.wrapT = THREE.RepeatWrapping;
    basic.map.magFilter = THREE.NearestFilter;
    basic.map.minFilter = THREE.NearestFilter;
    basic.map.needsUpdate = true;
  }
  return inheritRsMaterialMeta(src, basic);
}

function applyPrelitMaterial(src, THREE, { wireframe = false, morphTargets = false, vertexColors = true } = {}) {
  const cutout = materialUsesAlphaCutout(src) || isRsOpaqueTextureMaterial(src.name);
  const basic = new THREE.MeshBasicMaterial({
    map: src.map || null,
    vertexColors,
    wireframe,
    morphTargets,
    depthWrite: true,
    depthTest: true,
    side: cutout ? THREE.DoubleSide : THREE.FrontSide,
    alphaTest: cutout ? (src.alphaTest > 0 ? src.alphaTest : 0.02) : 0,
  });
  if (basic.map) {
    const repeat = isRsOpaqueTextureMaterial(src.name);
    basic.map.wrapS = repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
    basic.map.wrapT = repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
    basic.map.magFilter = THREE.NearestFilter;
    basic.map.minFilter = THREE.NearestFilter;
    basic.map.needsUpdate = true;
  }
  return inheritRsMaterialMeta(src, basic);
}

function applyRsMaterialFlags(m, { priority, transparent }, THREE, { disablePolygonOffset = false, doubleSide = false } = {}) {
  m.depthTest = true;
  if (transparent) {
    m.transparent = true;
    m.depthWrite = false;
    m.side = THREE.DoubleSide;
    m.polygonOffset = false;
  } else {
    m.transparent = false;
    m.depthWrite = true;
    m.side = doubleSide ? THREE.DoubleSide : THREE.FrontSide;
    const facePri = rsFacePriority(priority);
    if (!disablePolygonOffset && (facePri > 0 || rsModelLayer(priority) > 0)) {
      m.polygonOffset = true;
      m.polygonOffsetFactor = -1;
      m.polygonOffsetUnits = -(priority * 0.1);
    } else {
      m.polygonOffset = false;
    }
  }
  m.needsUpdate = true;
  return rsRenderOrder(priority, transparent);
}

/**
 * Apply RS draw-order material flags to a loaded GLB root.
 * Opaque primitives write depth; transparent overlays sort after all opaque
 * meshes via renderOrder (layer, then face priority).
 */
export function applyRsMaterials(obj, {
  wireframe = false,
  shadingMode = 'smooth317',
  smoothShading,
  three,
  useLambert = false,
  useStandard = false,
  prelit = false,
} = {}) {
  const THREE = three;
  if (!THREE) throw new Error('applyRsMaterials requires { three: THREE }');

  const flat317 = shadingMode === 'flat317';
  const smooth = smoothShading != null ? smoothShading : shadingMode !== 'flat317';
  const lambert = useLambert || shadingMode === 'lambert';
  const standard = useStandard || shadingMode === 'standard';
  const cutoutSide = (m) => (materialUsesAlphaCutout(m) ? THREE.DoubleSide : THREE.FrontSide);

  obj.traverse((o) => {
    if (!o.isMesh) return;
    enableMorphMaterials(o);
    let mats = Array.isArray(o.material) ? o.material.slice() : [o.material];
    let changed = false;
    const morph = !!(o.morphTargetInfluences && o.morphTargetInfluences.length);

    let renderOrder = 0;
    for (let i = 0; i < mats.length; i++) {
      let m = mats[i];
      const flags = rsMaterialFlags(m.name, o.geometry);

      if (flags.transparent) {
        m = applyRsBlendMaterial(m, THREE, {
          wireframe,
          morphTargets: morph,
          vertexColors: true,
        });
        mats[i] = m;
        changed = true;
      } else if (
        (materialUsesAlphaCutout(m) || isRsOpaqueTextureMaterial(m.name))
        && (m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)
      ) {
        m = applyAlphaCutoutMaterial(m, THREE, {
          wireframe,
          morphTargets: morph,
          vertexColors: !m.map,
        });
        mats[i] = m;
        changed = true;
      } else if (
        prelit
        && !flags.transparent
        && !materialUsesAlphaCutout(m)
        && !isRsOpaqueTextureMaterial(m.name)
        && (m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)
      ) {
        m = applyPrelitMaterial(m, THREE, {
          wireframe,
          morphTargets: morph,
          vertexColors: !m.map,
        });
        mats[i] = m;
        changed = true;
      } else if (
        standard
        && !flags.transparent
        && (m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)
      ) {
        m = new THREE.MeshStandardMaterial({
          map: m.map,
          vertexColors: true,
          flatShading: flat317,
          roughness: 1,
          metalness: 0,
          morphTargets: morph,
          alphaTest: materialUsesAlphaCutout(m) ? (m.alphaTest > 0 ? m.alphaTest : 0.02) : 0,
          side: cutoutSide(m),
        });
        mats[i] = m;
        changed = true;
      } else if (
        lambert
        && !flags.transparent
        && (m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)
      ) {
        m = new THREE.MeshLambertMaterial({
          map: m.map,
          vertexColors: true,
          flatShading: flat317,
          morphTargets: morph,
          alphaTest: m.alphaTest || 0,
          side: cutoutSide(m),
        });
        mats[i] = m;
        changed = true;
      } else if (materialUsesAlphaCutout(m) || isRsOpaqueTextureMaterial(m.name)) {
        m.alphaTest = m.alphaTest > 0 ? m.alphaTest : 0.02;
        m.transparent = false;
        m.depthWrite = true;
        m.side = THREE.DoubleSide;
        m.polygonOffset = false;
        if (m.map) {
          m.map.wrapS = THREE.RepeatWrapping;
          m.map.wrapT = THREE.RepeatWrapping;
          m.map.magFilter = THREE.NearestFilter;
          m.map.minFilter = THREE.NearestFilter;
          m.map.needsUpdate = true;
        }
      } else {
        m.wireframe = wireframe;
        m.flatShading = flat317 || !smooth;
        m.vertexColors = true;
      }
      if (!flags.transparent) forceRsTextureCutout(m, THREE);
      const isCutout = materialUsesAlphaCutout(m) || isRsOpaqueTextureMaterial(m.name);
      renderOrder = Math.max(renderOrder, applyRsMaterialFlags(m, flags, THREE, {
        disablePolygonOffset: !isCutout,
        doubleSide: isCutout,
      }));
    }
    o.renderOrder = renderOrder;

    if (changed) o.material = Array.isArray(o.material) ? mats : mats[0];
  });
}

/** Pre-lit RS terrain — HSL + lightmap baked into vertex colours (SceneBuilder mulHSL). */
export function applyTerrainMaterials(obj, { wireframe = false, shadingMode = 'smooth317', three } = {}) {
  const THREE = three;
  if (!THREE) throw new Error('applyTerrainMaterials requires { three: THREE }');
  let texLayer = 10;
  obj.traverse((o) => {
    if (!o.isMesh) return;
    if (o.geometry?.boundingSphere) {
      o.frustumCulled = true;
    }
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const isTerrainTex = mats.some((m) => m?.name && String(m.name).startsWith('terrain_tex_'));
    o.renderOrder = isTerrainTex ? texLayer++ : 0;
    const next = mats.map((m) => {
      if (!m) return m;
      const texCutout = !!(m.map && m.name && String(m.name).startsWith('terrain_tex_'));
      const cutout = materialUsesAlphaCutout(m) || texCutout;
      // Never use transparent blending on terrain — zero-alpha underlay corners caused
      // depthWrite=false and view-dependent holes (black ground until the camera moved).
      const common = {
        map: m.map || null,
        vertexColors: !m.map || texCutout,
        wireframe,
        depthWrite: true,
        depthTest: true,
        side: THREE.DoubleSide,
        transparent: false,
        alphaTest: cutout ? (m.alphaTest > 0 ? m.alphaTest : 0.05) : 0,
        polygonOffset: isTerrainTex,
        polygonOffsetFactor: isTerrainTex ? -1 : 0,
        polygonOffsetUnits: isTerrainTex ? -2 : 0,
      };
      // Always unlit: colours are already palette-lit HSL from flo.dat + corner lightmap.
      const mat = new THREE.MeshBasicMaterial(common);
      if (mat.map) {
        mat.map.magFilter = THREE.NearestFilter;
        mat.map.minFilter = THREE.NearestFilter;
        mat.map.wrapS = texCutout ? THREE.ClampToEdgeWrapping : THREE.RepeatWrapping;
        mat.map.wrapT = texCutout ? THREE.ClampToEdgeWrapping : THREE.RepeatWrapping;
        mat.map.needsUpdate = true;
      }
      return mat;
    });
    o.material = Array.isArray(o.material) ? next : next[0];
  });
}

/** @deprecated Use applyRsMaterials — kept for rs_viewer call sites. */
export function applyWire(obj, options) {
  return applyRsMaterials(obj, options);
}

// Smooth interpolation between RS keyframes, but NEVER on scale tracks: cubic
// smoothing overshoots and momentarily balloons body parts. Scale stays linear,
// and quaternion stays on the default slerp (three.js ignores smooth there).
export function applyClipInterpolation(clip, { tweening = true, three } = {}) {
  const THREE = three;
  if (!THREE || !clip) return;
  for (const track of clip.tracks) {
    if (track.name.endsWith('.scale') || track.name.endsWith('.quaternion')) continue;
    // RS morph seqs are discrete frame holds — never cubic-smooth weight tracks.
    if (track.name.includes('morphTargetInfluences') || track.name.endsWith('.weights')) continue;
    track.setInterpolation(tweening ? THREE.InterpolateSmooth : THREE.InterpolateLinear);
  }
}

export function tuneClipInterp(clip, three, tweening = true) {
  applyClipInterpolation(clip, { tweening, three });
}

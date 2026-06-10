/**
 * Custom NPC / character creator — browse idk.dat body parts and compose a GLB.
 */

export const PART_NAMES = ['head', 'jaw', 'torso', 'arms', 'hands', 'legs', 'feet'];
export const COLOR_NAMES = ['hair', 'torso', 'legs', 'feet', 'skin'];

export function createNpcCreator() {
  let idkData = null;
  let kitCatalog = [];
  let npcHints = new Map(); // kitId -> npc name hint
  let gender = 1; // female default for queen builds
  let activePart = 0;
  let kits = [-1, -1, -1, -1, -1, -1, -1];
  let colors = [0, 0, 0, 0, 0];
  let extraModels = [];
  let previewKitOnly = false;
  let creatorMode = 'human'; // 'human' | 'npc'
  let baseNpcId = null;
  let cloneModelIds = [];
  let modelParts = []; // [{id, slots, ...}] from clone.json
  let recolorPairs = []; // [{src, dst, srcRgb?, dstRgb?}, ...]

  function partIndexForKit(kit) {
    const slot = PART_NAMES.indexOf(kit.part);
    return slot >= 0 ? slot : 0;
  }

  function kitsForGender(genderCode = gender) {
    const gStr = genderCode === 1 ? 'female' : 'male';
    return kitCatalog.filter(k => k.gender === gStr && !k.selectable);
  }

  function kitsForPart(partIdx, g = gender) {
    const part = PART_NAMES[partIdx];
    const gStr = g === 1 ? 'female' : 'male';
    return kitCatalog.filter(k => k.part === part && k.gender === gStr && !k.selectable);
  }

  function buildNpcHints(allNpcs) {
    npcHints = new Map();
    if (!allNpcs?.length || !kitCatalog.length) return;
    const modelToKit = new Map();
    for (const k of kitCatalog) {
      for (const mid of k.modelIds || []) {
        if (!modelToKit.has(mid)) modelToKit.set(mid, k.id);
      }
    }
    for (const npc of allNpcs) {
      if (!npc.modelIds?.length || !npc.name) continue;
      for (const mid of npc.modelIds) {
        const kid = modelToKit.get(mid);
        if (kid != null && !npcHints.has(kid)) {
          npcHints.set(kid, npc.name);
        }
      }
    }
  }

  function kitLabel(k) {
    const hint = npcHints.get(k.id);
    const models = (k.modelIds || []).join(',');
    const heads = (k.headModelIds || []).length ? ` · chatheads ${k.headModelIds.join(',')}` : '';
    return hint
      ? `${hint} — kit #${k.id} (models ${models}${heads})`
      : `kit #${k.id} — ${k.part} (models ${models}${heads})`;
  }

  function filterKits(query, partIdx = activePart) {
    const q = (query || '').trim().toLowerCase();
    let list = kitsForPart(partIdx);
    if (!q) return list;
    return list.filter(k => {
      const label = kitLabel(k).toLowerCase();
      return label.includes(q)
        || String(k.id).includes(q)
        || (k.modelIds || []).some(m => String(m).includes(q))
        || (k.headModelIds || []).some(h => String(h).includes(q));
    });
  }

  function loadNpcClone(npc, detail) {
    if (!npc) return;
    creatorMode = 'npc';
    baseNpcId = npc.id;
    modelParts = detail?.modelParts || [];
    cloneModelIds = modelParts.length
      ? modelParts.map(p => p.id)
      : (npc.modelIds || []).slice();
    const src = detail?.recolors || npc.recolors || [];
    recolorPairs = src.map(p => ({
      src: p.src,
      dst: p.dst,
      srcRgb: p.srcRgb,
      dstRgb: p.dstRgb,
    }));
    previewKitOnly = false;
  }

  function setRecolorSrc(src, dst, dstRgb) {
    const i = recolorPairs.findIndex(p => p.src === src);
    if (i >= 0) {
      recolorPairs[i].dst = dst;
      if (dstRgb) recolorPairs[i].dstRgb = dstRgb;
    } else {
      recolorPairs.push({ src, dst, dstRgb });
    }
    previewKitOnly = false;
  }

  function effectiveDst(src) {
    const p = recolorPairs.find(r => r.src === src);
    return p ? p.dst : src;
  }

  function recolorQuery() {
    if (!recolorPairs.length) return '';
    return recolorPairs.map(p => `${p.src}:${p.dst}`).join(',');
  }

  function modelGlbUrl(modelId, opts = {}) {
    const params = [];
    const rec = opts.recolor ?? recolorQuery();
    if (rec) params.push(`recolor=${rec}`);
    params.push(`t=${Date.now()}`);
    return `/api/model/${modelId}.glb?${params.join('&')}`;
  }

  function removeModelPart(modelId) {
    cloneModelIds = cloneModelIds.filter(id => id !== modelId);
    modelParts = modelParts.filter(p => p.id !== modelId);
    previewKitOnly = false;
  }

  function addModelPart(modelId) {
    if (modelId < 0 || cloneModelIds.includes(modelId)) return;
    cloneModelIds.push(modelId);
    modelParts.push({ id: modelId, missing: false, slots: [] });
    previewKitOnly = false;
  }

  function npcCustomGlbUrl(opts = {}) {
    const base = opts.baseNpcId ?? baseNpcId;
    if (!base) return null;
    const params = [`base=${base}`];
    const mids = opts.cloneModelIds ?? cloneModelIds;
    if (mids?.length) params.push(`models=${mids.join(',')}`);
    const pairs = opts.recolorPairs ?? recolorPairs;
    if (pairs?.length) {
      params.push(`recolor=${pairs.map(p => `${p.src}:${p.dst}`).join(',')}`);
    }
    const extra = opts.extraModels ?? extraModels;
    if (extra.length) params.push(`extra=${extra.join(',')}`);
    params.push(`t=${Date.now()}`);
    return `/api/npc-custom.glb?${params.join('&')}`;
  }

  function previewGlbUrl(opts = {}) {
    const mode = opts.creatorMode ?? creatorMode;
    if (mode === 'npc') return npcCustomGlbUrl(opts);
    if (opts.previewKitOnly ?? previewKitOnly) {
      const kitId = opts.kitId;
      if (kitId >= 0) return kitPreviewUrl(kitId);
    }
    return customGlbUrl(opts);
  }

  function customGlbUrl(opts = {}) {
    const params = [`gender=${opts.gender ?? gender}`];
    const k = opts.kits ?? kits;
    const c = opts.colors ?? colors;
    for (let i = 0; i < 7; i++) params.push(`k${i}=${k[i] ?? -1}`);
    for (let i = 0; i < 5; i++) params.push(`c${i}=${c[i] ?? 0}`);
    const extra = opts.extraModels ?? extraModels;
    if (extra.length) params.push(`extra=${extra.join(',')}`);
    params.push(`t=${Date.now()}`);
    return `/api/custom.glb?${params.join('&')}`;
  }

  function kitPreviewUrl(kitId) {
    return `/api/idk-kit/${kitId}.glb?t=${Date.now()}`;
  }

  function applyDefaults(idkManifest) {
    idkData = idkManifest;
    const g = gender === 1 ? idkManifest.female : idkManifest.male;
    kits = (g?.defaults || []).slice();
    colors = [0, 0, 0, 0, 0];
    extraModels = [];
    previewKitOnly = false;
  }

  function applyQueenPreset() {
    gender = 1;
    applyDefaults(idkData);
    // Light/white clothing tints on torso + legs; pick first female head/torso options.
    colors = [0, 14, 14, 0, 0];
    const heads = kitsForPart(0, 1);
    const torsos = kitsForPart(2, 1);
    if (heads.length) kits[0] = heads[0].id;
    if (torsos.length) kits[2] = torsos[Math.min(3, torsos.length - 1)].id;
    previewKitOnly = false;
  }

  function setKit(partIdx, kitId) {
    kits[partIdx] = kitId;
    previewKitOnly = false;
  }

  function addExtraFromNpc(npc) {
    if (!npc?.modelIds?.length) return;
    for (const mid of npc.modelIds) {
      if (!extraModels.includes(mid)) extraModels.push(mid);
    }
    previewKitOnly = false;
  }

  async function loadCatalog() {
    const r = await fetch('/api/idk-kits.json?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('idk-kits HTTP ' + r.status);
    const data = await r.json();
    kitCatalog = data.kits || [];
    return data;
  }

  return {
    get creatorMode() { return creatorMode; },
    set creatorMode(v) { creatorMode = v; previewKitOnly = false; },
    get baseNpcId() { return baseNpcId; },
    get cloneModelIds() { return cloneModelIds.slice(); },
    set cloneModelIds(v) { cloneModelIds = v.slice(); previewKitOnly = false; },
    get modelParts() { return modelParts.map(p => ({ ...p, slots: (p.slots || []).map(s => ({ ...s })) })); },
    get recolorPairs() { return recolorPairs.map(p => ({ ...p })); },
    set recolorPairs(v) {
      recolorPairs = v.map(p => ({ src: p.src, dst: p.dst, srcRgb: p.srcRgb, dstRgb: p.dstRgb }));
      previewKitOnly = false;
    },
    get gender() { return gender; },
    set gender(v) { gender = v; previewKitOnly = false; },
    get activePart() { return activePart; },
    set activePart(v) { activePart = v; },
    get kits() { return kits.slice(); },
    get colors() { return colors.slice(); },
    set colors(v) { colors = v.slice(); previewKitOnly = false; },
    get extraModels() { return extraModels.slice(); },
    set extraModels(v) { extraModels = v.slice(); previewKitOnly = false; },
    get previewKitOnly() { return previewKitOnly; },
    set previewKitOnly(v) { previewKitOnly = v; },
    get idkData() { return idkData; },
    PART_NAMES,
    COLOR_NAMES,
    loadCatalog,
    buildNpcHints,
    applyDefaults,
    applyQueenPreset,
    setKit,
    addExtraFromNpc,
    loadNpcClone,
    setRecolorSrc,
    effectiveDst,
    modelGlbUrl,
    removeModelPart,
    addModelPart,
    kitsForPart,
    filterKits,
    kitLabel,
    customGlbUrl,
    npcCustomGlbUrl,
    previewGlbUrl,
    kitPreviewUrl,
    partIndexForKit,
  };
}

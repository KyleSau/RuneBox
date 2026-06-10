/**
 * YouTube video on a literal 3D cube: WebGL frame mesh + 2D iframe overlay
 * tracked to the front face (avoids CSS3D matrix3d which breaks YouTube embeds).
 */
/** Accept bare id or full youtube.com / youtu.be URLs. */
export function parseYoutubeInput(raw) {
  const s = (raw || '').trim();
  if (!s) return { id: '', start: 0 };
  try {
    if (/^[\w-]{6,}$/.test(s) && !s.includes('/')) {
      return { id: s, start: 0 };
    }
    const url = s.startsWith('http') ? new URL(s) : new URL('https://' + s);
    let id = url.searchParams.get('v') || '';
    if (!id && url.hostname.includes('youtu.be')) {
      id = url.pathname.replace(/^\//, '').split('/')[0];
    }
    let start = 0;
    const t = url.searchParams.get('t') || url.searchParams.get('start');
    if (t) {
      if (/^\d+$/.test(t)) start = parseInt(t, 10);
      else {
        const m = t.match(/(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?/);
        if (m) {
          start = (parseInt(m[1] || 0, 10) * 3600)
            + (parseInt(m[2] || 0, 10) * 60)
            + parseInt(m[3] || 0, 10);
        }
      }
    }
    return { id, start };
  } catch (_) {
    return { id: s, start: 0 };
  }
}

function embedOrigin() {
  const o = window.location.origin;
  if (o && o !== 'null' && !o.startsWith('file:')) return o;
  return `${window.location.protocol}//${window.location.hostname || '127.0.0.1'}:${window.location.port || '8848'}`;
}

function buildEmbedSrc(id, startAt) {
  const origin = embedOrigin();
  const start = Math.max(0, Math.floor(startAt));
  const params = new URLSearchParams({
    autoplay: '1',
    mute: '1',
    playsinline: '1',
    rel: '0',
    modestbranding: '1',
    enablejsapi: '1',
    origin,
    widget_referrer: origin,
    iv_load_policy: '3',
    fs: '0',
  });
  if (start > 0) params.set('start', String(start));
  return `https://www.youtube.com/embed/${encodeURIComponent(id)}?${params}`;
}

/**
 * @param {object} ctx — { THREE, overlayRoot?, audioCtx?, getPlayer? }
 */
export function createYoutubeCube(ctx, opts) {
  const { THREE } = ctx;
  const {
    position,
    rotationY = 0,
    width,
    height,
    depth = 24,
    youtubeId = 'jfKfPfyJRdk',
    startSeconds = 0,
    audioMaxDist = 1600,
  } = opts;

  const group = new THREE.Group();
  if (position) group.position.copy(position);
  group.rotation.y = rotationY;

  const pxW = 640;
  const pxH = Math.round(pxW * (height / width));
  const faceZ = depth / 2 + 4;

  const shellMat = new THREE.MeshStandardMaterial({
    color: 0x141018,
    roughness: 0.85,
    metalness: 0.15,
    emissive: 0x0a000f,
  });
  const cube = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), shellMat);
  group.add(cube);

  const bezel = new THREE.Mesh(
    new THREE.BoxGeometry(width + 12, height + 12, 6),
    new THREE.MeshStandardMaterial({ color: 0x2a1838, emissive: 0x330044, roughness: 0.6 }),
  );
  bezel.position.z = depth / 2 + 2;
  group.add(bezel);

  const overlayRoot = ctx.overlayRoot || document.getElementById('app');
  const host = document.createElement('div');
  host.style.position = 'absolute';
  host.style.left = '0';
  host.style.top = '0';
  host.style.width = pxW + 'px';
  host.style.height = pxH + 'px';
  host.style.background = '#000';
  host.style.overflow = 'hidden';
  host.style.border = '2px solid #1a1028';
  host.style.pointerEvents = 'none';
  host.style.zIndex = '3';
  host.style.display = 'none';
  const mount = document.createElement('div');
  mount.style.width = '100%';
  mount.style.height = '100%';
  mount.style.pointerEvents = 'none';
  host.appendChild(mount);
  overlayRoot.appendChild(host);

  const _faceWorld = new THREE.Vector3();
  const _camPos = new THREE.Vector3();
  const _rayDir = new THREE.Vector3();
  const _ray = new THREE.Raycaster();
  const _ndc = new THREE.Vector3();
  const _box = new THREE.Box3();
  const _boxCenter = new THREE.Vector3();
  const _boxPts = [
    new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(),
    new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(),
  ];
  const _screenPts = [
    new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3(),
  ];
  const _proj = [
    { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 }, { x: 0, y: 0 },
  ];

  let iframe = null;
  let currentId = youtubeId;
  let currentStart = startSeconds;
  let screenVisible = false;
  let unmuteHooked = false;

  function setScreenVisible(show) {
    screenVisible = show;
    host.style.display = show ? 'block' : 'none';
    host.style.visibility = show ? 'visible' : 'hidden';
  }

  function bindPlayer(id, startAt = 0) {
    currentId = id;
    currentStart = startAt;
    if (!id) return;

    mount.innerHTML = '';
    iframe = document.createElement('iframe');
    iframe.src = buildEmbedSrc(id, startAt);
    iframe.width = String(pxW);
    iframe.height = String(pxH);
    iframe.style.border = '0';
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.pointerEvents = 'none';
    iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = 'strict-origin-when-cross-origin';
    iframe.title = 'Rave stage video';
    mount.appendChild(iframe);

    if (!unmuteHooked) {
      unmuteHooked = true;
      document.addEventListener('pointerdown', () => {
        try {
          iframe?.contentWindow?.postMessage(JSON.stringify({
            event: 'command',
            func: 'unMute',
            args: [],
          }), '*');
          iframe?.contentWindow?.postMessage(JSON.stringify({
            event: 'command',
            func: 'setVolume',
            args: [70],
          }), '*');
        } catch (_) { /* ignore */ }
      }, { once: true });
    }
  }

  bindPlayer(youtubeId, startSeconds);

  function speakerWorldPos(target = new THREE.Vector3()) {
    group.updateMatrixWorld(true);
    return target.set(0, 0, depth / 2 + 8).applyMatrix4(group.matrixWorld);
  }

  function projectCorner(worldPt, camera, w, h) {
    _ndc.copy(worldPt).project(camera);
    return {
      x: (_ndc.x * 0.5 + 0.5) * w,
      y: (-_ndc.y * 0.5 + 0.5) * h,
      z: _ndc.z,
    };
  }

  function syncScreenOverlay(camera) {
    group.updateMatrixWorld(true);
    _faceWorld.set(0, 0, faceZ).applyMatrix4(group.matrixWorld);

    const w = window.innerWidth;
    const h = window.innerHeight;
    const hw = width * 0.5;
    const hh = height * 0.5;
    _screenPts[0].set(-hw, -hh, faceZ).applyMatrix4(group.matrixWorld);
    _screenPts[1].set(hw, -hh, faceZ).applyMatrix4(group.matrixWorld);
    _screenPts[2].set(hw, hh, faceZ).applyMatrix4(group.matrixWorld);
    _screenPts[3].set(-hw, hh, faceZ).applyMatrix4(group.matrixWorld);

    let minX = Infinity; let maxX = -Infinity;
    let minY = Infinity; let maxY = -Infinity;
    let behind = false;
    for (let i = 0; i < 4; i++) {
      const p = projectCorner(_screenPts[i], camera, w, h);
      _proj[i].x = p.x;
      _proj[i].y = p.y;
      if (p.z > 1) behind = true;
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }

    if (behind || maxX < 0 || maxY < 0 || minX > w || minY > h) {
      return { visible: false, faceWorld: _faceWorld };
    }

    const bw = Math.max(8, maxX - minX);
    const bh = Math.max(8, maxY - minY);
    host.style.left = minX + 'px';
    host.style.top = minY + 'px';
    host.style.width = bw + 'px';
    host.style.height = bh + 'px';

    const rel = _proj.map(p => `${((p.x - minX) / bw) * 100}% ${((p.y - minY) / bh) * 100}%`);
    host.style.clipPath = `polygon(${rel.join(', ')})`;
    host.style.webkitClipPath = host.style.clipPath;

    return { visible: true, faceWorld: _faceWorld, minX, maxX, minY, maxY };
  }

  function ndcOverlaps(aMinX, aMaxX, aMinY, aMaxY, bMinX, bMaxX, bMinY, bMaxY) {
    return aMinX <= bMaxX && aMaxX >= bMinX && aMinY <= bMaxY && aMaxY >= bMinY;
  }

  function playerBlocksScreen(camera, screenPos, playerRoot, screenRect) {
    if (!playerRoot || !camera || !screenRect?.visible) return false;
    _box.setFromObject(playerRoot);
    if (_box.isEmpty()) return false;

    camera.getWorldPosition(_camPos);
    const distToScreen = _camPos.distanceTo(screenPos);
    _box.getCenter(_boxCenter);
    const distToPlayer = _camPos.distanceTo(_boxCenter);
    if (distToPlayer >= distToScreen - 40) return false;

    const min = _box.min;
    const max = _box.max;
    _boxPts[0].set(min.x, min.y, min.z);
    _boxPts[1].set(max.x, min.y, min.z);
    _boxPts[2].set(min.x, max.y, min.z);
    _boxPts[3].set(max.x, max.y, min.z);
    _boxPts[4].set(min.x, min.y, max.z);
    _boxPts[5].set(max.x, min.y, max.z);
    _boxPts[6].set(min.x, max.y, max.z);
    _boxPts[7].set(max.x, max.y, max.z);

    const w = window.innerWidth;
    const h = window.innerHeight;
    let pMinX = Infinity; let pMaxX = -Infinity;
    let pMinY = Infinity; let pMaxY = -Infinity;
    for (const p of _boxPts) {
      const q = projectCorner(p, camera, w, h);
      pMinX = Math.min(pMinX, q.x);
      pMaxX = Math.max(pMaxX, q.x);
      pMinY = Math.min(pMinY, q.y);
      pMaxY = Math.max(pMaxY, q.y);
    }

    return ndcOverlaps(
      screenRect.minX, screenRect.maxX, screenRect.minY, screenRect.maxY,
      pMinX, pMaxX, pMinY, pMaxY,
    );
  }

  function updateOcclusion(camera, occluders, playerRoot) {
    const screenRect = syncScreenOverlay(camera);
    if (!camera || !screenRect.visible) {
      setScreenVisible(false);
      return false;
    }

    if (playerBlocksScreen(camera, screenRect.faceWorld, playerRoot, screenRect)) {
      setScreenVisible(false);
      return false;
    }

    if (occluders?.length) {
      camera.getWorldPosition(_camPos);
      const dist = _camPos.distanceTo(screenRect.faceWorld);
      _rayDir.subVectors(screenRect.faceWorld, _camPos);
      if (_rayDir.lengthSq() >= 1) {
        _rayDir.normalize();
        _ray.set(_camPos, _rayDir);
        _ray.far = Math.max(0, dist - 12);
        const hits = _ray.intersectObjects(occluders, true);
        if (hits.length > 0 && hits[0].distance < dist - 12) {
          setScreenVisible(false);
          return false;
        }
      }
    }

    setScreenVisible(true);
    return true;
  }

  function updateAudio(listenerPos, listenerForward) {
    if (!listenerPos) return;
    const sp = speakerWorldPos();
    const dist = listenerPos.distanceTo(sp);
    const t = Math.max(0, 1 - dist / audioMaxDist);
    const vol = Math.round(t * t * 100);

    const actx = ctx.audioCtx?.();
    if (actx && actx !== false && actx.listener) {
      if (actx.state === 'suspended') actx.resume();
      actx.listener.positionX.value = listenerPos.x;
      actx.listener.positionY.value = listenerPos.y;
      actx.listener.positionZ.value = listenerPos.z;
      if (listenerForward) {
        actx.listener.forwardX.value = listenerForward.x;
        actx.listener.forwardY.value = listenerForward.y;
        actx.listener.forwardZ.value = listenerForward.z;
        actx.listener.upX.value = 0;
        actx.listener.upY.value = 1;
        actx.listener.upZ.value = 0;
      }
    }

    if (iframe?.contentWindow && screenVisible) {
      try {
        iframe.contentWindow.postMessage(JSON.stringify({
          event: 'command',
          func: 'setVolume',
          args: [Math.max(0, Math.min(100, vol))],
        }), '*');
      } catch (_) { /* ignore */ }
    }
  }

  function update(camera, listenerPos, listenerForward, occluders, playerRoot) {
    updateOcclusion(camera, occluders, playerRoot ?? ctx.getPlayer?.());
    updateAudio(listenerPos, listenerForward);
  }

  function setYoutubeId(id, startAt = currentStart) {
    if (!id) return;
    if (id === currentId && startAt === currentStart) return;
    bindPlayer(id, startAt);
  }

  function dispose() {
    host.remove();
    iframe = null;
    cube.geometry.dispose();
    shellMat.dispose();
    bezel.geometry.dispose();
    bezel.material.dispose();
  }

  return {
    group,
    speakerWorldPos,
    updateOcclusion,
    updateAudio,
    update,
    setYoutubeId,
    dispose,
  };
}

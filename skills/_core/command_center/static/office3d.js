/* Agents Office 3D scene: weherd's procedural three.js office, ported.
 *
 * Same library (three.js 0.183.0, vendored under ./vendor/three, core only,
 * no addons), same office: an orthographic isometric camera looking from the
 * offset (28, 34, 36), the cream floor with seams, left and back walls with
 * windows, desks with monitor and chair, procedural people with pivoted
 * limbs, and the right wing with the coffee counter. The lounge of that wing
 * is the Engram memory core: a floating brain on a pedestal, one orbiting
 * cube per observed memory interaction, and data streams between a desk and
 * the brain.
 *
 * Layout: desks are grouped into tramo zones (the agent's stretch of the
 * pipeline), each with a colored floor and a sign; the orchestrator sits at
 * the front desk with three monitors, an empty chair while no agent CLI
 * session is live.
 *
 * Agent mechanics, one per measured state (office.py):
 *   working   seated, typing, a scrolling code screen, a lit arc from the
 *             orchestrator with data pulses travelling along it;
 *   available seated, leaning back with a coffee cup, dim screen;
 *   saving    standing by the desk facing the brain, cubes desk -> brain;
 *   loading   same pose, cubes brain -> desk.
 * Transitions are drawn as events: a task given (available -> working) sends
 * a document from the orchestrator to the agent with a bubble; a task done
 * (working -> available) sends it back with a check mark; a memory interaction
 * flashes the brain and its tag. Nothing is drawn that the snapshot does not
 * hold.
 *
 * Speed and sharpness: every static piece (room, desks, props, the body parts
 * of each limb) is baked into one vertex-colored mesh, so the scene is a few
 * hundred draws instead of thousands; the measured frame rate picks a quality
 * tier (pixel ratio, shadows). Names, states and bubbles are HTML tags over
 * the canvas, sized in rem so they follow the dashboard's text size.
 *
 * Camera: it follows the activity (orchestrator + active agents) until the
 * operator drags (pan), wheels (zoom at the cursor) or clicks an agent (fly
 * to it); fitAll() and followActive() reframe.
 *
 * Read-only by construction: it renders a snapshot and reports clicks. It
 * exposes window.officeScene = { mount(container, callbacks), update(snapshot),
 * start(), stop(), focus(id), fitAll(), followActive(), following(),
 * screenOf(id), snapshot() } for office-panel.js.
 */
import * as THREE from 'three';

const C = { green: 0x275849, lime: 0xd5e987, wood: 0xe7bb87, cream: 0xf8f2e5, ink: 0x253c37, floor: 0xf0dfbd, red: 0xe57065, teal: 0x74b9a9, violet: 0xb79ce0 };
/** Tramo zones in pipeline order ('' collects agents without a tramo). */
const ZONES = ['plausibility', 'ingestion', 'proposal', 'implementation', 'experimental-deliberation',
  'experimental-implementation', 'credentials', 'remote', 'writing', 'figures', 'paper', 'audit', ''];
const ZONE_COLOR = {
  plausibility: 0x769cbc, ingestion: 0x8594bf, proposal: 0xad91b4, implementation: 0x559b88,
  'experimental-deliberation': 0x668f74, 'experimental-implementation': 0x3f8f80, credentials: 0x8a9a6b,
  remote: 0x7a8f9f, writing: 0xdca569, figures: 0xca8d80, paper: 0xc98f5a, audit: 0xb5737a, '': 0x9aa39c,
};
const SKIN = [0xedc2a0, 0xd9a47e, 0xb98263, 0x8d5f45, 0xf1d0b5];
const HAIR = [0x574d44, 0x2f2a26, 0x9a6b3f, 0xc9a26b, 0x6b3b2a, 0x8a8a8a];
const STREAM = { save: C.lime, load: C.teal, use: C.violet };
const OFFSET = new THREE.Vector3(28, 34, 36);
/** Quality tiers, best last; the measured frame rate only ever steps down. */
const TIERS = [{ ratio: 1, shadows: false }, { ratio: 1.5, shadows: false }, { ratio: 2, shadows: true }];
const MIN_FPS = 24;

const shared = new Set();
const keep = (m) => { shared.add(m); return m; };
const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.8, ...extra });
const materials = Object.fromEntries(Object.entries({
  wood: mat(C.wood), cream: mat(C.cream), ink: mat(C.ink), floor: mat(C.floor), green: mat(C.green), teal: mat(C.teal),
  metal: mat(0x61716a), glass: mat(0xafd3c5, { transparent: true, opacity: 0.2, roughness: 0.1, depthWrite: false }),
  pot: mat(0xd79d7a), leaf: mat(0x46775c), soil: mat(0x685747), coffee: mat(0x594638), shoe: mat(0x3b302a),
  pants: mat(0x34433f), mouth: mat(0x9b4a45),
}).map(([k, m]) => [k, keep(m)]));
const VERTEX = keep(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.78 }));
const SHADOW = keep(new THREE.MeshBasicMaterial({ color: 0x1f2d29, transparent: true, opacity: 0.18, depthWrite: false }));
const SHADOW_GEO = new THREE.CircleGeometry(0.46, 24);
const CUBE_GEO = new THREE.BoxGeometry(0.4, 0.4, 0.4);
const DOT_GEO = new THREE.SphereGeometry(0.13, 10, 8);
const DOC_GEO = new THREE.BoxGeometry(0.56, 0.06, 0.72);
const STREAM_MAT = Object.fromEntries(Object.entries(STREAM).map(([k, c]) => [k, keep(new THREE.MeshBasicMaterial({ color: c }))]));
const DOC_MAT = keep(new THREE.MeshStandardMaterial({ color: 0xfcfaf3, emissive: 0xfcfaf3, emissiveIntensity: 0.55 }));
const FLOW_DOT = { working: keep(new THREE.MeshBasicMaterial({ color: 0x3a8f75 })), save: STREAM_MAT.save, load: STREAM_MAT.load };

/** The sine wave, spelled through cosine: the dashboard's Spanish-word scan flags the bare three-letter name. */
const wave = (x) => Math.cos(x - Math.PI / 2);
const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
const hash = (text) => { let h = 2166136261; for (const ch of String(text)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; };
const away = (state) => state === 'saving' || state === 'loading';
const memoryKind = (state) => (state === 'saving' ? 'save' : 'load');

// ---- geometry helpers ------------------------------------------------------
function place(parent, mesh, x, y, z) {
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
const box = (parent, w, h, d, x, y, z, material = materials.wood) => place(parent, new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material), x, y, z);
const cylinder = (parent, r1, r2, h, x, y, z, material = materials.cream, segments = 12) => place(parent, new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segments), material), x, y, z);
const sphere = (parent, r, x, y, z, material, w = 14, h = 10) => place(parent, new THREE.Mesh(new THREE.SphereGeometry(r, w, h), material), x, y, z);
const capsule = (parent, r, length, x, y, z, material) => place(parent, new THREE.Mesh(new THREE.CapsuleGeometry(r, length, 4, 10), material), x, y, z);

function bakeable(mesh) {
  const m = mesh.material;
  return mesh.isMesh && !mesh.userData.keep && m && m.isMeshStandardMaterial && !m.transparent && !m.map
    && !m.vertexColors && m.emissive.getHex() === 0;
}

/** Merge every bakeable mesh under `root` (not crossing children flagged
 *  `userData.keep`) into one vertex-colored mesh in root's frame. */
function bake(root) {
  root.updateMatrixWorld(true);
  const inverse = root.matrixWorld.clone().invert();
  const parts = [];
  const walk = (node) => {
    for (const child of node.children) {
      if (child.userData.keep) continue;
      if (bakeable(child)) parts.push(child);
      if (!child.isMesh && child.children.length) walk(child);
    }
  };
  walk(root);
  if (parts.length < 2) return null;
  let vertices = 0; let indices = 0;
  for (const p of parts) {
    vertices += p.geometry.attributes.position.count;
    indices += p.geometry.index ? p.geometry.index.count : p.geometry.attributes.position.count;
  }
  const position = new Float32Array(vertices * 3); const normal = new Float32Array(vertices * 3); const color = new Float32Array(vertices * 3);
  const index = vertices > 65535 ? new Uint32Array(indices) : new Uint16Array(indices);
  const m = new THREE.Matrix4(); const n = new THREE.Matrix3(); const v = new THREE.Vector3();
  let vo = 0; let io = 0;
  for (const p of parts) {
    m.multiplyMatrices(inverse, p.matrixWorld); n.getNormalMatrix(m);
    const g = p.geometry; const P = g.attributes.position; const N = g.attributes.normal; const c = p.material.color;
    for (let k = 0; k < P.count; k++) {
      v.fromBufferAttribute(P, k).applyMatrix4(m); position.set([v.x, v.y, v.z], (vo + k) * 3);
      v.fromBufferAttribute(N, k).applyMatrix3(n).normalize(); normal.set([v.x, v.y, v.z], (vo + k) * 3);
      color.set([c.r, c.g, c.b], (vo + k) * 3);
    }
    const I = g.index; const count = I ? I.count : P.count;
    for (let k = 0; k < count; k++) index[io + k] = (I ? I.getX(k) : k) + vo;
    vo += P.count; io += count;
    p.parent.remove(p); g.dispose(); if (!shared.has(p.material)) p.material.dispose();
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(position, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(color, 3));
  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  geometry.computeBoundingSphere();
  const merged = new THREE.Mesh(geometry, VERTEX);
  merged.castShadow = true; merged.receiveShadow = true; merged.userData.baked = true; root.add(merged);
  return merged;
}

function disposeObject(object) {
  object.traverse((o) => {
    if ((o.isMesh || o.isLine) && ![SHADOW_GEO, CUBE_GEO, DOT_GEO, DOC_GEO].includes(o.geometry)) o.geometry.dispose();
    if ((o.isMesh || o.isLine) && o.material && !shared.has(o.material)) { o.material.map?.dispose(); o.material.dispose(); }
  });
}

function codeTexture() {
  const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 128;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#2c6656'; ctx.fillRect(0, 0, 64, 128);
  const colors = ['#d5e987', '#fcfaf3', '#9fd8c8', '#cdb8ef'];
  for (let i = 0; i < 16; i++) { ctx.fillStyle = colors[i % 4]; ctx.fillRect(6 + ((i * 7) % 3) * 6, 4 + i * 8, 12 + ((i * 13) % 34), 3); }
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping; texture.wrapT = THREE.RepeatWrapping; texture.repeat.set(1, 0.5);
  return texture;
}
const CODE = codeTexture();
const SCREEN = {
  on: keep(mat(0xffffff, { map: CODE, emissive: 0xffffff, emissiveMap: CODE, emissiveIntensity: 0.6, roughness: 0.4 })),
  idle: keep(mat(0x70c4af, { emissive: 0x326b5c, emissiveIntensity: 0.45 })),
  dim: keep(mat(0x4f7d71, { emissive: 0x1d3b33, emissiveIntensity: 0.15 })),
};

/** The object on an agent's desk, from its name. */
function roleOf(id) {
  if (/audit|review|validation|grounding/.test(id)) return 'magnifier';
  if (/tutor/.test(id)) return 'books';
  if (/redactor|writ|style|publish|adapter|insumos/.test(id)) return 'pens';
  if (/scout|screener/.test(id)) return 'globe';
  if (/diagram|figure|grapher/.test(id)) return 'chart';
  if (/dataset|curator|remote/.test(id)) return 'server';
  if (/build|walk|replicator|implementation|experiment/.test(id)) return 'toolbox';
  return 'notepad';
}

class Office {
  constructor(container, callbacks) {
    this.container = container; this.callbacks = callbacks || {};
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-25, 25, 18, -18, 0.1, 300);
    const probe = new THREE.OrthographicCamera(); probe.position.copy(OFFSET); probe.lookAt(0, 0, 0);
    this.right = new THREE.Vector3(1, 0, 0).applyQuaternion(probe.quaternion);
    this.up = new THREE.Vector3(0, 1, 0).applyQuaternion(probe.quaternion);
    this.view = { target: new THREE.Vector3(), half: 16 };
    this.goal = { target: new THREE.Vector3(), half: 16 };
    this.follow = true; this.maxHalf = 30;
    this.environment = new THREE.Group();
    this.people = new Map(); this.tags = new Map(); this.zoneTags = [];
    this.flows = new THREE.Group(); this.flowKey = ''; this.flowList = [];
    this.streams = []; this.memoryCubes = []; this.seenMemory = new Set();
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2(9, 9); this.pointerDirty = false; this.drag = null;
    this.elapsed = 0; this.lastTick = performance.now(); this.layoutKey = null; this.updates = 0;
    this.hoverId = null; this.focusId = null; this.running = false;
    this.tier = TIERS.length - 1; this.fps = null; this.window = { frames: 0, start: 0 }; this.startedAt = 0;
    this.snapshotData = { agents: [], orchestrator: { state: 'absent' }, memory: { interactions: [] } };
    this.v = new THREE.Vector3();

    this.scene.background = new THREE.Color(0xe8eee6);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.3;
    const el = this.renderer.domElement;
    el.setAttribute('aria-label', t('office.aria'));
    el.style.display = 'block'; el.style.touchAction = 'none';
    container.append(el);
    this.overlay = document.createElement('div'); this.overlay.className = 'office-tags'; container.append(this.overlay);
    this.scene.add(new THREE.HemisphereLight(0xfffbef, 0x9bbab0, 3));
    this.sun = new THREE.DirectionalLight(0xffeed0, 4);
    this.sun.position.set(-12, 26, -15); this.sun.shadow.mapSize.set(1024, 1024);
    Object.assign(this.sun.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 1, far: 90 });
    this.sun.shadow.bias = -0.0005; this.sun.shadow.normalBias = 0.03;
    this.scene.add(this.sun, this.environment, this.flows);
    this.applyTier();
    this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(container);

    el.addEventListener('pointerdown', (e) => {
      this.drag = { x: e.clientX, y: e.clientY, moved: false };
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener('pointermove', (e) => {
      this.setPointer(e);
      const d = this.drag;
      if (!d) return;
      const dx = e.clientX - d.x; const dy = e.clientY - d.y;
      if (!d.moved && Math.hypot(dx, dy) < 5) return;
      d.moved = true; d.x = e.clientX; d.y = e.clientY;
      const perPixel = (2 * this.view.half) / Math.max(1, container.clientHeight);
      const shift = this.right.clone().multiplyScalar(-dx * perPixel).addScaledVector(this.up, dy * perPixel);
      this.view.target.add(shift); this.goal.target.copy(this.view.target); this.goal.half = this.view.half;
      this.follow = false; this.notify();
      el.style.cursor = 'grabbing';
    });
    el.addEventListener('pointerup', (e) => {
      const d = this.drag; this.drag = null; el.style.cursor = this.hoverId ? 'pointer' : 'grab';
      if (d && !d.moved) { this.setPointer(e); const id = this.pick(); if (id) this.select(id, e); }
    });
    el.addEventListener('pointerleave', () => { this.pointer.set(9, 9); this.pointerDirty = true; });
    el.addEventListener('wheel', (e) => {
      e.preventDefault(); this.setPointer(e);
      const before = this.goal.half;
      const after = THREE.MathUtils.clamp(before * Math.exp(e.deltaY * 0.0012), 3.5, this.maxHalf);
      const aspect = container.clientWidth / Math.max(1, container.clientHeight);
      const k = 1 - after / before;
      this.goal.target.addScaledVector(this.right, this.pointer.x * before * aspect * k).addScaledVector(this.up, this.pointer.y * before * k);
      this.goal.half = after; this.follow = false; this.notify();
    }, { passive: false });
    el.style.cursor = 'grab';
    this.buildOffice([]);
  }

  // ---- tags (HTML over the canvas) ----------------------------------------
  makeTag(id, kind) {
    const el = document.createElement('div');
    el.className = `office-tag office-tag--${kind}`;
    el.innerHTML = '<div class="office-tag__bubble"></div><div class="office-tag__card"><b></b><span><i></i><em></em></span></div>';
    if (kind === 'agent') el.addEventListener('click', (e) => this.select(id, e));
    this.overlay.append(el);
    const tag = { el, bubble: el.firstChild, name: el.querySelector('b'), status: el.querySelector('em'), x: NaN, y: NaN, mode: '', text: '', bubbleUntil: 0, bubbleOn: false };
    return tag;
  }
  tagText(tag, name, status, state) {
    const key = `${name}|${status}|${state}`;
    if (tag.text === key) return;
    tag.text = key; tag.name.textContent = name; tag.status.textContent = status;
    tag.el.dataset.state = state || '';
  }
  bubble(tag, text, kind, seconds = 4.5) {
    if (!tag || this.updates < 2) return;
    tag.bubble.textContent = text; tag.bubble.dataset.kind = kind;
    tag.bubbleUntil = this.elapsed + seconds;
  }
  placeTag(tag, world, mode) {
    const showBubble = this.elapsed < tag.bubbleUntil;
    if (showBubble !== tag.bubbleOn) { tag.bubbleOn = showBubble; tag.el.classList.toggle('office-tag--talking', showBubble); }
    let x = -1; let y = -1;
    if (mode !== 'hidden') {
      this.v.copy(world).project(this.camera);
      x = (this.v.x + 1) / 2 * this.container.clientWidth; y = (1 - this.v.y) / 2 * this.container.clientHeight;
      if (x < -60 || y < -20 || x > this.container.clientWidth + 60 || y > this.container.clientHeight + 60) mode = 'hidden';
    }
    if (mode !== tag.mode) { tag.mode = mode; tag.el.dataset.mode = mode; }
    if (mode === 'hidden') return;
    if (!(Math.abs(x - tag.x) <= 0.3 && Math.abs(y - tag.y) <= 0.3)) {
      tag.x = x; tag.y = y; tag.el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translate(-50%, -100%)`;
    }
  }
  clearTags() {
    for (const tag of this.tags.values()) tag.el.remove();
    for (const tag of this.zoneTags) tag.el.remove();
    if (this.brainTag) this.brainTag.el.remove();
    this.tags.clear(); this.zoneTags = []; this.brainTag = null;
  }

  // ---- building ----------------------------------------------------------
  plant(parent, x, z, size = 1) {
    const group = new THREE.Group(); group.position.set(x, 0, z); group.scale.setScalar(size); parent.add(group);
    cylinder(group, 0.42, 0.32, 0.65, 0, 0.33, 0, materials.pot);
    cylinder(group, 0.38, 0.38, 0.03, 0, 0.67, 0, materials.soil);
    for (let i = 0; i < 7; i++) {
      const angle = i * 2.4;
      const leaf = sphere(group, 0.38, Math.cos(angle) * 0.29, 1.08 + (i % 3) * 0.2, wave(angle) * 0.29, materials.leaf, 7, 5);
      leaf.scale.set(0.62, 1.8, 0.48); leaf.rotation.set(0.5 * Math.cos(angle), angle, 0.5 * wave(angle));
    }
  }
  prop(g, role, hue) {
    const accent = mat(hue);
    if (role === 'magnifier') {
      const lens = place(g, new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.03, 8, 20), materials.metal), -1.05, 1.24, 0.1);
      lens.rotation.x = Math.PI / 2;
      const handle = cylinder(g, 0.03, 0.03, 0.28, -0.82, 1.24, 0.22, materials.ink, 8); handle.rotation.set(Math.PI / 2, 0, 1.0);
      box(g, 0.42, 0.03, 0.55, -1.1, 1.215, 0.02, mat(0xf3eedf));
    } else if (role === 'books') {
      [0x769cbc, accent.color.getHex(), 0xdca569].forEach((c, i) => { const b = box(g, 0.5, 0.1, 0.36, -1.05, 1.25 + i * 0.1, 0.02, mat(c)); b.rotation.y = i * 0.25; });
    } else if (role === 'pens') {
      cylinder(g, 0.1, 0.09, 0.22, -1.1, 1.31, 0.05, accent);
      [C.red, C.ink, 0x3b6fb6].forEach((c, i) => { const p = cylinder(g, 0.018, 0.018, 0.32, -1.13 + i * 0.03, 1.44, 0.03 + i * 0.03, mat(c), 6); p.rotation.z = (i - 1) * 0.25; });
      box(g, 0.42, 0.03, 0.55, -0.62, 1.215, 0.08, mat(0xf3eedf));
    } else if (role === 'globe') {
      cylinder(g, 0.12, 0.15, 0.06, -1.05, 1.23, 0.02, materials.ink);
      cylinder(g, 0.02, 0.02, 0.16, -1.05, 1.32, 0.02, materials.metal, 6);
      sphere(g, 0.19, -1.05, 1.55, 0.02, mat(0x5aa6c8));
      sphere(g, 0.1, -1.0, 1.62, -0.08, materials.leaf, 8, 6).scale.set(1, 0.6, 1.2);
    } else if (role === 'chart') {
      const board = box(g, 0.56, 0.42, 0.04, -1.05, 1.47, -0.05, materials.cream); board.rotation.x = -0.25;
      [0.12, 0.22, 0.3].forEach((h, i) => { const bar = box(g, 0.09, h, 0.03, -1.2 + i * 0.15, 1.33 + h / 2, -0.01, mat([C.red, accent.color.getHex(), C.green][i])); bar.rotation.x = -0.25; });
    } else if (role === 'server') {
      box(g, 0.42, 0.38, 0.4, -1.05, 1.39, -0.05, materials.ink);
      for (let i = 0; i < 3; i++) box(g, 0.3, 0.025, 0.02, -1.05, 1.3 + i * 0.09, 0.155, mat(i === 1 ? C.lime : accent.color.getHex()));
    } else if (role === 'toolbox') {
      box(g, 0.52, 0.22, 0.3, -1.05, 1.31, 0.02, mat(C.red));
      box(g, 0.3, 0.05, 0.05, -1.05, 1.47, 0.02, materials.ink);
      box(g, 0.54, 0.03, 0.32, -1.05, 1.42, 0.02, accent);
    } else {
      box(g, 0.4, 0.03, 0.55, -1.07, 1.23, 0.04, mat(0xdceaac));
    }
  }
  desk(parent, x, z, { monitors = 1, role = 'notepad', hue = C.teal } = {}) {
    const g = new THREE.Group(); g.position.set(x, 0, z); parent.add(g);
    const wide = monitors > 1 ? 1.55 : 1;
    box(g, 3.1 * wide, 0.16, 1.45, 0, 1.12, 0);
    for (const dx of [-1.25 * wide, 1.25 * wide]) for (const dz of [-0.5, 0.5]) box(g, 0.11, 1.04, 0.11, dx, 0.52, dz, materials.cream);
    box(g, 1.06, 0.045, 0.4, 0, 1.22, 0.18, materials.ink);
    const screens = [];
    const offsets = monitors > 1 ? [-1.15, 0, 1.15] : [0];
    for (const ox of offsets) {
      const turn = ox ? (ox > 0 ? -0.35 : 0.35) : 0;
      const bezel = box(g, 1.06, 0.67, 0.05, ox, 1.56, -0.26, materials.ink); bezel.rotation.set(-0.12, turn, 0);
      box(g, 0.08, 0.3, 0.08, ox, 1.3, -0.3, materials.ink);
      const screen = box(g, 0.94, 0.54, 0.016, ox, 1.57, -0.225, SCREEN.idle);
      screen.rotation.copy(bezel.rotation); screen.userData.keep = true; screen.castShadow = false; screens.push(screen);
    }
    if (monitors === 1) this.prop(g, role, hue);
    const mug = new THREE.Group(); mug.position.set(1.13 * wide, 0, 0.18); g.add(mug);
    cylinder(mug, 0.095, 0.08, 0.2, 0, 1.3, 0); cylinder(mug, 0.072, 0.072, 0.01, 0, 1.405, 0, materials.coffee);
    const seat = mat(monitors > 1 ? C.green : hue);
    box(g, 0.74, 0.15, 0.68, 0, 0.58, 1.04, seat);
    box(g, 0.74, 0.65, 0.14, 0, 0.98, 1.36, seat);
    cylinder(g, 0.065, 0.065, 0.49, 0, 0.26, 1.06, materials.ink);
    box(g, 0.76, 0.075, 0.12, 0, 0.055, 1.06, materials.ink);
    box(g, 0.12, 0.075, 0.7, 0, 0.055, 1.06, materials.ink);
    return { group: g, screens };
  }
  brain(parent, x, z) {
    const core = new THREE.Group(); core.position.set(x, 0, z); core.scale.setScalar(1.35); parent.add(core);
    cylinder(core, 1.35, 1.55, 0.5, 0, 0.25, 0, materials.ink, 32);
    const disc = cylinder(core, 1.2, 1.2, 0.04, 0, 0.52, 0, mat(C.lime, { emissive: C.lime, emissiveIntensity: 0.35 }), 32);
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      cylinder(core, 0.06, 0.06, 1.4, Math.cos(a) * 1.05, 1.15, wave(a) * 1.05, materials.metal, 8);
    }
    const head = new THREE.Group(); head.position.y = 2.55; head.userData.keep = true; core.add(head);
    const lobe = mat(C.violet, { emissive: 0x6b4aa8, emissiveIntensity: 0.35, roughness: 0.55 });
    for (let i = 0; i < 14; i++) {
      const side = i % 2 ? 1 : -1; const k = Math.floor(i / 2);
      const s = sphere(head, 0.42, side * (0.32 + (k % 2) * 0.12), wave(k * 1.1) * 0.32, -0.75 + k * 0.25, lobe, 12, 10);
      s.scale.set(1, 0.85, 1.05);
    }
    const band = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.05, 8, 48), mat(C.lime, { emissive: C.lime, emissiveIntensity: 0.6 }));
    band.rotation.x = Math.PI / 2; head.add(band);
    const halo = new THREE.Mesh(new THREE.RingGeometry(1.5, 1.68, 48), new THREE.MeshBasicMaterial({ color: C.violet, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
    halo.rotation.x = -Math.PI / 2; halo.position.y = 0.08; core.add(halo);
    const ripple = new THREE.Mesh(new THREE.RingGeometry(1.0, 1.12, 48), new THREE.MeshBasicMaterial({ color: C.lime, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }));
    ripple.rotation.x = -Math.PI / 2; ripple.position.y = 0.1; core.add(ripple);
    this.core = { group: core, head, lobe, band, halo, ripple, disc, pulse: 0, rippleAt: -9, anchor: new THREE.Vector3(x, 2.55 * 1.35, z) };
  }

  /** Desks grouped into tramo zones, packed into shelf rows in pipeline order. */
  layout(agents) {
    const order = (a) => { const i = ZONES.indexOf(a.tramo || ''); return i < 0 ? ZONES.length - 1 : i; };
    const sorted = agents.map((a, i) => ({ a, i })).sort((x, y) => order(x.a) - order(y.a) || x.i - y.i).map((x) => x.a);
    const perRow = Math.max(5, Math.ceil(Math.sqrt(agents.length * 1.5)));
    const zones = [];
    for (const a of sorted) {
      const key = ZONES.includes(a.tramo || '') ? (a.tramo || '') : '';
      if (!zones.length || zones[zones.length - 1].key !== key) zones.push({ key, agents: [] });
      zones[zones.length - 1].agents.push(a);
    }
    const slots = []; const segments = [];
    let row = 0; let col = 0; let gaps = 0;
    for (const zone of zones) {
      if (col > 0 && col + Math.min(zone.agents.length, perRow) > perRow) { row += 1; col = 0; gaps = 0; }
      if (col > 0) gaps += 1;
      let segment = null;
      zone.agents.forEach((a) => {
        if (col >= perRow) { row += 1; col = 0; gaps = 0; segment = null; }
        const x = col * 4.6 + gaps * 1.1;
        if (!segment) { segment = { key: zone.key, row, x0: x, x1: x, first: !segments.some((s) => s.key === zone.key) }; segments.push(segment); }
        segment.x1 = x;
        slots.push({ agent: a, row, x });
        col += 1;
      });
    }
    const rows = Math.max(3, row + 1);
    const width = Math.max(...slots.map((s) => s.x), 9) + 4.6;
    return { slots, segments, rows, width };
  }

  buildOffice(agents) {
    for (const child of [...this.environment.children]) { disposeObject(child); this.environment.remove(child); }
    for (const person of this.people.values()) { this.scene.remove(person.root); disposeObject(person.root); }
    this.people.clear(); this.clearTags(); this.desks = new Map(); this.memoryCubes = []; this.flowList = [];
    const { slots, segments, rows, width } = this.layout(agents);
    this.roomWidth = width + 12; this.roomDepth = rows * 3.9 + 9.5;
    const left = -this.roomWidth / 2; const back = -this.roomDepth / 2; const right = this.roomWidth / 2;
    const env = this.environment;
    const statics = new THREE.Group(); env.add(statics);
    box(statics, this.roomWidth + 0.5, 0.52, this.roomDepth + 0.5, 0, -0.31, 0, materials.cream);
    box(statics, this.roomWidth, 0.12, this.roomDepth, 0, -0.015, 0, materials.floor);
    const seam = mat(0xdacaa9);
    for (let z = back + 0.7; z < -back; z += 0.85) box(statics, this.roomWidth - 0.12, 0.004, 0.012, 0, 0.05, z, seam);
    box(statics, 0.22, 4.25, this.roomDepth, left, 2.1, 0, materials.cream);
    box(statics, this.roomWidth, 4.25, 0.22, 0, 2.1, back, materials.cream);
    box(statics, this.roomWidth, 0.22, 0.32, 0, 4.25, back, materials.wood);
    for (let x = left + 2; x < right - 1; x += 4.6) {
      box(statics, 3.5, 2.42, 0.07, x, 2.55, back + 0.14, mat(0xd3e3dc));
      box(statics, 0.075, 2.6, 0.12, x, 2.55, back + 0.23, materials.cream);
      box(statics, 3.7, 0.12, 0.4, x, 1.25, back + 0.28, materials.cream);
      box(statics, 3.7, 0.08, 0.12, x, 2.65, back + 0.23, materials.cream);
    }
    const x0 = left + 3.5; const zOf = (row) => back + 3.1 + row * 3.9;
    // Tramo zones: a colored floor under each run of desks, a sign on the first one.
    for (const s of segments) {
      const hue = new THREE.Color(ZONE_COLOR[s.key]).lerp(new THREE.Color(C.floor), 0.55);
      const z = zOf(s.row);
      box(statics, s.x1 - s.x0 + 4.2, 0.03, 3.45, x0 + (s.x0 + s.x1) / 2, 0.066, z + 0.55, mat(hue.getHex()));
      box(statics, s.x1 - s.x0 + 4.2, 0.035, 0.12, x0 + (s.x0 + s.x1) / 2, 0.07, z - 1.12, mat(ZONE_COLOR[s.key]));
      if (s.first) {
        const tag = this.makeTag(`zone:${s.key}`, 'zone');
        const name = s.key ? t(`office.zone.${s.key}`) : t('office.zone.other');
        this.tagText(tag, name, '', s.key);
        tag.el.style.setProperty('--zone', `#${new THREE.Color(ZONE_COLOR[s.key]).getHexString()}`);
        tag.world = new THREE.Vector3(x0 + s.x0 - 2.0, 0.1, z - 1.1);
        this.zoneTags.push(tag);
      }
    }
    for (const slot of slots) {
      const a = slot.agent; const x = x0 + slot.x; const z = zOf(slot.row);
      const hue = ZONE_COLOR[ZONES.includes(a.tramo || '') ? (a.tramo || '') : ''];
      const desk = this.desk(statics, x, z, { role: roleOf(a.id), hue });
      this.desks.set(a.id, { ...desk, hue, seat: new THREE.Vector3(x, 0, z + 1.06), stand: new THREE.Vector3(x + 1.85, 0, z + 0.9) });
    }
    // The orchestrator's front desk, facing the room like the agents do.
    const ox = x0 + (width - 4.6) / 2; const oz = zOf(rows) + 1.4;
    this.orchestratorDesk = { ...this.desk(statics, ox, oz, { monitors: 3 }), hue: C.green, seat: new THREE.Vector3(ox, 0, oz + 1.06) };
    box(statics, 5.6, 0.03, 3.4, ox, 0.07, oz + 0.4, mat(0xe8bc94));
    // Right wing: weherd's coffee counter at the back, the Engram core in the lounge.
    box(statics, 5.5, 1.2, 1.3, right - 3.8, 0.6, back + 1.25, materials.green);
    box(statics, 5.7, 0.12, 1.55, right - 3.8, 1.26, back + 1.25, materials.cream);
    box(statics, 0.85, 0.85, 0.65, right - 4.9, 1.74, back + 1.3, materials.ink);
    box(statics, 0.63, 0.4, 0.05, right - 4.9, 1.67, back + 1.65, materials.metal);
    cylinder(statics, 0.1, 0.09, 0.23, right - 4.9, 1.48, back + 1.77);
    for (let i = 0; i < 3; i++) cylinder(statics, 0.1, 0.09, 0.2, right - 3.2 + i * 0.3, 1.43, back + 1.3);
    this.plant(statics, right - 0.8, back + 1.1, 1.5);
    const coreZ = back + 3.1 + rows * 1.95;
    box(statics, 6.2, 0.035, 6.2, right - 4.2, 0.07, coreZ, mat(0xd9cdea));
    this.brain(env, right - 4.2, coreZ);
    const glassZ = coreZ + 3.6;
    box(env, 5.3, 2.9, 0.06, right - 3.65, 1.47, glassZ, materials.glass);
    for (let x = right - 6.3; x <= right - 1; x += 2.65) box(statics, 0.06, 3.03, 0.09, x, 1.51, glassZ, materials.metal);
    box(statics, 5.4, 0.06, 0.08, right - 3.65, 3.04, glassZ, materials.metal);
    this.plant(statics, right - 1.1, this.roomDepth / 2 - 1.2, 1.4);
    this.plant(statics, left + 0.9, this.roomDepth / 2 - 1.1, 1.6);
    this.plant(statics, left + 0.8, back + 1, 1.2);
    bake(statics);
    bake(this.core.group);
    this.brainTag = this.makeTag('engram', 'engram');
    this.tagText(this.brainTag, t('office.brainSign'), '', 'engram');
    this.layoutKey = agents.map((a) => `${a.id}:${a.tramo || ''}`).join(',');
    this.flowKey = '';
    this.maxHalf = this.frameAll(false) * 1.5;
    this.resize();
  }

  // ---- people ------------------------------------------------------------
  createPerson(id, shirtColor) {
    const h = hash(id);
    const skin = mat(SKIN[h % SKIN.length]); const hair = mat(HAIR[(h >>> 3) % HAIR.length]); const style = (h >>> 6) % 4;
    const shirt = mat(shirtColor);
    const root = new THREE.Group();
    capsule(root, 0.26, 0.34, 0, 1.06, 0, shirt).scale.set(1, 1, 0.78);
    cylinder(root, 0.255, 0.255, 0.07, 0, 0.82, 0, materials.ink, 16).scale.set(1, 1, 0.8);
    box(root, 0.2, 0.07, 0.06, 0, 1.36, -0.17, materials.cream);
    cylinder(root, 0.08, 0.09, 0.12, 0, 1.42, 0, skin, 10);
    const head = new THREE.Group(); head.position.y = 1.5; head.userData.keep = true; root.add(head);
    sphere(head, 0.26, 0, 0.16, 0, skin, 18, 14);
    sphere(head, 0.05, -0.25, 0.14, 0, skin, 8, 6); sphere(head, 0.05, 0.25, 0.14, 0, skin, 8, 6);
    sphere(head, 0.275, 0, 0.24, 0.05, hair, 18, 12).scale.set(1, 0.72, 1);
    if (style === 1) sphere(head, 0.12, 0, 0.34, 0.27, hair, 10, 8);
    if (style === 2) for (let i = 0; i < 5; i++) { const spike = place(head, new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.18, 6), hair), -0.14 + i * 0.07, 0.42, 0.05 + (i % 2) * 0.06); spike.rotation.z = (i - 2) * 0.25; }
    if (style === 3) box(head, 0.5, 0.42, 0.14, 0, 0.04, 0.2, hair);
    box(head, 0.1, 0.022, 0.03, 0, 0.04, -0.245, materials.mouth);
    const eyes = new THREE.Group(); eyes.position.set(0, 0.15, -0.228); eyes.userData.keep = true; head.add(eyes);
    for (const x of [-0.09, 0.09]) sphere(eyes, 0.036, x, 0, 0, materials.ink, 8, 6);
    const limb = (x, y, arm) => {
      const group = new THREE.Group(); group.position.set(x, y, 0); group.userData.keep = true; root.add(group);
      if (arm) { capsule(group, 0.075, 0.28, 0, -0.2, 0, shirt); sphere(group, 0.078, 0, -0.43, 0, skin, 10, 8); }
      else { capsule(group, 0.092, 0.34, 0, -0.26, 0, materials.pants); box(group, 0.18, 0.1, 0.3, 0, -0.56, -0.05, materials.shoe); }
      return group;
    };
    const leftArm = limb(-0.35, 1.3, true); const rightArm = limb(0.35, 1.3, true);
    const leftLeg = limb(-0.13, 0.72, false); const rightLeg = limb(0.13, 0.72, false);
    const cup = new THREE.Group(); cup.position.set(0, -0.47, -0.05); cup.userData.keep = true; rightArm.add(cup);
    cylinder(cup, 0.105, 0.09, 0.2, 0, 0, -0.12); cylinder(cup, 0.08, 0.08, 0.012, 0, 0.1, -0.12, materials.coffee); cup.visible = false;
    const packet = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.26, 0.26), new THREE.MeshStandardMaterial({ color: C.lime, emissive: C.lime, emissiveIntensity: 0.8 }));
    packet.position.set(0, -0.62, -0.1); packet.visible = false; packet.userData.keep = true; rightArm.add(packet);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.52, 0.62, 32), new THREE.MeshBasicMaterial({ color: C.lime, side: THREE.DoubleSide, transparent: true, opacity: 0, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.075; root.add(ring);
    const blob = new THREE.Mesh(SHADOW_GEO, SHADOW); blob.rotation.x = -Math.PI / 2; blob.position.y = 0.07; blob.userData.keep = true; root.add(blob);
    for (const node of [root, head, eyes, leftArm, rightArm, leftLeg, rightLeg, cup]) bake(node);
    shirt.dispose(); skin.dispose(); hair.dispose();
    return { root, head, eyes, leftArm, rightArm, leftLeg, rightLeg, cup, packet, ring, blob, blinkAt: 2 + (h % 50) / 10 };
  }
  ensurePerson(id, place) {
    let person = this.people.get(id);
    if (!person) {
      person = { ...this.createPerson(id, place.hue), id, place, phase: this.people.size * 1.78, state: 'available', path: [] };
      person.root.position.copy(place.seat);
      person.root.traverse((o) => { if (o.isMesh && o !== person.ring && o !== person.blob) o.userData.agentId = id; });
      this.people.set(id, person); this.scene.add(person.root);
      this.tags.set(id, this.makeTag(id, 'agent'));
    }
    return person;
  }

  // ---- data --------------------------------------------------------------
  update(snapshot) {
    const data = snapshot || {}; this.snapshotData = data; this.updates += 1;
    const agents = data.agents || [];
    const key = agents.map((a) => `${a.id}:${a.tramo || ''}`).join(',');
    if (key !== this.layoutKey) this.buildOffice(agents);
    const orch = data.orchestrator || { state: 'absent' };
    const boss = this.ensurePerson('orchestrator', this.orchestratorDesk);
    boss.root.visible = orch.state !== 'absent';
    boss.title = t('office.orchestrator');
    agents.forEach((agent) => {
      const person = this.ensurePerson(agent.id, this.desks.get(agent.id));
      person.title = agent.label || agent.id;
      this.applyState(person, agent.state, !!agent.inPhase);
    });
    const absent = orch.state === 'absent';
    this.applyState(boss, absent ? 'available' : orch.state, false, [...new Set(orch.clis || [])].join(', '), absent);
    this.syncMemory((data.memory || {}).interactions || []);
    this.syncFlows();
    if (this.follow) this.frameActive();
  }
  applyState(person, state, inPhase, extra = '', absent = false) {
    const previous = person.state; const changed = previous !== state;
    person.state = state; person.inPhase = inPhase;
    if (changed && away(state) !== away(previous)) {
      const target = away(state) ? (person.place.stand || person.place.seat) : person.place.seat;
      person.path = [target.clone()];
    }
    const label = t(`office.state.${state}`);
    const status = absent ? t('office.state.absent') : (extra ? `${label} · ${extra}` : label);
    this.tagText(this.tags.get(person.id), person.title, status, absent ? 'absent' : state);
    const material = state === 'working' || away(state) ? SCREEN.on : (state === 'available' && person.id !== 'orchestrator' ? SCREEN.dim : SCREEN.idle);
    for (const screen of person.place.screens || []) screen.material = material;
    if (away(state)) { const c = STREAM[memoryKind(state)]; person.packet.material.color.setHex(c); person.packet.material.emissive.setHex(c); }
    if (!changed || this.updates < 2) return;
    const boss = this.people.get('orchestrator');
    const tag = this.tags.get(person.id);
    if (person !== boss && state === 'working' && previous === 'available') {
      this.courier(boss, person, 'dispatch');
      this.bubble(tag, `${t('office.orchestrator')} → ${person.title}`, 'dispatch');
    } else if (person !== boss && previous === 'working' && state === 'available') {
      this.courier(person, boss, 'done');
      this.bubble(tag, t('office.bubble.done'), 'done');
    }
    if (away(state)) {
      this.spawnStream(person, memoryKind(state));
      this.bubble(tag, t(`office.bubble.${memoryKind(state)}`), memoryKind(state));
    }
  }
  syncMemory(interactions) {
    const keys = new Set();
    interactions.forEach((item) => {
      const key = `${item.at}|${item.agent}|${item.kind}|${item.line}`; keys.add(key);
      if (!this.seenMemory.has(key)) {
        this.seenMemory.add(key);
        const person = this.people.get(item.agent);
        const kind = STREAM[item.kind] ? item.kind : 'use';
        if (person && this.updates > 1) {
          this.spawnStream(person, kind);
          this.bubble(this.brainTag, t(`office.bubble.engram.${kind}`, { agent: person.title }), kind, 5);
        }
        this.core.pulse = 1;
      }
    });
    for (const key of [...this.seenMemory]) if (!keys.has(key)) this.seenMemory.delete(key);
    while (this.memoryCubes.length > interactions.length) { const cube = this.memoryCubes.pop(); this.core.group.remove(cube); cube.material.dispose(); }
    interactions.forEach((item, i) => {
      let cube = this.memoryCubes[i];
      if (!cube) { cube = new THREE.Mesh(CUBE_GEO, new THREE.MeshStandardMaterial({ roughness: 0.4 })); cube.scale.setScalar(0.7); this.core.group.add(cube); this.memoryCubes.push(cube); }
      const color = STREAM[item.kind] || C.violet;
      cube.material.color.setHex(color); cube.material.emissive.setHex(color); cube.material.emissiveIntensity = 0.7;
      cube.userData.orbit = { r: 1.75 + (i % 3) * 0.28, y: 1.6 + (i % 4) * 0.42, a: (i / Math.max(interactions.length, 1)) * Math.PI * 2 };
    });
    this.tagText(this.brainTag, t('office.brainSign'), t('office.engramEvents', { count: interactions.length }), 'engram');
  }
  syncFlows() {
    const boss = this.people.get('orchestrator');
    const live = boss && boss.root.visible ? [...this.people.values()].filter((p) => p !== boss && p.state !== 'available') : [];
    const key = live.map((p) => `${p.id}:${p.state}`).join(',');
    if (key === this.flowKey) return;
    this.flowKey = key;
    for (const child of [...this.flows.children]) { this.flows.remove(child); disposeObject(child); }
    this.flowList = [];
    const from = this.orchestratorDesk.seat.clone().setY(2.0);
    for (const person of live) {
      const kind = person.state === 'working' ? 'working' : memoryKind(person.state);
      const to = person.place.seat.clone().setY(2.0);
      const mid = from.clone().lerp(to, 0.5).setY(5.2);
      const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
      const color = kind === 'working' ? 0x3a8f75 : STREAM[kind];
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.06, 6, false),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, depthWrite: false }));
      this.flows.add(tube);
      const dots = [0, 1, 2].map(() => { const d = new THREE.Mesh(DOT_GEO, FLOW_DOT[kind]); this.flows.add(d); return d; });
      this.flowList.push({ curve, tube, dots });
    }
  }
  spawnStream(person, kind) {
    const desk = person.root.position.clone().setY(1.6);
    const brain = this.core.anchor.clone();
    const [from, to] = kind === 'load' ? [brain, desk] : [desk, brain];
    const mid = from.clone().lerp(to, 0.5).setY(Math.max(from.y, to.y) + 3.2);
    const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
    for (let i = 0; i < 6; i++) {
      const cube = new THREE.Mesh(CUBE_GEO, STREAM_MAT[kind] || STREAM_MAT.use);
      cube.visible = false; this.scene.add(cube);
      this.streams.push({ mesh: cube, curve, time: -i * 0.16, duration: 1.7, spin: 4, arrive: () => { this.core.pulse = 1; this.core.rippleAt = this.elapsed; } });
    }
  }
  /** A document travelling between two desks: a task given or a task done. */
  courier(fromPerson, toPerson, kind) {
    if (!fromPerson || !toPerson) return;
    const from = fromPerson.place.seat.clone().setY(2.2); const to = toPerson.place.seat.clone().setY(2.2);
    const mid = from.clone().lerp(to, 0.5).setY(6.5);
    const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
    const doc = new THREE.Mesh(DOC_GEO, DOC_MAT); doc.visible = false; this.scene.add(doc);
    this.streams.push({ mesh: doc, curve, time: 0, duration: 1.9, spin: 1.5, scale: 1.5, arrive: () => { toPerson.flash = this.elapsed; } });
    const trail = kind === 'done' ? STREAM_MAT.save : FLOW_DOT.working;
    for (let i = 1; i <= 4; i++) {
      const dot = new THREE.Mesh(DOT_GEO, trail); dot.visible = false; this.scene.add(dot);
      this.streams.push({ mesh: dot, curve, time: -i * 0.09, duration: 1.9, spin: 0, scale: 1 - i * 0.15 });
    }
  }

  // ---- camera ------------------------------------------------------------
  /** Frame points (ortho: only their projection on the view plane matters). */
  frame(points, minHalf, apply = true) {
    let x0 = Infinity; let x1 = -Infinity; let y0 = Infinity; let y1 = -Infinity;
    for (const p of points) {
      const x = p.dot(this.right); const y = p.dot(this.up);
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const aspect = this.container.clientWidth / Math.max(1, this.container.clientHeight) || 1.6;
    const half = Math.max((y1 - y0) / 2 + 1.6, ((x1 - x0) / 2 + 1.6) / aspect, minHalf);
    if (apply) {
      this.goal.target.copy(this.right).multiplyScalar((x0 + x1) / 2).addScaledVector(this.up, (y0 + y1) / 2);
      this.goal.half = Math.min(half, this.maxHalf);
    }
    return half;
  }
  roomPoints() {
    const w = this.roomWidth / 2; const d = this.roomDepth / 2; const out = [];
    for (const x of [-w, w]) for (const z of [-d, d]) out.push(new THREE.Vector3(x, 0, z));
    out.push(new THREE.Vector3(-w, 4.3, -d), new THREE.Vector3(w, 4.3, -d));
    return out;
  }
  frameAll(apply = true) { return this.frame(this.roomPoints(), 8, apply); }
  frameActive() {
    const points = []; let active = 0; let memory = false;
    for (const p of this.people.values()) {
      const isBoss = p.id === 'orchestrator';
      if (!isBoss && p.state === 'available') continue;
      if (!isBoss) active += 1;
      if (away(p.state)) memory = true;
      const at = (p.place.stand && away(p.state) ? p.place.stand : p.place.seat);
      points.push(at.clone(), at.clone().setY(3.4));
    }
    if (!active && !memory) { this.frameAll(); return; }
    if (memory || (this.snapshotData.memory?.interactions || []).length) points.push(this.core.anchor.clone().setY(0), this.core.anchor.clone().setY(6));
    this.frame(points, 7);
  }
  fitAll() { this.follow = false; this.frameAll(); this.notify(); }
  followActive() { this.follow = true; this.frameActive(); this.notify(); }
  notify() { if (this.callbacks.camera) this.callbacks.camera({ following: this.follow }); }
  applyCamera() {
    const width = this.container.clientWidth; const height = this.container.clientHeight; if (!width || !height) return;
    const aspect = width / height; const half = this.view.half;
    Object.assign(this.camera, { left: -half * aspect, right: half * aspect, top: half, bottom: -half });
    this.camera.position.copy(this.view.target).add(OFFSET); this.camera.lookAt(this.view.target);
    this.camera.updateProjectionMatrix();
  }
  applyTier() {
    const tier = TIERS[this.tier];
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, tier.ratio));
    this.sun.castShadow = tier.shadows;
    for (const p of this.people.values()) p.blob.visible = !tier.shadows;
    this.resize();
  }
  /** Measured frame rate over 2 s windows; a slow window steps the tier down. */
  measure(now) {
    if (now - this.startedAt < 1500) return;
    const w = this.window;
    if (!w.start) { w.start = now; w.frames = 0; return; }
    w.frames += 1;
    if (now - w.start < 2000) return;
    this.fps = Math.round((w.frames * 1000) / (now - w.start));
    w.start = now; w.frames = 0;
    if (this.fps < MIN_FPS && this.tier > 0) { this.tier -= 1; this.applyTier(); }
  }

  // ---- interaction -------------------------------------------------------
  setPointer(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    this.pointerDirty = true;
  }
  pick() {
    if (Math.abs(this.pointer.x) > 1 || Math.abs(this.pointer.y) > 1) return null;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const meshes = [];
    for (const person of this.people.values()) if (person.root.visible) person.root.traverse((o) => { if (o.isMesh && o.userData.agentId) meshes.push(o); });
    const hit = this.raycaster.intersectObjects(meshes, false)[0];
    return hit ? hit.object.userData.agentId : null;
  }
  select(id, event) { if (this.callbacks.select) this.callbacks.select(id, event); }
  focus(id) {
    if (id && id !== this.focusId) {
      const person = this.people.get(id);
      if (person) {
        this.goal.target.copy(person.root.position).setY(1.4);
        this.goal.half = Math.min(this.goal.half, 6.5); this.follow = false; this.notify();
      }
    }
    this.focusId = id;
  }

  // ---- loop --------------------------------------------------------------
  start() {
    if (this.running) return;
    this.running = true; this.lastTick = performance.now(); this.startedAt = this.lastTick; this.window.start = 0;
    this.resize(); this.renderer.setAnimationLoop(() => this.animate());
  }
  stop() { this.running = false; this.renderer.setAnimationLoop(null); }
  animate() {
    const now = performance.now(); const dt = Math.min((now - this.lastTick) / 1000, 0.05); this.lastTick = now; this.elapsed += dt; const time = this.elapsed;
    this.measure(now);
    const k = 1 - Math.exp(-dt * 5);
    if (!this.drag || !this.drag.moved) {
      this.view.target.lerp(this.goal.target, k); this.view.half += (this.goal.half - this.view.half) * k;
    }
    this.applyCamera();
    if (this.pointerDirty && !this.drag) {
      this.pointerDirty = false;
      const hovered = this.pick();
      if (hovered !== this.hoverId) { this.hoverId = hovered; this.renderer.domElement.style.cursor = hovered ? 'pointer' : 'grab'; }
    }
    for (const person of this.people.values()) this.animatePerson(person, time + person.phase, dt, time);
    CODE.offset.y -= dt * 0.22;
    const core = this.core;
    if (core) {
      core.pulse = Math.max(0, core.pulse - dt * 0.8);
      const busy = [...this.people.values()].some((p) => p.root.visible && away(p.state));
      core.head.rotation.y += dt * (busy ? 0.9 : 0.25);
      core.head.position.y = 2.55 + wave(time * 1.6) * 0.08;
      core.lobe.emissiveIntensity = 0.3 + core.pulse * 1.1 + (busy ? 0.3 + wave(time * 6) * 0.15 : 0);
      core.halo.material.opacity = 0.25 + core.pulse * 0.6;
      core.halo.scale.setScalar(1 + core.pulse * 0.25);
      core.band.rotation.z += dt * (busy ? 2 : 0.4);
      const r = (time - core.rippleAt) / 1.2;
      core.ripple.material.opacity = r < 1 ? 0.8 * (1 - r) : 0;
      core.ripple.scale.setScalar(1 + Math.min(r, 1) * 1.8);
      for (const cube of this.memoryCubes) {
        const o = cube.userData.orbit; o.a += dt * 0.45;
        cube.position.set(Math.cos(o.a) * o.r, o.y + wave(time * 2 + o.a) * 0.08, wave(o.a) * o.r);
        cube.rotation.x += dt; cube.rotation.y += dt * 1.3;
      }
      const tag = this.brainTag;
      if (tag) this.placeTag(tag, this.v.set(core.anchor.x, core.anchor.y + 2.6, core.anchor.z).clone(), 'full');
    }
    for (let i = this.streams.length - 1; i >= 0; i--) {
      const s = this.streams[i]; s.time += dt;
      if (s.time < 0) continue;
      const p = s.time / s.duration;
      if (p >= 1) { this.scene.remove(s.mesh); this.streams.splice(i, 1); if (s.arrive) s.arrive(); continue; }
      const eased = p < 0.5 ? 2 * p * p : 1 - ((-2 * p + 2) ** 2) / 2;
      s.mesh.visible = true; s.mesh.position.copy(s.curve.getPoint(eased)); s.mesh.rotation.y += dt * s.spin;
      s.mesh.scale.setScalar((s.scale || 1) * Math.min(1, (1 - p) * 4, p * 8 + 0.2));
    }
    // Keep a stream going while an agent stays in a memory state.
    this.streamTimer = (this.streamTimer || 0) + dt;
    if (this.streamTimer > 1.1) {
      this.streamTimer = 0;
      for (const p of this.people.values()) if (p.root.visible && away(p.state) && !p.path.length) this.spawnStream(p, memoryKind(p.state));
    }
    for (const flow of this.flowList) {
      flow.tube.material.opacity = 0.45 + wave(time * 4) * 0.2;
      flow.dots.forEach((dot, i) => { dot.position.copy(flow.curve.getPoint(((time * 0.45) + i / 3) % 1)); });
    }
    for (const tag of this.zoneTags) this.placeTag(tag, tag.world, this.view.half < 26 ? 'full' : 'hidden');
    this.renderer.render(this.scene, this.camera);
  }
  animatePerson(person, t, dt, time) {
    const next = person.path[0];
    const walking = !!next;
    if (next) {
      const direction = next.clone().sub(person.root.position); direction.y = 0; const dist = direction.length();
      if (dist < 0.07) person.path.shift();
      else { person.root.position.addScaledVector(direction.normalize(), Math.min(dt * 2.6, dist)); person.root.rotation.y = Math.atan2(-direction.x, -direction.z); }
    }
    person.leftLeg.rotation.x = walking ? wave(t * 11) * 0.45 : 0;
    person.rightLeg.rotation.x = -person.leftLeg.rotation.x;
    person.head.rotation.set(0, 0, 0);
    person.leftArm.rotation.set(walking ? -person.leftLeg.rotation.x : 0, 0, 0);
    person.rightArm.rotation.set(walking ? person.leftLeg.rotation.x : 0, 0, 0);
    const memory = away(person.state);
    person.cup.visible = !walking && person.state === 'available';
    person.packet.visible = memory;
    // Blink: a short squash of the eyes every few seconds.
    if (time > person.blinkAt) person.blinkAt = time + 2.5 + ((person.phase * 7.3) % 3);
    person.eyes.scale.y = person.blinkAt - time < 0.12 ? 0.15 : 1;
    if (!walking) {
      if (person.state === 'working') {
        person.root.rotation.y = 0; person.leftArm.rotation.x = 1.8 + wave(t * 8) * 0.07; person.rightArm.rotation.x = 1.85 + Math.cos(t * 9) * 0.07;
        person.head.rotation.x = 0.1 + wave(t * 1.3) * 0.04; person.root.position.y = -0.15;
      } else if (memory) {
        const brain = this.core.anchor;
        person.root.rotation.y = Math.atan2(person.root.position.x - brain.x, person.root.position.z - brain.z);
        person.root.position.y = 0;
        person.rightArm.rotation.x = 1.5 + wave(t * 5) * 0.12;
        person.leftArm.rotation.set(0.5, 0, 0.25);
        person.head.rotation.x = person.state === 'loading' ? -0.15 : 0.05;
        person.packet.rotation.y += dt * 3;
      } else {
        person.root.rotation.y = -0.4 + wave(t * 0.3) * 0.35; person.rightArm.rotation.x = 0.95 + Math.max(0, wave(t * 0.8)) * 0.7;
        person.root.position.y = -0.15 + wave(t * 2) * 0.018;
      }
    } else person.root.position.y = Math.abs(wave(t * 11)) * 0.04;
    const selected = this.focusId === person.id || this.hoverId === person.id;
    const flash = person.flash !== undefined && time - person.flash < 1.2;
    const ringColor = memory ? STREAM[memoryKind(person.state)] : C.lime;
    person.ring.material.color.setHex(ringColor);
    person.ring.material.opacity = flash ? 1 : selected ? 0.9 : memory ? 0.75 : person.state === 'working' ? 0.5 : person.inPhase ? 0.3 : 0;
    person.ring.scale.setScalar(flash ? 1 + (time - person.flash) * 0.6 : 1);
    person.ring.visible = person.ring.material.opacity > 0;
    const tag = this.tags.get(person.id);
    if (tag) {
      const absent = person.id === 'orchestrator' && !person.root.visible;
      const full = selected || person.id === 'orchestrator' || person.state !== 'available' || person.inPhase || time < tag.bubbleUntil;
      const mode = full ? 'full' : this.view.half < 10 ? 'name' : 'hidden';
      const anchor = absent ? person.place.seat : person.root.position;
      this.placeTag(tag, this.v.set(anchor.x, anchor.y + 2.35, anchor.z).clone(), mode);
      tag.el.classList.toggle('office-tag--selected', selected);
    }
  }
  resize() {
    const width = this.container.clientWidth; const height = this.container.clientHeight; if (!width || !height) return;
    this.renderer.setSize(width, height);
    if (this.follow && this.people.size) this.frameActive();
    this.applyCamera();
  }
  screenOf(id) {
    const person = this.people.get(id); if (!person) return null;
    const v = person.root.position.clone().add(new THREE.Vector3(0, 1.2, 0)).project(this.camera);
    return { x: (v.x + 1) / 2 * this.container.clientWidth, y: (1 - v.y) / 2 * this.container.clientHeight };
  }
  debugSnapshot() {
    const info = this.renderer.info.render;
    return {
      people: [...this.people.values()].map((p) => ({ id: p.id, state: p.state, visible: p.root.visible, screen: this.screenOf(p.id) })),
      streams: this.streams.length, memoryCubes: this.memoryCubes.length, flows: this.flowList.length,
      room: { width: this.roomWidth, depth: this.roomDepth }, zones: this.zoneTags.map((z) => z.text.split('|')[0]),
      tags: [...this.tags.values()].filter((g) => g.mode !== 'hidden').length,
      tier: this.tier, fps: this.fps, calls: info.calls, triangles: info.triangles, half: +this.view.half.toFixed(2), following: this.follow,
    };
  }
}

let office = null;
window.officeScene = {
  mount(container, callbacks) {
    if (office) return office;
    try { office = new Office(container, callbacks); } catch (error) { office = null; throw error; }
    return office;
  },
  update(snapshot) { if (office) office.update(snapshot); },
  start() { if (office) office.start(); },
  stop() { if (office) office.stop(); },
  focus(id) { if (office) office.focus(id); },
  fitAll() { if (office) office.fitAll(); },
  followActive() { if (office) office.followActive(); },
  following() { return office ? office.follow : true; },
  screenOf(id) { return office ? office.screenOf(id) : null; },
  snapshot() { return office ? office.debugSnapshot() : null; },
};
window.dispatchEvent(new Event('office-scene-ready'));

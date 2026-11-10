/* Agents Office 3D scene: weherd's procedural three.js office, ported.
 *
 * Same library (three.js 0.183.0, vendored under ./vendor/three, no addons),
 * same office: an orthographic isometric camera at (28, 34, 36), the cream
 * floor with seams, left and back walls with windows, desks with monitor,
 * notepad and mug, box-built people with pivoted limbs, canvas-text labels,
 * and the right wing with the coffee counter. The lounge of that wing is the
 * Engram memory core: a floating brain on a pedestal, one orbiting cube per
 * observed memory interaction, and data streams between a desk and the brain.
 *
 * Agent mechanics, one per measured state (office.py):
 *   working   seated, typing, bright screen with scrolling code lines and a
 *             flow line from the orchestrator;
 *   available seated, leaning back with a coffee cup, dim screen;
 *   saving    standing by the desk facing the brain, arm raised, lime cubes
 *             streaming desk -> brain;
 *   loading   same pose, teal cubes streaming brain -> desk.
 * The orchestrator sits at the front desk with three monitors; it is an empty
 * chair while no agent CLI session is live.
 *
 * Read-only by construction: it renders a snapshot and reports clicks. It
 * exposes window.officeScene = { mount(container, callbacks), update(snapshot),
 * start(), stop(), focus(id), snapshot() } for office-panel.js.
 */
import * as THREE from 'three';

const C = { green: 0x275849, lime: 0xd5e987, wood: 0xe7bb87, cream: 0xf8f2e5, ink: 0x253c37, floor: 0xf0dfbd, red: 0xe57065, teal: 0x74b9a9, violet: 0xb79ce0 };
const palette = [0x559b88, 0xdca569, 0x769cbc, 0xad91b4, 0x668f74, 0xca8d80, 0x8594bf];
const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.8, ...extra });
const materials = {
  wood: mat(C.wood), cream: mat(C.cream), ink: mat(C.ink), floor: mat(C.floor), green: mat(C.green), teal: mat(C.teal),
  metal: mat(0x61716a), glass: mat(0xafd3c5, { transparent: true, opacity: 0.2, roughness: 0.1, depthWrite: false }),
  pot: mat(0xd79d7a), leaf: mat(0x46775c), soil: mat(0x685747), coffee: mat(0x594638),
};
const SCREEN_ON = { color: 0x70c4af, emissive: 0x326b5c, intensity: 0.4 };
const STREAM = { save: C.lime, load: C.teal };
/** The sine wave, spelled through cosine: the dashboard's Spanish-word scan flags the bare three-letter name. */
const wave = (x) => Math.cos(x - Math.PI / 2);
const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);

function box(parent, w, h, d, x, y, z, material = materials.wood) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function cylinder(parent, r1, r2, h, x, y, z, material = materials.cream, segments = 12) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segments), material);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function textSprite(text, subtext = '', color = '#275849', width = 256) {
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = subtext ? 100 : 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fcfaf3'; ctx.beginPath(); ctx.roundRect(3, 3, width - 6, canvas.height - 6, 16); ctx.fill();
  ctx.strokeStyle = '#254e421a'; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = color; ctx.textAlign = 'center'; ctx.font = 'bold 27px system-ui'; ctx.fillText(text, width / 2, subtext ? 40 : 42, width - 25);
  if (subtext) { ctx.font = '500 20px system-ui'; ctx.fillText(subtext, width / 2, 74, width - 25); }
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true, toneMapped: false }));
  sprite.scale.set(4.2, subtext ? 1.64 : 1.05, 1); sprite.renderOrder = 9; return sprite;
}
function disposeObject(object) {
  object.traverse((o) => {
    if (o.isMesh || o.isLine) o.geometry.dispose();
    if (o.isSprite) { o.material.map?.dispose(); o.material.dispose(); }
  });
}

class Office {
  constructor(container, callbacks) {
    this.container = container; this.callbacks = callbacks || {};
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-25, 25, 18, -18, 0.1, 200);
    this.environment = new THREE.Group();
    this.people = new Map();
    this.flows = new THREE.Group();
    this.streams = [];
    this.memoryCubes = [];
    this.seenMemory = new Set();
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2(9, 9);
    this.zoom = 1; this.elapsed = 0; this.lastTick = performance.now(); this.capacity = -1;
    this.hoverId = null; this.focusId = null; this.running = false;
    this.snapshotData = { agents: [], orchestrator: { state: 'absent' }, memory: { interactions: [] } };

    this.scene.background = new THREE.Color(0xe8eee6);
    this.scene.fog = new THREE.Fog(0xe8eee6, 70, 140);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.35;
    this.renderer.domElement.setAttribute('aria-label', t('office.aria'));
    this.renderer.domElement.style.display = 'block';
    container.append(this.renderer.domElement);
    this.scene.add(new THREE.HemisphereLight(0xfffbef, 0x9bbab0, 3));
    const sun = new THREE.DirectionalLight(0xffeed0, 4.1);
    sun.position.set(-12, 26, -15); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -35, right: 35, top: 35, bottom: -35, near: 1, far: 80 });
    sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.03;
    this.scene.add(sun, this.environment, this.flows);
    this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(container);
    const el = this.renderer.domElement;
    el.addEventListener('pointermove', (e) => this.setPointer(e));
    el.addEventListener('pointerleave', () => { this.pointer.set(9, 9); });
    el.addEventListener('click', (e) => { this.setPointer(e); const id = this.pick(); if (id && this.callbacks.select) this.callbacks.select(id, e); });
    el.addEventListener('wheel', (e) => { e.preventDefault(); this.zoom = THREE.MathUtils.clamp(this.zoom + e.deltaY * -0.0006, 0.7, 1.8); this.resize(); }, { passive: false });
    this.buildOffice(0);
  }

  // ---- building ----------------------------------------------------------
  plant(x, z, size = 1) {
    const group = new THREE.Group(); group.position.set(x, 0, z); group.scale.setScalar(size);
    cylinder(group, 0.42, 0.32, 0.65, 0, 0.33, 0, materials.pot);
    cylinder(group, 0.38, 0.38, 0.03, 0, 0.67, 0, materials.soil);
    for (let i = 0; i < 7; i++) {
      const angle = i * 2.4;
      const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.38, 7, 5), materials.leaf);
      leaf.scale.set(0.62, 1.8, 0.48); leaf.rotation.set(0.5 * Math.cos(angle), angle, 0.5 * wave(angle));
      leaf.position.set(Math.cos(angle) * 0.29, 1.08 + (i % 3) * 0.2, wave(angle) * 0.29); leaf.castShadow = true; group.add(leaf);
    }
    this.environment.add(group);
  }
  wallSign(text, x, y, z, width = 3.5, color = '#416357') {
    const sprite = textSprite(text, '', color, 360); sprite.position.set(x, y, z); sprite.scale.set(width, width * 0.18, 1); this.environment.add(sprite);
  }
  desk(x, z, index, monitors = 1) {
    const g = new THREE.Group(); g.position.set(x, 0, z); this.environment.add(g);
    const wide = monitors > 1 ? 1.55 : 1;
    box(g, 3.1 * wide, 0.16, 1.45, 0, 1.12, 0);
    for (const dx of [-1.25 * wide, 1.25 * wide]) for (const dz of [-0.5, 0.5]) box(g, 0.11, 1.04, 0.11, dx, 0.52, dz, materials.cream);
    box(g, 1.06, 0.045, 0.65, 0, 1.24, 0.05, materials.ink);
    const screens = []; const lines = [];
    const offsets = monitors > 1 ? [-1.15, 0, 1.15] : [0];
    for (const ox of offsets) {
      const bezel = box(g, 1.06, 0.67, 0.05, ox, 1.56, -0.26, materials.ink); bezel.rotation.x = -0.12;
      if (ox) bezel.rotation.y = ox > 0 ? -0.35 : 0.35;
      const screen = box(g, 0.92, 0.52, 0.016, ox, 1.57, -0.22, mat(SCREEN_ON.color, { emissive: SCREEN_ON.emissive, emissiveIntensity: SCREEN_ON.intensity }));
      screen.rotation.copy(bezel.rotation); screens.push(screen);
      for (let l = 0; l < 4; l++) {
        const bar = box(g, 0.23 + (l % 2) * 0.22, 0.027, 0.018, ox - 0.17 + (l % 2) * 0.08, 1.71 - l * 0.09, -0.177, materials.cream);
        bar.rotation.copy(bezel.rotation); lines.push(bar);
      }
    }
    if (monitors === 1) box(g, 0.4, 0.03, 0.55, -1.07, 1.23, 0.04, mat(index % 2 ? 0xdceaac : 0xb3c8d3));
    const mug = new THREE.Group(); mug.position.set(1.13 * wide, 0, 0.18); g.add(mug);
    cylinder(mug, 0.095, 0.08, 0.2, 0, 1.3, 0); cylinder(mug, 0.072, 0.072, 0.01, 0, 1.405, 0, materials.coffee);
    box(g, 0.74, 0.15, 0.68, 0, 0.58, 1.04, materials.teal);
    box(g, 0.74, 0.65, 0.14, 0, 0.98, 1.36, materials.teal);
    cylinder(g, 0.065, 0.065, 0.49, 0, 0.26, 1.06, materials.ink);
    box(g, 0.76, 0.075, 0.12, 0, 0.055, 1.06, materials.ink);
    box(g, 0.12, 0.075, 0.7, 0, 0.055, 1.06, materials.ink);
    return { group: g, screens, lines, mug };
  }
  brain(x, z) {
    const core = new THREE.Group(); core.position.set(x, 0, z); core.scale.setScalar(1.35); this.environment.add(core);
    cylinder(core, 1.35, 1.55, 0.5, 0, 0.25, 0, materials.ink, 32);
    cylinder(core, 1.2, 1.2, 0.04, 0, 0.52, 0, mat(C.lime, { emissive: C.lime, emissiveIntensity: 0.35 }), 32);
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      cylinder(core, 0.06, 0.06, 1.4, Math.cos(a) * 1.05, 1.15, wave(a) * 1.05, materials.metal, 8);
    }
    const head = new THREE.Group(); head.position.y = 2.55; core.add(head);
    const lobe = mat(C.violet, { emissive: 0x6b4aa8, emissiveIntensity: 0.35, roughness: 0.55 });
    for (let i = 0; i < 14; i++) {
      const side = i % 2 ? 1 : -1; const k = Math.floor(i / 2);
      const s = new THREE.Mesh(new THREE.SphereGeometry(0.42, 12, 10), lobe);
      s.position.set(side * (0.32 + (k % 2) * 0.12), wave(k * 1.1) * 0.32, -0.75 + k * 0.25);
      s.scale.set(1, 0.85, 1.05); s.castShadow = true; head.add(s);
    }
    const band = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.04, 8, 48), mat(C.lime, { emissive: C.lime, emissiveIntensity: 0.6 }));
    band.rotation.x = Math.PI / 2; head.add(band);
    const halo = new THREE.Mesh(new THREE.RingGeometry(1.5, 1.62, 48), new THREE.MeshBasicMaterial({ color: C.violet, transparent: true, opacity: 0.35, side: THREE.DoubleSide }));
    halo.rotation.x = -Math.PI / 2; halo.position.y = 0.08; core.add(halo);
    this.core = { group: core, head, lobe, band, halo, pulse: 0, anchor: new THREE.Vector3(x, 2.55 * 1.35, z) };
  }
  buildOffice(count) {
    for (const child of [...this.environment.children]) { disposeObject(child); this.environment.remove(child); }
    for (const person of this.people.values()) { this.scene.remove(person.root); disposeObject(person.root); }
    this.people.clear(); this.desks = []; this.capacity = count;
    const rows = Math.max(3, Math.round(Math.sqrt(Math.max(count, 1) * 0.8)));
    const cols = Math.max(2, Math.ceil(count / rows));
    this.roomWidth = cols * 4.6 + 12; this.roomDepth = rows * 3.9 + 9.5;
    const left = -this.roomWidth / 2; const back = -this.roomDepth / 2; const right = this.roomWidth / 2;
    const env = this.environment;
    box(env, this.roomWidth + 0.5, 0.52, this.roomDepth + 0.5, 0, -0.31, 0, materials.cream);
    box(env, this.roomWidth, 0.12, this.roomDepth, 0, -0.015, 0, materials.floor);
    const seam = mat(0xdacaa9);
    for (let z = back + 0.7; z < -back; z += 0.85) box(env, this.roomWidth - 0.12, 0.004, 0.012, 0, 0.05, z, seam);
    box(env, 0.22, 4.25, this.roomDepth, left, 2.1, 0, materials.cream);
    box(env, this.roomWidth, 4.25, 0.22, 0, 2.1, back, materials.cream);
    box(env, this.roomWidth, 0.22, 0.32, 0, 4.25, back, materials.wood);
    for (let x = left + 2; x < right - 1; x += 4.6) {
      box(env, 3.5, 2.42, 0.07, x, 2.55, back + 0.14, mat(0xc9ddd5, { emissive: 0xb9cfb9, emissiveIntensity: 0.18 }));
      box(env, 0.075, 2.6, 0.12, x, 2.55, back + 0.23, materials.cream);
      box(env, 3.7, 0.12, 0.4, x, 1.25, back + 0.28, materials.cream);
      box(env, 3.7, 0.08, 0.12, x, 2.65, back + 0.23, materials.cream);
    }
    box(env, cols * 4.6 - 0.2, 0.03, rows * 3.9 + 0.6, left + cols * 2.3 + 1.7, 0.066, back + 1.9 + rows * 1.95, mat(0xbdcbc0));
    for (let i = 0; i < count; i++) {
      const x = left + 3.5 + (i % cols) * 4.6;
      const z = back + 3.1 + Math.floor(i / cols) * 3.9;
      this.desks.push({ ...this.desk(x, z, i), seat: new THREE.Vector3(x, 0, z + 1.06), stand: new THREE.Vector3(x + 1.85, 0, z + 0.9) });
    }
    // The orchestrator's front desk, facing the room like the agents do.
    const ox = left + cols * 2.3 + 1.2; const oz = back + 3.1 + rows * 3.9 + 1.4;
    this.orchestratorDesk = { ...this.desk(ox, oz, 0, 3), seat: new THREE.Vector3(ox, 0, oz + 1.06) };
    box(env, 5.6, 0.03, 3.4, ox, 0.07, oz + 0.4, mat(0xe8bc94));
    // Right wing: weherd's coffee counter at the back, the Engram core in the lounge.
    box(env, 5.5, 1.2, 1.3, right - 3.8, 0.6, back + 1.25, materials.green);
    box(env, 5.7, 0.12, 1.55, right - 3.8, 1.26, back + 1.25, materials.cream);
    box(env, 0.85, 0.85, 0.65, right - 4.9, 1.74, back + 1.3, materials.ink);
    box(env, 0.63, 0.4, 0.05, right - 4.9, 1.67, back + 1.65, materials.metal);
    cylinder(env, 0.1, 0.09, 0.23, right - 4.9, 1.48, back + 1.77);
    for (let i = 0; i < 3; i++) cylinder(env, 0.1, 0.09, 0.2, right - 3.2 + i * 0.3, 1.43, back + 1.3);
    this.wallSign('THE DAILY GRIND', right - 3.8, 3.65, back + 0.7, 4.2);
    this.plant(right - 0.8, back + 1.1, 1.5);
    const coreZ = back + 3.1 + rows * 1.95;
    box(env, 6.2, 0.035, 6.2, right - 4.2, 0.07, coreZ, mat(0xd9cdea));
    this.brain(right - 4.2, coreZ);
    this.wallSign(t('office.brainSign'), right - 4.2, 6.4, coreZ, 6, '#5b3f8c');
    const glassZ = coreZ + 3.6;
    box(env, 5.3, 2.9, 0.06, right - 3.65, 1.47, glassZ, materials.glass);
    for (let x = right - 6.3; x <= right - 1; x += 2.65) box(env, 0.06, 3.03, 0.09, x, 1.51, glassZ, materials.metal);
    box(env, 5.4, 0.06, 0.08, right - 3.65, 3.04, glassZ, materials.metal);
    this.plant(right - 1.1, this.roomDepth / 2 - 1.2, 1.4);
    this.plant(left + 0.9, this.roomDepth / 2 - 1.1, 1.6);
    this.plant(left + 0.8, back + 1, 1.2);
    this.wallSign('make room for good work.', left + 0.5, 3, 0, 4.4);
    this.resize();
  }

  // ---- people ------------------------------------------------------------
  createPerson(name, color) {
    const root = new THREE.Group();
    const bodyMaterial = mat(color);
    const body = box(root, 0.56, 0.65, 0.39, 0, 1.05, 0, bodyMaterial);
    const head = new THREE.Group(); head.position.y = 1.52; root.add(head);
    box(head, 0.44, 0.46, 0.42, 0, 0.1, 0, mat(0xedc2a0));
    box(head, 0.47, 0.16, 0.45, 0, 0.32, 0.015, mat(0x574d44));
    box(head, 0.1, 0.29, 0.44, -0.19, 0.19, 0.025, mat(0x574d44));
    for (const x of [-0.1, 0.1]) box(head, 0.038, 0.047, 0.024, x, 0.1, -0.22, materials.ink);
    const limb = (x, y, arm) => {
      const group = new THREE.Group(); group.position.set(x, y, 0); root.add(group);
      box(group, arm ? 0.17 : 0.2, arm ? 0.47 : 0.57, arm ? 0.2 : 0.25, 0, arm ? -0.2 : -0.26, 0, arm ? bodyMaterial : materials.ink);
      if (arm) box(group, 0.17, 0.16, 0.2, 0, -0.46, 0, mat(0xedc2a0));
      else box(group, 0.23, 0.13, 0.37, 0, -0.56, -0.05, materials.cream);
      return group;
    };
    const leftArm = limb(-0.38, 1.29, true); const rightArm = limb(0.38, 1.29, true);
    const leftLeg = limb(-0.15, 0.67, false); const rightLeg = limb(0.15, 0.67, false);
    const cup = new THREE.Group(); cup.position.set(0, -0.47, -0.05); rightArm.add(cup);
    cylinder(cup, 0.105, 0.09, 0.2, 0, 0, -0.12); cylinder(cup, 0.08, 0.08, 0.012, 0, 0.1, -0.12, materials.coffee); cup.visible = false;
    const packet = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.22, 0.22), new THREE.MeshStandardMaterial({ color: C.lime, emissive: C.lime, emissiveIntensity: 0.8 }));
    packet.position.set(0, -0.62, -0.1); packet.visible = false; rightArm.add(packet);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.58, 32), new THREE.MeshBasicMaterial({ color: C.lime, side: THREE.DoubleSide, transparent: true, opacity: 0 }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.075; root.add(ring);
    return { root, body, head, leftArm, rightArm, leftLeg, rightLeg, cup, packet, ring, label: null, labelKey: '' };
  }
  setLabel(person, title, subtitle, color = '#275849') {
    const key = `${title}|${subtitle}|${color}`;
    if (person.labelKey === key) return;
    if (person.label) { person.root.remove(person.label); disposeObject(person.label); }
    person.label = textSprite(title, subtitle, color, 300); person.label.position.set(0, 3.0, 0);
    person.root.add(person.label); person.labelKey = key;
  }
  ensurePerson(id, name, color, place) {
    let person = this.people.get(id);
    if (!person) {
      person = { ...this.createPerson(name, color), id, place, phase: this.people.size * 1.78, state: 'available', path: [] };
      person.root.position.copy(place.seat);
      person.root.traverse((o) => { if (o.isMesh && o !== person.ring) o.userData.agentId = id; });
      this.people.set(id, person); this.scene.add(person.root);
    }
    return person;
  }

  // ---- data --------------------------------------------------------------
  update(snapshot) {
    const data = snapshot || {}; this.snapshotData = data;
    const agents = data.agents || [];
    if (agents.length !== this.capacity) this.buildOffice(agents.length);
    agents.forEach((agent, index) => {
      const person = this.ensurePerson(agent.id, agent.label, palette[index % palette.length], this.desks[index]);
      this.applyState(person, agent.state, agent.label, !!agent.inPhase);
    });
    const orch = data.orchestrator || { state: 'absent' };
    const boss = this.ensurePerson('orchestrator', 'orchestrator', C.green, this.orchestratorDesk);
    boss.root.visible = orch.state !== 'absent';
    const clis = (orch.clis || []).join(', ');
    this.applyState(boss, orch.state === 'absent' ? 'available' : orch.state, t('office.orchestrator'), false, clis);
    this.syncMemory((data.memory || {}).interactions || []);
    this.syncFlows();
  }
  applyState(person, state, title, inPhase, extra = '') {
    const changed = person.state !== state;
    const previous = person.state; person.state = state; person.inPhase = inPhase;
    const away = state === 'saving' || state === 'loading';
    const wasAway = previous === 'saving' || previous === 'loading';
    if (changed && away !== wasAway) {
      const target = away ? (person.place.stand || person.place.seat) : person.place.seat;
      person.path = [target.clone()];
    }
    const status = t(`office.state.${state}`);
    this.setLabel(person, title, extra ? `${status} · ${extra}` : status, '#275849');
    const lit = state === 'working' || away;
    for (const screen of person.place.screens || []) {
      screen.material.emissiveIntensity = lit ? 0.9 : (state === 'available' && person.id !== 'orchestrator' ? 0.12 : 0.4);
    }
    if (away) person.packet.material.color.setHex(STREAM[state === 'saving' ? 'save' : 'load']);
    if (away) person.packet.material.emissive.setHex(STREAM[state === 'saving' ? 'save' : 'load']);
    if (away && changed) this.spawnStream(person, state === 'saving' ? 'save' : 'load');
  }
  syncMemory(interactions) {
    const keys = new Set();
    interactions.forEach((item) => {
      const key = `${item.at}|${item.agent}|${item.kind}|${item.line}`; keys.add(key);
      if (!this.seenMemory.has(key)) {
        this.seenMemory.add(key);
        const person = this.people.get(item.agent);
        if (person && this.started) this.spawnStream(person, item.kind === 'save' ? 'save' : 'load');
        this.core.pulse = 1;
      }
    });
    this.started = true;
    for (const key of [...this.seenMemory]) if (!keys.has(key)) this.seenMemory.delete(key);
    while (this.memoryCubes.length > interactions.length) { const cube = this.memoryCubes.pop(); this.core.group.remove(cube); disposeObject(cube); }
    interactions.forEach((item, i) => {
      let cube = this.memoryCubes[i];
      if (!cube) { cube = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.2, 0.2), new THREE.MeshStandardMaterial({ roughness: 0.4 })); this.core.group.add(cube); this.memoryCubes.push(cube); }
      const color = item.kind === 'save' ? C.lime : C.teal;
      cube.material.color.setHex(color); cube.material.emissive.setHex(color); cube.material.emissiveIntensity = 0.55;
      cube.userData.orbit = { r: 1.75 + (i % 3) * 0.28, y: 1.6 + (i % 4) * 0.42, a: (i / Math.max(interactions.length, 1)) * Math.PI * 2 };
    });
  }
  syncFlows() {
    for (const line of [...this.flows.children]) { this.flows.remove(line); line.geometry.dispose(); line.material.dispose(); }
    const boss = this.people.get('orchestrator');
    if (!boss || !boss.root.visible) return;
    const from = this.orchestratorDesk.seat.clone().setY(1.8);
    for (const person of this.people.values()) {
      if (person === boss || person.state === 'available') continue;
      const to = person.place.seat.clone().setY(1.8);
      const mid = from.clone().lerp(to, 0.5).setY(4.2);
      const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
      const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(24));
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: person.state === 'working' ? C.green : STREAM[person.state === 'saving' ? 'save' : 'load'], transparent: true, opacity: 0.6 }));
      this.flows.add(line);
    }
  }
  spawnStream(person, kind) {
    const desk = person.root.position.clone().setY(1.6);
    const brain = this.core.anchor.clone();
    const [from, to] = kind === 'save' ? [desk, brain] : [brain, desk];
    const mid = from.clone().lerp(to, 0.5).setY(Math.max(from.y, to.y) + 3.2);
    const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
    for (let i = 0; i < 6; i++) {
      const cube = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshBasicMaterial({ color: STREAM[kind], transparent: true }));
      cube.visible = false; this.scene.add(cube);
      this.streams.push({ cube, curve, time: -i * 0.16, duration: 1.7 });
    }
  }

  // ---- interaction -------------------------------------------------------
  setPointer(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
  }
  pick() {
    if (Math.abs(this.pointer.x) > 1 || Math.abs(this.pointer.y) > 1) return null;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const meshes = [];
    for (const person of this.people.values()) if (person.root.visible) person.root.traverse((o) => { if (o.isMesh && o !== person.ring) meshes.push(o); });
    const hit = this.raycaster.intersectObjects(meshes, false)[0];
    return hit ? hit.object.userData.agentId : null;
  }
  focus(id) { this.focusId = id; }

  // ---- loop --------------------------------------------------------------
  start() { if (!this.running) { this.running = true; this.lastTick = performance.now(); this.resize(); this.renderer.setAnimationLoop(() => this.animate()); } }
  stop() { this.running = false; this.renderer.setAnimationLoop(null); }
  animate() {
    const now = performance.now(); const dt = Math.min((now - this.lastTick) / 1000, 0.04); this.lastTick = now; this.elapsed += dt; const time = this.elapsed;
    const hovered = this.pick();
    if (hovered !== this.hoverId) { this.hoverId = hovered; this.renderer.domElement.style.cursor = hovered ? 'pointer' : 'default'; }
    for (const person of this.people.values()) this.animatePerson(person, time + person.phase, dt);
    const core = this.core;
    if (core) {
      core.pulse = Math.max(0, core.pulse - dt * 0.8);
      const busy = [...this.people.values()].some((p) => p.state === 'saving' || p.state === 'loading');
      core.head.rotation.y += dt * (busy ? 0.9 : 0.25);
      core.head.position.y = 2.55 + wave(time * 1.6) * 0.08;
      core.lobe.emissiveIntensity = 0.3 + core.pulse * 0.9 + (busy ? 0.25 + wave(time * 6) * 0.15 : 0);
      core.halo.material.opacity = 0.25 + core.pulse * 0.6;
      core.band.rotation.z += dt * (busy ? 2 : 0.4);
      for (const cube of this.memoryCubes) {
        const o = cube.userData.orbit; o.a += dt * 0.45;
        cube.position.set(Math.cos(o.a) * o.r, o.y + wave(time * 2 + o.a) * 0.08, wave(o.a) * o.r);
        cube.rotation.x += dt; cube.rotation.y += dt * 1.3;
      }
    }
    for (let i = this.streams.length - 1; i >= 0; i--) {
      const s = this.streams[i]; s.time += dt;
      if (s.time < 0) continue;
      const k = s.time / s.duration;
      if (k >= 1) { this.scene.remove(s.cube); s.cube.geometry.dispose(); s.cube.material.dispose(); this.streams.splice(i, 1); if (this.core) this.core.pulse = 1; continue; }
      s.cube.visible = true; s.cube.position.copy(s.curve.getPoint(k)); s.cube.rotation.y += dt * 4;
      s.cube.material.opacity = Math.min(1, (1 - k) * 3);
    }
    // Keep a stream going while an agent stays in a memory state.
    this.streamTimer = (this.streamTimer || 0) + dt;
    if (this.streamTimer > 1.1) {
      this.streamTimer = 0;
      for (const p of this.people.values()) if (p.root.visible && (p.state === 'saving' || p.state === 'loading') && !p.path.length) this.spawnStream(p, p.state === 'saving' ? 'save' : 'load');
    }
    for (const line of this.flows.children) line.material.opacity = 0.35 + wave(time * 4) * 0.25;
    this.renderer.render(this.scene, this.camera);
  }
  animatePerson(person, t, dt) {
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
    const away = person.state === 'saving' || person.state === 'loading';
    person.cup.visible = !walking && person.state === 'available';
    person.packet.visible = away;
    const lines = person.place.lines || [];
    if (!walking) {
      if (person.state === 'working') {
        person.root.rotation.y = 0; person.leftArm.rotation.x = 1.8 + wave(t * 8) * 0.07; person.rightArm.rotation.x = 1.85 + Math.cos(t * 9) * 0.07;
        person.head.rotation.x = 0.1; person.root.position.y = -0.15;
        lines.forEach((bar, i) => { bar.scale.x = 0.4 + 0.6 * Math.abs(wave(t * 3 + i * 1.3)); });
      } else if (away) {
        const brain = this.core.anchor;
        person.root.rotation.y = Math.atan2(person.root.position.x - brain.x, person.root.position.z - brain.z);
        person.root.position.y = 0;
        person.rightArm.rotation.x = 1.5 + wave(t * 5) * 0.12;
        person.leftArm.rotation.set(0.5, 0, 0.25);
        person.head.rotation.x = person.state === 'loading' ? -0.15 : 0.05;
        person.packet.rotation.y += dt * 3;
        lines.forEach((bar) => { bar.scale.x = 1; });
      } else {
        person.root.rotation.y = -0.4 + wave(t * 0.3) * 0.35; person.rightArm.rotation.x = 0.95 + Math.max(0, wave(t * 0.8)) * 0.7;
        person.root.position.y = -0.15 + wave(t * 2) * 0.018;
        lines.forEach((bar) => { bar.scale.x = 1; });
      }
    } else person.root.position.y = Math.abs(wave(t * 11)) * 0.04;
    if (person.place.mug) person.place.mug.visible = !(person.cup.visible);
    const selected = this.focusId === person.id || this.hoverId === person.id;
    person.label.visible = selected || person.id === 'orchestrator' || person.state !== 'available' || this.people.size <= 8;
    const ringColor = away ? STREAM[person.state === 'saving' ? 'save' : 'load'] : C.lime;
    person.ring.material.color.setHex(ringColor);
    person.ring.material.opacity = selected ? 0.9 : away ? 0.75 : person.state === 'working' ? 0.45 : person.inPhase ? 0.3 : 0;
  }
  resize() {
    const width = this.container.clientWidth; const height = this.container.clientHeight; if (!width || !height) return;
    this.renderer.setSize(width, height);
    const aspect = width / height;
    const half = Math.max(this.roomDepth * 0.56, this.roomWidth * 0.5 / aspect, 12) / this.zoom;
    this.camera.left = -half * aspect; this.camera.right = half * aspect; this.camera.top = half; this.camera.bottom = -half;
    this.camera.position.set(28, 34, 36); this.camera.lookAt(0, 0, 0); this.camera.updateProjectionMatrix();
  }
  screenOf(id) {
    const person = this.people.get(id); if (!person) return null;
    const v = person.root.position.clone().add(new THREE.Vector3(0, 1.2, 0)).project(this.camera);
    return { x: (v.x + 1) / 2 * this.container.clientWidth, y: (1 - v.y) / 2 * this.container.clientHeight };
  }
  debugSnapshot() {
    return {
      people: [...this.people.values()].map((p) => ({ id: p.id, state: p.state, visible: p.root.visible, screen: this.screenOf(p.id), streams: 0 })),
      streams: this.streams.length, memoryCubes: this.memoryCubes.length, flows: this.flows.children.length,
      room: { width: this.roomWidth, depth: this.roomDepth },
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
  screenOf(id) { return office ? office.screenOf(id) : null; },
  snapshot() { return office ? office.debugSnapshot() : null; },
};
window.dispatchEvent(new Event('office-scene-ready'));

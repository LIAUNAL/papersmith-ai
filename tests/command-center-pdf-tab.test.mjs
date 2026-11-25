// The dashboard's PDF tab beside Caztor: the tab's decisions (pdfTabLogic in index.html), the markup
// contract of its toolbar and Change Control panel, and the CLI assistant taking the keyboard from the
// Caztor frame (cli-console.js). Runs the shipped sources in node with stub DOMs.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const STATIC = new URL('../skills/_core/command_center/static/', import.meta.url);
const PAGE = readFileSync(new URL('index.html', STATIC), 'utf8');
const CLI = readFileSync(new URL('cli-console.js', STATIC), 'utf8');
const EN = readFileSync(new URL('i18n/en.js', STATIC), 'utf8');
const ES = readFileSync(new URL('i18n/es.js', STATIC), 'utf8');

function pdfTabLogic() {
  const match = PAGE.match(/<script id="pdfTabLogic">([\s\S]*?)<\/script>/);
  assert.ok(match, 'index.html carries the pdfTabLogic block');
  const window = {};
  vm.runInNewContext(match[1], { window });
  return window.pdfTabLogic;
}

function memoryStore(initial = {}) {
  const data = { ...initial };
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); } };
}
// Objects built inside the vm context have that context's prototypes: compare their JSON.
const plain = (value) => JSON.parse(JSON.stringify(value));
const blockedStore = {
  getItem() { throw new Error('SecurityError'); },
  setItem() { throw new Error('SecurityError'); },
};

// -- the Change Control panel and the board report: remembered per browser ----------------------------
test('the Change Control panel starts collapsed in the editor and open in the viewer', () => {
  const logic = pdfTabLogic();
  const store = memoryStore();
  assert.equal(logic.panelOpen(store, 'editor'), false);
  assert.equal(logic.panelOpen(store, 'viewer'), true);
});

test('the operator choice is remembered per mode', () => {
  const logic = pdfTabLogic();
  const store = memoryStore();
  logic.rememberPanel(store, 'editor', true);
  logic.rememberPanel(store, 'viewer', false);
  assert.equal(logic.panelOpen(store, 'editor'), true);
  assert.equal(logic.panelOpen(store, 'viewer'), false);
  assert.deepEqual(store.data, { 'papersmith.changeControl.editor': 'open', 'papersmith.changeControl.viewer': 'collapsed' });
});

test('blocked storage falls back to the defaults and never throws', () => {
  const logic = pdfTabLogic();
  assert.doesNotThrow(() => logic.rememberPanel(blockedStore, 'editor', true));
  assert.equal(logic.panelOpen(blockedStore, 'editor'), false);
  assert.equal(logic.panelOpen(blockedStore, 'viewer'), true);
  assert.equal(logic.panelOpen(null, 'viewer'), true);
  assert.doesNotThrow(() => logic.rememberBoard(blockedStore, true));
  assert.equal(logic.boardOpen(blockedStore), false);
});

test('the board report starts collapsed and remembers an expansion', () => {
  const logic = pdfTabLogic();
  const store = memoryStore();
  assert.equal(logic.boardOpen(store), false);
  logic.rememberBoard(store, true);
  assert.equal(logic.boardOpen(store), true);
  logic.rememberBoard(store, false);
  assert.equal(logic.boardOpen(store), false);
});

// -- the frame key contract (/api/terminal/caztor) ------------------------------------------------------
test('the frame loads Caztor with its frame key when the dashboard has one', () => {
  const logic = pdfTabLogic();
  assert.equal(logic.caztorFrameUrl({ url: 'http://127.0.0.1:4100', key: 'a b/c+d' }),
    'http://127.0.0.1:4100/?k=a%20b%2Fc%2Bd');
  assert.equal(logic.caztorFrameUrl({ url: 'http://127.0.0.1:4100/', key: 'k1' }), 'http://127.0.0.1:4100/?k=k1');
  assert.equal(logic.caztorFrameUrl({ url: 'http://127.0.0.1:4100' }), 'http://127.0.0.1:4100');
  assert.equal(logic.caztorFrameUrl({ url: 'http://127.0.0.1:4100', key: '' }), 'http://127.0.0.1:4100');
});

test('the page asks for Caztor under /api/terminal, where the terminal login cookie reaches', () => {
  const logic = pdfTabLogic();
  assert.equal(logic.CAZTOR_API, '/api/terminal/caztor');
  assert.equal(logic.CAZTOR_STOP_API, '/api/terminal/caztor/stop');
  assert.doesNotMatch(PAGE, /fetch\(\s*['"`]\/api\/caztor/);
  assert.match(PAGE, /fetch\(pdfTabLogic\.CAZTOR_API, \{ method: 'POST' \}\)/);
  assert.match(PAGE, /fetch\(pdfTabLogic\.CAZTOR_STOP_API, \{ method: 'POST' \}\)/);
});

test('a missing terminal login is a locked state with its reason; other answers pass through', () => {
  const logic = pdfTabLogic();
  const reason = 'The LaTeX editor needs the terminal access link, the same one the CLI assistant needs: ...';
  assert.deepEqual(
    plain(logic.caztorReply(403, { available: false, error: 'TERMINAL_LOGIN_REQUIRED', reason })),
    { available: false, locked: true, reason });
  const ready = { available: true, url: 'http://127.0.0.1:4100', instance: 3, key: 'k' };
  assert.equal(logic.caztorReply(200, ready), ready);
  const crossOrigin = { available: false, reason: 'cross-origin request rejected' };
  assert.equal(logic.caztorReply(403, crossOrigin), crossOrigin);
  assert.deepEqual(plain(logic.caztorReply(502, null)), { available: false, reason: 'HTTP 502' });
});

test('the locked notice uses the CLI assistant activation hint and its Activate button', () => {
  assert.match(PAGE, /t\('caztor\.locked', \{ reason \}\)\} \$\{t\('cli\.activateBanner'\)\}`, \{ activate: true \}/);
  assert.match(PAGE, /window\.smithTerminalActivate\(\)/);
  assert.match(CLI, /window\.smithTerminalActivate = ensureAuthorized;/);
});

// -- asking for Caztor: on a reload, and not on every visit -------------------------------------------
test('a page load asks for Caztor: no instance runs in the frame yet', () => {
  const logic = pdfTabLogic();
  assert.equal(logic.shouldAskCaztor({ active: false, frameInstance: '', askedAt: 0, now: 1e6 }), true);
  // A stale "not set up" answer is not kept either: an unavailable state always asks again.
  assert.equal(logic.shouldAskCaztor({ active: false, frameInstance: 'http://x#1', askedAt: 1e6 - 10, now: 1e6 }), true);
});

test('a ready frame for the same instance is not asked for again on each visit, but rechecked later', () => {
  const logic = pdfTabLogic();
  const ready = { active: true, frameInstance: 'http://127.0.0.1:4100#3', askedAt: 1_000_000 };
  assert.equal(logic.shouldAskCaztor({ ...ready, now: 1_000_000 + 5_000 }), false);
  assert.equal(logic.shouldAskCaztor({ ...ready, now: 1_000_000 + logic.CAZTOR_RECHECK_MS }), true);
  assert.equal(logic.shouldAskCaztor({ ...ready, now: 1_000_000 + 5_000, force: true }), true);
});

test('the tab visit and the page load go through the same ask', () => {
  // navigateTab('preview') asks (unforced); the load route reaches it for a direct #preview load.
  assert.match(PAGE, /if \(tabId === 'preview'\) \{\s*openPdfWorkspace\(\);/);
  assert.match(PAGE, /\['pipeline', 'flow', [^\]]*'preview'[^\]]*\]\.includes\(hash\)\) \{\s*navigateTab\(hash\);/);
  // The switch turned on forces a new ask.
  assert.match(PAGE, /pdfViewerPeek = false;\s*await openPdfWorkspace\(\{ force: true \}\);/);
});

// -- timers ----------------------------------------------------------------------------------------------
test('the 5 s fallback status poll pauses while the page is hidden', () => {
  const logic = pdfTabLogic();
  assert.equal(logic.statusPollDue({ hidden: true, connected: false, lastStatusAt: 0, now: 1e6 }), false);
  assert.equal(logic.statusPollDue({ hidden: false, connected: false, lastStatusAt: 1e6, now: 1e6 }), true);
  assert.equal(logic.statusPollDue({ hidden: false, connected: true, lastStatusAt: 1e6 - 1000, now: 1e6 }), false);
  assert.equal(logic.statusPollDue({ hidden: false, connected: true, lastStatusAt: 1e6 - 31000, now: 1e6 }), true);
  assert.match(PAGE, /if \(pdfTabLogic\.statusPollDue\(\{/);
});

test('the frame watch stops once the frame is ready and waits while the page is hidden', () => {
  const logic = pdfTabLogic();
  assert.equal(logic.caztorTimersMayRun({ hidden: false, ready: false, wanted: true }), true);
  assert.equal(logic.caztorTimersMayRun({ hidden: false, ready: true, wanted: true }), false);
  assert.equal(logic.caztorTimersMayRun({ hidden: true, ready: false, wanted: true }), false);
  assert.equal(logic.caztorTimersMayRun({ hidden: false, ready: false, wanted: false }), false);
  // `caztor:ready` clears the watch; a hidden page does not probe.
  assert.match(PAGE, /caztorReady = true;[\s\S]{0,200}clearTimeout\(caztorWatch\);\s*caztorWatch = null;/);
  assert.match(PAGE, /if \(document\.hidden\) \{\s*const left = deadline - Date\.now\(\);\s*await whenVisible\(\);/);
});

// -- markup: one toolbar, a collapsible panel, a frame that fits the window ------------------------------
function between(text, start, end) {
  const from = text.indexOf(start);
  assert.ok(from >= 0, `missing ${start}`);
  const to = text.indexOf(end, from);
  assert.ok(to > from, `missing ${end} after ${start}`);
  return text.slice(from, to);
}

test('one toolbar holds the editor switch, the new tab link, Style & redundancy and the panel toggle', () => {
  const toolbar = between(PAGE, '<div class="pdf-tab-toolbar" id="pdfTabToolbar"', '<div class="pdf-workspace-layout">');
  for (const id of ['caztorToggle', 'linkPdfDirect', 'btnAuditAi', 'btnToggleChangeControl', 'btnBackToEditor', 'toolbarMarksCount']) {
    assert.match(toolbar, new RegExp(`id="${id}"`), id);
  }
  assert.match(toolbar, /id="btnAuditAi" onclick="openStyleRedundancyPanel\(\)"/);
  assert.match(toolbar, /data-i18n-attr="title:pdf\.manuscriptHint"/);
  // The viewer's own bar no longer repeats it, and the long description block is gone.
  const viewerBar = between(PAGE, '<div class="pdf-viewer-topbar">', '<!-- Continuous multi-page PDF container -->');
  assert.doesNotMatch(viewerBar, /btnAuditAi/);
  assert.doesNotMatch(PAGE, /data-i18n-html="pdf\.manuscriptHtml"/);
  assert.equal((PAGE.match(/id="btnAuditAi"/g) || []).length, 1);
});

test('the Change Control panel has a handle that opens it and keeps the pending marks in view', () => {
  const aside = between(PAGE, '<aside class="pdf-control-panel" id="pdfControlPanel"', '</aside>');
  assert.match(aside, /class="control-panel__handle" id="changeControlHandle" onclick="setChangeControlOpen\(true\)"/);
  assert.match(aside, /id="changeControlHandleCount"/);
  assert.match(aside, /onclick="setChangeControlOpen\(false\)"/);
  assert.match(PAGE, /\.pdf-control-panel\.is-collapsed > :not\(\.control-panel__handle\) \{ display: none; \}/);
  assert.match(PAGE, /\['toolbarMarksCount', 'changeControlHandleCount'\]\.forEach/);
});

test('the Caztor frame and the viewer fit the window under the sticky header and the toolbar', () => {
  const frameRule = between(PAGE, '    .caztor-frame {', '}');
  assert.match(frameRule, /height: var\(--pdf-fit-h\);/);
  assert.doesNotMatch(frameRule, /750px|720px/);
  assert.match(PAGE, /--pdf-fit-h: calc\(100vh - var\(--topbar-h, 72px\) - var\(--pdf-toolbar-h, 46px\) - 1\.5rem\);/);
  assert.match(PAGE, /#pane-preview \.pdf-viewport-container \{\s*max-height: max\(420px, calc\(var\(--pdf-fit-h\)/);
  // The stacked layout under 900 px stays.
  assert.match(PAGE, /@media \(max-width: 900px\) \{\s*\.split-layout[^}]*\}\s*\.pdf-workspace-layout \{ flex-direction: column; \}/);
});

test('venue, translation and page jumps switch to the viewer with a way back to the editor', () => {
  assert.match(PAGE, /if \(pdfVenueSlug\) showViewerOverEditor\(\);/);
  assert.match(PAGE, /if \(pdfTranslation\) showViewerOverEditor\(\);/);
  assert.match(PAGE, /navigateTab\('preview'\);\s*\/\/[^\n]*\n\s*peekPdfViewer\(\);/);
  assert.match(PAGE, /id="btnBackToEditor" onclick="backToCaztorEditor\(\)" hidden/);
  assert.match(PAGE, /window\.backToCaztorEditor = backToCaztorEditor;/);
});

test('every new label exists in both catalogues', () => {
  const keys = ['pdf.toolbarLabel', 'pdf.manuscriptShort', 'pdf.manuscriptHint', 'caztor.backToEditor',
    'caztor.backToEditorHint', 'caztor.locked', 'changes.toggleButton', 'changes.toggleHint',
    'changes.expand', 'changes.collapse', 'board.expand', 'board.collapse'];
  for (const key of keys) {
    assert.match(EN, new RegExp(`"${key.replace('.', '\\.')}": "`), `en ${key}`);
    assert.match(ES, new RegExp(`"${key.replace('.', '\\.')}": "`), `es ${key}`);
  }
});

// -- the CLI assistant takes the keyboard from the Caztor frame -------------------------------------------
function cliHarness() {
  const els = {};
  const el = (id) => {
    if (!els[id]) {
      const cls = new Set();
      els[id] = {
        id, value: '', textContent: '', dataset: {}, disabled: false, innerHTML: '',
        classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
          toggle: (c) => (cls.has(c) ? cls.delete(c) : cls.add(c)) },
        setAttribute() {}, addEventListener() {}, appendChild() {}, append() {}, focus() {},
      };
    }
    return els[id];
  };
  const counts = { termFocus: 0, frameBlur: 0, inputs: [] };
  const textarea = { tagName: 'TEXTAREA' };
  const frame = { tagName: 'IFRAME', blur() { counts.frameBlur += 1; document.activeElement = document.body; } };
  const docListeners = {};
  const winListeners = {};
  const document = {
    body: { tagName: 'BODY' },
    activeElement: frame,
    getElementById: el,
    createElement: () => el(`x${Math.random()}`),
    addEventListener: (type, fn) => { docListeners[type] = fn; },
  };
  const store = { smith_terminal_agent: 'shell' };
  const window = {
    confirm: () => true,
    addEventListener: (type, fn) => { winListeners[type] = fn; },
    phaseRuns: { anyRunning: () => false },
    Terminal: class {
      constructor() { this.cols = 80; this.rows = 3; this.buffer = { active: { viewportY: 0, getLine: () => ({ translateToString: () => '' }) } }; }
      loadAddon() {} open() {} onData() {} onResize() {} write() {} clear() {} reset() {}
      focus() { counts.termFocus += 1; document.activeElement = textarea; }
    },
  };
  const fetch = async (path, opts = {}) => {
    const method = opts.method || 'GET';
    let data = {};
    if (path === '/api/terminal/agents') {
      data = { enabled: true, authorized: true, default: 'shell', quick: {},
        agents: ['claude', 'shell'].map((id) => ({ id, label: id, available: true })) };
    } else if (path === '/api/terminal/sessions' && method === 'POST') {
      data = { id: 's1' };
    } else if (path.endsWith('/input')) {
      const body = JSON.parse(opts.body);
      if ('data' in body) counts.inputs.push(body.data);
    }
    return { ok: true, status: 200, json: async () => data };
  };
  class EventSource { addEventListener() {} close() {} }
  const sandbox = {
    window, document, fetch, EventSource, setTimeout, clearTimeout, Date, JSON, Promise, Error, RegExp,
    ResizeObserver: class { observe() {} },
    localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; }, removeItem: (k) => { delete store[k]; } },
  };
  vm.runInNewContext(CLI, sandbox);
  docListeners.DOMContentLoaded();
  return { window, document, frame, textarea, counts, winListeners };
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('opening the CLI assistant blurs the Caztor frame and focuses the terminal', async () => {
  const h = cliHarness();
  assert.equal(h.document.activeElement, h.frame);
  h.window.openCliConsole();
  // The keyboard leaves the frame at once, before the terminal exists (it is built once the agents load).
  assert.equal(h.counts.frameBlur, 1, 'the frame gives the keyboard up at once');
  assert.notEqual(h.document.activeElement, h.frame);
  await wait(250);
  assert.ok(h.counts.termFocus >= 1, 'the terminal takes it once built');
  assert.equal(h.document.activeElement, h.textarea);
});

test('a frame grabbing the keyboard right after the window opens gives it back', async () => {
  const h = cliHarness();
  h.window.openCliConsole();
  await wait(250);
  // Caztor's editor takes focus (the page sees a window blur, and the frame as its active element).
  h.document.activeElement = h.frame;
  h.winListeners.blur();
  await wait(10);
  assert.equal(h.document.activeElement, h.textarea);
  assert.equal(h.counts.frameBlur, 2);
});

test('switching to another application does not pull the keyboard back', async () => {
  const h = cliHarness();
  h.window.openCliConsole();
  await wait(250);
  const before = h.counts.termFocus;
  h.winListeners.blur(); // activeElement stays the terminal: the focus left the page
  await wait(10);
  assert.equal(h.counts.termFocus, before);
});

test('a command typed into the CLI keeps reaching the session and takes the keyboard from the frame', async () => {
  const h = cliHarness();
  const sent = await h.window.sendToCli('ls', true);
  assert.equal(sent, true);
  await wait(250);
  assert.deepEqual(h.counts.inputs, ['ls', '\r']);
  assert.ok(h.counts.frameBlur >= 1);
  assert.equal(h.document.activeElement, h.textarea);
  // The claim ends: a later blur toward a frame the operator clicked is left alone.
  h.window.smithTerminalFocus();
  h.document.activeElement = h.frame;
  await wait(1600);
  h.winListeners.blur();
  await wait(10);
  assert.equal(h.document.activeElement, h.frame);
});

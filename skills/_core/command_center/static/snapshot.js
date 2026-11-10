/* Read-only snapshot mode of the Paper Command Center.
 *
 * `smith ui --export-snapshot <dir>` (static_export.py) writes every read-only
 * answer the dashboard needs as a file and inlines its index,
 * window.PAPERSMITH_SNAPSHOT_MANIFEST, before this script. Without that
 * manifest -- the live dashboard -- this file returns at once and changes
 * nothing.
 *
 * In a snapshot it:
 *   - answers same-origin /api/ GETs made through fetch() from the manifest,
 *     and every other method with 403 {ok:false, error:"STATIC_SNAPSHOT"};
 *   - maps /api/ URLs given to iframes, images and links (property setters,
 *     setAttribute and innerHTML) to their files, keeping the original URL in
 *     data-ps-src, which iframe.src then reports, so the page's own path
 *     checks keep working; root-absolute paths become relative, so the site
 *     works under /<repo>/ on GitHub Pages;
 *   - makes sendToCli, phase runs and the other launchers no-ops, hides every
 *     control that runs something (HIDDEN_CONTROLS), and the AI History tab
 *     when the export left it out (--no-ai-history), and shows a banner.
 *
 * Public surface (snapshot only): window.psRewrite(url), window.psApiPath(pathname).
 * The request key is static_export.request_key: the path, then the sorted
 * query without v, t and fresh, `lang` only when not English, and
 * /api/artifact's `file` named `path`.
 */
(function () {
  'use strict';

  const manifest = window.PAPERSMITH_SNAPSHOT_MANIFEST;
  if (!manifest || typeof manifest !== 'object' || !manifest.entries) return;

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const info = window.PAPERSMITH_STATIC || {};
  const entries = manifest.entries;
  const DROPPED = ['v', 't', 'fresh'];
  const MISSING_PAGE = 'snapshot/missing.html';
  const ORIGINAL = 'data-ps-src';
  const language = () => (window.i18n ? window.i18n.getLanguage() : 'en');

  // Every control that would run, write or launch something. One place.
  const HIDDEN_CONTROLS = [
    '#smithAssistantFab', '#smithTerminalWindow', '#btnLaunchExternalTerm',
    '[onclick^="triggerRunPhase"]', '[data-phase-action]', '[data-phase-agent]',
    '[data-action-override]', '[data-kw-help]', '[data-run-verify]', '[data-run-terminal]',
    '[data-run-stop]', '[data-cli]', '[onclick*="sendToCli"]', '[data-exp-cli]', '[data-exp-step]',
    '[data-model-step]', '[data-novelty-judge]', '[onclick*="sendNoveltyDecision"]',
    '[onclick*="launchNoveltyJudge"]', '[onclick*="rebuildAtlasManuscript"]',
    '[onclick*="rebuildManuscriptGraph"]', '#btnBuildGraph', '[data-diagram-validate]',
    '[data-diagram-override]', '[data-xtutor-deliberate]', '#tutorPanel', '#xtutorFold',
    '#btnAuditAi', '#btnComment', '#btnStrikethrough', '#btnHumanize', '#btnAuditSelectionAi',
    '#btnClearAllAnnots', '#btnExecuteChanges', '#btnTopbarUnmark', '#dropBtnUnmarkSelected',
    '#btnUnmarkComments', '#btnUnmarkStrikes', '#btnUnmarkHumanize', '#btnUnmarkSelected',
    '[data-jp-action]:not([data-jp-action="pdf"])', '.journals-sjr label',
    '[data-exp-fold="infrastructure"]', '[data-atlas-complete]', '.badge--live',
    '.phase-action__input', '.phase-action__agent', '.phase-action__foot', '.kw-help',
    '[onclick="navigateTab(\'doctor\')"]', '#keysCard', '[data-keys-prompt]', '[data-keys-terminal]',
  ];
  // The AI History tab is in the snapshot unless it was exported with --no-ai-history.
  if (!entries['/api/ai-history']) HIDDEN_CONTROLS.push('[onclick="navigateTab(\'historia\')"]');

  // Global launchers defined by the page and its panels.
  const LAUNCHERS = ['triggerRunPhase', 'triggerBuildAtlas', 'sendNoveltyDecision', 'launchNoveltyJudge',
    'rebuildAtlasManuscript', 'rebuildManuscriptGraph', 'openCliConsole', 'toggleSmithTerminal'];

  // ---------------------------------------------------------------- keys
  function parseApi(url) {
    if (typeof url !== 'string' || !url) return null;
    let parsed;
    try {
      parsed = new URL(url, window.location.href);
    } catch (_) {
      return null;
    }
    if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/')) return null;
    const params = {};
    parsed.searchParams.forEach((value, name) => {
      if (DROPPED.includes(name) || (name === 'lang' && value === 'en')) return;
      params[parsed.pathname === '/api/artifact' && name === 'file' ? 'path' : name] = value;
    });
    return { path: parsed.pathname, params };
  }

  function keyOf(path, params) {
    const names = Object.keys(params).sort();
    if (!names.length) return path;
    return `${path}?${names.map((n) => `${encodeURIComponent(n)}=${encodeURIComponent(params[n])}`).join('&')}`;
  }

  // The entry for a request: in the active language first (as i18n.js adds
  // ?lang= to fetch()), then the English answer.
  function lookup(api) {
    const lang = language();
    if (!('lang' in api.params) && lang !== 'en') {
      const localized = entries[keyOf(api.path, Object.assign({}, api.params, { lang }))];
      if (localized) return localized;
    }
    return entries[keyOf(api.path, api.params)] || null;
  }

  function psRewrite(url) {
    if (typeof url !== 'string') return url;
    const api = parseApi(url);
    if (api) {
      const entry = lookup(api);
      return entry ? entry.file : MISSING_PAGE;
    }
    if (url.length > 1 && url[0] === '/' && url[1] !== '/') return url.slice(1);
    return url;
  }

  let reverse = null;
  function psApiPath(pathname) {
    if (!reverse) {
      reverse = new Map();
      Object.keys(entries).forEach((key) => {
        try {
          const file = new URL(entries[key].file, window.location.href).pathname;
          if (!reverse.has(file)) reverse.set(file, key.split('?')[0]);
        } catch (_) { /* a malformed entry maps nothing */ }
      });
    }
    return reverse.get(pathname) || pathname;
  }

  window.psRewrite = psRewrite;
  window.psApiPath = psApiPath;

  // ---------------------------------------------------------------- fetch
  const baseFetch = window.fetch.bind(window);
  const jsonResponse = (status, body) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  });

  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || String(input);
    const api = parseApi(url);
    if (!api) return baseFetch(input, init);
    const method = String((init && init.method) || (input && typeof input === 'object' && input.method) || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      return jsonResponse(403, { ok: false, error: 'STATIC_SNAPSHOT', message: t('static.refused') });
    }
    const entry = lookup(api);
    if (!entry) return jsonResponse(404, { ok: false, error: 'NOT_IN_SNAPSHOT', detail: t('static.missing') });
    const answer = await baseFetch(entry.file);
    if (!answer.ok) return jsonResponse(404, { ok: false, error: 'NOT_IN_SNAPSHOT', detail: t('static.missing') });
    const status = entry.status || 200;
    const body = [204, 205, 304].includes(status) ? null : await answer.arrayBuffer();
    return new Response(body, { status, headers: { 'Content-Type': entry.type || 'application/octet-stream' } });
  };

  // ---------------------------------------------------------------- URLs
  const nativeSetAttribute = Element.prototype.setAttribute;
  const nativeGetAttribute = Element.prototype.getAttribute;
  const nativeRemoveAttribute = Element.prototype.removeAttribute;

  function mapped(element, value) {
    const text = String(value);
    const rewritten = psRewrite(text);
    if (rewritten !== text) nativeSetAttribute.call(element, ORIGINAL, text);
    else nativeRemoveAttribute.call(element, ORIGINAL);
    return rewritten;
  }

  function patchProperty(proto, prop, reportOriginal) {
    const native = proto && Object.getOwnPropertyDescriptor(proto, prop);
    if (!native || !native.set || !native.get) return;
    Object.defineProperty(proto, prop, {
      configurable: true,
      enumerable: native.enumerable,
      get() {
        const original = reportOriginal ? nativeGetAttribute.call(this, ORIGINAL) : null;
        if (original) {
          try { return new URL(original, window.location.href).href; } catch (_) { /* fall through */ }
        }
        return native.get.call(this);
      },
      set(value) { native.set.call(this, mapped(this, value)); },
    });
  }

  patchProperty(window.HTMLIFrameElement && HTMLIFrameElement.prototype, 'src', true);
  patchProperty(window.HTMLImageElement && HTMLImageElement.prototype, 'src', false);
  patchProperty(window.HTMLAnchorElement && HTMLAnchorElement.prototype, 'href', false);

  Element.prototype.setAttribute = function setAttribute(name, value) {
    const attr = String(name).toLowerCase();
    if (attr === 'src' || attr === 'href') return nativeSetAttribute.call(this, name, mapped(this, value));
    return nativeSetAttribute.call(this, name, value);
  };

  // Panels draw links and images as HTML strings.
  const HTML_URL = /(\s(?:src|href)\s*=\s*)(["'])(\/(?!\/)[^"']*)\2/gi;
  function rewriteHtml(html) {
    return String(html).replace(HTML_URL, (match, prefix, quote, url) => {
      const rewritten = psRewrite(url.replace(/&amp;/g, '&'));
      return rewritten === url ? match : `${prefix}${quote}${rewritten}${quote} ${ORIGINAL}=${quote}${url}${quote}`;
    });
  }

  const innerHtml = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
  if (innerHtml && innerHtml.set) {
    Object.defineProperty(Element.prototype, 'innerHTML', {
      configurable: true,
      enumerable: innerHtml.enumerable,
      get() { return innerHtml.get.call(this); },
      set(value) { innerHtml.set.call(this, rewriteHtml(value)); },
    });
  }
  const insertAdjacent = Element.prototype.insertAdjacentHTML;
  Element.prototype.insertAdjacentHTML = function insertAdjacentHTML(position, html) {
    return insertAdjacent.call(this, position, rewriteHtml(html));
  };

  // ---------------------------------------------------------------- launchers
  window.sendToCli = () => false;
  window.openCliConsole = () => false;
  window.toggleSmithTerminal = () => false;

  function neutralize() {
    LAUNCHERS.forEach((name) => {
      if (typeof window[name] === 'function') window[name] = () => false;
    });
    window.sendToCli = () => false;
    if (window.phaseRuns) window.phaseRuns.start = () => null;
  }

  // ---------------------------------------------------------------- banner
  function bannerText() {
    const date = String(info.generated || manifest.generated || '').slice(0, 10);
    return t('static.banner', { workspace: info.workspace || manifest.workspace || '', date });
  }

  function decorate() {
    neutralize();
    document.body.classList.add('ps-static');
    const style = document.createElement('style');
    style.id = 'psStaticStyle';
    style.textContent = `${HIDDEN_CONTROLS.map((selector) => `body.ps-static ${selector}`).join(',\n')} { display: none !important; }
body.ps-static .ps-static-banner { position: sticky; top: 0; z-index: 1000; padding: 0.45rem 1rem;
  background: var(--accent, #38bdf8); color: #fff; font-size: 0.85rem; text-align: center; }`;
    document.head.appendChild(style);
    const banner = document.createElement('div');
    banner.className = 'ps-static-banner';
    banner.id = 'psStaticBanner';
    banner.setAttribute('role', 'note');
    banner.textContent = bannerText();
    document.body.insertBefore(banner, document.body.firstChild);
    document.addEventListener('languagechange', () => { banner.textContent = bannerText(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', decorate);
  else decorate();
  // Panel scripts that define launchers on `load` are covered too.
  window.addEventListener('load', neutralize);
})();

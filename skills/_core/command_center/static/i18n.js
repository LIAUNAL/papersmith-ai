// Dashboard language runtime: English by default, Spanish on request.
//
// The catalogues live in ./i18n/en.js and ./i18n/es.js; each registers
// window.PAPERSMITH_I18N.<lang> as a flat { key: text } object and must load
// before this file. The public surface is:
//
//   t(key, vars)        the text of `key` in the active language; `{name}`
//                       placeholders are filled from `vars`. A key missing from
//                       the active catalogue falls back to English, then to
//                       the key itself, never to an empty string.
//   setLanguage(lang)   'en' or 'es': persists the choice in localStorage,
//                       sets <html lang>, re-applies the static markup and
//                       dispatches a 'languagechange' CustomEvent on document
//                       (detail: { lang }) so each panel re-renders itself.
//   getLanguage()       the active language.
//   i18n.has(key)       whether the catalogues know `key` (for token labels
//                       that fall back to the token itself).
//   applyTranslations(root)
//                       re-applies the markup under `root` (default document).
//
// Static markup opts in with data-i18n="key" (text), data-i18n-html="key"
// (catalogue HTML; trusted, shipped with the dashboard) and
// data-i18n-attr="title:key;placeholder:key;aria-label:key". An element is
// rewritten only while it still shows a catalogue text for its key, so a value
// a panel script has written since (a run id, a count) is never overwritten.
//
// Same-origin /api/ requests made through fetch() carry ?lang=<lang> when the
// language is not English; the server then localizes its display labels
// (command_center/localize.py). English requests are sent unchanged.
(function () {
  'use strict';

  const STORAGE_KEY = 'papersmith-lang';
  const SUPPORTED = ['en', 'es'];
  const DEFAULT_LANGUAGE = 'en';
  const catalogues = window.PAPERSMITH_I18N || (window.PAPERSMITH_I18N = {});

  function readSaved() {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      return SUPPORTED.includes(saved) ? saved : DEFAULT_LANGUAGE;
    } catch (_) {
      return DEFAULT_LANGUAGE;
    }
  }

  let current = readSaved();

  function has(table, key) {
    return !!table && Object.prototype.hasOwnProperty.call(table, key);
  }

  function format(text, vars) {
    if (!vars) return text;
    return text.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (match, name) =>
      (has(vars, name) && vars[name] !== undefined && vars[name] !== null ? String(vars[name]) : match));
  }

  function t(key, vars) {
    const active = catalogues[current];
    const english = catalogues[DEFAULT_LANGUAGE];
    let text = has(active, key) ? active[key] : (has(english, key) ? english[key] : '');
    if (!text) text = has(english, key) && english[key] ? english[key] : String(key);
    return format(text, vars);
  }

  function getLanguage() {
    return current;
  }

  // Whether `key` has a text in English (the catalogue every key is in).
  function hasKey(key) {
    return has(catalogues[DEFAULT_LANGUAGE], key);
  }

  const normalize = (text) => String(text == null ? '' : text).replace(/\s+/g, ' ').trim();

  // True while `shown` is the text of `key` in some catalogue: the element
  // still holds what this runtime (or the shipped markup) put there.
  function showsCatalogueText(key, shown) {
    const value = normalize(shown);
    return SUPPORTED.some((lang) => has(catalogues[lang], key) && normalize(catalogues[lang][key]) === value);
  }

  // Panel scripts also run under bare DOM stubs (the node render tests).
  const canQuery = (scope) => !!scope && typeof scope.querySelectorAll === 'function';

  function applyTranslations(root) {
    const scope = root || document;
    if (!canQuery(scope)) return;
    scope.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (showsCatalogueText(key, el.textContent)) el.textContent = t(key);
    });
    scope.querySelectorAll('[data-i18n-html]').forEach((el) => {
      const key = el.getAttribute('data-i18n-html');
      if (showsCatalogueText(key, el.innerHTML)) el.innerHTML = t(key);
    });
    scope.querySelectorAll('[data-i18n-attr]').forEach((el) => {
      el.getAttribute('data-i18n-attr').split(';').forEach((pair) => {
        const at = pair.indexOf(':');
        if (at < 1) return;
        const attr = pair.slice(0, at).trim();
        const key = pair.slice(at + 1).trim();
        if (!el.hasAttribute(attr) || showsCatalogueText(key, el.getAttribute(attr))) el.setAttribute(attr, t(key));
      });
    });
  }

  function syncSelectors() {
    if (!canQuery(document)) return;
    document.querySelectorAll('[data-lang-select]').forEach((select) => {
      if (select.value !== current) select.value = current;
    });
  }

  function setLanguage(lang) {
    const next = SUPPORTED.includes(lang) ? lang : DEFAULT_LANGUAGE;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch (_) { /* private mode: the choice lasts for this page only */ }
    const changed = next !== current;
    current = next;
    if (document.documentElement) document.documentElement.lang = next;
    applyTranslations(document);
    syncSelectors();
    if (changed && typeof document.dispatchEvent === 'function') document.dispatchEvent(new CustomEvent('languagechange', { detail: { lang: next } }));
    return next;
  }

  // Same-origin /api/ URLs get ?lang=<lang> unless they already name one.
  function withLanguage(url) {
    if (current === DEFAULT_LANGUAGE || typeof url !== 'string') return url;
    let parsed;
    try {
      parsed = new URL(url, window.location.href);
    } catch (_) {
      return url;
    }
    if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/')) return url;
    if (parsed.searchParams.has('lang')) return url;
    parsed.searchParams.set('lang', current);
    return parsed.pathname + parsed.search + parsed.hash;
  }

  if (typeof window.fetch === 'function') {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => nativeFetch(typeof input === 'string' ? withLanguage(input) : input, init);
  }

  if (document.documentElement) document.documentElement.lang = current;

  function bindSelectors() {
    if (!canQuery(document)) return;
    document.querySelectorAll('[data-lang-select]').forEach((select) => {
      if (select.dataset.langBound) return;
      select.dataset.langBound = '1';
      select.value = current;
      select.addEventListener('change', () => setLanguage(select.value));
    });
  }

  function start() {
    applyTranslations(document);
    bindSelectors();
  }

  if (document.readyState === 'loading' && typeof document.addEventListener === 'function') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  window.t = t;
  window.i18n = { t, has: hasKey, setLanguage, getLanguage, applyTranslations, withLanguage, SUPPORTED: SUPPORTED.slice() };
})();

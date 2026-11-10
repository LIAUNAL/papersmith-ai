/* API keys panel (Doctor tab): where the dashboard asks for the Asta and
 * OpenAlex keys.
 *
 * GET /api/terminal/keys answers each provider's status — configured or not,
 * stored or exported, never the key. PUT /api/terminal/keys/<provider> stores
 * one ({"value", "verify"}), DELETE removes it, POST .../verify checks the
 * configured one. The routes sit behind the support terminal's cookie and
 * guards (loopback bind, same origin); where they answer 403/404 the panel says
 * to run `smith keys set <provider>` in a terminal instead.
 *
 * A key typed here is read once from its password input, which is cleared
 * before the request leaves; it is never kept in a variable, localStorage or
 * the DOM, and no answer carries it back.
 *
 * Elsewhere in the page, an empty <div data-keys-prompt="asta|openalex" hidden>
 * becomes a short "add your key" prompt while that key is missing (the Phase 2
 * plausibility card asks for Asta, the journals panel for OpenAlex); a prompt
 * dismissed once stays dismissed in this browser (only that flag is stored).
 *
 * Public surface (window): refreshKeysPanel(),
 * KeysPanel.{render, fillPrompts, status, save, remove, verify, isUnavailable}.
 */
(function () {
  'use strict';

  // A read-only snapshot has no server to hold a key: nothing to render.
  if (window.PAPERSMITH_SNAPSHOT_MANIFEST) return;

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
  const HEADERS = { 'Content-Type': 'application/json', 'X-Papersmith-Terminal': '1' };
  const KEYS_URL = '/api/terminal/keys';
  const DISMISS_PREFIX = 'papersmith-keys-dismissed:';

  // Fixed maps, so every catalogue key is a literal the i18n test can see.
  const NAME = { asta: 'keys.provider.asta.name', openalex: 'keys.provider.openalex.name' };
  const ROLE = { asta: 'keys.provider.asta.role', openalex: 'keys.provider.openalex.role' };
  const PROMPT = { asta: 'keys.prompt.asta', openalex: 'keys.prompt.openalex' };
  const VERIFY = {
    ok: 'keys.verify.ok', refused: 'keys.verify.refused',
    unreachable: 'keys.verify.unreachable', unconfigured: 'keys.verify.unconfigured',
  };
  const ERRORS = {
    EMPTY: 'keys.error.EMPTY', TOO_SHORT: 'keys.error.TOO_SHORT', TOO_LONG: 'keys.error.TOO_LONG',
    BAD_CHARACTERS: 'keys.error.BAD_CHARACTERS',
  };

  let last = null; // the last GET payload: statuses only
  let unavailable = false;

  const nameOf = (provider) => (NAME[provider] ? t(NAME[provider]) : provider);

  function stateBadge(state) {
    if (state.source === 'env') {
      const text = state.shadowed ? t('keys.state.shadowed', { env: state.env }) : t('keys.state.env', { env: state.env });
      return `<span class="badge badge--ok">${esc(text)}</span>`;
    }
    if (state.source === 'store') return `<span class="badge badge--ok">${esc(t('keys.state.store'))}</span>`;
    if (state.problem) {
      return `<span class="badge badge--warn">${esc(t('keys.state.insecure', { problem: state.problem }))}</span>`;
    }
    return `<span class="badge badge--absent">${esc(t('keys.state.none'))}</span>`;
  }

  function providerHtml(state) {
    const p = esc(state.provider);
    const name = nameOf(state.provider);
    const license = state.provider === 'asta'
      ? `<p class="keys-license">${esc(t('keys.asta.license'))}`
        + (state.license_url ? ` <a href="${esc(state.license_url)}" target="_blank" rel="noopener noreferrer">${esc(t('keys.license'))}</a>` : '')
        + '</p>'
      : '';
    const request = state.request_url
      ? `<a class="btn btn--sm" href="${esc(state.request_url)}" target="_blank" rel="noopener noreferrer">${esc(t('keys.request'))}</a>`
      : '';
    const mcp = (state.provider === 'asta' && last && last.asta_mcp) ? last.asta_mcp : null;
    const registered = mcp
      ? `<p class="panel__meta">${esc(mcp.registered && mcp.registered.length
        ? t('keys.asta.mcp', { files: mcp.registered.join(', ') }) : t('keys.asta.mcpNone'))}</p>`
      : '';
    const outside = state.source === 'store'
      ? `<details class="keys-outside"><summary>${esc(t('keys.outsideTitle'))}</summary>`
        + `<p>${esc(t('keys.outsideText'))}</p><code>${esc(state.export_command)}</code></details>`
      : '';
    return `<div class="keys-provider" data-keys-provider="${p}">
        <div class="keys-provider__head"><strong>${esc(name)}</strong> ${stateBadge(state)}</div>
        <p class="keys-provider__role">${esc(ROLE[state.provider] ? t(ROLE[state.provider]) : '')}</p>
        ${registered}
        ${license}
        <form class="keys-form" data-keys-form="${p}" autocomplete="off">
          <label class="keys-form__label" for="keysInput-${p}">${esc(t('keys.input.label', { name }))}</label>
          <input id="keysInput-${p}" type="password" autocomplete="off" spellcheck="false"
            autocapitalize="off" maxlength="512" placeholder="${esc(t('keys.input.placeholder'))}">
          <div class="keys-form__buttons">
            <button type="submit" class="btn btn--primary btn--sm" data-keys-save="${p}">${esc(t('keys.save'))}</button>
            <button type="button" class="btn btn--sm" data-keys-save-verify="${p}">${esc(t('keys.saveVerify'))}</button>
            <button type="button" class="btn btn--sm" data-keys-verify="${p}"${state.configured ? '' : ' disabled'}>${esc(t('keys.verify'))}</button>
            <button type="button" class="btn btn--sm" data-keys-remove="${p}"${state.stored || state.problem ? '' : ' disabled'}>${esc(t('keys.remove'))}</button>
            <button type="button" class="btn btn--sm" data-keys-terminal="${p}">${esc(t('keys.terminal'))}</button>
            ${request}
          </div>
        </form>
        <div class="keys-result" id="keysResult-${p}" role="status" aria-live="polite"></div>
        ${outside}
      </div>`;
  }

  function unavailableHtml() {
    return `<div class="keys-unavailable">${t('keys.unavailableHtml')}</div>`;
  }

  function render(payload) {
    const host = document.getElementById('keysPanel');
    if (!host) return;
    if (!payload || !Array.isArray(payload.keys)) {
      host.innerHTML = unavailableHtml();
      return;
    }
    const sessions = payload.sessions_open > 0
      ? `<p class="panel__meta">${esc(t('keys.sessionsOpen', { n: payload.sessions_open }))}</p>` : '';
    host.innerHTML = payload.keys.map(providerHtml).join('') + sessions;
    bind(host);
  }

  function result(provider, text, kind) {
    const box = document.getElementById(`keysResult-${provider}`);
    if (!box) return;
    box.textContent = text;
    box.className = `keys-result keys-result--${kind || 'info'}`;
  }

  function verifyText(check) {
    if (!check) return '';
    const key = VERIFY[check.state] || 'keys.verify.unreachable';
    let text = t(key, { detail: check.detail || '' });
    const budget = check.budget || {};
    if (budget.remaining_usd) text += ` ${t('keys.verify.budget', { remaining: budget.remaining_usd, limit: budget.limit_usd || '?' })}`;
    return text;
  }

  async function request(method, path, payload) {
    const options = { method, headers: HEADERS, credentials: 'same-origin', cache: 'no-store' };
    if (payload !== undefined) options.body = JSON.stringify(payload);
    const response = await fetch(path, options);
    let body = null;
    try { body = await response.json(); } catch (_) { body = null; }
    return { status: response.status, body: body || {} };
  }

  function errorText(answer) {
    const body = answer.body || {};
    if (answer.status === 403 || answer.status === 404) return t('keys.error.forbidden');
    if (body.error === 'KEY_INVALID' && ERRORS[body.reason]) return t(ERRORS[body.reason]);
    if (body.error === 'KEY_REFUSED' || body.error === 'VERIFY_UNREACHABLE') return verifyText(body.verify);
    return t('keys.error.failed', { status: answer.status });
  }

  async function save(provider, verify) {
    const input = document.getElementById(`keysInput-${provider}`);
    if (!input) return;
    // Read once, clear at once: the value lives only in this call's payload.
    const payload = { value: input.value, verify: Boolean(verify) };
    input.value = '';
    if (!payload.value.trim()) { result(provider, t('keys.error.EMPTY'), 'warn'); return; }
    result(provider, t('keys.saving'), 'info');
    let answer;
    try {
      answer = await request('PUT', `${KEYS_URL}/${encodeURIComponent(provider)}`, payload);
    } catch (_) {
      result(provider, t('keys.error.failed', { status: 0 }), 'bad');
      return;
    }
    payload.value = '';
    if (answer.status !== 200) { result(provider, errorText(answer), 'bad'); return; }
    const body = answer.body;
    await refreshKeysPanel();
    const env = (body.status && body.status.env) || '';
    let text = t('keys.saved', { env });
    if (body.verify) text = `${verifyText(body.verify)} ${text}`;
    if (body.sessions_open > 0) text += ` ${t('keys.sessionsOpen', { n: body.sessions_open })}`;
    result(provider, text, 'ok');
    window.refreshDoctorPanel?.(true);
  }

  async function removeKey(provider) {
    if (!window.confirm(t('keys.removeConfirm', { name: nameOf(provider) }))) return;
    let answer;
    try {
      answer = await request('DELETE', `${KEYS_URL}/${encodeURIComponent(provider)}`, {});
    } catch (_) {
      result(provider, t('keys.error.failed', { status: 0 }), 'bad');
      return;
    }
    if (answer.status !== 200) { result(provider, errorText(answer), 'bad'); return; }
    await refreshKeysPanel();
    result(provider, t(answer.body.removed ? 'keys.removed' : 'keys.nothingRemoved'), 'ok');
    window.refreshDoctorPanel?.(true);
  }

  async function verifyKey(provider) {
    result(provider, t('keys.verifying'), 'info');
    let answer;
    try {
      answer = await request('POST', `${KEYS_URL}/${encodeURIComponent(provider)}/verify`, {});
    } catch (_) {
      result(provider, t('keys.error.failed', { status: 0 }), 'bad');
      return;
    }
    if (answer.status !== 200) { result(provider, errorText(answer), 'bad'); return; }
    const check = answer.body.verify || {};
    result(provider, verifyText(check), check.state === 'ok' ? 'ok' : 'bad');
  }

  function bind(host) {
    host.querySelectorAll('[data-keys-form]').forEach((form) => {
      form.addEventListener('submit', (event) => { event.preventDefault(); save(form.dataset.keysForm, false); });
    });
    host.querySelectorAll('[data-keys-save-verify]').forEach((b) => b.addEventListener('click', () => save(b.dataset.keysSaveVerify, true)));
    host.querySelectorAll('[data-keys-verify]').forEach((b) => b.addEventListener('click', () => verifyKey(b.dataset.keysVerify)));
    host.querySelectorAll('[data-keys-remove]').forEach((b) => b.addEventListener('click', () => removeKey(b.dataset.keysRemove)));
    host.querySelectorAll('[data-keys-terminal]').forEach((b) => b.addEventListener('click', () => {
      // `--stdin` is never typed for the person: the hidden prompt asks in the shell.
      if (typeof window.sendToCli === 'function') window.sendToCli(`smith keys set ${b.dataset.keysTerminal}`, true, { kind: 'shell' });
    }));
  }

  // ---- prompts elsewhere in the page -----------------------------------
  const dismissed = (provider) => { try { return localStorage.getItem(DISMISS_PREFIX + provider) === '1'; } catch (_) { return false; } };
  const dismiss = (provider) => { try { localStorage.setItem(DISMISS_PREFIX + provider, '1'); } catch (_) { /* blocked */ } };

  function status(provider) {
    if (!last || !Array.isArray(last.keys)) return null;
    return last.keys.find((s) => s.provider === provider) || null;
  }

  function fillPrompts() {
    document.querySelectorAll('[data-keys-prompt]').forEach((box) => {
      const provider = box.dataset.keysPrompt;
      const state = status(provider);
      if (!state || state.configured || dismissed(provider) || !PROMPT[provider]) {
        box.hidden = true;
        box.innerHTML = '';
        return;
      }
      box.innerHTML = `<span>${esc(t(PROMPT[provider]))}</span> `
        + `<button type="button" class="btn btn--sm" data-keys-open="${esc(provider)}">${esc(t('keys.prompt.open'))}</button> `
        + `<button type="button" class="btn btn--sm" data-keys-dismiss="${esc(provider)}">${esc(t('keys.prompt.dismiss'))}</button>`;
      box.hidden = false;
      box.querySelectorAll('[data-keys-open]').forEach((b) => b.addEventListener('click', () => {
        if (typeof window.navigateTab === 'function') window.navigateTab('doctor');
        setTimeout(() => document.getElementById(`keysInput-${provider}`)?.focus(), 50);
      }));
      box.querySelectorAll('[data-keys-dismiss]').forEach((b) => b.addEventListener('click', () => {
        dismiss(provider);
        fillPrompts();
      }));
    });
  }

  async function refreshKeysPanel() {
    let answer;
    try {
      answer = await request('GET', KEYS_URL);
    } catch (_) {
      answer = { status: 0, body: {} };
    }
    if (answer.status === 200) {
      last = answer.body;
      unavailable = false;
      render(last);
    } else {
      last = null;
      unavailable = true;
      render(null);
    }
    fillPrompts();
    return last;
  }

  // Panels re-render their HTML; fill any prompt placeholder they add.
  let pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    setTimeout(() => { pending = false; if (last) fillPrompts(); }, 0);
  }
  if (typeof MutationObserver === 'function' && document.body) {
    new MutationObserver((records) => {
      if (records.some((r) => [...r.addedNodes].some((n) => n.nodeType === 1
        && (n.matches?.('[data-keys-prompt]') || n.querySelector?.('[data-keys-prompt]'))))) schedule();
    }).observe(document.body, { childList: true, subtree: true });
  }

  window.KeysPanel = { render, fillPrompts, status, save, remove: removeKey, verify: verifyKey,
    isUnavailable: () => unavailable };
  window.refreshKeysPanel = refreshKeysPanel;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { refreshKeysPanel(); });
  } else {
    refreshKeysPanel();
  }
})();

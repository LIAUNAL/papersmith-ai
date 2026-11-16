// Manuscript version selector of the PDF Preview tab: the English manuscript
// (canonical) or its Spanish translation under paper/translations/es/.
// The Spanish option reads `GET /api/translations?lang=es`, compiles with
// `POST /api/paper/compile?translation=es`, previews `/api/pdf?translation=es`
// (index.html's setPdfTranslation) and audits with
// `POST /api/pdf/ai-audit?translation=es`. The English preview is the default
// and stays as it was; every label comes from the i18n catalogue.
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
  const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});
  const list = (v) => (Array.isArray(v) ? v : []);
  const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
  const num = (v, digits) => (isNum(v) ? (digits === undefined ? String(v) : v.toFixed(digits)) : '—');
  const LANG = 'es';
  const AGENT_COMMAND = '/paper-writing translate es';
  const VERDICTS = { clear: 'badge--ok', uneven: 'badge--warn', needs_revision: 'badge--bad' };

  const state = { version: 'en', status: null, error: null, audit: null, auditError: null,
    busy: {}, message: null, previewing: false };

  function host() {
    return typeof document !== 'undefined' ? document.getElementById('translationPanel') : null;
  }

  function verdictBadge(verdict) {
    const key = String(verdict ?? '');
    const label = Object.prototype.hasOwnProperty.call(VERDICTS, key) ? t(`translation.verdict.${key}`) : key;
    return `<span class="badge ${VERDICTS[key] || 'badge--absent'}">${esc(label)}</span>`;
  }

  const command = () => `<code>${esc(AGENT_COMMAND)}</code>`;

  // -- version selector -------------------------------------------------------
  function selectorHtml(s) {
    const option = (value) => `<option value="${value}"${s.version === value ? ' selected' : ''}>`
      + `${esc(t(`translation.version.${value}`))}</option>`;
    return `<label class="translation-version">${esc(t('translation.version'))} `
      + `<select data-tp-field="version">${option('en')}${option('es')}</select></label>`;
  }

  // -- status -------------------------------------------------------------------
  function emptyHtml() {
    return `<div class="journals-msg">${esc(t('translation.empty'))} ${command()}</div>`
      + `<p class="panel__meta">${esc(t('translation.emptyWhy'))}</p>`;
  }

  function statusHtml(s) {
    const status = obj(s.status);
    const counts = obj(status.counts);
    const translated = (isNum(counts.current) ? counts.current : 0) + (isNum(counts.stale) ? counts.stale : 0);
    if (!translated) return emptyHtml();
    const busy = obj(s.busy);
    const parts = [`<div>${esc(t('translation.counts', {
      current: num(counts.current), stale: num(counts.stale), missing: num(counts.missing), total: num(counts.total),
    }))}</div>`];
    // Titles, headings and captions outside the blocks are translated too; they are counted apart.
    const fragments = obj(status.fragment_counts);
    if (isNum(fragments.total) && fragments.total > 0) {
      parts.push(`<div>${esc(t('translation.fragmentCounts', {
        current: num(fragments.current), stale: num(fragments.stale), missing: num(fragments.missing),
        total: num(fragments.total),
      }))}</div>`);
    }
    const badges = [status.built
      ? `<span class="badge badge--ok">${esc(t('translation.built'))}</span>`
      : `<span class="badge badge--absent">${esc(t('translation.notBuiltBadge'))}</span>`];
    badges.push(status.pdf
      ? `<span class="badge badge--ok">${esc(t('translation.pdfReady'))}</span>`
      : `<span class="badge badge--absent">${esc(t('translation.pdfAbsent'))}</span>`);
    const audit = status.audit && typeof status.audit === 'object' ? status.audit : null;
    if (audit) {
      badges.push(`<span class="panel__meta">${esc(t('translation.lastAudit', { index: num(audit.index) }))}</span> `
        + verdictBadge(audit.verdict));
    }
    parts.push(`<div>${badges.join(' ')}</div>`);
    const pending = (c) => (isNum(c.stale) && c.stale > 0) || (isNum(c.missing) && c.missing > 0);
    if (pending(counts) || pending(fragments)) {
      parts.push(`<div class="journals-msg journals-msg--warn">${esc(t('translation.staleHint'))} ${command()}</div>`);
    }
    if (!status.built) {
      parts.push(`<div class="journals-msg">${esc(t('translation.notBuilt'))} ${command()}</div>`);
    } else {
      const button = (action, label, busyLabel, disabled) => `<button class="btn btn--sm" data-tp-action="${action}"`
        + `${disabled ? ' disabled' : ''}>${esc(t(busy[action] ? busyLabel : label))}</button>`;
      parts.push(`<div class="btn-group">`
        + button('compile', 'translation.action.compile', 'translation.action.compiling', busy.compile)
        + button('preview', 'translation.action.preview', 'translation.action.preview', !status.pdf)
        + button('audit', 'translation.action.audit', 'translation.action.auditing', busy.audit)
        + `</div>`);
    }
    if (s.message) parts.push(`<div class="panel__meta">${esc(s.message)}</div>`);
    return parts.join('');
  }

  // -- the Spanish quality audit -------------------------------------------------
  function findingsHtml(findings) {
    const items = list(findings).map((f) => obj(f));
    if (!items.length) return `<span class="panel__meta">${esc(t('translation.noFindings'))}</span>`;
    const rows = items.map((f) => {
      const where = isNum(f.paragraph) && isNum(f.sentence)
        ? ` <span class="panel__meta">${esc(t('translation.finding.where', { paragraph: f.paragraph, sentence: f.sentence }))}</span>` : '';
      return `<li><strong>${esc(f.category)}</strong>: <em>${esc(f.fragment)}</em>${where}`
        + (f.hint ? `<div class="panel__meta">${esc(f.hint)}</div>` : '') + `</li>`;
    }).join('');
    return `<details><summary>${esc(t('translation.findings', { count: items.length }))}</summary><ul>${rows}</ul></details>`;
  }

  function auditHtml(audit) {
    const a = obj(audit);
    const doc = obj(a.document);
    const out = [];
    out.push(`<h5>${esc(t('translation.audit.title'))}</h5>`);
    if (a.notice) out.push(`<p class="panel__meta translation-notice">${esc(a.notice)}</p>`);
    out.push(`<div>${esc(t('translation.audit.index'))} <strong>${esc(num(doc.index))}</strong>/100 ${verdictBadge(doc.verdict)}</div>`);
    out.push(`<div class="panel__meta">${esc(t('translation.score.style', { value: num(doc.style_score, 2) }))} · `
      + `${esc(t('translation.score.flow', { value: num(doc.flow_score, 2) }))} · `
      + `${esc(t('translation.score.redundancy', { value: num(doc.redundancy_score, 2) }))} · `
      + `${esc(t('translation.scoresHint'))}</div>`);
    if (a.generated_at) out.push(`<div class="panel__meta">${esc(t('translation.generated', { date: a.generated_at }))}</div>`);
    const blocks = list(a.blocks).map((b) => obj(b));
    if (blocks.length) {
      const rows = blocks.map((b) => `<tr><td><code>${esc(b.id)}</code></td><td>${esc(num(b.index))}</td>`
        + `<td>${verdictBadge(b.verdict)}</td><td class="panel__meta">${esc(num(b.style_score, 2))} · `
        + `${esc(num(b.flow_score, 2))} · ${esc(num(b.redundancy_score, 2))}</td><td>${findingsHtml(b.findings)}</td></tr>`).join('');
      out.push(`<table class="journals-table"><thead><tr><th>${esc(t('translation.col.block'))}</th>`
        + `<th>${esc(t('translation.col.index'))}</th><th>${esc(t('translation.col.verdict'))}</th>`
        + `<th>${esc(t('translation.col.scores'))}</th><th>${esc(t('translation.col.findings'))}</th></tr></thead>`
        + `<tbody>${rows}</tbody></table>`);
    }
    const cross = list(a.cross_block_redundancy).map((c) => obj(c));
    out.push(`<h5>${esc(t('translation.cross'))}</h5>`);
    out.push(cross.length
      ? `<ul>${cross.map((c) => `<li><em>${esc(c.phrase ?? c.sentence)}</em> `
        + `<span class="panel__meta">${esc(list(c.blocks).join(', '))}</span></li>`).join('')}</ul>`
      : `<div class="panel__meta">${esc(t('translation.crossNone'))}</div>`);
    const fidelity = list(a.fidelity).map((f) => obj(f));
    if (fidelity.length) {
      const rows = fidelity.map((f) => {
        const diffs = list(f.differences);
        const cell = f.ok === true
          ? `<span class="badge badge--ok">${esc(t('translation.fidelityOk'))}</span>`
          : `<span class="badge badge--bad">${esc(t('translation.fidelityDiff', { count: diffs.length }))}</span>`
            + (diffs.length ? `<ul>${diffs.map((d) => `<li>${esc(typeof d === 'string' ? d : JSON.stringify(d))}</li>`).join('')}</ul>` : '');
        return `<tr><td><code>${esc(f.id)}</code></td><td>${cell}</td></tr>`;
      }).join('');
      out.push(`<h5>${esc(t('translation.fidelity'))}</h5><table class="journals-table"><tbody>${rows}</tbody></table>`);
    }
    return `<section class="translation-audit">${out.join('')}</section>`;
  }

  function panelHtml(s) {
    const parts = [selectorHtml(s)];
    if (s.version === LANG) {
      if (s.busy.status && !s.status) parts.push(`<div class="panel__meta">${esc(t('translation.loading'))}</div>`);
      else if (s.error) parts.push(`<div class="journals-msg journals-msg--bad">${esc(s.error)}</div>`);
      else if (s.status) parts.push(statusHtml(s));
      if (s.auditError) parts.push(`<div class="journals-msg journals-msg--bad">${esc(s.auditError)}</div>`);
      else if (s.audit) parts.push(auditHtml(s.audit));
    }
    return `<div class="translation-panel">${parts.join('')}</div>`;
  }

  function render() {
    const el = host();
    if (el) el.innerHTML = panelHtml(state);
  }

  // -- requests -------------------------------------------------------------------
  async function call(url, method) {
    try {
      const response = await fetch(url, method ? { method } : undefined);
      let body = {};
      try { body = await response.json(); } catch (_) { body = {}; }
      return { ok: response.ok, status: response.status, body: obj(body) };
    } catch (error) {
      return { ok: false, status: 0, body: { message: String(error && error.message || error) } };
    }
  }

  const failure = (reply) => reply.body.message || reply.body.detail
    || t('translation.error', { status: reply.status });

  async function refresh() {
    state.busy.status = true;
    render();
    const reply = await call(`/api/translations?lang=${LANG}`);
    state.busy.status = false;
    if (reply.ok) { state.status = reply.body; state.error = null; } else { state.error = failure(reply); }
    render();
  }

  async function compile() {
    state.busy.compile = true;
    render();
    const reply = await call(`/api/paper/compile?translation=${LANG}`, 'POST');
    state.busy.compile = false;
    state.message = reply.ok ? (reply.body.message || '') : failure(reply);
    await refresh();
    if (reply.ok && state.previewing && typeof window.setPdfTranslation === 'function') window.setPdfTranslation(LANG);
  }

  async function audit() {
    state.busy.audit = true;
    render();
    const reply = await call(`/api/pdf/ai-audit?translation=${LANG}`, 'POST');
    state.busy.audit = false;
    if (reply.ok) { state.audit = reply.body; state.auditError = null; } else { state.auditError = failure(reply); }
    render();
  }

  function preview(lang) {
    state.previewing = Boolean(lang);
    if (typeof window.setPdfTranslation === 'function') window.setPdfTranslation(lang);
  }

  // -- events ---------------------------------------------------------------------
  function bind(el) {
    if (el.__tpBound) return;
    el.__tpBound = true;
    el.addEventListener('change', async (event) => {
      const field = event.target && event.target.closest ? event.target.closest('[data-tp-field]') : null;
      if (!field || field.getAttribute('data-tp-field') !== 'version') return;
      state.version = field.value === LANG ? LANG : 'en';
      if (state.version === LANG) {
        await refresh();
      } else {
        if (state.previewing) preview(null);
        render();
      }
    });
    el.addEventListener('click', async (event) => {
      const button = event.target && event.target.closest ? event.target.closest('[data-tp-action]') : null;
      if (!button || button.disabled) return;
      const action = button.getAttribute('data-tp-action');
      if (action === 'compile' && !state.busy.compile) await compile();
      else if (action === 'preview') preview(LANG);
      else if (action === 'audit' && !state.busy.audit) await audit();
    });
  }

  function mount() {
    const el = host();
    if (!el) return;
    bind(el);
    render();
  }

  async function refreshTranslationPanel() {
    if (!host()) return;
    mount();
    if (state.version === LANG) await refresh();
  }

  window.TranslationPanel = { state, mount, panelHtml, statusHtml, auditHtml, emptyHtml };
  window.refreshTranslationPanel = refreshTranslationPanel;
  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('languagechange', () => { if (host()) render(); });
  }
})();

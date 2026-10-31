/* Math panel of the "Concept Map & Model" tab.
 *
 * Renders the paper's own LaTeX (GET /api/model/math) with the vendored KaTeX
 * as calm cards — heading, display equation, one-line "Connection" — under a
 * lema, beside a compact "Idea and novelty" card; and hosts the Socratic tutor
 * (skills/math-tutor): hand-written images are dropped, pasted or picked,
 * uploaded, and each message runs one headless turn of the `math-tutor` agent
 * (POST /api/terminal/tutor/turn) whose structured answer is rendered here.
 *
 * Text that comes back from the model is never inserted as HTML: it is escaped,
 * then a tiny Markdown subset and KaTeX (trust off) are applied. Each formula
 * also keeps its LaTeX source; [data-math-toggle] buttons switch the whole tab
 * between the compiled and the source view (remembered in localStorage).
 *
 * Public surface (window): refreshMathPanel(), mathRichText(text).
 */
(function () {
  'use strict';

  // The dashboard catalogue (i18n.js); a bare key where it is not loaded.
  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const HEADERS = { 'Content-Type': 'application/json', 'X-Papersmith-Terminal': '1' };
  // Display labels of the assessment scale 0-4 (tutor.LEVELS holds the stored values).
  const LEVELS = ['math.level.0', 'math.level.1', 'math.level.2', 'math.level.3', 'math.level.4'];
  const level = (i) => (LEVELS[i] ? t(LEVELS[i]) : '');
  const state = { view: null, pending: [], mode: 'ask', busy: false, authorized: null };
  const $ = (id) => document.getElementById(id);

  // ---- safe rendering --------------------------------------------------------
  function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  function compile(latex, display) {
    if (!window.katex) return `<code>${escapeHtml(latex)}</code>`;
    try {
      return window.katex.renderToString(latex, { displayMode: display, throwOnError: false, strict: 'ignore' });
    } catch (_) {
      return `<code class="math-error">${escapeHtml(latex)}</code>`;
    }
  }

  // Every formula carries its compiled form and its escaped LaTeX source; the
  // "TeX / Rendered" toggle (data-math-view on <html>) shows one of the two.
  function tex(latex, display) {
    const fence = display ? '$$' : '$';
    return `<span class="tex-dual${display ? ' tex-dual--block' : ''}"><span class="tex-dual__out">${compile(latex, display)}</span>`
      + `<code class="tex-dual__src" translate="no">${escapeHtml(fence + latex + fence)}</code></span>`;
  }

  function setMathView(view) {
    const source = view === 'source';
    document.documentElement.dataset.mathView = source ? 'source' : 'rendered';
    document.querySelectorAll('[data-math-toggle]').forEach((b) => {
      b.setAttribute('aria-pressed', String(source));
      b.textContent = source ? t('math.viewRendered') : t('math.viewSource');
    });
    try { localStorage.setItem('papersmith.mathView', source ? 'source' : 'rendered'); } catch (_) { /* private mode */ }
  }

  // Markdown subset + math: $$…$$ (display) and $…$ (inline) are cut out first,
  // the rest is escaped, then **bold**, *italic*, `code`, lists and paragraphs.
  function richText(source) {
    const slots = [];
    const keep = (html) => `\u0000${slots.push(html) - 1}\u0000`;
    let text = String(source ?? '')
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => keep(`<div class="math-inline-display">${tex(m.trim(), true)}</div>`))
      .replace(/\$([^\s$](?:[^$\n]*?[^\s$])?)\$/g, (_, m) => keep(tex(m, false)));
    text = escapeHtml(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    const blocks = text.split(/\n{2,}/).map((block) => {
      const lines = block.split('\n');
      if (lines.every((l) => /^\s*(?:[-*]|\d+\.)\s+/.test(l))) {
        return `<ul>${lines.map((l) => `<li>${l.replace(/^\s*(?:[-*]|\d+\.)\s+/, '')}</li>`).join('')}</ul>`;
      }
      return `<p>${lines.join('<br>')}</p>`;
    });
    return blocks.join('').replace(/\u0000(\d+)\u0000/g, (_, i) => slots[Number(i)]);
  }

  // ---- paper mathematics ---------------------------------------------------
  function renderNovelty(view) {
    const card = $('mathNoveltyCard');
    if (!card) return;
    const n = view.novelty || {};
    const contributions = (n.contributions || []).slice(0, 5)
      .map((c) => `<li>${richText(c).replace(/^<p>|<\/p>$/g, '')}</li>`).join('');
    card.innerHTML = `
      <div class="math-label">${escapeHtml(t('math.centralIdea'))}</div>
      <div class="math-novelty__idea">${escapeHtml(n.central_idea || view.title || '')}</div>
      ${n.novelty ? `<div class="math-novelty__row"><span class="math-label">${escapeHtml(t('math.novelty'))}</span><div>${richText(n.novelty)}${n.novelty_detail ? `<div class="math-novelty__detail">${richText(n.novelty_detail)}</div>` : ''}</div></div>` : ''}
      ${n.problem ? `<div class="math-novelty__row"><span class="math-label">${escapeHtml(t('math.problem'))}</span><div>${richText(n.problem)}</div></div>` : ''}
      ${contributions ? `<div class="math-novelty__row"><span class="math-label">${escapeHtml(t('math.contributions'))}</span><ul>${contributions}</ul></div>` : ''}
      ${n.key_equation ? `<div class="math-novelty__key"><span class="math-label">${escapeHtml(t('math.keyEquation', { tag: n.key_equation.tag }))}</span>${tex(n.key_equation.latex, true)}</div>` : ''}
      ${!n.novelty && !n.key_equation ? `<p class="math-muted">${t('math.noProposalHtml')}</p>` : ''}`;
  }

  function renderEquations(view) {
    const lema = $('mathLema');
    if (lema) lema.innerHTML = richText(view.lema || '');
    const source = $('mathSourceBadge');
    if (source) source.textContent = source.title = view.source === 'none' ? t('math.noMathYet') : t('math.source', { source: view.source });
    const stack = $('mathStack');
    if (!stack) return;
    if (!view.equations.length) {
      stack.innerHTML = `<div class="eq-card eq-card--empty"><p>${t('math.noEquationsHtml')}</p></div>`;
      return;
    }
    stack.innerHTML = view.equations.map((eq) => `
      <article class="eq-card" id="mathEq-${escapeHtml(eq.id)}">
        <header class="eq-card__head"><span class="eq-card__tag">(${escapeHtml(eq.tag)})</span><span>${escapeHtml(eq.heading || t('math.equation'))}</span></header>
        <div class="eq-card__display">${tex(eq.latex, true)}</div>
        ${eq.connection ? `<div class="eq-card__conn"><strong>${escapeHtml(t('math.connection'))}</strong> ${richText(eq.connection).replace(/^<p>|<\/p>$/g, '')}</div>` : ''}
        ${(eq.variables || []).length ? `<dl class="eq-card__vars">${eq.variables.map((v) => `<dt><code>${escapeHtml(v.symbol)}</code></dt><dd>${escapeHtml(v.meaning)}</dd>`).join('')}</dl>` : ''}
      </article>`).join('');
  }

  async function refreshMathPanel() {
    try {
      const res = await fetch('/api/model/math');
      if (!res.ok) return;
      state.view = await res.json();
      renderNovelty(state.view);
      renderEquations(state.view);
    } catch (_) { /* offline: keep what is shown */ }
    loadThread();
  }

  // ---- tutor: thread ----------------------------------------------------------
  function setTutorStatus(text, tone) {
    const el = $('tutorStatus');
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone || 'muted';
  }

  function renderMeter(currentLevel) {
    const meter = $('tutorMeter');
    if (!meter) return;
    const lvl = Number.isInteger(currentLevel) ? currentLevel : 0;
    // One dot per level above "no evidence": level N lights N dots.
    meter.innerHTML = LEVELS.slice(1).map((_, i) => `<span class="tutor-meter__dot${i < lvl ? ' is-on' : ''}" title="${i + 1} · ${escapeHtml(level(i + 1))}"></span>`).join('')
      + `<span class="tutor-meter__label">${lvl} · ${escapeHtml(level(lvl))}</span>`;
  }

  function imageUrl(id) {
    return `/api/terminal/tutor/images/${encodeURIComponent(id)}`;
  }

  function renderTurn(turn) {
    if (turn.role === 'reader') {
      const imgs = (turn.images || []).map((id) => `<img src="${imageUrl(id)}" alt="${escapeHtml(t('math.readerImage'))}" loading="lazy">`).join('');
      return `<div class="tutor-msg tutor-msg--reader"><div class="tutor-msg__meta">${escapeHtml(t('tutor.you'))} · ${escapeHtml(turn.mode || '')}</div>${imgs ? `<div class="tutor-msg__imgs">${imgs}</div>` : ''}${turn.message ? richText(turn.message) : ''}</div>`;
    }
    const a = turn.assessment || {};
    const latex = (turn.latex || []).map((l) => `<div class="tutor-latex">${tex(l, true)}</div>`).join('');
    return `<div class="tutor-msg tutor-msg--tutor">
      <div class="tutor-msg__meta">${escapeHtml(t('tutor.tutor'))} · ${escapeHtml(turn.agent || '')}</div>
      ${turn.image_reading ? `<details class="tutor-reading"><summary>${escapeHtml(t('math.imageReading'))}</summary>${richText(turn.image_reading)}</details>` : ''}
      ${richText(turn.reply)}
      ${latex ? `<div class="tutor-latex-list">${latex}</div>` : ''}
      <div class="tutor-question">${richText(turn.question)}</div>
      ${turn.novelty_link ? `<div class="tutor-novelty"><span class="math-label">${escapeHtml(t('math.novelty'))}</span>${richText(turn.novelty_link)}</div>` : ''}
      <div class="tutor-assess"><span>${escapeHtml(t('math.understanding', { level: a.level }))} · ${escapeHtml(level(a.level) || a.label || '')}</span>${a.evidence ? ` — ${richText(a.evidence).replace(/^<p>|<\/p>$/g, '')}` : ''}${(a.gaps || []).length ? `<ul>${a.gaps.map((g) => `<li>${richText(g).replace(/^<p>|<\/p>$/g, '')}</li>`).join('')}</ul>` : ''}</div>
      ${turn.next_step ? `<div class="tutor-next"><span class="math-label">${escapeHtml(t('tutor.nextStep'))}</span>${richText(turn.next_step)}</div>` : ''}
    </div>`;
  }

  function renderThread(thread) {
    const box = $('tutorThread');
    if (!box) return;
    const turns = thread.turns || [];
    box.innerHTML = turns.length ? turns.map(renderTurn).join('')
      : `<p class="math-muted">${escapeHtml(t('math.threadEmpty'))}</p>`;
    const last = [...turns].reverse().find((turn) => turn.role === 'tutor');
    renderMeter(last && last.assessment ? last.assessment.level : 0);
    box.scrollTop = box.scrollHeight;
  }

  async function loadThread() {
    try {
      const res = await fetch('/api/terminal/tutor/thread', { headers: HEADERS });
      if (res.status === 403 || res.status === 404) {
        state.authorized = false;
        setTutorStatus(res.status === 404 ? t('tutor.disabled') : t('tutor.openFromLink'), 'bad');
        renderThread({ turns: [] });
        return;
      }
      state.authorized = true;
      renderThread(await res.json());
      setTutorStatus(t('common.ready'), 'ok');
    } catch (_) { setTutorStatus(t('tutor.offline'), 'bad'); }
  }

  // ---- tutor: attachments -------------------------------------------------------
  function renderPending() {
    const box = $('tutorPending');
    if (!box) return;
    box.innerHTML = state.pending.map((p, i) => `<figure class="tutor-thumb"><img src="${p.preview}" alt=""><button type="button" data-i="${i}" title="${escapeHtml(t('math.remove'))}">✕</button></figure>`).join('');
    box.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      state.pending.splice(Number(b.dataset.i), 1);
      renderPending();
    }));
  }

  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function addFiles(files) {
    for (const file of files) {
      if (!/^image\/(png|jpeg|webp)$/.test(file.type)) { setTutorStatus(t('math.imageTypes', { name: file.name }), 'bad'); continue; }
      if (state.pending.length >= 6) { setTutorStatus(t('math.maxImages'), 'bad'); break; }
      try {
        const dataUrl = await readAsDataUrl(file);
        setTutorStatus(t('math.uploading'), 'warn');
        const res = await fetch('/api/terminal/tutor/images', { method: 'POST', headers: HEADERS, body: JSON.stringify({ data_url: dataUrl }) });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
        state.pending.push({ id: body.id, preview: dataUrl });
        renderPending();
        setTutorStatus(t('math.imageReady'), 'ok');
      } catch (err) { setTutorStatus(t('math.uploadFailed', { error: err.message }), 'bad'); }
    }
  }

  // ---- tutor: send ----------------------------------------------------------------
  async function send() {
    if (state.busy) return;
    const input = $('tutorInput');
    const message = (input?.value || '').trim();
    if (!message && !state.pending.length) { setTutorStatus(t('math.writeOrAttach'), 'bad'); return; }
    state.busy = true;
    $('tutorSend').disabled = true;
    setTutorStatus(t('tutor.thinking'), 'warn');
    try {
      const res = await fetch('/api/terminal/tutor/turn', {
        method: 'POST', headers: HEADERS,
        body: JSON.stringify({ message, images: state.pending.map((p) => p.id), mode: state.mode }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      if (input) input.value = '';
      state.pending = [];
      renderPending();
      await loadThread();
      setTutorStatus(t('tutor.answeredBy', { agent: body.agent }), 'ok');
    } catch (err) {
      setTutorStatus(t('tutor.failed', { error: err.message }), 'bad');
    } finally {
      state.busy = false;
      $('tutorSend').disabled = false;
    }
  }

  async function resetThread() {
    if (!window.confirm(t('math.confirmReset'))) return;
    await fetch('/api/terminal/tutor/thread', { method: 'DELETE', headers: HEADERS, body: '{}' });
    loadThread();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const drop = $('tutorPanel');
    const file = $('tutorFile');
    if (drop) {
      ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('is-drop'); }));
      ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('is-drop'); }));
      drop.addEventListener('drop', (e) => addFiles([...(e.dataTransfer?.files || [])]));
      drop.addEventListener('paste', (e) => {
        const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
        if (files.length) { e.preventDefault(); addFiles(files); }
      });
    }
    $('tutorAttach')?.addEventListener('click', () => file?.click());
    file?.addEventListener('change', () => { addFiles([...file.files]); file.value = ''; });
    $('tutorSend')?.addEventListener('click', send);
    $('tutorReset')?.addEventListener('click', resetThread);
    $('tutorInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send(); });
    document.querySelectorAll('[data-tutor-mode]').forEach((b) => b.addEventListener('click', () => {
      state.mode = b.dataset.tutorMode;
      document.querySelectorAll('[data-tutor-mode]').forEach((x) => x.classList.toggle('is-on', x === b));
    }));
    document.querySelectorAll('[data-math-toggle]').forEach((b) => b.addEventListener('click', () => {
      setMathView(document.documentElement.dataset.mathView === 'source' ? 'rendered' : 'source');
    }));
    let saved = 'rendered';
    try { saved = localStorage.getItem('papersmith.mathView') || 'rendered'; } catch (_) { /* private mode */ }
    setMathView(saved);
    renderMeter(0);
  });

  // Labels are drawn here; the paper's text and the thread keep their language.
  document.addEventListener('languagechange', () => {
    setMathView(document.documentElement.dataset.mathView === 'source' ? 'source' : 'rendered');
    if (state.view) { renderNovelty(state.view); renderEquations(state.view); }
    if (state.authorized !== null) loadThread();
    else renderMeter(0);
  });

  window.refreshMathPanel = refreshMathPanel;
  window.mathRichText = richText;
})();

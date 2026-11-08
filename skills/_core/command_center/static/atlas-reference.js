/**
 * atlas-reference.js: a cited SOTA reference opens on the 3D constellation.
 *
 * Every citation the panels draw (citations.js) is a `data-atlas-ref` button.
 * A click opens the Graph Atlas on the constellation, asks the atlas page to
 * centre and light the reference's system (`focus`, answered by
 * `atlas-focused`), and fills #atlasReferenceCard with what the constellation
 * knows: GET /api/atlas/reference. An atlas drawn before the page understood
 * `focus` never answers; the card then says to regenerate the graph.
 */
(function () {
  'use strict';

  const t = (key, vars) => (window.i18n ? window.i18n.t(key, vars) : key);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const SLOTS = ['topic_app', 'topic_ai', 'problem', 'application', 'family', 'branch', 'novelty',
    'contribution', 'result', 'conclusion'];
  const RETRY_MS = 400;
  const TRIES = 15;
  let pending = null;
  let timer = 0;

  const card = () => document.getElementById('atlasReferenceCard');

  function note(text) {
    const el = document.getElementById('atlasReferenceNote');
    if (el) el.textContent = text;
  }

  function render(data) {
    const host = card();
    if (!host) return;
    const record = data.record || {};
    const system = data.system;
    const meta = [record.year, record.venue].filter(Boolean).map(esc).join(' · ');
    const rows = system ? SLOTS.filter((slot) => system.slots && system.slots[slot]).map((slot) => {
      // A detail that only repeats its label adds nothing.
      const extra = (item) => item.detail && item.detail.trim().toLowerCase() !== item.label.trim().toLowerCase();
      const items = system.slots[slot].map((item) => `<li><strong>${esc(item.label)}</strong>${extra(item) ? `<span> — ${esc(item.detail)}</span>` : ''}</li>`).join('');
      return `<div class="atlas-ref__row"><dt>${esc(t(`atlasRef.slot.${slot}`))}</dt><dd><ul>${items}</ul></dd></div>`;
    }).join('') : '';
    document.getElementById('atlasReferenceBody').innerHTML = `
      <div class="atlas-ref__head">
        <span class="atlas-ref__title">📚 ${esc(record.title || (system && system.title) || data.id)}</span>
        ${meta ? `<span class="atlas-ref__meta">${meta}</span>` : ''}
        ${system ? `<span class="badge badge--info">${esc(t('atlasRef.system', { title: system.title || system.id }))}</span>` : ''}
      </div>
      ${rows ? `<dl class="atlas-ref__slots">${rows}</dl>` : ''}`;
    note(system ? '' : t('atlasRef.notDrawn'));
    host.hidden = false;
    if (typeof host.scrollIntoView === 'function') host.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  function stop() {
    clearTimeout(timer);
    pending = null;
  }

  // The atlas page opens the paper's summary beside the sky itself; this card
  // only speaks when that page cannot (an atlas drawn by an older release).
  function focus(key, data) {
    stop();
    pending = key;
    let tries = 0;
    const send = () => {
      if (pending !== key) return;
      tries += 1;
      if (typeof window.postToGraph === 'function') window.postToGraph({ type: 'atlas-command', command: 'focus', key });
      if (tries < TRIES) timer = setTimeout(send, RETRY_MS);
      else { pending = null; render(data); note(t('atlasRef.oldAtlas')); }
    };
    send();
  }

  async function open(id) {
    let data;
    try {
      const response = await fetch(`/api/atlas/reference?id=${encodeURIComponent(id)}`, { cache: 'no-store' });
      data = await response.json();
    } catch (_) {
      data = { id, record: {}, system: null };
    }
    if (typeof window.navigateTab === 'function') window.navigateTab('atlas');
    if (typeof window.switchGraph === 'function') window.switchGraph('atlas');
    if (data.system && data.system.key) {
      const host = card();
      if (host) host.hidden = true;
      focus(data.system.key, data);
    } else {
      render(data);
    }
  }

  function close() {
    stop();
    const host = card();
    if (host) host.hidden = true;
  }

  document.addEventListener('click', (event) => {
    const button = event.target && event.target.closest ? event.target.closest('[data-atlas-ref]') : null;
    if (button) {
      event.preventDefault();
      open(button.getAttribute('data-atlas-ref'));
      return;
    }
    if (event.target && event.target.closest && event.target.closest('[data-atlas-ref-close]')) close();
  });

  window.addEventListener('message', (event) => {
    const frame = document.getElementById('graphIframe');
    const data = event.data;
    if (!frame || event.source !== frame.contentWindow || !data || data.type !== 'atlas-focused') return;
    if (data.key === pending) { stop(); close(); }
  });

  window.AtlasReference = { open, close };
})();

/**
 * section-folds.js: the folding bars of the Concept Map & Model and Novelty &
 * Findings tabs, the same bars the Experiments tab draws.
 *
 * A block marked `data-fold="<name>"` with `data-fold-title="<catalogue key>"`
 * (and `data-fold-open` when it should start open) is wrapped in a <details>
 * whose summary carries that title. The operator's open or closed choice is
 * remembered per browser, so a reload or a panel that redraws itself keeps it.
 */
(function () {
  'use strict';

  const KEY = 'papersmith.folds';
  const t = (key) => (window.i18n ? window.i18n.t(key) : key);

  function stored() {
    try {
      const value = JSON.parse(window.localStorage.getItem(KEY) || '{}');
      return value && typeof value === 'object' ? value : {};
    } catch (_) {
      return {};
    }
  }

  function remember(name, open) {
    const folds = stored();
    folds[name] = open;
    try { window.localStorage.setItem(KEY, JSON.stringify(folds)); } catch (_) { /* this page only */ }
  }

  function wrap(root) {
    const scope = root || document;
    if (!scope.querySelectorAll) return;
    const saved = stored();
    scope.querySelectorAll('[data-fold]:not(details)').forEach((block) => {
      if (block.parentElement && block.parentElement.classList.contains('exp-fold__body')) return;
      const name = block.getAttribute('data-fold');
      const details = document.createElement('details');
      details.className = 'exp-fold';
      details.setAttribute('data-fold-name', name);
      details.open = typeof saved[name] === 'boolean' ? saved[name] : block.hasAttribute('data-fold-open');
      const summary = document.createElement('summary');
      summary.className = 'exp-fold__summary';
      const title = document.createElement('span');
      title.className = 'exp-fold__title';
      const key = block.getAttribute('data-fold-title') || '';
      if (key) title.setAttribute('data-i18n', key);
      title.textContent = t(key);
      summary.appendChild(title);
      const body = document.createElement('div');
      body.className = 'exp-fold__body';
      block.replaceWith(details);
      details.append(summary, body);
      body.appendChild(block);
    });
  }

  document.addEventListener('toggle', (event) => {
    const item = event.target;
    if (item && item.getAttribute && item.getAttribute('data-fold-name')) {
      remember(item.getAttribute('data-fold-name'), item.open);
    }
  }, true);
  document.addEventListener('DOMContentLoaded', () => wrap(document));

  window.SectionFolds = { wrap };
})();

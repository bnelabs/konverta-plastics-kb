#!/usr/bin/env node
'use strict';
/*
 * Frontend smoke test.
 *
 * Production pulls a release image automatically, so a bundle that is missing or
 * throws at startup reaches kb.konverta.eu without a human in the loop. This test
 * asserts the contract between index.html, the built bundle and the API shape:
 *   1. every /assets/... reference in index.html resolves to a real file
 *   2. app/static/dist/app.js exists (the bundle the page actually loads)
 *   3. the bundle boots, renders cards, marks review state and opens a detail view
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const staticDir = path.join(root, 'app/static');
const bundlePath = path.join(staticDir, 'dist', 'app.js');

const failures = [];
function check(name, ok, detail = '') {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  if (!ok) failures.push(name);
}

const MATERIALS = [
  {
    id: 2, code: 'HDPE', name: 'High-Density Polyethylene', common_uses: 'Milk jugs',
    melt_temp_c: '130 - 135°C', density_g_cm3: 0.95, toxicity_level: 'Low',
    recyclability: 'High', notes: 'Shreds cleanly.', source_title: 'EPA guide',
    source_url: 'https://www.epa.gov/recycling-materials/plastic-identification-codes',
    review_status: 'verified',
  },
  {
    id: 4, code: 'LDPE', name: 'Low-Density Polyethylene', common_uses: 'Plastic bags',
    melt_temp_c: '105 - 115°C', density_g_cm3: 0.92, toxicity_level: 'Low',
    recyclability: 'Low-Medium', notes: 'Melts at low temperatures.',
    source_title: null, source_url: null, review_status: 'needs_review',
  },
];

const PROCESSES = [{
  id: 1, name: 'Shredding', description: 'Mechanical reduction.',
  equipment_needed: 'Shredder', safety_precautions: 'Wear eye protection.',
}];

const PROJECTS = [{
  id: 1, title: 'HDPE Clip', difficulty: 'Medium', description: 'Utility clips.',
  instructions: 'Sort, shred, dry, mold.', material_code: 'HDPE', process_name: 'Injection Molding',
}];

const MATERIAL_DETAIL = {
  ...MATERIALS[0],
  processes: [{
    name: 'Shredding', description: 'Mechanical reduction.', equipment_needed: 'Shredder',
    safety_precautions: 'Wear eye protection.', suitability_rating: 'Excellent', notes: 'Shreds cleanly.',
  }],
  projects: [{ title: 'HDPE Clip', difficulty: 'Medium', description: 'Utility clips.' }],
};

function payloadFor(url) {
  if (url.startsWith('/api/v1/metrics')) {
    return { version: '0.2.1', uptime_seconds: 1, database_bytes: 1, last_event: null,
      records: { materials: 2, processes: 1, material_processes: 1, compatibility: 1, projects: 1 } };
  }
  if (url.startsWith('/api/v1/materials/')) {
    const code = decodeURIComponent(url.split('/').pop()).toUpperCase();
    return code === 'HDPE' ? MATERIAL_DETAIL : { ...MATERIALS[1], processes: [], projects: [], sources: [] };
  }
  if (url.startsWith('/api/v1/materials')) return MATERIALS;
  if (url.startsWith('/api/v1/processes')) return PROCESSES;
  if (url.startsWith('/api/v1/projects')) return PROJECTS;
  throw new Error(`smoke test: unexpected fetch ${url}`);
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 30));

(async function main() {
  const html = fs.readFileSync(path.join(staticDir, 'index.html'), 'utf8');

  // 1. static asset references resolve
  const refs = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
  check('index.html references at least one /assets file', refs.length > 0);
  for (const ref of refs) {
    const file = path.join(staticDir, ref.replace('/assets/', ''));
    check(`asset resolves: ${ref}`, fs.existsSync(file), `missing ${file}`);
  }

  // 2. entry bundle exists and parses
  if (!fs.existsSync(bundlePath)) {
    check('app/static/dist/app.js exists', false, 'run scripts/build-frontend.sh');
    process.exitCode = 1;
    return;
  }
  const bundle = fs.readFileSync(bundlePath, 'utf8');
  check('app/static/dist/app.js exists', true);

  // 3. boot the bundle against a stubbed API
  const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost/', pretendToBeVisual: true });
  const { window } = dom;
  window.fetch = async (url) => ({ ok: true, json: async () => payloadFor(String(url)) });
  window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; };
  window.HTMLDialogElement.prototype.close = function close() { this.open = false; };

  const errors = [];
  window.addEventListener('error', (e) => errors.push(e.message));
  const script = window.document.createElement('script');
  script.textContent = bundle;
  window.document.body.appendChild(script);
  await tick(); await tick(); await tick();

  check('bundle boots without runtime errors', errors.length === 0, errors.join('; '));
  check('version rendered from /api/v1/metrics', window.document.querySelector('#version').textContent === 'v0.2.1',
    `got ${window.document.querySelector('#version').textContent}`);
  check('stats rendered', window.document.querySelectorAll('#stats .stat').length === 4);

  const cards = window.document.querySelectorAll('#content [data-code]');
  check('material cards rendered', cards.length === 2, `got ${cards.length}`);
  check('verified material shows a verified badge',
    !!window.document.querySelector('#content .review-badge.verified'));
  check('unverified material shows a draft badge',
    !!window.document.querySelector('#content .review-badge.draft'));

  // Review Queue view filters out verified materials
  window.document.querySelector('.nav-item[data-view="needs_review"]').click();
  await tick(); await tick();
  const queue = window.document.querySelector('#content');
  check('Review Queue view renders', queue.textContent.includes('Review Queue'));
  check('Review Queue lists only unverified materials',
    queue.querySelectorAll('[data-code]').length === 1 && queue.textContent.includes('LDPE'),
    queue.textContent.slice(0, 120));

  // Detail dialog surfaces the recorded source for a verified material
  window.document.querySelector('.nav-item[data-view="materials"]').click();
  await tick(); await tick();
  window.document.querySelector('#content [data-code="HDPE"]').click();
  await tick(); await tick();
  const detail = window.document.querySelector('#detail-body');
  check('detail dialog renders the material', detail.textContent.includes('High-Density Polyethylene'));
  check('detail dialog surfaces the notes block', detail.textContent.includes('Notes & handling'));
  check('detail dialog links the recorded source',
    !!detail.querySelector('.source-block a[href^="https://"]'),
    detail.querySelector('.source-block')?.textContent?.trim());
  check('detail dialog is labelled by the material name',
    window.document.querySelector('#detail-title')?.textContent === 'High-Density Polyethylene',
    window.document.querySelector('#detail-title')?.outerHTML);

  // Unverified material must not pretend to have a source
  window.document.querySelector('#detail .close').click();
  window.document.querySelector('#content [data-code="LDPE"]').click();
  await tick(); await tick();
  const draftDetail = window.document.querySelector('#detail-body');
  check('unverified material states no source is recorded',
    draftDetail.textContent.includes('Source not yet recorded'),
    draftDetail.querySelector('.source-block')?.textContent?.trim());
  check('unverified material warns before operational use',
    draftDetail.textContent.includes('verify before operational use'));
  window.document.querySelector('#detail .close').click();

  // Editor validation must block unsourced records and announce the failure
  const editor = window.document.querySelector('#editor');
  const form = window.document.querySelector('#material-form');
  const toastText = () => window.document.querySelector('#toast').textContent;
  const submit = () => form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));

  const addButton = window.document.querySelector('#content [data-add-material]');
  addButton.focus();
  addButton.click();
  await tick();
  check('editor dialog opens', editor.open === true);

  form.querySelector('[name="code"]').value = 'TEST';
  form.querySelector('[name="name"]').value = 'Test material';
  form.querySelector('[name="source_title"]').value = '';
  form.querySelector('[name="source_url"]').value = 'https://example.org/source';
  submit();
  await tick();
  check('editor rejects a missing source title', toastText().includes('Source title is required'));
  check('editor stays open after a validation failure', editor.open === true);

  form.querySelector('[name="source_title"]').value = 'EPA Plastic Identification Guide';
  form.querySelector('[name="source_url"]').value = 'http://example.org/source';
  submit();
  await tick();
  check('editor rejects a non-https source url', toastText().includes('Source URL must start with'));

  // Keyboard users must not tab out of an open dialog
  const focusables = [...editor.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])')];
  const firstFocusable = focusables[0];
  const lastFocusable = focusables[focusables.length - 1];
  const tab = (shift) => new window.KeyboardEvent('keydown', { key: 'Tab', shiftKey: shift, bubbles: true, cancelable: true });

  lastFocusable.focus();
  lastFocusable.dispatchEvent(tab(false));
  check('Tab from the last control wraps to the first', window.document.activeElement === firstFocusable,
    `active=${window.document.activeElement?.tagName}:${window.document.activeElement?.getAttribute('name') || window.document.activeElement?.className}`);

  firstFocusable.focus();
  firstFocusable.dispatchEvent(tab(true));
  check('Shift+Tab from the first control wraps to the last', window.document.activeElement === lastFocusable);

  // Closing a dialog returns focus to whatever opened it
  window.document.querySelector('#editor .close').click();
  await tick();
  check('closing the editor restores focus to its trigger',
    window.document.activeElement === addButton, `active=${window.document.activeElement?.tagName}`);

  // Navigation state and keyboard reachability
  window.document.querySelector('.nav-item[data-view="processes"]').click();
  await tick();
  const current = window.document.querySelector('.nav-item[aria-current="page"]');
  check('active nav item exposes aria-current="page"',
    current?.dataset.view === 'processes', `aria-current on ${current?.dataset.view}`);
  check('inactive nav items do not claim aria-current',
    [...window.document.querySelectorAll('.nav-item')]
      .filter((b) => b.dataset.view !== 'processes')
      .every((b) => !b.hasAttribute('aria-current')));

  window.document.querySelector('.nav-item[data-view="projects"]').click();
  await tick(); await tick();
  const projectCard = window.document.querySelector('#content [data-project]');
  check('project card is exposed as a keyboard-focusable button',
    projectCard?.getAttribute('role') === 'button' && projectCard?.getAttribute('tabindex') === '0',
    projectCard?.outerHTML?.slice(0, 90));
  projectCard.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  await tick(); await tick();
  check('Enter opens the project detail dialog',
    window.document.querySelector('#detail-body').textContent.includes('HDPE Clip'));

  window.close();
  console.log(failures.length ? `\n${failures.length} check(s) failed` : '\nall frontend smoke checks passed');
  process.exitCode = failures.length ? 1 : 0;
})().catch((error) => {
  console.error('smoke test crashed:', error);
  process.exitCode = 1;
});

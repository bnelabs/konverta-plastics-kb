// Typed frontend for the Konverta materials library. DOM contract: app/static/index.html.
type MaterialProcess = {
  name: string;
  description?: string | null;
  suitability_rating?: string | null;
  notes?: string | null;
  safety_precautions?: string | null;
};

type MaterialProject = {
  title: string;
  difficulty?: string | null;
  description?: string | null;
};

type Material = {
  id?: number;
  code: string;
  name: string;
  common_uses?: string | null;
  melt_temp_c?: string | null;
  density_g_cm3?: number | null;
  toxicity_level?: string | null;
  recyclability?: string | null;
  notes?: string | null;
  source_title?: string | null;
  source_url?: string | null;
  review_status?: string | null;
};

type MaterialDetail = Material & {
  processes: MaterialProcess[];
  projects: MaterialProject[];
};

type KbEvent = {
  id: number;
  event: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  details?: string | null;
  created_at: string;
};

type Process = {
  name: string;
  description?: string | null;
  equipment_needed?: string | null;
  safety_precautions?: string | null;
};

type Project = {
  id: number;
  title: string;
  difficulty?: string | null;
  description?: string | null;
  instructions?: string | null;
  material_code?: string | null;
  process_name?: string | null;
};

type ContaminationRisk = {
  id: number;
  contaminant_name: string;
  material_code: string;
  material_name: string;
  impact_description: string;
  safety_notes: string;
  source_title: string;
  source_url: string;
  review_status?: string | null;
};

type Metrics = {
  version: string;
  records: { materials: number; processes: number; compatibility: number; projects: number };
};

// index.html names every control, so the form's named controls can be read directly.
type MaterialForm = HTMLFormElement & {
  elements: HTMLFormControlsCollection & Record<string, { value: string | number | null }>;
};

const $ = <T extends HTMLElement = HTMLElement>(selector: string): T | null => document.querySelector<T>(selector);
const labels: Record<string, readonly [string, string, string]> = {
  overview: ['Overview', 'Materials, made useful.', 'A practical field guide to working with recycled plastics.'],
  materials: ['Materials', 'Know your material.', 'Explore common polymers, their uses, and handling notes.'],
  processes: ['Processes', 'From feedstock to form.', 'Compare practical recycling and upcycling methods.'],
  projects: ['Projects', 'Ideas for another life.', 'Browse practical concepts built around recovered materials.'],
  needs_review: ['Review Queue', 'Factual curation.', 'Materials needing source verification and safety review.'],
  contamination: ['Contamination', 'What can go wrong.', 'Common contaminants, impact on recycling and safety notes.'],
};
let view = 'overview';
let currentMaterialCode: string | null = null;
let searchTimer: number | undefined;
const CACHE_TTL_MS = 60_000;
const CACHEABLE_PREFIXES = ['/api/v1/materials', '/api/v1/processes', '/api/v1/projects', '/api/v1/metrics'];
const apiCache = new Map<string, {data: unknown; ts: number}>();

function isCacheable(path: string): boolean {
  return CACHEABLE_PREFIXES.some(p => path.startsWith(p));
}

async function get<T>(path: string): Promise<T> {
  if (isCacheable(path)) {
    const now = Date.now();
    const cached = apiCache.get(path);
    if (cached && now - cached.ts < CACHE_TTL_MS) {
      return cached.data as T;
    }
  }
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  const data = await response.json() as T;
  if (isCacheable(path)) {
    apiCache.set(path, { data, ts: Date.now() });
  }
  return data;
}

// Invalidate cache on writes
function invalidateCache(): void {
  apiCache.clear();
}

function esc(value: unknown = ''): string {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  } as Record<string, string>)[character]);
}

// Keyboard users must not tab out of an open dialog into the page behind it.
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const dialogTriggers = new WeakMap<HTMLDialogElement, HTMLElement | null>();

function openDialog(dialog: HTMLDialogElement): void {
  dialogTriggers.set(dialog, document.activeElement as HTMLElement | null);
  dialog.showModal();
}

function closeDialog(dialog: HTMLDialogElement): void {
  dialog.close();
  const trigger = dialogTriggers.get(dialog);
  if (trigger && document.contains(trigger)) trigger.focus();
}

function trapFocus(dialog: HTMLDialogElement, event: KeyboardEvent): void {
  if (event.key !== 'Tab') return;
  const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  const inside = active instanceof HTMLElement && dialog.contains(active);
  if (event.shiftKey) {
    if (!inside || active === first) { event.preventDefault(); last.focus(); }
  } else if (!inside || active === last) {
    event.preventDefault();
    first.focus();
  }
}

function setView(next: string, updateHash = true): void {
  const viewChanged = view !== next;
  if (viewChanged) {
    // close material dialog if leaving materials view
    if (view === 'materials' && next !== 'materials' && currentMaterialCode) {
      const dlg = $('#detail') as HTMLDialogElement;
      if (dlg?.open) closeDialog(dlg);
      currentMaterialCode = null;
    }
    view = next;
    document.querySelectorAll<HTMLElement>('.nav-item').forEach((button) => {
      const isActive = button.dataset.view === view;
      button.classList.toggle('active', isActive);
      // Keep the accessibility state in step with the visual state.
      if (isActive) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    $('#breadcrumb')!.textContent = labels[view][0];
    $('#page-title')!.textContent = labels[view][1];
    $('#page-description')!.textContent = labels[view][2];
  }
  if (updateHash) {
    const params = new URLSearchParams();
    params.set('view', view);
    if (currentMaterialCode && view === 'materials') {
      params.set('material', currentMaterialCode);
    }
    const newHash = params.toString();
    if (location.hash.slice(1) !== newHash) {
      history.replaceState(null, '', '#' + newHash);
    }
  }
  render();
}

async function loadData(): Promise<{ materials: Material[]; processes: Process[]; projects: Project[] }> {
  const query = encodeURIComponent($<HTMLInputElement>('#search')!.value);
  const [materials, processes, projects, metrics] = await Promise.all([
    get<Material[]>(`/api/v1/materials?q=${query}`), get<Process[]>('/api/v1/processes'),
    get<Project[]>(`/api/v1/projects?q=${query}`), get<Metrics>('/api/v1/metrics'),
  ]);
  $('#version')!.textContent = `v${metrics.version}`;
  $('#nav-materials')!.textContent = String(metrics.records.materials);
  $('#stats')!.innerHTML = [
    ['Materials', metrics.records.materials, 'Polymer profiles'],
    ['Processes', metrics.records.processes, 'Methods and equipment'],
    ['Compatibility rules', metrics.records.compatibility, 'Recorded blend guidance'],
    ['Project concepts', metrics.records.projects, 'Starting points to explore'],
  ].map(([title, value, note]) => `<div class="stat"><div class="stat-top">${title}</div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></div>`).join('');
  return { materials, processes, projects };
}

async function render(): Promise<void> {
  try {
    const data = await loadData();
    const query = $<HTMLInputElement>('#search')!.value.trim().toLowerCase();
    let html: string;
    if (view === 'needs_review') {
      const matches = data.materials.filter(m => m.review_status !== 'verified');
      html = `<div class="section-title"><div><h2>Review Queue</h2><p>${matches.length} material${matches.length === 1 ? '' : 's'} needing source verification</p></div></div><div class="material-grid">${matches.map(materialCard).join('') || '<div class="empty">No materials need review.</div>'}</div>`;
    } else if (view === 'overview' || view === 'materials') {
      const matches = data.materials;
      const shown = view === 'overview' ? matches.slice(0, 6) : matches;
      html = `<div class="section-title"><div><h2>${view === 'overview' ? 'Explore materials' : 'Material directory'}</h2><p>${matches.length} polymer ${matches.length === 1 ? 'profile' : 'profiles'} in the library</p></div><div class="section-actions">${view === 'overview' ? '<a class="text-link" data-goto="materials">View all materials <span aria-hidden="true">→</span></a>' : ''}<button class="text-link add-link" data-add-material><span aria-hidden="true">＋</span> Add material</button></div></div><div class="material-grid">${shown.map(materialCard).join('') || '<div class="empty">No materials match that search.</div>'}</div>`;
    } else if (view === 'processes') {
      const shown = data.processes.filter((item) => !query || JSON.stringify(item).toLowerCase().includes(query));
      html = `<div class="section-title"><div><h2>Recycling processes</h2><p>Methods, equipment, and safety notes</p></div></div><div class="process-grid">${shown.map((item) => `<article class="process-card"><h3>${esc(item.name)}</h3><p>${esc(item.description || '')}</p><p><b>Equipment</b> · ${esc(item.equipment_needed || 'Not recorded')}</p><div class="safety"><b>Safety</b> · ${esc(item.safety_precautions || 'Follow local safety guidance.')}</div></article>`).join('') || '<div class="empty">No processes match that search.</div>'}</div>`;
    } else if (view === 'contamination') {
      const risks = await get<ContaminationRisk[]>(`/api/v1/contamination?material_code=${encodeURIComponent(query)}&contaminant=${encodeURIComponent(query)}&limit=200`);
      const shown = risks.filter(r => !query || r.contaminant_name.toLowerCase().includes(query) || r.material_code.toLowerCase().includes(query) || r.impact_description.toLowerCase().includes(query));
      const severityFor = (r: ContaminationRisk) => {
        const s = (r.safety_notes + ' ' + r.impact_description).toLowerCase();
        if (s.includes('hcl') || s.includes('hydrogen chloride') || s.includes('corrosive')) return 'critical';
        if (s.includes('voc') || s.includes('styrene') || s.includes('monomer')) return 'high';
        if (s.includes('metal') || s.includes('cutting')) return 'moderate';
        return 'low';
      };
      const guide = `<div class="contamination-guide"><h3>Discrimination guide</h3><p>Use visual, density and safety cues. See <a href="/assets/docs/CONTAMINATION_SCENARIOS.md" target="_blank" rel="noopener">Contamination Scenarios</a> for mixed-bulk decision trees. Never infer compatibility – record unknown.</p><ul><li><b>PVC in PET</b> → HCl risk on heating, remove by sink-float.</li><li><b>Black PP + inks</b> → VOCs on heating, downcycle.</li><li><b>Food residue</b> → wash + dry, PPE.</li><li><b>Metal clips</b> → magnet/e eddy current before shred.</li></ul></div>`;
      html = `<div class="section-title"><div><h2>Contamination risks</h2><p>${shown.length} recorded risk${shown.length === 1 ? '' : 's'}</p></div></div>${guide}<div class="contamination-grid">${shown.map(r => {
        const sev = severityFor(r);
        return `<article class="contamination-card"><div class="card-head"><button class="code-pill" data-code="${esc(r.material_code)}">${esc(r.material_code)}</button><span class="contaminant">${esc(r.contaminant_name)}</span><span class="severity-badge ${sev}">${sev.toUpperCase()}</span></div><h3>${esc(r.material_name)}</h3><p><b>Impact:</b> ${esc(r.impact_description)}</p><div class="safety"><b>Safety:</b> ${esc(r.safety_notes)}</div><div class="source"><small>Source: <a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source_title)} ↗</a> · ${esc(r.review_status || 'needs review')}</small></div></article>`;
      }).join('') || '<div class="empty">No contamination risks match that search.</div>'}</div>`;
    } else {
      const shown = data.projects.filter((item) => !query || JSON.stringify(item).toLowerCase().includes(query));
      html = `<div class="section-title"><div><h2>Project ideas</h2><p>Concepts to validate and develop with the right expertise</p></div></div><div class="project-grid">${shown.map((item) => `<article class="project-card" data-project="${item.id}" role="button" tabindex="0"><span class="badge">${esc(item.difficulty || 'Concept')}</span><h3>${esc(item.title)}</h3><p>${esc(item.description || '')}</p><div class="project-meta">${esc(item.material_code || 'Material not linked')} · ${esc(item.process_name || 'Process not linked')}</div></article>`).join('') || '<div class="empty">No projects match that search.</div>'}</div>`;
    }
    $('#content')!.innerHTML = html;
    document.querySelectorAll<HTMLElement>('[data-code]').forEach((card) => card.addEventListener('click', () => showMaterial(card.dataset.code!)));
    document.querySelectorAll<HTMLElement>('[data-goto]').forEach((link) => link.addEventListener('click', () => setView(link.dataset.goto!)));
    document.querySelectorAll<HTMLElement>('[data-project]').forEach((card) => {
      card.addEventListener('click', () => showProject(Number(card.dataset.project)));
      // The card is role="button", so it must also respond to the keyboard.
      card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          showProject(Number(card.dataset.project));
        }
      });
    });
    document.querySelectorAll<HTMLElement>('[data-add-material]').forEach((button) => button.addEventListener('click', () => editMaterial()));
  } catch (error) {
    $('#content')!.innerHTML = `<div class="empty">The library could not be loaded. ${esc((error as Error).message)} <button class="text-link" id="retry">Try again</button></div>`;
    $('#retry')?.addEventListener('click', render);
  }
}

function materialCard(material: Material): string {
  const needsReview = material.review_status !== 'verified';
  const risk = String(material.toxicity_level || 'Not rated').toLowerCase();
  const reviewClass = needsReview ? 'review-badge draft' : 'review-badge verified';
  const reviewText = needsReview ? 'Prototype data · verify' : 'Source checked';
  return `<button class="material-card" type="button" data-code="${esc(material.code)}"><div class="card-head"><span class="code-pill">${esc(material.code)}</span><span class="risk ${risk === 'high' ? 'high' : ''}">${esc(material.toxicity_level || 'Not rated')} handling</span></div><h3>${esc(material.name)}</h3><p>${esc(material.common_uses || 'No common uses recorded')}</p><div class="card-foot"><span class="${reviewClass}">${reviewText}</span><span>Melting range <b>${esc(material.melt_temp_c || 'Not recorded')}</b></span></div></button>`;
}

async function showMaterial(code: string, updateHash = true): Promise<void> {
  try {
    const material = await get<MaterialDetail>(`/api/v1/materials/${encodeURIComponent(code)}`);
    const source = material.source_url
      ? `<a href="${esc(material.source_url)}" target="_blank" rel="noopener noreferrer">${esc(material.source_title || material.source_url)} ↗</a>`
      : '<span>Source not yet recorded</span>';
    $('#detail-body')!.innerHTML = `<div class="detail-inner"><div class="detail-kicker">Material profile · ${esc(material.code)}</div><h2 id="detail-title">${esc(material.name)}</h2><p class="lead">${esc(material.common_uses || 'Common uses have not yet been recorded.')}</p><div class="review-banner ${material.review_status === 'verified' ? 'verified' : ''}">${material.review_status === 'verified' ? 'Source reviewed' : 'Prototype data · verify before operational use'}</div><div class="detail-grid"><div class="detail-field"><small>Melting range</small><b>${esc(material.melt_temp_c || 'Not recorded')}</b></div><div class="detail-field"><small>Density</small><b>${material.density_g_cm3 ? `${esc(material.density_g_cm3)} g/cm³` : 'Not recorded'}</b></div><div class="detail-field"><small>Handling</small><b>${esc(material.toxicity_level || 'Not rated')}</b></div><div class="detail-field"><small>Recyclability</small><b>${esc(material.recyclability || 'Not recorded')}</b></div></div><div class="detail-block"><h3>Notes & handling</h3><p class="lead">${esc(material.notes || 'No notes have been recorded.')}</p></div><div class="detail-block"><h3>Process suitability</h3><div class="detail-list">${material.processes.length ? material.processes.map((item) => `<div class="detail-item"><b>${esc(item.name)} · ${esc(item.suitability_rating || 'Unrated')}</b><p>${esc(item.notes || item.description || '')}</p>${item.safety_precautions ? `<p><b>Safety:</b> ${esc(item.safety_precautions)}</p>` : ''}</div>`).join('') : '<p class="lead">No process suitability recorded. Treat as unknown.</p>'}</div></div><div class="detail-block"><h3>Related projects</h3><div class="detail-list">${material.projects.length ? material.projects.map((item) => `<div class="detail-item"><b>${esc(item.title)} · ${esc(item.difficulty || '')}</b><p>${esc(item.description || '')}</p></div>`).join('') : '<p class="lead">No projects linked yet.</p>'}</div></div><div class="detail-block source-block"><h3>Source</h3><p>${source}</p></div><div class="detail-block detail-actions"><span>Updates are stored with a history entry.</span><button id="history-button" class="text-link" type="button" aria-expanded="false">History</button><button id="edit-material" class="primary-button">Edit material</button></div><div id="history-block" class="detail-block" hidden><h3>History</h3><div id="history-timeline" class="detail-list"><p class="lead">No history loaded yet.</p></div></div></div>`;
    $<HTMLButtonElement>('#edit-material')!.addEventListener('click', () => { closeDialog($<HTMLDialogElement>('#detail')!); editMaterial(material); });
    const historyBtn = $<HTMLButtonElement>('#history-button')!;
    const historyBlock = $('#history-block')!;
    const timeline = $('#history-timeline')!;
    let historyLoaded = false;
    historyBtn.addEventListener('click', async () => {
      if (!material.id) { toast('Material ID missing, cannot load history'); return; }
      if (!historyLoaded) {
        try {
          const events = await get<KbEvent[]>(`/api/v1/events?entity_type=material&entity_id=${material.id}&limit=100`);
          if (events.length) {
            timeline.innerHTML = events.map(ev => `<div class="detail-item"><b>${esc(ev.event)} · ${esc(new Date(ev.created_at).toLocaleString())}</b><p><b>Actor:</b> ${esc(ev.actor)}</p><p>${esc(ev.details || '')}</p></div>`).join('');
          } else {
            timeline.innerHTML = '<p class="lead">No history recorded for this material.</p>';
          }
          historyLoaded = true;
        } catch (err) { timeline.innerHTML = `<p class="lead">Could not load history. ${esc((err as Error).message)}</p>`; }
      }
      const isHidden = historyBlock.hidden;
      historyBlock.hidden = !isHidden;
      historyBtn.setAttribute('aria-expanded', String(!historyBlock.hidden));
    });
    openDialog($<HTMLDialogElement>('#detail')!);
    // ensure view is materials and update deep link
    if (view !== 'materials') {
      setView('materials', false);
    }
    currentMaterialCode = code;
    if (updateHash) {
      const params = new URLSearchParams();
      params.set('view', 'materials');
      params.set('material', code);
      const newHash = params.toString();
      if (location.hash.slice(1) !== newHash) {
        history.replaceState(null, '', '#' + newHash);
      }
    }
  } catch (error) { toast((error as Error).message); }
}

async function showProject(id: number): Promise<void> {
  try {
    const project = (await get<Project[]>('/api/v1/projects')).find((item) => item.id === id);
    if (!project) return;
    $('#detail-body')!.innerHTML = `<div class="detail-inner"><div class="detail-kicker">Project concept · ${esc(project.difficulty || 'Concept')}</div><h2 id="detail-title">${esc(project.title)}</h2><p class="lead">${esc(project.description || '')}</p><div class="detail-grid"><div class="detail-field"><small>Material</small><b>${esc(project.material_code || 'Not linked')}</b></div><div class="detail-field"><small>Process</small><b>${esc(project.process_name || 'Not linked')}</b></div></div><div class="detail-block"><h3>Starting steps</h3><p class="lead">${esc(project.instructions || 'No steps recorded.').replace(/\n/g, '<br>')}</p></div><div class="review-banner">Concept only · validate material, settings, ventilation, and product safety before use.</div></div>`;
    openDialog($<HTMLDialogElement>('#detail')!);
  } catch (error) { toast((error as Error).message); }
}

function editMaterial(material: Material | null = null): void {
  const form = $<MaterialForm>('#material-form')!;
  form.reset();
  form.elements.original_code.value = material?.code || '';
  $('#editor-title')!.textContent = material ? `Edit ${material.code}` : 'Add a material';
  if (material) Object.entries(material).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ''; });
  form.elements.review_status.value = material?.review_status || 'draft';
  openDialog($<HTMLDialogElement>('#editor')!);
}

function toast(message: string): void {
  const element = $('#toast')!;
  element.textContent = message;
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 2800);
}

function clearFieldErrors(form: HTMLFormElement): void {
  form.querySelectorAll<HTMLElement>('.field-error').forEach(el => el.remove());
  form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('input, select, textarea').forEach(el => el.removeAttribute('aria-invalid'));
}

function setFieldError(form: HTMLFormElement, name: string, message: string): void {
  const control = form.elements.namedItem(name) as HTMLElement | null;
  if (!control) return;
  const input = control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement ? control : null;
  if (input) input.setAttribute('aria-invalid', 'true');
  const label = control.closest('label');
  if (label) {
    let err = label.querySelector('.field-error') as HTMLElement | null;
    if (!err) {
      err = document.createElement('span');
      err.className = 'field-error';
      err.setAttribute('role', 'alert');
      label.appendChild(err);
    }
    err.textContent = message;
  }
}

document.querySelectorAll<HTMLElement>('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view!)));
$<HTMLInputElement>('#search')!.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(render, 160); });
$('#refresh')!.addEventListener('click', render);
// deep link handling
const VALID_VIEWS = ['overview','materials','processes','projects','contamination','needs_review'];
function applyHash(): void {
  const params = new URLSearchParams(location.hash.slice(1));
  const viewParam = params.get('view');
  const materialParam = params.get('material');
  const codeParam = params.get('code');
  const code = materialParam || codeParam;
  let targetView = 'overview';
  if (code) {
    targetView = 'materials';
  } else if (viewParam && VALID_VIEWS.includes(viewParam)) {
    targetView = viewParam;
  }
  if (view !== targetView) {
    setView(targetView, false);
  }
  if (code) {
    if (currentMaterialCode !== code) {
      if (view !== 'materials') {
        setView('materials', false);
      }
      void showMaterial(code, false);
    }
  } else {
    if (currentMaterialCode) {
      const dlg = $('#detail') as HTMLDialogElement;
      if (dlg?.open) closeDialog(dlg);
      currentMaterialCode = null;
    }
  }
}
window.addEventListener('hashchange', applyHash);
$<HTMLButtonElement>('#bulk-import')?.addEventListener('click', () => openDialog($<HTMLDialogElement>('#bulk')!));
$('#detail .close')!.addEventListener('click', () => closeDialog($<HTMLDialogElement>('#detail')!));
$('#editor .close')!.addEventListener('click', () => closeDialog($<HTMLDialogElement>('#editor')!));
$('#bulk .close')!.addEventListener('click', () => closeDialog($<HTMLDialogElement>('#bulk')!));
for (const dialog of [$<HTMLDialogElement>('#detail')!, $<HTMLDialogElement>('#editor')!, $<HTMLDialogElement>('#bulk')!]) {
  dialog.addEventListener('click', (event) => { if (event.target === dialog) closeDialog(dialog); });
  dialog.addEventListener('keydown', (event) => trapFocus(dialog, event as KeyboardEvent));
}
$<MaterialForm>('#material-form')!.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget as MaterialForm;
  clearFieldErrors(form);
  const values: Record<string, unknown> = Object.fromEntries(new FormData(form).entries());
  const originalCode = values.original_code as string | undefined;
  delete values.original_code;
  values.density_g_cm3 = values.density_g_cm3 ? Number(values.density_g_cm3) : null;

  let hasError = false;
  if (!values.code || !(values.code as string).trim()) {
    setFieldError(form, 'code', 'Resin code is required');
    hasError = true;
  }
  if (!values.name || !(values.name as string).trim()) {
    setFieldError(form, 'name', 'Material name is required');
    hasError = true;
  }
  if (!values.source_title || (values.source_title as string).trim().length < 2) {
    setFieldError(form, 'source_title', 'Source title is required for factual records');
    hasError = true;
  }
  if (!values.source_url || !(values.source_url as string).trim().startsWith('https://')) {
    setFieldError(form, 'source_url', 'Source URL must start with https://');
    hasError = true;
  }
  if (!values.review_status || !['draft','verified'].includes(values.review_status as string)) {
    setFieldError(form, 'review_status', 'Review status must be draft or verified');
    hasError = true;
  }
  if (hasError) {
    toast('Please fix the highlighted fields');
    // Focus first invalid control
    const firstInvalid = form.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('[aria-invalid="true"]');
    firstInvalid?.focus();
    return;
  }
  try {
    const response = await fetch(originalCode ? `/api/v1/materials/${encodeURIComponent(originalCode)}` : '/api/v1/materials', {
      method: originalCode ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
    });
    const result: { detail?: string } = await response.json();
    if (!response.ok) throw new Error(result.detail || `Save failed (${response.status})`);
    invalidateCache();
    closeDialog($<HTMLDialogElement>('#editor')!);
    $<HTMLInputElement>('#search')!.value = '';
    await render();
    toast('Material saved to the library');
  } catch (error) { toast((error as Error).message); }
});

// Bulk import handler
$<HTMLButtonElement>('#bulk-submit')?.addEventListener('click', async () => {
  const input = $<HTMLInputElement>('#bulk-file')!;
  const status = $('#bulk-status')!;
  const results = $('#bulk-results')!;
  if (!input.files?.[0]) { toast('Select a CSV or JSON file'); return; }
  status.textContent = 'Uploading...';
  try {
    const file = input.files[0];
    const text = await file.text();
    const contentType = file.name.toLowerCase().endsWith('.json') ? 'application/json' : 'text/csv';
    const response = await fetch('/api/v1/materials/bulk', {
      method: 'POST',
      headers: { 'Content-Type': contentType },
      body: text,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Import failed ${response.status}`);
    invalidateCache();
    status.textContent = `Inserted ${data.inserted}, skipped ${data.skipped}`;
    results.textContent = JSON.stringify(data, null, 2);
    await render();
    toast('Bulk import complete');
  } catch (err) {
    status.textContent = 'Error';
    results.textContent = (err as Error).message;
    toast((err as Error).message);
  }
});

applyHash();
render();

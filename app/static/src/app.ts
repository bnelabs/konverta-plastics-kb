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
};
let view = 'overview';
let searchTimer: number | undefined;

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
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

function setView(next: string): void {
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

async function showMaterial(code: string): Promise<void> {
  try {
    const material = await get<MaterialDetail>(`/api/v1/materials/${encodeURIComponent(code)}`);
    const source = material.source_url
      ? `<a href="${esc(material.source_url)}" target="_blank" rel="noopener noreferrer">${esc(material.source_title || material.source_url)} ↗</a>`
      : '<span>Source not yet recorded</span>';
    $('#detail-body')!.innerHTML = `<div class="detail-inner"><div class="detail-kicker">Material profile · ${esc(material.code)}</div><h2 id="detail-title">${esc(material.name)}</h2><p class="lead">${esc(material.common_uses || 'Common uses have not yet been recorded.')}</p><div class="review-banner ${material.review_status === 'verified' ? 'verified' : ''}">${material.review_status === 'verified' ? 'Source reviewed' : 'Prototype data · verify before operational use'}</div><div class="detail-grid"><div class="detail-field"><small>Melting range</small><b>${esc(material.melt_temp_c || 'Not recorded')}</b></div><div class="detail-field"><small>Density</small><b>${material.density_g_cm3 ? `${esc(material.density_g_cm3)} g/cm³` : 'Not recorded'}</b></div><div class="detail-field"><small>Handling</small><b>${esc(material.toxicity_level || 'Not rated')}</b></div><div class="detail-field"><small>Recyclability</small><b>${esc(material.recyclability || 'Not recorded')}</b></div></div><div class="detail-block"><h3>Notes & handling</h3><p class="lead">${esc(material.notes || 'No notes have been recorded.')}</p></div><div class="detail-block"><h3>Process suitability</h3><div class="detail-list">${material.processes.length ? material.processes.map((item) => `<div class="detail-item"><b>${esc(item.name)} · ${esc(item.suitability_rating || 'Unrated')}</b><p>${esc(item.notes || item.description || '')}</p>${item.safety_precautions ? `<p><b>Safety:</b> ${esc(item.safety_precautions)}</p>` : ''}</div>`).join('') : '<p class="lead">No process suitability recorded. Treat as unknown.</p>'}</div></div><div class="detail-block"><h3>Related projects</h3><div class="detail-list">${material.projects.length ? material.projects.map((item) => `<div class="detail-item"><b>${esc(item.title)} · ${esc(item.difficulty || '')}</b><p>${esc(item.description || '')}</p></div>`).join('') : '<p class="lead">No projects linked yet.</p>'}</div></div><div class="detail-block source-block"><h3>Source</h3><p>${source}</p></div><div class="detail-block detail-actions"><span>Updates are stored with a history entry.</span><button id="edit-material" class="primary-button">Edit material</button></div></div>`;
    $<HTMLButtonElement>('#edit-material')!.addEventListener('click', () => { closeDialog($<HTMLDialogElement>('#detail')!); editMaterial(material); });
    openDialog($<HTMLDialogElement>('#detail')!);
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

document.querySelectorAll<HTMLElement>('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view!)));
$<HTMLInputElement>('#search')!.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(render, 160); });
$('#refresh')!.addEventListener('click', render);
$<HTMLButtonElement>('#bulk-import')?.addEventListener('click', () => toast('Bulk import UI coming soon. Use scripts/collect_facts.py for CSV import with source validation.'));
$('#detail .close')!.addEventListener('click', () => closeDialog($<HTMLDialogElement>('#detail')!));
$('#editor .close')!.addEventListener('click', () => closeDialog($<HTMLDialogElement>('#editor')!));
for (const dialog of [$<HTMLDialogElement>('#detail')!, $<HTMLDialogElement>('#editor')!]) {
  dialog.addEventListener('click', (event) => { if (event.target === dialog) closeDialog(dialog); });
  dialog.addEventListener('keydown', (event) => trapFocus(dialog, event as KeyboardEvent));
}
$<MaterialForm>('#material-form')!.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget as MaterialForm;
  const values: Record<string, unknown> = Object.fromEntries(new FormData(form).entries());
  const originalCode = values.original_code as string | undefined;
  delete values.original_code;
  values.density_g_cm3 = values.density_g_cm3 ? Number(values.density_g_cm3) : null;
  if (!values.source_title || (values.source_title as string).trim().length < 2) {
    toast('Source title is required for factual records');
    return;
  }
  if (!values.source_url || !(values.source_url as string).trim().startsWith('https://')) {
    toast('Source URL must start with https://');
    return;
  }
  if (!values.review_status || !['draft','verified'].includes(values.review_status as string)) {
    toast('Review status must be draft or verified');
    return;
  }
  try {
    const response = await fetch(originalCode ? `/api/v1/materials/${encodeURIComponent(originalCode)}` : '/api/v1/materials', {
      method: originalCode ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
    });
    const result: { detail?: string } = await response.json();
    if (!response.ok) throw new Error(result.detail || `Save failed (${response.status})`);
    closeDialog($<HTMLDialogElement>('#editor')!);
    $<HTMLInputElement>('#search')!.value = '';
    await render();
    toast('Material saved to the library');
  } catch (error) { toast((error as Error).message); }
});
render();

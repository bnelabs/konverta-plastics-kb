// @ts-nocheck
const $ = (selector) => document.querySelector(selector);
const labels = {
  overview: ['Overview', 'Materials, made useful.', 'A practical field guide to working with recycled plastics.'],
  materials: ['Materials', 'Know your material.', 'Explore common polymers, their uses, and handling notes.'],
  processes: ['Processes', 'From feedstock to form.', 'Compare practical recycling and upcycling methods.'],
  projects: ['Projects', 'Ideas for another life.', 'Browse practical concepts built around recovered materials.'],
};
let view = 'overview';
let searchTimer;

async function get(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function esc(value = '') {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function setView(next) {
  view = next;
  document.querySelectorAll('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  $('#breadcrumb').textContent = labels[view][0];
  $('#page-title').textContent = labels[view][1];
  $('#page-description').textContent = labels[view][2];
  render();
}

async function loadData() {
  const query = encodeURIComponent($('#search').value);
  const [materials, processes, projects, metrics] = await Promise.all([
    get(`/api/v1/materials?q=${query}`), get('/api/v1/processes'),
    get(`/api/v1/projects?q=${query}`), get('/api/v1/metrics'),
  ]);
  $('#version').textContent = `v${metrics.version}`;
  $('#nav-materials').textContent = metrics.records.materials;
  $('#stats').innerHTML = [
    ['Materials', metrics.records.materials, 'Polymer profiles'],
    ['Processes', metrics.records.processes, 'Methods and equipment'],
    ['Compatibility rules', metrics.records.compatibility, 'Recorded blend guidance'],
    ['Project concepts', metrics.records.projects, 'Starting points to explore'],
  ].map(([title, value, note]) => `<div class="stat"><div class="stat-top">${title}</div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></div>`).join('');
  return { materials, processes, projects };
}

async function render() {
  try {
    const data = await loadData();
    const query = $('#search').value.trim().toLowerCase();
    let html;
    if (view === 'overview' || view === 'materials') {
      const matches = data.materials;
      const shown = view === 'overview' ? matches.slice(0, 6) : matches;
      html = `<div class="section-title"><div><h2>${view === 'overview' ? 'Explore materials' : 'Material directory'}</h2><p>${matches.length} polymer ${matches.length === 1 ? 'profile' : 'profiles'} in the library</p></div><div class="section-actions">${view === 'overview' ? '<a class="text-link" data-goto="materials">View all materials <span aria-hidden="true">→</span></a>' : ''}<button class="text-link add-link" data-add-material><span aria-hidden="true">＋</span> Add material</button></div></div><div class="material-grid">${shown.map(materialCard).join('') || '<div class="empty">No materials match that search.</div>'}</div>`;
    } else if (view === 'processes') {
      const shown = data.processes.filter((item) => !query || JSON.stringify(item).toLowerCase().includes(query));
      html = `<div class="section-title"><div><h2>Recycling processes</h2><p>Methods, equipment, and safety notes</p></div></div><div class="process-grid">${shown.map((item) => `<article class="process-card"><h3>${esc(item.name)}</h3><p>${esc(item.description || '')}</p><p><b>Equipment</b> · ${esc(item.equipment_needed || 'Not recorded')}</p><div class="safety"><b>Safety</b> · ${esc(item.safety_precautions || 'Follow local safety guidance.')}</div></article>`).join('') || '<div class="empty">No processes match that search.</div>'}</div>`;
    } else {
      const shown = data.projects.filter((item) => !query || JSON.stringify(item).toLowerCase().includes(query));
      html = `<div class="section-title"><div><h2>Project ideas</h2><p>Concepts to validate and develop with the right expertise</p></div></div><div class="project-grid">${shown.map((item) => `<article class="project-card" data-project="${item.id}"><span class="badge">${esc(item.difficulty || 'Concept')}</span><h3>${esc(item.title)}</h3><p>${esc(item.description || '')}</p><div class="project-meta">${esc(item.material_code || 'Material not linked')} · ${esc(item.process_name || 'Process not linked')}</div></article>`).join('') || '<div class="empty">No projects match that search.</div>'}</div>`;
    }
    $('#content').innerHTML = html;
    document.querySelectorAll('[data-code]').forEach((card) => card.addEventListener('click', () => showMaterial(card.dataset.code)));
    document.querySelectorAll('[data-goto]').forEach((link) => link.addEventListener('click', () => setView(link.dataset.goto)));
    document.querySelectorAll('[data-project]').forEach((card) => card.addEventListener('click', () => showProject(Number(card.dataset.project))));
    document.querySelectorAll('[data-add-material]').forEach((button) => button.addEventListener('click', () => editMaterial()));
  } catch (error) {
    $('#content').innerHTML = `<div class="empty">The library could not be loaded. ${esc(error.message)} <button class="text-link" id="retry">Try again</button></div>`;
    $('#retry')?.addEventListener('click', render);
  }
}

function materialCard(material) {
  const needsReview = material.review_status !== 'verified';
  const risk = String(material.toxicity_level || 'Not rated').toLowerCase();
  const reviewClass = needsReview ? 'review-badge draft' : 'review-badge verified';
  const reviewText = needsReview ? 'Prototype data · verify' : 'Source checked';
  return `<button class="material-card" type="button" data-code="${esc(material.code)}"><div class="card-head"><span class="code-pill">${esc(material.code)}</span><span class="risk ${risk === 'high' ? 'high' : ''}">${esc(material.toxicity_level || 'Not rated')} handling</span></div><h3>${esc(material.name)}</h3><p>${esc(material.common_uses || 'No common uses recorded')}</p><div class="card-foot"><span class="${reviewClass}">${reviewText}</span><span>Melting range <b>${esc(material.melt_temp_c || 'Not recorded')}</b></span></div></button>`;
}

async function showMaterial(code) {
  try {
    const material = await get(`/api/v1/materials/${encodeURIComponent(code)}`);
    const source = material.source_url
      ? `<a href="${esc(material.source_url)}" target="_blank" rel="noopener noreferrer">${esc(material.source_title || material.source_url)} ↗</a>`
      : '<span>Source not yet recorded</span>';
    $('#detail-body').innerHTML = `<div class="detail-inner"><div class="detail-kicker">Material profile · ${esc(material.code)}</div><h2>${esc(material.name)}</h2><p class="lead">${esc(material.common_uses || 'Common uses have not yet been recorded.')}</p><div class="review-banner ${material.review_status === 'verified' ? 'verified' : ''}">${material.review_status === 'verified' ? 'Source reviewed' : 'Prototype data · verify before operational use'}</div><div class="detail-grid"><div class="detail-field"><small>Melting range</small><b>${esc(material.melt_temp_c || 'Not recorded')}</b></div><div class="detail-field"><small>Density</small><b>${material.density_g_cm3 ? `${esc(material.density_g_cm3)} g/cm³` : 'Not recorded'}</b></div><div class="detail-field"><small>Handling</small><b>${esc(material.toxicity_level || 'Not rated')}</b></div><div class="detail-field"><small>Recyclability</small><b>${esc(material.recyclability || 'Not recorded')}</b></div></div><div class="detail-block"><h3>Notes & handling</h3><p class="lead">${esc(material.notes || 'No notes have been recorded.')}</p></div><div class="detail-block"><h3>Process suitability</h3><div class="detail-list">${material.processes.length ? material.processes.map((item) => `<div class="detail-item"><b>${esc(item.name)} · ${esc(item.suitability_rating || 'Unrated')}</b><p>${esc(item.notes || item.description || '')}</p>${item.safety_precautions ? `<p><b>Safety:</b> ${esc(item.safety_precautions)}</p>` : ''}</div>`).join('') : '<p class="lead">No process suitability recorded. Treat as unknown.</p>'}</div></div><div class="detail-block"><h3>Related projects</h3><div class="detail-list">${material.projects.length ? material.projects.map((item) => `<div class="detail-item"><b>${esc(item.title)} · ${esc(item.difficulty || '')}</b><p>${esc(item.description || '')}</p></div>`).join('') : '<p class="lead">No projects linked yet.</p>'}</div></div><div class="detail-block source-block"><h3>Source</h3><p>${source}</p></div><div class="detail-block detail-actions"><span>Updates are stored with a history entry.</span><button id="edit-material" class="primary-button">Edit material</button></div></div>`;
    $('#edit-material').addEventListener('click', () => { $('#detail').close(); editMaterial(material); });
    $('#detail').showModal();
  } catch (error) { toast(error.message); }
}

async function showProject(id) {
  try {
    const project = (await get('/api/v1/projects')).find((item) => item.id === id);
    if (!project) return;
    $('#detail-body').innerHTML = `<div class="detail-inner"><div class="detail-kicker">Project concept · ${esc(project.difficulty || 'Concept')}</div><h2>${esc(project.title)}</h2><p class="lead">${esc(project.description || '')}</p><div class="detail-grid"><div class="detail-field"><small>Material</small><b>${esc(project.material_code || 'Not linked')}</b></div><div class="detail-field"><small>Process</small><b>${esc(project.process_name || 'Not linked')}</b></div></div><div class="detail-block"><h3>Starting steps</h3><p class="lead">${esc(project.instructions || 'No steps recorded.').replace(/\n/g, '<br>')}</p></div><div class="review-banner">Concept only · validate material, settings, ventilation, and product safety before use.</div></div>`;
    $('#detail').showModal();
  } catch (error) { toast(error.message); }
}

function editMaterial(material = null) {
  const form = $('#material-form');
  form.reset();
  form.elements.original_code.value = material?.code || '';
  $('#editor-title').textContent = material ? `Edit ${material.code}` : 'Add a material';
  if (material) Object.entries(material).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value ?? ''; });
  form.elements.review_status.value = material?.review_status || 'draft';
  $('#editor').showModal();
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 2800);
}

document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
$('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(render, 160); });
$('#refresh').addEventListener('click', render);
$('#detail .close').addEventListener('click', () => $('#detail').close());
$('#editor .close').addEventListener('click', () => $('#editor').close());
for (const dialog of [$('#detail'), $('#editor')]) dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
$('#material-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  const originalCode = values.original_code;
  delete values.original_code;
  values.density_g_cm3 = values.density_g_cm3 ? Number(values.density_g_cm3) : null;
  if (!values.source_title || values.source_title.trim().length < 2) {
    toast('Source title is required for factual records');
    return;
  }
  if (!values.source_url || !values.source_url.trim().startsWith('https://')) {
    toast('Source URL must start with https://');
    return;
  }
  if (!values.review_status || !['draft','verified'].includes(values.review_status)) {
    toast('Review status must be draft or verified');
    return;
  }
  try {
    const response = await fetch(originalCode ? `/api/v1/materials/${encodeURIComponent(originalCode)}` : '/api/v1/materials', {
      method: originalCode ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Save failed (${response.status})`);
    $('#editor').close();
    $('#search').value = '';
    await render();
    toast('Material saved to the library');
  } catch (error) { toast(error.message); }
});
render();

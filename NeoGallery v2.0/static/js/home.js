import { api, toast, thumbUrl, artUrl, coverUrl, hostOfEntry } from './api.js';
import { openModal, closeModal, confirmDialog } from './ui.js';
import { openTagModal } from './tag_modal.js';

let drafts = [];           // [{id, file, previewUrl, title, description, tags}]
let knownTags = [];        // [{name, coverPhoto, ...}]
let mediaCache = [];
let thumbWidth = 150;
const VALID_SORTS = new Set(['tag', 'date-desc', 'date-asc']);
let sortMode = VALID_SORTS.has(localStorage.getItem('sortMode')) ? localStorage.getItem('sortMode') : 'date-desc';
let selectedTags = new Set();

// ---------- global drop ----------
export function attachDropTarget() {
  const overlay = document.getElementById('drop-overlay');
  let depth = 0;
  const aModalIsOpen = () => !!document.querySelector('.modal:not([hidden])');

  window.addEventListener('dragenter', (e) => {
    if (aModalIsOpen()) return;
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes('Files')) return;
    depth++; overlay.hidden = false;
  });
  window.addEventListener('dragleave', () => {
    if (aModalIsOpen()) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) overlay.hidden = true;
  });
  window.addEventListener('dragover', (e) => { e.preventDefault(); });
  window.addEventListener('drop', (e) => {
    if (aModalIsOpen()) return;  // let in-modal drop zones handle their own drops
    e.preventDefault();
    depth = 0;
    overlay.hidden = true;
    const files = [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith('image/'));
    if (files.length) addDrafts(files);
  });

  const input = document.getElementById('hidden-file-input');
  input.addEventListener('change', (e) => {
    const files = [...(e.target.files || [])].filter(f => f.type.startsWith('image/'));
    if (files.length) addDrafts(files);
    input.value = '';
  });

  document.getElementById('close-upload').addEventListener('click', tryCloseUploadModal);
  document.getElementById('add-more-drafts').addEventListener('click', () => input.click());
  document.getElementById('submit-uploads').addEventListener('click', submitDrafts);
  document.getElementById('upload-modal').addEventListener('click', (e) => {
    if (e.target.id === 'upload-modal') tryCloseUploadModal();
  });

  // edit-modal backdrop click: close silently when previewing, do nothing when editing
  document.getElementById('edit-modal').addEventListener('click', (e) => {
    if (e.target.id !== 'edit-modal') return;
    if (document.getElementById('edit-modal').dataset.mode === 'preview') closeModal('edit-modal');
  });
}

async function tryCloseUploadModal() {
  if (drafts.length === 0) { closeModal('upload-modal'); return; }
  const ok = await confirmDialog({
    title: 'Cancel upload(s)?',
    message: `Discard ${drafts.length} pending post${drafts.length === 1 ? '' : 's'}? They won't be saved.`,
    okLabel: 'Discard',
  });
  if (!ok) return;
  drafts.forEach(d => URL.revokeObjectURL(d.previewUrl));
  drafts = [];
  renderDrafts();
  closeModal('upload-modal');
}

function addDrafts(files) {
  for (const file of files) {
    drafts.push({
      id: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
      title: '',
      description: '',
      tags: [],
    });
  }
  renderDrafts();
  openModal('upload-modal');
}

function renderDrafts() {
  const list = document.getElementById('draft-list');
  document.getElementById('draft-count').textContent = drafts.length ? `(${drafts.length})` : '';
  list.innerHTML = '';
  if (!drafts.length) {
    list.innerHTML = '<p class="muted">No files. Drop images on the window or click "Add more".</p>';
    return;
  }
  for (const d of drafts) list.appendChild(draftRow(d));
}

function draftRow(d) {
  const wrap = document.createElement('div');
  wrap.className = 'draft';

  const img = document.createElement('img');
  img.className = 'preview';
  img.src = d.previewUrl;
  wrap.appendChild(img);

  const fields = document.createElement('div');
  fields.className = 'fields';

  fields.appendChild(field('Title', input('text', d.title, v => d.title = v)));
  fields.appendChild(field('Description', textarea(d.description, v => d.description = v)));
  fields.appendChild(field('Tags', tagPicker(d)));

  wrap.appendChild(fields);

  const remove = document.createElement('button');
  remove.className = 'icon-btn remove';
  remove.textContent = '✕';
  remove.title = 'Remove from this batch';
  remove.addEventListener('click', () => {
    URL.revokeObjectURL(d.previewUrl);
    drafts = drafts.filter(x => x.id !== d.id);
    renderDrafts();
  });
  wrap.appendChild(remove);
  return wrap;
}

function field(label, control) {
  const w = document.createElement('div');
  const l = document.createElement('label');
  l.textContent = label;
  w.appendChild(l);
  w.appendChild(control);
  return w;
}

function input(type, value, onchange) {
  const el = document.createElement('input');
  el.type = type;
  el.value = value;
  el.addEventListener('input', () => onchange(el.value));
  return el;
}

function textarea(value, onchange) {
  const el = document.createElement('textarea');
  el.value = value;
  el.rows = 2;
  el.addEventListener('input', () => onchange(el.value));
  return el;
}

function tagPicker(d) {
  const wrap = document.createElement('div');
  wrap.className = 'col gap';

  const chips = document.createElement('div');
  chips.className = 'row gap';
  chips.style.flexWrap = 'wrap';

  for (const t of knownTags) {
    const chip = document.createElement('label');
    chip.className = 'check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = d.tags.includes(t.name);
    cb.addEventListener('change', () => {
      if (cb.checked) {
        if (!d.tags.includes(t.name)) d.tags.push(t.name);
      } else {
        d.tags = d.tags.filter(x => x !== t.name);
      }
    });
    chip.appendChild(cb);
    chip.appendChild(document.createTextNode(t.name));
    chips.appendChild(chip);
  }
  wrap.appendChild(chips);

  // new-tag chip on its own row below the checklist
  const newRow = document.createElement('div');
  newRow.style.marginTop = '8px';
  const newChip = document.createElement('span');
  newChip.className = 'new-tag-chip';
  newChip.textContent = '+ New tag';
  newChip.title = 'Create a new tag';
  newChip.addEventListener('click', () => {
    openTagModal(null, async () => {
      try { knownTags = await api.get('/api/tags'); } catch {}
      renderDrafts();
    });
  });
  newRow.appendChild(newChip);
  wrap.appendChild(newRow);

  return wrap;
}

async function submitDrafts() {
  if (!drafts.length) { toast('Drop some images first', 'error'); return; }
  const status = document.getElementById('upload-status');
  const btn = document.getElementById('submit-uploads');
  btn.disabled = true;
  status.textContent = 'Uploading...';

  const fd = new FormData();
  const meta = [];
  for (const d of drafts) {
    fd.append('files', d.file, d.file.name);
    meta.push({ title: d.title, description: d.description, tags: [...d.tags] });
  }
  fd.append('meta', JSON.stringify(meta));

  try {
    const res = await api.form('/api/media', fd);
    toast(`Uploaded ${res.count} item(s)`, 'success');
    status.textContent = '';
    drafts.forEach(d => URL.revokeObjectURL(d.previewUrl));
    drafts = [];
    renderDrafts();
    closeModal('upload-modal');
    await refreshGallery();
  } catch (e) {
    status.textContent = '';
    toast('Upload failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

// ---------- gallery (sections-by-tag) ----------
async function loadKnownTags() {
  knownTags = await api.get('/api/tags');
  try {
    const { config } = await api.get('/api/settings');
    thumbWidth = parseInt(config.thumb_width, 10) || 150;
  } catch {}
}

async function refreshGallery() {
  const [media, tags, settings] = await Promise.all([
    api.get('/api/media'),
    api.get('/api/tags'),
    api.get('/api/settings').catch(() => null),
  ]);
  mediaCache = media;
  knownTags = tags;
  if (settings?.config?.thumb_width) thumbWidth = parseInt(settings.config.thumb_width, 10) || thumbWidth;
  paintGallery();
}

// shared tag-checkbox picker used by the edit-post modal. wraps the chosen Set
// so the new-tag chip can rebuild itself in place after a tag is created.
function renderTagChecklist(container, chosen) {
  container.innerHTML = '';

  const chips = document.createElement('div');
  chips.className = 'row gap';
  chips.style.flexWrap = 'wrap';
  for (const t of knownTags) {
    const lab = document.createElement('label'); lab.className = 'check';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = chosen.has(t.name);
    cb.addEventListener('change', () => cb.checked ? chosen.add(t.name) : chosen.delete(t.name));
    lab.appendChild(cb); lab.appendChild(document.createTextNode(t.name));
    chips.appendChild(lab);
  }
  container.appendChild(chips);

  // new-tag chip lives on its own row below the checklist (where "include in random" used to be)
  const newRow = document.createElement('div');
  newRow.style.marginTop = '8px';
  const newChip = document.createElement('span');
  newChip.className = 'new-tag-chip';
  newChip.textContent = '+ New tag';
  newChip.title = 'Create a new tag';
  newChip.addEventListener('click', () => {
    openTagModal(null, async () => {
      try { knownTags = await api.get('/api/tags'); } catch {}
      renderTagChecklist(container, chosen);
    });
  });
  newRow.appendChild(newChip);
  container.appendChild(newRow);
}

function postMatchesFilter(entry) {
  if (!selectedTags.size) return true;
  return (entry.tags || []).some(t => selectedTags.has(t));
}

function paintGallery() {
  const wrap = document.getElementById('gallery-root');
  if (!wrap) return;
  wrap.innerHTML = '';

  // tag chip strip is always visible so "+ New tag" is reachable on a fresh install
  wrap.appendChild(tagsStrip());

  if (!mediaCache.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.innerHTML = '<h2>Your gallery is empty</h2><p>Drop images anywhere on the window to start.</p>';
    wrap.appendChild(empty);
    return;
  }

  if (sortMode === 'tag') {
    paintByTag(wrap);
  } else {
    paintFlat(wrap);
  }
}

function paintFlat(wrap) {
  let items = sortMode === 'date-asc' ? [...mediaCache] : [...mediaCache].reverse();
  items = items.filter(postMatchesFilter);

  if (!items.length) {
    wrap.appendChild(emptyFilter());
    return;
  }
  const grid = makeGrid();
  for (const entry of items) grid.appendChild(galleryItem(entry));
  wrap.appendChild(grid);
}

function makeGrid() {
  const grid = document.createElement('div');
  grid.className = 'gallery-grid';
  grid.style.gridTemplateColumns = `repeat(auto-fill, ${thumbWidth}px)`;
  return grid;
}

function paintByTag(wrap) {
  // newest-first within each section
  const ordered = [...mediaCache].reverse();
  const definedNames = new Set(knownTags.map(t => t.name));
  const adhoc = new Set();
  for (const e of ordered) for (const t of e.tags || []) if (!definedNames.has(t)) adhoc.add(t);

  let sections = [
    ...knownTags.map(t => ({ tag: t, name: t.name })),
    ...[...adhoc].sort().map(name => ({ tag: null, name })),
  ];
  // when filtering, only render sections for selected tags
  if (selectedTags.size) sections = sections.filter(s => selectedTags.has(s.name));

  let renderedAny = false;
  for (const s of sections) {
    const items = ordered.filter(e => (e.tags || []).includes(s.name));
    if (!items.length && !s.tag) continue;
    wrap.appendChild(tagSection(s.tag, s.name, items));
    renderedAny = true;
  }
  // untagged only shown when no filter is active
  if (!selectedTags.size) {
    const untagged = ordered.filter(e => !(e.tags || []).length);
    if (untagged.length) {
      wrap.appendChild(tagSection(null, '(untagged)', untagged, { untagged: true }));
      renderedAny = true;
    }
  }
  if (!renderedAny) wrap.appendChild(emptyFilter());
}

function emptyFilter() {
  const empty = document.createElement('div');
  empty.className = 'empty';
  if (selectedTags.size) {
    empty.innerHTML = `<h2>No posts match</h2><p>No posts have ${[...selectedTags].map(t => '#' + t).join(' or ')}.</p>`;
  } else {
    empty.innerHTML = '<h2>No posts yet</h2><p>Drop images anywhere on the window to start.</p>';
  }
  return empty;
}

function tagsStrip() {
  const strip = document.createElement('div');
  strip.className = 'tag-strip';

  const label = document.createElement('span');
  label.className = 'muted';
  label.textContent = 'Tags:';
  strip.appendChild(label);

  for (const t of knownTags) {
    strip.appendChild(tagChip(t));
  }

  if (selectedTags.size) {
    const clear = document.createElement('button');
    clear.className = 'btn small ghost';
    clear.textContent = 'Clear filter';
    clear.addEventListener('click', () => { selectedTags.clear(); paintGallery(); });
    strip.appendChild(clear);
  }

  // + new tag chip pinned to the far right
  const newChip = document.createElement('span');
  newChip.className = 'new-tag-chip';
  newChip.textContent = '+ New tag';
  newChip.title = 'Create a new tag';
  newChip.style.marginLeft = 'auto';
  newChip.addEventListener('click', () => openTagModal(null, refreshGallery));
  strip.appendChild(newChip);

  return strip;
}

function tagChip(t) {
  const chip = document.createElement('span');
  chip.className = 'tag-chip' + (selectedTags.has(t.name) ? ' selected' : '');

  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = `#${t.name}`;
  label.addEventListener('click', () => {
    if (selectedTags.has(t.name)) selectedTags.delete(t.name);
    else selectedTags.add(t.name);
    paintGallery();
  });
  chip.appendChild(label);

  const edit = document.createElement('button');
  edit.className = 'icon-btn tiny';
  edit.textContent = '✎';
  edit.title = `Edit #${t.name}`;
  edit.addEventListener('click', (e) => {
    e.stopPropagation();
    openTagModal(t, refreshGallery);
  });
  chip.appendChild(edit);

  return chip;
}

function tagSection(tagDef, name, items, opts = {}) {
  const sec = document.createElement('section');
  sec.className = 'tag-section';

  const head = document.createElement('div');
  head.className = 'tag-section-head';

  const left = document.createElement('div');
  left.className = 'row gap';
  if (tagDef && tagDef.coverPhoto) {
    const c = document.createElement('img');
    c.className = 'tag-section-cover';
    c.src = coverUrl(tagDef);
    left.appendChild(c);
  }
  const titleWrap = document.createElement('div');
  const h2 = document.createElement('h2');
  h2.textContent = opts.untagged ? name : `#${name}`;
  titleWrap.appendChild(h2);
  const sub = document.createElement('div');
  sub.className = 'muted';
  sub.style.fontSize = '12px';
  sub.textContent = `${items.length} post${items.length === 1 ? '' : 's'}` + (tagDef?.linkTitle ? ` · ${tagDef.linkTitle}` : '');
  titleWrap.appendChild(sub);
  left.appendChild(titleWrap);

  const right = document.createElement('div');
  right.className = 'row gap';
  if (tagDef) {
    const edit = document.createElement('button');
    edit.className = 'icon-btn'; edit.textContent = '✎'; edit.title = `Edit #${name}`;
    edit.addEventListener('click', () => openTagModal(tagDef, refreshGallery));
    right.appendChild(edit);
  } else if (!opts.untagged) {
    const promote = document.createElement('button');
    promote.className = 'btn small ghost';
    promote.textContent = 'Define this tag';
    promote.title = 'Posts use this tag, but it has no proper definition yet';
    promote.addEventListener('click', () => openTagModal({ name, metaDesc: '', pageTitle: name, linkTitle: name, coverPhoto: '' }, refreshGallery));
    right.appendChild(promote);
  }

  head.appendChild(left);
  head.appendChild(right);
  sec.appendChild(head);

  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'No posts here yet.';
    sec.appendChild(empty);
  } else {
    const grid = makeGrid();
    for (const entry of items) grid.appendChild(galleryItem(entry));
    sec.appendChild(grid);
  }
  return sec;
}

function galleryItem(entry) {
  const el = document.createElement('div');
  el.className = 'gallery-item';
  el.dataset.src = entry.fullSrc;

  const img = document.createElement('img');
  img.className = 'thumb';
  img.src = thumbUrl(entry);
  img.loading = 'lazy';
  img.addEventListener('click', () => openImagePreview(entry));
  el.appendChild(img);

  const meta = document.createElement('div');
  meta.className = 'meta';
  const title = document.createElement('div');
  title.className = 'title';
  title.textContent = entry.title || '(untitled)';
  meta.appendChild(title);

  const tagLine = document.createElement('div');
  tagLine.className = 'tags';
  const badge = document.createElement('span');
  badge.className = 'host-badge';
  badge.textContent = hostOfEntry(entry);
  tagLine.appendChild(badge);
  if (entry.tags?.length) {
    tagLine.appendChild(document.createTextNode(' · ' + entry.tags.join(', ')));
  }
  meta.appendChild(tagLine);
  el.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'actions';
  const edit = document.createElement('button');
  edit.className = 'icon-btn'; edit.textContent = '✎'; edit.title = 'Edit';
  edit.addEventListener('click', e => { e.stopPropagation(); openEditModal(entry); });
  actions.appendChild(edit);
  const del = document.createElement('button');
  del.className = 'icon-btn'; del.textContent = '🗑'; del.title = 'Delete';
  del.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (!await confirmDialog({
      title: 'Delete post',
      message: `Delete "${entry.title || entry.fullSrc}"? Removes it locally, from the host, and from the live gallery.`,
    })) return;
    try {
      await api.del('/api/media', { fullSrc: entry.fullSrc });
      toast('Deleted', 'success');
      await refreshGallery();
    } catch (err) { toast('Delete failed: ' + err.message, 'error'); }
  });
  actions.appendChild(del);
  el.appendChild(actions);
  return el;
}

function openImagePreview(entry) {
  const modal = document.getElementById('edit-modal');
  modal.dataset.mode = 'preview';
  document.getElementById('edit-modal-title').textContent = '';
  document.getElementById('edit-foot').hidden = true;

  const body = document.getElementById('edit-body');
  body.innerHTML = '';

  const img = document.createElement('img');
  img.src = artUrl(entry);
  img.addEventListener('error', () => { img.src = thumbUrl(entry); }, { once: true });
  img.style.maxWidth = '100%';
  img.style.maxHeight = '70vh';
  img.style.display = 'block';
  img.style.margin = '0 auto';
  body.appendChild(img);

  if (entry.title) {
    const h = document.createElement('h3');
    h.textContent = entry.title;
    h.style.marginTop = '12px';
    body.appendChild(h);
  }
  if (entry.description) {
    const p = document.createElement('p');
    p.textContent = entry.description;
    body.appendChild(p);
  }

  // jump straight to the edit form
  const editBtn = document.createElement('button');
  editBtn.className = 'btn primary';
  editBtn.textContent = '✎ Edit post';
  editBtn.style.marginTop = '14px';
  editBtn.addEventListener('click', () => openEditModal(entry));
  body.appendChild(editBtn);

  document.getElementById('close-edit').onclick = () => closeModal('edit-modal');
  openModal('edit-modal');
}

function openEditModal(entry) {
  const modal = document.getElementById('edit-modal');
  modal.dataset.mode = 'edit';
  document.getElementById('edit-modal-title').textContent = 'Edit post';
  document.getElementById('edit-foot').hidden = false;

  const body = document.getElementById('edit-body');
  body.innerHTML = '';

  // photo at the top so the user knows what they're editing
  const photoWrap = document.createElement('div');
  photoWrap.className = 'edit-photo';
  const photo = document.createElement('img');
  photo.src = artUrl(entry);
  photo.addEventListener('error', () => { photo.src = thumbUrl(entry); }, { once: true });
  photo.addEventListener('click', () => window.open(artUrl(entry), '_blank'));
  photo.title = 'Click to open full size';
  photoWrap.appendChild(photo);
  body.appendChild(photoWrap);

  const titleEl = document.createElement('input'); titleEl.type = 'text'; titleEl.value = entry.title || '';
  const descEl = document.createElement('textarea'); descEl.value = entry.description || '';
  const tagsEl = document.createElement('div');
  const chosen = new Set(entry.tags || []);
  renderTagChecklist(tagsEl, chosen);
  body.appendChild(wrapField('Title', titleEl));
  body.appendChild(wrapField('Description', descEl));
  body.appendChild(wrapField('Tags', tagsEl));

  document.getElementById('edit-save').textContent = 'Save';
  document.getElementById('edit-cancel').onclick = () => closeModal('edit-modal');
  document.getElementById('close-edit').onclick = () => closeModal('edit-modal');
  document.getElementById('edit-save').onclick = async () => {
    try {
      await api.patch('/api/media', {
        fullSrc: entry.fullSrc,
        title: titleEl.value,
        description: descEl.value,
        tags: [...chosen],
      });
      toast('Saved', 'success');
      closeModal('edit-modal');
      await refreshGallery();
    } catch (e) { toast('Save failed: ' + e.message, 'error'); }
  };
  openModal('edit-modal');
}

function wrapField(label, control) {
  const w = document.createElement('div');
  w.className = 'form-row';
  const l = document.createElement('label');
  l.textContent = label;
  w.appendChild(l); w.appendChild(control);
  return w;
}

// ---------- public render ----------
export async function renderHome(root) {
  await loadKnownTags();

  const head = document.createElement('div');
  head.className = 'home-head';
  const h1 = document.createElement('h1'); h1.textContent = 'Gallery';
  const actions = document.createElement('div'); actions.className = 'row gap';

  const sortLabel = document.createElement('label');
  sortLabel.className = 'inline-label muted';
  sortLabel.textContent = 'Sort by';
  sortLabel.style.marginBottom = '0';
  const sortSel = document.createElement('select');
  sortSel.className = 'sort-select';
  for (const [v, label] of [
    ['date-desc', 'Date ↓ (newest first)'],
    ['date-asc', 'Date ↑ (oldest first)'],
    ['tag', 'Tag'],
  ]) {
    const o = document.createElement('option');
    o.value = v; o.textContent = label;
    if (v === sortMode) o.selected = true;
    sortSel.appendChild(o);
  }
  sortSel.addEventListener('change', () => {
    sortMode = sortSel.value;
    localStorage.setItem('sortMode', sortMode);
    paintGallery();
  });
  actions.appendChild(sortLabel);
  actions.appendChild(sortSel);

  const pickBtn = document.createElement('button');
  pickBtn.className = 'btn primary';
  pickBtn.textContent = '+ New post';
  pickBtn.addEventListener('click', () => document.getElementById('hidden-file-input').click());
  actions.appendChild(pickBtn);

  head.appendChild(h1); head.appendChild(actions);
  root.appendChild(head);

  const hint = document.createElement('div');
  hint.className = 'home-hint';
  hint.innerHTML = '<strong>Drop images anywhere</strong> to start a new post.';
  root.appendChild(hint);

  const gallery = document.createElement('div');
  gallery.id = 'gallery-root';
  root.appendChild(gallery);

  await refreshGallery();
}

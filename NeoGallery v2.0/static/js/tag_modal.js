import { api, toast, coverUrl } from './api.js';
import { openModal, closeModal, confirmDialog } from './ui.js';

const SYSTEM_TAGS = new Set(['random']);

let stagedCover = null;

export function openTagModal(existing, onSaved) {
  stagedCover = null;
  const isEdit = !!existing;
  const isSystem = isEdit && SYSTEM_TAGS.has(existing.name);

  document.getElementById('tag-modal-title').textContent =
    isSystem ? `#${existing.name} (built-in)` :
    isEdit ? `Edit tag: ${existing.name}` : 'New tag';
  const body = document.getElementById('tag-body');
  body.innerHTML = '';

  if (isSystem) {
    return renderSystemTag(existing, onSaved);
  }

  const fields = {
    name: textInput('Tag name (no spaces)', isEdit ? existing.name : ''),
    metaDesc: textInput('Meta description', isEdit ? (existing.metaDesc || '') : ''),
    pageTitle: textInput('Page title', isEdit ? (existing.pageTitle || '') : ''),
    linkTitle: textInput('Link title (shown on gallery index)', isEdit ? (existing.linkTitle || '') : ''),
  };
  Object.values(fields).forEach(f => body.appendChild(f.row));

  const coverRow = document.createElement('div');
  coverRow.className = 'form-row';
  const coverLabel = document.createElement('label');
  coverLabel.textContent = 'Cover photo (optional)';
  coverRow.appendChild(coverLabel);

  const dropZone = document.createElement('div');
  dropZone.className = 'cover-drop';

  const preview = document.createElement('img');
  preview.className = 'cover-preview';
  preview.hidden = true;
  const hint = document.createElement('div');
  hint.className = 'cover-hint';
  hint.innerHTML = '<strong>Drop an image here</strong><br><span class="muted">or click to choose</span>';

  if (isEdit && existing.coverPhoto) {
    preview.src = coverUrl(existing);
    preview.hidden = false;
    hint.innerHTML = '<span class="muted">Drop a new image or click to replace</span>';
  }

  const file = document.createElement('input');
  file.type = 'file'; file.accept = 'image/*'; file.hidden = true;

  function stage(f) {
    stagedCover = f;
    preview.src = URL.createObjectURL(f);
    preview.hidden = false;
    hint.innerHTML = `<span class="muted">${f.name} — drop or click to replace</span>`;
  }

  file.addEventListener('change', () => {
    const f = file.files[0];
    if (f) stage(f);
  });
  dropZone.addEventListener('click', () => file.click());
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const f = [...(e.dataTransfer?.files || [])].find(x => x.type.startsWith('image/'));
    if (f) stage(f);
  });

  dropZone.appendChild(preview);
  dropZone.appendChild(hint);
  dropZone.appendChild(file);
  coverRow.appendChild(dropZone);
  body.appendChild(coverRow);

  // edit mode gets a "danger zone" with delete-tag tucked away inside the modal
  if (isEdit) {
    const danger = document.createElement('div');
    danger.className = 'danger-zone';
    const dl = document.createElement('label');
    dl.textContent = 'Danger zone';
    danger.appendChild(dl);
    const delBtn = document.createElement('button');
    delBtn.className = 'btn danger';
    delBtn.textContent = `Delete #${existing.name}`;
    delBtn.addEventListener('click', async () => {
      const ok = await confirmDialog({
        title: 'Delete tag',
        message: `Delete "#${existing.name}"? Removes the tag page on Neocities and unlinks it from every post. This cannot be undone.`,
      });
      if (!ok) return;
      try {
        await api.del(`/api/tags/${encodeURIComponent(existing.name)}`);
        toast('Deleted', 'success');
        closeModal('tag-modal');
        onSaved && onSaved();
      } catch (e) {
        toast('Delete failed: ' + e.message, 'error');
      }
    });
    danger.appendChild(delBtn);
    body.appendChild(danger);
  }

  document.getElementById('tag-cancel').onclick = () => closeModal('tag-modal');
  document.getElementById('close-tag').onclick = () => closeModal('tag-modal');
  document.getElementById('tag-save').onclick = async () => {
    const fd = new FormData();
    fd.append('name', fields.name.input.value.trim());
    fd.append('metaDesc', fields.metaDesc.input.value);
    fd.append('pageTitle', fields.pageTitle.input.value);
    fd.append('linkTitle', fields.linkTitle.input.value);
    if (stagedCover) fd.append('cover', stagedCover);
    if (!fd.get('name')) { toast('Name required', 'error'); return; }
    try {
      if (isEdit) {
        await api.form(`/api/tags/${encodeURIComponent(existing.name)}`, fd, 'PUT');
      } else {
        await api.form('/api/tags', fd);
      }
      toast('Saved', 'success');
      closeModal('tag-modal');
      onSaved && onSaved();
    } catch (e) {
      toast('Save failed: ' + e.message, 'error');
    }
  };
  openModal('tag-modal');
}

function textInput(label, value) {
  const row = document.createElement('div'); row.className = 'form-row';
  const l = document.createElement('label'); l.textContent = label;
  const input = document.createElement('input'); input.type = 'text'; input.value = value;
  row.appendChild(l); row.appendChild(input);
  return { row, input };
}

function renderSystemTag(existing, onSaved) {
  const body = document.getElementById('tag-body');
  body.innerHTML = '';
  const p = document.createElement('p');
  p.className = 'muted';
  p.style.lineHeight = '1.5';
  p.innerHTML = `<strong>#${existing.name}</strong> is a built-in tag — the visitor gallery uses it to show a shuffled selection of posts. It doesn't have a page, cover, or other settings.<br><br>Check it on any post to include that post in the shuffle.`;
  body.appendChild(p);

  const danger = document.createElement('div');
  danger.className = 'danger-zone';
  const dl = document.createElement('label'); dl.textContent = 'Danger zone';
  danger.appendChild(dl);
  const delBtn = document.createElement('button');
  delBtn.className = 'btn danger';
  delBtn.textContent = `Delete #${existing.name}`;
  delBtn.addEventListener('click', async () => {
    const ok = await confirmDialog({
      title: 'Delete tag',
      message: `Delete the built-in "#${existing.name}" tag? You can recreate it later via "+ New tag".`,
    });
    if (!ok) return;
    try {
      await api.del(`/api/tags/${encodeURIComponent(existing.name)}`);
      toast('Deleted', 'success');
      closeModal('tag-modal');
      onSaved && onSaved();
    } catch (e) {
      toast('Delete failed: ' + e.message, 'error');
    }
  });
  danger.appendChild(delBtn);
  body.appendChild(danger);

  // hide the footer's Save button — nothing to save for a system tag
  document.getElementById('tag-cancel').onclick = () => closeModal('tag-modal');
  document.getElementById('close-tag').onclick = () => closeModal('tag-modal');
  const saveBtn = document.getElementById('tag-save');
  saveBtn.style.display = 'none';
  // restore on close so regular tag editing still works
  const restore = () => { saveBtn.style.display = ''; };
  document.getElementById('tag-cancel').addEventListener('click', restore, { once: true });
  document.getElementById('close-tag').addEventListener('click', restore, { once: true });
  delBtn.addEventListener('click', restore, { once: true });

  openModal('tag-modal');
}

// shared modal helpers

export function openModal(id) {
  document.getElementById(id).hidden = false;
}
export function closeModal(id) {
  document.getElementById(id).hidden = true;
}

export function confirmDialog({ title = 'Confirm', message = 'Are you sure?', okLabel = 'Delete', danger = true }) {
  return new Promise(resolve => {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');
    okBtn.textContent = okLabel;
    okBtn.className = 'btn ' + (danger ? 'danger' : 'primary');
    const cleanup = () => { okBtn.onclick = null; cancelBtn.onclick = null; closeModal('confirm-modal'); };
    okBtn.onclick = () => { cleanup(); resolve(true); };
    cancelBtn.onclick = () => { cleanup(); resolve(false); };
    openModal('confirm-modal');
  });
}

// install-feed row + ascii spinner, shared by onboarding / settings / sync

export const SPINNER_FRAMES = ['-', '\\', '|', '/'];
let spinnerTimer = null;
let spinnerTick = 0;

export function runSpinner() {
  if (spinnerTimer) return;
  spinnerTimer = setInterval(() => {
    spinnerTick = (spinnerTick + 1) % SPINNER_FRAMES.length;
    const live = document.querySelectorAll('.install-row.uploading .icon');
    if (!live.length) { clearInterval(spinnerTimer); spinnerTimer = null; return; }
    const ch = SPINNER_FRAMES[spinnerTick];
    live.forEach(el => { el.textContent = ch; });
  }, 120);
}

export function feedRow(klass, icon, file, note) {
  const r = document.createElement('div'); r.className = 'install-row ' + klass;
  const i = document.createElement('span'); i.className = 'icon'; i.textContent = icon;
  const p = document.createElement('span'); p.className = 'path'; p.textContent = file;
  const n = document.createElement('span'); n.className = 'note'; n.textContent = note;
  r.appendChild(i); r.appendChild(p); r.appendChild(n);
  return r;
}

export function setFeedRow(row, klass, icon, file, note) {
  row.className = 'install-row ' + klass;
  row.children[0].textContent = icon;
  row.children[1].textContent = file;
  row.children[2].textContent = note;
}

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

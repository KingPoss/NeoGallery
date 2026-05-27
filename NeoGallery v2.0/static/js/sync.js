import { api, toast } from './api.js';
import { openModal, closeModal, confirmDialog, SPINNER_FRAMES, runSpinner, feedRow, setFeedRow } from './ui.js';

const DRIFT_DISMISS_KEY = 'sync.driftDismissed';

// the only public entry point -- used from settings, the drift toast, and the wizard
export async function runSyncFlow({ confirmOverwrite = true, onDone } = {}) {
  let state;
  try {
    state = await api.get('/api/sync/state');
  } catch (e) {
    toast('Sync failed: ' + e.message, 'error');
    return;
  }
  if (!state.ok) {
    toast(state.message || 'Could not reach Neocities', 'error');
    return;
  }

  if (confirmOverwrite && state.local_posts > 0) {
    const ok = await confirmDialog({
      title: 'Replace local gallery?',
      message: `Local has ${state.local_posts} post${state.local_posts === 1 ? '' : 's'}; the site has ${state.remote_posts}. Local data will be overwritten with what's on Neocities. Files already downloaded will be reused.`,
      okLabel: 'Sync',
      danger: false,
    });
    if (!ok) return;
  }

  await runSyncWithFeed(onDone);
}

async function runSyncWithFeed(onDone) {
  // open the sync modal + render header
  const modal = document.getElementById('sync-modal');
  if (!modal) return;
  document.getElementById('sync-modal-title').textContent = 'Syncing from Neocities';
  const closeBtn = document.getElementById('sync-modal-close');
  closeBtn.style.display = 'none';  // hide until done
  const list = document.getElementById('sync-list');
  list.innerHTML = '';
  const status = document.getElementById('sync-status');
  status.textContent = 'Connecting...';
  openModal('sync-modal');

  const rows = new Map();
  await new Promise(resolve => {
    const es = new EventSource('/api/sync/stream');
    es.onmessage = ev => {
      let d; try { d = JSON.parse(ev.data); } catch { return; }
      if (d.done) {
        es.close();
        if (d.fatal) {
          status.textContent = 'Failed: ' + d.fatal;
          toast('Sync failed: ' + d.fatal, 'error');
        } else {
          const s = d.summary || {};
          if (s.errors) {
            status.textContent = `Pulled ${s.pulled}, ${s.errors} error(s).`;
            toast(`Synced with ${s.errors} error(s)`, 'error');
          } else {
            status.textContent = `Pulled ${s.pulled} file(s). ${s.skipped} already present.`;
            toast(`Sync complete -- pulled ${s.pulled} file(s)`, 'success');
            sessionStorage.removeItem(DRIFT_DISMISS_KEY);
          }
        }
        closeBtn.style.display = '';
        if (onDone) onDone();
        resolve();
        return;
      }
      const { file, status: st, note } = d;
      let r = rows.get(file);
      if (!r) {
        r = feedRow('uploading', SPINNER_FRAMES[0], file, 'pulling...');
        rows.set(file, r);
        list.appendChild(r);
        list.scrollTo(0, list.scrollHeight);
        runSpinner();
      }
      if (st === 'uploading') {
        setFeedRow(r, 'uploading', SPINNER_FRAMES[0], file, 'pulling...');
        status.textContent = `Pulling ${file}`;
      } else if (st === 'uploaded') {
        setFeedRow(r, 'uploaded', '✓', file, 'pulled');
      } else if (st === 'skipped') {
        setFeedRow(r, 'skipped', '--', file, note || 'already present');
      } else if (st === 'error') {
        setFeedRow(r, 'error', '✗', file, note || 'error');
      }
    };
    es.onerror = () => {
      es.close();
      status.textContent = 'Connection dropped.';
      closeBtn.style.display = '';
      resolve();
    };
  });
}

// fires on every launch (when configured + onboarded), shows a sticky toast
// when local/remote post counts disagree
export async function checkSyncDrift() {
  if (sessionStorage.getItem(DRIFT_DISMISS_KEY)) return;
  try {
    const { completed } = await api.get('/api/onboarding/status');
    if (!completed) return;
  } catch { return; }
  let state;
  try {
    state = await api.get('/api/sync/state');
  } catch { return; }
  if (!state.ok) return;
  if (state.in_sync) return;

  // build a sticky action-toast
  const root = document.getElementById('toasts');
  if (!root) return;
  const el = document.createElement('div');
  el.className = 'toast action';
  const msg = document.createElement('div');
  msg.innerHTML = `<strong>Out of sync with Neocities</strong><br>` +
    `<span class="muted">Site has ${state.remote_posts} post${state.remote_posts === 1 ? '' : 's'}, ` +
    `this machine has ${state.local_posts}.</span>`;
  el.appendChild(msg);

  const actions = document.createElement('div');
  actions.className = 'row gap';
  actions.style.marginTop = '8px';

  const syncBtn = document.createElement('button');
  syncBtn.className = 'btn primary small';
  syncBtn.textContent = 'Sync now';
  syncBtn.addEventListener('click', () => {
    el.remove();
    runSyncFlow();
  });
  actions.appendChild(syncBtn);

  const dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn ghost small';
  dismissBtn.textContent = 'Dismiss';
  dismissBtn.addEventListener('click', () => {
    sessionStorage.setItem(DRIFT_DISMISS_KEY, '1');
    el.remove();
  });
  actions.appendChild(dismissBtn);

  el.appendChild(actions);
  root.appendChild(el);
}

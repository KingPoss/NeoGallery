import { api, toast } from './api.js';
import { renderHome, attachDropTarget } from './home.js';
import { renderSettings } from './settings.js';

// apply cached theme immediately so we don't flash the wrong colors on launch
const cachedTheme = localStorage.getItem('theme');
if (cachedTheme === 'dark' || cachedTheme === 'light') {
  document.documentElement.dataset.theme = cachedTheme;
}

const views = {
  home: renderHome,
  settings: renderSettings,
};

function currentView() {
  const hash = (location.hash || '#home').slice(1).split('?')[0];
  return views[hash] ? hash : 'home';
}

function setActiveTab(name) {
  document.querySelectorAll('.tab').forEach(el => {
    el.classList.toggle('active', el.dataset.view === name);
  });
}

async function route() {
  const name = currentView();
  setActiveTab(name);
  const root = document.getElementById('view');
  root.innerHTML = '';
  try {
    await views[name](root);
  } catch (e) {
    console.error(e);
    toast('Failed to load view: ' + e.message, 'error');
  }
}

async function refreshHostPill() {
  try {
    const { config, hosts } = await api.get('/api/settings');
    const active = hosts.find(h => h.id === config.active_image_host);
    document.getElementById('active-host-pill').textContent = active ? `→ ${active.name}` : '--';
    // re-apply theme so we don't stay on the hardcoded default until Settings opens
    const theme = config.dark_mode ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('theme', theme);
  } catch (e) { console.warn(e); }
}
window.refreshHostPill = refreshHostPill;

async function refreshBrand() {
  const el = document.getElementById('brand-name');
  if (!el) return;
  try {
    const info = await api.get('/api/neocities/info');
    if (info.ok && info.domain) {
      const name = info.domain.endsWith('.neocities.org') ? info.domain.replace(/\.neocities\.org$/, '') : info.domain;
      el.textContent = `${name}'s gallery`;
      return;
    }
  } catch (e) { console.warn(e); }
  el.textContent = 'Gallery';
}
window.refreshBrand = refreshBrand;

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', async () => {
  attachDropTarget();
  refreshHostPill();
  refreshBrand();

  // first run: open onboarding before routing
  try {
    const { completed } = await api.get('/api/onboarding/status');
    if (!completed) {
      const m = await import('./onboarding.js');
      m.startOnboarding(() => {
        refreshHostPill();
        refreshBrand();
        if (!location.hash) location.hash = '#home'; else route();
      });
      return;
    }
  } catch (e) { console.warn(e); }

  if (!location.hash) location.hash = '#home';
  else route();

  // fire after first render so a slow check never blocks the UI
  import('./sync.js').then(m => m.checkSyncDrift());
});

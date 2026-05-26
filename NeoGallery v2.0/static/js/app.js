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
    document.getElementById('active-host-pill').textContent = active ? `→ ${active.name}` : '—';
    // also apply the theme — otherwise it stays at the hardcoded HTML default until Settings is opened
    const theme = config.dark_mode ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('theme', theme);
  } catch {}
}
window.refreshHostPill = refreshHostPill;

window.addEventListener('hashchange', route);
document.addEventListener('DOMContentLoaded', async () => {
  attachDropTarget();
  refreshHostPill();

  // show onboarding wizard before anything else on first run
  try {
    const { completed } = await api.get('/api/onboarding/status');
    if (!completed) {
      const m = await import('./onboarding.js');
      m.startOnboarding(() => {
        refreshHostPill();
        if (!location.hash) location.hash = '#home'; else route();
      });
      return;
    }
  } catch {}

  if (!location.hash) location.hash = '#home';
  else route();
});

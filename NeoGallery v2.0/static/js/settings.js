import { api, toast } from './api.js';

export async function renderSettings(root) {
  const { config, hosts } = await api.get('/api/settings');

  const h1 = document.createElement('h1'); h1.textContent = 'Settings';
  root.appendChild(h1);

  // active host
  const hostCard = card('Active image host', 'Where new uploads go. Site files (HTML/JSON) always live on Neocities.');
  const hostSelect = document.createElement('select');
  for (const h of hosts) {
    const o = document.createElement('option');
    o.value = h.id; o.textContent = h.name;
    if (h.id === config.active_image_host) o.selected = true;
    hostSelect.appendChild(o);
  }
  hostSelect.addEventListener('change', async () => {
    await save({ active_image_host: hostSelect.value });
    window.refreshHostPill?.();
  });
  const hostRow = document.createElement('div'); hostRow.className = 'form-row';
  hostRow.appendChild(hostSelect);
  hostCard.appendChild(hostRow);
  root.appendChild(hostCard);

  // thumbnails
  const thumbCard = card('Thumbnails');
  const widthInput = numberInput('Width (px)', config.thumb_width, 50, 800, async v => save({ thumb_width: v }));
  thumbCard.appendChild(widthInput);
  const regenBtn = btn('Regenerate all thumbnails', 'primary', async () => {
    regenBtn.disabled = true;
    regenBtn.textContent = 'Regenerating...';
    try {
      const { regenerated } = await api.post('/api/media/regenerate-thumbs', {});
      toast(`Regenerated ${regenerated} thumbnails`, 'success');
    } catch (e) { toast('Failed: ' + e.message, 'error'); }
    regenBtn.disabled = false;
    regenBtn.textContent = 'Regenerate all thumbnails';
  });
  thumbCard.appendChild(regenBtn);
  root.appendChild(thumbCard);

  // neocities
  const neoCard = card('Neocities');
  neoCard.appendChild(passwordInput('API key', config.neocities.api_key, v => save({ neocities: { api_key: v } })));
  const grid = document.createElement('div'); grid.className = 'settings-grid';
  for (const [k, label] of [
    ['art_dir', 'Art dir'], ['thumb_dir', 'Thumb dir'], ['json_dir', 'JSON dir'],
    ['tag_dir', 'Tag pages dir'], ['gallery_dir', 'Gallery dir'],
  ]) {
    grid.appendChild(textRow(label, config.neocities[k], v => save({ neocities: { [k]: v } })));
  }
  neoCard.appendChild(grid);
  root.appendChild(neoCard);

  // catbox
  const catCard = card('Catbox', 'Userhash is optional. Leave blank for anonymous uploads (cannot be deleted via the API later).');
  catCard.appendChild(passwordInput('Userhash', config.catbox.userhash, v => save({ catbox: { userhash: v } })));
  root.appendChild(catCard);

  // appearance
  const themeCard = card('Appearance');
  const darkRow = document.createElement('label'); darkRow.className = 'check';
  const dark = document.createElement('input'); dark.type = 'checkbox'; dark.checked = !!config.dark_mode;
  dark.addEventListener('change', () => {
    const t = dark.checked ? 'dark' : 'light';
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
    save({ dark_mode: dark.checked });
  });
  document.documentElement.dataset.theme = config.dark_mode ? 'dark' : 'light';
  darkRow.appendChild(dark); darkRow.appendChild(document.createTextNode(' Dark mode'));
  themeCard.appendChild(darkRow);
  root.appendChild(themeCard);

  // maintenance
  const maintCard = card('Maintenance');
  const importBtn = btn('Import data from v1.0', 'ghost', async () => {
    try {
      const r = await api.post('/api/import-v1', {});
      toast(`Imported ${r.media} media, ${r.tags} tags`, 'success');
    } catch (e) { toast('Failed: ' + e.message, 'error'); }
  });
  maintCard.appendChild(importBtn);

  const wizardBtn = btn('Run setup wizard again', 'ghost', async () => {
    try {
      await api.post('/api/onboarding/reset', {});
      const m = await import('./onboarding.js');
      m.startOnboarding(() => location.hash = '#home');
    } catch (e) { toast('Failed: ' + e.message, 'error'); }
  });
  wizardBtn.style.marginLeft = '8px';
  maintCard.appendChild(wizardBtn);

  root.appendChild(maintCard);
}

async function save(patch) {
  try {
    await api.put('/api/settings', patch);
    toast('Saved', 'success');
  } catch (e) { toast('Save failed: ' + e.message, 'error'); }
}

function card(title, subtitle) {
  const c = document.createElement('section'); c.className = 'card';
  const h = document.createElement('h2'); h.textContent = title;
  c.appendChild(h);
  if (subtitle) {
    const p = document.createElement('p'); p.className = 'muted'; p.textContent = subtitle; p.style.marginTop = '4px';
    c.appendChild(p);
  }
  return c;
}

function textRow(label, value, onchange) {
  const w = document.createElement('div'); w.className = 'form-row';
  const l = document.createElement('label'); l.textContent = label;
  const input = document.createElement('input'); input.type = 'text'; input.value = value || '';
  input.addEventListener('change', () => onchange(input.value));
  w.appendChild(l); w.appendChild(input);
  return w;
}

function passwordInput(label, value, onchange) {
  const w = document.createElement('div'); w.className = 'form-row';
  const l = document.createElement('label'); l.textContent = label;
  const row = document.createElement('div'); row.className = 'row gap';
  const input = document.createElement('input'); input.type = 'password'; input.value = value || ''; input.style.flex = '1';
  input.addEventListener('change', () => onchange(input.value));
  const toggle = document.createElement('button'); toggle.className = 'btn ghost small'; toggle.textContent = 'show';
  toggle.addEventListener('click', () => {
    input.type = input.type === 'password' ? 'text' : 'password';
    toggle.textContent = input.type === 'password' ? 'show' : 'hide';
  });
  row.appendChild(input); row.appendChild(toggle);
  w.appendChild(l); w.appendChild(row);
  return w;
}

function numberInput(label, value, min, max, onchange) {
  const w = document.createElement('div'); w.className = 'form-row inline';
  const l = document.createElement('label'); l.textContent = label;
  const input = document.createElement('input'); input.type = 'number'; input.value = value; input.min = min; input.max = max;
  input.style.width = '100px';
  input.addEventListener('change', () => onchange(parseInt(input.value, 10) || value));
  w.appendChild(l); w.appendChild(input);
  return w;
}

function btn(label, kind, onclick) {
  const b = document.createElement('button');
  b.className = 'btn ' + kind;
  b.textContent = label;
  b.addEventListener('click', onclick);
  b.style.marginTop = '8px';
  return b;
}

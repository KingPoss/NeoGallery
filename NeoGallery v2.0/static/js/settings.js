import { api, toast } from './api.js';
import { runSpinner, feedRow, setFeedRow } from './ui.js';

export async function renderSettings(root) {
  const { config, hosts } = await api.get('/api/settings');

  const h1 = document.createElement('h1'); h1.textContent = 'Settings';
  root.appendChild(h1);

  root.appendChild(await galleryCard(config));
  root.appendChild(hostingCard(config, hosts));
  root.appendChild(appearanceCard(config));
  root.appendChild(maintenanceCard());
}

// ---------- cards ----------

async function galleryCard(config) {
  const c = card('Gallery', 'How your gallery looks to visitors on your live site.');

  // local mirror of the gallery settings so the pending-changes indicator
  // can diff against the last-applied snapshot without re-fetching every keystroke
  const current = {
    use_thumbnails: !!config.use_thumbnails,
    thumb_width: config.thumb_width,
    full_image_display_width: config.full_image_display_width,
    loading_image: config.show_loader ? (config.loading_image || '') : '',
    show_loader: !!config.show_loader,
  };
  const lastApplied = config.last_applied_gallery_state || {};
  let indicatorEl = null;  // wired up below; updateIndicator() rebuilds its contents

  // ---------- thumbnails ----------
  c.appendChild(subsection('Thumbnails'));

  const thumbToggle = checkRow('Use thumbnails', !!config.use_thumbnails);
  c.appendChild(thumbToggle.row);

  const widthOn = numberInput('Width (px)', config.thumb_width, 50, 800, async v => {
    if (v === current.thumb_width) return;  // no-op if value unchanged on blur
    current.thumb_width = v; updateIndicator();
    await save({ thumb_width: v });
    if (current.use_thumbnails) runRegen();
  });
  c.appendChild(widthOn);

  const widthOff = numberInput('Display full image at width (px)', config.full_image_display_width, 50, 2000, async v => {
    current.full_image_display_width = v; updateIndicator();
    await save({ full_image_display_width: v });
  });
  c.appendChild(widthOff);

  const syncThumbVisibility = (on) => {
    widthOn.hidden = !on;
    widthOff.hidden = on;
  };
  syncThumbVisibility(!!config.use_thumbnails);
  thumbToggle.cb.addEventListener('change', async () => {
    const turningOn = thumbToggle.cb.checked && !current.use_thumbnails;
    current.use_thumbnails = thumbToggle.cb.checked;
    syncThumbVisibility(thumbToggle.cb.checked);
    updateIndicator();
    await save({ use_thumbnails: thumbToggle.cb.checked });
    if (turningOn) runRegen();
  });

  // ---------- throbber ----------
  c.appendChild(subsection('Throbber'));

  const hint = document.createElement('p');
  hint.className = 'muted'; hint.style.fontSize = '12px'; hint.style.margin = '0 0 8px';
  hint.textContent = "The animated graphic shown briefly while the gallery loads. Old-school web term, very Geocities.";
  c.appendChild(hint);

  const row = document.createElement('div'); row.className = 'row gap';
  const sel = document.createElement('select'); sel.style.flex = '1';
  row.appendChild(sel);

  const preview = document.createElement('img');
  preview.className = 'throbber-preview'; preview.hidden = true;
  row.appendChild(preview);

  const fileInput = document.createElement('input'); fileInput.type = 'file'; fileInput.accept = 'image/*,image/gif'; fileInput.hidden = true;
  const uploadBtn = btn('Upload custom throbber...', 'ghost', () => fileInput.click());
  uploadBtn.classList.add('small');
  row.appendChild(uploadBtn);
  row.appendChild(fileInput);
  c.appendChild(row);

  async function refillThrobberOptions(selectedPath) {
    sel.innerHTML = '';
    const { loaders } = await api.get('/api/site/loaders');
    const lookup = new Map();
    for (const l of loaders) {
      lookup.set(l.path, l);
      const o = document.createElement('option');
      o.value = l.path; o.textContent = l.name;
      if (l.path === selectedPath) o.selected = true;
      sel.appendChild(o);
    }
    const noneOpt = document.createElement('option');
    noneOpt.value = ''; noneOpt.textContent = 'None -- show image as it loads';
    if (!selectedPath) noneOpt.selected = true;
    sel.appendChild(noneOpt);
    // preview via dedicated endpoint so we don't fight Flask's static routing
    updatePreviewFor(selectedPath, lookup);
  }

  function updatePreviewFor(path, lookup) {
    if (!path) { preview.hidden = true; preview.removeAttribute('src'); return; }
    preview.src = `/api/site/loader-preview?path=${encodeURIComponent(path)}`;
    preview.hidden = false;
  }

  await refillThrobberOptions(config.show_loader ? config.loading_image : '');

  sel.addEventListener('change', async () => {
    const v = sel.value;
    if (!v) {
      current.show_loader = false; current.loading_image = '';
      updateIndicator();
      await save({ show_loader: false });
      updatePreviewFor('', null);
    } else {
      current.show_loader = true; current.loading_image = v;
      updateIndicator();
      await save({ show_loader: true, loading_image: v });
      updatePreviewFor(v, null);
    }
  });

  fileInput.addEventListener('change', async () => {
    const f = fileInput.files[0];
    if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try {
      const res = await api.form('/api/site/loader/upload', fd);
      await refillThrobberOptions(res.path);
      current.show_loader = true; current.loading_image = res.path;
      updateIndicator();
      await save({ show_loader: true, loading_image: res.path });
      toast(`Throbber added: ${res.name}`, 'success');
    } catch (e) {
      toast('Upload failed: ' + e.message, 'error');
    }
    fileInput.value = '';
  });

  // ---------- republish ----------
  c.appendChild(subsection('Publish'));

  const applyHint = document.createElement('p');
  applyHint.className = 'muted'; applyHint.style.fontSize = '12px'; applyHint.style.margin = '0 0 8px';
  applyHint.textContent = "Re-render and re-upload the gallery pages so changes above take effect on the live site.";
  c.appendChild(applyHint);

  const applyRow = document.createElement('div');
  applyRow.className = 'row gap';
  applyRow.style.alignItems = 'center';
  applyRow.style.flexWrap = 'wrap';

  const applyBtn = btn('Apply changes (republish gallery)', 'primary', () => runRepublish());
  applyRow.appendChild(applyBtn);

  indicatorEl = document.createElement('span');
  indicatorEl.className = 'pending-indicator-wrap';
  applyRow.appendChild(indicatorEl);

  c.appendChild(applyRow);

  // expandable list of diff lines (toggled by the "(?)" link inside the indicator)
  const pendingPanel = document.createElement('div');
  pendingPanel.className = 'pending-panel';
  pendingPanel.hidden = true;
  c.appendChild(pendingPanel);

  // streaming republish progress feed below the button
  const feed = document.createElement('div');
  feed.className = 'install-list';
  feed.style.marginTop = '10px';
  c.appendChild(feed);

  // restore the last in-process republish report so persisted errors stay visible
  // even if the user navigated away and came back
  try {
    const last = await api.get('/api/site/republish/last');
    if (last.present && (last.errors?.length || 0) > 0) {
      paintFeedFromReport(feed, last);
    }
  } catch {}

  updateIndicator();

  // ---------- closures (have to live here so they can see current/feed/indicatorEl) ----------

  function updateIndicator() {
    if (!indicatorEl) return;
    const diff = diffPending(current, lastApplied);
    indicatorEl.innerHTML = '';
    pendingPanel.hidden = true;
    pendingPanel.innerHTML = '';
    if (!diff.length) return;

    const dot = document.createElement('span'); dot.className = 'pending-dot'; dot.textContent = '●';
    indicatorEl.appendChild(dot);
    const text = document.createTextNode(` Live site has ${diff.length} pending change${diff.length === 1 ? '' : 's'} `);
    indicatorEl.appendChild(text);
    const q = document.createElement('a');
    q.className = 'pending-q'; q.href = '#'; q.textContent = '(?)';
    q.addEventListener('click', e => {
      e.preventDefault();
      if (pendingPanel.hidden) {
        renderPendingPanel(pendingPanel, diff);
        pendingPanel.hidden = false;
      } else {
        pendingPanel.hidden = true;
      }
    });
    indicatorEl.appendChild(q);
  }

  async function runRegen() {
    const pill = openStatusPill('Regenerating thumbnails...');
    let total = 0;
    await new Promise(resolve => {
      const es = new EventSource('/api/media/regenerate-thumbs/stream');
      es.onmessage = ev => {
        let d; try { d = JSON.parse(ev.data); } catch { return; }
        if (d.done) {
          es.close();
          if (d.fatal) {
            pill.close();
            toast('Regenerate failed: ' + d.fatal, 'error');
          } else if (d.count === 0) {
            pill.close();  // no posts → nothing to show
          } else {
            pill.update(`Regenerated ${d.count} thumbnails`);
            setTimeout(() => pill.close(), 1800);
          }
          resolve();
          return;
        }
        if (d.total) total = d.total;
        if (d.status === 'uploading') {
          pill.update(`Regenerating ${d.index} of ${total} thumbnails...`);
        }
      };
      es.onerror = () => { es.close(); pill.close(); resolve(); };
    });
  }

  async function runRepublish() {
    applyBtn.disabled = true;
    const orig = applyBtn.textContent;
    applyBtn.textContent = 'Republishing...';
    feed.innerHTML = '';
    const rows = new Map();

    await new Promise(resolve => {
      const es = new EventSource('/api/site/republish/stream');
      let errors = 0;
      es.onmessage = ev => {
        let d; try { d = JSON.parse(ev.data); } catch { return; }
        if (d.done) {
          es.close();
          if (d.fatal) {
            toast('Republish failed: ' + d.fatal, 'error');
          } else {
            const ok = d.summary?.uploaded ?? 0;
            const errs = d.summary?.errors ?? 0;
            if (errs) {
              toast(`Republished ${ok} files, ${errs} error(s)`, 'error');
            } else {
              toast(`Republished ${ok} files`, 'success');
              // success → snapshot moved server-side; pull fresh config and clear diff
              Object.assign(lastApplied, current);
              updateIndicator();
              // auto-clear the feed after a beat so the card stays uncluttered
              setTimeout(() => { feed.innerHTML = ''; }, 3000);
            }
          }
          resolve();
          return;
        }
        const { file, status, note } = d;
        let row = rows.get(file);
        if (!row) {
          row = feedRow('uploading', '-', file, 'uploading...');
          rows.set(file, row);
          feed.appendChild(row);
        }
        if (status === 'uploading') {
          setFeedRow(row, 'uploading', '-', file, 'uploading...');
          runSpinner();
        } else if (status === 'uploaded') {
          setFeedRow(row, 'uploaded', '✓', file, 'uploaded');
        } else if (status === 'error') {
          setFeedRow(row, 'error', '✗', file, note || 'error');
          errors++;
        }
      };
      es.onerror = () => { es.close(); resolve(); };
    });

    applyBtn.disabled = false;
    applyBtn.textContent = orig;
  }

  return c;
}

function hostingCard(config, hosts) {
  const c = card('Hosting', 'Where new uploads go and how files get published.');

  // ---------- image host ----------
  c.appendChild(subsection('Image host'));

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
  c.appendChild(hostRow);

  const hostHint = document.createElement('p');
  hostHint.className = 'muted'; hostHint.style.fontSize = '12px'; hostHint.style.margin = '4px 0 0';
  hostHint.textContent = "Site files (HTML, JSON) always go to Neocities. Image host only affects new art uploads.";
  c.appendChild(hostHint);

  // ---------- neocities ----------
  c.appendChild(subsection('Neocities'));
  c.appendChild(passwordInput('API key', config.neocities.api_key, v => save({ neocities: { api_key: v } })));

  const adv = document.createElement('details');
  adv.className = 'settings-advanced';
  const summary = document.createElement('summary');
  summary.textContent = 'Advanced -- remote folders';
  adv.appendChild(summary);

  const advHint = document.createElement('p');
  advHint.className = 'muted'; advHint.style.fontSize = '12px'; advHint.style.margin = '0 0 8px';
  advHint.textContent = "Set once via the wizard. Change only if you've moved files around manually on Neocities.";
  adv.appendChild(advHint);

  const grid = document.createElement('div'); grid.className = 'settings-grid';
  for (const [k, label] of [
    ['gallery_dir', 'Gallery dir'],
    ['tag_dir', 'Tag pages dir'],
    ['art_dir', 'Art dir'],
    ['thumb_dir', 'Thumb dir'],
    ['json_dir', 'JSON dir'],
  ]) {
    grid.appendChild(textRow(label, config.neocities[k], v => save({ neocities: { [k]: v } })));
  }
  adv.appendChild(grid);
  c.appendChild(adv);

  // ---------- catbox ----------
  c.appendChild(subsection('Catbox'));
  const catHint = document.createElement('p');
  catHint.className = 'muted'; catHint.style.fontSize = '12px'; catHint.style.margin = '0 0 8px';
  catHint.textContent = "Userhash is optional. Leave blank for anonymous uploads (cannot be deleted via API later).";
  c.appendChild(catHint);
  c.appendChild(passwordInput('Userhash', config.catbox.userhash, v => save({ catbox: { userhash: v } })));

  return c;
}

function appearanceCard(config) {
  const c = card('Appearance', 'The desktop app itself.');
  const darkRow = checkRow('Dark mode', !!config.dark_mode);
  darkRow.cb.addEventListener('change', () => {
    const t = darkRow.cb.checked ? 'dark' : 'light';
    document.documentElement.dataset.theme = t;
    localStorage.setItem('theme', t);
    save({ dark_mode: darkRow.cb.checked });
  });
  c.appendChild(darkRow.row);
  return c;
}

function maintenanceCard() {
  const c = card('Maintenance');
  const row = document.createElement('div'); row.className = 'row gap';
  row.style.flexWrap = 'wrap';

  const syncBtn = btn('Sync from Neocities', 'ghost', async () => {
    const m = await import('./sync.js');
    m.runSyncFlow();
  });
  row.appendChild(syncBtn);

  const importBtn = btn('Import data from v1.0', 'ghost', async () => {
    try {
      const r = await api.post('/api/import-v1', {});
      toast(`Imported ${r.media} media, ${r.tags} tags`, 'success');
    } catch (e) { toast('Failed: ' + e.message, 'error'); }
  });
  row.appendChild(importBtn);

  const wizardBtn = btn('Run setup wizard again', 'ghost', async () => {
    try {
      await api.post('/api/onboarding/reset', {});
      const m = await import('./onboarding.js');
      m.startOnboarding(() => location.hash = '#home');
    } catch (e) { toast('Failed: ' + e.message, 'error'); }
  });
  row.appendChild(wizardBtn);

  c.appendChild(row);
  return c;
}

// ---------- helpers ----------

async function save(patch) {
  try {
    await api.put('/api/settings', patch);
  } catch (e) { toast('Save failed: ' + e.message, 'error'); }
}

function card(title, subtitle) {
  const c = document.createElement('section'); c.className = 'card';
  const h = document.createElement('h2'); h.textContent = title;
  c.appendChild(h);
  if (subtitle) {
    const p = document.createElement('p'); p.className = 'muted'; p.textContent = subtitle;
    p.style.margin = '4px 0 0'; p.style.fontSize = '12px';
    c.appendChild(p);
  }
  return c;
}

function subsection(title) {
  const h = document.createElement('h3');
  h.className = 'settings-subsection';
  h.textContent = title;
  return h;
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

function checkRow(label, checked) {
  const row = document.createElement('label'); row.className = 'check';
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = checked;
  row.appendChild(cb); row.appendChild(document.createTextNode(' ' + label));
  return { row, cb };
}

function btn(label, kind, onclick) {
  const b = document.createElement('button');
  b.className = 'btn ' + kind;
  b.textContent = label;
  b.addEventListener('click', onclick);
  return b;
}

// ---------- pending-changes diff ----------

const PENDING_LABELS = {
  use_thumbnails: 'Use thumbnails',
  thumb_width: 'Width',
  full_image_display_width: 'Full-image width',
  loading_image: 'Throbber',
  show_loader: 'Throbber shown',
};

function _fmtVal(key, v) {
  if (v === undefined || v === null || v === '') return '(none)';
  if (key === 'use_thumbnails' || key === 'show_loader') return v ? 'on' : 'off';
  if (key === 'loading_image') return String(v).split('/').pop().replace(/\.[^.]+$/, '');
  if (key.endsWith('_width') || key === 'thumb_width') return `${v} px`;
  return String(v);
}

function diffPending(current, lastApplied) {
  // empty lastApplied means we've never republished -- surface every set field
  const baselineKeys = Object.keys(lastApplied);
  const out = [];
  for (const k of Object.keys(current)) {
    const a = lastApplied[k];
    const b = current[k];
    if (!baselineKeys.length || a !== b) {
      out.push({ key: k, label: PENDING_LABELS[k] || k, from: _fmtVal(k, a), to: _fmtVal(k, b) });
    }
  }
  return out;
}

function renderPendingPanel(panel, diff) {
  panel.innerHTML = '';
  for (const row of diff) {
    const r = document.createElement('div');
    r.className = 'pending-row';
    r.innerHTML = `<span class="pending-label">${row.label}</span><span class="pending-arrow">${row.from} → <strong>${row.to}</strong></span>`;
    panel.appendChild(r);
  }
}

function paintFeedFromReport(feed, report) {
  feed.innerHTML = '';
  for (const path of (report.uploaded || [])) feed.appendChild(feedRow('uploaded', '✓', path, 'uploaded'));
  for (const path of (report.skipped  || [])) feed.appendChild(feedRow('skipped',  '--', path, 'already exists'));
  for (const err  of (report.errors   || [])) feed.appendChild(feedRow('error',    '✗', err.file, err.error));
}

// ---------- status pill (bottom-right floating) ----------

let _statusPill = null;
function openStatusPill(text) {
  if (!_statusPill) {
    _statusPill = document.createElement('div');
    _statusPill.className = 'status-pill';
    document.body.appendChild(_statusPill);
  }
  _statusPill.textContent = text;
  _statusPill.hidden = false;
  return {
    update: (t) => { if (_statusPill) _statusPill.textContent = t; },
    close: () => { if (_statusPill) { _statusPill.hidden = true; } },
  };
}

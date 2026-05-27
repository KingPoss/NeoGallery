import { api, toast } from './api.js';
import { SPINNER_FRAMES, runSpinner, feedRow, setFeedRow } from './ui.js';

const STEPS = ['welcome', 'connect', 'verify', 'install', 'done'];
let stepIdx = 0;
let onFinish = null;
let siteDomain = '';   // captured in step 3, used to build the live URL preview in step 4

export function startOnboarding(onFinishCb) {
  onFinish = onFinishCb || (() => {});
  stepIdx = 0;
  document.getElementById('onboarding').hidden = false;
  document.getElementById('onboarding-skip').onclick = (e) => { e.preventDefault(); skip(); };
  renderStep();
}

function renderDots() {
  const wrap = document.getElementById('onboarding-steps');
  wrap.innerHTML = '';
  STEPS.forEach((_, i) => {
    const dot = document.createElement('div');
    dot.className = 'dot' + (i < stepIdx ? ' done' : i === stepIdx ? ' active' : '');
    wrap.appendChild(dot);
  });
}

function renderStep() {
  renderDots();
  const body = document.getElementById('onboarding-body');
  body.innerHTML = '';
  ({
    welcome: stepWelcome,
    connect: stepConnect,
    verify: stepVerify,
    install: stepInstall,
    done: stepDone,
  })[STEPS[stepIdx]](body);
}

function next() { stepIdx = Math.min(STEPS.length - 1, stepIdx + 1); renderStep(); }
function back() { stepIdx = Math.max(0, stepIdx - 1); renderStep(); }
function goTo(name) { stepIdx = STEPS.indexOf(name); renderStep(); }

async function skip() {
  try { await api.post('/api/onboarding/complete', {}); } catch {}
  close();
}

function close() {
  document.getElementById('onboarding').hidden = true;
  if (onFinish) onFinish();
}

// ---------- step 1: welcome ----------
function stepWelcome(body) {
  body.innerHTML = `
    <h1>Welcome to NeoGallery</h1>
    <p>This app manages your art gallery on Neocities. We'll get you connected and install the gallery template on your site in under a minute.</p>
  `;
  body.appendChild(actions([primary('Get started', next)]));
}

// ---------- step 2: connect ----------
function stepConnect(body) {
  body.innerHTML = `
    <h1>Connect to Neocities</h1>
    <p>Paste your Neocities API key. You can find it under <em>Settings → Manage Site Settings → API</em> on neocities.org.</p>
  `;

  const row = document.createElement('div'); row.className = 'form-row';
  const lab = document.createElement('label'); lab.textContent = 'API key';
  const input = document.createElement('input'); input.type = 'password'; input.placeholder = 'paste here';
  input.autocomplete = 'off';
  row.appendChild(lab); row.appendChild(input);
  body.appendChild(row);

  // prefill if user already has one saved
  api.get('/api/settings').then(({ config }) => {
    if (config?.neocities?.api_key) input.value = config.neocities.api_key;
  }).catch(() => {});

  const result = document.createElement('div'); result.className = 'test-result';
  body.appendChild(result);

  const nextBtn = primary('Next', async () => {
    const key = input.value.trim();
    if (!key) {
      result.className = 'test-result err';
      result.textContent = 'Paste your key first.';
      return;
    }
    nextBtn.disabled = true;
    result.className = 'test-result';
    result.textContent = 'Saving...';
    try {
      await api.put('/api/settings', { neocities: { api_key: key } });
      next();
    } catch (e) {
      result.className = 'test-result err';
      result.textContent = 'Save failed: ' + e.message;
      nextBtn.disabled = false;
    }
  });

  body.appendChild(actions([
    ghost('Back', back),
    nextBtn,
  ]));
}

// ---------- step 3: verify ----------
function stepVerify(body) {
  body.innerHTML = `<h1>Checking your site...</h1>`;

  api.get('/api/neocities/info').then(info => {
    body.innerHTML = '';
    if (!info.ok) {
      body.innerHTML = `<h1>Couldn't reach Neocities</h1><p class="muted">${escapeHtml(info.message || 'Unknown error')}</p><p>Double-check your API key.</p>`;
      body.appendChild(actions([ghost('Back to API key', () => goTo('connect'))]));
      return;
    }

    siteDomain = info.domain;

    const h1 = document.createElement('h1');
    h1.textContent = 'Is this you?';
    body.appendChild(h1);

    const card = document.createElement('div');
    card.className = 'site-confirm';
    const big = document.createElement('div');
    big.className = 'site-confirm-domain';
    big.textContent = info.domain;
    card.appendChild(big);
    if (info.domain !== `${info.sitename}.neocities.org`) {
      const sub = document.createElement('div');
      sub.className = 'site-confirm-sub';
      sub.textContent = `Neocities account: ${info.sitename}`;
      card.appendChild(sub);
    }
    body.appendChild(card);

    body.appendChild(actions([
      ghost('No, wrong key', () => goTo('connect')),
      primary('Yes, that\'s me', next),
    ]));
  }).catch(e => {
    body.innerHTML = `<h1>Couldn't reach Neocities</h1><p class="muted">${escapeHtml(e.message)}</p>`;
    body.appendChild(actions([ghost('Back to API key', () => goTo('connect'))]));
  });
}

// ---------- step 4: install ----------
function stepInstall(body) {
  body.innerHTML = `<h1>Checking your site...</h1>`;

  // if NeoGallery is already installed on this site, offer to sync instead of reinstalling
  api.get('/api/sync/state').then(state => {
    if (state.ok && state.detected) {
      renderInstallOrSyncFork(body, state);
    } else {
      renderInstallPrompt(body);
    }
  }).catch(() => renderInstallPrompt(body));
}

function renderInstallOrSyncFork(body, state) {
  body.innerHTML = '';
  const h1 = document.createElement('h1');
  h1.textContent = 'NeoGallery is already on this site';
  body.appendChild(h1);
  const p = document.createElement('p');
  p.innerHTML = `Found <strong>${state.remote_posts}</strong> post${state.remote_posts === 1 ? '' : 's'} ` +
    `at <code>${escapeHtml(state.suggested_dirs?.gallery_dir || '(root)')}</code> on your site. ` +
    `You can pull everything to this machine instead of starting fresh.`;
  body.appendChild(p);

  body.appendChild(actions([
    ghost('Install fresh anyway', () => renderInstallPrompt(body)),
    primary('Sync existing site', async () => {
      // apply the detected dirs so subsequent sync + future republishes target the right place
      if (state.suggested_dirs) {
        try { await api.put('/api/settings', { neocities: state.suggested_dirs }); } catch {}
      }
      const sync = await import('./sync.js');
      sync.runSyncFlow({ confirmOverwrite: false, onDone: () => {
        // mark onboarding complete and close the wizard once the modal is dismissed
        api.post('/api/onboarding/complete', {}).catch(() => {});
        close();
      } });
    }),
  ]));
}

function renderInstallPrompt(body) {
  body.innerHTML = '';
  const h1 = document.createElement('h1'); h1.textContent = 'Install gallery files?';
  body.appendChild(h1);
  const p = document.createElement('p');
  p.textContent = "We'll upload the gallery template (HTML, CSS, JS, starter JSON) to a folder on your site. Anything already on Neocities stays untouched.";
  body.appendChild(p);

  // first prompt: yes / no
  const choiceRow = actions([
    ghost("No thanks, I'll do it later", () => goTo('done')),
    primary('Yes, install', () => revealInstallForm()),
  ]);
  body.appendChild(choiceRow);

  function revealInstallForm() {
    body.innerHTML = '';
    const h = document.createElement('h1'); h.textContent = 'Where on your site?';
    body.appendChild(h);
    const hint = document.createElement('p');
    hint.innerHTML = "Pick a folder. Default is <code>NeoGallery</code>. You can rename it or nest it deeper, like <code>art/portfolio</code> or <code>my-gallery</code>.";
    body.appendChild(hint);

    const row = document.createElement('div'); row.className = 'form-row';
    const lab = document.createElement('label'); lab.textContent = 'Install path (relative to site root)';
    const input = document.createElement('input');
    input.type = 'text';
    input.value = 'NeoGallery';
    input.spellcheck = false;
    row.appendChild(lab); row.appendChild(input);
    body.appendChild(row);

    const preview = document.createElement('p');
    preview.className = 'muted'; preview.style.fontSize = '12px';
    body.appendChild(preview);

    let currentUrl = '';
    const updatePreview = () => {
      const p = (input.value || '').trim().replace(/^\/+|\/+$/g, '');
      if (!p) {
        currentUrl = '';
        preview.textContent = '(install path required)';
        return;
      }
      const prefix = siteDomain ? `${siteDomain}/` : '';
      currentUrl = `https://${prefix}${p}/NeoGallery.html`;
      preview.innerHTML = '';
      preview.appendChild(document.createTextNode('Visitor URL will be '));
      const link = document.createElement('a');
      link.href = currentUrl; link.className = 'external-link';
      link.textContent = `${prefix}${p}/NeoGallery.html`;
      link.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentUrl) api.post('/api/open', { url: currentUrl }).catch(() => {});
      });
      preview.appendChild(link);
    };
    input.addEventListener('input', updatePreview);
    updatePreview();

    const list = document.createElement('div'); list.className = 'install-list';
    body.appendChild(list);

    // single button morphs: Install -> (working) -> Next
    let installed = false;
    const backBtn = ghost('Back', back);
    const actionBtn = primary('Install', async () => {
      if (installed) { next(); return; }

      const pathRaw = (input.value || '').trim().replace(/^\/+|\/+$/g, '');
      if (!pathRaw) { toast('Pick a path first', 'error'); return; }

      actionBtn.disabled = true;
      actionBtn.textContent = 'Installing...';
      backBtn.disabled = true;
      list.innerHTML = '';
      const pending = document.createElement('div');
      pending.className = 'muted'; pending.style.fontSize = '12px';
      pending.textContent = 'Saving config and uploading...';
      list.appendChild(pending);

      try {
        await api.put('/api/settings', {
          neocities: {
            gallery_dir: pathRaw,
            tag_dir: pathRaw,
            json_dir: `${pathRaw}/json`,
            art_dir: `${pathRaw}/assets/media`,
            thumb_dir: `${pathRaw}/assets/thumbnails`,
          },
        });

        list.innerHTML = '';
        const rows = new Map();  // file -> dom row, so we can morph "uploading" into "uploaded"/"error"

        await new Promise((resolve, reject) => {
          const es = new EventSource('/api/site/install/stream');
          let errored = 0, uploaded = 0, skipped = 0;

          es.onmessage = (ev) => {
            let data;
            try { data = JSON.parse(ev.data); } catch { return; }

            if (data.done) {
              es.close();
              if (data.fatal) return reject(new Error(data.fatal));
              installed = true;
              actionBtn.textContent = errored ? 'Continue anyway' : 'Next';
              if (!rows.size) {
                const empty = document.createElement('p'); empty.className = 'muted';
                empty.textContent = 'Nothing to install.';
                list.appendChild(empty);
              }
              resolve();
              return;
            }

            const { file, status, note } = data;
            let row = rows.get(file);
            if (!row) {
              row = feedRow('uploading', SPINNER_FRAMES[0], file, 'uploading...');
              rows.set(file, row);
              list.appendChild(row);
              row.scrollIntoView({ block: 'nearest' });
              runSpinner();
            }
            if (status === 'uploading') {
              setFeedRow(row, 'uploading', SPINNER_FRAMES[0], file, 'uploading...');
              runSpinner();
            } else if (status === 'uploaded') {
              setFeedRow(row, 'uploaded', '✓', file, 'uploaded');
              uploaded++;
            } else if (status === 'skipped') {
              setFeedRow(row, 'skipped', '--', file, note || 'already exists');
              skipped++;
            } else if (status === 'error') {
              setFeedRow(row, 'error', '✗', file, note || 'error');
              errored++;
            }
          };

          es.onerror = () => {
            es.close();
            reject(new Error('connection to install stream dropped'));
          };
        });
      } catch (e) {
        toast('Install failed: ' + e.message, 'error');
        actionBtn.textContent = 'Install';
      }
      actionBtn.disabled = false;
      backBtn.disabled = false;
    });

    body.appendChild(actions([backBtn, actionBtn]));
  }
}

// ---------- step 5: done ----------
function stepDone(body) {
  body.innerHTML = `
    <h1>You're all set</h1>
    <p>NeoGallery is ready to use. Drop images on the gallery to start posting, or tweak directories and host preferences in Settings whenever you want.</p>
  `;
  body.appendChild(actions([primary('Open my gallery', async () => {
    try { await api.post('/api/onboarding/complete', {}); } catch {}
    close();
  })]));
}

// ---------- helpers ----------

function actions(children) {
  const a = document.createElement('div'); a.className = 'onboarding-actions';
  for (const c of children) a.appendChild(c);
  return a;
}
function primary(label, onclick) {
  const b = document.createElement('button'); b.className = 'btn primary'; b.textContent = label;
  b.addEventListener('click', onclick); return b;
}
function ghost(label, onclick) {
  const b = document.createElement('button'); b.className = 'btn ghost'; b.textContent = label;
  b.addEventListener('click', onclick); return b;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function handle(res) {
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export const api = {
  get:  (url)            => fetch(url).then(handle),
  post: (url, body)      => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle),
  put:  (url, body)      => fetch(url, { method: 'PUT',  headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle),
  patch:(url, body)      => fetch(url, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handle),
  del:  (url, body)      => fetch(url, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }).then(handle),
  form: (url, formData, method='POST') => fetch(url, { method, body: formData }).then(handle),
};

export function toast(msg, kind = '') {
  const root = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

export function thumbUrl(entry) {
  const url = entry.thumbnailSrc || '';
  if (url.startsWith('http')) return url;
  const name = url.split('/').pop();
  return name ? `/local/thumbs/${encodeURIComponent(name)}` : url;
}

export function artUrl(entry) {
  const url = entry.fullSrc || '';
  if (url.startsWith('http')) return url;
  const name = url.split('/').pop();
  return name ? `/local/art/${encodeURIComponent(name)}` : url;
}

export function coverUrl(tag) {
  const url = tag.coverPhoto || '';
  if (!url) return '';
  if (url.startsWith('http')) return url;
  const name = url.split('/').pop();
  return name ? `/local/tag_covers/${encodeURIComponent(name)}` : url;
}

export function hostOfEntry(entry) {
  return entry.host || (entry.fullSrc && entry.fullSrc.includes('catbox.moe') ? 'catbox' : 'neocities');
}

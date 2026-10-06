const DATA = __DATA__;
const ICONS = {
  date: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 6.5h12M5 1.5v3M11 1.5v3"/></svg>',
  place: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 15s5.5-5.6 5.5-9.4A5.5 5.5 0 0 0 2.5 5.6C2.5 9.4 8 15 8 15z"/><circle cx="8" cy="5.6" r="1.8"/></svg>',
  mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/></svg>',
  phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
  globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19"/><path d="M12 2.5a15.3 15.3 0 0 1 4 9.5 15.3 15.3 0 0 1-4 9.5 15.3 15.3 0 0 1-4-9.5 15.3 15.3 0 0 1 4-9.5z"/></svg>',
  plus: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M6 1.2v9.6M1.2 6h9.6"/></svg>',
  star: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>'
};
const esc = s => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const byId = {};
DATA.entries.forEach(e => byId[e.entryType] = (byId[e.entryType] || 0) + 1);
let activeType = ''; // '' = show all entry types (chips are single-select)

function fmtRange(e) {
  const s = e.start ? monthName(e.start) : '';
  const en = e.end ? monthName(e.end) : (e.start ? 'Present' : '');
  if (s && s === en) return s;
  return (s && en) ? s + ' – ' + en : (s || en);
}
function placeStr(e) {
  return [e.location, e.country, e.locationType].filter(Boolean).join(' · ');
}
function monthName(ym) {
  if (!ym.includes('-')) return ym;
  const iso = ym.length > 7 ? ym : ym + '-01'; // "YYYY-MM" or full "YYYY-MM-DD"
  const d = new Date(iso + 'T00:00:00');
  return isNaN(d) ? ym : d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function msDate(e) {
  if (e.start && e.end && e.start !== e.end) return fmtRange(e);
  return monthName(e.start || e.end);
}
// Milestones headline the event's own title (`company`); role + organization
// stay secondary (italic sub / "under …" link). Cards, in contrast, lead
// with organization + role.
function msTitle(e) {
  if (e.role && e.company) return [e.company, e.role];
  return [e.company || e.role || e.categoryDisplay, ''];
}
function milestone(e) {
  // uid keys off e.id, so two instances of one `dates` entry (same file) get
  // distinct detail-panel ids and aria targets.
  const uid = 'msd-' + e.id.replace(/^ent-/, '');
  const [title, sub] = msTitle(e);
  const d = msDate(e);
  const auto = !!activeType; // a type filter is on: milestones start expanded
  let rowSub = '';
  if (e.parentIds.length) rowSub = '<span class="ms-sub">under ' +
    e.parentIds.map((id, i) => '<span class="plink" onclick="event.stopPropagation();jumpTo(\'' + id + '\')">' +
      esc(e.parentNames[i]) + '</span>').join(' · ') + '</span>';
  else if (sub) rowSub = '<span class="ms-sub">' + esc(sub) + '</span>';
  let row = '<button class="ms-row" aria-expanded="' + auto + '" aria-controls="' + uid + '">' +
    '<span class="ms-dot"></span><span class="ms-rule"></span><span class="ms-label">' +
    '<span class="ms-title">' + esc(title) + '</span>' + rowSub;
  if (d) row += '<span class="ms-date">' + esc(d) + '</span>';
  row += '</span><span class="ms-rule ms-tail"></span><span class="ms-tw">' + ICONS.plus + '</span>' +
    (e.featured ? '<span class="feat-star" title="Featured">' + ICONS.star + '</span>' : '') + '</button>';
  let pips = '';
  if (e.pips.length) pips = '<div class="ms-pips">' + e.pips.map((p, i) =>
    '<img class="pip" loading="lazy" src="' + esc(p) + '" data-full="' + esc(e.images[i]) + '" alt="" ' +
    'onclick="lb(this.dataset.full)" onerror="this.remove()">').join('') + '</div>';
  // Picture view: image_view: full + exactly one image — the picture is the
  // meat of the detail, shown whole (never cropped), text as a caption beneath.
  const pict = e.imageView === 'full' && e.images.length === 1;
  let c = '<div class="ms-detail" id="' + uid + '"><div class="ms-circle' +
    (pict ? ' pict' : '') + '">';
  if (pict) c += '<img class="phero" src="' + esc(e.images[0]) +
    '" alt="" loading="lazy" onclick="lb(this.src)" onerror="this.remove()">';
  else if (e.logo) c += '<img class="clogo" src="' + esc(e.logo) + '" alt="" loading="lazy" onerror="this.remove()">';
  c += '<h3>' + esc(title) + '</h3>';
  const csub = sub || e.parentNames.join(' · ');
  if (csub) c += '<p class="csub">' + esc(csub) + '</p>';
  const meta = [];
  if (d) meta.push('<span>' + ICONS.date + esc(d) + '</span>');
  const pl = placeStr(e);
  if (pl) meta.push('<span>' + ICONS.place + esc(pl) + '</span>');
  if (e.employmentType) meta.push('<span>' + esc(e.employmentType) + '</span>');
  if (e.industry) meta.push('<span>' + esc(e.industry) + '</span>');
  if (e.url) meta.push('<span><a class="elink" href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
    esc(hostLabel(e.url)) + ' ↗</a></span>');
  if (meta.length) c += '<div class="cmeta">' + meta.join('') + '</div>';
  c += '<div class="cbadges"><span class="badge type-' + esc(e.entryType) + '"><span class="tdot"></span>' +
    esc(e.entryType.replace(/_/g, ' ')) + '</span><span class="badge">' + esc(e.categoryDisplay) + '</span></div>';
  if (e.accomplishments.length === 1) c += '<p class="cacc">' + esc(e.accomplishments[0]) + '</p>';
  else if (e.accomplishments.length) c += '<ul class="cacc">' +
    e.accomplishments.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>';
  if (e.skills.length) c += '<div class="cskills">' +
    e.skills.map(s => '<span class="skill">' + esc(s) + '</span>').join('') + '</div>';
  if (e.images.length && !pict) c += '<div class="cimgs">' + e.images.map(i =>
    '<img src="' + esc(i) + '" alt="" loading="lazy" onclick="lb(this.src)" onerror="this.remove()">').join('') + '</div>';
  c += '</div></div>';
  return '<article class="ms' + (auto ? ' open auto' : '') + (e.featured ? ' featured' : '') +
    '" id="' + e.id + '">' + row + pips + c + '</article>';
}
function entryHtml(e) { return e.milestone ? milestone(e) : card(e); }

function renderChips() {
  const box = document.getElementById('chips');
  box.innerHTML = '';
  const mk = (label, typeKey, on, count, onclick) => {
    const c = document.createElement('button');
    c.type = 'button';
    c.className = 'chip' + (typeKey ? ' type-' + typeKey : '') + (on ? ' on' : '');
    c.innerHTML = (typeKey ? '<span class="tdot"></span>' : '') + esc(label) +
      ' <span class="n">' + count + '</span>';
    c.onclick = onclick;
    box.appendChild(c);
  };
  mk('All', '', !activeType, DATA.entries.length,
    () => { activeType = ''; renderChips(); render(); });
  Object.keys(byId).sort().forEach(k => {
    mk(k.replace(/_/g, ' '), k, activeType === k, byId[k],
      () => { activeType = (activeType === k) ? '' : k; renderChips(); render(); });
  });
}

function stripRow(c) {
  const title = c.milestone ? msTitle(c)[0] : (c.company || c.role || c.categoryDisplay);
  const d = msDate(c);
  const target = c.dates.length ? c.id + '-' + c.end : c.id; // jump to its latest occurrence
  return '<div class="ms-row"><span class="ms-dot"></span><span class="ms-rule"></span>' +
    '<span class="ms-label"><span class="ms-title"><span class="plink" onclick="jumpTo(\'' + target + '\', true)">' +
    esc(title) + '</span></span>' +
    (d ? '<span class="ms-date">' + esc(d) + '</span>' : '') +
    '</span><span class="ms-rule ms-tail"></span><span class="es-jump">↗</span></div>';
}
function eventsStrip(children) {
  return '<div class="events-strip">' +
    '<button class="es-head" aria-expanded="false" onclick="toggleStrip(this)">' +
    '<span class="es-label">Entries (' + children.length + ')</span><span class="es-rule"></span>' +
    '<span class="es-tw">' + ICONS.plus + '</span></button>' +
    '<div class="es-lines">' + children.map(stripRow).join('') + '</div></div>';
}
// Career break photo view: entries of type career_break with pictures get a
// "Photos (n)" strip. Expanding fills the whole card frame with the
// pictures — a square-ish collage whose tiles crop (never letterbox) so any
// image count tiles the frame edge to edge — with the text overlaid on a
// faint dark highlight so it stays readable on top of the photos.
function cbCollage(e) {
  const cols = Math.ceil(Math.sqrt(e.images.length));
  let html = '';
  for (let i = 0; i < e.images.length; i += cols) {
    html += '<div class="cb-row">' + e.images.slice(i, i + cols).map(img =>
      '<img src="' + esc(img) + '" alt="" loading="lazy" onclick="lb(this.src)" onerror="this.remove()">').join('') + '</div>';
  }
  return html;
}
function cbFrame(e) {
  let head = '<h2>' + esc(e.company || e.role || e.categoryDisplay) + '</h2>';
  if (e.role && e.company) head += '<p class="role">' + esc(e.role) + '</p>';
  const meta = [];
  const range = fmtRange(e);
  if (range) meta.push('<span>' + ICONS.date + esc(range) + '</span>');
  const pl = placeStr(e);
  if (pl) meta.push('<span>' + ICONS.place + esc(pl) + '</span>');
  if (e.employmentType) meta.push('<span>' + esc(e.employmentType) + '</span>');
  if (e.industry) meta.push('<span>' + esc(e.industry) + '</span>');
  if (e.url) meta.push('<span><a class="elink" href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
    esc(hostLabel(e.url)) + ' ↗</a></span>');
  if (meta.length) head += '<div class="meta">' + meta.join('') + '</div>';
  let foot = '';
  if (e.accomplishments.length) foot += '<ul class="acc">' +
    e.accomplishments.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>';
  if (e.skills.length) foot += '<div class="skills">' +
    e.skills.map(s => '<span class="skill">' + esc(s) + '</span>').join('') + '</div>';
  foot += '<div class="badges"><span class="badge type-' + esc(e.entryType) + '"><span class="tdot"></span>' +
    esc(e.entryType.replace(/_/g, ' ')) + '</span><span class="badge">' + esc(e.categoryDisplay) + '</span>' +
    e.parentIds.map((id, i) => '<span class="badge parent jump" title="Jump to ' + esc(e.parentNames[i]) +
      '" onclick="jumpTo(\'' + id + '\')">↗ ' + esc(e.parentNames[i]) + '</span>').join('') + '</div>';
  return '<div class="cb-frame"><div class="cb-collage">' + cbCollage(e) + '</div>' +
    '<div class="cb-overlay"><div class="cb-head">' + head + '</div>' +
    '<div class="cb-foot">' + foot + '</div></div></div>';
}
function cbStrip(e) {
  return '<button class="cb-strip" aria-expanded="false" onclick="togglePhotos(this)">' +
    '<span class="cb-label">Photos (' + e.images.length + ')</span><span class="cb-rule"></span>' +
    '<span class="cb-tw">' + ICONS.plus + '</span></button>';
}
function togglePhotos(btn) {
  const card = btn.closest('.card');
  const open = card.classList.toggle('photo');
  btn.setAttribute('aria-expanded', open);
}
function card(e) {
  const children = DATA.entries.filter(x => x.parentIds.includes(e.id));
  const cb = e.entryType === 'career_break' && e.images.length; // photo view
  const parts = ['<article class="card' + (cb ? ' cb' : '') + (e.featured ? ' featured' : '') +
    '" id="' + e.id + '">' + (cb ? '<div class="cb-body">' : '') + '<div class="card-top">'];
  if (e.logo) parts.push('<img class="logo" src="' + esc(e.logo) + '" alt="" loading="lazy" onerror="this.remove()">');
  parts.push('<div style="min-width:0"><h2>' + esc(e.company || e.role || e.categoryDisplay) + '</h2>');
  if (e.role && e.company) parts.push('<p class="role">' + esc(e.role) + '</p>');
  const meta = [];
  const range = fmtRange(e);
  if (range) meta.push('<span>' + ICONS.date + esc(range) + '</span>');
  const pl = placeStr(e);
  if (pl) meta.push('<span>' + ICONS.place + esc(pl) + '</span>');
  if (e.employmentType) meta.push('<span>' + esc(e.employmentType) + '</span>');
  if (e.industry) meta.push('<span>' + esc(e.industry) + '</span>');
  if (e.url) meta.push('<span><a class="elink" href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
    esc(hostLabel(e.url)) + ' ↗</a></span>');
  if (meta.length) parts.push('<div class="meta">' + meta.join('') + '</div>');
  if (e.accomplishments.length) {
    parts.push('<ul class="acc">' + e.accomplishments.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>');
  }
  if (e.skills.length) {
    parts.push('<div class="skills">' + e.skills.map(s => '<span class="skill">' + esc(s) + '</span>').join('') + '</div>');
  }
  if (e.images.length && !cb) {
    parts.push('<div class="thumbs">' + e.images.map(i =>
      '<img src="' + esc(i) + '" alt="" loading="lazy" onclick="lb(this.src)" onerror="this.remove()">').join('') + '</div>');
  }
  parts.push('</div>');
  parts.push('<div class="badges">' + (e.featured ? '<span class="feat-star" title="Featured">' + ICONS.star + '</span>' : '') +
    '<span class="badge type-' + esc(e.entryType) + '"><span class="tdot"></span>' + esc(e.entryType.replace(/_/g, ' ')) + '</span>');
  parts.push('<span class="badge">' + esc(e.categoryDisplay) + '</span>');
  e.parentIds.forEach((id, i) => parts.push('<span class="badge parent jump" title="Jump to ' +
    esc(e.parentNames[i]) + '" onclick="jumpTo(\'' + id + '\')">↗ ' + esc(e.parentNames[i]) + '</span>'));
  if (children.length) parts.push('<span class="badge parent">' + children.length +
    (children.length === 1 ? ' entry' : ' entries') + '</span>');
  parts.push('</div>');
  parts.push('</div>');
  if (children.length) parts.push(eventsStrip(children));
  if (cb) { parts.push('</div>'); parts.push(cbFrame(e)); parts.push(cbStrip(e)); }
  parts.push('</article>');
  return parts.join('');
}

function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const shown = DATA.entries.filter(e => {
    if (activeType && e.entryType !== activeType) return false;
    if (!q) return true;
    return [e.company, e.role, e.country, e.location, e.industry, e.employmentType,
            e.categoryDisplay, e.entryType, e.url,
            e.accomplishments.join(' '), e.skills.join(' ')].join(' ').toLowerCase().includes(q);
  });
  const box = document.getElementById('timeline');
  if (!shown.length) { box.innerHTML = '<p class="empty">No entries match.</p>'; return; }
  const groups = new Map();
  const undated = [];
  shown.forEach(e => {
    // A `dates` entry renders once per date as its own instance showing
    // only that date; the id suffix keeps DOM ids unique across instances.
    const ds = e.dates.length ? e.dates : (e.start ? [e.start] : []);
    if (!ds.length) { undated.push(e); return; }
    ds.forEach(d => {
      const y = d.slice(0, 4);
      if (!groups.has(y)) groups.set(y, []);
      groups.get(y).push(e.dates.length
        ? Object.assign({}, e, { id: e.id + '-' + d, start: d, end: '' }) : e);
    });
  });
  let html = '';
  [...groups.keys()].sort((a, b) => b.localeCompare(a)).forEach(y => {
    // Sort each year by date, newest first (stable — ties keep DATA order,
    // which already breaks them by end date then company).
    const list = groups.get(y).sort((a, b) => b.start.localeCompare(a.start));
    html += '<div class="year">' + esc(y) + ' <span class="n">(' + list.length + ')</span></div>';
    html += list.map(entryHtml).join('');
  });
  if (undated.length) {
    html += '<div class="year">Undated <span class="n">(' + undated.length + ')</span></div>';
    html += undated.map(entryHtml).join('');
  }
  box.innerHTML = html;
}

document.getElementById('timeline').addEventListener('click', ev => {
  const row = ev.target.closest('.ms-row');
  if (!row) return;
  const art = row.closest('.ms');
  if (!art) return; // events-strip rows are jump links, not toggles
  art.classList.remove('auto'); // manual toggle: restore bloom animation
  const open = art.classList.toggle('open');
  row.setAttribute('aria-expanded', open);
});

function lb(src) {
  const box = document.getElementById('lightbox');
  box.querySelector('img').src = src;
  box.style.display = 'flex';
  box.onclick = () => box.style.display = 'none';
}

function flash(el) {
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1700);
}
function toggleStrip(btn) {
  const s = btn.closest('.events-strip');
  const open = s.classList.toggle('open');
  btn.setAttribute('aria-expanded', open);
}
function jumpTo(id, expand) {
  const q = document.getElementById('q');
  if (activeType || q.value.trim()) { // unfilter so the jump target is rendered
    activeType = '';
    q.value = '';
    renderChips();
    render();
  }
  const el = document.getElementById(id);
  if (!el) return;
  const strip = el.querySelector('.events-strip');
  if (strip) {
    strip.classList.add('open');
    strip.querySelector('.es-head').setAttribute('aria-expanded', 'true');
  }
  if (expand && el.classList.contains('ms')) {
    el.classList.add('open');
    el.querySelector('.ms-row').setAttribute('aria-expanded', 'true');
  }
  el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  flash(el.classList.contains('ms') ? el.querySelector('.ms-row') : el);
}

// Contact header, rendered from DATA.contact (contact/contact.yaml at the
// repo root). Social URLs are labeled by brand/host; print spells out URLs.
const SOCIAL_LABELS = { 'github.com': 'GitHub', 'github.io': 'GitHub', 'linkedin.com': 'LinkedIn',
  'instagram.com': 'Instagram', 'twitter.com': 'Twitter', 'x.com': 'X', 'facebook.com': 'Facebook',
  'youtube.com': 'YouTube' };
// Brand marks for the same hosts — filled paths on the 24px grid, from
// Simple Icons (CC0); twitter.com gets the X mark, as Simple Icons does.
// An unlisted host falls back to the globe + its label in the contact line.
const SOCIAL_ICONS = {
  'github.com': 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12',
  'github.io': 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12',
  'linkedin.com': 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z',
  'instagram.com': 'M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077',
  'twitter.com': 'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z',
  'x.com': 'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z',
  'facebook.com': 'M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z',
  'youtube.com': 'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z'
};
function baseHost(u) {
  try {
    const h = new URL(u).hostname.replace(/^www\./, '');
    const base = h.match(/([^.]+\.[^.]+)$/);
    return base ? base[1] : h;
  } catch { return ''; }
}
function hostLabel(u) {
  const h = baseHost(u);
  return (h && SOCIAL_LABELS[h]) || h || u;
}
(function () {
  const C = DATA.contact || {};
  if (C.name) {
    document.getElementById('pname').textContent = C.name;
    document.title = C.name + ' — CV';
  } else {
    // No name given: the wordmark stays "Curriculum Vitae", so the small-caps
    // mast line above it (also "Curriculum Vitae") must drop out.
    document.getElementById('mast-line').hidden = true;
  }
  if (C.tagline) document.getElementById('tagline').textContent = C.tagline;
  if (C.photo) {
    const pfp = document.getElementById('pfp');
    pfp.onerror = () => { pfp.hidden = true; };
    pfp.src = C.photo;
    pfp.hidden = false;
  }
  // Contact line: stroke icons for the direct lines (email, phone, location,
  // website), and for a recognised social a bare brand mark — self-labelling,
  // with the name on title/aria and the print rules still spelling the URL
  // out after the mark. Unlisted hosts keep the globe + label.
  const brand = u => {
    const d = SOCIAL_ICONS[baseHost(u)];
    if (!d) return null;
    const name = esc(hostLabel(u));
    return '<a class="ic" href="' + esc(u) + '" title="' + name + '" aria-label="' + name +
      '"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="' + d +
      '"/></svg></a>';
  };
  const parts = [];
  if (C.website) parts.push('<a href="' + esc(C.website) + '">' + ICONS.globe + esc(hostLabel(C.website)) + '</a>');
  (C.social || []).forEach(u => parts.push(brand(u) ||
    '<a href="' + esc(u) + '">' + ICONS.globe + esc(hostLabel(u)) + '</a>'));
  if (C.email) parts.push('<a href="mailto:' + esc(C.email) + '">' + ICONS.mail + esc(C.email) + '</a>');
  if (C.phone) parts.push('<a href="tel:' + esc(C.phone.replace(/[^\d+]/g, '')) + '">' + ICONS.phone + esc(C.phone) + '</a>');
  if (C.location) parts.push('<span>' + ICONS.place + esc(C.location) + '</span>');
  document.getElementById('contact').innerHTML = parts.join(' &middot; ');
})();

const countries = new Set(DATA.entries.map(e => e.country).filter(Boolean)).size;
// Cities: `location` is authored as a city (new_entry.py prompts "location —
// city:") but often carries a region suffix ("Lexington, KY"), so count the
// segment before the first comma, case-insensitively, to keep one city one
// count. Entries with no location just drop out, like blank countries above.
const cities = new Set(DATA.entries.map(e => e.location.split(',')[0].trim().toLowerCase())
  .filter(Boolean)).size;
// Years: span of record — earliest to latest dated point (start/end/dates).
// Derived from the data, not the build clock, so the number only moves when
// entries are added, and stays truthful if the corpus goes quiet.
const points = DATA.entries.flatMap(e => [e.start, e.end, ...e.dates]).filter(Boolean).sort();
const years = +points[points.length - 1].slice(0, 4) - +points[0].slice(0, 4);
// Organizations: entities other entries hang off (build.py's link_parents
// fills parentIds only for resolved parents, so this counts real entries).
// A landing page, not a `company` string — most entries are their own
// employer record, which would just echo the entry count.
const orgs = new Set(DATA.entries.flatMap(e => e.parentIds)).size;
document.getElementById('sub').textContent =
  years + ' years · ' + countries + ' countries · ' + cities + ' cities · ' +
  orgs + ' organizations';
document.getElementById('f-stats').textContent = 'compiled from ' + DATA.entries.length + ' YAML entries';
document.getElementById('q').addEventListener('input', render);
renderChips();
render();
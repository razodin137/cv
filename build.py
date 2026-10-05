#!/usr/bin/env python3
"""Build a self-contained index.html CV viewer from the YAML files.

Usage: python3 build.py [style]
Renders index.html in the chosen style — "original" (the pre-Hallmark
look), "hallmark" (Newsprint) or "libron" (Reading Edition, set
entirely in the Libron book face). With no argument, the build asks
interactively; non-interactive runs (pipes, CI) use the default style.
Reads every */*.yaml in this directory, resolves logo + image paths,
and writes index.html with all data embedded. Open index.html directly
in a browser (works from file://, no server or internet needed).
Re-run after editing YAML files.
"""

import base64
import io
import json
import os
import re
import sys
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))

# Root directories scanned for CV entry YAML files; these are excluded
# (logos/ holds images, contact/ holds the header contact block).
ASSET_DIRS = {"logos", "contact"}


def slug_display(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title()


def resolve(category: str, filename: str, prefer_logos: bool) -> str | None:
    """Return a working relative path for an asset filename, or None."""
    if not filename:
        return None
    candidates = []
    if prefer_logos:
        candidates.append(os.path.join("logos", filename))
    candidates.append(os.path.join(category, filename))
    if not prefer_logos:
        candidates.append(os.path.join("logos", filename))
    for c in candidates:
        if os.path.isfile(os.path.join(ROOT, c)):
            return c
    return None


def pip_srcs(images):
    """Tiny bubbles for a milestone's pictures: 32px WebP data URIs so a
    collapsed line never loads a full-size photo. Falls back to the raw
    path (lazy-loaded by the viewer) if Pillow is missing or the file
    can't be decoded."""
    if not images:
        return []
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return list(images)
    out = []
    for rel in images:
        uri = None
        try:
            with Image.open(os.path.join(ROOT, rel)) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((32, 32))
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "WEBP", quality=70)
            uri = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            uri = None
        out.append(uri or rel)
    return out


def parent_slugs(raw):
    """`parent` accepts one slug or a list; normalize to a clean slug list."""
    if isinstance(raw, (list, tuple)):
        return [str(s).strip().strip("/") for s in raw if str(s).strip()]
    return [raw.strip().strip("/")] if raw and raw.strip() else []


def load_entries():
    entries = []
    for category in sorted(os.listdir(ROOT)):
        catdir = os.path.join(ROOT, category)
        if not os.path.isdir(catdir) or category in ASSET_DIRS or category.startswith("."):
            continue
        for fname in sorted(os.listdir(catdir)):
            if not fname.endswith(".yaml"):
                continue
            path = os.path.join(catdir, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                print(f"WARNING: skipping unparseable {path}: {e}", file=sys.stderr)
                continue
            if not isinstance(raw, dict):
                continue
            ms = str(raw.get("milestone")).strip().lower() in ("true", "yes", "1")
            images = [p for p in (resolve(category, str(i).strip(), prefer_logos=False)
                                  for i in (raw.get("images") or []) if i) if p]
            start = str(raw.get("start") or "").strip().strip('"')
            end = str(raw.get("end") or "").strip().strip('"')
            # `dates` (milestones only): a recurring event's occurrences —
            # the timeline renders one instance per date, each showing only
            # its own date. start/end become the earliest…latest span, used
            # for sorting and summary display (parent strips, card ranges).
            raw_dates = raw.get("dates")
            raw_dates = raw_dates if isinstance(raw_dates, list) else ([raw_dates] if raw_dates else [])
            dates = [d for d in (str(x).strip().strip('"') for x in raw_dates) if d]
            dates = list(dict.fromkeys(dates)) # dupes would collide instance ids in the DOM
            if dates and not ms:
                print(f"WARNING: {category}/{fname}: 'dates' needs milestone: true; ignoring it",
                      file=sys.stderr)
                dates = []
            elif dates:
                if start or end:
                    print(f"WARNING: {category}/{fname}: 'dates' overrides 'start'/'end'",
                          file=sys.stderr)
                start, end = min(dates), max(dates)
            e = {
                "category": category,
                "categoryDisplay": slug_display(category),
                "file": f"{category}/{fname}",
                "id": "ent-" + re.sub(r"[^a-z0-9]+", "-", f"{category}/{fname[:-5]}".lower()).strip("-"),
                "entryType": (raw.get("entry_type") or "").strip(),
                "milestone": ms,
                "featured": str(raw.get("featured")).strip().lower() in ("true", "yes", "1"),
                "parentSlugs": parent_slugs(raw.get("parent")),
                "parentIds": [],
                "parentNames": [],
                "company": (raw.get("company") or "").strip(),
                "role": (raw.get("role") or "").strip(),
                "employmentType": (raw.get("employment_type") or "").strip(),
                "industry": (raw.get("industry") or "").strip(),
                "url": (raw.get("url") or "").strip(),
                "start": start,
                "end": end,
                "dates": dates,
                "location": (raw.get("location") or "").strip(),
                "country": (raw.get("country") or "").strip(),
                "locationType": (raw.get("location_type") or "").strip(),
                "accomplishments": [a.strip() for a in (raw.get("accomplishments") or []) if a and a.strip()],
                "skills": [s.strip() for s in (raw.get("skills") or []) if s and s.strip()],
                "logo": resolve(category, str(raw.get("logo") or "").strip(), prefer_logos=True),
                "images": images,
                "pips": pip_srcs(images) if ms else [],
            }
            entries.append(e)
    return entries


def load_contact():
    """contact/contact.yaml is the single source for the header contact
    block — ASSET_DIRS keeps the directory out of the */*.yaml entry scan.
    Returns {} (empty contact block) if missing or unparseable."""
    path = os.path.join(ROOT, "contact", "contact.yaml")
    if not os.path.exists(path):
        print("WARNING: contact/contact.yaml not found — the header contact line is empty", file=sys.stderr)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"WARNING: ignoring unparseable contact/contact.yaml: {e}", file=sys.stderr)
        return {}
    return raw if isinstance(raw, dict) else {}


def link_parents(entries):
    """Resolve each entry's `parent` slug — a single slug or a list — to its
    parent entity: the YAML in that directory named like the directory (or
    the directory's only other YAML), or — for parents that share a
    directory with their children, like a club or team — the unique entry
    whose YAML file is named <slug>.yaml. Fills parentIds/parentNames
    (multiple parents allowed), inherits a logo from the first parent that
    has one, and warns + renders the entry standalone when a slug can't be
    resolved."""
    by_dir, by_file, by_id = {}, {}, {}
    for e in entries:
        by_dir.setdefault(e["category"], []).append(e)
        by_file.setdefault(e["file"].rsplit("/", 1)[-1][:-5], []).append(e)
        by_id[e["id"]] = e
    for e in entries:
        for slug in e.pop("parentSlugs"):
            cands = [p for p in by_dir.get(slug, ()) if p["file"] != e["file"]]
            parent = next((p for p in cands if p["file"] == f"{slug}/{slug}.yaml"), None)
            if parent is None and len(cands) == 1:
                parent = cands[0]
            if parent is None:
                files = [p for p in by_file.get(slug, ()) if p["file"] != e["file"]]
                if len(files) == 1:
                    parent = files[0]
            if parent is None:
                print(f"WARNING: {e['file']}: parent '{slug}' not resolved "
                      f"(need {slug}/{slug}.yaml, exactly one YAML in {slug}/, "
                      f"or a unique {slug}.yaml entry); rendering standalone",
                      file=sys.stderr)
                continue
            if parent["id"] in e["parentIds"]:
                continue
            e["parentIds"].append(parent["id"])
            e["parentNames"].append(parent["company"] or parent["role"] or parent["categoryDisplay"])
    # Logo inheritance can chain (event → organization → university), so
    # repeat until nothing changes. A logo comes from the first parent that
    # has one.
    for _ in range(len(entries)):
        changed = False
        for e in entries:
            if e["logo"]:
                continue
            p = next((by_id[i] for i in e["parentIds"] if by_id.get(i, {}).get("logo")), None)
            if p:
                e["logo"] = p["logo"]
                changed = True
        if not changed:
            break

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CV — Curriculum Vitae</title>
<style>
__CSS__
</style>
</head>
<body>
<header class="masthead">
  <div class="mast-in">
    <img class="pfp" id="pfp" hidden alt="Profile photo">
    <p class="mast-line" id="mast-line">Curriculum Vitae</p>
    <h1 id="pname">Curriculum Vitae</h1>
    <p class="tagline" id="tagline"></p>
    <p class="links" id="contact"></p>
    <p class="sub" id="sub"></p>
  </div>
  <hr class="mast-rule" aria-hidden="true">
</header>
<main>
  <div class="controls">
    <input type="search" id="q" placeholder="Search company, role, skills, accomplishments&hellip;" autocomplete="off">
    <div class="chips" id="chips"></div>
  </div>
  <div id="timeline"></div>
</main>
<footer class="colophon">
  <hr class="colo-rule" aria-hidden="true">
  <p>Set in __TYPEFACES__ · <span id="f-stats"></span> · built <span id="f-date">__BUILD_DATE__</span> · print via Ctrl+P / ⌘P</p>
</footer>
<div id="lightbox"><img alt=""></div>
<script>
const DATA = __DATA__;
const ICONS = {
  date: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 6.5h12M5 1.5v3M11 1.5v3"/></svg>',
  place: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 15s5.5-5.6 5.5-9.4A5.5 5.5 0 0 0 2.5 5.6C2.5 9.4 8 15 8 15z"/><circle cx="8" cy="5.6" r="1.8"/></svg>',
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
  let c = '<div class="ms-detail" id="' + uid + '"><div class="ms-circle">';
  if (e.logo) c += '<img class="clogo" src="' + esc(e.logo) + '" alt="" loading="lazy" onerror="this.remove()">';
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
  if (e.images.length) c += '<div class="cimgs">' + e.images.map(i =>
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
function hostLabel(u) {
  try {
    const h = new URL(u).hostname.replace(/^www\./, '');
    const base = h.match(/([^.]+\.[^.]+)$/);
    return (base && SOCIAL_LABELS[base[1]]) || h;
  } catch { return u; }
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
  const parts = [];
  if (C.website) parts.push('<a href="' + esc(C.website) + '">' + esc(hostLabel(C.website)) + '</a>');
  (C.social || []).forEach(u => parts.push('<a href="' + esc(u) + '">' + esc(hostLabel(u)) + '</a>'));
  if (C.email) parts.push('<a href="mailto:' + esc(C.email) + '">' + esc(C.email) + '</a>');
  if (C.phone) parts.push('<a href="tel:' + esc(C.phone.replace(/[^\d+]/g, '')) + '">' + esc(C.phone) + '</a>');
  if (C.location) parts.push('<span>' + esc(C.location) + '</span>');
  document.getElementById('contact').innerHTML = parts.join(' &middot; ');
})();

const countries = new Set(DATA.entries.map(e => e.country).filter(Boolean)).size;
document.getElementById('sub').textContent =
  DATA.entries.length + ' entries · ' + DATA.categories + ' categories · ' + countries + ' countries';
document.getElementById('f-stats').textContent = 'compiled from ' + DATA.entries.length + ' YAML entries';
document.getElementById('q').addEventListener('input', render);
renderChips();
render();
</script>
</body>
</html>
"""

# Render styles: one CSS file per style in styles/, chosen at build time.
# Each entry is stem -> (menu description, typefaces for the colophon line).
# All are kept conformant to the 37signals house style (stylelint with
# @37signals/stylelint-config-scss) — see README.md for the check command.
STYLES = {
    "1": ("original", "pre-Hallmark look: Georgia serif, navy header, blue accent",
          "Georgia & system-ui"),
    "2": ("hallmark", "Newsprint: Newsreader serif, warm paper, oxblood accent",
          "Newsreader & IBM Plex Mono"),
    "3": ("libron", "Reading Edition: Libron book serif, ivory paper, library-green accent",
          "Libron"),
}
DEFAULT_STYLE = "hallmark"  # matches the currently deployed page


def pick_style():
    """Resolve the render style: CLI argument if given, else an interactive
    prompt, else the default (so piped and CI runs still produce a build)."""
    arg = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""
    for key, (stem, _desc, _tf) in STYLES.items():
        if arg in (key, stem):
            return stem
    if arg:
        sys.exit(f"Unknown style '{sys.argv[1]}'. "
                 f"Choose one of: {', '.join(s for s, _, _ in STYLES.values())}.")
    if not sys.stdin.isatty():
        return DEFAULT_STYLE
    print("Render style:")
    for key, (stem, desc, _tf) in STYLES.items():
        print(f"  {key}) {stem} — {desc}")
    try:
        choice = input(f"Choose [Enter = {DEFAULT_STYLE}]: ").strip().lower()
    except EOFError:
        return DEFAULT_STYLE
    for key, (stem, _desc, _tf) in STYLES.items():
        if choice in (key, stem):
            return stem
    print(f"Unrecognized '{choice}' — using {DEFAULT_STYLE}.", file=sys.stderr)
    return DEFAULT_STYLE


def main():
    entries = load_entries()
    link_parents(entries)

    # Sort: by start date desc (undated last), then by end date, then company.
    def sort_key(e):
        return (0 if e["start"] else 1,
                tuple(-int(x) for x in e["start"].split("-")[:2]) if e["start"] else (0, 0),
                tuple(-int(x) for x in e["end"].split("-")[:2]) if e["end"] else (0, 0),
                e["company"] or e["role"] or "")

    entries.sort(key=sort_key)

    c = load_contact()
    data = {
        "entries": entries,
        "categories": len({e["category"] for e in entries}),
        "contact": {
            "name": str(c.get("name") or "").strip(),
            "tagline": str(c.get("tagline") or "").strip(),
            "photo": resolve("contact", str(c.get("photo") or "").strip(), prefer_logos=False) or "",
            "location": str(c.get("location") or "").strip(),
            "phone": str(c.get("phone") or "").strip(),
            "email": str(c.get("email") or "").strip(),
            "website": str(c.get("website") or "").strip(),
            "social": [str(s).strip() for s in (c.get("social media") or []) if str(s).strip()],
        },
    }
    style = pick_style()
    typefaces = next(tf for s, _desc, tf in STYLES.values() if s == style)
    with open(os.path.join(ROOT, "styles", f"{style}.css"), encoding="utf-8") as f:
        css = f.read()
    out = (HTML_TEMPLATE
           .replace("__CSS__", css)
           .replace("__DATA__", json.dumps(data, ensure_ascii=False))
           .replace("__TYPEFACES__", typefaces.replace("&", "&amp;"))
           .replace("__BUILD_DATE__", date.today().isoformat()))
    dest = os.path.join(ROOT, "index.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {dest} ({len(out) / 1024:.0f} KB) — {len(entries)} entries, "
          f"{data['categories']} categories, style '{style}'.")


if __name__ == "__main__":
    main()
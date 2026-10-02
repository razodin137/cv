#!/usr/bin/env python3
"""Build a self-contained index.html CV viewer from the YAML files.

Usage: python3 build.py
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

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))

# Directories that hold CV entry YAML files (everything except asset dirs).
ASSET_DIRS = {"logos"}


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
            e = {
                "category": category,
                "categoryDisplay": slug_display(category),
                "file": f"{category}/{fname}",
                "id": "ent-" + re.sub(r"[^a-z0-9]+", "-", f"{category}/{fname[:-5]}".lower()).strip("-"),
                "entryType": (raw.get("entry_type") or "").strip(),
                "milestone": ms,
                "featured": str(raw.get("featured")).strip().lower() in ("true", "yes", "1"),
                "parent": (raw.get("parent") or "").strip().strip("/"),
                "parentId": "",
                "parentName": "",
                "company": (raw.get("company") or "").strip(),
                "role": (raw.get("role") or "").strip(),
                "employmentType": (raw.get("employment_type") or "").strip(),
                "industry": (raw.get("industry") or "").strip(),
                "start": str(raw.get("start") or "").strip().strip('"'),
                "end": str(raw.get("end") or "").strip().strip('"'),
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


def link_parents(entries):
    """Resolve each entry's `parent` slug to the parent entity: the YAML in
    that directory named like the directory (or the directory's only other
    YAML), or — for parents that share a directory with their children, like
    a club or team — the unique entry whose YAML file is named <slug>.yaml.
    Fills parentId/parentName, inherits logos down parent chains when the
    entry has none, and warns + renders the entry standalone when the slug
    can't be resolved."""
    by_dir, by_file, by_id = {}, {}, {}
    for e in entries:
        by_dir.setdefault(e["category"], []).append(e)
        by_file.setdefault(e["file"].rsplit("/", 1)[-1][:-5], []).append(e)
        by_id[e["id"]] = e
    for e in entries:
        slug = e["parent"]
        if not slug:
            continue
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
            e["parent"] = ""
            continue
        e["parentId"] = parent["id"]
        e["parentName"] = parent["company"] or parent["role"] or parent["categoryDisplay"]
    # Logo inheritance can chain (event → organization → university), so
    # repeat until nothing changes.
    for _ in range(len(entries)):
        changed = False
        for e in entries:
            if e["logo"] or not e["parentId"]:
                continue
            p = by_id.get(e["parentId"])
            if p and p["logo"]:
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
  :root {
    --bg: #f6f7f9; --card: #ffffff; --ink: #1a2233; --muted: #5c677d;
    --line: #e3e7ee; --accent: #2456d6; --gold: #d4af37; --gold-deep: #8a6d1e;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: var(--bg); color: var(--ink); }
  header { background: var(--ink); color: #fff; padding: 2.2rem 2rem 1.6rem; }
  header h1 { margin: 0; font-size: 2rem; font-weight: normal; letter-spacing: .02em; }
  header p { margin: .4rem 0 0; color: #b8c0d4; font-size: .95rem; }
  header .links { margin: .7rem 0 0; font-family: system-ui, sans-serif; font-size: .85rem; color: #b8c0d4; }
  header .links a { color: #b8c0d4; text-decoration: none; border-bottom: 1px solid rgba(184,192,212,.45); }
  header .links a:hover { color: #fff; border-color: #fff; }
  main { max-width: 900px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
  .controls { position: sticky; top: 0; z-index: 10; background: var(--bg); padding: .8rem 0; display: flex;
    flex-direction: column; gap: .6rem; border-bottom: 1px solid var(--line); }
  .chips { display: flex; flex-wrap: wrap; gap: .4rem; }
  .chip { font-family: system-ui, sans-serif; font-size: .78rem; padding: .3rem .7rem; border-radius: 999px;
    border: 1px solid var(--line); background: var(--card); cursor: pointer; color: var(--muted); user-select: none; }
  .chip.on { background: var(--ink); color: #fff; border-color: var(--ink); }
  .chip .n { opacity: .55; margin-left: .3rem; }
  input[type=search] { font-family: system-ui, sans-serif; font-size: .95rem; padding: .55rem .8rem;
    border: 1px solid var(--line); border-radius: 8px; background: var(--card); outline: none; }
  input[type=search]:focus { border-color: var(--accent); }
  .year { font-family: system-ui, sans-serif; font-size: 1.15rem; font-weight: 600; color: var(--ink);
    margin: 2rem 0 .4rem; display: flex; align-items: baseline; gap: .8rem; }
  .year::after { content: ''; flex: 1; border-top: 2px solid var(--line); }
  .year .n { font-size: .78rem; color: var(--muted); font-weight: normal; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 1.1rem 1.25rem; margin: .55rem 0; break-inside: avoid; }
  .card.featured { border-color: var(--gold); background: #fffbea; box-shadow: 0 1px 9px rgba(212,175,55,.2); }
  .feat-star { color: var(--gold); display: inline-flex; flex: none; }
  .feat-star svg { width: 17px; height: 17px; }
  .badges .feat-star { margin-bottom: .35rem; }
  .card-top { display: flex; gap: 1rem; align-items: flex-start; }
  .card img.logo { width: 52px; height: 52px; object-fit: contain; border-radius: 8px;
    background: #fff; border: 1px solid var(--line); padding: 4px; flex: none; }
  .card h2 { margin: 0; font-size: 1.12rem; font-weight: 600; }
  .card .role { margin: .15rem 0 0; color: var(--muted); font-size: .95rem; font-style: italic; }
  .meta { display: flex; flex-wrap: wrap; gap: .35rem .9rem; margin-top: .5rem;
    font-family: system-ui, sans-serif; font-size: .78rem; color: var(--muted); }
  .meta svg { width: 12px; height: 12px; vertical-align: -1px; margin-right: 3px; }
  .badges { margin-left: auto; display: flex; flex-direction: column; gap: .25rem; align-items: flex-end; flex: none; }
  .badge { font-family: system-ui, sans-serif; font-size: .68rem; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; padding: .18rem .55rem; border-radius: 999px; background: #eef1f7; color: var(--muted); }
  .badge.type-job { background: #e1ecff; color: #1d4fd8; }
  .badge.type-volunteer { background: #e2f6e9; color: #1c7c46; }
  .badge.type-education { background: #efe6ff; color: #6b3fd4; }
  .badge.type-events { background: #fff0dd; color: #a35c00; }
  .badge.type-ministry { background: #dff7f4; color: #0d7a6c; }
  .badge.type-creative { background: #ffe3ee; color: #c22a74; }
  .badge.type-career_break { background: #eceff3; color: #566074; }
  .badge.type-organization { background: #e4e1ff; color: #4338ca; }
  ul.acc { margin: .6rem 0 0; padding-left: 1.15rem; }
  ul.acc li { font-size: .92rem; line-height: 1.5; margin-bottom: .3rem; }
  .skills { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .7rem; }
  .skill { font-family: system-ui, sans-serif; font-size: .72rem; background: #eef1f7; color: var(--ink);
    border-radius: 6px; padding: .18rem .5rem; }
  .thumbs { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .8rem; }
  .thumbs img { width: 74px; height: 74px; object-fit: cover; border-radius: 8px;
    border: 1px solid var(--line); cursor: zoom-in; }
  /* Milestone one-line entries (milestone: true) */
  .ms { margin: .1rem 0; }
  .ms-row { display: flex; align-items: center; gap: .55rem; width: 100%;
    padding: .45rem .25rem .45rem 0; background: none; border: 0; cursor: pointer;
    font: inherit; text-align: left; color: var(--ink); }
  .ms-row:hover .ms-title { color: var(--accent); }
  .ms-dot { width: 13px; height: 13px; border-radius: 50%; border: 2px solid var(--muted);
    background: var(--bg); flex: none; margin-left: .35rem; transition: border-color .15s, background .15s; }
  .ms-row:hover .ms-dot { border-color: var(--accent); }
  .ms.open .ms-dot { background: var(--accent); border-color: var(--accent); }
  .ms-rule { height: 1px; background: var(--line); flex: 0 0 22px; }
  .ms-tail { flex: 1 1 auto; min-width: 12px; }
  .ms-label { display: flex; align-items: baseline; gap: .5rem; min-width: 0; }
  .ms-title { font-size: .98rem; font-weight: 600; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
  .ms-sub { color: var(--muted); font-size: .82rem; font-style: italic; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
  .ms-date { font-family: system-ui, sans-serif; font-size: .74rem; color: var(--muted);
    white-space: nowrap; flex: none; }
  .ms-tw { flex: none; color: var(--muted); display: inline-flex; transition: transform .2s; }
  .ms-tw svg { width: 11px; height: 11px; }
  .ms.open .ms-tw { transform: rotate(45deg); }
  /* Featured entries (featured: true): gold highlight + star */
  .ms.featured .ms-dot { border-color: var(--gold); background: var(--gold); }
  .ms.featured .ms-title { color: var(--gold-deep); }
  .ms.featured .ms-row:hover .ms-title { color: var(--accent); }
  .ms-row .feat-star svg { width: 14px; height: 14px; }
  .ms.featured .ms-circle { border-color: var(--gold); background: #fffbea; }
  .ms-detail { display: none; }
  .ms.open .ms-detail { display: flex; justify-content: center; padding: .8rem 0 1rem;
    animation: msbloom .45s ease-out; }
  .ms.open.auto .ms-detail { animation: none; } /* filter-expanded: shown instantly */
  @keyframes msbloom { from { clip-path: circle(0 at 21px 0); } to { clip-path: circle(200% at 21px 0); } }
  .ms-circle { width: clamp(260px, 72vw, 440px); aspect-ratio: 1; border-radius: 50%;
    background: var(--card); border: 1px solid var(--line); padding: 2.1rem 2.4rem;
    display: flex; flex-direction: column; align-items: center; text-align: center;
    overflow-y: auto; scrollbar-width: thin; }
  .ms-circle img.clogo { width: 58px; height: 58px; object-fit: contain; border-radius: 50%;
    background: #fff; border: 1px solid var(--line); padding: 4px; margin-bottom: .6rem; }
  .ms-circle h3 { margin: 0; font-size: 1rem; font-weight: 600; }
  .ms-circle .csub { margin: .2rem 0 0; color: var(--muted); font-size: .85rem; font-style: italic; }
  .ms-circle .cmeta { display: flex; flex-wrap: wrap; justify-content: center; gap: .3rem .8rem;
    margin-top: .5rem; font-family: system-ui, sans-serif; font-size: .74rem; color: var(--muted); }
  .ms-circle .cmeta svg { width: 11px; height: 11px; vertical-align: -1px; margin-right: 3px; }
  .ms-circle .cbadges { display: flex; flex-wrap: wrap; justify-content: center; gap: .3rem; margin-top: .55rem; }
  .ms-circle p.cacc { margin: .7rem 0 0; font-size: .8rem; line-height: 1.45; }
  .ms-circle ul.cacc { margin: .7rem 0 0; padding-left: 1.05rem; text-align: left; }
  .ms-circle ul.cacc li { font-size: .8rem; line-height: 1.45; margin-bottom: .35rem; }
  .ms-circle .cskills { display: flex; flex-wrap: wrap; justify-content: center; gap: .3rem; margin-top: .7rem; }
  .ms-circle .cimgs { display: flex; flex-wrap: wrap; justify-content: center; gap: .45rem; margin-top: .8rem; }
  .ms-circle .cimgs img { width: 52px; height: 52px; object-fit: cover; border-radius: 50%;
    border: 1px solid var(--line); cursor: zoom-in; }
  /* Parent links + collapsible Events strip on parent cards */
  .plink { color: var(--accent); text-decoration: underline; text-decoration-color: rgba(36,86,214,.4);
    text-underline-offset: 3px; font-style: normal; cursor: pointer; }
  .plink:hover { text-decoration-color: var(--accent); }
  .badge.parent { background: #e1ecff; color: #1d4fd8; }
  .badge.jump { cursor: pointer; max-width: 210px; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; }
  .badge.jump:hover { text-decoration: underline; }
  .events-strip { border-top: 1px solid var(--line); margin-top: .9rem; padding-top: .45rem; }
  .es-head { display: flex; align-items: center; gap: .55rem; width: 100%; padding: .35rem 0;
    background: none; border: 0; cursor: pointer; font: inherit; text-align: left; color: var(--ink); }
  .es-head:hover .es-label { color: var(--accent); }
  .es-label { font-family: system-ui, sans-serif; font-size: .7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em; color: var(--muted); flex: none; }
  .es-rule { height: 1px; background: var(--line); flex: 1 1 auto; }
  .es-tw { flex: none; color: var(--muted); display: inline-flex; transition: transform .2s; }
  .es-tw svg { width: 11px; height: 11px; }
  .es-head[aria-expanded="true"] .es-tw { transform: rotate(45deg); }
  .es-lines { display: none; padding-top: .2rem; }
  .events-strip.open .es-lines { display: block; }
  .es-lines .ms-row { padding: .3rem 0; cursor: default; }
  .es-lines .ms-row:hover .ms-title { color: var(--ink); }
  .es-jump { flex: none; color: var(--muted); font-family: system-ui, sans-serif; font-size: .78rem; }
  .plink:hover + .es-jump, .es-jump:hover { color: var(--accent); }
  /* picture bubbles under a collapsed milestone line (aligned with its title) */
  .ms-pips { display: flex; align-items: center; gap: 5px; padding: 0 0 .45rem 58px; }
  .pip { width: 14px; height: 14px; border-radius: 50%; object-fit: cover;
    border: 1px solid var(--line); background: var(--card); cursor: zoom-in; }
  .pip:hover { border-color: var(--accent); }
  .ms.open .ms-pips { display: none; } /* expanded circle shows the real photos */
  /* flash highlight for jump targets */
  @keyframes flashbg { 0% { outline: 3px solid rgba(36,86,214,.55); background: #eef3ff; }
    70% { background: #eef3ff; } 100% { outline: 3px solid transparent; background: transparent; } }
  .flash { animation: flashbg 1.6s ease-out; border-radius: 10px; }
  .card.flash { border-radius: 12px; }
  @media (prefers-reduced-motion: reduce) { .ms.open .ms-detail { animation: none; } }
  .empty { text-align: center; color: var(--muted); font-style: italic; margin-top: 3rem; }
  #lightbox { position: fixed; inset: 0; background: rgba(10,14,22,.88); display: none;
    align-items: center; justify-content: center; cursor: zoom-out; z-index: 100; }
  #lightbox img { max-width: 92vw; max-height: 90vh; border-radius: 6px; }
  /* Mobile phones: compact header, swipeable filter chips, badges stacked
     under card text, wrapping milestone lines, and the milestone circle
     opening as a full-width card (same shape as the print layout). */
  @media (max-width: 640px) {
    header { padding: 1.4rem 1rem 1rem; }
    header h1 { font-size: 1.45rem; }
    main { padding: 1rem .7rem 3rem; }
    .controls { padding: .6rem 0; }
    input[type=search] { font-size: 16px; } /* >=16px stops iOS auto-zoom on focus */
    .chips { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
    .chips::-webkit-scrollbar { display: none; }
    .chip { flex: none; padding: .38rem .75rem; }
    .year { margin: 1.5rem 0 .4rem; }
    .card { padding: .9rem .95rem; }
    .card-top { flex-wrap: wrap; }
    .card-top > div { flex: 1 1 auto; }
    .badges { width: 100%; margin-left: 0; flex-direction: row; flex-wrap: wrap;
      align-items: center; gap: .3rem; }
    .badges .feat-star { margin-bottom: 0; }
    .ms-row { padding: .55rem 0; }
    .ms-tail { display: none; }
    .ms-label { flex: 1 1 auto; flex-wrap: wrap; }
    .ms-date { margin-left: auto; }
    .ms-circle { width: 100%; aspect-ratio: auto; border-radius: 12px; padding: 1rem 1.1rem;
      overflow: visible; align-items: flex-start; text-align: left; }
    .ms-circle .cmeta, .ms-circle .cbadges, .ms-circle .cskills, .ms-circle .cimgs {
      justify-content: flex-start; }
  }
  @media print {
    .controls, #lightbox { display: none !important; }
    body { background: #fff; }
    header { background: #fff; color: #000; }
    header p { color: #444; }
    header .links a { color: #444; }
    .card { break-inside: avoid; box-shadow: none; }
    .card.featured, .ms.featured .ms-circle { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .ms { break-inside: avoid; }
    .ms-row { display: none; }
    .es-lines .ms-row { display: flex; }
    .es-head { display: none; }
    .es-lines { display: block !important; }
    .ms-pips { display: none !important; }
    .ms-detail { display: flex !important; animation: none; padding: 0; }
    .ms-circle { width: 100%; aspect-ratio: auto; border-radius: 12px; padding: 1rem 1.25rem;
      overflow: visible; align-items: flex-start; text-align: left; }
  }
</style>
</head>
<body>
<header>
  <h1>Curriculum Vitae</h1>
  <p id="sub"></p>
  <p class="links"><a href="https://razodin137.github.io/">GitHub</a> &middot; <a href="https://www.linkedin.com/in/kaojaicam/">LinkedIn</a> &middot; <a href="mailto:jcamnorman@gmail.com">jcamnorman@gmail.com</a> &middot; <span>Chiang Rai, Thailand</span></p>
</header>
<main>
  <div class="controls">
    <input type="search" id="q" placeholder="Search company, role, skills, accomplishments&hellip;" autocomplete="off">
    <div class="chips" id="chips"></div>
  </div>
  <div id="timeline"></div>
</main>
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
  const uid = 'msd-' + e.file.replace(/[^a-z0-9]/g, '');
  const [title, sub] = msTitle(e);
  const d = msDate(e);
  const auto = !!activeType; // a type filter is on: milestones start expanded
  let rowSub = '';
  if (e.parentId) rowSub = '<span class="ms-sub">under <span class="plink" onclick="event.stopPropagation();jumpTo(\'' + e.parentId + '\')">' + esc(e.parentName) + '</span></span>';
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
  const csub = sub || e.parentName;
  if (csub) c += '<p class="csub">' + esc(csub) + '</p>';
  const meta = [];
  if (d) meta.push('<span>' + ICONS.date + esc(d) + '</span>');
  const pl = placeStr(e);
  if (pl) meta.push('<span>' + ICONS.place + esc(pl) + '</span>');
  if (e.employmentType) meta.push('<span>' + esc(e.employmentType) + '</span>');
  if (e.industry) meta.push('<span>' + esc(e.industry) + '</span>');
  if (meta.length) c += '<div class="cmeta">' + meta.join('') + '</div>';
  c += '<div class="cbadges"><span class="badge type-' + esc(e.entryType) + '">' +
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
  const all = document.createElement('span');
  all.className = 'chip' + (activeType ? '' : ' on');
  all.textContent = 'All (' + DATA.entries.length + ')';
  all.onclick = () => { activeType = ''; renderChips(); render(); };
  box.appendChild(all);
  Object.keys(byId).sort().forEach(k => {
    const c = document.createElement('span');
    c.className = 'chip' + (activeType === k ? ' on' : '');
    c.innerHTML = esc(k.replace(/_/g, ' ')) + ' <span class="n">' + byId[k] + '</span>';
    c.onclick = () => { activeType = (activeType === k) ? '' : k; renderChips(); render(); };
    box.appendChild(c);
  });
}

function stripRow(c) {
  const title = c.milestone ? msTitle(c)[0] : (c.company || c.role || c.categoryDisplay);
  const d = msDate(c);
  return '<div class="ms-row"><span class="ms-dot"></span><span class="ms-rule"></span>' +
    '<span class="ms-label"><span class="ms-title"><span class="plink" onclick="jumpTo(\'' + c.id + '\', true)">' +
    esc(title) + '</span></span>' +
    (d ? '<span class="ms-date">' + esc(d) + '</span>' : '') +
    '</span><span class="ms-rule ms-tail"></span><span class="es-jump">↗</span></div>';
}
function eventsStrip(children) {
  return '<div class="events-strip">' +
    '<button class="es-head" aria-expanded="false" onclick="toggleStrip(this)">' +
    '<span class="es-label">Events (' + children.length + ')</span><span class="es-rule"></span>' +
    '<span class="es-tw">' + ICONS.plus + '</span></button>' +
    '<div class="es-lines">' + children.map(stripRow).join('') + '</div></div>';
}
function card(e) {
  const children = DATA.entries.filter(x => x.parentId === e.id);
  const parts = ['<article class="card' + (e.featured ? ' featured' : '') + '" id="' + e.id + '"><div class="card-top">'];
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
  if (meta.length) parts.push('<div class="meta">' + meta.join('') + '</div>');
  if (e.accomplishments.length) {
    parts.push('<ul class="acc">' + e.accomplishments.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>');
  }
  if (e.skills.length) {
    parts.push('<div class="skills">' + e.skills.map(s => '<span class="skill">' + esc(s) + '</span>').join('') + '</div>');
  }
  if (e.images.length) {
    parts.push('<div class="thumbs">' + e.images.map(i =>
      '<img src="' + esc(i) + '" alt="" loading="lazy" onclick="lb(this.src)" onerror="this.remove()">').join('') + '</div>');
  }
  parts.push('</div>');
  parts.push('<div class="badges">' + (e.featured ? '<span class="feat-star" title="Featured">' + ICONS.star + '</span>' : '') +
    '<span class="badge type-' + esc(e.entryType) + '">' + esc(e.entryType.replace(/_/g, ' ')) + '</span>');
  parts.push('<span class="badge">' + esc(e.categoryDisplay) + '</span>');
  if (e.parentId) parts.push('<span class="badge parent jump" title="Jump to ' + esc(e.parentName) +
    '" onclick="jumpTo(\'' + e.parentId + '\')">↗ ' + esc(e.parentName) + '</span>');
  if (children.length) parts.push('<span class="badge parent">' + children.length +
    (children.length === 1 ? ' event' : ' events') + '</span>');
  parts.push('</div>');
  parts.push('</div>');
  if (children.length) parts.push(eventsStrip(children));
  parts.push('</article>');
  return parts.join('');
}

function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const shown = DATA.entries.filter(e => {
    if (activeType && e.entryType !== activeType) return false;
    if (!q) return true;
    return [e.company, e.role, e.country, e.location, e.industry, e.employmentType,
            e.categoryDisplay, e.entryType,
            e.accomplishments.join(' '), e.skills.join(' ')].join(' ').toLowerCase().includes(q);
  });
  const box = document.getElementById('timeline');
  if (!shown.length) { box.innerHTML = '<p class="empty">No entries match.</p>'; return; }
  const groups = new Map();
  const undated = [];
  shown.forEach(e => {
    if (!e.start) { undated.push(e); return; }
    const y = e.start.slice(0, 4);
    if (!groups.has(y)) groups.set(y, []);
    groups.get(y).push(e);
  });
  let html = '';
  [...groups.keys()].sort((a, b) => b.localeCompare(a)).forEach(y => {
    html += '<div class="year">' + esc(y) + ' <span class="n">(' + groups.get(y).length + ')</span></div>';
    html += groups.get(y).map(entryHtml).join('');
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
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  flash(el.classList.contains('ms') ? el.querySelector('.ms-row') : el);
}

document.getElementById('q').addEventListener('input', render);
document.getElementById('sub').textContent =
  DATA.entries.length + ' entries · ' + DATA.categories + ' categories · ' +
  new Set(DATA.entries.map(e => e.country).filter(Boolean)).size + ' countries';
renderChips();
render();
</script>
</body>
</html>
"""


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

    data = {
        "entries": entries,
        "categories": len({e["category"] for e in entries}),
    }
    out = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    dest = os.path.join(ROOT, "index.html")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {dest} ({len(out) / 1024:.0f} KB) — {len(entries)} entries, "
          f"{data['categories']} categories.")


if __name__ == "__main__":
    main()
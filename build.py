#!/usr/bin/env python3
"""Build a self-contained index.html CV viewer from the YAML files.

Usage: python3 build.py [style]
Renders index.html in the chosen style — "original" (the pre-Hallmark
look), "hallmark" (Newsprint) or "libron" (Reading Edition, set
entirely in the Libron book face). With no argument, the build asks
interactively; non-interactive runs (pipes, CI) use the default style.
Reads every content/*/*.yaml, resolves logo + image paths,
and writes index.html with all data embedded. The viewer's JS source
is app.js and each style's CSS lives in styles/<style>.css; the build
splices both into the single file. Open index.html directly in a
browser (works from file://, no server or internet needed).
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

# Entry YAML lives under content/; every content/ subdirectory is scanned
# as a category except ASSET_DIRS (contact/ holds the header contact block
# — logos/ stays a root asset dir, never scanned). The app itself (build.py,
# app.js, styles/, fonts/, index.html) sits at the repo root.
CONTENT = os.path.join(ROOT, "content")
ASSET_DIRS = {"logos", "contact"}


def slug_display(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title()


def resolve(category: str, filename: str, prefer_logos: bool) -> str | None:
    """Return a working repo-root-relative asset path (logos/ at the root,
    entry directories under content/), or None."""
    if not filename:
        return None
    candidates = []
    if prefer_logos:
        candidates.append(os.path.join("logos", filename))
    candidates.append(os.path.join("content", category, filename))
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
    for category in sorted(os.listdir(CONTENT)):
        catdir = os.path.join(CONTENT, category)
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
                "file": f"content/{category}/{fname}",
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
                "imageView": str(raw.get("image_view") or "").strip(),
                "pips": pip_srcs(images) if ms else [],
            }
            entries.append(e)
    return entries


def load_contact():
    """content/contact/contact.yaml is the single source for the header
    contact block — ASSET_DIRS keeps the directory out of the content/*/*.yaml
    entry scan. Returns {} (empty contact block) if missing or unparseable."""
    path = os.path.join(CONTENT, "contact", "contact.yaml")
    if not os.path.exists(path):
        print("WARNING: content/contact/contact.yaml not found — the header contact line is empty", file=sys.stderr)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"WARNING: ignoring unparseable content/contact/contact.yaml: {e}", file=sys.stderr)
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

# Viewer skeleton. main() fills the placeholders: __CSS__ from
# styles/<style>.css, __JS__ from app.js (which carries __DATA__ for
# the embedded JSON), plus __TYPEFACES__/__BUILD_DATE__ for the colophon.
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
__JS__
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
    # Viewer JS lives in app.js — spliced in like the CSS above; it carries
    # __DATA__ for the JSON. rstrip: the template adds the final newline.
    with open(os.path.join(ROOT, "app.js"), encoding="utf-8") as f:
        js = f.read().rstrip("\n")
    out = (HTML_TEMPLATE
           .replace("__CSS__", css)
           .replace("__JS__", js)
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
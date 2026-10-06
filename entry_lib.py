#!/usr/bin/env python3
"""Shared core for the CV entry tools — the single place that knows how
entries are scanned, validated, and written.

new_entry.py (create form) and tui.py (terminal editor) both go through
here, so every write lands in the exact shape build.py reads: the 20
template.yaml keys in template order, dates force-quoted, blank scalars
as bare `key:` lines. Generated text is always re-parsed and compared
against the intended data before anything hits disk.
"""

import os
import re

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")  # entry data lives under content/
ASSET_DIRS = {"logos", "contact"}  # same exclusions as build.py's scan

# (type, one-line description) — order matches README/explainer-template.
ENTRY_TYPES = [
    ("job", "paid work"),
    ("volunteer", "unpaid work"),
    ("education", "schools, degrees, certifications"),
    ("events", "gigs, one-offs, recurring events"),
    ("ministry", "church / missions / ministry work"),
    ("creative", "awards, art, performances"),
    ("career_break", "travel or a break between roles"),
    ("online_presence", "websites & digital presence work, e.g. client sites"),
    ("organization", "an umbrella entry (club, team) that sub-events parent to"),
]

# Markers to detect which style the current index.html was built with,
# so rebuilds keep the look (falls back to build.py's own interactive/
# default choice when undetectable).
STYLE_MARKERS = [("'Libron'", "libron"), ("'Newsreader'", "hallmark"),
                 ("#2456d6", "original")]

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")

# The 20 template.yaml keys, in template order.
TEMPLATE_KEYS = ("entry_type", "milestone", "featured", "parent", "company",
                 "role", "employment_type", "industry", "url", "start", "end",
                 "dates", "location", "country", "location_type",
                 "accomplishments", "skills", "logo", "images", "image_view")

# Dropdown vocabularies (template's canonical choices plus every value
# already in the corpus; blank is always allowed).
EMPLOYMENT_TYPES = ("full-time", "part-time", "contract", "seasonal",
                    "intern", "volunteer", "freelance")
LOCATION_TYPES = ("onsite", "remote", "hybrid")

# Plain string fields vs string-list fields within TEMPLATE_KEYS.
SCALAR_KEYS = ("entry_type", "company", "role", "employment_type", "industry",
               "url", "start", "end", "location", "country", "location_type",
               "logo", "image_view")
LIST_KEYS = ("accomplishments", "skills", "images")


# ------------------------------------------------------------ basic checks

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_date(s):
    """Sortable (y, m, d) for YYYY / YYYY-MM / YYYY-MM-DD, else None."""
    m = DATE_RE.match(s.strip())
    if not m:
        return None
    y, mo, d = (int(g) if g else 0 for g in m.groups())
    if mo and not 1 <= mo <= 12:
        return None
    if d and not 1 <= d <= 31:
        return None
    return (y, mo, d)


def parse_bool(v):
    """The build's own truthiness rule for milestone/featured."""
    return str(v).strip().lower() in ("true", "yes", "1")


# --------------------------------------------------------------- scanning

def scan_dirs():
    """Entry categories under content/ (mirrors build.py's scan)."""
    return [d for d in sorted(os.listdir(CONTENT))
            if os.path.isdir(os.path.join(CONTENT, d))
            and d not in ASSET_DIRS and not d.startswith(".")]


def categories():
    """Scanned directories that already hold at least one entry YAML."""
    return [d for d in scan_dirs()
            if any(f.endswith(".yaml")
                   for f in os.listdir(os.path.join(CONTENT, d)))]


def dir_yamls(category):
    d = os.path.join(CONTENT, category)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".yaml"))


def parent_resolvable(slug, category, stem):
    """Mirror build.py's parent resolution: <slug>/<slug>.yaml, the only
    YAML in <slug>/, or a unique */<slug>.yaml (self excluded)."""
    if os.path.isdir(os.path.join(CONTENT, slug)):
        ys = dir_yamls(slug)
        if f"{slug}.yaml" in ys or len(ys) == 1:
            return True
    hits = [d for d in scan_dirs()
            if os.path.isfile(os.path.join(CONTENT, d, f"{slug}.yaml"))
            and not (d == category and slug == stem)]
    return len(hits) == 1


def resolve_asset(category, filename, prefer_logos):
    """build.py's asset search order: logos/ (repo root) first for logos,
    the content/<category>/ directory first for images."""
    candidates = ([os.path.join("logos", filename),
                   os.path.join("content", category, filename)] if prefer_logos else
                  [os.path.join("content", category, filename),
                   os.path.join("logos", filename)])
    for c in candidates:
        if os.path.isfile(os.path.join(ROOT, c)):
            return c
    return None


def parent_list(v):
    """`parent` accepts one slug or a list; normalize to a clean slug
    list (build.py's parent_slugs rule)."""
    if v is None:
        return []
    if not isinstance(v, list):
        v = [v]
    out = []
    for s in v:
        s = str(s).strip().strip("/")
        if s and s not in out:
            out.append(s)
    return out


def clean_list(v):
    """A template list field as strings, blank items dropped (the build
    drops them too), order kept. A scalar counts as one item."""
    if v is None:
        return []
    if not isinstance(v, list):
        v = [v]
    out = []
    for x in v:
        s = "" if x is None else str(x).strip()
        if s:
            out.append(s)
    return out


def clean_dates(v):
    """`dates` as sorted unique strings — any precision. Handles the
    scalar form and the datetime.date objects PyYAML gives unquoted
    ISO dates (both exist in the corpus; build.py tolerates them)."""
    if v is None:
        return []
    if not isinstance(v, list):
        v = [v]
    out = []
    for x in v:
        s = "" if x is None else str(x).strip().strip('"')
        if s and s not in out:
            out.append(s)
    return sorted(out)


def canonical(raw):
    """The in-memory shape serialize() and verify() speak: every template
    key present, booleans as bools, parent as a slug list, dates sorted
    unique strings, list items blank-dropped, scalars stripped strings.
    Keys outside the 20 (none exist in the corpus; the build doesn't read
    them) ride along verbatim so a rewrite never drops data."""
    c = {k: "" for k in SCALAR_KEYS}
    for k in LIST_KEYS:
        c[k] = []
    c["milestone"] = parse_bool(raw.get("milestone"))
    c["featured"] = parse_bool(raw.get("featured"))
    c["parent"] = parent_list(raw.get("parent"))
    c["dates"] = clean_dates(raw.get("dates"))
    for k in SCALAR_KEYS:
        v = raw.get(k)
        c[k] = "" if v is None else str(v).strip()
    for k in LIST_KEYS:
        c[k] = clean_list(raw.get(k))
    for k in raw:
        if k not in TEMPLATE_KEYS:
            c[k] = raw[k]
    return c


def scan_entries():
    """All entry YAMLs (build.py's scan order: category, then filename),
    parsed and canonicalized. Returns (entries, problems); unparseable or
    non-mapping files are skipped and reported like the build skips them.
    Each entry dict carries category/fname/stem/path/relpath plus every
    canonical() key."""
    out, bad = [], []
    for category in scan_dirs():
        for fname in dir_yamls(category):
            path = os.path.join(CONTENT, category, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError) as e:
                bad.append(f"content/{category}/{fname}: {e}")
                continue
            if not isinstance(raw, dict):
                bad.append(f"content/{category}/{fname}: not a mapping")
                continue
            e = canonical(raw)
            e.update({"category": category, "fname": fname, "stem": fname[:-5],
                      "path": path, "relpath": f"content/{category}/{fname}"})
            out.append(e)
    return out, bad


def reload_entry(entry):
    """Re-parse one entry's file in place (after a write); returns the
    canonical dict or None if it no longer parses."""
    with open(entry["path"], encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        return None
    return canonical(raw)


# ------------------------------------------------------------- YAML output

def needs_quote(v):
    if re.fullmatch(r"[-+]?[\d.]+", v):
        return True  # keep numbers-as-text strings strings
    if v.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~"):
        return True
    if v[0] in " \t" or v[-1] in " \t" or v[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    if ": " in v or v.endswith(":") or " #" in v:
        return True
    return False


def scalar(v, force_quote=False):
    if not v:
        return ""
    if force_quote or needs_quote(v):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def key_line(k, v, force_quote=False):
    """`key:` when blank (matches the hand-written entries), `key: value` otherwise."""
    s = scalar(v, force_quote)
    return f"{k}: {s}" if s else k + ":"


def _extra_lines(k, v):
    """Serialize a non-template key verbatim-ish (safety net; the corpus
    has none): bools stay bools, lists stay lists, blanks stay blank."""
    if isinstance(v, bool):
        return [f"{k}: {'true' if v else 'false'}"]
    if isinstance(v, list):
        out = [k + ":"]
        out.extend(f" - {scalar(str(x))}" for x in clean_list(v))
        return out
    if v is None or v == "":
        return [k + ":"]
    return [key_line(k, str(v))]


def serialize(c):
    """Canonical text for a canonical() dict — the exact template.yaml
    shape build.py reads, 20 keys in template order."""
    L = [key_line("entry_type", c["entry_type"]),
         f"milestone: {'true' if c['milestone'] else 'false'}",
         f"featured: {'true' if c['featured'] else 'false'}"]
    if len(c["parent"]) == 1:
        L.append(f"parent: {c['parent'][0]}")
    else:
        L.append("parent:")
        L.extend(f" - {s}" for s in c["parent"])
    for k in ("company", "role", "employment_type", "industry", "url"):
        L.append(key_line(k, c[k]))
    L.append(key_line("start", c["start"], True))
    L.append(key_line("end", c["end"], True))
    L.append("dates:")
    L.extend(f' - "{d}"' for d in c["dates"])
    for k in ("location", "country", "location_type"):
        L.append(key_line(k, c[k]))
    for k in ("accomplishments", "skills"):  # images follows logo below
        L.append(k + ":")
        L.extend(f" - {scalar(x)}" for x in c[k])
    L.append(key_line("logo", c["logo"]))
    L.append("images:")
    L.extend(f" - {scalar(x)}" for x in c["images"])
    L.append(key_line("image_view", c["image_view"]))
    for k in (kk for kk in c if kk not in TEMPLATE_KEYS):
        L.extend(_extra_lines(k, c[k]))
    return "\n".join(L) + "\n"


def verify(text, c):
    """True if parsing `text` yields exactly the canonical dict `c`
    (parent list of one reads back scalar, empties read back None)."""
    loaded = yaml.safe_load(text)
    expected = {}
    for k in TEMPLATE_KEYS:
        v = c[k]
        if k in ("milestone", "featured"):
            expected[k] = bool(v)
        elif k == "parent":
            expected[k] = v[0] if len(v) == 1 else (v or None)
        else:  # dates, lists, scalars: empty reads back as a missing value
            expected[k] = v or None
    for k in (kk for kk in c if kk not in TEMPLATE_KEYS):
        expected[k] = c[k]
    return loaded == expected


def normalize_entry(c):
    """Enforce the build's invariants in memory (mutates the canonical
    dict): dates need milestone: true — the editor forces the flag on
    (new_entry.py instead clears the dates, since its form asks for the
    flag first) — and dates override start/end."""
    if c["dates"] and not c["milestone"]:
        c["milestone"] = True
    if c["dates"]:
        c["start"] = c["end"] = ""
    return c



def set_line(path, key, newline):
    """Replace the `key:` line — and any list items hanging under it —
    with `newline`, in place. Returns False when `key:` isn't a single
    plain block (missing key, or a duplicate), so the caller can fall
    back to a canonical rewrite."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pat = re.compile(rf"(?m)^{re.escape(key)}:[^\n]*(?:\n[ \t]*-[^\n]*)*")
    new, n = pat.subn(newline, text, count=2)
    if n != 1:
        return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)
    return True


def write_scalar(path, field, value, force_quote=False):
    """Set one scalar field to `value` (a string, "" clears it) with a
    minimal write: replace just that line in place when possible and
    verify by re-parsing; otherwise rewrite the whole file canonically.
    `force_quote` keeps date strings quoted per the template's rule.
    Returns the entry's new canonical dict."""
    line = key_line(field, value, force_quote) if value else field + ":"
    if set_line(path, field, line):
        with open(path, encoding="utf-8") as f:
            c = canonical(yaml.safe_load(f) or {})
        if c[field] == value:
            return c
    with open(path, encoding="utf-8") as f:
        c = canonical(yaml.safe_load(f) or {})
    c[field] = value
    write_entry(path, c)
    return c


def write_entry(path, c):
    """Serialize + verify + atomic write; returns the text written.
    Raises ValueError if the text wouldn't round-trip to `c`."""
    text = serialize(c)
    if not verify(text, c):
        raise ValueError("INTERNAL: generated YAML does not round-trip "
                         "to the entry data; nothing written.")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return text


def toggle_line(path, key, value):
    """Flip a `key: true|false` line in place, preserving the rest of the
    file byte-for-byte (every corpus file has exactly one such line for
    milestone and featured). Returns False when the line can't be found —
    the caller falls back to a full canonical rewrite."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new, n = re.subn(rf"(?m)^{re.escape(key)}: (?:true|false)[ \t]*$",
                     f"{key}: {value}", text)
    if n != 1:
        return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)
    return True


# ---------------------------------------------------------------- rebuild

def current_style():
    """Which style index.html carries now, or None."""
    try:
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return None
    for marker, style in STYLE_MARKERS:
        if marker in html:
            return style
    return None
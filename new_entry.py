#!/usr/bin/env python3
"""Interactive form that writes one CV entry YAML for build.py.

Usage: python3 new_entry.py                 # answer the prompts
       python3 new_entry.py < answers.txt   # same prompts, one answer per line

Prompts for the 19 template.yaml fields in order, validates against the
build's own rules (entry types, date formats, parent slugs, logo/image
filenames), shows a summary you can edit field by field, writes
content/<category>/<entry>.yaml in the exact shape build.py reads — verified by
a parse round-trip before anything hits disk — and offers to rebuild
index.html in the style it's currently built with.

Enter accepts the [default]; blank = skip; Ctrl+C cancels. Multi-line
fields (accomplishments, skills, images) read one item per line and end
on an empty line. Piped runs that run out of input take defaults, and
abort cleanly after a few consecutive end-of-inputs instead of looping.
"""

import os
import re
import subprocess
import sys

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
# so the form's rebuild keeps the look (falls back to build.py's own
# interactive/default choice when undetectable).
STYLE_MARKERS = [("'Libron'", "libron"), ("'Newsreader'", "hallmark"),
                 ("#2456d6", "original")]

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")

_eof_hits = 0  # consecutive end-of-inputs — abort instead of looping forever


# ---------------------------------------------------------------- prompts

def ask(prompt, default=""):
    global _eof_hits
    try:
        v = input(prompt).strip()
    except EOFError:
        _eof_hits += 1
        if _eof_hits > 3:
            sys.exit("Cancelled — input ended mid-form; nothing written.")
        print()
        return default
    _eof_hits = 0
    return v if v else default


def ask_yes_no(prompt, default=False):
    while True:
        a = ask(prompt, "y" if default else "n").lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        print("  Please answer y or n.", file=sys.stderr)


def ask_line_list(prompt):
    """One item per line; an empty line (or end of input) finishes."""
    print(prompt)
    items = []
    while True:
        try:
            v = input().strip()
        except EOFError:
            global _eof_hits
            _eof_hits += 1
            if items or _eof_hits > 3:
                print()
                return items
            sys.exit("Cancelled — input ended mid-form; nothing written.")
        if not v:
            return items
        items.append(v)


# ------------------------------------------------------------- validation

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def ask_slug(prompt, default=""):
    while True:
        v = slugify(ask(prompt, default))
        if not v:
            print("  Enter a name — lowercase letters, digits, hyphens.", file=sys.stderr)
            continue
        return v


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


def ask_date(prompt):
    while True:
        v = ask(prompt)
        if not v:
            return ""
        if parse_date(v):
            return v
        print("  Dates look like YYYY, YYYY-MM or YYYY-MM-DD.", file=sys.stderr)


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


# ------------------------------------------------------------ field picks

def pick_category():
    cats = categories()
    print("\nCategory directories (the directory name is the entry's badge):")
    for i, c in enumerate(cats, 1):
        print(f"  {i:>2}) {c}")
    while True:
        v = ask("Pick a number, or type a new directory name: ")
        if v.isdigit() and 1 <= int(v) <= len(cats):
            return cats[int(v) - 1]
        s = slugify(v)
        if not s:
            print("  Enter a number from the list or a new name.", file=sys.stderr)
            continue
        if s in ASSET_DIRS:
            print(f"  '{s}' is reserved for assets ({', '.join(sorted(ASSET_DIRS))}).",
                  file=sys.stderr)
            continue
        return s


def pick_file(category):
    existing = dir_yamls(category)
    default = "" if existing else category  # convention: <dir>/<dir>.yaml
    hint = f" [Enter = {default}]" if default else ""
    while True:
        stem = ask_slug(f"Entry file name{hint}: ", default)
        if os.path.isfile(os.path.join(CONTENT, category, f"{stem}.yaml")):
            print(f"  {category}/{stem}.yaml already exists — this form creates "
                  f"new entries; pick another name.", file=sys.stderr)
            default = ""
            continue
        return stem


def default_entry_type(category):
    counts = {}
    for f in dir_yamls(category):
        try:
            with open(os.path.join(CONTENT, category, f), encoding="utf-8") as fh:
                t = str((yaml.safe_load(fh) or {}).get("entry_type") or "").strip()
        except (OSError, yaml.YAMLError):
            continue
        if t:
            counts[t] = counts.get(t, 0) + 1
    known = dict(ENTRY_TYPES)
    for t, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if t in known:
            return t
    return "job"


def pick_entry_type(category):
    default = default_entry_type(category)
    print("\nentry_type:")
    for i, (name, desc) in enumerate(ENTRY_TYPES, 1):
        print(f"  {i}) {name} — {desc}")
    while True:
        v = ask(f"Choose [Enter = {default}]: ")
        if not v:
            return default
        if v.isdigit() and 1 <= int(v) <= len(ENTRY_TYPES):
            return ENTRY_TYPES[int(v) - 1][0]
        if v in dict(ENTRY_TYPES):
            return v
        print("  Pick a number from the list.", file=sys.stderr)


def pick_parents(category, stem):
    while True:
        v = ask("parent slugs (comma-separated; blank = none): ")
        if not v:
            return []
        slugs = list(dict.fromkeys(slugify(s) for s in re.split(r"[,\s]+", v) if s.strip()))
        bad = [s for s in slugs if not parent_resolvable(s, category, stem)]
        if not bad:
            return slugs
        print(f"  Can't resolve: {', '.join(bad)} — build.py needs "
              f"<slug>/<slug>.yaml, exactly one YAML in <slug>/, or a unique "
              f"<slug>.yaml entry.", file=sys.stderr)
        if ask_yes_no("  Keep anyway (build warns + renders it standalone)? ", False):
            return slugs


def pick_url():
    while True:
        v = ask("url (blank = none): ")
        if not v or re.match(r"^https?://", v):
            return v
        print("  External links start with http:// or https://.", file=sys.stderr)


def pick_dates():
    while True:
        v = ask("dates (comma-separated occurrence dates, any precision — "
                "e.g. 2024-05, 2025; blank = use a single start date): ")
        if not v:
            return []
        ds, bad = [], []
        for part in (p for p in re.split(r"[,\s]+", v) if p):
            (ds if parse_date(part) else bad).append(part)
        if bad:
            print("  Not dates: " + ", ".join(bad), file=sys.stderr)
            continue
        return list(dict.fromkeys(ds))


def pick_start_end(milestone, dates):
    """dates define the timeline themselves; start/end stay blank (the
    build derives the earliest…latest span from them)."""
    if dates:
        print(f"  start/end stay blank — the build derives "
              f"{min(dates)}…{max(dates)} from dates.")
        return "", ""
    while True:
        label = "date" if milestone else "start"
        start = ask_date(f"{label} [YYYY-MM] (blank = undated, sorts last): ")
        if milestone:
            print("  end stays blank — a milestone is a point in time.")
            return start, ""
        end = ask_date("end [YYYY-MM] (blank = Present): ")
        if end and not start:
            print("  An end without a start leaves nothing on the timeline — "
                  "give a start.", file=sys.stderr)
            continue
        if start and end and parse_date(end) < parse_date(start):
            print("  end is before start.", file=sys.stderr)
            continue
        return start, end


def pick_logo(category):
    while True:
        v = ask("logo filename (resolved from logos/, then this directory; "
                "blank = none): ")
        if not v:
            return ""
        if resolve_asset(category, v, prefer_logos=True):
            return v
        print(f"  '{v}' not found in logos/ or {category}/ — drop the file in "
              f"first (or leave blank and add it to the YAML later).", file=sys.stderr)


def pick_images(category):
    imgs = ask_line_list("images — one filename per line (resolved from this "
                         "directory, then logos/):")
    keep, drop = [], []
    for f in imgs:
        (keep if resolve_asset(category, f, prefer_logos=False) else drop).append(f)
    if drop:
        print("  Not found — dropped (the build couldn't resolve them): "
              + ", ".join(drop), file=sys.stderr)
    return keep


# ------------------------------------------------------------------ state

def collect():
    a = {"category": pick_category()}
    a["file"] = pick_file(a["category"])
    print(f"\n{a['category']}/{a['file']}.yaml — 19 fields; Enter = default, "
          f"blank = skip.")

    a["entry_type"] = pick_entry_type(a["category"])

    a["milestone"] = False
    a["milestone"] = ask_yes_no("milestone — one-off point event that renders "
                                "as a timeline line? [y/N]: ", False)
    a["featured"] = ask_yes_no("featured — gold highlight + star? [y/N]: ", False)

    a["parent"] = pick_parents(a["category"], a["file"])

    a["company"] = ask("company — organization, or the event title for a "
                       "milestone: ")
    a["role"] = ask("role — job title / activity: ")
    while not a["company"] and (a["milestone"] or not a["role"]):
        why = ("milestones headline this field" if a["milestone"]
               else "a card headlines company or role")
        a["company"] = ask(f"  {why} — company is required: ")

    a["employment_type"] = ask("employment_type (full-time | part-time | "
                               "contract | seasonal | intern — free text): ")
    a["industry"] = ask("industry (e.g. hospitality, ministry, food service, "
                        "education): ")
    a["url"] = pick_url()

    a["dates"] = pick_dates() if a["milestone"] else []
    a["start"], a["end"] = pick_start_end(a["milestone"], a["dates"])

    a["location"] = ask("location — city: ")
    a["country"] = ask("country (full name, e.g. Thailand): ")
    a["location_type"] = ask("location_type (onsite | remote | hybrid — free "
                             "text): ")

    a["accomplishments"] = ask_line_list(
        "accomplishments — one per line, lead with a verb, end with an "
        "outcome (empty line to finish):")
    a["skills"] = ask_line_list(
        "skills — one short tag per line (empty line to finish):")

    a["logo"] = pick_logo(a["category"])
    a["images"] = pick_images(a["category"])
    normalize(a)
    return a


def normalize(a):
    """Enforce the build's invariants: dates need milestone: true and
    override start/end."""
    if a["dates"] and not a["milestone"]:
        a["dates"] = []
        print("  dates cleared — they need milestone: true.", file=sys.stderr)
    if a["dates"]:
        a["start"] = a["end"] = ""


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


def entry_text(a):
    L = [f"entry_type: {a['entry_type']}",
         f"milestone: {'true' if a['milestone'] else 'false'}",
         f"featured: {'true' if a['featured'] else 'false'}"]
    if len(a["parent"]) == 1:
        L.append(f"parent: {a['parent'][0]}")
    else:
        L.append("parent:")
        L.extend(f" - {s}" for s in a["parent"])
    for k in ("company", "role", "employment_type", "industry", "url"):
        L.append(key_line(k, a[k]))
    L.append(key_line("start", a["start"], True))
    L.append(key_line("end", a["end"], True))
    L.append("dates:")
    L.extend(f' - "{d}"' for d in a["dates"])
    for k in ("location", "country", "location_type"):
        L.append(key_line(k, a[k]))
    for k in ("accomplishments", "skills"):
        L.append(k + ":")
        L.extend(f" - {scalar(x)}" for x in a[k])
    L.append(key_line("logo", a["logo"]))
    L.append("images:")
    L.extend(f" - {scalar(x)}" for x in a["images"])
    return "\n".join(L) + "\n"


def verify(text, a):
    """Guarantee the written YAML round-trips to exactly the answers."""
    loaded = yaml.safe_load(text)
    expected = {
        "entry_type": a["entry_type"],
        "milestone": a["milestone"],
        "featured": a["featured"],
        "parent": a["parent"][0] if len(a["parent"]) == 1 else (a["parent"] or None),
        "company": a["company"] or None,
        "role": a["role"] or None,
        "employment_type": a["employment_type"] or None,
        "industry": a["industry"] or None,
        "url": a["url"] or None,
        "start": a["start"] or None,
        "end": a["end"] or None,
        "dates": a["dates"] or None,
        "location": a["location"] or None,
        "country": a["country"] or None,
        "location_type": a["location_type"] or None,
        "accomplishments": a["accomplishments"] or None,
        "skills": a["skills"] or None,
        "logo": a["logo"] or None,
        "images": a["images"] or None,
    }
    if loaded != expected:
        sys.exit("INTERNAL: generated YAML does not round-trip to the answers; "
                 "nothing written.")


# ------------------------------------------------------- summary + confirm

def disp(v):
    if isinstance(v, list):
        if not v:
            return ""
        s = str(v[0])
        more = "…" if len(v) > 1 else ("…" if len(s) > 48 else "")
        return f"{len(v)} — {s[:48]}{more}"
    return str(v)


def show_summary(a):
    print(f"\n{'─' * 64}\n  {a['category']}/{a['file']}.yaml\n{'─' * 64}")
    rows = [(k, a[k]) for k in
            ("entry_type", "milestone", "featured", "parent", "company", "role",
             "employment_type", "industry", "url", "start", "end", "dates",
             "location", "country", "location_type", "accomplishments",
             "skills", "logo", "images")]
    for i, (k, v) in enumerate(rows, 1):
        print(f"  {i:>2}) {k:<16} {disp(v)}")
    print("  (blank end = Present; blank start = undated, sorts last)")


def edit_field(a, n):
    cat, stem = a["category"], a["file"]
    if n == 1:
        a["entry_type"] = pick_entry_type(cat)
    elif n == 2:
        a["milestone"] = ask_yes_no("milestone? [y/N]: ", False)
    elif n == 3:
        a["featured"] = ask_yes_no("featured? [y/N]: ", False)
    elif n == 4:
        a["parent"] = pick_parents(cat, stem)
    elif n == 5:
        a["company"] = ask("company: ")
    elif n == 6:
        a["role"] = ask("role: ")
    elif n == 7:
        a["employment_type"] = ask("employment_type (free text): ")
    elif n == 8:
        a["industry"] = ask("industry: ")
    elif n == 9:
        a["url"] = pick_url()
    elif n == 10:
        a["start"] = ask_date("start [YYYY-MM]: ")
    elif n == 11:
        a["end"] = ask_date("end [YYYY-MM] (blank = Present): ")
    elif n == 12:
        if not a["milestone"]:
            print("  dates need milestone: true (field 2) — the build ignores "
                  "them otherwise.", file=sys.stderr)
            return
        a["dates"] = pick_dates()
    elif n == 13:
        a["location"] = ask("location — city: ")
    elif n == 14:
        a["country"] = ask("country: ")
    elif n == 15:
        a["location_type"] = ask("location_type (free text): ")
    elif n == 16:
        a["accomplishments"] = ask_line_list("accomplishments — one per line "
                                             "(empty line to finish):")
    elif n == 17:
        a["skills"] = ask_line_list("skills — one per line (empty line to "
                                   "finish):")
    elif n == 18:
        a["logo"] = pick_logo(cat)
    elif n == 19:
        a["images"] = pick_images(cat)
    else:
        print("  Fields are numbered 1–19 (or f = file location).", file=sys.stderr)
        return
    normalize(a)


def confirm(a):
    while True:
        show_summary(a)
        c = ask("Write it? [Enter = yes / n = cancel / e<field> or f to edit]: ",
                "y").lower()
        if c in ("y", "yes"):
            return True
        if c in ("n", "no"):
            return False
        if c == "f":
            a["category"] = pick_category()
            a["file"] = pick_file(a["category"])
            continue
        m = re.fullmatch(r"e(\d{1,2})|\d{1,2}", c)
        if m:
            edit_field(a, int(m.group(1) or m.group(0)))
            continue
        print("  Answer Enter, n, or a field number (e.g. e5).", file=sys.stderr)


# ------------------------------------------------------------------ write

def current_style():
    """Which build style index.html carries now, or None."""
    try:
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return None
    for marker, style in STYLE_MARKERS:
        if marker in html:
            return style
    return None


def offer_rebuild():
    if not ask_yes_no("Rebuild index.html now? [Y/n]: ", True):
        print("Run `python3 build.py` when ready.")
        return
    style = current_style()
    subprocess.run([sys.executable, "build.py"] + ([style] if style else []),
                   cwd=ROOT)


def main():
    print("CV entry form — one content/*/*.yaml for build.py. Ctrl+C cancels.")
    a = collect()
    if not confirm(a):
        print("Cancelled — nothing written.")
        return
    text = entry_text(a)
    verify(text, a)
    os.makedirs(os.path.join(CONTENT, a["category"]), exist_ok=True)
    path = os.path.join(CONTENT, a["category"], a["file"] + ".yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nWrote content/{a['category']}/{a['file']}.yaml")
    offer_rebuild()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Cancelled — nothing written.")
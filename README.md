# CV

Live: **<https://razodin137.github.io/cv/>**

Curriculum vitae as data: 107 YAML entries across directories under
`content/` (plus logos/images) rendered by `build.py` into a single
self-contained `index.html` viewer.

## Usage

```sh
python3 build.py     # regenerate index.html from all content/*/*.yaml files
```

Then open `index.html` in any browser — double-click works; no server or
internet needed (all data is embedded; logos/images load from this folder).
The viewer's JS lives in `app.js` and each render style in `styles/*.css`;
the build splices both into `index.html` — edit those sources (not the
built file), then rerun.

### Adding an entry

```sh
python3 new_entry.py   # guided form: validates, writes content/<category>/<entry>.yaml, rebuilds
```

The form prompts for the 20 fields (Enter accepts the default, blank = skip),
checks everything against the build's own rules — entry types, date formats,
parent slugs, logo/image filenames — shows a summary you can edit field by
field, writes the YAML in the same shape as `template.yaml`, and offers to
rebuild in the style `index.html` is currently built with. Answers can be
piped from a file, one per line (`python3 new_entry.py < answers.txt`); a run
that runs out of input takes defaults, then aborts cleanly instead of looping.

### Editing entries

```sh
python3 tui.py   # terminal list of every entry: toggle, filter, edit
```

One row per entry — a filled dot (●) marks `milestone: true`, a star (★)
marks `featured: true`. Run down the list with ↑/↓ and press `space` to
flip the dot (in the ★ column it flips the star); `enter` opens the full 20-field editor; `d` appends
occurrence dates to a recurring event; `r` rebuilds `index.html` in its
current style and reports the result — success or the failing tail — in
a centered popup. `/` filters live — free text
plus tokens (`ms:true`,
`ms:false`, `feat:true`, `cat:<dir>`, `type:<entry_type>`, `undated`,
`dated`, `hasdates`), so "all milestones" is `/ms:true` and "every
recurring event" is `/hasdates`. `s` sorts by the focused column — press
again to flip direction (blanks first ⇄ blanks last), a third time to
clear; date columns sort by precision — blanks, then year-only, then
year+month, then full dates — so the least-refined dates surface for
filling in, while text sorts alphabetically and `ms`/`★` by on/off.
The grid opens with undated entries in their own leading segment (under
a dim divider row), dated entries below, and the split survives every
sort — the needs-work backlog stays on top. `accomplishments`/`skills`
sit at the far right of the grid so their long bullets don't spread the
other columns. The grid's top line shows the highlighted row's company
as a bold title, so scrolling far left or right keeps the row
identifiable. `q` with session changes opens a centered save/discard
dialog: save, save and rebuild, or discard (every file touched this
session is restored). Save + rebuild shows the same build popup — on
error you stay put and quitting is blocked until it builds, on success
the changes are committed and a second `q` closes the editor.
Writes are immediate and minimal: booleans flip their single line in
place, everything else rewrites the file in `template.yaml`'s canonical
shape — re-parsed before it touches
disk, so a save can't corrupt an entry. Turning a dated entry's dot off
asks first (the build ignores `dates:` without `milestone: true`). Needs
`pip install pyyaml textual`.

By hand, if you'd rather copy the skeleton:

```sh
mkdir content/my-new-entry-dir
cp template.yaml content/my-new-entry-dir/my-new-entry.yaml   # then fill it in
python3 build.py
```

`template.yaml` (project root) is a blank, copy-ready skeleton — all 20 keys,
no comments. Field-by-field documentation lives in `explainer-template.yaml`.
Both sit outside the `content/*/*.yaml` scan pattern, so the build ignores them.

## Styles

Three render styles ship in `styles/` — pick one when building:

```sh
python3 build.py original   # 1 — pre-Hallmark look: Georgia serif, navy header, blue accent
python3 build.py hallmark    # 2 — Newsprint: Newsreader, warm paper, oxblood accent (default)
python3 build.py libron      # 3 — Reading Edition: Libron, ivory paper, library-green accent
```

With no argument the build asks interactively (defaults to `hallmark` when
piped). The libron style is typeset entirely in
[Libron](https://github.com/nicoverbruggen/libron) (OFL) — one book face doing
everything via its real OpenType gear: small caps for labels, tabular figures
for dates, true italic for roles, bold for titles; its four woff2 files live
in `fonts/`.

## Contact block

`content/contact/contact.yaml` is the one place for your contact info — the
header renders from it on every build, and blank fields drop out. Drop your
profile picture in `content/contact/` as well; `photo:` takes its filename
(resolved from there, then `logos/`) and renders as a little circle at the top
of the page — print included.

```yaml
name:
tagline:
photo: profile.jpg
location: Chiang Rai, Thailand
phone:
email: you@example.com
website:
social media:
  - https://github.com/you
```

`social media:` takes plain URLs — the viewer labels them by brand or
hostname (github.com|github.io → "GitHub", linkedin.com → "LinkedIn", …),
and printing spells out every external link's full URL. A filled `name:`
becomes a header line and the browser tab title; a filled `tagline:` is a
one-line headline under it.

## Viewer features

- Timeline grouped by year, newest first, undated entries at the end
- One-off events (`milestone: true`) collapse to a single timeline line — a
  thin-line circle with the title and date; click/tap expands a circular
  detail view (logo, tags, location, description). The event's own title
  (`company`) headlines the line, with organization and role kept secondary
  (italic sub, "under …" parent link) — unlike cards, which lead with
  organization + role. Milestones with pictures show tiny bubbles of each
  picture under the collapsed line (click one to zoom); bubbles are
  build-time thumbnails, so full photos load only on open
- Parent entities: `parent: <slug>` — the parent's directory (e.g.
  `mae-fah-luang-university`) or, for an umbrella entry like a club or team,
  its YAML file name (e.g. `mfu-christian-club`); a list of slugs gives an
  entry multiple parents. Links to it both ways: milestone lines get an
  "under …" link, each parent card gets a collapsible `Entries (n)` strip
  with jump links to every child, and a child without its own `logo:`
  inherits the first parent's logo that has one. Jumps clear any active
  chip/search filter so the target is rendered; children may live in any
  directory (their category badge comes from it). Recurring events
  instead list their occurrence dates on one entry (see `dates` below)
- Featured entries (`featured: true`) get a gold highlight with a star in the
  top-right corner (collapsed milestone lines show the star at the far right)
- Career break photo view: `career_break` cards with `images:` get a
  `Photos (n)` strip — expand it and the whole card frame fills edge to edge
  with the pictures (a square-ish collage; tiles crop rather than letterbox,
  so any image count scales to fill the frame), with the title, dates and
  place sitting on top under a faint dark highlight so they stay readable;
  click a picture to zoom. Print always shows the standard card.
  Each career break lives in its own directory under `content/`, labeled by
  location and year (e.g. `content/chiang-mai-2018/`), its photos dropped in
  next to its YAML.
- Picture view (`image_view: full` on a milestone): when the detail is one
  clean picture (an album cover, a poster), it expands to show that single
  picture whole — never cropped, so slightly-off-square images show in full —
  with the title, date and place as a small caption beneath it.
- Filter by entry type (single-select chips; milestones auto-expand while a
  type filter is active), live full-text search
- Mobile-friendly: on narrow screens the filter chips become a swipeable
  single row, card badges stack under the text, milestone lines wrap instead
  of truncating, and an expanded milestone opens as a full-width card rather
  than the desktop circle
- Logos, image thumbnails with click-to-zoom lightbox
- Print-friendly (`Ctrl+P` hides the controls; milestone details print
  expanded, and external header links print with the full URL spelled out)

## YAML schema

Every `content/*/*.yaml` follows the same 20 fields:

| Field | Notes |
|---|---|
| `entry_type` | `job`, `volunteer`, `education`, `events`, `ministry`, `creative`, `career_break`, `online_presence`, `organization` |
| `milestone` | `true` = one-off point event → compact line headlined by the entry's own title (`company`); role/organization secondary; `false` = standard card |
| `parent` | slug of the parent entity — its directory (e.g. `mae-fah-luang-university`) or its YAML file name (e.g. `mfu-christian-club`); a list gives multiple parents; cross-links + logo inheritance |
| `featured` | `true` = gold highlight + star in the top-right corner (milestones: star at the far right); `false` = standard |
| `company`, `role`, `employment_type`, `industry` | plain text, any may be blank |
| `url` | external link for the entry (e.g. a client's website) — rendered as a link on cards and milestone circles; print spells it out |
| `start`, `end` | `YYYY-MM` strings (full `YYYY-MM-DD` also works), blank end = "Present" |
| `dates` | a recurring event's occurrence dates — a list of any precision (`"2026-09-11"`, `"2024"`, `"2011-09"`), replaces `start`/`end`; needs `milestone: true`. The entry shows up once per date on the timeline, each point labeled with only its own date (e.g. `play-ashram/play-ashram.yaml`, `rocktoberfest/`) |
| `location`, `country`, `location_type` | plain text |
| `accomplishments`, `skills` | string lists (blank items are dropped) |
| `logo` | filename; resolved from `logos/` first, then the entry's directory |
| `images` | filenames resolved from the entry's directory, then `logos/` |
| `image_view` | `full` = picture view — a milestone's single picture shown whole as the meat of its expanded detail (never cropped; slightly-off-square images included), with the title/date/place as a caption beneath; needs `milestone: true` and exactly one image, anything else falls back to the detail circle |

Re-run `python3 build.py` after editing any YAML to refresh the viewer.
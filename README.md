# CV

Live: **<https://razodin137.github.io/cv/>**

Curriculum vitae as data: 68 YAML entries across category directories
(plus logos/images) rendered by `build.py` into a single self-contained
`index.html` viewer.

## Usage

```sh
python3 build.py     # regenerate index.html from all */*.yaml files
```

Then open `index.html` in any browser — double-click works; no server or
internet needed (all data is embedded; logos/images load from this folder).

### Adding an entry

```sh
mkdir my-new-entry-dir
cp template.yaml my-new-entry-dir/my-new-entry.yaml   # then fill it in
python3 build.py
```

`template.yaml` (project root) is a blank, copy-ready skeleton — all 17 keys,
no comments. Field-by-field documentation lives in `explainer-template.yaml`.
Both sit outside the `*/*.yaml` scan pattern, so the build ignores them.

## Contact block

`contact.yaml` (project root) is the one place for your contact info — the
header contact line renders from it on every build, and blank fields drop
out of the line.

```yaml
website:
social media:
  - https://github.com/you
name:
location: Chiang Rai, Thailand
phone:
email: you@example.com
```

`social media:` takes plain URLs — the viewer labels them by brand or
hostname (github.com|github.io → "GitHub", linkedin.com → "LinkedIn", …),
and printing spells out every external link's full URL. A filled `name:`
becomes a header line and the browser tab title.

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
  its YAML file name (e.g. `mfu-christian-club`) — links an entry to its
  parent both ways: milestone lines get an "under …" link, the parent card
  gets a collapsible `Events (n)` strip with jump links to every child, and
  a child without its own `logo:` inherits the parent's logo. Jumps clear any
  active chip/search filter so the target is rendered; children may live in
  any directory (their category badge comes from it). Recurring events use
  this shape: one umbrella entry spanning the years plus a milestone per
  instance (e.g. `play-ashram/`)
- Featured entries (`featured: true`) get a gold highlight with a star in the
  top-right corner (collapsed milestone lines show the star at the far right)
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

Every `*/*.yaml` follows the same 17 fields:

| Field | Notes |
|---|---|
| `entry_type` | `job`, `volunteer`, `education`, `events`, `ministry`, `creative`, `career_break`, `organization` |
| `milestone` | `true` = one-off point event → compact line headlined by the entry's own title (`company`); role/organization secondary; `false` = standard card |
| `parent` | slug of the parent entity — its directory (e.g. `mae-fah-luang-university`) or its YAML file name (e.g. `mfu-christian-club`); cross-links + logo inheritance |
| `featured` | `true` = gold highlight + star in the top-right corner (milestones: star at the far right); `false` = standard |
| `company`, `role`, `employment_type`, `industry` | plain text, any may be blank |
| `start`, `end` | `YYYY-MM` strings (full `YYYY-MM-DD` also works), blank end = "Present" |
| `location`, `country`, `location_type` | plain text |
| `accomplishments`, `skills` | string lists (blank items are dropped) |
| `logo` | filename; resolved from `logos/` first, then the entry's directory |
| `images` | filenames resolved from the entry's directory, then `logos/` |

Re-run `python3 build.py` after editing any YAML to refresh the viewer.
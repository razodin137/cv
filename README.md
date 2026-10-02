# CV

Live: **<https://razodin137.github.io/cv/>**

Curriculum vitae as data: 51 YAML entries (one per directory, plus
logos/images) rendered by `build.py` into a single self-contained
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

`template.yaml` (project root) documents every field inline. It sits outside
the `*/*.yaml` scan pattern, so the build ignores it.

## Viewer features

- Timeline grouped by year, newest first, undated entries at the end
- One-off events (`milestone: true`) collapse to a single timeline line — a
  thin-line circle with the title and date; click/tap expands a circular
  detail view (logo, tags, location, description). Give sub-events their own
  YAML in the parent entity's directory to share its category badge.
- Filter by entry type (chips), live full-text search
- Logos, image thumbnails with click-to-zoom lightbox
- Print-friendly (`Ctrl+P` hides the controls; milestone details print expanded)

## YAML schema

Every `*/*.yaml` follows the same 15 fields:

| Field | Notes |
|---|---|
| `entry_type` | `job`, `volunteer`, `education`, `events`, `ministry`, `creative`, `career_break` |
| `milestone` | `true` = one-off point event → compact timeline line; `false` = standard card |
| `company`, `role`, `employment_type`, `industry` | plain text, any may be blank |
| `start`, `end` | `YYYY-MM` strings, blank end = "Present" |
| `location`, `country`, `location_type` | plain text |
| `accomplishments`, `skills` | string lists (blank items are dropped) |
| `logo` | filename; resolved from `logos/` first, then the entry's directory |
| `images` | filenames resolved from the entry's directory, then `logos/` |

Re-run `python3 build.py` after editing any YAML to refresh the viewer.
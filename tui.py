#!/usr/bin/env python3
"""Terminal editor for existing CV entries — a spreadsheet over the corpus,
the companion to new_entry.py's create form.

    python3 tui.py

One row per content/*/*.yaml entry, one column per template field (ms ●/○,
★, type, employment, parent, company, role, … — accomplishments/skills at
the far right so their long bullets can't spread the useful columns;
category is read-only). The grid opens in two segments — undated entries
first under a dim divider (they're the ones that still need dating), dated
entries below — and the split survives every sort, so the backlog is
always on top. The top line shows the highlighted row's company as a bold
title, anchoring the row however far right you scroll. Arrows move cell
to cell; the bar under the grid shows the focused cell.

    space   the primary cell key — toggles the ●/★ dot on the ms/★
            columns, opens the cell's editor everywhere else; enter does
            the same, and commits jump down one row, so a column can be
            filled in one pass
    e       open the full 20-field editor for the cursor's row
    d       add occurrence dates… (modal; keeps existing dates)
    /       filter — text plus ms:true, ms:false, feat:true, cat:<dir>,
            type:<t>, undated, dated, hasdates (combined with spaces)
    s       sort by the focused column — s again flips direction (blanks
            first ⇄ blanks last), a third s clears it. Date columns sort
            by precision first: blank, then year-only, then year+month,
            then full date (chronological inside each tier), so the least
            refined dates surface for filling in; text sorts A→Z, bools
            ○ before ●
    r       rebuild index.html (current style)      q  quit
    esc     cancel a cell edit / leave the filter box / clear the filter

Cell editors by field: text fields take free text; entry_type,
employment_type, location_type and parent are dropdowns (arrows move,
enter picks, space backs out) — parent's options are the corpus's own
entry slugs, with several current parents shown as one "both of these"
choice; the other list fields (dates, accomplishments, skills, images)
take one item per line — enter adds a line, an empty line saves the list
(the form's convention).

Writes are immediate and minimal: booleans flip their single line in
place, scalar cells rewrite just their line, lists rewrite the file in
template.yaml's canonical shape — always re-parsed before anything hits
disk, so a write can never corrupt an entry. `r` (re)builds index.html in
its current style and reports the outcome in a centered popup — success or
error. Quitting with changes opens a centered save/discard dialog: save
(they're already written), save + rebuild, or discard, which restores
every file's pre-session text; beyond that, undo is git. Save + rebuild
shows the same build popup — on error you stay put and quitting is blocked
until it builds, on success the changes are committed and a second q
closes the editor. Turning a dated entry's milestone dot off asks first
(build.py ignores `dates:` without `milestone: true`). Needs
`pip install pyyaml textual`.
"""

import asyncio
import sys

import yaml
from rich.text import Text

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.message import Message
    from textual.screen import ModalScreen, Screen
    from textual.widgets import (Button, Checkbox, DataTable, Footer, Input,
                                 Label, ListItem, ListView, Select, TextArea)
except ImportError:
    sys.exit("tui.py needs Textual — install it with: pip install textual")

import entry_lib as lib

DOT_TRUE, DOT_FALSE, STAR = "●", "○", "★"

# The grid: (header, yaml field, editing kind). Kinds: bool-ms, bool-feat,
# text, date, dropdown, parent, list, list-date, readonly. accomplishments
# and skills sit at the far right, before read-only category: their long
# bullets would otherwise spread the columns everything else needs.
COLUMNS = [
    ("ms", "milestone", "bool-ms"),
    ("★", "featured", "bool-feat"),
    ("type", "entry_type", "dropdown"),
    ("employment", "employment_type", "dropdown"),
    ("parent", "parent", "parent"),
    ("company", "company", "text"),
    ("role", "role", "text"),
    ("industry", "industry", "text"),
    ("url", "url", "text"),
    ("start", "start", "date"),
    ("end", "end", "date"),
    ("dates", "dates", "list-date"),
    ("location", "location", "text"),
    ("country", "country", "text"),
    ("loc type", "location_type", "dropdown"),
    ("logo", "logo", "text"),
    ("images", "images", "list"),
    ("img view", "image_view", "dropdown"),
    ("accomplishments", "accomplishments", "list"),
    ("skills", "skills", "list"),
    ("category", None, "readonly"),
]

DROPDOWN_OPTIONS = {
    "entry_type": [t for t, _d in lib.ENTRY_TYPES],
    "employment_type": list(lib.EMPLOYMENT_TYPES),
    "location_type": list(lib.LOCATION_TYPES),
    "image_view": ["full"],
}


def cell_text(e, field):
    """A field's display text: lists join with ' · '."""
    v = e[field]
    return " · ".join(v) if isinstance(v, list) else str(v)

def date_sort_key(s):
    """(precision, y, m, d) — blank sorts first (least filled out), then
    year-only, then year+month, then full dates; chronological inside
    each precision tier, so the coarsest dates surface for refinement."""
    if not s:
        return (0, 0, 0, 0)
    parsed = lib.parse_date(s)
    if parsed is None:
        return (0, 0, 0, 0)
    y, mo, d = parsed
    return (1 if not mo else 2 if not d else 3, y, mo, d)


def dates_sort_key(items):
    """A recurring entry's key: its coarsest occurrence date picks the
    precision tier, its most recent occurrence orders within it."""
    if not items:
        return (0, 0, 0, 0)
    keys = [date_sort_key(d) for d in items]
    return (min(k[0] for k in keys),) + max(k[1:] for k in keys)


# --------------------------------------------------------- cell edit widgets

class CellInput(Input):
    """The bar's text editor: enter submits, escape cancels."""

    BINDINGS = [Binding("escape", "cancel", "cancel", priority=True)]

    class Cancelled(Message):
        pass

    def action_cancel(self):
        self.post_message(self.Cancelled())


class CellTextArea(TextArea):
    """The bar's list editor — one item per line: enter adds a line;
    enter on an empty line saves the list (the form's convention)."""

    BINDINGS = [Binding("enter", "commit_or_line", show=False, priority=True),
                Binding("escape", "cancel", "cancel", priority=True)]

    class Commit(Message):
        pass

    class Cancel(Message):
        pass

    def action_commit_or_line(self):
        row = self.cursor_location[0]
        lines = self.text.split("\n") if self.text else [""]
        if not lines[min(row, len(lines) - 1)].strip():
            self.post_message(self.Commit())
        else:
            self.insert("\n")

    def action_cancel(self):
        self.post_message(self.Cancel())


# ==================================================================== main

class MainScreen(Screen):

    BINDINGS = [
        Binding("space", "primary", "edit · toggle"),
        Binding("e", "edit_row", "full editor"),
        Binding("d", "add_dates", "dates…"),
        Binding("slash", "focus_filter", "filter"),
        Binding("r", "rebuild", "rebuild"),
        Binding("s", "sort_column", "sort"),
        Binding("q", "quit", "quit"),
        Binding("ctrl+q", "quit", "quit", show=False),
        Binding("escape", "escape", "cancel/clear"),
    ]

    DEFAULT_CSS = """
    #title {
        text-align: center;
        text-style: bold;
        padding: 0 1;
        border-bottom: heavy $primary-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self.entries, self.view, self.by = [], [], {}
        self._rows = []      # table rows: entry dicts, None = divider row
        self._dividers = {}  # divider row index -> "undated · 5" label
        self._sort = None   # (column index, "asc"|"desc") — None = scan order
        self._touched = {}  # relpath -> pre-session file text (discard on exit)
        self.filter_q = ""
        self._note = ""
        self._edit = None  # the cell being edited, if any

    # ------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield Label("", id="title")
        yield Input(placeholder="filter — text, ms:true, cat:nexus, undated … "
                                 "(esc clears)", id="filter")
        yield DataTable(id="table")
        yield Vertical(Label("", id="cell-label"), Label("", id="cell-view"),
                       CellInput(id="cell-input"), CellTextArea(id="cell-area"),
                       id="cellbar")
        yield Label("", id="status")
        yield Footer()

    def on_mount(self):
        t = self.query_one("#table", DataTable)
        t.cursor_type = "cell"
        self.rescan()
        t.focus()

    def rescan(self):
        self.entries, bad = lib.scan_entries()
        self.by = {e["relpath"]: e for e in self.entries}
        self.refresh_rows()
        if bad:
            self.say(f"⚠ {len(bad)} unreadable file(s): {bad[0]}", error=True)

    def row_cells(self, e):
        cells = []
        for _h, field, kind in COLUMNS:
            if kind == "bool-ms":
                cells.append(DOT_TRUE if e["milestone"] else DOT_FALSE)
            elif kind == "bool-feat":
                cells.append(STAR if e["featured"] else "·")
            elif kind == "readonly":
                cells.append(e["category"])
            elif field == "dates":
                prefix = "⚠ " if e["dates"] and not e["milestone"] else ""
                cells.append(prefix + " · ".join(e["dates"]))
            elif field == "company":
                cells.append(e["company"] or e["role"] or e["stem"])
            else:
                cells.append(cell_text(e, field))
        return tuple(cells)

    def column_header(self, i, h):
        """Column label, carrying the sort arrow when this column is
        the sorted one."""
        if self._sort and self._sort[0] == i:
            h += " ↑" if self._sort[1] == "asc" else " ↓"
        return h

    def divider_cells(self, label):
        """A segment-divider row: dim label in the company column (the
        wide identity column), blanks elsewhere."""
        cells = [""] * len(COLUMNS)
        cells[next(i for i, (_h, f, _k) in enumerate(COLUMNS)
                   if f == "company")] = Text(f"── {label} ──",
                                              style="dim italic")
        return cells

    def sort_key(self, spec, e):
        """One comparable key per column kind, matching what the column
        shows: bools by on/off, dates by precision then time (least
        refined first), text alphabetically with blanks ahead of all."""
        _h, field, kind = spec
        if kind == "bool-ms":
            return (1 if e["milestone"] else 0,)
        if kind == "bool-feat":
            return (1 if e["featured"] else 0,)
        if kind == "date":
            return date_sort_key(e[field])
        if field == "dates":
            return dates_sort_key(e["dates"])
        if kind == "readonly":
            return (e["category"].lower(),)
        if field == "company":  # the cell falls back role → stem
            return ((e["company"] or e["role"] or e["stem"]).lower(),)
        return (cell_text(e, field).lower(),)

    def refresh_rows(self):
        t = self.query_one("#table", DataTable)
        row, col = t.cursor_row, t.cursor_column
        prev = self._rows[row] if row < len(self._rows) else None
        t.clear(columns=True)  # re-add: sorted column's header gets an arrow
        t.add_columns(*[self.column_header(i, h)
                        for i, (h, _f, _k) in enumerate(COLUMNS)])
        hit = [e for e in self.entries if self.matches(e, self.filter_q)]
        undated = [e for e in hit if not (e["dates"] or e["start"])]
        dated = [e for e in hit if e["dates"] or e["start"]]
        if self._sort:  # the sort orders inside each segment — undated
            spec = COLUMNS[self._sort[0]]  # keeps its leading segment
            key = lambda e: self.sort_key(spec, e)
            rev = self._sort[1] == "desc"
            undated.sort(key=key, reverse=rev)
            dated.sort(key=key, reverse=rev)
        self.view = undated + dated
        self._rows, self._dividers = [], {}
        for seg, name in ((undated, "undated"), (dated, "dated")):
            if not seg:
                continue
            self._dividers[len(self._rows)] = f"{name} · {len(seg)}"
            t.add_row(*self.divider_cells(f"{name} · {len(seg)}"))
            self._rows.append(None)
            for e in seg:
                t.add_row(*self.row_cells(e))
                self._rows.append(e)
        if self._rows:
            r = row
            if prev is not None:  # keep the cursor on its entry, not its
                r = next((i for i, x in enumerate(self._rows) if x is prev),
                         r)       # old row — a sort may have moved it
            t.move_cursor(row=min(r, len(self._rows) - 1), column=col)
        self.update_title()
        self.update_status()

    def say(self, msg, error=False):
        self._note = msg
        self.update_status(error)

    def update_status(self, error=False):
        sort = ""
        if self._sort:
            sort = (f" · sorted by {COLUMNS[self._sort[0]][0]} "
                    f"{'↑' if self._sort[1] == 'asc' else '↓'}")
        self.query_one("#status", Label).update(
            f"[{'red' if error else 'dim'}]"
            f"{len(self.view)}/{len(self.entries)} entries{sort} · {self._note}[/]")

    def update_title(self):
        """The big top line: the highlighted row's company — the anchor
        when scrolled deep into a row's long columns."""
        t = self.query_one("#table", DataTable)
        lbl = self.query_one("#title", Label)
        e = self.cursor_entry()
        if not e:
            seg = self._dividers.get(t.cursor_row, "")
            lbl.update(Text(f"── {seg} ──", style="dim italic") if seg else "")
            return
        lbl.update(Text(e["company"] or e["role"] or e["stem"] or "—"))

    # ------------------------------------------------------------ helpers

    def cursor_entry(self):
        """The entry under the cursor — None when the list is empty or
        the cursor sits on a segment divider row."""
        t = self.query_one("#table", DataTable)
        return self._rows[t.cursor_row] if t.cursor_row < len(self._rows) \
            else None

    def cursor_spec(self):
        t = self.query_one("#table", DataTable)
        return COLUMNS[min(t.cursor_column, len(COLUMNS) - 1)]

    def parent_stems(self, e):
        """The parent dropdown's choices: every entry's slug but this
        row's own (an entry parenting itself is meaningless)."""
        return sorted({x["stem"] for x in self.entries} - {e["stem"]})

    def reload_entry(self, e):
        """Re-parse one entry's file in place after a write."""
        meta = {k: e[k] for k in ("category", "fname", "stem", "path", "relpath")}
        with open(e["path"], encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        e.clear()
        e.update(lib.canonical(raw))
        e.update(meta)

    def canonical_of(self, e):
        return {k: e[k] for k in lib.TEMPLATE_KEYS}

    def snapshot(self, e):
        """Remember a file's pre-session text the first time we touch it,
        so "discard changes" on exit can restore it."""
        if e["relpath"] not in self._touched:
            try:
                with open(e["path"], encoding="utf-8") as f:
                    self._touched[e["relpath"]] = f.read()
            except OSError:
                pass

    # ------------------------------------------------- cell bar (idle view)

    def show_cell_view(self):
        self.update_title()
        e = self.cursor_entry()
        if not e:  # empty list, or the cursor is on a divider row
            self.query_one("#cell-label", Label).update("")
            self.query_one("#cell-view", Label).update("")
            return
        _h, field, kind = self.cursor_spec()
        label = self.query_one("#cell-label", Label)
        value = ("space toggles" if kind.startswith("bool")
                 else cell_text(e, field or "category"))
        label.update(f"{field or 'category'} · {e['relpath']}")
        self.query_one("#cell-view", Label).update(f"  {value or '—'}")
        self.query_one("#cell-view", Label).styles.display = "block"
        for w in ("#cell-input", "#cell-area"):
            self.query_one(w).styles.display = "none"

    @on(DataTable.CellHighlighted)
    def cell_highlighted(self, _event):
        if self._edit is None:
            self.show_cell_view()

    # ------------------------------------------------------- cell editing

    @on(DataTable.CellSelected)
    def cell_selected(self, _event):
        if self._edit is None:  # enter — same as space
            self.action_primary()

    def action_primary(self):
        """The one cell key: toggles the ●/★ dots on the bool columns,
        opens the editor (bar or dropdown) everywhere else."""
        e = self.cursor_entry()
        if not e:
            if self._rows:  # cursor on a dim divider row
                self.say("segment divider — move to an entry row")
            return
        _h, field, kind = self.cursor_spec()
        if kind == "readonly":
            self.say("category is the entry's directory name — read-only")
        elif kind.startswith("bool"):
            self.toggle_bool(field)
        else:
            self.open_cell_editor(e, field, kind)

    def open_cell_editor(self, e, field, kind):
        label = self.query_one("#cell-label", Label)
        self.query_one("#cell-view", Label).styles.display = "none"
        if kind in ("dropdown", "parent"):
            self._edit = {"field": field, "kind": kind, "entry": e}
            # several current parents read as one "both of these" option
            value = " · ".join(e[field]) if kind == "parent" else e[field]
            options = (self.parent_stems(e) if kind == "parent"
                       else DROPDOWN_OPTIONS[field])
            self.app.push_screen(PickerModal(field, value, options,
                                             self.cell_picked))
            return
        self._edit = {"field": field, "kind": kind, "entry": e}
        if kind in ("text", "date"):
            inp = self.query_one("#cell-input", CellInput)
            inp.styles.display = "block"
            inp.styles.border = None
            inp.value = e[field]
            hint = (" — YYYY, YYYY-MM or YYYY-MM-DD" if kind == "date"
                    else " — enter saves, esc cancels")
            label.update(f"{field} · {e['relpath']}{hint}")
            inp.focus()
        else:  # list kinds
            area = self.query_one("#cell-area", CellTextArea)
            area.styles.display = "block"
            area.styles.border = None
            items = e[field]
            area.load_text("\n".join(items))
            if items:  # caret after the last char: typing appends an item
                area.move_cursor(location=(len(items) - 1, len(items[-1])))
            label.update(f"{field} · {e['relpath']} — one item per line; "
                         "enter adds a line, an empty line saves")
            area.focus()

    def cell_error(self, msg):
        self.say(f"✗ {msg}", error=True)
        ed = self._edit
        if ed and not ed["kind"].startswith("list"):
            self.query_one("#cell-input", CellInput).styles.border = ("tall", "red")
        elif ed:
            self.query_one("#cell-area", CellTextArea).styles.border = ("tall", "red")

    def close_cell_editor(self, focus_table=True):
        self._edit = None
        for w in ("#cell-input", "#cell-area"):
            wid = self.query_one(w)
            wid.styles.display = "none"
            wid.styles.border = None
        self.show_cell_view()
        if focus_table:
            self.query_one("#table", DataTable).focus()

    def advance(self):
        """After a commit, step down one row — fill a column in one pass
        (segment dividers are skipped)."""
        t = self.query_one("#table", DataTable)
        r = t.cursor_row + 1
        while r < len(self._rows) and self._rows[r] is None:
            r += 1
        if r < len(self._rows):
            t.move_cursor(row=r)

    @on(Input.Submitted)
    def input_submitted(self, event):
        if event.input.id == "cell-input" and self._edit:
            self.commit_cell(event.input.value)

    @on(CellInput.Cancelled)
    def input_cancelled(self, _event):
        self.close_cell_editor()
        self.say("cancelled — nothing written")

    @on(CellTextArea.Commit)
    def area_committed(self, _event):
        if self._edit:
            self.commit_cell(self.query_one("#cell-area", CellTextArea).text)

    @on(CellTextArea.Cancel)
    def area_cancelled(self, _event):
        self.close_cell_editor()
        self.say("cancelled — nothing written")

    def cell_picked(self, value):
        """PickerModal result: None cancels, a string commits (parent's
        string may carry several " · "-joined slugs)."""
        ed = self._edit
        if ed is None:
            return
        if value is None:
            self._edit = None
            self.say("cancelled — nothing written")
            self.query_one("#table", DataTable).focus()
            return
        self.commit_cell(value)

    def commit_cell(self, value):
        ed = self._edit
        if not ed:
            return
        e, field, kind = ed["entry"], ed["field"], ed["kind"]
        notes = []
        self.snapshot(e)  # for the discard-on-exit choice
        try:
            if kind == "date":
                if value and not lib.parse_date(value):
                    self.cell_error(f"'{value}' is not a date — "
                                    "YYYY, YYYY-MM or YYYY-MM-DD")
                    return
                lib.write_scalar(e["path"], field, value, force_quote=True)
                if e["dates"]:
                    notes.append("dates override start/end; the build "
                                 "ignores these")
            elif kind in ("text", "dropdown"):
                lib.write_scalar(e["path"], field, value)
            elif kind == "list-date":
                items = [d.strip() for d in value.splitlines() if d.strip()]
                bad = [d for d in items if not lib.parse_date(d)]
                if bad:
                    self.cell_error("not dates: " + ", ".join(bad)
                                    + " — use YYYY, YYYY-MM or YYYY-MM-DD")
                    return
                c = self.canonical_of(e)
                c["dates"] = sorted(set(items))
                forced = bool(c["dates"]) and not c["milestone"]
                lib.normalize_entry(c)
                lib.write_entry(e["path"], c)
                if forced:
                    notes.append("milestone auto-set — dates need it")
            elif kind == "parent":
                c = self.canonical_of(e)
                c["parent"] = value.split(" · ") if value else []
                lib.write_entry(e["path"], c)
                bad = [s for s in c["parent"]
                       if not lib.parent_resolvable(s, e["category"], e["stem"])]
                if bad:
                    notes.append(f"unresolved parents: {', '.join(bad)}")
            else:  # list
                items = [x.strip() for x in value.splitlines() if x.strip()]
                c = self.canonical_of(e)
                c[field] = items
                lib.write_entry(e["path"], c)
                if field == "images":
                    miss = [f for f in items
                            if not lib.resolve_asset(e["category"], f,
                                                     prefer_logos=False)]
                    if miss:
                        notes.append(f"images not found: {', '.join(miss)}")
        except ValueError as ex:
            self.cell_error(str(ex))
            return
        self.close_cell_editor(focus_table=False)
        self.reload_entry(e)
        self.refresh_rows()
        self.advance()
        self.query_one("#table", DataTable).focus()
        msg = f"✓ {field} — {e['relpath']}"
        if notes:
            msg += "  (" + "; ".join(notes) + ")"
        self.say(msg)

    # ----------------------------------------------------------- toggles

    def toggle_bool(self, field):
        e = self.cursor_entry()
        if not e:
            return
        if field == "milestone" and e["milestone"] and e["dates"]:
            self.app.push_screen(DatesGuardModal(e, self.guard_result))
            return
        self.snapshot(e)
        val = not e[field]
        if not lib.toggle_line(e["path"], field, "true" if val else "false"):
            c = self.canonical_of(e)
            c[field] = val
            lib.write_entry(e["path"], c)
            self.reload_entry(e)
        else:
            e[field] = val
        mark = (DOT_TRUE if field == "milestone" else STAR) if val \
            else (DOT_FALSE if field == "milestone" else "·")
        self.say(f"{'✓' if val else '·'} {field} {mark} {e['relpath']}")
        self.refresh_rows()

    def guard_result(self, entry, choice):
        if choice is None:
            self.say("cancelled — nothing written")
        elif choice == "keep":  # dates stay in the file, dormant (⚠ in the
            self.snapshot(entry)  # grid) until milestone returns
            c = self.canonical_of(entry)
            c["milestone"] = False
            lib.write_entry(entry["path"], c)
            self.reload_entry(entry)
            self.say(f"· milestone off — dates kept dormant "
                     f"({entry['relpath']})")
        else:  # drop
            self.snapshot(entry)
            c = self.canonical_of(entry)
            c["milestone"], c["dates"] = False, []
            lib.write_entry(entry["path"], c)
            self.reload_entry(entry)
            self.say(f"✓ dates dropped — {entry['relpath']}")
        self.refresh_rows()

    # ------------------------------------------------------------- dates

    def action_add_dates(self):
        e = self.cursor_entry()
        if e:
            self.app.push_screen(QuickDatesModal(e, self.dates_added))

    def dates_added(self, entry, new_dates):
        self.snapshot(entry)
        c = self.canonical_of(entry)
        c["dates"] = sorted(set(c["dates"]) | set(new_dates))
        forced = bool(c["dates"]) and not c["milestone"]
        lib.normalize_entry(c)  # dates need milestone: true; override start/end
        lib.write_entry(entry["path"], c)
        self.reload_entry(entry)
        note = " (milestone auto-set)" if forced else ""
        self.say(f"✓ {len(c['dates'])} dates — {entry['relpath']}{note}")
        self.refresh_rows()

    # ------------------------------------------------------------ editing

    def action_edit_row(self):
        e = self.cursor_entry()
        if e:
            self.snapshot(e)  # the editor may write; remember for discard
            self.app.push_screen(EditorScreen(e, self.parent_stems(e),
                                              self.entry_saved))

    def entry_saved(self, entry, warnings):
        self.reload_entry(entry)
        msg = f"✓ wrote {entry['relpath']}"
        if warnings:
            msg += " — " + "; ".join(warnings)
        self.say(msg, error=bool(warnings))
        self.refresh_rows()

    # ------------------------------------------------------------- sort

    def action_sort_column(self):
        """s: sort by the cursor's column — s again flips direction
        (ascending surfaces the blanks, descending sinks them), a third
        s returns to scan order. Undated keeps its leading segment; the
        sort orders inside each segment."""
        t = self.query_one("#table", DataTable)
        col = min(t.cursor_column, len(COLUMNS) - 1)
        h, field, kind = COLUMNS[col]
        if self._sort and self._sort[0] == col and self._sort[1] == "desc":
            self._sort = None
            self.refresh_rows()
            self.say("sort cleared — scan order, undated segment first")
            return
        self._sort = (col, "desc" if self._sort and self._sort[0] == col
                      else "asc")
        self.refresh_rows()
        up = self._sort[1] == "asc"
        if kind == "date" or field == "dates":
            detail = ("blanks, then year-only, then year+month, then full "
                      "date — coarsest first" if up else
                      "fullest dates, newest first — blanks last")
        elif kind.startswith("bool"):
            detail = "○/· before ●/★" if up else "●/★ first"
        else:
            detail = "blanks first, A→Z" if up else "Z→A, blanks last"
        self.say(f"sorted by {h} {'↑' if up else '↓'} — {detail}")

    # ------------------------------------------------------------ filter

    def matches(self, e, q):
        if not q:
            return True
        blob = " ".join((e["company"], e["role"], e["entry_type"], e["category"],
                         e["stem"], e["industry"], e["location"], e["country"],
                         " ".join(e["parent"]))).lower()
        for tok in q.lower().split():
            if tok in ("ms", "ms:true", "milestone"):
                ok = e["milestone"]
            elif tok == "ms:false":
                ok = not e["milestone"]
            elif tok in ("feat", "feat:true", "featured"):
                ok = e["featured"]
            elif tok == "feat:false":
                ok = not e["featured"]
            elif tok == "undated":
                ok = not (e["dates"] or e["start"])
            elif tok == "dated":
                ok = bool(e["dates"] or e["start"])
            elif tok == "hasdates":
                ok = bool(e["dates"])
            elif tok.startswith("cat:"):
                ok = e["category"].startswith(tok[4:])
            elif tok.startswith("type:"):
                ok = e["entry_type"] == tok[5:]
            else:
                ok = tok in blob
            if not ok:
                return False
        return True

    def action_focus_filter(self):
        self.query_one("#filter", Input).focus()

    @on(Input.Changed)
    def filter_changed(self, event):
        if event.input.id == "filter":
            self.filter_q = event.value.strip()
            self.refresh_rows()

    @on(Input.Submitted)
    def filter_submitted(self, event):
        if event.input.id == "filter":
            self.query_one("#table", DataTable).focus()

    def action_escape(self):
        if self._edit is not None:  # editors handle escape themselves
            return
        if isinstance(self.focused, Input):  # leave the filter box first
            self.query_one("#table", DataTable).focus()
            return
        self.query_one("#filter", Input).value = ""
        self.filter_q = ""
        self.refresh_rows()
        self.say("filter cleared")

    # ----------------------------------------------------------- rebuild

    async def _run_build(self):
        """Run build.py in index.html's current style; return (ok, tail) —
        the last line of output, or the reason it couldn't start."""
        style = lib.current_style()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "build.py", *([style] if style else []),
                cwd=lib.ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
        except OSError as ex:
            return False, f"build failed to start: {ex}"
        out, _ = await proc.communicate()
        lines = [l for l in out.decode(errors="replace").splitlines() if l.strip()]
        tail = lines[-1] if lines else f"exit {proc.returncode}"
        return proc.returncode == 0, tail

    async def action_rebuild(self):
        """r: rebuild and report the outcome in a centered popup."""
        style = lib.current_style()
        self.say(f"rebuilding index.html{f' (style {style})' if style else ''}…")
        ok, msg = await self._run_build()
        self.say(("✓ " if ok else "✗ ") + msg, error=not ok)
        self.app.push_screen(RebuildResultModal(ok, msg, style))

    def action_quit(self):
        """q: quit — with session changes, ask first: save / save + rebuild
        / discard (restores every file's pre-session text)."""
        if self._touched:
            self.app.push_screen(ExitModal(len(self._touched),
                                           self.exit_choice))
        else:
            self.app.exit()

    def exit_choice(self, choice):
        if choice is None:
            self.say("quit cancelled — changes stay written")
            return
        if choice == "save":  # writes were immediate; nothing to do
            self.app.exit()
            return
        if choice == "discard":
            for relpath, text in self._touched.items():
                e = self.by.get(relpath)
                if e:
                    with open(e["path"], "w", encoding="utf-8") as f:
                        f.write(text)
                    self.reload_entry(e)
            self.say(f"↩ discarded changes in {len(self._touched)} file(s)")
            self._touched.clear()
            self.refresh_rows()
            self.app.exit()
            return
        asyncio.create_task(self._rebuild_then_report())  # save + rebuild

    async def _rebuild_then_report(self):
        """save + rebuild from the quit prompt: show the build's result in
        the same centered popup. On error, stay put — quitting stays blocked
        and a later q offers the dialog again. On success, commit (the files
        are on disk) so a second q closes without asking."""
        style = lib.current_style()
        self.say(f"rebuilding index.html{f' (style {style})' if style else ''}…")
        ok, msg = await self._run_build()
        self.say(("✓ " if ok else "✗ ") + msg, error=not ok)
        if ok:
            self._touched.clear()
        self.app.push_screen(RebuildResultModal(ok, msg, style, blocked=not ok))


# ================================================================= modals

class PickerModal(ModalScreen):
    """A dropdown for a cell: arrows move, enter picks, space/esc back
    out without changes."""

    BINDINGS = [Binding("escape", "cancel", "cancel"),
                Binding("space", "cancel", "back", show=False)]

    def __init__(self, field, value, options, on_pick):
        super().__init__()
        self._field = field
        self._value = value
        self._on_pick = on_pick
        vals = []
        if value and value not in options:
            vals.append(value)      # e.g. parent's "both of these" option
        vals.extend(o for o in options if o not in vals)
        vals.append("")             # blank is always offered
        self._values = vals

    def compose(self):
        yield Vertical(
            Label(f"{self._field} — arrows move, enter picks, space backs out",
                  classes="picker-title"),
            ListView(*[ListItem(Label(v or "(blank)")) for v in self._values]),
            id="picker-panel")

    def on_mount(self):
        lv = self.query_one(ListView)
        if self._value:
            lv.index = self._values.index(self._value)
        lv.focus()

    @on(ListView.Selected)
    def picked(self, event):
        v = self._values[event.list_view.index]
        self.dismiss()
        self._on_pick(v)

    def action_cancel(self):
        self.dismiss()
        self._on_pick(None)


class DatesGuardModal(ModalScreen):
    """build.py ignores `dates:` without milestone: true — confirm first."""

    BINDINGS = [Binding("escape", "cancel", "cancel"),
                Binding("k", "keep", "keep dates"),
                Binding("d", "drop", "drop dates")]

    def __init__(self, entry, on_result):
        super().__init__()
        self.entry = entry
        self._on_result = on_result

    def compose(self):
        n = len(self.entry["dates"])
        yield Label(f"{self.entry['relpath']} — {n} occurrence "
                    f"date{'s' if n != 1 else ''}")
        yield Label("The build ignores `dates:` unless milestone stays true.")
        yield Label("[k] keep the dates (dormant, ⚠ in the grid)   "
                    "[d] drop them   [esc] cancel")

    def _finish(self, choice):
        self.dismiss()
        self._on_result(self.entry, choice)

    def action_cancel(self):
        self._finish(None)

    def action_keep(self):
        self._finish("keep")

    def action_drop(self):
        self._finish("drop")


class QuickDatesModal(ModalScreen):
    """Add occurrence dates to a recurring event without the grid."""

    BINDINGS = [Binding("escape", "cancel", "cancel")]

    def __init__(self, entry, on_added):
        super().__init__()
        self.entry = entry
        self._on_added = on_added

    def compose(self):
        existing = ", ".join(self.entry["dates"]) or "none yet"
        yield Label(f"add dates to {self.entry['relpath']}")
        yield Label(f"existing: {existing}", classes="panel-sub")
        yield Input(placeholder="2024-05, 2025, 2026-09-11  (enter to save)",
                    id="qd-input")
        yield Label("", id="qd-error")
        yield Label("[enter] add   [esc] cancel — dates sort, dedupe, and "
                    "turn milestone on", classes="panel-sub")

    def on_mount(self):
        self.query_one("#qd-input", Input).focus()

    @on(Input.Submitted)
    def submitted(self, event):
        if event.input.id != "qd-input":
            return
        parts = [p for p in event.value.replace(",", " ").split() if p]
        bad = [p for p in parts if not lib.parse_date(p)]
        if bad:
            self.query_one("#qd-error", Label).update(
                f"✗ not dates: {', '.join(bad)} — use YYYY, YYYY-MM or YYYY-MM-DD")
            return
        self.dismiss()
        self._on_added(self.entry, sorted(set(parts)))

    def action_cancel(self):
        self.dismiss()


class ExitModal(ModalScreen):
    """The quit prompt when this session changed files: save (already on
    disk), save + rebuild, or discard — restore every pre-session file.
    Centered; ↑/↓ move, enter chooses, s/r/x are shortcuts."""

    BINDINGS = [Binding("escape", "cancel", "stay"),
                Binding("s", "save", "save"),
                Binding("r", "rebuild", "save + rebuild"),
                Binding("x", "discard", "discard")]

    # (choice sent to the caller, menu line)
    CHOICES = [("save", "Save changes and quit"),
               ("rebuild", "Save + rebuild index.html, then show the result"),
               ("discard", "Discard changes — restore the original text"),
               (None, "Stay — cancel quitting")]

    def __init__(self, n_files, on_choice):
        super().__init__()
        self.n = n_files
        self._on_choice = on_choice

    def compose(self):
        n = f"{self.n} file{'s' if self.n != 1 else ''}"
        yield Vertical(
            Label(f"Quit — {n} changed this session", id="exit-title"),
            Label("Changes are already written to disk. Rebuilding refreshes "
                  "index.html; discarding restores the original text.",
                  id="exit-body"),
            ListView(*[ListItem(Label(text)) for _c, text in self.CHOICES],
                     id="exit-choices"),
            Label("[↑/↓] pick   [enter] choose   [s] save   "
                  "[r] save + rebuild   [x] discard   [esc] stay",
                  id="exit-hint"),
            id="exit-panel")

    def on_mount(self):
        self.query_one("#exit-choices", ListView).focus()

    @on(ListView.Selected)
    def _picked(self, event):
        self._finish(self.CHOICES[event.list_view.index][0])

    def _finish(self, choice):
        self.dismiss()
        self._on_choice(choice)

    def action_cancel(self):
        self._finish(None)

    def action_save(self):
        self._finish("save")

    def action_rebuild(self):
        self._finish("rebuild")

    def action_discard(self):
        self._finish("discard")


class RebuildResultModal(ModalScreen):
    """A centered report of build.py's run — success, or the failing tail.
    Shows for a plain r and for save + rebuild; any key closes it, and the
    caller (not this screen) decides whether to stay or exit."""

    BINDINGS = [Binding("escape", "close", "close"),
                Binding("enter", "close", "close", show=False),
                Binding("q", "close", "close", show=False)]

    def __init__(self, ok, message, style=None, blocked=False):
        super().__init__()
        self.ok = ok
        self.message = message
        self.style = style
        self.blocked = blocked  # save + rebuild failed: quitting is blocked

    def compose(self):
        head = "✓ rebuild succeeded" if self.ok else "✗ rebuild failed"
        if self.style:
            head += f" — style {self.style}"
        body = self.message
        if self.blocked:
            body += ("\nindex.html was not updated — you stay here; "
                     "press q to try again or discard the changes.")
        yield Vertical(
            Label(head, id="rb-title", classes="-ok" if self.ok else "-bad"),
            Label(body, id="rb-body"),
            Label("[enter] close", id="rb-hint"),
            id="rb-panel")

    def action_close(self):
        self.dismiss()


# ============================================================== full editor

class EditorScreen(ModalScreen):
    """The 20-field editor for one entry: checkbox booleans, dropdowns for
    the closed vocabularies (entry_type, employment_type, location_type,
    image_view), and for parent (the corpus's own entry slugs), inputs for
    scalars, and one-item-per-line text areas for every list. ctrl+s
    saves, esc cancels."""

    BINDINGS = [Binding("ctrl+s", "save", "save"),
                Binding("escape", "cancel", "cancel")]

    TEXT_SCALARS = ("company", "role", "industry", "url", "start", "end",
                    "location", "country", "logo")
    DROPDOWN_SCALARS = ("entry_type", "employment_type", "location_type",
                        "image_view")
    DROPDOWN_VOCAB = {"entry_type": [t for t, _d in lib.ENTRY_TYPES],
                      "employment_type": list(lib.EMPLOYMENT_TYPES),
                      "location_type": list(lib.LOCATION_TYPES),
                      "image_view": ["full"]}
    HINTS = {"start": "— YYYY, YYYY-MM or YYYY-MM-DD; blank = undated",
             "end": "— blank = Present",
             "logo": "— filename, resolved from logos/ then this directory",
             "location_type": ""}

    def __init__(self, entry, parent_stems, on_saved):
        super().__init__()
        self.entry = entry
        self._parent_stems = parent_stems
        self._on_saved = on_saved

    def _select(self, key, value, vocab=None):
        vocab = self.DROPDOWN_VOCAB[key] if vocab is None else vocab
        opts = [(v, v) for v in vocab]
        if value and value not in vocab:  # e.g. parent's "both of these"
            opts.insert(0, (value, value))
        # Select.NULL (not None) is Textual's blank — None raises
        return Select(opts, value=value or Select.NULL, allow_blank=True,
                      id=f"fld-{key}")

    def compose(self):
        e = self.entry
        yield VerticalScroll(
            Label(f"editing {e['relpath']}", id="editor-title"),
            Label("", id="editor-error"),
            Label("entry_type:"),
            self._select("entry_type", e["entry_type"]),
            Checkbox("milestone — one-off point event (renders as a line)",
                     value=e["milestone"], id="fld-milestone"),
            Checkbox("featured — gold highlight + star",
                     value=e["featured"], id="fld-featured"),
            Label("parent — pick an existing entry (blank = none)"),
            self._select("parent", " · ".join(e["parent"]),
                         self._parent_stems),
            *[w for k in ("company", "role") for w in (Label(f"{k}:"), Input(
                value=e[k], id=f"fld-{k}"))],
            Label("employment_type:"),
            self._select("employment_type", e["employment_type"]),
            *[w for k in ("industry", "url") for w in (Label(f"{k}:"), Input(
                value=e[k], id=f"fld-{k}"))],
            *[w for k in ("start", "end") for w in (
                Label(f"{k}: {self.HINTS[k]}"), Input(
                    value=e[k], id=f"fld-{k}"))],
            Label("dates — one occurrence date per line (replaces start/end, "
                  "needs milestone)"),
            TextArea("\n".join(e["dates"]), id="fld-dates"),
            *[w for k in ("location", "country") for w in (Label(f"{k}:"), Input(
                value=e[k], id=f"fld-{k}"))],
            Label("location_type:"),
            self._select("location_type", e["location_type"]),
            Label("accomplishments — one bullet per line"),
            TextArea("\n".join(e["accomplishments"]), id="fld-accomplishments"),
            Label("skills — one tag per line"),
            TextArea("\n".join(e["skills"]), id="fld-skills"),
            Label(f"logo: {self.HINTS['logo']}"),
            Input(value=e["logo"], id="fld-logo"),
            Label("images — one filename per line"),
            TextArea("\n".join(e["images"]), id="fld-images"),
            Label("image_view — 'full' = picture view (needs milestone + "
                  "exactly one image)"),
            self._select("image_view", e["image_view"]),
            Horizontal(Button("Save", id="btn-save"),
                       Button("Cancel", id="btn-cancel"), id="editor-buttons"),
            id="editor-scroll")

    def on_mount(self):
        self.query_one("#fld-company", Input).focus()

    @on(Button.Pressed, "#btn-save")
    def save_pressed(self):
        self.action_save()

    @on(Button.Pressed, "#btn-cancel")
    def cancel_pressed(self):
        self.action_cancel()

    def collect(self):
        c = {"milestone": False, "featured": False, "parent": [], "dates": []}
        for k in self.DROPDOWN_SCALARS:
            v = self.query_one(f"#fld-{k}", Select).value
            c[k] = v.strip() if isinstance(v, str) else ""
        c["milestone"] = self.query_one("#fld-milestone", Checkbox).value
        c["featured"] = self.query_one("#fld-featured", Checkbox).value
        v = self.query_one("#fld-parent", Select).value
        c["parent"] = v.split(" · ") if isinstance(v, str) and v else []
        for k in self.TEXT_SCALARS:
            c[k] = self.query_one(f"#fld-{k}", Input).value.strip()
        c["dates"] = [d.strip() for d in
                      self.query_one("#fld-dates", TextArea).text.splitlines()
                      if d.strip()]
        for k in ("accomplishments", "skills", "images"):
            c[k] = [x.strip() for x in
                    self.query_one(f"#fld-{k}", TextArea).text.splitlines()
                    if x.strip()]
        return c

    def validate(self, c):
        for k in ("start", "end"):
            if c[k] and not lib.parse_date(c[k]):
                return f"{k}: '{c[k]}' is not YYYY, YYYY-MM or YYYY-MM-DD"
        for d in c["dates"]:
            if not lib.parse_date(d):
                return f"dates: '{d}' is not YYYY, YYYY-MM or YYYY-MM-DD"
        if c["start"] and c["end"] and \
                lib.parse_date(c["end"]) < lib.parse_date(c["start"]):
            return "end is before start"
        if not c["company"] and (c["milestone"] or not c["role"]):
            return ("company is required — milestones headline it; cards "
                    "headline company or role")
        if c["url"] and not c["url"].startswith(("http://", "https://")):
            return "url must start with http:// or https://"
        return None

    def warnings(self, c):
        """Non-blocking checks, reported after the save (build tolerates)."""
        cat, stem = self.entry["category"], self.entry["stem"]
        out = []
        bad = [s for s in c["parent"] if not lib.parent_resolvable(s, cat, stem)]
        if bad:
            out.append(f"unresolved parents: {', '.join(bad)}")
        miss = [f for f in c["images"]
                if not lib.resolve_asset(cat, f, prefer_logos=False)]
        if miss:
            out.append(f"images not found: {', '.join(miss)}")
        if c["logo"] and not lib.resolve_asset(cat, c["logo"], prefer_logos=True):
            out.append(f"logo not found: {c['logo']}")
        if c["image_view"] and (not c["milestone"] or len(c["images"]) != 1):
            out.append("image_view: full ignored — it needs milestone: true "
                       "and exactly one image")
        return out

    def action_save(self):
        c = self.collect()
        err = self.validate(c)
        if err:
            self.query_one("#editor-error", Label).update(f"✗ {err}")
            return
        forced = bool(c["dates"]) and not c["milestone"]
        lib.normalize_entry(c)  # dates need milestone: true; override start/end
        try:
            lib.write_entry(self.entry["path"], c)
        except ValueError as ex:
            self.query_one("#editor-error", Label).update(f"✗ {ex}")
            return
        warns = self.warnings(c)
        if forced:
            warns.insert(0, "milestone auto-set (dates need it)")
        self.dismiss()
        self._on_saved(self.entry, warns)

    def action_cancel(self):
        self.dismiss()


# ==================================================================== app

class EntriesApp(App):

    TITLE = "CV entries — space edits or toggles the focused cell"
    CSS = """
    MainScreen { layout: vertical; }
    #filter { height: 3; }
    #table { height: 1fr; }
    #cellbar { height: auto; border-top: hkey $primary; padding: 0 1; }
    #cell-label { height: 1; color: $text-muted; }
    #cell-view { height: 1; }
    #cell-input { height: 3; display: none; }
    #cell-area { height: auto; max-height: 10; display: none; }
    #status { height: 1; }
    EditorScreen { layout: vertical; }
    #editor-scroll { border: round $primary; padding: 0 2; height: 1fr; }
    #editor-title { background: $primary; color: $text; padding: 0 1; }
    #editor-error { color: $text-error; }
    #editor-buttons { height: 3; padding: 1 0; }
    DatesGuardModal, QuickDatesModal, PickerModal,
    ExitModal, RebuildResultModal { align: center middle; }
    DatesGuardModal > Label, QuickDatesModal > Label {
        border: round $accent; background: $surface;
        padding: 0 2; width: 90; height: auto;
    }
    #exit-panel, #rb-panel {
        border: round $accent; background: $surface;
        padding: 1 2; width: 74; height: auto;
    }
    #exit-title, #rb-title { text-style: bold; width: 100%; }
    #rb-title.-ok { color: $text-success; }
    #rb-title.-bad { color: $text-error; }
    #exit-body, #exit-hint, #rb-body, #rb-hint {
        color: $text-muted; width: 100%; height: auto;
    }
    #exit-choices { height: auto; max-height: 8; }
    #picker-panel { border: round $accent; background: $surface;
                    padding: 0 2; width: 40; height: auto; }
    #picker-panel ListView { max-height: 20; }
    .picker-title { color: $text-muted; }
    .panel-sub { color: $text-muted; }
    #qd-error { color: $text-error; }
    """

    def get_default_screen(self):
        return MainScreen()


if __name__ == "__main__":
    EntriesApp().run()
"""Headless pilot smoke for the spreadsheet TUI: rewrites the two
zz-smoke-* fixture entries, then drives the grid, cell editors, pickers,
the full editor, the filter and a rebuild end to end.
Run: python3 _smoke_tui.py"""
import asyncio
import sys

import yaml

sys.path.insert(0, ".")
from tui import (EntriesApp, MainScreen, EditorScreen, QuickDatesModal,
                 DatesGuardModal, PickerModal, ExitModal, RebuildResultModal,
                 COLUMNS)
from textual.containers import Vertical
from textual.widgets import DataTable, Input, TextArea, Label, ListView, Select
import entry_lib as lib

A = "content/zz-smoke-a/zz-smoke-a.yaml"
B = "content/zz-smoke-b/zz-smoke-b.yaml"
ENTRY_A = """entry_type: events
milestone: false
featured: false
parent:
company: Smoke A
role: Test Entry
employment_type:
industry: testing
url:
start: "2024-01"
end: "2024-06"
dates:
location: Chiang Rai
country: Thailand
location_type: onsite
accomplishments:
 - A smoke-test bullet.
skills:
 - smoke
logo:
images:
"""
ENTRY_B = """entry_type: job
milestone: false
featured: false
parent:
company: Smoke B
role: Old Style
employment_type:
industry:
start: "2020"
end:
location:
country:
location_type:
accomplishments:
 -
 -
skills:
 -
logo:
images:
 -
 -
"""
COL = {h: i for i, (h, _f, _k) in enumerate(COLUMNS)}


def rows(app):
    return app.query_one("#table", DataTable).row_count


def ms(app):
    return app.screen


def goto(app, relpath, col):
    """Move the table cursor onto an entry's row (table rows carry the
    segment dividers, so the view index is not the row index)."""
    m = ms(app)
    row = next(i for i, e in enumerate(m._rows)
               if e is not None and e["relpath"] == relpath)
    m.query_one("#table", DataTable).move_cursor(row=row, column=col)


def bar_visible(app):
    return ms(app)._edit is not None


def set_parents(app, relpath, slugs):
    """Hand-write a parent list straight to the file, then rescan."""
    m = ms(app)
    with open(relpath, encoding="utf-8") as f:
        c = lib.canonical(yaml.safe_load(f) or {})
    c["parent"] = slugs
    lib.write_entry(relpath, c)
    m.rescan()


async def main():
    open(A, "w").write(ENTRY_A)
    open(B, "w").write(ENTRY_B)
    app = EntriesApp()
    async with app.run_test(size=(150, 45)) as pilot:
        m = ms(app)
        assert isinstance(m, MainScreen)
        await pilot.pause()
        N = len(m.entries)              # corpus count (fixtures included)
        assert rows(app) == len(m._rows) == N + len(m._dividers), (rows(app), N)
        # idle formula bar shows the focused cell (table row 0 is the
        # undated-divider, so land on an entry first)
        goto(app, A, COL["ms"])
        await pilot.pause()
        assert "milestone" in str(m.query_one("#cell-label", Label).content)

        # ---- text cell: space edits, enter commits + advances one row down
        row_a = next(i for i, e in enumerate(m._rows)
                     if e is not None and e["relpath"] == A)
        goto(app, A, COL["company"])
        await pilot.press("space"); await pilot.pause()
        assert bar_visible(app)
        assert m.query_one("#cell-input", Input).value == "Smoke A"
        m.query_one("#cell-input", Input).value = "Smoke A Prime"
        await pilot.press("enter"); await pilot.pause()
        now = open(A).read()
        assert "company: Smoke A Prime" in now, now
        assert len(now.splitlines()) == len(ENTRY_A.splitlines())
        diff = [(x, y) for x, y in zip(ENTRY_A.splitlines(), now.splitlines()) if x != y]
        assert diff == [("company: Smoke A", "company: Smoke A Prime")], diff
        assert not bar_visible(app)
        cur_row = m.query_one("#table", DataTable).cursor_row
        assert cur_row == row_a + 1, (cur_row, row_a)  # advanced down the column

        # ---- escape cancels without writing (enter still opens too)
        goto(app, A, COL["role"])
        await pilot.press("enter"); await pilot.pause()
        m.query_one("#cell-input", Input).value = "Changed"
        await pilot.press("escape"); await pilot.pause()
        assert "role: Test Entry" in open(A).read()
        assert not bar_visible(app)

        # ---- date cell: invalid input blocks, valid commits
        goto(app, A, COL["start"])
        await pilot.press("enter"); await pilot.pause()
        m.query_one("#cell-input", Input).value = "13"
        await pilot.press("enter"); await pilot.pause()
        assert bar_visible(app), "invalid date must keep the editor open"
        assert 'start: "2024-01"' in open(A).read()
        m.query_one("#cell-input", Input).value = "2024-02"
        await pilot.press("enter"); await pilot.pause()
        assert 'start: "2024-02"' in open(A).read()

        # ---- dropdown cell: picker modal selects and writes
        goto(app, A, COL["employment"])
        await pilot.press("enter"); await pilot.pause()
        assert isinstance(app.screen, PickerModal)
        await pilot.press("down"); await pilot.pause()
        await pilot.press("enter"); await pilot.pause()
        assert "employment_type: part-time" in open(A).read(), open(A).read()
        # space opens the dropdown too, and space backs out without changes
        goto(app, A, COL["loc type"])
        await pilot.press("space"); await pilot.pause()
        assert isinstance(app.screen, PickerModal)
        await pilot.press("space"); await pilot.pause()
        assert "location_type: onsite" in open(A).read()
        assert not bar_visible(app)
        assert "cancelled" in m._note, m._note

        # ---- list cell: enter adds a line, empty line commits
        goto(app, A, COL["dates"])
        await pilot.press("enter"); await pilot.pause()
        area = m.query_one("#cell-area", TextArea)
        area.load_text("2024-05\n2025\n2024-05")
        area.move_cursor(location=(2, 7))  # caret at end, like a real user
        await pilot.press("enter"); await pilot.pause()
        assert len(area.text.split("\n")) == 4, "enter must add a line"
        await pilot.press("enter"); await pilot.pause()   # empty line commits
        now = open(A).read()
        assert ' - "2024-05"\n - "2025"' in now, now
        assert "milestone: true" in now, "dates auto-set milestone"
        assert "start:\nend:\n" in now, "dates blank start/end"
        assert not bar_visible(app)

        # ---- skills list cell
        goto(app, A, COL["skills"])
        await pilot.press("enter"); await pilot.pause()
        m.query_one("#cell-area", TextArea).load_text("smoke\ntest")
        m.query_one("#cell-area", TextArea).move_cursor(location=(1, 4))
        await pilot.press("enter"); await pilot.press("enter"); await pilot.pause()
        assert " - smoke\n - test" in open(A).read()

        # ---- bool cells: space toggles; ★ column is featured, ms is milestone
        goto(app, A, COL["★"])
        await pilot.press("space"); await pilot.pause()
        assert "featured: true" in open(A).read()
        await pilot.press("space"); await pilot.pause()
        assert "featured: false" in open(A).read()
        goto(app, A, COL["ms"])
        await pilot.press("space"); await pilot.pause()   # dated → guard
        assert isinstance(app.screen, DatesGuardModal)
        await pilot.press("k"); await pilot.pause()       # keep dates dormant
        assert "milestone: false" in open(A).read()
        await pilot.press("space"); await pilot.pause()   # off → on, no guard
        assert "milestone: true" in open(A).read()
        await pilot.press("enter"); await pilot.pause()   # enter toggles too
        assert isinstance(app.screen, DatesGuardModal)
        await pilot.press("d"); await pilot.pause()       # drop dates + flag
        now = open(A).read()
        assert "milestone: false" in now and "2024-05" not in now, now
        await pilot.press("space"); await pilot.pause()   # plain toggle now
        assert "milestone: true" in open(A).read()

        # ---- category cell is read-only
        goto(app, A, COL["category"])
        await pilot.press("space"); await pilot.pause()
        assert not bar_visible(app)
        assert "read-only" in m._note, m._note

        # ---- right edge: highlighting the category column must not crash
        #      (KeyError None — it's the one field-less readonly column)
        goto(app, A, COL["company"])
        for _ in range(COL["category"] - COL["company"]):
            await pilot.press("right")
        await pilot.pause()
        assert "category" in str(m.query_one("#cell-label", Label).content)
        assert "zz-smoke-a" in str(m.query_one("#cell-view", Label).content)

        # ---- guard drop path via quick-dates on B
        goto(app, B, COL["dates"])
        await pilot.press("d"); await pilot.pause()
        app.screen.query_one("#qd-input", Input).value = "2021-03"
        await pilot.press("enter"); await pilot.pause()
        assert '"2021-03"' in open(B).read()
        goto(app, B, COL["ms"])            # dates set milestone → guard
        await pilot.press("space"); await pilot.pause()
        assert isinstance(app.screen, DatesGuardModal)
        await pilot.press("d"); await pilot.pause()
        now = open(B).read()
        assert "milestone: false" in now and '"2021-03"' not in now

        # ---- parent: a dropdown of the corpus's entry slugs
        goto(app, B, COL["parent"])
        await pilot.press("space"); await pilot.pause()
        pm = app.screen
        assert isinstance(pm, PickerModal)
        assert "arrows move" in \
            str(pm.query_one(".picker-title", Label).content)
        lv = pm.query_one(ListView)
        assert lv.size.height <= 22, lv.size.height   # long list scrolls
        assert "zz-smoke-a" in pm._values and "zz-smoke-b" not in pm._values
        assert pm._values[-1] == ""                   # blank offered last
        await pilot.press("space"); await pilot.pause()   # backs out
        assert "cancelled" in m._note, m._note
        assert "\nparent:\ncompany:" in open(B).read()

        goto(app, B, COL["parent"])
        await pilot.press("space"); await pilot.pause()
        pm = app.screen
        pm.query_one(ListView).index = pm._values.index("zz-smoke-a")
        await pilot.press("enter"); await pilot.pause()   # enter picks
        assert "parent: zz-smoke-a" in open(B).read(), open(B).read()

        # several parents appear as one "both of these" choice
        set_parents(app, B, ["amazon", "zz-smoke-a"])
        await pilot.pause()
        goto(app, B, COL["parent"])
        await pilot.press("space"); await pilot.pause()
        pm = app.screen
        assert pm._values[0] == "amazon · zz-smoke-a", pm._values[:2]
        assert pm.query_one(ListView).index == 0        # highlighted
        await pilot.press("enter"); await pilot.pause()
        assert "parent:\n - amazon\n - zz-smoke-a" in open(B).read(), \
            open(B).read()

        # picking one slug replaces the set; blank clears it
        goto(app, B, COL["parent"])
        await pilot.press("space"); await pilot.pause()
        pm = app.screen
        pm.query_one(ListView).index = pm._values.index("wwoof")
        await pilot.press("enter"); await pilot.pause()
        assert "parent: wwoof" in open(B).read(), open(B).read()
        goto(app, B, COL["parent"])
        await pilot.press("space"); await pilot.pause()
        pm = app.screen
        pm.query_one(ListView).index = len(pm._values) - 1   # (blank)
        await pilot.press("enter"); await pilot.pause()
        assert "\nparent:\ncompany:" in open(B).read(), open(B).read()

        # ---- full editor: dropdowns for the closed vocabularies
        goto(app, A, COL["company"])
        await pilot.press("e"); await pilot.pause()
        assert isinstance(app.screen, EditorScreen)
        assert isinstance(app.screen.query_one("#fld-employment_type", Select), Select)
        assert isinstance(app.screen.query_one("#fld-location_type", Select), Select)
        await pilot.press("escape"); await pilot.pause()

        # ---- editor on blank dropdown fields (used to crash: Select
        #      rejects value=None) + parent dropdown round-trips
        goto(app, B, COL["company"])
        await pilot.press("e"); await pilot.pause()
        ed = app.screen
        assert isinstance(ed, EditorScreen)
        psel = ed.query_one("#fld-parent", Select)
        assert isinstance(psel, Select)
        assert psel.value == Select.NULL, psel.value      # blank parent
        assert len(psel._options) == len({e["stem"] for e in m.entries}), \
            len(psel._options)  # every stem but this row's, + blank
        await pilot.press("ctrl+s"); await pilot.pause()
        assert "\nparent:\ncompany:" in open(B).read(), open(B).read()
        assert "✓ wrote" in m._note, m._note

        # editor keeps a multi-parent entry's set through a save
        set_parents(app, B, ["amazon", "zz-smoke-a"])
        await pilot.pause()
        goto(app, B, COL["company"])
        await pilot.press("e"); await pilot.pause()
        ed = app.screen
        assert ed.query_one("#fld-parent", Select).value == "amazon · zz-smoke-a"
        await pilot.press("ctrl+s"); await pilot.pause()
        assert "parent:\n - amazon\n - zz-smoke-a" in open(B).read(), \
            open(B).read()

        # ---- filter tokens still work on the grid
        f = m.query_one("#filter", Input)
        n_ms = sum(1 for e in lib.scan_entries()[0] if e["milestone"])
        f.value = "ms:true"; await pilot.pause()
        assert rows(app) == n_ms + len(m._dividers), (rows(app), n_ms)
        await pilot.press("escape"); await pilot.pause()   # leave filter box
        await pilot.press("escape"); await pilot.pause()   # clear filter
        assert rows(app) == len(m._rows)

        # ---- rebuild pops a centered success report, then closes back
        await pilot.press("r")
        await pilot.pause(delay=3.0)
        assert isinstance(app.screen, RebuildResultModal), app.screen
        rb = app.screen
        assert rb.ok and f"{N} entries" in rb.message, rb.message
        rpanel = rb.query_one("#rb-panel", Vertical).region
        # centered: the panel's middle sits on the screen's middle (it used
        # to render in the top-left corner)
        assert abs((rpanel.x + rpanel.width / 2) - app.size.width / 2) <= 2, rpanel
        assert abs((rpanel.y + rpanel.height / 2) - app.size.height / 2) <= 2, rpanel
        assert f"{N} entries" in m._note and m._note.startswith("✓"), m._note
        await pilot.press("enter"); await pilot.pause()
        assert isinstance(app.screen, MainScreen)

        # ---- quit prompt: centered + selectable; esc stays put
        assert m._touched, "edits above must leave the session dirty"
        await pilot.press("q"); await pilot.pause()
        assert isinstance(app.screen, ExitModal), app.screen
        ex = app.screen
        epanel = ex.query_one("#exit-panel", Vertical).region
        assert abs((epanel.x + epanel.width / 2) - app.size.width / 2) <= 2, epanel
        assert abs((epanel.y + epanel.height / 2) - app.size.height / 2) <= 2, epanel
        assert ex.query_one("#exit-choices", ListView).has_focus
        await pilot.press("escape"); await pilot.pause()
        assert isinstance(app.screen, MainScreen) and m._touched

        # ---- save + rebuild: same popup, then stay; a second q closes
        await pilot.press("q"); await pilot.pause()
        await pilot.press("r"); await pilot.pause(delay=3.0)
        assert isinstance(app.screen, RebuildResultModal), app.screen
        assert app.screen.ok, app.screen.message
        await pilot.press("enter"); await pilot.pause()
        assert isinstance(app.screen, MainScreen), app.screen   # stayed
        assert not m._touched, "save + rebuild commits the session"

        # ---- rebuild error: popup reports it and keeps you here
        goto(app, B, COL["company"])
        await pilot.press("space"); await pilot.pause()
        m.query_one("#cell-input", Input).value = "Smoke B Prime"
        await pilot.press("enter"); await pilot.pause()
        assert m._touched

        async def boom():
            return False, "boom: build broke"
        m._run_build = boom
        await pilot.press("q"); await pilot.pause()
        await pilot.press("r"); await pilot.pause()
        assert isinstance(app.screen, RebuildResultModal), app.screen
        assert not app.screen.ok and app.screen.blocked, app.screen.message
        await pilot.press("enter"); await pilot.pause()
        assert isinstance(app.screen, MainScreen), app.screen   # not exited
        assert m._touched, "a failed build must not commit the session"
        await pilot.press("q"); await pilot.pause()
        assert isinstance(app.screen, ExitModal)                # q still asks

        # ---- discard restores every touched file, then quits
        del m._run_build                    # real build again
        snap = dict(m._touched)
        exits, real_exit = [], app.exit
        app.exit = lambda *a, **k: exits.append(True)
        await pilot.press("x"); await pilot.pause()
        assert exits, "discard must quit"
        assert not m._touched
        for rel, text in snap.items():
            assert open(rel, encoding="utf-8").read() == text, rel
        assert "discarded changes" in m._note, m._note

        # ---- save keeps the writes and quits
        goto(app, B, COL["company"])
        await pilot.press("space"); await pilot.pause()
        m.query_one("#cell-input", Input).value = "Smoke B Final"
        await pilot.press("enter"); await pilot.pause()
        exits.clear()
        await pilot.press("q"); await pilot.pause()
        assert isinstance(app.screen, ExitModal), app.screen
        await pilot.press("s"); await pilot.pause()
        assert exits and "Smoke B Final" in open(B).read()
        app.exit = real_exit
    print("PILOT SMOKE: ALL CHECKS PASSED")


asyncio.run(main())
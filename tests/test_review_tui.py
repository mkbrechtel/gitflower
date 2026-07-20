"""The Textual TUI, driven headlessly through Textual's pilot."""

import asyncio

import pygit2
import pytest

from tests.conftest import git
from gitflower.review import format as fmt, notes, scaffold
from gitflower.review.session import Session
from gitflower.review.tui import ReviewApp, SectionPane


@pytest.fixture
def tui_session(work_repo):
    git(work_repo, "config", "user.name", "Tester")
    git(work_repo, "config", "user.email", "t@example.org")
    git(work_repo, "checkout", "-b", "work/feature/x")
    (work_repo / "README.md").write_text("hello\nworld\n")
    (work_repo / "new.txt").write_text("fresh\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "feature work")
    repo = pygit2.Repository(str(work_repo))
    tip = str(repo.branches.local["work/feature/x"].target)
    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")
    return Session(repo, review, tip)


def drive(session, script):
    async def go():
        app = ReviewApp(session)
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause()
            await script(app, pilot)

    asyncio.run(go())


def _drill_into_diff(app, tree_presses):
    """Selecting a tree leaf focuses the pane on that section."""
    return tree_presses


def test_drill_comment_and_verdict(tui_session):
    async def script(app, pilot):
        # tree order: Review > Sources, Verdicts, General Issues, Diff …, Commits
        await pilot.press("down", "down", "down", "down", "enter")
        pane = app.query_one(SectionPane)
        assert pane.has_focus and pane.rows

        # cursor onto the first quote line, comment there
        quote_index = next(i for i, r in enumerate(pane.rows) if r.kind == "quote")
        pane.move_cursor(quote_index)
        await pilot.press("c")
        await pilot.pause()
        app.query_one("#body").text = "Looks fine."
        await pilot.press("ctrl+s")
        await pilot.pause()
        comments = [e for e in tui_session.review.all_events() if e.keyword == "Commented"]
        assert [c.body for c in comments] == [["Looks fine."]]

        # a question, answered from its own row
        await pilot.press("question_mark")
        await pilot.pause()
        app.query_one("#body").text = "Why though?"
        await pilot.press("ctrl+s")
        await pilot.pause()
        question_row = next(
            i for i, r in enumerate(pane.rows)
            if r.kind == "event" and r.event.keyword == "Question-asked"
        )
        pane.move_cursor(question_row)
        await pilot.press("c")
        await pilot.pause()
        app.query_one("#body").text = "Because."
        await pilot.press("ctrl+s")
        await pilot.pause()
        questions = [
            e for e in tui_session.review.all_events() if e.keyword == "Question-asked"
        ]
        assert questions[0].children[0].keyword == "Answer-given"

        # reactions and verdict cycling
        pane.move_cursor(quote_index)
        await pilot.press("a")
        assert any(e.args == "👍" for e in tui_session.review.all_events())
        await pilot.press("greater_than_sign", "greater_than_sign")
        state = fmt.verdict_of(tui_session.review, "t@example.org")
        assert state == "RequestedChanges"

        # explicit save persists to the notes ref
        await pilot.press("s")
        assert notes.read_note(tui_session.repo, tui_session.tip_sha) is not None

    drive(tui_session, script)


def test_read_tracking_keys(tui_session):
    async def script(app, pilot):
        await pilot.press("down", "down", "down", "down", "enter")
        pane = app.query_one(SectionPane)
        section = pane.section
        quote_index = next(i for i, r in enumerate(pane.rows) if r.kind == "quote")
        pane.move_cursor(quote_index)
        row = pane.rows[quote_index]

        tui_session.mark_read(section, row.quote_position)
        assert tui_session.is_read(section, row.quote_position)
        await pilot.press("u")
        assert not tui_session.is_read(section, row.quote_position)

    drive(tui_session, script)


def test_new_issue_overlay(tui_session):
    async def script(app, pilot):
        await pilot.press("i")
        await pilot.pause()
        app.query_one("#title").value = "naming sweep"
        app.query_one("#body").text = "snake_case everywhere"
        await pilot.press("ctrl+s")
        await pilot.pause()
        issues = [
            s for s in tui_session.review.review_section.sections()
            if s.title.startswith("Issue ")
        ]
        assert [issue.title for issue in issues] == ["Issue naming sweep"]

    drive(tui_session, script)


def test_quit_flushes_dirty_state(tui_session):
    async def script(app, pilot):
        await pilot.press("down", "down", "down", "down", "enter")
        pane = app.query_one(SectionPane)
        quote_index = next(i for i, r in enumerate(pane.rows) if r.kind == "quote")
        pane.move_cursor(quote_index)
        await pilot.press("g")  # react, marks dirty
        await pilot.press("q")  # quit must force-flush

    drive(tui_session, script)
    assert notes.read_note(tui_session.repo, tui_session.tip_sha) is not None

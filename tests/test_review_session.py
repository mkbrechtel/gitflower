"""Session behaviour: anchoring, read-marker persistence, notes round-trips."""

import pygit2
import pytest

from tests.conftest import git
from gitflower.review import format as fmt, notes, scaffold
from gitflower.review.session import Session


@pytest.fixture
def sessioned(work_repo):
    git(work_repo, "config", "user.name", "Tester")
    git(work_repo, "config", "user.email", "t@example.org")
    git(work_repo, "checkout", "-b", "work/feature/x")
    (work_repo / "README.md").write_text("hello\nbrave\nnew\nworld\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "grow the readme")
    repo = pygit2.Repository(str(work_repo))
    tip = str(repo.branches.local["work/feature/x"].target)
    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")
    return Session(repo, review, tip)


def _diff_section(session: Session) -> fmt.Section:
    return session.review.sections[1]


def test_comment_anchors_to_quote_line(sessioned):
    section = _diff_section(sessioned)
    rows = sessioned.rows(section)
    quote_rows = [r for r in rows if r.kind == "quote"]
    target = quote_rows[2]
    sessioned.add_event(section, target, "Commented", body="nice line")
    item_after = target.container[target.index + 1]
    assert isinstance(item_after, fmt.Event)
    assert item_after.keyword == "Commented"
    assert item_after.body == ["nice line"]


def test_comment_from_the_bottom_lands_at_section_top(sessioned):
    section = _diff_section(sessioned)
    eof = sessioned.rows(section)[-1]
    assert eof.kind == "eof"
    sessioned.add_event(section, eof, "Commented", body="overall: fine")
    first_event = section.events()[0]
    assert first_event.body == ["overall: fine"]
    # on disk the event sits before the first quoted line of the section
    body = fmt.render(sessioned.review)
    assert body.index("overall: fine") < body.index("> @@")


def test_answer_nests_under_question(sessioned):
    section = _diff_section(sessioned)
    quote = [r for r in sessioned.rows(section) if r.kind == "quote"][0]
    question = sessioned.add_event(section, quote, "Question-asked", body="why?")
    answer = sessioned.answer(question, "because")
    assert question.children == [answer]
    assert answer.indent == question.indent + 2
    reparsed = fmt.parse(fmt.render(sessioned.review))
    questions = [e for e in reparsed.all_events() if e.keyword == "Question-asked"]
    assert questions[0].children[0].keyword == "Answer-given"


def test_read_markers_round_trip(sessioned):
    section = _diff_section(sessioned)
    quote_rows = [r for r in sessioned.rows(section) if r.kind == "quote"]
    for row in quote_rows[:2]:
        sessioned.mark_read(section, row.quote_position)
    sessioned.mark_read(section, quote_rows[-1].quote_position)
    sessioned.save()

    stored = notes.read_note(sessioned.repo, sessioned.tip_sha)
    # two disjoint runs -> two begin/end pairs, star bullets
    assert stored.count("* Read-by: Tester <t@example.org>; begin") == 2
    assert stored.count("* Read-by: Tester <t@example.org>; end") == 2

    reloaded = Session(
        sessioned.repo, notes.load(sessioned.repo, sessioned.tip_sha),
        sessioned.tip_sha,
    )
    new_section = _diff_section(reloaded)
    read = {
        r.quote_position
        for r in reloaded.rows(new_section)
        if r.kind == "quote" and reloaded.is_read(new_section, r.quote_position)
    }
    assert read == {
        quote_rows[0].quote_position,
        quote_rows[1].quote_position,
        quote_rows[-1].quote_position,
    }


def test_repeated_saves_do_not_stack_markers(sessioned):
    section = _diff_section(sessioned)
    sessioned.mark_read(section, 0)
    sessioned.save()
    sessioned.save()
    stored = notes.read_note(sessioned.repo, sessioned.tip_sha)
    assert stored.count("* Read-by:") == 2  # one begin + one end


def test_issue_and_delete(sessioned):
    issue = sessioned.add_issue("naming sweep", "snake_case everywhere")
    assert issue.title == "Issue naming sweep"
    assert issue.events()[0].keyword == "Issued"

    section = _diff_section(sessioned)
    quote = [r for r in sessioned.rows(section) if r.kind == "quote"][0]
    event = sessioned.add_event(section, quote, "Commented", body="oops")
    assert sessioned.delete_event(section, event)
    assert all(e is not event for e in sessioned.review.all_events())


def test_timestamps_opt_in(sessioned):
    sessioned.with_timestamps = True
    section = _diff_section(sessioned)
    quote = [r for r in sessioned.rows(section) if r.kind == "quote"][0]
    event = sessioned.add_event(section, quote, "Commented", body="stamped")
    assert event.timestamp is not None
    assert "T" in event.timestamp and event.timestamp.endswith("Z")

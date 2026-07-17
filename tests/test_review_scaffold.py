"""Scaffolding a .review from a live repository."""

import pygit2
import pytest

from tests.conftest import git
from gitflower.review import format as fmt, scaffold


@pytest.fixture
def review_repo(work_repo):
    """work_repo plus a feature branch touching every file lifecycle."""
    git(work_repo, "config", "user.name", "Tester")
    git(work_repo, "config", "user.email", "t@example.org")
    (work_repo / "doomed.txt").write_text("short\nlife\n")
    (work_repo / "moved.txt").write_text("stable content\nnothing changes here\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "more files on main")
    git(work_repo, "checkout", "-b", "work/feature/x")
    (work_repo / "README.md").write_text("hello\nworld\n")
    (work_repo / "new.txt").write_text("fresh\n")
    (work_repo / "doomed.txt").unlink()
    git(work_repo, "mv", "moved.txt", "renamed.txt")
    git(work_repo, "add", "-A")
    git(work_repo, "commit", "-m", "feature work\n\nWith a body\nof two lines.")
    return work_repo


def test_scaffold_covers_the_delta(review_repo):
    repo = pygit2.Repository(str(review_repo))
    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")

    assert review.header[0] == (fmt.FILE_VERSION_KEY, fmt.FILE_VERSION)
    assert review.meta("Review-Branch") == "work/feature/x"
    assert review.meta("Created-By") == "Tester <t@example.org>"

    diff_section = review.sections[1]
    assert diff_section.title.startswith("Diff ")
    assert diff_section.recipe.startswith("git diff ")
    titles = {s.title for s in diff_section.sections()}
    assert titles == {
        'File "README.md" modified',
        'File "doomed.txt" deleted',
        'File "moved.txt" moved to "renamed.txt"',
        'File "new.txt" created',
    }

    # one commit in range -> one # Commit section with quoted headers
    commit_section = review.sections[2]
    assert commit_section.title.startswith("Commit ")
    quotes = [q.raw for q in commit_section.quotes()]
    assert quotes[0] == "> From: Test <test@example.invalid>"  # the suite's git env
    assert quotes[2] == "> Subject: feature work"
    assert "> > With a body" in quotes

    # the scaffold parses and round-trips
    assert fmt.render(fmt.parse(fmt.render(review))) == fmt.render(review)


def test_diff_body_shapes(review_repo):
    repo = pygit2.Repository(str(review_repo))
    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")
    by_title = {s.title: s for s in review.sections[1].sections()}

    modified = by_title['File "README.md" modified']
    lines = [q.raw for q in modified.quotes()]
    assert lines[0].startswith("> @@ -1")
    assert "> 1 1: hello" in lines
    assert "> 2: +world" in lines

    deleted = by_title['File "doomed.txt" deleted']
    assert [q.raw for q in deleted.quotes()] == ["> 1: -short", "> 2: -life"]

    created = by_title['File "new.txt" created']
    assert [q.raw for q in created.quotes()] == ["> 1: fresh"]
    assert created.recipe.startswith("git show ")

    moved = by_title['File "moved.txt" moved to "renamed.txt"']
    assert moved.recipe is None
    assert moved.quotes() == []


def test_base_is_last_review_merge(review_repo):
    git(review_repo, "checkout", "-b", "side", "main")
    (review_repo / "side.txt").write_text("side\n")
    git(review_repo, "add", ".")
    git(review_repo, "commit", "-m", "side work")
    git(review_repo, "checkout", "work/feature/x")
    git(review_repo, "merge", "--no-ff", "-m", "[Review] approve up to here", "side")
    (review_repo / "after.txt").write_text("after\n")
    git(review_repo, "add", ".")
    git(review_repo, "commit", "-m", "after the review")

    repo = pygit2.Repository(str(review_repo))
    tip = repo[repo.branches.local["work/feature/x"].target]
    base = scaffold.find_base(repo, tip)
    assert base.message.startswith("[Review]")

    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")
    commits = [s for s in review.sections if s.title.startswith("Commit ")]
    assert len(commits) == 1  # only the post-review commit
    subjects = [q.raw for q in commits[0].quotes() if q.raw.startswith("> Subject:")]
    assert subjects == ["> Subject: after the review"]


def test_merge_commit_gets_per_parent_subsections(review_repo):
    git(review_repo, "checkout", "-b", "topic", "main")
    (review_repo / "topic.txt").write_text("topic\n")
    git(review_repo, "add", ".")
    git(review_repo, "commit", "-m", "topic work")
    git(review_repo, "checkout", "work/feature/x")
    git(review_repo, "merge", "--no-ff", "-m", "merge topic", "topic")

    repo = pygit2.Repository(str(review_repo))
    review = scaffold.scaffold(repo, "work/feature/x", "Tester", "t@example.org")
    merges = [s for s in review.sections if s.title.startswith("Merge-Commit ")]
    assert len(merges) == 1
    assert merges[0].recipe.startswith("git show -m ")
    parents = [s.title for s in merges[0].sections()]
    assert parents == ["Diff from parent 1", "Diff from parent 2"]
    # per-parent file subsections are H3
    parent_one = merges[0].sections()[0]
    assert all(s.level == 3 for s in parent_one.sections())


def test_empty_review(review_repo):
    repo = pygit2.Repository(str(review_repo))
    review = scaffold.scaffold(
        repo, "work/feature/x", "Tester", "t@example.org", empty=True
    )
    assert [s.title for s in review.sections] == ["Review"]

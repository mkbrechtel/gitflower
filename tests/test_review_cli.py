"""The `gitflower review` command (--no-tui paths)."""

import subprocess

import pytest
from click.testing import CliRunner

from tests.conftest import git
from gitflower.cli import main
from gitflower.review import format as fmt


@pytest.fixture
def branch_repo(work_repo, monkeypatch):
    git(work_repo, "config", "user.name", "Tester")
    git(work_repo, "config", "user.email", "t@example.org")
    git(work_repo, "checkout", "-b", "work/feature/x")
    (work_repo / "README.md").write_text("hello\nworld\n")
    git(work_repo, "add", ".")
    git(work_repo, "commit", "-m", "say more")
    monkeypatch.chdir(work_repo)
    return work_repo


def _note(repo, ref="refs/notes/reviews"):
    tip = git(repo, "rev-parse", "work/feature/x").stdout.strip()
    result = git(repo, "notes", "--ref", ref, "show", tip, check=False)
    return result.stdout if result.returncode == 0 else None


def test_no_tui_scaffolds_and_persists(branch_repo, tmp_path):
    mirror = tmp_path / "mirror.review"
    result = CliRunner().invoke(
        main, ["review", "--no-tui", "-o", str(mirror)], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "git notes --ref=refs/notes/reviews show" in result.output
    assert "git cat-file blob" in result.output

    body = _note(branch_repo)
    assert body is not None and fmt.is_dot_review(body)
    review = fmt.parse(body)
    assert review.meta("Review-Branch") == "work/feature/x"
    assert mirror.read_text() == body


def test_rerun_is_non_destructive(branch_repo):
    runner = CliRunner()
    assert runner.invoke(main, ["review", "--no-tui"]).exit_code == 0
    # a reviewer event lands on the note between runs
    body = _note(branch_repo)
    edited = body.replace(
        "# Review\n",
        "# Review\n- Commented-by: Alice <alice@example.com>\n  Keep this.\n",
    )
    tip = git(branch_repo, "rev-parse", "work/feature/x").stdout.strip()
    subprocess.run(
        ["git", "-C", str(branch_repo), "notes", "--ref", "refs/notes/reviews",
         "add", "-f", "-F", "-", tip],
        input=edited, text=True, check=True, capture_output=True,
    )
    assert runner.invoke(main, ["review", "--no-tui"]).exit_code == 0
    assert "Keep this." in _note(branch_repo)


def test_foreign_note_is_imported(branch_repo):
    tip = git(branch_repo, "rev-parse", "work/feature/x").stdout.strip()
    git(branch_repo, "notes", "--ref", "refs/notes/reviews", "add",
        "-m", "Reviewed-By: Kernel Person <kp@example.org>", tip)
    result = CliRunner().invoke(main, ["review", "--no-tui"])
    assert result.exit_code == 0, result.output
    body = _note(branch_repo)
    assert fmt.is_dot_review(body)
    assert "## Note @ git notes --ref=refs/notes/reviews show" in body
    # kernel-style trailer stays grep-able for a future review-gate
    assert "Reviewed-By: Kernel Person <kp@example.org>" in body


def test_empty_review_flag(branch_repo):
    result = CliRunner().invoke(main, ["review", "--no-tui", "--empty-review"])
    assert result.exit_code == 0, result.output
    review = fmt.parse(_note(branch_repo))
    assert [s.title for s in review.sections] == ["Review"]


def test_branch_must_exist(branch_repo):
    result = CliRunner().invoke(main, ["review", "--no-tui", "--branch", "nope"])
    assert result.exit_code != 0
    assert "no such branch" in result.output

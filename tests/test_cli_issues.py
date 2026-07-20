"""The issues CLI family and maintenance command."""

import pytest
from click.testing import CliRunner

from gitflower import gitread
from gitflower.cli import main
from tests.conftest import git
from tests.test_issues import UUID_A, UUID_B, issue_md


@pytest.fixture
def hosted(tmp_path):
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "issues").mkdir()
    (work / "issues" / "login.md").write_text(issue_md(UUID_A, "Login times out", status="open"))
    (work / "issues" / "notes.md").write_text("# id-less notes\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "file issues")
    git(work, "checkout", "-b", "qa")
    (work / "issues" / "crash.md").write_text(issue_md(UUID_B, "Crash on save", status="open"))
    git(work, "add", ".")
    git(work, "commit", "-m", "qa: crash")
    git(work, "checkout", "main")
    git(work, "push", "origin", "main", "qa")
    config = tmp_path / "config.yaml"
    config.write_text(f"repos:\n  directory: {root}\n")
    return config


def run(hosted, *args):
    return CliRunner().invoke(main, ["--config", str(hosted), *args])


def test_issues_list_table(hosted):
    result = run(hosted, "issues", "list", "app.git")
    assert result.exit_code == 0
    assert "Login times out" in result.output
    assert "qa:added" in result.output
    assert "(no id)" in result.output


def test_issues_list_query_json(hosted):
    result = run(hosted, "issues", "list", "app.git", "--format", "json", "--q", "[?id]")
    assert result.exit_code == 0
    assert UUID_A in result.output and UUID_B in result.output
    assert "notes" not in result.output


def test_issues_list_bad_query(hosted):
    result = run(hosted, "issues", "list", "app.git", "--q", "[?broken")
    assert result.exit_code != 0
    assert "JMESPath" in result.output


def test_issues_show(hosted):
    result = run(hosted, "issues", "show", "app.git", UUID_A)
    assert result.exit_code == 0
    assert "title: Login times out" in result.output
    assert "# Login times out" in result.output

    missing = run(hosted, "issues", "show", "app.git", "nope")
    assert missing.exit_code != 0


def test_issues_fsck(hosted):
    result = run(hosted, "issues", "fsck", "app.git")
    assert result.exit_code == 0  # a missing id is a warning, not an error
    assert "missing id" in result.output
    assert "issues/notes.md" in result.output


def test_maintenance_writes_commit_graph(hosted, tmp_path):
    result = run(hosted, "maintenance")
    assert result.exit_code == 0
    assert "app.git: commit-graph written" in result.output
    assert (tmp_path / "repos" / "app.git" / "objects" / "info" / "commit-graph").exists()

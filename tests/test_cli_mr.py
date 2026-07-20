"""The merge-request commands, from both sides of the wire."""

import json

import pytest
from click.testing import CliRunner

from gitflower import gitread, mr
from gitflower.cli import main
from tests.conftest import git


@pytest.fixture
def hosted(tmp_path):
    """A hosted repository with one open request, and the clone that made it."""
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "file.txt").write_text("hello\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "first")
    git(work, "checkout", "-b", "feature/thing")
    (work / "feature.txt").write_text("feature\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "the work")
    git(work, "commit", "--allow-empty", "-m", "MR: add the feature\n\nwhy it matters")
    git(work, "push", "origin", "main", "feature/thing")
    config = tmp_path / "config.yaml"
    config.write_text(f"repos:\n  directory: {root}\n")
    return config, work


def run(config, *args):
    return CliRunner().invoke(main, ["--config", str(config), *args])


def test_list_from_the_host(hosted):
    config, _work = hosted
    result = run(config, "mr", "list", "--repo", "app.git")
    assert result.exit_code == 0, result.output
    assert "add the feature" in result.output
    assert "open" in result.output
    assert "feature/thing" in result.output


def test_list_from_a_clone(hosted, monkeypatch):
    """Without --repo the command reads the repository you are standing in."""
    config, work = hosted
    monkeypatch.chdir(work)
    result = run(config, "mr", "list")
    assert result.exit_code == 0, result.output
    assert "add the feature" in result.output


def test_list_says_so_when_there_are_none(hosted):
    config, _work = hosted
    result = run(config, "mr", "list", "--repo", "app.git", "--state", "merged")
    assert result.exit_code == 0
    assert "No merge requests found" in result.output


def test_show_by_id_and_by_branch(hosted):
    config, _work = hosted
    listed = json.loads(run(config, "mr", "list", "--repo", "app.git", "--format", "json").output)
    oid = listed["mrs"][0]["oid"]
    by_id = run(config, "mr", "show", oid, "--repo", "app.git")
    by_short = run(config, "mr", "show", oid[:8], "--repo", "app.git")
    by_branch = run(config, "mr", "show", "feature/thing", "--repo", "app.git")
    assert by_id.output == by_short.output == by_branch.output
    assert "add the feature" in by_id.output
    assert "why it matters" in by_id.output
    assert "the work" in by_id.output  # the line of work


def test_show_refuses_an_unknown_request(hosted):
    config, _work = hosted
    result = run(config, "mr", "show", "deadbeef", "--repo", "app.git")
    assert result.exit_code != 0
    assert "no merge request matching" in result.output


def test_status_exit_code_carries_the_state(hosted):
    config, _work = hosted
    result = run(config, "mr", "status", "feature/thing", "--repo", "app.git")
    assert result.exit_code == 2  # open
    assert "open" in result.output


def test_create_writes_an_empty_request(hosted, monkeypatch):
    config, work = hosted
    git(work, "checkout", "-b", "feature/another", "main")
    (work / "another.txt").write_text("more\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "more work")
    monkeypatch.chdir(work)
    result = run(config, "mr", "create", "-m", "another feature\nand why")
    assert result.exit_code == 0, result.output
    assert "Opened merge request" in result.output
    subject = git(work, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "MR: another feature"
    # empty by construction: the tree did not move
    assert git(work, "diff", "HEAD~1", "HEAD", "--stat").stdout.strip() == ""


def test_create_refuses_to_ask_twice(hosted, monkeypatch):
    config, work = hosted
    monkeypatch.chdir(work)
    git(work, "checkout", "feature/thing")
    result = run(config, "mr", "create", "-m", "asking again")
    assert result.exit_code != 0
    assert "already offers" in result.output


def test_create_refuses_a_detached_head(hosted, monkeypatch):
    config, work = hosted
    monkeypatch.chdir(work)
    git(work, "checkout", "--detach", "HEAD")
    result = run(config, "mr", "create", "-m", "from nowhere")
    assert result.exit_code != 0
    assert "detached" in result.output


def test_create_then_list_sees_it(hosted, monkeypatch):
    config, work = hosted
    git(work, "checkout", "-b", "feature/third", "main")
    (work / "third.txt").write_text("third\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "third work")
    monkeypatch.chdir(work)
    run(config, "mr", "create", "-m", "the third thing")
    listed = json.loads(run(config, "mr", "list", "--format", "json").output)
    assert "the third thing" in [m["title"] for m in listed["mrs"]]


def test_the_table_columns_are_the_shared_ones(hosted):
    from gitflower import models

    config, _work = hosted
    header = run(config, "mr", "list", "--repo", "app.git").output.splitlines()[0]
    assert header.split() == [w for c in models.MR_COLUMNS for w in c.header.split()]

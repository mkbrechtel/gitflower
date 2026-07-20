"""The CLI and the web serve one contract.

Every view a user can reach from more than one surface is assembled by the
same `models.X.of(...)` and shaped by the same `models.to_dict`, so the JSON
a command prints and the JSON an endpoint returns are equal by construction.
This suite is the standing check that they stay that way: a new dual-surface
view adds a row here, and a surface that starts assembling its own model
fails it.
"""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from gitflower import gitread
from gitflower.cli import main
from gitflower.config import GlobalConfig, ReposConfig
from gitflower.web.app import create_app
from tests.conftest import git
from tests.test_issues import UUID_A, UUID_B, issue_md


@pytest.fixture
def both(tmp_path):
    """One repos directory reachable through both surfaces."""
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    gitread.create_repository(root, "org/lib.git")
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
    return config, root


def cli_json(config, argv):
    result = CliRunner().invoke(main, ["--config", str(config), *argv, "--format", "json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def web_json(root, path, **params):
    app = create_app(GlobalConfig(repos=ReposConfig(directory=str(root))))
    response = TestClient(app).get(path, params={"format": "json", **params})
    assert response.status_code == 200, response.text
    return response.json()


# (web path, cli argv) — the argv is each command's real invocation, so a
# command taking a positional repo stays positional.
DUAL_SURFACE = [
    ("/repos/", ["list"]),
    ("/repos/app.git/issues/", ["issues", "list", "app.git"]),
]


@pytest.mark.parametrize("path,argv", DUAL_SURFACE)
def test_cli_and_web_serve_the_same_json(both, path, argv):
    config, root = both
    assert cli_json(config, argv) == web_json(root, path)


def test_issue_filter_agrees_across_surfaces(both):
    """Query parameters select the same documents on both sides."""
    config, root = both
    argv = ["issues", "list", "app.git", "--branch", "qa"]
    assert cli_json(config, argv) == web_json(root, "/repos/app.git/issues/", branch="qa")

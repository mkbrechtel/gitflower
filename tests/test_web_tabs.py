"""The repository sections: one tab bar on every repo-scoped page."""

import pytest
from fastapi.testclient import TestClient

from gitflower import gitread, models
from gitflower.config import GlobalConfig, ReposConfig
from gitflower.web.app import create_app
from tests.conftest import git


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "file.txt").write_text("hello\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "first")
    git(work, "checkout", "-b", "work/feature/thing")
    (work / "feature.txt").write_text("feature\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "the work")
    git(work, "commit", "--allow-empty", "-m", "MR: add the feature\n\nwhy it matters")
    git(work, "push", "origin", "main", "work/feature/thing")
    app = create_app(GlobalConfig(repos=ReposConfig(directory=str(root))))
    return TestClient(app)


def mr_oid(client):
    return client.get("/repos/app.git/mrs/", params={"format": "json"}).json()["mrs"][0]["oid"]


REPO_PAGES = [
    ("/repos/app.git", "commits"),
    ("/repos/app.git/branches/", "branches"),
    ("/repos/app.git/tree/", "code"),
    ("/repos/app.git/tree/main/file.txt", "code"),
    ("/repos/app.git/issues/", "issues"),
    ("/repos/app.git/mrs/", "mrs"),
]


def tab_bar(html: str) -> str:
    start = html.index('<nav class="tabs repo-tabs">')
    return html[start : html.index("</nav>", start)]


@pytest.mark.parametrize("path,active", REPO_PAGES)
def test_every_repo_page_carries_the_tabs(client, path, active):
    bar = tab_bar(client.get(path).text)
    for _key, label, _suffix in models.TABS:
        assert f">{label}" in bar
    # exactly one tab is current, and it is this page's
    assert bar.count('<a class="on"') == 1
    suffix = dict((k, s) for k, _l, s in models.TABS)[active]
    assert f'<a class="on" href="/repos/app.git{suffix}"' in bar


def test_the_commit_page_belongs_to_commits(client):
    sha = client.get("/repos/app.git", params={"format": "json"}).json()["commits"][0]["sha"]
    bar = tab_bar(client.get(f"/repos/app.git/commit/{sha}").text)
    assert '<a class="on" href="/repos/app.git"' in bar


def test_the_code_tab_needs_no_default_branch(client):
    """It points at /tree/, which resolves through HEAD — so no page has to
    carry the default branch just to draw a tab."""
    assert client.get("/repos/app.git/tree/").status_code == 200
    assert "file.txt" in client.get("/repos/app.git/tree/").text


def test_pages_outside_a_repository_have_no_tabs(client):
    """The repository list is not a repository — no section bar there."""
    assert '<nav class="tabs repo-tabs">' not in client.get("/repos/").text


def test_mr_list_shows_the_request(client):
    data = client.get("/repos/app.git/mrs/", params={"format": "json"}).json()
    assert [m["title"] for m in data["mrs"]] == ["add the feature"]
    assert data["mrs"][0]["state"] == "open"
    assert data["mrs"][0]["source"] == "work/feature/thing"
    assert data["mrs"][0]["target"] == "main"
    html = client.get("/repos/app.git/mrs/").text
    assert "add the feature" in html and "state-open" in html


def test_mr_list_filters_by_state(client):
    merged = client.get("/repos/app.git/mrs/", params={"format": "json", "state": "merged"}).json()
    assert merged["mrs"] == [] and merged["state"] == "merged"
    open_only = client.get("/repos/app.git/mrs/", params={"format": "json", "state": "open"}).json()
    assert len(open_only["mrs"]) == 1


def test_mr_detail_by_full_and_short_id(client):
    oid = mr_oid(client)
    full = client.get(f"/repos/app.git/mrs/{oid}", params={"format": "json"}).json()
    short = client.get(f"/repos/app.git/mrs/{oid[:8]}", params={"format": "json"}).json()
    assert full == short
    assert full["title"] == "add the feature"
    assert full["body"] == "why it matters"
    assert [c["subject"] for c in full["commits"]] == ["MR: add the feature", "the work"]


def test_mr_detail_renders_the_line_of_work(client):
    html = client.get(f"/repos/app.git/mrs/{mr_oid(client)}").text
    assert "The line of work" in html
    assert "the work" in html
    assert "Open — nothing has concluded it yet." in html


def test_a_bad_mr_id_is_a_404(client):
    assert client.get("/repos/app.git/mrs/nothexadecimal").status_code == 404
    assert client.get("/repos/app.git/mrs/abcdef1").status_code == 404


def test_mr_pages_serve_three_representations(client):
    oid = mr_oid(client)
    for path in ("/repos/app.git/mrs/", f"/repos/app.git/mrs/{oid}", "/repos/app.git/branches/"):
        assert client.get(path, params={"format": "json"}).headers["content-type"].startswith(
            "application/json"
        )
        fragment = client.get(path, headers={"GF-Fragment": "1"}).text
        assert fragment.startswith("<gf-view>")
        page = client.get(path).text
        assert page.startswith("<!doctype html>") and '<nav class="gf-nav">' in page

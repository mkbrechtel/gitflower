"""The issues endpoints: list, JMESPath filtering, detail, cross-links."""

import pytest
from fastapi.testclient import TestClient

from gitflower import gitread
from gitflower.config import GlobalConfig, ReposConfig
from gitflower.web.app import create_app
from tests.conftest import git
from tests.test_issues import UUID_A, UUID_B, issue_md

CHROME = '<nav class="gf-nav">'


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
    (work / "README.md").write_text("hello\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "file login issue")
    git(work, "checkout", "-b", "qa")
    (work / "issues" / "crash.md").write_text(issue_md(UUID_B, "Crash on save", status="open"))
    (work / "issues" / "login.md").write_text(
        issue_md(UUID_A, "Login times out", "Confirmed.\n", status="confirmed")
    )
    git(work, "add", ".")
    git(work, "commit", "-m", "qa: crash filed, login confirmed")
    git(work, "checkout", "main")
    git(work, "push", "origin", "main", "qa")
    return root


@pytest.fixture
def client(hosted):
    cfg = GlobalConfig(repos=ReposConfig(directory=str(hosted)))
    return TestClient(create_app(cfg))


def test_three_representations(client):
    url = "/repos/app.git/issues/"
    page = client.get(url)
    assert page.status_code == 200
    assert CHROME in page.text

    fragment = client.get(url, headers={"GF-Fragment": "1"})
    assert fragment.text.startswith("<gf-view>")

    data = client.get(url, headers={"Accept": "application/json"}).json()
    assert data["default_branch"] == "main"
    assert {i["id"] for i in data["issues"]} == {UUID_A, UUID_B}


def test_list_classification(client):
    data = client.get("/repos/app.git/issues/?format=json").json()
    by_id = {i["id"]: i for i in data["issues"]}
    assert by_id[UUID_A]["branches"]["qa"]["state"] == "modified"
    assert by_id[UUID_B]["branches"]["qa"]["state"] == "added"
    assert "main" not in by_id[UUID_B]["branches"]


def test_list_jmespath_filter(client):
    url = "/repos/app.git/issues/?format=json&q=" + "[?frontmatter.status=='open']"
    data = client.get(url).json()
    assert {i["id"] for i in data["issues"]} == {UUID_A, UUID_B}
    assert data["query"] == "[?frontmatter.status=='open']"

    none = client.get(
        "/repos/app.git/issues/?format=json&q=[?frontmatter.status=='wontfix']"
    ).json()
    assert none["issues"] == []


def test_list_branch_scope(client):
    data = client.get("/repos/app.git/issues/?format=json&branch=main").json()
    assert {i["id"] for i in data["issues"]} == {UUID_A}


def test_list_bad_query_is_400(client):
    assert client.get("/repos/app.git/issues/?q=[?broken").status_code == 400
    assert client.get("/repos/app.git/issues/?q=[].title").status_code == 400


def test_detail(client):
    page = client.get(f"/repos/app.git/issues/{UUID_A}")
    assert page.status_code == 200
    assert "Login times out" in page.text

    data = client.get(f"/repos/app.git/issues/{UUID_A}?format=json").json()
    assert data["shown_branch"] == "main"
    assert "# Login times out" in data["content"]
    assert {t["subject"] for t in data["transitions"]} == {
        "file login issue",
        "qa: crash filed, login confirmed",
    }


def test_detail_pinned(client):
    data = client.get(f"/repos/app.git/issues/{UUID_A}?format=json&at=qa").json()
    assert "Confirmed." in data["content"]
    assert data["at"] == "qa"


def test_detail_unknown_is_404(client):
    assert client.get("/repos/app.git/issues/no-such-id").status_code == 404
    assert client.get(f"/repos/app.git/issues/{UUID_A}?at=nonsense").status_code == 404


def test_blob_badge(client):
    data = client.get("/repos/app.git/tree/main/issues/login.md?format=json").json()
    assert data["issue"]["id"] == UUID_A

    page = client.get("/repos/app.git/tree/main/issues/login.md")
    assert f"/repos/app.git/issues/{UUID_A}" in page.text

    readme = client.get("/repos/app.git/tree/main/README.md?format=json").json()
    assert readme["issue"] is None


def test_commit_badge(client, hosted):
    import pygit2

    repo = pygit2.Repository(str(hosted / "app.git"))
    sha = str(repo.branches.local["qa"].peel(pygit2.Commit).id)
    data = client.get(f"/repos/app.git/commit/{sha}?format=json").json()
    assert {i["id"] for i in data["issues"]} == {UUID_A, UUID_B}
    page = client.get(f"/repos/app.git/commit/{sha}")
    assert "issues touched:" in page.text

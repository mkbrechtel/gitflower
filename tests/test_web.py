"""Route contract: every endpoint serves JSON, full page, and fragment."""

import pytest
from fastapi.testclient import TestClient

from gitflower import gitread
from gitflower.config import GlobalConfig, ReposConfig
from gitflower.web.app import create_app
from tests.conftest import git

CHROME = '<nav class="gf-nav">'


@pytest.fixture
def hosted(tmp_path):
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    gitread.create_repository(root, "org/lib.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    for n in range(6):
        (work / f"file-{n}.txt").write_text(f"content {n}\n")
        (work / "sub").mkdir(exist_ok=True)
        (work / "sub" / "nested.txt").write_text("nested\n")
        git(work, "add", ".")
        git(work, "commit", "-m", f"commit {n}")
    (work / "binary.bin").write_bytes(bytes(range(256)))
    git(work, "add", ".")
    git(work, "commit", "-m", "add binary")
    git(work, "push", "origin", "main")
    return root


@pytest.fixture
def client(hosted):
    cfg = GlobalConfig(repos=ReposConfig(directory=str(hosted)))
    return TestClient(create_app(cfg))


# ---------------------------------------------------------- negotiation


@pytest.mark.parametrize(
    "url",
    ["/", "/repos/", "/repos/org", "/repos/app.git", "/repos/app.git/tree/main/", "/docs/"],
)
def test_three_representations(client, url):
    page = client.get(url)
    assert page.status_code == 200
    assert CHROME in page.text
    assert "<gf-view>" in page.text

    fragment = client.get(url, headers={"GF-Fragment": "1"})
    assert fragment.status_code == 200
    assert CHROME not in fragment.text  # no chrome on fragments
    assert fragment.text.startswith("<gf-view>")
    assert 'shadowrootmode="open"' in fragment.text

    data = client.get(url, headers={"Accept": "application/json"})
    assert data.status_code == 200
    assert data.headers["content-type"].startswith("application/json")
    data.json()

    # explicit overrides beat headers
    assert client.get(url + "?format=json").json() == data.json()
    assert CHROME not in client.get(url + "?format=fragment").text


def test_index_and_list_show_repos(client):
    for url in ("/", "/repos/"):
        body = client.get(url).text
        assert "app.git" in body and "org/lib.git" in body
    data = client.get("/repos/", headers={"Accept": "application/json"}).json()
    assert {r["path"] for r in data["repos"]} == {"app.git", "org/lib.git"}


def test_org_folder_filters(client):
    data = client.get("/repos/org", headers={"Accept": "application/json"}).json()
    assert [r["path"] for r in data["repos"]] == ["org/lib.git"]
    assert client.get("/repos/nope").status_code == 404


def test_repo_detail_carries_graph_and_branches(client):
    page = client.get("/repos/app.git")
    assert '<svg class="graph-svg"' in page.text
    assert "git clone" in page.text
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    assert [b["name"] for b in data["branches"]] == ["main"]
    assert data["graph"]["rows"] and data["graph"]["width"] > 0
    assert data["clone_url"].endswith("/repos/app.git")


def test_graph_folds_and_full_unfolds(client):
    folded = client.get("/repos/app.git").text
    assert "⋯" in folded  # the linear stretch became a gap row
    assert "commit 2" not in folded
    full = client.get("/repos/app.git?full=1").text
    assert "⋯" not in full
    assert "commit 2" in full


def test_tree_browsing(client):
    listing = client.get("/repos/app.git/tree/main/").text
    assert "file-0.txt" in listing and "sub/" in listing
    nested = client.get("/repos/app.git/tree/main/sub/").text
    assert "nested.txt" in nested
    assert client.get("/repos/app.git/tree/main/nope/").status_code == 404


def test_blob_views(client):
    page = client.get("/repos/app.git/tree/main/file-0.txt")
    assert "content 0" in page.text
    raw = client.get("/repos/app.git/tree/main/file-0.txt?format=raw")
    assert raw.text == "content 0\n"
    assert raw.headers["content-type"].startswith("text/plain")

    binary = client.get("/repos/app.git/tree/main/binary.bin")
    assert "Binary file not shown" in binary.text
    raw_bin = client.get("/repos/app.git/tree/main/binary.bin?format=raw")
    assert raw_bin.content == bytes(range(256))
    assert raw_bin.headers["content-type"] == "application/octet-stream"


def test_commit_view(client):
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    sha = data["branches"][0]["sha"]
    page = client.get(f"/repos/app.git/commit/{sha}")
    assert "add binary" in page.text and "Changes" in page.text
    assert '<details class="file"' in page.text  # per-file diff sections
    assert "file changed" in page.text or "files changed" in page.text  # diffstat
    assert "Binary file not shown" in page.text  # binary.bin has no patch body
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    assert detail["sha"] == sha and detail["patch"]
    assert {f["path"] for f in detail["files"]} == {"binary.bin"}
    assert detail["files"][0]["binary"] is True
    assert detail["stats"]["files_changed"] == 1
    assert client.get("/repos/app.git/commit/0000000").status_code == 404


def test_404_serves_all_representations(client):
    missing = client.get("/repos/ghost.git")
    assert missing.status_code == 404
    assert CHROME in missing.text
    fragment = client.get("/repos/ghost.git", headers={"GF-Fragment": "1"})
    assert fragment.status_code == 404 and CHROME not in fragment.text
    data = client.get("/repos/ghost.git", headers={"Accept": "application/json"})
    assert data.status_code == 404 and data.json()["status"] == 404


@pytest.mark.parametrize(
    "url",
    [
        "/repos/../etc/passwd.git",
        "/repos/..%2f..%2fetc%2fpasswd.git",
        "/repos/UPPER.git",
        "/repos/.hidden.git",
    ],
)
def test_traversal_is_a_404(client, url):
    assert client.get(url).status_code == 404


def test_static_and_api_schema(client):
    css = client.get("/static/gitflower.css")
    assert css.status_code == 200 and "--accent" in css.text
    js = client.get("/static/components.js")
    assert js.status_code == 200 and "setHTMLUnsafe" in js.text
    schema = client.get("/api/openapi.json").json()
    assert "/repos/" in schema["paths"]
    docs = client.get("/api")
    assert docs.status_code == 200
    assert CHROME in docs.text  # swagger page wears the site chrome
    assert 'id="swagger-ui"' in docs.text and "SwaggerUIBundle" in docs.text


def test_posts_are_rejected(client):
    """The browse surface is read-only; only upload-pack accepts POST."""
    for url in ("/", "/docs/"):
        assert client.post(url).status_code == 405
    # a POST into /repos/ that is not git-upload-pack is a 404
    assert client.post("/repos/app.git").status_code == 404

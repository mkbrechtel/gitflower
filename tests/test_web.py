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
    (work / "long.txt").write_text("".join(f"long line {i}\n" for i in range(1, 41)))
    git(work, "add", ".")
    git(work, "commit", "-m", "long file")
    (work / "binary.bin").write_bytes(bytes(range(256)))
    git(work, "add", ".")
    git(work, "commit", "-m", "add binary")
    git(work, "checkout", "-b", "work/feature/thing")
    (work / "feature.txt").write_text("feature work\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "feature commit")
    # a merge commit on its own branch, so main's tip stays a plain commit;
    # the side branch also changes one line deep in long.txt so the merge's
    # side-by-side view has unchanged runs to fold
    git(work, "checkout", "-b", "side", "main~1")
    (work / "side.txt").write_text("side\n")
    lines = (work / "long.txt").read_text().splitlines(keepends=True)
    lines[19] = "long line 20 changed by side\n"
    (work / "long.txt").write_text("".join(lines))
    git(work, "add", ".")
    git(work, "commit", "-m", "side work")
    git(work, "checkout", "-b", "merged", "main")
    git(work, "merge", "--no-ff", "side", "-m", "merge side")
    git(work, "checkout", "-b", "archive/retired", "main")
    (work / "retired.txt").write_text("retired\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "retired work")
    git(work, "checkout", "main")
    git(work, "push", "origin", "main", "work/feature/thing", "merged", "archive/retired")
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
    # commit ids link to the commit view — in the graph and in the branches table
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    tip = data["branches"][0]
    assert f'<a class="graph-sha" href="/repos/app.git/commit/' in page.text
    # the branch table is its own section now; the graph page keeps the graph
    branches = client.get("/repos/app.git/branches/").text
    assert f'<a href="/repos/app.git/commit/{tip["sha"]}"><code>{tip["short"]}</code></a>' in branches
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    # main pinned first, archive/retired hidden — both by default config
    assert [b["name"] for b in data["branches"]] == ["main", "merged", "work/feature/thing"]
    assert data["graph"]["rows"] and data["graph"]["width"] > 0
    assert data["clone_url"].endswith("/repos/app.git")


def test_hidden_branches_expand_and_grey_out(client):
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    assert data["hidden_count"] == 1 and data["show_hidden"] is False
    subjects = [r["commit"]["subject"] for r in data["graph"]["rows"] if r["kind"] == "commit"]
    assert "retired work" not in subjects
    page = client.get("/repos/app.git")
    assert "1 hidden branch" in page.text and "?hidden=1" in page.text

    data = client.get("/repos/app.git?hidden=1", headers={"Accept": "application/json"}).json()
    assert data["show_hidden"] is True
    assert [b["name"] for b in data["branches"] if b["hidden"]] == ["archive/retired"]
    rows = {r["commit"]["subject"]: r for r in data["graph"]["rows"] if r["kind"] == "commit"}
    # only the archived branch's own commit greys out — its base is main's
    assert rows["retired work"]["dimmed"] is True
    assert rows["feature commit"]["dimmed"] is False
    assert rows["add binary"]["dimmed"] is False
    # pinned main renders filled, other branches hollow
    assert rows["add binary"]["pinned"] is True
    assert rows["feature commit"]["pinned"] is False
    page = client.get("/repos/app.git?hidden=1")
    assert "graph-dimmed" in page.text
    assert "(hidden)" in client.get("/repos/app.git/branches/?hidden=1").text


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


def test_slashed_branch_names_resolve(client):
    """Branch names contain slashes; the longest resolving prefix is the ref."""
    data = client.get(
        "/repos/app.git/tree/work/feature/thing/", headers={"Accept": "application/json"}
    ).json()
    assert data["ref"] == "work/feature/thing" and data["subpath"] == ""
    assert "feature.txt" in {e["name"] for e in data["entries"]}
    # a file below the slashed ref
    blob = client.get(
        "/repos/app.git/tree/work/feature/thing/feature.txt",
        headers={"Accept": "application/json"},
    ).json()
    assert blob["ref"] == "work/feature/thing" and blob["subpath"] == "feature.txt"
    raw = client.get("/repos/app.git/tree/work/feature/thing/feature.txt?format=raw")
    assert raw.text == "feature work\n"
    # an unresolvable prefix is a 404, not a directory guess
    missing = client.get("/repos/app.git/tree/work/")
    assert missing.status_code == 404 and "no such ref" in missing.text


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
    sha = next(b["sha"] for b in data["branches"] if b["name"] == "main")
    page = client.get(f"/repos/app.git/commit/{sha}")
    assert "add binary" in page.text and "Changes" in page.text
    assert '<details class="file"' in page.text  # per-file diff sections
    assert "1 file," in page.text  # the single column's diffstat
    assert "Binary file not shown" in page.text  # binary.bin has no rows
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    assert detail["sha"] == sha
    assert {f["path"] for f in detail["files"]} == {"binary.bin"}
    assert detail["files"][0]["binary"] is True
    (column,) = detail["columns"]
    assert column["index"] == 1 and column["stats"]["files_changed"] == 1
    assert client.get("/repos/app.git/commit/0000000").status_code == 404


def test_single_parent_commit_uses_the_side_by_side_table(client):
    """The only diff view: a one-parent commit gets one column plus the result."""
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    sha = next(b["sha"] for b in data["branches"] if b["name"] == "work/feature/thing")
    page = client.get(f"/repos/app.git/commit/{sha}")
    assert '<table class="diff"' in page.text and "result</th>" in page.text
    assert "<pre class=\"patch\"" not in page.text  # the unified view is gone
    assert 'class="tabs"' not in page.text  # one parent, no choice to offer
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    assert detail["diff_parent"] is None and len(detail["columns"]) == 1
    (row,) = detail["files"][0]["rows"]
    assert row["result_text"] == "feature work" and not row["merge_authored"]


def test_root_commit_renders_against_the_empty_tree(client):
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    sha = next(b["sha"] for b in data["branches"] if b["name"] == "main")
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    while detail["parents"]:  # walk first parents down to the root commit
        detail = client.get(
            f"/repos/app.git/commit/{detail['parents'][0]}",
            headers={"Accept": "application/json"},
        ).json()
    (column,) = detail["columns"]
    assert column["index"] is None and column["sha"] == ""
    page = client.get(f"/repos/app.git/commit/{detail['sha']}")
    assert "the empty tree" in page.text and '<table class="diff"' in page.text
    assert "none (initial commit)" in page.text
    assert 'class="tabs"' not in page.text


def _merge_sha(client) -> str:
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    return next(b["sha"] for b in data["branches"] if b["name"] == "merged")


def test_merge_commit_defaults_to_side_by_side(client):
    sha = _merge_sha(client)
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    assert len(detail["parents"]) == 2 and len(detail["columns"]) == 2
    files = {f["path"]: f for f in detail["files"]}
    assert set(files) == {"side.txt", "long.txt", "binary.bin"}
    # side.txt came from the side branch: added vs parent 1, unchanged vs parent 2
    assert files["side.txt"]["statuses"] == ["A", "="]
    (row,) = files["side.txt"]["rows"]
    assert row["kind"] == "line" and row["result_text"] == "side"
    assert [c["status"] for c in row["cells"]] == ["absent", "same"]
    assert not row["merge_authored"]
    # long.txt: one line changed on the side branch, the rest folds
    assert files["long.txt"]["statuses"] == ["M", "="]
    changed = next(r for r in files["long.txt"]["rows"] if r["result_no"] == 20)
    assert changed["cells"][0]["text"] == "long line 20"
    assert [c["status"] for c in changed["cells"]] == ["changed", "same"]
    # binary.bin is on main's side only
    assert files["binary.bin"]["statuses"] == ["=", "A"] and files["binary.bin"]["binary"]

    page = client.get(f"/repos/app.git/commit/{sha}")
    assert '<table class="diff"' in page.text and "result</th>" in page.text
    assert 'class="tabs"' in page.text and f"?parent=2" in page.text
    # taken-from-one-side rows still read as classic diff additions: green +
    assert '<td class="res add"><span class="ln">1</span><span class="sign">+</span>side</td>' in page.text
    fragment = client.get(f"/repos/app.git/commit/{sha}", headers={"GF-Fragment": "1"})
    assert fragment.status_code == 200 and CHROME not in fragment.text


def test_parent_tabs_narrow_the_side_by_side_view(client):
    """?parent=N is a column filter now, not a different view."""
    sha = _merge_sha(client)
    vs1 = client.get(
        f"/repos/app.git/commit/{sha}?parent=1", headers={"Accept": "application/json"}
    ).json()
    assert vs1["diff_parent"] == 1 and [c["index"] for c in vs1["columns"]] == [1]
    assert {f["path"] for f in vs1["files"]} == {"side.txt", "long.txt"}
    vs2 = client.get(
        f"/repos/app.git/commit/{sha}?parent=2", headers={"Accept": "application/json"}
    ).json()
    assert vs2["diff_parent"] == 2 and [c["index"] for c in vs2["columns"]] == [2]
    assert {f["path"] for f in vs2["files"]} == {"binary.bin"}
    page = client.get(f"/repos/app.git/commit/{sha}?parent=1")
    assert '<table class="diff"' in page.text and 'class="tabs"' in page.text
    # every table is one parent column plus the result
    assert page.text.count("<th>") == 2 * page.text.count('<table class="diff"')
    assert client.get(f"/repos/app.git/commit/{sha}?parent=3").status_code == 404
    assert client.get(f"/repos/app.git/commit/{sha}?parent=0").status_code == 404


def test_fold_and_unfold_links_keep_the_parent_selection(client):
    sha = _merge_sha(client)
    folded = client.get(f"/repos/app.git/commit/{sha}?parent=1")
    assert f"/commit/{sha}?parent=1&full=1" in folded.text  # unfold keeps the column
    unfolded = client.get(f"/repos/app.git/commit/{sha}?parent=1&full=1")
    assert f'href="/repos/app.git/commit/{sha}?parent=1">fold unchanged lines' in unfolded.text


def test_merge_full_unfolds(client):
    sha = _merge_sha(client)
    for suffix, expect_fold in (("", True), ("?full=1", False)):
        detail = client.get(
            f"/repos/app.git/commit/{sha}{suffix}", headers={"Accept": "application/json"}
        ).json()
        folds = [r for f in detail["files"] for r in f["rows"] if r["kind"] == "fold"]
        assert bool(folds) == expect_fold  # long.txt's unchanged runs fold by default
        assert detail["full"] == bool(suffix)
        if folds:
            assert all(f'⋯ {r["count"]} unchanged lines' for r in folds)


def test_non_merge_commits_have_no_tabs(client):
    data = client.get("/repos/app.git", headers={"Accept": "application/json"}).json()
    sha = next(b["sha"] for b in data["branches"] if b["name"] == "main")
    page = client.get(f"/repos/app.git/commit/{sha}")
    assert 'class="tabs"' not in page.text
    detail = client.get(
        f"/repos/app.git/commit/{sha}", headers={"Accept": "application/json"}
    ).json()
    assert detail["diff_parent"] is None  # nothing to narrow: one parent already


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
    for url in ("/", "/docs/", "/repos/app.git"):
        assert client.post(url).status_code == 405

import pytest

from gitflower import gitread
from tests.conftest import git


@pytest.fixture
def repos_dir(tmp_path):
    """A hosted repos tree: two repos (one nested in an org), plus noise."""
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    gitread.create_repository(root, "org/team/lib.git")
    (root / "INVALID_NAME").mkdir()
    (root / "too" / "deep" / "nested" / "lost.git").mkdir(parents=True)
    return root


@pytest.fixture
def seeded(repos_dir, tmp_path):
    """app.git populated with a branchy history via a working clone."""
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(repos_dir / "app.git"), str(work))
    git(work, "checkout", "-b", "main")

    def commit(name):
        (work / name).write_text(name)
        git(work, "add", ".")
        git(work, "commit", "-m", name)

    for n in range(6):
        commit(f"linear-{n}.txt")
    git(work, "checkout", "-b", "side")
    commit("side.txt")
    git(work, "checkout", "main")
    commit("trunk.txt")
    git(work, "merge", "--no-ff", "side", "-m", "merge side")
    git(work, "checkout", "-b", "open")
    commit("open.txt")
    git(work, "push", "origin", "main", "side", "open")
    return repos_dir


def test_create_repository_is_bare(repos_dir):
    import pygit2

    repo = pygit2.Repository(str(repos_dir / "app.git"))
    assert repo.is_bare
    assert gitread.head_branch(repo) == "main"


def test_create_duplicate_rejected(repos_dir):
    with pytest.raises(gitread.GitReadError, match="repository app.git already exists"):
        gitread.create_repository(repos_dir, "app.git")


def test_scan_finds_repos_and_warns(repos_dir):
    result = gitread.scan_repos(repos_dir, depth=3)
    assert [r.path for r in result.repos] == ["app.git", "org/team/lib.git"]
    assert "Invalid directory name: INVALID_NAME" in result.warnings


def test_scan_depth_honored(repos_dir):
    assert [r.path for r in gitread.scan_repos(repos_dir, depth=1).repos] == ["app.git"]
    # depth 4 reaches the deep (invalid) one — which reports as invalid
    deep = gitread.scan_repos(repos_dir, depth=4)
    lost = [r for r in deep.repos if "lost" in r.path]
    assert lost and not lost[0].is_valid


def test_scan_missing_dir_is_empty(tmp_path):
    result = gitread.scan_repos(tmp_path / "nope")
    assert result.repos == [] and result.warnings == []


def test_branches_and_commits_feed(seeded):
    repo = gitread.open_repo(seeded, "app.git")
    names = {b["name"] for b in gitread.branches(repo)}
    assert names == {"main", "side", "open"}

    commits = gitread.commits(repo)
    # 6 linear + side + trunk + merge + open
    assert gitread.commit_count(repo) == len(commits) == 10
    # children before parents — what the graph layout requires
    seen = set()
    for commit in commits:
        seen.add(commit["sha"])
        for parent in commit["parents"]:
            assert parent not in seen
    merge = [c for c in commits if len(c["parents"]) == 2]
    assert len(merge) == 1 and merge[0]["subject"] == "merge side"


def test_tree_and_blob(seeded):
    repo = gitread.open_repo(seeded, "app.git")
    entries = gitread.tree_entries(repo, "main")
    assert {e["name"] for e in entries} >= {"linear-0.txt", "trunk.txt", "side.txt"}
    found = gitread.blob(repo, "main", "trunk.txt")
    assert found["data"] == b"trunk.txt" and not found["is_binary"]
    with pytest.raises(gitread.GitReadError, match="no such path"):
        gitread.blob(repo, "main", "nope.txt")
    with pytest.raises(gitread.GitReadError, match="no such ref"):
        gitread.tree_entries(repo, "does-not-exist")


def test_commit_detail_patch(seeded):
    repo = gitread.open_repo(seeded, "app.git")
    tip = gitread.branches(repo)
    sha = [b for b in tip if b["name"] == "side"][0]["sha"]
    detail = gitread.commit_detail(repo, sha)
    assert "+side.txt" in detail["patch"]
    root = gitread.commits(repo)[-1]
    root_detail = gitread.commit_detail(repo, root["sha"])
    assert root_detail["parents"] == []
    assert "+linear-0.txt" in root_detail["patch"]  # diff against the empty tree


def test_open_repo_validates_path(repos_dir):
    with pytest.raises(Exception):
        gitread.open_repo(repos_dir, "../escape.git")

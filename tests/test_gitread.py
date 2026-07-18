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


@pytest.fixture
def folders(seeded, tmp_path):
    """seeded plus folder branches, one with its own commit (archive)."""
    work = tmp_path / "seed"
    for name in ("work/fix/hook-install", "work/feature/web-ui", "releases/v1"):
        git(work, "branch", name)
        git(work, "push", "origin", name)
    git(work, "checkout", "-b", "archive/old-thing")
    (work / "old.txt").write_text("old")
    git(work, "add", ".")
    git(work, "commit", "-m", "archived work")
    git(work, "push", "origin", "archive/old-thing")
    return seeded


def test_branches_grouped_by_folder(folders):
    repo = gitread.open_repo(folders, "app.git")
    assert [b["name"] for b in gitread.branches(repo)] == [
        "main",
        "open",
        "side",
        "archive/old-thing",
        "releases/v1",
        "work/feature/web-ui",
        "work/fix/hook-install",
    ]


def test_branches_pinned_and_hidden(folders):
    repo = gitread.open_repo(folders, "app.git")
    listed = gitread.branches(repo, pinned=["main", "releases"], hidden=["archive", "side"])
    assert [b["name"] for b in listed] == [
        "main",
        "releases/v1",
        "open",
        "work/feature/web-ui",
        "work/fix/hook-install",
    ]


def test_hidden_branches_leave_the_graph(folders):
    repo = gitread.open_repo(folders, "app.git")
    subjects = {c["subject"] for c in gitread.commits(repo)}
    assert "archived work" in subjects
    shown = gitread.commits(repo, hidden=["archive"])
    assert "archived work" not in {c["subject"] for c in shown}
    born = gitread.born_on(repo, shown, "main", hidden=["archive"])
    assert "archive/old-thing" not in born.values()


def test_commit_detail_patch(seeded):
    repo = gitread.open_repo(seeded, "app.git")
    tip = gitread.branches(repo)
    sha = [b for b in tip if b["name"] == "side"][0]["sha"]
    detail = gitread.commit_detail(repo, sha)
    assert "+side.txt" in detail["patch"]
    (added,) = detail["files"]
    assert added["path"] == "side.txt" and added["status"] == "A"
    assert added["additions"] == 1 and added["deletions"] == 0
    assert not added["binary"] and "+side.txt" in added["patch"]
    assert detail["stats"] == {"files_changed": 1, "additions": 1, "deletions": 0}
    assert detail["committer"] == detail["author"]
    root = gitread.commits(repo)[-1]
    root_detail = gitread.commit_detail(repo, root["sha"])
    assert root_detail["parents"] == []
    assert "+linear-0.txt" in root_detail["patch"]  # diff against the empty tree
    assert [f["status"] for f in root_detail["files"]] == ["A"]


def test_open_repo_validates_path(repos_dir):
    with pytest.raises(Exception):
        gitread.open_repo(repos_dir, "../escape.git")


# ---------------------------------------------------------- merge detail

BASE_PY = "import os\n\n# TODO drop this\ndef fetch(url):\n    r = get(url, timeout=1)\n    return r\n"
P1_PY = "import os\n\n# TODO drop this\ndef fetch(url):\n    r = get(url, timeout=10)\n    return r\n\ndef old_helper():\n    return legacy()\n"
P2_PY = "import os\nimport logging\n\n# TODO drop this\ndef fetch(url):\n    logging.debug(url)\n    r = get(url, timeout=60)\n    return r\n"
RESOLVED_PY = "import os\nimport logging\n\ndef fetch(url):\n    logging.debug(url)\n    retry = True\n    r = get(url, timeout=30)\n    return r\n"


@pytest.fixture
def merged(repos_dir, tmp_path):
    """app.git with a hand-resolved merge exercising the full taxonomy,
    plus a second merge whose diff against parent 2 is empty."""
    work = tmp_path / "mseed"
    git(tmp_path, "clone", str(repos_dir / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "app.py").write_text(BASE_PY)
    (work / "common.txt").write_text("shared\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "base")
    git(work, "checkout", "-b", "feature")
    (work / "app.py").write_text(P2_PY)
    (work / "feature.txt").write_text("feature\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "logging work")
    git(work, "checkout", "main")
    (work / "app.py").write_text(P1_PY)
    git(work, "add", ".")
    git(work, "commit", "-m", "timeout tweak")
    # a genuine conflict, resolved by hand to content matching NEITHER side;
    # the resolution also drops common.txt, which both parents carried
    assert git(work, "merge", "feature", check=False).returncode != 0
    (work / "app.py").write_text(RESOLVED_PY)
    git(work, "add", "app.py")
    git(work, "rm", "-q", "common.txt")
    git(work, "commit", "-m", "merge feature")
    # …and a merge that takes one side wholesale (empty diff vs parent 2)
    git(work, "checkout", "-b", "topic")
    (work / "topic.txt").write_text("topic\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "topic work")
    git(work, "checkout", "main")
    git(work, "merge", "--no-ff", "topic", "-m", "take topic")
    git(work, "push", "origin", "main", "feature")
    return repos_dir


def _find(repo, subject):
    return next(c for c in gitread.commits(repo) if c["subject"] == subject)


def test_merge_detail_full_taxonomy(merged):
    repo = gitread.open_repo(merged, "app.git")
    detail = gitread.merge_detail(repo, _find(repo, "merge feature")["sha"])
    assert len(detail["parent_commits"]) == 2
    assert {p["subject"] for p in detail["parent_commits"]} == {"timeout tweak", "logging work"}
    files = {f["path"]: f for f in detail["files"]}
    assert set(files) == {"app.py", "common.txt", "feature.txt"}

    # taken wholesale from one side: A vs the parent lacking it, = vs its source
    assert files["feature.txt"]["statuses"] == ["A", "="]
    assert not any(r["merge_authored"] for r in files["feature.txt"]["rows"])

    # deleted by the merge although both parents had it
    assert files["common.txt"]["statuses"] == ["D", "D"]
    (gone,) = files["common.txt"]["rows"]
    assert gone["kind"] == "only" and gone["merge_authored"]
    assert [c["status"] for c in gone["cells"]] == ["removed", "removed"]

    app = files["app.py"]
    assert app["statuses"] == ["M", "M"]
    rows = app["rows"]

    def line(text):
        return next(r for r in rows if r["result_text"] == text)

    # taken from parent 2's side: matches a parent, not merge-authored
    taken = line("import logging")
    assert [c["status"] for c in taken["cells"]] == ["absent", "same"]
    assert not taken["merge_authored"]
    # inserted by the merge: in neither parent
    added = line("    retry = True")
    assert [c["status"] for c in added["cells"]] == ["absent", "absent"]
    assert added["merge_authored"]
    # hand-resolved: both parents' own versions on the row
    resolved = line("    r = get(url, timeout=30)")
    assert [c["text"] for c in resolved["cells"]] == [
        "    r = get(url, timeout=10)",
        "    r = get(url, timeout=60)",
    ]
    assert resolved["merge_authored"]
    # removed by the merge: ONE row although both parents carried the line
    todos = [r for r in rows if r["kind"] == "only" and "TODO" in (r["cells"][0]["text"] or "")]
    assert len(todos) == 1 and todos[0]["merge_authored"]
    # removed from one side only: taking the other side is not merge-authored
    helper = next(r for r in rows if "old_helper" in (r["cells"][0]["text"] or ""))
    assert [c["status"] for c in helper["cells"]] == ["removed", "absent"]
    assert not helper["merge_authored"]
    # per-parent stats both non-empty for this hand-resolved merge
    assert all(s["files_changed"] for s in detail["parent_stats"])


def test_merge_taking_one_side_reports_empty_parent_diff(merged):
    repo = gitread.open_repo(merged, "app.git")
    detail = gitread.merge_detail(repo, _find(repo, "take topic")["sha"])
    assert detail["parent_stats"][1] == {"files_changed": 0, "additions": 0, "deletions": 0}
    (topic,) = detail["files"]
    assert topic["path"] == "topic.txt" and topic["statuses"] == ["A", "="]


def test_merge_detail_rejects_non_merges(merged):
    repo = gitread.open_repo(merged, "app.git")
    with pytest.raises(gitread.GitReadError, match="not a merge commit"):
        gitread.merge_detail(repo, _find(repo, "base")["sha"])


def test_commit_detail_against_chosen_parent(merged):
    repo = gitread.open_repo(merged, "app.git")
    sha = _find(repo, "merge feature")["sha"]
    vs1 = gitread.commit_detail(repo, sha, parent=1)
    assert vs1["diff_parent"] == 1
    assert {f["path"] for f in vs1["files"]} == {"app.py", "common.txt", "feature.txt"}
    vs2 = gitread.commit_detail(repo, sha, parent=2)
    assert vs2["diff_parent"] == 2
    assert {f["path"] for f in vs2["files"]} == {"app.py", "common.txt"}
    assert gitread.commit_detail(repo, sha)["diff_parent"] == 1  # default: parent 1
    with pytest.raises(gitread.GitReadError, match="no such parent: 3"):
        gitread.commit_detail(repo, sha, parent=3)
    with pytest.raises(gitread.GitReadError, match="no such parent: 2"):
        gitread.commit_detail(repo, _find(repo, "base")["sha"], parent=2)


def test_octopus_merge_gets_a_column_per_parent(merged, tmp_path):
    work = tmp_path / "octo"
    git(tmp_path, "clone", str(merged / "org/team/lib.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "base.txt").write_text("base\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "base")
    for branch in ("b1", "b2"):
        git(work, "checkout", "-b", branch, "main")
        (work / f"{branch}.txt").write_text(f"{branch}\n")
        git(work, "add", ".")
        git(work, "commit", "-m", f"{branch} work")
    git(work, "checkout", "main")
    git(work, "merge", "--no-ff", "b1", "b2", "-m", "octopus")
    git(work, "push", "origin", "main")

    repo = gitread.open_repo(merged, "org/team/lib.git")
    detail = gitread.merge_detail(repo, _find(repo, "octopus")["sha"])
    assert len(detail["parent_commits"]) == 3
    files = {f["path"]: f for f in detail["files"]}
    assert files["b1.txt"]["statuses"] == ["A", "=", "A"]
    assert files["b2.txt"]["statuses"] == ["A", "A", "="]
    (row,) = files["b1.txt"]["rows"]
    assert [c["status"] for c in row["cells"]] == ["absent", "same", "absent"]
    assert not row["merge_authored"]  # b1's side was taken; nothing merge-authored


# ------------------------------------------------------------- born_on


@pytest.fixture
def attributed(tmp_path):
    """A non-bare repo (reflogs on) with a merged feature and a stack."""
    import pygit2

    work = tmp_path / "attributed"
    work.mkdir()
    git(work, "init", "-b", "main")

    def commit(name):
        (work / name).write_text(name)
        git(work, "add", ".")
        git(work, "commit", "-m", name)
        return git(work, "rev-parse", "HEAD").stdout.strip()

    shas = {}
    shas["m1"] = commit("m1.txt")
    shas["m2"] = commit("m2.txt")
    git(work, "checkout", "-b", "feat")
    shas["f1"] = commit("f1.txt")
    shas["f2"] = commit("f2.txt")
    git(work, "checkout", "main")
    shas["m3"] = commit("m3.txt")
    git(work, "merge", "--no-ff", "feat", "-m", "merge feat")
    shas["merge"] = git(work, "rev-parse", "HEAD").stdout.strip()
    git(work, "checkout", "-b", "stack", "feat")
    shas["s1"] = commit("s1.txt")
    git(work, "checkout", "main")
    return pygit2.Repository(str(work)), shas


def _born(repo):
    commits = gitread.commits(repo)
    return gitread.born_on(repo, commits, gitread.head_branch(repo))


def test_born_on_attributes_trunk_feature_and_stack(attributed):
    repo, shas = attributed
    by = _born(repo)
    # the trunk line: pre-fork commits, main's own commit, and the merge
    for name in ("m1", "m2", "m3", "merge"):
        assert by[shas[name]] == "main", name
    # the feature's commits stay the feature's, even after the merge…
    assert by[shas["f1"]] == "feat" and by[shas["f2"]] == "feat"
    # …and the branch stacked on it owns only its own commit
    assert by[shas["s1"]] == "stack"


def test_born_on_fast_forward_belongs_to_the_trunk_line(attributed):
    repo, shas = attributed
    work = repo.workdir
    from pathlib import Path

    w = Path(work)
    git(w, "checkout", "-b", "ff-feat")
    (w / "ff.txt").write_text("ff")
    git(w, "add", ".")
    git(w, "commit", "-m", "ff work")
    sha = git(w, "rev-parse", "HEAD").stdout.strip()
    git(w, "checkout", "main")
    git(w, "merge", "--ff-only", "ff-feat")
    # born on ff-feat per the reflog — but it is main's line now
    assert _born(repo)[sha] == "main"


def test_born_on_reflog_beats_tip_distance_ties(attributed):
    repo, shas = attributed
    from pathlib import Path

    w = Path(repo.workdir)
    # a second branch parked on feat's tip: same distance-0 claim, and it
    # sorts BEFORE "feat" — only the reflog knows f2 was born on feat
    git(w, "branch", "a-parked", "feat")
    assert _born(repo)[shas["f2"]] == "feat"


def test_born_on_survives_reflogless_repos(seeded):
    """Bare server repos may have no reflogs at all — first-parent chains
    still attribute the trunk and living branch tips."""
    repo = gitread.open_repo(seeded, "app.git")
    by = _born(repo)
    commits = {c["sha"]: c["subject"] for c in gitread.commits(repo)}
    subject_of = {v: k for k, v in commits.items()}
    assert by[subject_of["merge side"]] == "main"
    assert by[subject_of["side.txt"]] == "side"
    assert by[subject_of["open.txt"]] == "open"
    assert by[subject_of["linear-0.txt"]] == "main"

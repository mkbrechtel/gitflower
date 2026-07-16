"""The issues read core: parsing, listings, documents, feed, queries."""

import pygit2
import pytest

from gitflower import issues
from tests.conftest import git

UUID_A = "11111111-aaaa-4bbb-8ccc-000000000001"
UUID_B = "11111111-aaaa-4bbb-8ccc-000000000002"
UUID_C = "11111111-aaaa-4bbb-8ccc-000000000003"


def issue_md(uuid: str, title: str, body: str = "", **fields) -> str:
    extra = "".join(f"{k}: {v}\n" for k, v in fields.items())
    return f"---\nid: {uuid}\ntitle: {title}\n{extra}---\n\n# {title}\n\n{body}"


@pytest.fixture
def issue_repo(tmp_path):
    """main: two issues + one id-less file. qa: files a new issue and edits
    one. archive: moves an issue (move+edit in ONE commit — the case uuid
    identity exists to survive). main then gains a commit qa doesn't have."""
    repo = tmp_path / "issues-work"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "issues").mkdir()
    (repo / "issues" / "login.md").write_text(issue_md(UUID_A, "Login times out", status="open"))
    (repo / "issues" / "crash.md").write_text(issue_md(UUID_B, "Crash on save", status="open"))
    (repo / "issues" / "notes.md").write_text("# Just notes\n\nno front matter\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "file issues")

    git(repo, "checkout", "-b", "qa")
    (repo / "issues" / "flicker.md").write_text(issue_md(UUID_C, "Flickering menu", status="open"))
    (repo / "issues" / "login.md").write_text(
        issue_md(UUID_A, "Login times out", "Reproduced on staging.\n", status="confirmed")
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "qa: file flicker, confirm login")

    git(repo, "checkout", "-b", "archive", "main")
    (repo / "issues" / "archive").mkdir()
    (repo / "issues" / "archive" / "crash.md").write_text(
        issue_md(UUID_B, "Crash on save", "Fixed in 1.2.\n", status="closed")
    )
    (repo / "issues" / "crash.md").unlink()
    git(repo, "add", ".")
    git(repo, "commit", "-m", "archive crash issue, closing it")

    git(repo, "checkout", "main")
    (repo / "unrelated.txt").write_text("not an issue\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "unrelated work on main")
    return repo


@pytest.fixture
def repo(issue_repo):
    return pygit2.Repository(str(issue_repo))


# ----------------------------------------------------------- frontmatter


def test_frontmatter_parses_block():
    fm = issues.parse_frontmatter(b"---\nid: x\ntitle: T\n---\nbody\n")
    assert fm == {"id": "x", "title": "T"}


@pytest.mark.parametrize(
    "data",
    [
        b"# no front matter\n",
        b"---\n[not: a: mapping\n---\n",  # invalid yaml
        b"---\n- just\n- a list\n---\n",  # not a mapping
        b"---\nnever closed\n",
        b"",
    ],
)
def test_frontmatter_tolerates_garbage(data):
    assert issues.parse_frontmatter(data) is None


def test_frontmatter_closing_fence_at_eof():
    assert issues.parse_frontmatter(b"---\nid: x\n---") == {"id": "x"}


# ------------------------------------------------------------- documents


def test_documents_union_across_branches(repo):
    data = issues.documents(repo)
    assert data["default_branch"] == "main"
    keys = {d["key"] for d in data["issues"]}
    assert keys == {UUID_A, UUID_B, UUID_C, "path:issues/notes.md"}


def test_documents_classification(repo):
    by_key = {d["key"]: d for d in issues.documents(repo)["issues"]}

    login = by_key[UUID_A]["branches"]
    assert login["main"]["state"] == "same"
    assert login["qa"]["state"] == "modified"
    assert login["archive"]["state"] == "same"

    flicker = by_key[UUID_C]["branches"]
    assert flicker["qa"]["state"] == "added"
    assert "main" not in flicker

    # crash moved AND changed in one commit on archive: modified (uuid keeps
    # identity; the path change is subsumed by the content change)
    crash = by_key[UUID_B]["branches"]
    assert crash["archive"]["state"] == "modified"
    assert crash["archive"]["path"] == "issues/archive/crash.md"
    assert crash["main"]["state"] == "same"


def test_documents_title_and_frontmatter_from_default_branch(repo):
    by_key = {d["key"]: d for d in issues.documents(repo)["issues"]}
    assert by_key[UUID_A]["title"] == "Login times out"
    assert by_key[UUID_A]["frontmatter"]["status"] == "open"  # main's, not qa's


def test_documents_idless_file_falls_back_to_path(repo):
    by_key = {d["key"]: d for d in issues.documents(repo)["issues"]}
    notes = by_key["path:issues/notes.md"]
    assert notes["id"] is None
    assert notes["title"] == "Just notes"  # first heading


def test_documents_deleted_state(issue_repo, repo):
    git(issue_repo, "checkout", "-b", "resolve")
    (issue_repo / "issues" / "login.md").unlink()
    git(issue_repo, "add", ".")
    git(issue_repo, "commit", "-m", "resolve login by deleting it")
    git(issue_repo, "checkout", "main")
    by_key = {d["key"]: d for d in issues.documents(repo)["issues"]}
    assert by_key[UUID_A]["branches"]["resolve"]["state"] == "deleted"


# ------------------------------------------------------------------ feed


def test_feed_transitions(repo):
    cfg = issues.issues_config(repo)
    feed = issues.transitions_feed(repo, cfg, issues.issue_branches(repo, cfg))
    subjects = {t["subject"] for t in feed}
    assert "file issues" in subjects
    assert "unrelated work on main" not in subjects  # path-scoped walk

    crash = [t for t in feed if issues._transition_key(repo, t) == UUID_B]
    paths = {(t["path"], t["status"]) for t in crash}
    # the move+edit commit shows as D old path + A new path, both keyed to
    # the same uuid — exactly what path identity could not do
    assert ("issues/crash.md", "D") in paths
    assert ("issues/archive/crash.md", "A") in paths
    assert ("issues/crash.md", "A") in paths  # the original filing


def test_feed_full_oids(repo):
    cfg = issues.issues_config(repo)
    feed = issues.transitions_feed(repo, cfg, ["main"])
    assert all(len(t["new_oid"]) == 40 for t in feed)


# ------------------------------------------------------------------ config


def test_config_defaults(repo):
    cfg = issues.issues_config(repo)
    assert cfg.directory == "issues"
    assert cfg.branches == []


def test_config_from_git_config(issue_repo, repo):
    git(issue_repo, "config", "gitflower.issues.directory", "tickets")
    git(issue_repo, "config", "--add", "gitflower.issues.branches", "main")
    git(issue_repo, "config", "--add", "gitflower.issues.branches", "qa")
    cfg = issues.issues_config(repo)
    assert cfg.directory == "tickets"
    assert cfg.branches == ["main", "qa"]
    assert issues.issue_branches(repo, cfg) == ["main", "qa"]  # archive filtered out


def test_configured_directory_scopes_everything(issue_repo, repo):
    git(issue_repo, "config", "gitflower.issues.directory", "tickets")
    assert issues.documents(repo)["issues"] == []


# ------------------------------------------------------------------ query


def test_filter_documents_by_frontmatter(repo):
    docs = issues.documents(repo)["issues"]
    open_issues = issues.filter_documents(docs, "[?frontmatter.status=='open']")
    assert {d["key"] for d in open_issues} == {UUID_A, UUID_B, UUID_C}


def test_filter_documents_by_branch_state(repo):
    docs = issues.documents(repo)["issues"]
    on_qa = issues.filter_documents(docs, "[?branches.qa]")
    assert {d["key"] for d in on_qa} == {UUID_A, UUID_B, UUID_C, "path:issues/notes.md"}


def test_filter_documents_bad_expression(repo):
    with pytest.raises(issues.QueryError):
        issues.filter_documents([], "[?unclosed")


def test_filter_documents_must_select_documents(repo):
    docs = issues.documents(repo)["issues"]
    with pytest.raises(issues.QueryError):
        issues.filter_documents(docs, "[].title")


# ----------------------------------------------------------------- detail


def test_issue_detail(repo):
    detail = issues.issue_detail(repo, UUID_B)
    assert detail["title"] == "Crash on save"
    assert detail["shown_branch"] == "main"
    assert "# Crash on save" in detail["content"]
    assert {t["status"] for t in detail["transitions"]} == {"A", "D"}


def test_issue_detail_pinned_at_commit(issue_repo, repo):
    tip = git(issue_repo, "rev-parse", "archive").stdout.strip()
    detail = issues.issue_detail(repo, UUID_B, at=tip)
    assert detail["shown_path"] == "issues/archive/crash.md"
    assert "Fixed in 1.2." in detail["content"]


def test_issue_detail_unknown(repo):
    assert issues.issue_detail(repo, "no-such-id") is None
    assert issues.issue_detail(repo, UUID_A, at="not-a-commit") is None


# ------------------------------------------------------------ cross-links


def test_issues_for_commit(issue_repo, repo):
    sha = git(issue_repo, "rev-parse", "archive").stdout.strip()
    found = issues.issues_for_commit(repo, sha)
    assert [f["id"] for f in found] == [UUID_B]

    unrelated = git(issue_repo, "rev-parse", "main").stdout.strip()
    assert issues.issues_for_commit(repo, unrelated) == []


def test_issue_for_blob(repo):
    doc = issues.documents(repo)["issues"]
    login = next(d for d in doc if d["key"] == UUID_A)
    oid = login["branches"]["main"]["oid"]
    found = issues.issue_for_blob(repo, "issues/login.md", oid)
    assert found["id"] == UUID_A
    assert issues.issue_for_blob(repo, "README.md", oid) is None


# ------------------------------------------------------------------- fsck


def test_fsck_reports_missing_and_duplicate_ids(issue_repo, repo):
    git(issue_repo, "checkout", "-b", "broken")
    (issue_repo / "issues" / "twin.md").write_text(issue_md(UUID_A, "Twin of login"))
    git(issue_repo, "add", ".")
    git(issue_repo, "commit", "-m", "duplicate id by copy-paste")
    git(issue_repo, "checkout", "main")
    findings = issues.fsck(repo)
    kinds = {(f["kind"], f["branch"]) for f in findings}
    assert ("duplicate-id", "broken") in kinds
    assert ("missing-id", "main") in kinds
    dup = next(f for f in findings if f["kind"] == "duplicate-id")
    assert dup["id"] == UUID_A

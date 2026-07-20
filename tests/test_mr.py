"""The merge-request model: grammar, discovery, and derived state."""

import pygit2
import pytest

from gitflower import mr
from tests.conftest import git


# ----------------------------------------------------------------- grammar


def test_plain_subject():
    parsed = mr.parse_subject("MR: add the thing")
    assert (parsed.title, parsed.topic, parsed.target) == ("add the thing", None, None)


def test_topic_subject():
    parsed = mr.parse_subject("MR(web-ui): tab navigation")
    assert (parsed.title, parsed.topic, parsed.target) == ("tab navigation", "web-ui", None)


def test_target_subject():
    parsed = mr.parse_subject("MR@release/1.2: backport the fix")
    assert (parsed.title, parsed.target) == ("backport the fix", "release/1.2")


@pytest.mark.parametrize(
    "subject",
    [
        "Merge branch 'x'",
        "MR:no space after the colon is still a subject",
        "mr: lowercase is not the grammar",
        "MRX: not the grammar",
        "MR:",
    ],
)
def test_non_mr_subjects(subject):
    if subject == "MR:no space after the colon is still a subject":
        assert mr.parse_subject(subject) is None
    else:
        assert mr.parse_subject(subject) is None


def test_trailer_reads_the_last_one():
    message = "Merge x\n\nMerge-Request: aaa\nMerge-Request: bbb\n"
    assert mr.trailer(message, mr.MERGE_REQUEST_TRAILER) == "bbb"
    assert mr.trailer("no trailers here\n", mr.MERGE_REQUEST_TRAILER) is None


# ----------------------------------------------------------------- fixtures


def commit(work, message, *, name=None, empty=False):
    if empty:
        git(work, "commit", "--allow-empty", "-m", message)
    else:
        (work / (name or "file.txt")).write_text(message + "\n")
        git(work, "add", ".")
        git(work, "commit", "-m", message)
    return git(work, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A repository with main and one work branch carrying a request."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    commit(work, "base", name="base.txt")
    git(work, "checkout", "-q", "-b", "feature/thing")
    commit(work, "the work", name="thing.txt")
    request = commit(work, "MR: add the thing", empty=True)
    git(work, "checkout", "-q", "main")
    return pygit2.Repository(str(work)), work, request


# --------------------------------------------------------------- discovery


def test_discover_finds_a_request_on_a_branch(repo):
    r, _work, request = repo
    found = mr.discover(r, mainline="main")
    assert [x.oid for x in found] == [request]
    assert found[0].title == "add the thing"
    assert found[0].branch == "feature/thing"
    assert found[0].state == mr.OPEN


def test_discover_survives_branch_deletion_once_recorded(repo):
    r, work, request = repo
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    git(work, "branch", "-D", "feature/thing")
    found = mr.discover(r, mainline="main")
    assert [x.oid for x in found] == [request]
    assert found[0].branch is None  # the ref remembers, the branch is gone


def test_discover_does_not_duplicate_a_recorded_request(repo):
    r, _work, request = repo
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    assert len(mr.discover(r, mainline="main")) == 1


def test_requests_already_on_main_are_merged(repo):
    """Once the work is on the mainline the request has landed. The branch
    scan alone cannot see it any more — it is behind main — which is why the
    server records the request ref as it arrives."""
    r, work, request = repo
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    git(work, "merge", "--no-ff", "feature/thing", "-m", "Merge feature/thing")
    found = mr.discover(r, mainline="main")
    assert [x.state for x in found] == [mr.MERGED]


def test_count_open_ignores_concluded(repo):
    r, work, request = repo
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    assert mr.count_open(r, mainline="main") == 1
    git(work, "merge", "--no-ff", "feature/thing", "-m", "Merge feature/thing")
    assert mr.count_open(r, mainline="main") == 0


# ------------------------------------------------------------------- state


def test_closure_closes(repo):
    r, _work, request = repo
    resolution = mr.create_resolution(r, request, "Closure", "withdrawn for now")
    r.references.create(mr.resolution_ref(request), pygit2.Oid(hex=resolution))
    found = mr.load(r, request, mainline="main")
    assert found.state == mr.CLOSED
    assert found.resolution_kind == "Closure"


def test_rejection_rejects(repo):
    r, _work, request = repo
    resolution = mr.create_resolution(r, request, "Rejection", "wrong approach")
    r.references.create(mr.resolution_ref(request), pygit2.Oid(hex=resolution))
    assert mr.load(r, request, mainline="main").state == mr.REJECTED


def test_resolution_must_be_a_closure_or_rejection(repo):
    r, _work, request = repo
    with pytest.raises(mr.MRError):
        mr.create_resolution(r, request, "Merged", "nope")


def test_a_newer_request_supersedes(repo):
    r, work, first = repo
    git(work, "checkout", "-q", "feature/thing")
    commit(work, "rework", name="thing.txt")
    second = commit(work, "MR: add the thing, reworked", empty=True)
    by_oid = {x.oid: x for x in mr.discover(r, mainline="main")}
    assert by_oid[first].state == mr.SUPERSEDED
    assert by_oid[first].superseded_by == second
    assert by_oid[second].state == mr.OPEN


def test_stacked_requests_know_their_base(repo):
    r, work, first = repo
    git(work, "checkout", "-q", "-b", "feature/stacked", "feature/thing")
    commit(work, "more work", name="stacked.txt")
    second = commit(work, "MR: the stacked thing", empty=True)
    by_oid = {x.oid: x for x in mr.discover(r, mainline="main")}
    assert by_oid[second].stacked_on == first
    assert by_oid[first].stacked_on is None
    # a stack is not a supersede: real work sits between the two requests
    assert by_oid[first].state == mr.OPEN


# --------------------------------------------------------------- readiness


def test_ready_when_the_request_is_the_tip(repo):
    r, _work, request = repo
    assert mr.is_ready(r, "feature/thing", "main").oid == request


def test_ready_through_a_trailing_empty_commit(repo):
    r, work, request = repo
    git(work, "checkout", "-q", "feature/thing")
    commit(work, "an afterthought, no tree change", empty=True)
    assert mr.is_ready(r, "feature/thing", "main").oid == request


def test_not_ready_when_work_follows_the_request(repo):
    r, work, _request = repo
    git(work, "checkout", "-q", "feature/thing")
    commit(work, "more work after asking", name="later.txt")
    assert mr.is_ready(r, "feature/thing", "main") is None


def test_not_ready_without_a_request(repo):
    r, work, _request = repo
    git(work, "checkout", "-q", "-b", "feature/quiet", "main")
    commit(work, "unrequested work", name="quiet.txt")
    assert mr.is_ready(r, "feature/quiet", "main") is None


# ------------------------------------------------------------------ writes


def test_create_request_is_empty_and_advances_the_branch(repo):
    r, work, _request = repo
    git(work, "checkout", "-q", "-b", "feature/another", "main")
    before = git(work, "rev-parse", "HEAD").stdout.strip()
    oid = mr.create_request(r, "feature/another", "another thing", body="why it matters")
    made = r.get(oid)
    assert made.tree.id == r.get(before).tree.id  # empty by construction
    assert str(r.references["refs/heads/feature/another"].target) == oid
    assert made.message.startswith("MR: another thing\n")
    assert "why it matters" in made.message
    assert mr.load(r, oid, mainline="main").title == "another thing"


def test_create_request_writes_the_topic_and_target_forms(repo):
    r, _work, _request = repo
    topic = mr.create_request(r, "main", "with a topic", topic="web-ui")
    assert r.get(topic).message.startswith("MR(web-ui): with a topic")
    target = mr.create_request(r, "main", "with a target", target="release/1.2")
    assert r.get(target).message.startswith("MR@release/1.2: with a target")


def test_a_request_names_a_topic_or_a_target_not_both(repo):
    r, _work, _request = repo
    with pytest.raises(mr.MRError):
        mr.create_request(r, "main", "confused", topic="x", target="y")


# ------------------------------------------------------------ bookkeeping


def test_record_push_records_arriving_requests(repo):
    r, _work, request = repo
    tip = str(r.references["refs/heads/feature/thing"].target)
    notes = mr.record_push(r, "feature/thing", "0" * 40, tip, mainline="main")
    assert str(r.references[mr.request_ref(request)].target) == request
    assert any(request[: mr.ABBREV] in note for note in notes)
    # recording twice is not an error and does not duplicate
    assert mr.record_push(r, "feature/thing", "0" * 40, tip, mainline="main") == []


def test_record_push_concludes_on_the_mainline(repo):
    r, work, request = repo
    before = str(r.references["refs/heads/main"].target)
    mr.record_push(
        r, "feature/thing", "0" * 40,
        str(r.references["refs/heads/feature/thing"].target), mainline="main",
    )
    git(work, "merge", "--no-ff", "feature/thing", "-m", "Merge feature/thing")
    after = str(r.references["refs/heads/main"].target)
    mr.record_push(r, "main", before, after, mainline="main")
    assert str(r.references[mr.merge_ref(request)].target) == after
    assert str(r.references[mr.resolution_ref(request)].target) == after
    assert mr.load(r, request, mainline="main").state == mr.MERGED


def test_a_basket_merge_does_not_conclude(repo):
    """Sitting in an integration branch is not landing: the request stays
    open until the mainline reaches it."""
    r, work, request = repo
    mr.record_push(
        r, "feature/thing", "0" * 40,
        str(r.references["refs/heads/feature/thing"].target), mainline="main",
    )
    git(work, "checkout", "-q", "-b", "integration/topic", "main")
    before = str(r.references["refs/heads/integration/topic"].target)
    git(work, "merge", "--no-ff", "feature/thing", "-m", "Merge feature/thing into integration")
    after = str(r.references["refs/heads/integration/topic"].target)
    mr.record_push(r, "integration/topic", before, after, mainline="main")
    assert mr.merge_ref(request) not in r.references
    assert mr.load(r, request, mainline="main").state == mr.OPEN


def test_the_trailer_names_what_a_merge_concludes(repo):
    r, work, request = repo
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    before = str(r.references["refs/heads/main"].target)
    git(
        work,
        "merge",
        "--no-ff",
        "feature/thing",
        "-m",
        f"Merge feature/thing\n\n{mr.MERGE_REQUEST_TRAILER}: {request}",
    )
    after = str(r.references["refs/heads/main"].target)
    assert mr.concluding_merges(r, before, after) == {request: after}


def test_gitread_counts_the_same_namespace(repo):
    """The repository scan matches the refs literally rather than opening the
    MR model — this pins the two spellings together."""
    from gitflower import gitread

    r, work, request = repo
    assert gitread.MR_REF_PREFIX == mr.MR_REF_PREFIX
    assert mr.request_ref(request) == f"{gitread.MR_REF_PREFIX}{request}{gitread.MR_REQUEST_SUFFIX}"
    r.references.create(mr.request_ref(request), pygit2.Oid(hex=request))
    r.references.create(mr.merge_ref(request), pygit2.Oid(hex=request))
    info = gitread._scan_one(work.parent, work)
    assert info.mr_count == 1  # the merge ref is not a second request

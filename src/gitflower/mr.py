"""Merge requests, as git objects.

A merge request is an empty commit on the work branch whose subject reads
`MR: <title>`. The commit's own SHA is the id — intrinsic to the repository,
needing no allocation, and abbreviating like any other SHA. Three refs track
it, all maintained by the server:

    refs/mrs/<oid>/request      the MR commit itself
    refs/mrs/<oid>/merge        the merge that concluded it positively
    refs/mrs/<oid>/resolution   that merge, or a Closure:/Rejection: commit

State is derived, never stored: there is no status field that could drift
from what the graph says. An MR is open until something concludes it, and
what concludes it is reachability — the request being merged into the
default branch — or an explicit resolution commit.

Discovery reads both the refs and the branches. The refs survive branch
deletion and are the durable record; the branch scan finds MR commits that
have been made but not yet pushed through a server that keeps refs, which is
what a clone sees. See issues/in-tree-merge-requests.md for the design.
"""

import re
from dataclasses import dataclass, field

import pygit2

MR_REF_PREFIX = "refs/mrs/"
REQUEST = "request"
MERGE = "merge"
RESOLUTION = "resolution"

#: `MR: title`, `MR(topic): title`, `MR@target: title`
MR_SUBJECT = re.compile(r"^MR(?:\((?P<topic>[^)]+)\)|@(?P<target>\S+))?: (?P<title>.+)$")
RESOLUTION_SUBJECT = re.compile(r"^(?P<kind>Closure|Rejection): (?P<reason>.+)$")

#: written by every helper that cuts a concluding merge, so the server can
#: identify what a merge concludes without guessing
MERGE_REQUEST_TRAILER = "Merge-Request"

OPEN = "open"
MERGED = "merged"
CLOSED = "closed"
REJECTED = "rejected"
SUPERSEDED = "superseded"

ABBREV = 12


class MRError(Exception):
    pass


def request_ref(oid: str) -> str:
    return f"{MR_REF_PREFIX}{oid}/{REQUEST}"


def merge_ref(oid: str) -> str:
    return f"{MR_REF_PREFIX}{oid}/{MERGE}"


def resolution_ref(oid: str) -> str:
    return f"{MR_REF_PREFIX}{oid}/{RESOLUTION}"


@dataclass
class Subject:
    """The parsed first line of an MR commit."""

    title: str
    topic: str | None = None
    target: str | None = None


def parse_subject(subject: str) -> Subject | None:
    """The MR grammar, or None if this commit is not a merge request."""
    match = MR_SUBJECT.match(subject.strip())
    if match is None:
        return None
    return Subject(
        title=match.group("title").strip(),
        topic=match.group("topic"),
        target=match.group("target"),
    )


def trailer(message: str, name: str) -> str | None:
    """The last `Name: value` trailer with this name, if any."""
    found = None
    for line in message.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == name:
            found = value.strip()
    return found


@dataclass
class MergeRequest:
    oid: str
    short: str
    title: str
    body: str
    author: str
    email: str
    date: str
    topic: str | None = None
    target: str | None = None  # explicit MR@<branch> target, else the mainline
    branch: str | None = None  # a branch whose history carries the request
    state: str = OPEN
    merge_oid: str | None = None
    resolution_oid: str | None = None
    resolution_kind: str | None = None  # Closure | Rejection
    superseded_by: str | None = None
    stacked_on: str | None = None
    baskets: list[str] = field(default_factory=list)


def _subject_and_body(message: str) -> tuple[str, str]:
    subject, _, rest = message.partition("\n")
    return subject.strip(), rest.strip("\n")


def _date(commit: pygit2.Commit) -> str:
    from gitflower.gitread import _commit_date

    return _commit_date(commit)


def _request_oids(repo: pygit2.Repository) -> set[str]:
    """Every MR id the server has recorded."""
    tail = "/" + REQUEST
    return {
        ref[len(MR_REF_PREFIX) : -len(tail)]
        for ref in repo.references
        if ref.startswith(MR_REF_PREFIX) and ref.endswith(tail)
    }


def _ref_target(repo: pygit2.Repository, name: str) -> str | None:
    try:
        return str(repo.references[name].target)
    except KeyError:
        return None


def default_branch(repo: pygit2.Repository) -> str | None:
    """The mainline a request aims at unless it names its own target.

    On a hosting repository HEAD is the default branch and says it. In a
    clone HEAD follows the checkout — asking it there would make the branch
    you happen to be on the mainline — so the remote's idea of the default
    branch wins, and HEAD is the last resort.
    """
    from gitflower.gitread import head_branch

    if not repo.is_bare:
        remotes = [r.name for r in repo.remotes] or ["origin"]
        for remote in remotes:
            # what the remote says its default is, when it has said so
            try:
                ref = repo.references[f"refs/remotes/{remote}/HEAD"]
            except KeyError:
                ref = None
            if ref is not None:
                target = ref.target
                if isinstance(target, str) and target.startswith("refs/remotes/"):
                    return target.split("/", 3)[-1]
            # a clone of a repository that was empty at the time never
            # learns origin/HEAD, so fall back to the conventional names
            # among the branches the remote does have
            for name in ("main", "master", "trunk"):
                if f"refs/remotes/{remote}/{name}" in repo.references:
                    return name
    return head_branch(repo)


def _tip(repo: pygit2.Repository, branch: str) -> pygit2.Commit | None:
    try:
        return repo.revparse_single(f"refs/heads/{branch}").peel(pygit2.Commit)
    except (KeyError, pygit2.GitError, pygit2.InvalidSpecError):
        return None


def _reaches(repo: pygit2.Repository, tip: pygit2.Commit | None, oid: str) -> bool:
    """Is `oid` in `tip`'s history (or the tip itself)?"""
    if tip is None:
        return False
    if str(tip.id) == oid:
        return True
    try:
        return repo.descendant_of(tip.id, oid)
    except (ValueError, pygit2.GitError):
        return False


def scan_branches(
    repo: pygit2.Repository, *, mainline: str | None = None, hidden: tuple[str, ...] = ()
) -> dict[str, str]:
    """MR commits found on branches, mapped to the branch carrying them.

    Walks each branch back to where the default branch already covers it, so
    a long-lived mainline is not re-read for every branch. This is what a
    clone sees: the same one-liner as
    `git log --branches --not main --grep '^MR[(:]'`.
    """
    trunk = mainline or default_branch(repo)
    trunk_tip = _tip(repo, trunk) if trunk else None
    carriers: dict[str, list[str]] = {}
    offered: dict[str, str] = {}  # branch -> the request it offers
    for name in sorted(repo.branches.local):
        if name == trunk or name in hidden:
            continue
        tip = _tip(repo, name)
        if tip is None:
            continue
        walker = repo.walk(tip.id)
        if trunk_tip is not None:
            walker.hide(trunk_tip.id)
        for commit in walker:
            if not is_request(repo, commit):
                continue
            oid = str(commit.id)
            carriers.setdefault(oid, []).append(name)
            offered.setdefault(name, oid)  # the walk is newest-first
    # A request belongs to the branch that offers it — the branch whose
    # newest request it is. A stacked branch carries the requests below it
    # too, but does not offer them; without this they would look like one
    # branch asking twice, which is what supersede means.
    owners = {oid: branch for branch, oid in offered.items()}
    # A request no branch offers has none: the branch that asked is gone, and
    # the branches that merely carry it are asking for something else.
    return {oid: owners.get(oid) for oid in carriers}


def is_request(repo: pygit2.Repository, commit: pygit2.Commit) -> bool:
    """An MR commit is empty, by construction and by definition.

    The subject alone is not enough: a work commit that happens to be
    described as `MR: …` changes the tree, and asking for something is not
    the same as doing it.
    """
    subject, _ = _subject_and_body(commit.message)
    return parse_subject(subject) is not None and _is_empty(repo, commit)


def load(
    repo: pygit2.Repository,
    oid: str,
    *,
    branch: str | None = None,
    mainline: str | None = None,
) -> MergeRequest | None:
    """One merge request by id, with its state derived."""
    try:
        commit = repo.get(oid)
    except (ValueError, KeyError):
        return None
    if commit is None or not isinstance(commit, pygit2.Commit):
        return None
    subject_line, body = _subject_and_body(commit.message)
    subject = parse_subject(subject_line)
    if subject is None or not _is_empty(repo, commit):
        return None
    oid = str(commit.id)
    request = MergeRequest(
        oid=oid,
        short=oid[:ABBREV],
        title=subject.title,
        body=body,
        topic=subject.topic,
        target=subject.target,
        author=commit.author.name,
        email=commit.author.email,
        date=_date(commit),
        branch=branch,
        merge_oid=_ref_target(repo, merge_ref(oid)),
        resolution_oid=_ref_target(repo, resolution_ref(oid)),
    )
    _derive_state(repo, request, mainline)
    return request


def _derive_state(
    repo: pygit2.Repository, request: MergeRequest, mainline: str | None = None
) -> None:
    """Resolution ref, then reachability, then supersede, else open.

    Reachability outranks supersede on purpose: once the line of work is in
    the mainline it has landed, whether or not a later request replaced this
    one on the way. Supersede is only interesting while nothing has merged.
    """
    if request.resolution_oid:
        resolution = repo.get(request.resolution_oid)
        if resolution is not None and isinstance(resolution, pygit2.Commit):
            subject, _ = _subject_and_body(resolution.message)
            match = RESOLUTION_SUBJECT.match(subject)
            if match:
                request.resolution_kind = match.group("kind")
                request.state = CLOSED if match.group("kind") == "Closure" else REJECTED
                return
        request.state = MERGED
        return

    target = request.target or mainline or default_branch(repo)
    if target and _reaches(repo, _tip(repo, target), request.oid):
        request.state = MERGED
        return

    request.state = OPEN


def _nearest_above(repo: pygit2.Repository, candidates: list[MergeRequest]) -> MergeRequest:
    """Of several requests built on top of one another, the lowest — the one
    the most others descend from."""
    return max(
        candidates,
        key=lambda o: sum(
            1 for x in candidates if x.oid != o.oid and _reaches(repo, repo.get(x.oid), o.oid)
        ),
    )


def _nearest_below(repo: pygit2.Repository, candidates: list[MergeRequest]) -> MergeRequest:
    """Of several requests underneath one, the highest — the one that
    descends from the most others."""
    return max(
        candidates,
        key=lambda o: sum(
            1 for x in candidates if x.oid != o.oid and _reaches(repo, repo.get(o.oid), x.oid)
        ),
    )


def _same_line(repo: pygit2.Repository, newer: str, older: str) -> bool:
    """Is `older` on `newer`'s own line of work?

    Following first parents only, and refusing to cross a merge. Work that
    arrived through a merge is work someone else did on their own line; a
    rework is what happens when you keep committing on yours.
    """
    commit = repo.get(newer)
    while commit is not None and isinstance(commit, pygit2.Commit):
        if str(commit.id) == older:
            return True
        if len(commit.parents) != 1:
            return False
        commit = commit.parents[0]
    return False


def _apply_supersede(
    repo: pygit2.Repository, requests: list[MergeRequest], carriers: dict[str, str | None]
) -> None:
    """A branch offers one request at a time: its newest.

    Rework supersedes — the request never moves, so asking again means a new
    MR commit, and the older one is spent. Three cases have to stay apart,
    and each clause below separates one of them:

    * a **rework**: the branch has moved past this request to a newer one on
      the same line, and nothing else offers it;
    * a **stack**: another branch is built on top, but this request is still
      the one its own branch offers, so it is still being asked for;
    * **history**: an old request that merged into an integration branch is
      carried by everything built since. It arrived through a merge, so it is
      not on the newer request's line and supersedes nothing.
    """
    offered = {r.branch for r in requests if r.branch}
    for request in requests:
        if request.state != OPEN or request.branch is not None:
            continue  # a request its own branch still offers is not spent
        newer = [
            other
            for other in requests
            if other.oid != request.oid
            and other.state == OPEN
            and other.branch in offered
            and _same_line(repo, other.oid, request.oid)
        ]
        if not newer:
            continue
        replacement = _nearest_above(repo, newer)
        request.state = SUPERSEDED
        request.superseded_by = replacement.oid
        request.branch = replacement.branch  # the branch that moved on


def _apply_stacking(repo: pygit2.Repository, requests: list[MergeRequest]) -> None:
    """`stacked_on` is the nearest unmerged request this one builds upon."""
    unmerged = [r for r in requests if r.state != MERGED]
    for request in requests:
        below = [
            other
            for other in unmerged
            if other.oid != request.oid and _reaches(repo, repo.get(request.oid), other.oid)
        ]
        if below:
            request.stacked_on = _nearest_below(repo, below).oid


def discover(
    repo: pygit2.Repository, *, mainline: str | None = None, hidden: tuple[str, ...] = ()
) -> list[MergeRequest]:
    """Every merge request in the repository, newest first.

    The union of the recorded refs and what the branches carry: refs outlive
    the branch, and a branch shows work the server has not seen yet.
    """
    mainline = mainline or default_branch(repo)
    on_branches = scan_branches(repo, mainline=mainline, hidden=hidden)
    requests: list[MergeRequest] = []
    for oid in _request_oids(repo) | set(on_branches):
        request = load(repo, oid, branch=on_branches.get(oid), mainline=mainline)
        if request is not None:
            requests.append(request)
    _apply_supersede(repo, requests, on_branches)
    _apply_stacking(repo, requests)
    requests.sort(key=lambda r: r.date, reverse=True)
    return requests


def count_open(repo: pygit2.Repository, *, mainline: str | None = None) -> int:
    """Open merge requests — what the repository list shows."""
    return sum(1 for request in discover(repo, mainline=mainline) if request.state == OPEN)


def is_ready(repo: pygit2.Repository, branch: str, base: str) -> MergeRequest | None:
    """The request a branch offers for merging, if it offers one.

    Ready means the newest MR commit is the tip, or everything above it is
    empty — a trailing annotation does not unready a branch, but real work
    after the request does: that work was never requested.
    """
    tip = _tip(repo, branch)
    base_tip = _tip(repo, base)
    if tip is None:
        return None
    walker = repo.walk(tip.id)
    if base_tip is not None:
        walker.hide(base_tip.id)
    above: list[pygit2.Commit] = []
    for commit in walker:
        if is_request(repo, commit):
            if any(not _is_empty(repo, c) for c in above):
                return None
            return load(repo, str(commit.id), branch=branch, mainline=base)
        above.append(commit)
    return None


def line_of_work(
    repo: pygit2.Repository, request_oid: str, *, mainline: str | None = None, limit: int = 200
) -> list[dict]:
    """The commits a request is asking to merge, newest first.

    Everything the request carries that the mainline does not — the work, not
    the branch's whole history. A stacked request still lists the work below
    it, because that is what merging it would bring in.
    """
    from gitflower.gitread import _commit_dict

    request = repo.get(request_oid)
    if request is None or not isinstance(request, pygit2.Commit):
        return []
    trunk = mainline or default_branch(repo)
    trunk_tip = _tip(repo, trunk) if trunk else None
    walker = repo.walk(request.id)
    if trunk_tip is not None:
        walker.hide(trunk_tip.id)
    out = []
    for commit in walker:
        out.append(_commit_dict(commit))
        if len(out) >= limit:
            break
    return out


def _is_empty(repo: pygit2.Repository, commit: pygit2.Commit) -> bool:
    """No tree change against the first parent."""
    if not commit.parents:
        return not len(commit.tree)
    return commit.tree.id == commit.parents[0].tree.id


def create_request(
    repo: pygit2.Repository,
    branch: str,
    title: str,
    *,
    body: str = "",
    topic: str | None = None,
    target: str | None = None,
    author: pygit2.Signature | None = None,
) -> str:
    """Put an MR commit on `branch` and return its id.

    Empty by construction — it reuses the branch tip's tree — so it never
    conflicts and never changes what merges.
    """
    tip = _tip(repo, branch)
    if tip is None:
        raise MRError(f"no such branch: {branch}")
    if topic and target:
        raise MRError("a merge request names a topic or a target, not both")
    prefix = f"MR({topic})" if topic else (f"MR@{target}" if target else "MR")
    message = f"{prefix}: {title}\n"
    if body:
        message += f"\n{body.strip()}\n"
    signature = author or repo.default_signature
    oid = repo.create_commit(
        f"refs/heads/{branch}", signature, signature, message, tip.tree.id, [tip.id]
    )
    return str(oid)


def create_resolution(
    repo: pygit2.Repository,
    request_oid: str,
    kind: str,
    reason: str,
    *,
    author: pygit2.Signature | None = None,
) -> str:
    """Build the empty commit that closes or rejects a request.

    Only the negative resolutions: a merge concludes an MR positively, and
    that is a real merge commit, not this.
    """
    if kind not in ("Closure", "Rejection"):
        raise MRError(f"a resolution is a Closure or a Rejection, not {kind!r}")
    request = repo.get(request_oid)
    if request is None or not isinstance(request, pygit2.Commit):
        raise MRError(f"no such merge request: {request_oid}")
    signature = author or repo.default_signature
    message = f"{kind}: {reason.strip()}\n"
    oid = repo.create_commit(
        None, signature, signature, message, request.tree.id, [request.id]
    )
    return str(oid)


def concluding_merges(repo: pygit2.Repository, old: str, new: str) -> dict[str, str]:
    """Which requests each merge in `old..new` concludes.

    A merge says so itself when it carries a `Merge-Request:` trailer — every
    gitflower helper writes one. Otherwise the shape says it: a merge that
    reaches a request through a later parent but not through its first parent
    is what brought that request in.
    """
    concluded: dict[str, str] = {}
    new_commit = repo.get(new)
    if new_commit is None or not isinstance(new_commit, pygit2.Commit):
        return concluded
    walker = repo.walk(new_commit.id)
    old_commit = repo.get(old) if old and set(old) != {"0"} else None
    if old_commit is not None and isinstance(old_commit, pygit2.Commit):
        walker.hide(old_commit.id)
    known = _request_oids(repo)
    for commit in walker:
        if len(commit.parents) < 2:
            continue
        named = trailer(commit.message, MERGE_REQUEST_TRAILER)
        if named:
            concluded.setdefault(named, str(commit.id))
            continue
        first = commit.parents[0]
        for parent in commit.parents[1:]:
            for oid in known:
                if oid in concluded:
                    continue
                if _reaches(repo, parent, oid) and not _reaches(repo, first, oid):
                    concluded.setdefault(oid, str(commit.id))
    return concluded


def record_push(
    repo: pygit2.Repository, branch: str, old: str, new: str, *, mainline: str | None = None
) -> list[str]:
    """Server-side bookkeeping for one pushed branch; returns what it did.

    Runs after the push is durable, never before: these refs are a record of
    what happened, and recording must not be able to fail a push. Requests
    are recorded as they arrive on any branch; a request concludes only when
    the mainline (or its explicit target) reaches it, so sitting in an
    integration basket leaves it open.
    """
    notes: list[str] = []
    new_commit = repo.get(new)
    if new_commit is None or not isinstance(new_commit, pygit2.Commit):
        return notes

    walker = repo.walk(new_commit.id)
    old_commit = repo.get(old) if old and set(old) != {"0"} else None
    if old_commit is not None and isinstance(old_commit, pygit2.Commit):
        walker.hide(old_commit.id)
    for commit in walker:
        if not is_request(repo, commit):
            continue
        oid = str(commit.id)
        if _ref_target(repo, request_ref(oid)) is None:
            repo.references.create(request_ref(oid), commit.id)
            notes.append(f"recorded merge request {oid[:ABBREV]}")

    mainline = mainline or default_branch(repo)
    for oid, merge_oid in concluding_merges(repo, old, new).items():
        request = load(repo, oid, mainline=mainline)
        if request is None:
            continue
        target = request.target or mainline
        if branch != target:
            continue
        if _ref_target(repo, merge_ref(oid)) is not None:
            continue
        repo.references.create(merge_ref(oid), pygit2.Oid(hex=merge_oid))
        repo.references.create(resolution_ref(oid), pygit2.Oid(hex=merge_oid))
        notes.append(f"merge request {oid[:ABBREV]} concluded by {merge_oid[:ABBREV]}")
    return notes

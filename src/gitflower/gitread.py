"""Read-only git access for the hosting CLI and the web browser (pygit2).

Everything here reads; the only writer is `create_repository` (a bare init).
The hook engine deliberately does NOT use this module — it shells out to git,
because hooks run inside live repositories (see workflows.py).
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pygit2
from pygit2.enums import SortMode

from gitflower import mergerows
from gitflower.slug import is_repository, validate_repo_path, validate_slug, SlugError

# NOTE: libgit2 enforces git's safe.directory ownership check — a repository
# owned by another user will not open. The check is respected here, not
# disabled: the packaged service runs as the static `gitflower` system user
# that owns /var/lib/gitflower, so hosted repos are created via
# `sudo -u gitflower gitflower create <path>` and ownership matches.

MR_REF_PREFIX = "refs/gitflower/merge-requests/"


class GitReadError(Exception):
    pass


@dataclass
class RepoInfo:
    path: str  # relative to the repos directory, e.g. "org/app.git"
    name: str
    branch_count: int = 0
    mr_count: int = 0
    size: int = 0
    last_update: str | None = None  # ISO 8601
    is_valid: bool = True
    error: str = ""


@dataclass
class ScanResult:
    repos: list[RepoInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _commit_date(commit: pygit2.Commit) -> str:
    tz = timezone(timedelta(minutes=commit.commit_time_offset))
    return datetime.fromtimestamp(commit.commit_time, tz).isoformat()


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def open_repo(repos_dir: Path | str, repo_path: str) -> pygit2.Repository:
    """Open a hosted repo by its validated relative path."""
    rel = validate_repo_path(repo_path)
    full = Path(repos_dir) / rel
    if not full.is_dir():
        raise GitReadError(f"no such repository: {rel}")
    try:
        return pygit2.Repository(str(full))
    except pygit2.GitError as exc:
        raise GitReadError(f"not a valid git repository: {exc}")


def scan_repos(directory: Path | str, depth: int = 3) -> ScanResult:
    """Find `*.git` repositories up to `depth` directory levels deep.

    Unlike the Go original, scan_depth is honored rather than parsed-and-ignored.
    """
    result = ScanResult()
    root = Path(directory)
    if not root.is_dir():
        return result

    def walk(current: Path, level: int) -> None:
        for entry in sorted(current.iterdir()):
            if not entry.is_dir():
                continue
            rel = str(entry.relative_to(root))
            try:
                validate_slug(entry.name)
            except SlugError:
                result.warnings.append(f"Invalid directory name: {rel}")
                continue
            if is_repository(entry.name):
                result.repos.append(_scan_one(root, entry))
            elif level < depth:
                walk(entry, level + 1)

    walk(root, 1)
    return result


def _scan_one(root: Path, path: Path) -> RepoInfo:
    info = RepoInfo(path=str(path.relative_to(root)), name=path.name)
    try:
        repo = pygit2.Repository(str(path))
    except pygit2.GitError as exc:
        info.is_valid = False
        info.error = f"not a valid git repository: {exc}"
        return info
    info.branch_count = sum(1 for _ in repo.branches.local)
    info.mr_count = sum(1 for ref in repo.references if ref.startswith(MR_REF_PREFIX))
    info.size = _dir_size(path)
    tips = _branch_tips(repo)
    if tips:
        newest = max(tips.values(), key=lambda c: c.commit_time)
        info.last_update = _commit_date(newest)
    return info


def create_repository(repos_dir: Path | str, repo_path: str, default_branch: str = "main") -> Path:
    rel = validate_repo_path(repo_path)
    full = Path(repos_dir) / rel
    if full.exists():
        raise GitReadError(f"repository {rel} already exists")
    full.parent.mkdir(parents=True, exist_ok=True)
    pygit2.init_repository(str(full), bare=True, initial_head=default_branch)
    return full


# ------------------------------------------------------------- browsing


def _branch_tips(repo: pygit2.Repository) -> dict[str, pygit2.Commit]:
    tips = {}
    for name in repo.branches.local:
        try:
            tips[name] = repo.branches.local[name].peel(pygit2.Commit)
        except pygit2.GitError:
            continue
    return tips


def head_branch(repo: pygit2.Repository) -> str | None:
    """The branch HEAD points at (even when unborn), or None if detached."""
    ref = repo.lookup_reference("HEAD")
    if ref.type == pygit2.enums.ReferenceType.SYMBOLIC:
        return str(ref.target).removeprefix("refs/heads/")
    return None


def branches(repo: pygit2.Repository) -> list[dict]:
    """Branch tips, newest commit first."""
    result = []
    for name, commit in _branch_tips(repo).items():
        result.append(
            {
                "name": name,
                "sha": str(commit.id),
                "short": str(commit.short_id),
                "date": _commit_date(commit),
                "subject": commit.message.splitlines()[0] if commit.message else "",
            }
        )
    result.sort(key=lambda b: b["date"], reverse=True)
    return result


def _commit_dict(commit: pygit2.Commit) -> dict:
    return {
        "sha": str(commit.id),
        "short": str(commit.short_id),
        "parents": [str(p) for p in commit.parent_ids],
        "author": commit.author.name,
        "date": _commit_date(commit),
        "subject": commit.message.splitlines()[0] if commit.message else "",
    }


def commits(repo: pygit2.Repository, limit: int = 400) -> list[dict]:
    """Commits reachable from any branch, newest first, children before
    parents — the ordering the graph layout's single forward pass needs."""
    tips = list(_branch_tips(repo).values())
    if not tips:
        return []
    walker = repo.walk(tips[0].id, SortMode.TOPOLOGICAL | SortMode.TIME)
    for tip in tips[1:]:
        walker.push(tip.id)
    result = []
    for commit in walker:
        result.append(_commit_dict(commit))
        if len(result) >= limit:
            break
    return result


def born_on(repo: pygit2.Repository, commits: list[dict], default: str | None) -> dict[str, str]:
    """Which branch each shown commit belongs to, best-effort.

    Git erases "made on branch X" at commit time; two signals recover most
    of it. Three layers, first claim wins:

    1. the default branch's first-parent chain — that *is* the trunk, even
       through fast-forwarded history (line identity beats birth identity);
    2. reflog entries — a `commit:` (or `commit (merge/amend):`) update
       records the sha's birth branch, and a real merge belongs to the
       branch that performed it. Reflogs are server-local and expire, so
       this only ever adds knowledge;
    3. every tip's first-parent chain, nearest tip wins — stacked branches
       resolve to the inner branch, whose tip sits closest.
    """
    shown = {c["sha"]: c for c in commits}
    tips = _branch_tips(repo)
    by: dict[str, str] = {}

    def first_parents(sha: str):
        while sha in shown:
            yield sha
            parents = shown[sha]["parents"]
            sha = parents[0] if parents else ""

    if default in tips:
        for sha in first_parents(str(tips[default].id)):
            by[sha] = default

    for name in sorted(tips):
        try:
            log = repo.lookup_reference(f"refs/heads/{name}").log()
        except (pygit2.GitError, KeyError, OSError):
            continue
        for entry in log:
            message = entry.message or ""
            born = message.startswith("commit") or ": Merge made by" in message
            if not born:
                continue  # pushes, fast-forwards, resets: not born here
            sha = str(entry.oid_new)
            if sha in shown and sha not in by:
                by[sha] = name

    nearest: dict[str, tuple[int, str]] = {}
    for name in sorted(tips):
        for distance, sha in enumerate(first_parents(str(tips[name].id))):
            if sha in by:
                continue  # claimed — but the chain continues through it
            if sha not in nearest or (distance, name) < nearest[sha]:
                nearest[sha] = (distance, name)
    for sha, (_, name) in nearest.items():
        by[sha] = name
    return by


def commit_count(repo: pygit2.Repository) -> int:
    tips = list(_branch_tips(repo).values())
    if not tips:
        return 0
    walker = repo.walk(tips[0].id, SortMode.NONE)
    for tip in tips[1:]:
        walker.push(tip.id)
    return sum(1 for _ in walker)


def resolve(repo: pygit2.Repository, ref: str) -> pygit2.Commit:
    try:
        obj = repo.revparse_single(ref)
        return obj.peel(pygit2.Commit)
    except (pygit2.GitError, KeyError, ValueError):
        raise GitReadError(f"no such ref: {ref}")


def split_ref(repo: pygit2.Repository, refpath: str) -> tuple[str, str]:
    """Split 'work/feature/x/some/dir' into (ref, subpath).

    Branch names contain slashes, so the URL grammar /tree/<ref>/<path> is
    ambiguous — the longest prefix that resolves to a ref wins (a branch
    always beats a same-named directory under a shorter branch)."""
    segments = [s for s in refpath.split("/") if s]
    for i in range(len(segments), 0, -1):
        candidate = "/".join(segments[:i])
        try:
            resolve(repo, candidate)
        except GitReadError:
            continue
        return candidate, "/".join(segments[i:])
    raise GitReadError(f"no such ref: {refpath}")


def tree_entries(repo: pygit2.Repository, ref: str, path: str = "") -> list[dict]:
    commit = resolve(repo, ref)
    tree = commit.tree
    if path:
        try:
            obj = tree[path]
        except KeyError:
            raise GitReadError(f"no such path: {path}")
        if not isinstance(obj, pygit2.Tree):
            raise GitReadError(f"not a directory: {path}")
        tree = obj
    entries = []
    for entry in tree:
        blob_size = 0
        if entry.type_str == "blob":
            blob_size = repo[entry.id].size
        entries.append(
            {
                "name": entry.name,
                "type": "dir" if entry.type_str == "tree" else "file",
                "mode": f"{entry.filemode:06o}",
                "size": blob_size,
            }
        )
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"]))
    return entries


def blob(repo: pygit2.Repository, ref: str, path: str) -> dict:
    commit = resolve(repo, ref)
    try:
        obj = commit.tree[path]
    except KeyError:
        raise GitReadError(f"no such path: {path}")
    if not isinstance(obj, pygit2.Blob):
        raise GitReadError(f"not a file: {path}")
    return {
        "path": path,
        "size": obj.size,
        "is_binary": obj.is_binary,
        "data": obj.data,
    }


def commit_detail(repo: pygit2.Repository, sha: str, parent: int | None = None) -> dict:
    """Commit metadata + the diff against one parent (1-based `parent`,
    default the first). A merge commit has one such diff per parent."""
    commit = resolve(repo, sha)
    if parent is not None and not 1 <= parent <= len(commit.parents):
        raise GitReadError(f"no such parent: {parent}")
    if commit.parents:
        diff = repo.diff(commit.parents[(parent or 1) - 1], commit)
    else:
        diff = commit.tree.diff_to_tree(swap=True)
    diff.find_similar()  # detect renames so they show as R, not delete+add

    files = []
    for patch in diff:
        delta = patch.delta
        _context, additions, deletions = patch.line_stats
        files.append(
            {
                "path": delta.new_file.path,
                "old_path": delta.old_file.path,
                "status": delta.status_char(),  # A/M/D/R/…
                "additions": additions,
                "deletions": deletions,
                "binary": bool(delta.flags & pygit2.enums.DiffFlag.BINARY),
                "patch": "" if delta.flags & pygit2.enums.DiffFlag.BINARY else (patch.text or ""),
            }
        )
    stats = diff.stats

    detail = _commit_dict(commit)
    detail.update(
        {
            "message": commit.message,
            "author_email": commit.author.email,
            "committer": commit.committer.name,
            "committer_email": commit.committer.email,
            "diff_parent": parent or 1,
            "files": files,
            "stats": {
                "files_changed": stats.files_changed,
                "additions": stats.insertions,
                "deletions": stats.deletions,
            },
            "patch": diff.patch or "",
        }
    )
    return detail


def _patch_hunks(patch: pygit2.Patch) -> list[dict]:
    """A patch's hunks in the shape mergerows.build expects."""
    hunks = []
    for hunk in patch.hunks:
        lines = [
            {
                "origin": line.origin,
                "old": line.old_lineno,
                "new": line.new_lineno,
                "text": line.content.rstrip("\n"),
            }
            for line in hunk.lines
            if line.origin in "+-"
        ]
        hunks.append({"new_start": hunk.new_start, "new_lines": hunk.new_lines, "lines": lines})
    return hunks


def merge_detail(repo: pygit2.Repository, sha: str, full: bool = False) -> dict:
    """A merge commit's side-by-side data: one diff per parent, and per file
    the aligned multi-column rows (mergerows) against the plain result."""
    commit = resolve(repo, sha)
    parents = list(commit.parents)
    if len(parents) < 2:
        raise GitReadError(f"not a merge commit: {sha}")
    diffs = []
    for p in parents:
        diff = repo.diff(p, commit, context_lines=0)
        diff.find_similar()
        diffs.append(diff)

    per_file: dict[str, list] = {}  # result path -> one patch (or None) per parent
    for i, diff in enumerate(diffs):
        for patch in diff:
            entry = per_file.setdefault(patch.delta.new_file.path, [None] * len(parents))
            entry[i] = patch

    files = []
    for path in sorted(per_file):
        patches = per_file[path]
        binary = any(
            p is not None and p.delta.flags & pygit2.enums.DiffFlag.BINARY for p in patches
        )
        result_lines: list[str] = []
        try:
            obj = commit.tree[path]
            if isinstance(obj, pygit2.Blob):
                if obj.is_binary:
                    binary = True
                elif not binary:
                    result_lines = obj.data.decode("utf-8", errors="replace").splitlines()
        except KeyError:
            pass  # file absent in the result: the merge deleted it — only-rows
        statuses, old_paths, counts, hunks = [], [], [], []
        for p in patches:
            if p is None:  # identical to this parent: every cell is `same`
                statuses.append("=")
                old_paths.append(path)
                counts.append({"additions": 0, "deletions": 0})
                hunks.append([])
            else:
                statuses.append(p.delta.status_char())
                old_paths.append(p.delta.old_file.path)
                _context, additions, deletions = p.line_stats
                counts.append({"additions": additions, "deletions": deletions})
                hunks.append([] if binary else _patch_hunks(p))
        laid_out = (
            {"rows": [], "truncated": False}
            if binary
            else mergerows.build(result_lines, hunks, full=full)
        )
        files.append(
            {
                "path": path,
                "old_paths": old_paths,
                "statuses": statuses,
                "parent_counts": counts,
                "binary": binary,
                "truncated": laid_out["truncated"],
                "rows": laid_out["rows"],
            }
        )

    detail = _commit_dict(commit)
    detail.update(
        {
            "message": commit.message,
            "author_email": commit.author.email,
            "committer": commit.committer.name,
            "committer_email": commit.committer.email,
            "parent_commits": [_commit_dict(p) for p in parents],
            "parent_stats": [
                {
                    "files_changed": d.stats.files_changed,
                    "additions": d.stats.insertions,
                    "deletions": d.stats.deletions,
                }
                for d in diffs
            ],
            "files": files,
            "full": full,
        }
    )
    return detail

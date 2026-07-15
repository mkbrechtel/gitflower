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

from gitflower.slug import is_repository, validate_repo_path, validate_slug, SlugError

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
    except (pygit2.GitError, KeyError):
        raise GitReadError(f"no such ref: {ref}")


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


def commit_detail(repo: pygit2.Repository, sha: str) -> dict:
    commit = resolve(repo, sha)
    if commit.parents:
        diff = repo.diff(commit.parents[0], commit)
    else:
        diff = commit.tree.diff_to_tree(swap=True)
    detail = _commit_dict(commit)
    detail.update(
        {
            "message": commit.message,
            "author_email": commit.author.email,
            "patch": diff.patch or "",
        }
    )
    return detail

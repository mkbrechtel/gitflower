"""In-tree issues, read across branches (design: issues/issues-view.md).

An issue is a markdown file under the configured issues directory. Identity
is the `id:` in its front matter — the single field gitflower defines; a
file without one falls back to path identity and is only tracked at its
current path.

Per-tip state comes from tree reads (pygit2); history comes from one
`git log --raw` walk over the issues directory (a subprocess, like
smart-HTTP, because pygit2 exposes neither `--raw` plumbing nor the
commit-graph acceleration the walk benefits from). Every cache is keyed by
an immutable OID — blob OID → parsed issue, tree OID → listing — so entries
never invalidate; they only grow with distinct content ever seen.
"""

import subprocess
from dataclasses import dataclass, field

import jmespath
import pygit2
import yaml

from gitflower.matcher import BadPattern, match

DEFAULT_DIRECTORY = "issues"
CONFIG_DIRECTORY = "gitflower.issues.directory"
CONFIG_BRANCHES = "gitflower.issues.branches"

ZERO_OID = "0" * 40


class QueryError(ValueError):
    """A JMESPath expression that cannot be applied to the issue list."""


@dataclass
class IssuesConfig:
    directory: str = DEFAULT_DIRECTORY
    branches: list[str] = field(default_factory=list)  # patterns; empty = all


def issues_config(repo: pygit2.Repository) -> IssuesConfig:
    """Per-repo settings from git config, readable straight off a bare repo."""
    cfg = IssuesConfig()
    try:
        cfg.directory = repo.config[CONFIG_DIRECTORY].strip().strip("/")
    except KeyError:
        pass
    try:
        cfg.branches = [p for p in (v.strip() for v in repo.config.get_multivar(CONFIG_BRANCHES)) if p]
    except KeyError:
        pass
    return cfg


# --------------------------------------------------------------- parsing

# blob OID → parsed issue; content-addressed, so never invalidated
_parsed: dict[str, dict] = {}


def parse_frontmatter(data: bytes) -> dict | None:
    """The YAML front block of a markdown file, or None if there isn't a
    well-formed one. Tolerant: any parse problem means 'no front matter',
    never an error — issue files are free-format."""
    text = data.decode("utf-8", errors="replace")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    body = text.split("\n", 1)[1]
    for end in ("\n---\n", "\n---\r\n"):
        if (pos := body.find(end)) != -1:
            block = body[:pos]
            break
    else:
        if body.rstrip("\r\n").endswith("\n---"):
            block = body.rstrip("\r\n")[: -len("\n---")]
        else:
            return None
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def parse_issue(repo: pygit2.Repository, oid: str, path: str) -> dict:
    """id, display title, and front matter of one issue blob, memoized by OID."""
    if oid in _parsed:
        return _parsed[oid]
    data = repo[oid].data
    fm = parse_frontmatter(data) or {}
    issue_id = fm.get("id")
    issue_id = str(issue_id) if issue_id is not None else None
    title = fm.get("title")
    if not isinstance(title, str) or not title:
        title = _first_heading(data.decode("utf-8", errors="replace"))
    parsed = {"id": issue_id, "title": title, "frontmatter": fm}
    _parsed[oid] = parsed
    return parsed


def _basename_title(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


# ----------------------------------------------------------- tree reads

# issues-subtree OID → {path: blob OID}; branches sharing the subtree share it
_listings: dict[str, dict[str, str]] = {}


def _subtree(repo: pygit2.Repository, commit: pygit2.Commit, directory: str):
    try:
        entry = commit.tree[directory]
    except KeyError:
        return None
    return entry if isinstance(repo[entry.id], pygit2.Tree) else None


def tree_listing(repo: pygit2.Repository, commit: pygit2.Commit, directory: str) -> dict[str, str]:
    """Markdown files under the issues directory at one commit."""
    subtree = _subtree(repo, commit, directory)
    if subtree is None:
        return {}
    key = str(subtree.id)
    if key in _listings:
        return _listings[key]
    listing: dict[str, str] = {}

    def walk(tree: pygit2.Tree, prefix: str) -> None:
        for entry in tree:
            obj = repo[entry.id]
            if isinstance(obj, pygit2.Tree):
                walk(obj, f"{prefix}{entry.name}/")
            elif entry.name.endswith(".md"):
                listing[f"{prefix}{entry.name}"] = str(entry.id)

    walk(repo[subtree.id], f"{directory}/")
    _listings[key] = listing
    return listing


def issue_branches(repo: pygit2.Repository, cfg: IssuesConfig) -> list[str]:
    """Local branches feeding the view, filtered by the configured patterns."""
    names = sorted(repo.branches.local)
    if not cfg.branches:
        return names
    selected = []
    for name in names:
        for pattern in cfg.branches:
            try:
                if match(pattern, name):
                    selected.append(name)
                    break
            except BadPattern:
                continue
    return selected


def _tip(repo: pygit2.Repository, branch: str) -> pygit2.Commit | None:
    try:
        return repo.branches.local[branch].peel(pygit2.Commit)
    except (KeyError, pygit2.GitError):
        return None


def _issue_key(parsed: dict, path: str) -> str:
    return parsed["id"] if parsed["id"] else f"path:{path}"


# ---------------------------------------------------------------- feed


def transitions_feed(repo: pygit2.Repository, cfg: IssuesConfig, branches: list[str]) -> list[dict]:
    """Every commit that changed the issues directory on any selected branch,
    newest first, with per-file old/new blob OIDs — the raw material for
    timelines and version history. One Bloom-accelerated path-scoped walk."""
    if not branches:
        return []
    out = subprocess.run(
        [
            "git",
            "-C",
            repo.path,
            "log",
            "-z",
            "--raw",
            "--no-renames",
            "--no-abbrev",
            "--diff-merges=first-parent",
            "--format=%x01%H %P%x02%aN%x02%aI%x02%s%x03",
            *branches,
            "--",
            f"{cfg.directory}/",
        ],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return []
    transitions = []
    for chunk in out.stdout.split("\x01"):
        if "\x03" not in chunk:
            continue
        header, raw = chunk.split("\x03", 1)
        shas, author, date, subject = header.split("\x02")
        sha, _, parents = shas.partition(" ")
        tokens = [t for t in raw.strip("\0\n").split("\0") if t]
        for meta, path in zip(tokens[::2], tokens[1::2]):
            fields = meta.lstrip(":").split(" ")
            if len(fields) != 5:
                continue
            _, _, old_oid, new_oid, status = fields
            transitions.append(
                {
                    "sha": sha,
                    "short": sha[:7],
                    "parents": parents.split() if parents else [],
                    "author": author,
                    "date": date,
                    "subject": subject,
                    "path": path,
                    "old_oid": old_oid,
                    "new_oid": new_oid,
                    "status": status,
                }
            )
    return transitions


def _transition_key(repo: pygit2.Repository, t: dict) -> str:
    """Which issue a transition belongs to: the new blob's id, or for a
    deletion the removed blob's — falling back to path identity."""
    oid = t["new_oid"] if t["new_oid"] != ZERO_OID else t["old_oid"]
    if oid == ZERO_OID:
        return f"path:{t['path']}"
    return _issue_key(parse_issue(repo, oid, t["path"]), t["path"])


# ----------------------------------------------------------- documents


def documents(repo: pygit2.Repository, default_branch: str | None = None) -> dict:
    """The issue documents across branch tips: the union of every tip's
    issues, each classified against the merge-base with the default branch.
    Pure tree reads and OID comparisons — no history walk, no diffs."""
    cfg = issues_config(repo)
    branches = issue_branches(repo, cfg)
    head = default_branch if default_branch in branches else None
    if head is None and branches:
        from gitflower.gitread import head_branch

        head = head_branch(repo)
        if head not in branches:
            head = branches[0]
    docs: dict[str, dict] = {}
    default_tip = _tip(repo, head) if head else None

    for branch in branches:
        tip = _tip(repo, branch)
        if tip is None:
            continue
        listing = tree_listing(repo, tip, cfg.directory)
        base_listing = listing
        if default_tip is not None and tip.id != default_tip.id:
            base_oid = repo.merge_base(tip.id, default_tip.id)
            base_listing = (
                tree_listing(repo, repo[base_oid], cfg.directory) if base_oid else {}
            )
        by_key = {}
        for path, oid in listing.items():
            parsed = parse_issue(repo, oid, path)
            by_key[_issue_key(parsed, path)] = (path, oid, parsed)
        base_by_key = {}
        for path, oid in base_listing.items():
            parsed = parse_issue(repo, oid, path)
            base_by_key[_issue_key(parsed, path)] = (path, oid)

        for key, (path, oid, parsed) in by_key.items():
            doc = docs.setdefault(
                key,
                {
                    "key": key,
                    "id": parsed["id"],
                    "title": parsed["title"] or _basename_title(path),
                    "frontmatter": parsed["frontmatter"],
                    "branches": {},
                },
            )
            if key not in base_by_key:
                state = "added"
            else:
                base_path, base_oid = base_by_key[key]
                if oid != base_oid:
                    state = "modified"
                elif path != base_path:
                    state = "moved"
                else:
                    state = "same"
            doc["branches"][branch] = {"path": path, "oid": oid, "state": state}
            if branch == head:  # the default branch names the issue
                doc["title"] = parsed["title"] or _basename_title(path)
                doc["frontmatter"] = parsed["frontmatter"]
        for key, (path, oid) in base_by_key.items():
            if key in by_key:
                continue
            parsed = parse_issue(repo, oid, path)
            doc = docs.setdefault(
                key,
                {
                    "key": key,
                    "id": parsed["id"],
                    "title": parsed["title"] or _basename_title(path),
                    "frontmatter": parsed["frontmatter"],
                    "branches": {},
                },
            )
            doc["branches"][branch] = {"path": path, "oid": oid, "state": "deleted"}

    issues = sorted(docs.values(), key=lambda d: (d["title"] or "").lower())
    return {"default_branch": head, "branches": branches, "issues": issues}


def filter_documents(issues: list[dict], expression: str) -> list[dict]:
    """Apply a JMESPath expression to the document array. The expression must
    select issue documents — arbitrary project logic, gitflower vocabulary
    not required."""
    try:
        result = jmespath.search(expression, issues)
    except jmespath.exceptions.JMESPathError as exc:
        raise QueryError(f"invalid JMESPath query: {exc}")
    if not isinstance(result, list) or not all(
        isinstance(d, dict) and "key" in d for d in result
    ):
        raise QueryError(
            "the query must select issue documents, e.g. [?frontmatter.status=='open']"
        )
    return result


def issue_detail(repo: pygit2.Repository, uuid: str, at: str | None = None) -> dict | None:
    """One issue by its id: cross-branch states, its transitions across all
    selected branches, and the content of the shown version (the default
    branch's, or the version at the pinning commit `at`)."""
    cfg = issues_config(repo)
    data = documents(repo)
    doc = next((d for d in data["issues"] if d["id"] == uuid), None)
    if doc is None:
        return None
    branches = data["branches"]
    feed = transitions_feed(repo, cfg, branches)
    mine = [t for t in feed if _transition_key(repo, t) == uuid]

    shown_branch = data["default_branch"] if data["default_branch"] in doc["branches"] else None
    if shown_branch is None and doc["branches"]:
        shown_branch = sorted(doc["branches"])[0]
    shown_oid, shown_path = None, None
    if at:
        try:
            commit = repo.revparse_single(at).peel(pygit2.Commit)
        except (KeyError, pygit2.GitError, TypeError):
            return None
        for path, oid in tree_listing(repo, commit, cfg.directory).items():
            if _issue_key(parse_issue(repo, oid, path), path) == uuid:
                shown_oid, shown_path, shown_branch = oid, path, None
                break
        if shown_oid is None:
            return None
    elif shown_branch:
        state = doc["branches"][shown_branch]
        shown_oid, shown_path = state["oid"], state["path"]
    content = repo[shown_oid].data.decode("utf-8", errors="replace") if shown_oid else ""
    return {
        **doc,
        "transitions": mine,
        "content": content,
        "shown_oid": shown_oid or "",
        "shown_path": shown_path or "",
        "shown_branch": shown_branch,
        "at": at,
    }


def issues_for_commit(repo: pygit2.Repository, sha: str) -> list[dict]:
    """The issues a commit transitions (for the commit-page cross-link):
    diff against the first parent, scoped to the issues directory."""
    cfg = issues_config(repo)
    try:
        commit = repo.revparse_single(sha).peel(pygit2.Commit)
    except (KeyError, pygit2.GitError, TypeError):
        return []
    listing = tree_listing(repo, commit, cfg.directory)
    parent_listing = (
        tree_listing(repo, commit.parents[0], cfg.directory) if commit.parents else {}
    )
    found = {}
    for path, oid in listing.items():
        if parent_listing.get(path) != oid:
            parsed = parse_issue(repo, oid, path)
            found[_issue_key(parsed, path)] = {
                "key": _issue_key(parsed, path),
                "id": parsed["id"],
                "title": parsed["title"] or _basename_title(path),
                "path": path,
            }
    for path, oid in parent_listing.items():
        if path not in listing:
            parsed = parse_issue(repo, oid, path)
            key = _issue_key(parsed, path)
            found.setdefault(
                key,
                {
                    "key": key,
                    "id": parsed["id"],
                    "title": parsed["title"] or _basename_title(path),
                    "path": path,
                },
            )
    return sorted(found.values(), key=lambda d: d["path"])


def issue_for_blob(repo: pygit2.Repository, path: str, oid: str) -> dict | None:
    """Whether a browsed blob is an issue file (for the blob-page badge)."""
    cfg = issues_config(repo)
    if not path.startswith(f"{cfg.directory}/") or not path.endswith(".md"):
        return None
    parsed = parse_issue(repo, oid, path)
    return {
        "key": _issue_key(parsed, path),
        "id": parsed["id"],
        "title": parsed["title"] or _basename_title(path),
    }

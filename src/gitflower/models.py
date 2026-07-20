"""Typed view models — the contract every surface reads.

Plain dataclasses (FastAPI wraps them in pydantic for the OpenAPI schema, so
the 5-dependency rule holds). A web route declares its model as
`response_model`; the negotiated HTML page and fragment render from the same
`asdict()` data, so the three representations cannot drift apart. The models
live here rather than under web/ because the CLI and TUI read the same
contract — one typed shape, rendered as JSON, HTML, a table, or a DataTable.
"""

import json
from dataclasses import asdict, dataclass, field, is_dataclass

from gitflower import gitread, graph as graphlayout, issues as issuestore
from gitflower.gitread import RepoInfo

GRAPH_LIMIT = 400
RECENT_COMMITS = 10


def to_dict(data):
    """The one shaping point: every surface serializes through this, so the
    JSON a CLI command prints and the JSON an endpoint returns are the same
    bytes by construction rather than by parallel code."""
    return asdict(data) if is_dataclass(data) else data


def to_json(data) -> str:
    return json.dumps(to_dict(data), indent=2)


@dataclass
class Column:
    """One column of a list view: a header and the attribute it reads.

    A spec, not a DSL — `attr` is an attribute name, never a callable, so the
    CLI table and the TUI DataTable render the same columns in the same order
    without either owning the definition. The web keeps its own cells (links,
    badges) but reads the headers from here.
    """

    header: str
    attr: str
    align: str = "left"


def cells(columns: tuple["Column", ...], row) -> list[str]:
    """One row's text cells, in column order."""
    return [str(getattr(row, c.attr, "") or "") for c in columns]


@dataclass
class RepoRow:
    """A repository as a list row — the shape the CLI table and the TUI show."""

    path: str
    branches: str
    mrs: str
    size: str
    last_update: str
    status: str

    @classmethod
    def of(cls, repo: RepoInfo) -> "RepoRow":
        return cls(
            path=repo.path,
            branches=str(repo.branch_count),
            mrs=str(repo.mr_count),
            size=f"{repo.size / (1024 * 1024):.2f} MB",
            last_update=repo.last_update or "",
            status="OK" if repo.is_valid else f"ERROR: {repo.error}",
        )


REPO_COLUMNS = (
    Column("PATH", "path"),
    Column("BRANCHES", "branches", "right"),
    Column("MR", "mrs", "right"),
    Column("SIZE", "size", "right"),
    Column("LAST UPDATE", "last_update"),
    Column("STATUS", "status"),
)

ISSUE_COLUMNS = (
    Column("TITLE", "title"),
    Column("ID", "display_id"),
    Column("BRANCHES", "states"),
)


@dataclass
class RepoList:
    """The overview and /repos/ listing."""

    repos: list[RepoInfo]
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, scan: "gitread.ScanResult") -> "RepoList":
        return cls(repos=scan.repos, warnings=scan.warnings)

    def rows(self) -> list[RepoRow]:
        return [RepoRow.of(r) for r in self.repos]


@dataclass
class OrgFolder:
    """Repositories under one organization folder."""

    org: str
    repos: list[RepoInfo]

    @classmethod
    def of(cls, org: str, scan: "gitread.ScanResult") -> "OrgFolder":
        return cls(org=org, repos=[r for r in scan.repos if r.path.startswith(org + "/")])


@dataclass
class Branch:
    name: str
    sha: str
    short: str
    date: str
    subject: str
    pinned: bool = False
    hidden: bool = False


@dataclass
class Commit:
    sha: str
    short: str
    parents: list[str]
    author: str
    date: str
    subject: str


@dataclass
class GraphEdge:
    """One parent link as an SVG path; `lanes` drives hover highlighting."""

    d: str
    color: str
    lanes: list[int]
    stub: bool
    dimmed: bool = False


@dataclass
class GraphRow:
    """One graph row: kind 'commit' carries `commit`; kind 'gap' (a folded
    linear run) carries `count`/`first`/`last`."""

    id: str
    kind: str
    parents: list[str]
    row: int
    lane: int
    x: float
    y: float
    color: str
    branch: str | None = None
    pinned: bool = False
    dimmed: bool = False  # only hidden branches reach this commit
    commit: Commit | None = None
    count: int | None = None
    first: Commit | None = None
    last: Commit | None = None


@dataclass
class Graph:
    """Commit-graph geometry: SVG coordinates, ready to draw."""

    rows: list[GraphRow]
    edges: list[GraphEdge]
    width: float
    height: float
    row_height: int
    dot: float
    collapsed: int

    @classmethod
    def of(cls, g: dict) -> "Graph":
        rows = [
            GraphRow(
                id=r["id"],
                kind=r["kind"],
                parents=r["parents"],
                row=r["row"],
                lane=r["lane"],
                x=r["x"],
                y=r["y"],
                color=r["color"],
                branch=r.get("branch"),
                pinned=r.get("pinned", False),
                dimmed=r.get("dimmed", False),
                commit=Commit(**r["commit"]) if "commit" in r else None,
                count=r.get("count"),
                first=Commit(**r["first"]) if "first" in r else None,
                last=Commit(**r["last"]) if "last" in r else None,
            )
            for r in g["rows"]
        ]
        return cls(
            rows=rows,
            edges=[GraphEdge(**e) for e in g["edges"]],
            width=g["width"],
            height=g["height"],
            row_height=g["row_height"],
            dot=g["dot"],
            collapsed=g["collapsed"],
        )


@dataclass
class RepoDetail:
    path: str
    branches: list[Branch]
    commits: list[Commit]
    graph: Graph
    full: bool
    total_shown: int
    clone_url: str
    show_hidden: bool = False
    hidden_count: int = 0  # branches hidden by config (shown when show_hidden)

    @classmethod
    def of(
        cls,
        repo,
        path: str,
        cfg,
        *,
        full: bool = False,
        show_hidden: bool = False,
        clone_url: str = "",
    ) -> "RepoDetail":
        flagged = gitread.branches(
            repo, pinned=cfg.pinned_branches, hidden=cfg.hidden_branches
        )
        branches = [Branch(**b) for b in flagged if show_hidden or not b["hidden"]]
        hide = () if show_hidden else cfg.hidden_branches
        commits = gitread.commits(repo, GRAPH_LIMIT, hidden=hide)
        trunk = gitread.head_branch(repo)
        # commits only hidden branches follow up on grey out when expanded
        dimmed: set[str] = set()
        if show_hidden and any(b.hidden for b in branches):
            live = {b.sha for b in branches if not b.hidden}
            dimmed = {c["sha"] for c in commits} - gitread.reachable(commits, live)
        laid_out = graphlayout.build(
            commits,
            {b.sha for b in branches},
            collapse=not full,
            branch_of=gitread.born_on(repo, commits, trunk, hidden=hide),
            trunk=trunk,
            pinned=[b.name for b in branches if b.pinned],
            dimmed=dimmed,
        )
        return cls(
            path=path,
            branches=branches,
            commits=[Commit(**c) for c in commits[:RECENT_COMMITS]],
            graph=Graph.of(laid_out),
            full=full,
            total_shown=len(commits),
            clone_url=clone_url,
            show_hidden=show_hidden,
            hidden_count=sum(1 for b in flagged if b["hidden"]),
        )


@dataclass
class TreeEntry:
    name: str
    type: str  # "dir" | "file"
    mode: str
    size: int


@dataclass
class TreeView:
    path: str
    ref: str
    subpath: str
    entries: list[TreeEntry]

    @classmethod
    def of(cls, repo, path: str, ref: str, subpath: str) -> "TreeView":
        entries = [TreeEntry(**e) for e in gitread.tree_entries(repo, ref, subpath)]
        return cls(path=path, ref=ref, subpath=subpath, entries=entries)


@dataclass
class IssueLink:
    """A cross-link to an issue from a commit or blob page."""

    key: str
    id: str | None
    title: str
    path: str = ""


@dataclass
class IssueBranchState:
    """One branch's version of an issue, classified against the merge-base
    with the default branch."""

    path: str
    oid: str
    state: str  # same | modified | moved | added | deleted


@dataclass
class IssueDoc:
    """One issue across branches — also the JMESPath query document."""

    key: str
    id: str | None
    title: str
    frontmatter: dict
    branches: dict[str, IssueBranchState]

    @classmethod
    def of(cls, doc: dict) -> "IssueDoc":
        return cls(
            key=doc["key"],
            id=doc["id"],
            title=doc["title"],
            frontmatter=doc["frontmatter"],
            branches={
                name: IssueBranchState(**state) for name, state in doc["branches"].items()
            },
        )

    @property
    def states(self) -> str:
        """Branch states as one cell, for the list surfaces."""
        return " ".join(f"{n}:{s.state}" for n, s in sorted(self.branches.items()))

    @property
    def display_id(self) -> str:
        return self.id or "(no id)"


@dataclass
class IssueList:
    path: str
    default_branch: str | None
    branches: list[str]
    issues: list[IssueDoc]
    query: str | None = None
    branch: str | None = None

    @classmethod
    def of(
        cls, repo, path: str, *, q: str | None = None, branch: str | None = None
    ) -> "IssueList":
        """Raises issuestore.QueryError on a bad JMESPath filter — the surface
        decides whether that is a 400 or a usage error."""
        data = issuestore.documents(repo)
        docs = data["issues"]
        if branch:
            docs = [d for d in docs if branch in d["branches"]]
        if q:
            docs = issuestore.filter_documents(docs, q)
        return cls(
            path=path,
            default_branch=data["default_branch"],
            branches=data["branches"],
            issues=[IssueDoc.of(d) for d in docs],
            query=q,
            branch=branch,
        )

    def rows(self) -> list[IssueDoc]:
        return self.issues


@dataclass
class IssueTransition:
    """One commit's change to an issue file (old/new blob OID)."""

    sha: str
    short: str
    parents: list[str]
    author: str
    date: str
    subject: str
    path: str
    old_oid: str
    new_oid: str
    status: str


@dataclass
class IssueDetail:
    path: str
    key: str
    id: str | None
    title: str
    frontmatter: dict
    branches: dict[str, IssueBranchState]
    transitions: list[IssueTransition]
    content: str
    shown_oid: str
    shown_path: str
    shown_branch: str | None
    at: str | None = None

    @classmethod
    def of(cls, repo, path: str, uuid: str, *, at: str | None = None) -> "IssueDetail | None":
        detail = issuestore.issue_detail(repo, uuid, at=at)
        if detail is None:
            return None
        doc = IssueDoc.of(detail)
        return cls(
            path=path,
            key=doc.key,
            id=doc.id,
            title=doc.title,
            frontmatter=doc.frontmatter,
            branches=doc.branches,
            transitions=[IssueTransition(**t) for t in detail["transitions"]],
            content=detail["content"],
            shown_oid=detail["shown_oid"],
            shown_path=detail["shown_path"],
            shown_branch=detail["shown_branch"],
            at=at,
        )


@dataclass
class BlobView:
    path: str
    ref: str
    subpath: str
    size: int
    is_binary: bool
    content: str
    issue: IssueLink | None = None

    @classmethod
    def of(cls, repo, path: str, ref: str, subpath: str, found: dict) -> "BlobView":
        """`found` is the gitread.blob() read — passed in because the caller
        also serves it raw, and the bytes are read once."""
        badge = issuestore.issue_for_blob(repo, subpath, found["oid"])
        return cls(
            path=path,
            ref=ref,
            subpath=subpath,
            size=found["size"],
            is_binary=found["is_binary"],
            content=(
                "" if found["is_binary"] else found["data"].decode("utf-8", errors="replace")
            ),
            issue=IssueLink(**badge) if badge else None,
        )


@dataclass
class DiffStats:
    files_changed: int
    additions: int
    deletions: int


@dataclass
class LineCounts:
    additions: int
    deletions: int


@dataclass
class DiffColumn:
    """One parent column of the side-by-side view. `index` is the 1-based
    parent number `?parent=` selects, or None for a root commit's empty-tree
    column (which has no `sha` to link to)."""

    index: int | None
    sha: str
    short: str
    stats: DiffStats


@dataclass
class DiffCell:
    """One column's relation to a result line: `same` (identical), `changed`
    (cell carries the parent's own text), `absent` (no counterpart), or
    `removed` (a parent line the result dropped — `only` rows)."""

    status: str
    no: int | None = None
    text: str | None = None


@dataclass
class DiffRow:
    """One aligned row of the side-by-side view. kind `line` carries the
    plain result line plus one cell per column; `only` is parent-only content
    the result dropped; `fold` is a collapsed run of all-same rows.
    `merge_authored` marks rows matching NO parent — the merger's own work,
    and only ever set when there are two or more columns."""

    kind: str
    cells: list[DiffCell] = field(default_factory=list)
    result_no: int | None = None
    result_text: str | None = None
    merge_authored: bool = False
    count: int | None = None
    start: int | None = None
    end: int | None = None


@dataclass
class DiffFile:
    path: str
    old_paths: list[str]  # per column (renames may differ per side)
    statuses: list[str]  # per column: A/M/D/R/… or "=" (unchanged vs it)
    parent_counts: list[LineCounts]
    binary: bool
    truncated: bool
    rows: list[DiffRow]


@dataclass
class CommitDiff:
    """A commit's side-by-side diff — the one diff view. One column per
    parent (or per the single `?parent=`-selected one) plus the result."""

    sha: str
    short: str
    parents: list[str]  # every real parent, for the meta block and tabs
    author: str
    author_email: str
    committer: str
    committer_email: str
    date: str
    subject: str
    message: str
    path: str
    columns: list[DiffColumn]
    files: list[DiffFile]
    diff_parent: int | None  # the single parent selected, or None for all
    full: bool
    issues: list[IssueLink] = field(default_factory=list)

    @classmethod
    def of(
        cls, repo, path: str, sha: str, *, parent: int | None = None, full: bool = False
    ) -> "CommitDiff":
        """Raises gitread.GitReadError when the commit does not resolve."""
        detail = gitread.diff_detail(repo, sha, parent, full=full)
        return cls(
            sha=detail["sha"],
            short=detail["short"],
            parents=detail["parents"],
            author=detail["author"],
            author_email=detail["author_email"],
            committer=detail["committer"],
            committer_email=detail["committer_email"],
            date=detail["date"],
            subject=detail["subject"],
            message=detail["message"],
            path=path,
            columns=[
                DiffColumn(
                    index=c["index"],
                    sha=c["sha"],
                    short=c["short"],
                    stats=DiffStats(**c["stats"]),
                )
                for c in detail["columns"]
            ],
            issues=[IssueLink(**link) for link in issuestore.issues_for_commit(repo, sha)],
            files=[
                DiffFile(
                    path=f["path"],
                    old_paths=f["old_paths"],
                    statuses=f["statuses"],
                    parent_counts=[LineCounts(**c) for c in f["parent_counts"]],
                    binary=f["binary"],
                    truncated=f["truncated"],
                    rows=[
                        DiffRow(
                            kind=r["kind"],
                            cells=[DiffCell(**c) for c in r["cells"]],
                            result_no=r["result_no"],
                            result_text=r["result_text"],
                            merge_authored=r["merge_authored"],
                            count=r.get("count"),
                            start=r.get("start"),
                            end=r.get("end"),
                        )
                        for r in f["rows"]
                    ],
                )
                for f in detail["files"]
            ],
            diff_parent=detail["diff_parent"],
            full=full,
        )


@dataclass
class DocsPage:
    title: str


@dataclass
class NotFound:
    detail: str
    status: int = 404

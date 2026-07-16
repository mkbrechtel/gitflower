"""Typed response models — the JSON contract of every browse endpoint.

Plain dataclasses (FastAPI wraps them in pydantic for the OpenAPI schema, so
the 5-dependency rule holds). Each route declares its model as
`response_model`; the negotiated HTML page and fragment render from the same
`asdict()` data, so the three representations cannot drift apart.
"""

from dataclasses import dataclass, field

from gitflower.gitread import RepoInfo


@dataclass
class RepoList:
    """The overview and /repos/ listing."""

    repos: list[RepoInfo]
    warnings: list[str] = field(default_factory=list)


@dataclass
class OrgFolder:
    """Repositories under one organization folder."""

    org: str
    repos: list[RepoInfo]


@dataclass
class Branch:
    name: str
    sha: str
    short: str
    date: str
    subject: str


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


@dataclass
class RepoDetail:
    path: str
    branches: list[Branch]
    commits: list[Commit]
    graph: Graph
    full: bool
    total_shown: int
    clone_url: str


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


@dataclass
class IssueList:
    path: str
    default_branch: str | None
    branches: list[str]
    issues: list[IssueDoc]
    query: str | None = None
    branch: str | None = None


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


@dataclass
class BlobView:
    path: str
    ref: str
    subpath: str
    size: int
    is_binary: bool
    content: str
    issue: IssueLink | None = None


@dataclass
class FileDiff:
    path: str
    old_path: str
    status: str  # A/M/D/R/…
    additions: int
    deletions: int
    binary: bool
    patch: str


@dataclass
class DiffStats:
    files_changed: int
    additions: int
    deletions: int


@dataclass
class CommitDetail:
    sha: str
    short: str
    parents: list[str]
    author: str
    author_email: str
    committer: str
    committer_email: str
    date: str
    subject: str
    message: str
    files: list[FileDiff]
    stats: DiffStats
    patch: str
    path: str
    diff_parent: int = 1  # which parent (1-based) the diff is against
    issues: list[IssueLink] = field(default_factory=list)


@dataclass
class LineCounts:
    additions: int
    deletions: int


@dataclass
class MergeCell:
    """One parent's relation to a result line: `same` (identical), `changed`
    (cell carries the parent's own text), `absent` (no counterpart), or
    `removed` (a parent line the result dropped — `only` rows)."""

    status: str
    no: int | None = None
    text: str | None = None


@dataclass
class MergeRow:
    """One aligned row of the side-by-side view. kind `line` carries the
    plain result line plus one cell per parent; `only` is parent-only content
    the result dropped; `fold` is a collapsed run of all-same rows.
    `merge_authored` marks rows matching NO parent — the merger's own work."""

    kind: str
    cells: list[MergeCell] = field(default_factory=list)
    result_no: int | None = None
    result_text: str | None = None
    merge_authored: bool = False
    count: int | None = None
    start: int | None = None
    end: int | None = None


@dataclass
class MergeFile:
    path: str
    old_paths: list[str]  # per parent (renames may differ per side)
    statuses: list[str]  # per parent: A/M/D/R/… or "=" (unchanged vs it)
    parent_counts: list[LineCounts]
    binary: bool
    truncated: bool
    rows: list[MergeRow]


@dataclass
class MergeDetail:
    """A merge commit's side-by-side view: N parents, one resulting tree."""

    sha: str
    short: str
    parents: list[Commit]
    author: str
    author_email: str
    committer: str
    committer_email: str
    date: str
    subject: str
    message: str
    path: str
    parent_stats: list[DiffStats]
    files: list[MergeFile]
    full: bool


@dataclass
class DocsPage:
    title: str


@dataclass
class NotFound:
    detail: str
    status: int = 404

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
class BlobView:
    path: str
    ref: str
    subpath: str
    size: int
    is_binary: bool
    content: str


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


@dataclass
class DocsPage:
    title: str


@dataclass
class NotFound:
    detail: str
    status: int = 404

"""The browse routes: one explicit, typed FastAPI endpoint per view.

Repo paths nest (`org/team/app.git`), which Starlette's `{param:path}`
convertor expresses directly — it may sit mid-route, so `.git`-anchored
sub-routes (tree, commit, smart-HTTP) are ordinary typed routes and land in
the OpenAPI schema with their response models. Every endpoint builds its
typed model (web.models); respond() serves it as JSON, page, or fragment.

Every path component is slug-validated before it touches the filesystem —
a traversal attempt fails validation and 404s.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from gitflower import gitread, graph
from gitflower.config import GlobalConfig
from gitflower.slug import SlugError, validate_org_folder, validate_repo_path
from gitflower.web import fragments, models, smarthttp
from gitflower.web.respond import respond

GRAPH_LIMIT = 400
RECENT_COMMITS = 10

GIT_PROTOCOL_RESPONSES = {
    200: {"content": {"application/octet-stream": {}}, "description": "git protocol stream"},
    404: {"model": models.NotFound},
}


def _graph_model(g: dict) -> models.Graph:
    rows = [
        models.GraphRow(
            id=r["id"],
            kind=r["kind"],
            parents=r["parents"],
            row=r["row"],
            lane=r["lane"],
            x=r["x"],
            y=r["y"],
            color=r["color"],
            commit=models.Commit(**r["commit"]) if "commit" in r else None,
            count=r.get("count"),
            first=models.Commit(**r["first"]) if "first" in r else None,
            last=models.Commit(**r["last"]) if "last" in r else None,
        )
        for r in g["rows"]
    ]
    edges = [models.GraphEdge(**e) for e in g["edges"]]
    return models.Graph(
        rows=rows,
        edges=edges,
        width=g["width"],
        height=g["height"],
        row_height=g["row_height"],
        dot=g["dot"],
        collapsed=g["collapsed"],
    )


def build_router(cfg: GlobalConfig) -> APIRouter:
    router = APIRouter(responses={404: {"model": models.NotFound}})
    repos_dir = Path(cfg.repos.directory)

    def scan() -> gitread.ScanResult:
        return gitread.scan_repos(repos_dir, cfg.repos.scan_depth)

    def _validated(repo_path: str) -> str:
        try:
            return validate_repo_path(repo_path)
        except SlugError as exc:
            raise HTTPException(404, str(exc))

    def repo_or_404(repo_path: str):
        try:
            return gitread.open_repo(repos_dir, repo_path)
        except (SlugError, gitread.GitReadError) as exc:
            raise HTTPException(404, str(exc))

    @router.get("/", response_model=models.RepoList, summary="Overview: all repositories")
    def index(request: Request) -> Response:
        result = scan()
        data = models.RepoList(repos=result.repos, warnings=result.warnings)
        return respond(request, data, fragments.index, "overview")

    @router.get("/repos/", response_model=models.RepoList, summary="Repository list")
    def repo_list(request: Request) -> Response:
        result = scan()
        data = models.RepoList(repos=result.repos, warnings=result.warnings)
        return respond(request, data, fragments.repo_list, "repositories")

    @router.get("/docs/", response_model=models.DocsPage, summary="Documentation")
    def docs(request: Request) -> Response:
        return respond(request, models.DocsPage(title="documentation"), fragments.docs, "docs")

    @router.get(
        "/repos/{repo_path:path}/info/refs",
        summary="git smart-HTTP ref advertisement (read-only)",
        responses=GIT_PROTOCOL_RESPONSES,
    )
    def info_refs(repo_path: str, service: str | None = None) -> Response:
        repo_path = _validated(repo_path)
        repo_or_404(repo_path)
        return smarthttp.advertisement(repos_dir / repo_path, service)

    @router.post(
        "/repos/{repo_path:path}/git-upload-pack",
        summary="git smart-HTTP upload-pack (read-only clone/fetch)",
        responses=GIT_PROTOCOL_RESPONSES,
    )
    async def upload_pack(repo_path: str, request: Request) -> Response:
        repo_path = _validated(repo_path)
        repo_or_404(repo_path)
        return await smarthttp.upload_pack(repos_dir / repo_path, request)

    def _tree_or_blob(request: Request, repo_path: str, refpath: str) -> Response:
        repo = repo_or_404(_validated(repo_path))
        wants_dir = refpath.endswith("/") or refpath == ""
        try:
            ref, subpath = gitread.split_ref(repo, refpath.strip("/")) if refpath.strip("/") else ("HEAD", "")
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        wants_dir = wants_dir or subpath == ""
        try:
            if wants_dir:
                entries = [
                    models.TreeEntry(**entry) for entry in gitread.tree_entries(repo, ref, subpath)
                ]
                data = models.TreeView(path=repo_path, ref=ref, subpath=subpath, entries=entries)
                return respond(request, data, fragments.tree, f"{repo_path}: {subpath or '/'}")
            found = gitread.blob(repo, ref, subpath)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        raw = found["data"]
        if request.query_params.get("format") == "raw":
            if found["is_binary"]:
                return Response(raw, media_type="application/octet-stream")
            return PlainTextResponse(raw)
        data = models.BlobView(
            path=repo_path,
            ref=ref,
            subpath=subpath,
            size=found["size"],
            is_binary=found["is_binary"],
            content="" if found["is_binary"] else raw.decode("utf-8", errors="replace"),
        )
        return respond(request, data, fragments.blob, f"{repo_path}: {subpath}")

    @router.get(
        "/repos/{repo_path:path}/tree/{refpath:path}",
        response_model=models.TreeView | models.BlobView,
        summary="Tree listing (trailing slash) or file view; ?format=raw for bytes. "
        "Refs may contain slashes — the longest prefix that resolves to a ref wins.",
    )
    def tree(request: Request, repo_path: str, refpath: str) -> Response:
        return _tree_or_blob(request, repo_path, refpath)

    @router.get(
        "/repos/{repo_path:path}/commit/{sha}",
        response_model=models.CommitDetail | models.MergeDetail,
        summary="Commit detail: metadata, diffstat, per-file diffs. A merge "
        "commit defaults to the side-by-side per-parent view (?full=1 unfolds "
        "unchanged runs); ?parent=N selects the plain diff against one parent.",
    )
    def commit(
        request: Request, repo_path: str, sha: str, parent: int | None = None, full: bool = False
    ) -> Response:
        repo = repo_or_404(_validated(repo_path))
        try:
            if parent is None and len(gitread.resolve(repo, sha).parents) > 1:
                return _merge_view(request, repo, repo_path, sha, full)
            detail = gitread.commit_detail(repo, sha, parent)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        data = models.CommitDetail(
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
            files=[models.FileDiff(**f) for f in detail["files"]],
            stats=models.DiffStats(**detail["stats"]),
            patch=detail["patch"],
            path=repo_path,
            diff_parent=detail["diff_parent"],
        )
        return respond(request, data, fragments.commit, f"{repo_path}: {detail['short']}")

    def _merge_view(
        request: Request, repo, repo_path: str, sha: str, full: bool
    ) -> Response:
        detail = gitread.merge_detail(repo, sha, full=full)
        data = models.MergeDetail(
            sha=detail["sha"],
            short=detail["short"],
            parents=[models.Commit(**p) for p in detail["parent_commits"]],
            author=detail["author"],
            author_email=detail["author_email"],
            committer=detail["committer"],
            committer_email=detail["committer_email"],
            date=detail["date"],
            subject=detail["subject"],
            message=detail["message"],
            path=repo_path,
            parent_stats=[models.DiffStats(**s) for s in detail["parent_stats"]],
            files=[
                models.MergeFile(
                    path=f["path"],
                    old_paths=f["old_paths"],
                    statuses=f["statuses"],
                    parent_counts=[models.LineCounts(**c) for c in f["parent_counts"]],
                    binary=f["binary"],
                    truncated=f["truncated"],
                    rows=[
                        models.MergeRow(
                            kind=r["kind"],
                            cells=[models.MergeCell(**c) for c in r["cells"]],
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
            full=full,
        )
        return respond(request, data, fragments.merge, f"{repo_path}: {detail['short']}")

    @router.get(
        "/repos/{rest:path}",
        response_model=models.RepoDetail | models.OrgFolder,
        summary="Repository detail (…/name.git: branches, commit graph) or organization folder",
    )
    def repo_or_org(request: Request, rest: str, full: bool = False) -> Response:
        rest = rest.rstrip("/")
        if rest.endswith(".git"):
            return _repo_detail(request, _validated(rest), full)
        return _org_view(request, rest)

    def _repo_detail(request: Request, repo_path: str, full: bool) -> Response:
        repo = repo_or_404(repo_path)
        commits = gitread.commits(repo, GRAPH_LIMIT)
        branches = [models.Branch(**b) for b in gitread.branches(repo)]
        laid_out = graph.build(commits, {b.sha for b in branches}, collapse=not full)
        data = models.RepoDetail(
            path=repo_path,
            branches=branches,
            commits=[models.Commit(**c) for c in commits[:RECENT_COMMITS]],
            graph=_graph_model(laid_out),
            full=full,
            total_shown=len(commits),
            clone_url=str(request.base_url) + f"repos/{repo_path}",
        )
        return respond(request, data, fragments.repo, repo_path)

    def _org_view(request: Request, org_path: str) -> Response:
        for part in org_path.split("/"):
            try:
                validate_org_folder(part)
            except SlugError as exc:
                raise HTTPException(404, str(exc))
        if not (repos_dir / org_path).is_dir():
            raise HTTPException(404, f"no such organization folder: {org_path}")
        inside = [r for r in scan().repos if r.path.startswith(org_path + "/")]
        data = models.OrgFolder(org=org_path, repos=inside)
        return respond(request, data, fragments.org, org_path)

    return router

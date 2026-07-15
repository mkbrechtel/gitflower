"""The browse routes. `/repos/...` is one dispatcher, Go-style: repo paths
nest (`org/team/app.git`) and carry `.git`-anchored sub-routes (tree, commit,
smart-HTTP), which FastAPI's fixed path templates cannot express.

Every path component is slug-validated before it touches the filesystem —
a traversal attempt fails validation and 404s.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from gitflower import gitread, graph
from gitflower.config import GlobalConfig
from gitflower.slug import SlugError, validate_org_folder, validate_repo_path
from gitflower.web import fragments, smarthttp
from gitflower.web.respond import respond

GRAPH_LIMIT = 400
RECENT_COMMITS = 10


def build_router(cfg: GlobalConfig) -> APIRouter:
    router = APIRouter()
    repos_dir = Path(cfg.repos.directory)

    def scan() -> gitread.ScanResult:
        return gitread.scan_repos(repos_dir, cfg.repos.scan_depth)

    def repo_or_404(repo_path: str):
        try:
            return gitread.open_repo(repos_dir, repo_path)
        except (SlugError, gitread.GitReadError) as exc:
            raise HTTPException(404, str(exc))

    @router.get("/", summary="Overview: all repositories")
    def index(request: Request) -> Response:
        result = scan()
        data = {"repos": [vars(r) for r in result.repos], "warnings": result.warnings}
        return respond(request, data, fragments.index, "overview")

    @router.get("/repos/", summary="Repository list")
    def repo_list(request: Request) -> Response:
        result = scan()
        data = {"repos": [vars(r) for r in result.repos], "warnings": result.warnings}
        return respond(request, data, fragments.repo_list, "repositories")

    @router.get("/docs/", summary="Documentation")
    def docs(request: Request) -> Response:
        return respond(request, {"title": "documentation"}, fragments.docs, "docs")

    def repo_detail(request: Request, repo_path: str) -> Response:
        repo = repo_or_404(repo_path)
        full = request.query_params.get("full") == "1"
        commits = gitread.commits(repo, GRAPH_LIMIT)
        branches = gitread.branches(repo)
        data = {
            "path": repo_path,
            "branches": branches,
            "commits": commits[:RECENT_COMMITS],
            "graph": graph.build(commits, {b["sha"] for b in branches}, collapse=not full),
            "full": full,
            "total_shown": len(commits),
            "clone_url": str(request.base_url) + f"repos/{repo_path}",
        }
        return respond(request, data, fragments.repo, repo_path)

    def org_view(request: Request, org_path: str) -> Response:
        for part in org_path.split("/"):
            try:
                validate_org_folder(part)
            except SlugError as exc:
                raise HTTPException(404, str(exc))
        if not (repos_dir / org_path).is_dir():
            raise HTTPException(404, f"no such organization folder: {org_path}")
        result = scan()
        inside = [r for r in result.repos if r.path.startswith(org_path + "/")]
        data = {"org": org_path, "repos": [vars(r) for r in inside]}
        return respond(request, data, fragments.org, org_path)

    def tree_or_blob(request: Request, repo_path: str, subref: str) -> Response:
        repo = repo_or_404(repo_path)
        ref, _, subpath = subref.partition("/")
        ref = ref or "HEAD"
        wants_dir = subpath.endswith("/") or subpath == ""
        subpath = subpath.strip("/")
        try:
            if wants_dir:
                entries = gitread.tree_entries(repo, ref, subpath)
                data = {"path": repo_path, "ref": ref, "subpath": subpath, "entries": entries}
                return respond(request, data, fragments.tree, f"{repo_path}: {subpath or '/'}")
            found = gitread.blob(repo, ref, subpath)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        raw = found["data"]
        if request.query_params.get("format") == "raw":
            if found["is_binary"]:
                return Response(raw, media_type="application/octet-stream")
            return PlainTextResponse(raw)
        content = "" if found["is_binary"] else raw.decode("utf-8", errors="replace")
        data = {
            "path": repo_path,
            "ref": ref,
            "subpath": subpath,
            "size": found["size"],
            "is_binary": found["is_binary"],
            "content": content,
        }
        return respond(request, data, fragments.blob, f"{repo_path}: {subpath}")

    def commit_view(request: Request, repo_path: str, sha: str) -> Response:
        repo = repo_or_404(repo_path)
        try:
            detail = gitread.commit_detail(repo, sha)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        detail["path"] = repo_path
        return respond(request, detail, fragments.commit, f"{repo_path}: {detail['short']}")

    @router.get("/repos/{rest:path}", summary="Repository browser (dispatcher)")
    async def repos_dispatch(request: Request, rest: str) -> Response:
        rest = rest.rstrip("/") if rest.endswith("/") and ".git" not in rest else rest

        # smart-HTTP first: <repo>.git/info/refs and <repo>.git/git-upload-pack
        if rest.endswith("/info/refs"):
            repo_path = _validated(rest.removesuffix("/info/refs"))
            repo_or_404(repo_path)
            return smarthttp.advertisement(
                repos_dir / repo_path, request.query_params.get("service")
            )

        if ".git/tree/" in rest:
            repo_path, _, subref = rest.partition(".git/tree/")
            return tree_or_blob(request, _validated(repo_path + ".git"), subref)

        if ".git/commit/" in rest:
            repo_path, _, sha = rest.partition(".git/commit/")
            return commit_view(request, _validated(repo_path + ".git"), sha)

        if rest.endswith(".git"):
            return repo_detail(request, _validated(rest))

        return org_view(request, rest.strip("/"))

    @router.post("/repos/{rest:path}", summary="git smart-HTTP upload-pack")
    async def repos_post(request: Request, rest: str) -> Response:
        if not rest.endswith(f"/{smarthttp.UPLOAD_PACK}"):
            raise HTTPException(404, "not found")
        repo_path = _validated(rest.removesuffix(f"/{smarthttp.UPLOAD_PACK}"))
        repo_or_404(repo_path)
        return await smarthttp.upload_pack(repos_dir / repo_path, request)

    def _validated(repo_path: str) -> str:
        try:
            return validate_repo_path(repo_path)
        except SlugError as exc:
            raise HTTPException(404, str(exc))

    return router

"""The browse routes: one explicit, typed FastAPI endpoint per view.

Repo paths nest (`org/team/app.git`), which Starlette's `{param:path}`
convertor expresses directly — it may sit mid-route, so `.git`-anchored
sub-routes (tree, commit, smart-HTTP) are ordinary typed routes and land in
the OpenAPI schema with their response models. Every endpoint builds its
typed model (gitflower.models); respond() serves it as JSON, page, or fragment.

Every path component is slug-validated before it touches the filesystem —
a traversal attempt fails validation and 404s.
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from gitflower import gitread, issues as issuestore, models
from gitflower.config import (
    ConfigError,
    GlobalConfig,
    RepoConfig,
    default_repo_config,
    load_repo_config,
)
from gitflower.slug import SlugError, validate_org_folder, validate_repo_path
from gitflower.web import fragments, smarthttp
from gitflower.web.respond import respond

GIT_PROTOCOL_RESPONSES = {
    200: {"content": {"application/octet-stream": {}}, "description": "git protocol stream"},
    404: {"model": models.NotFound},
}


def build_router(cfg: GlobalConfig) -> APIRouter:
    router = APIRouter(responses={404: {"model": models.NotFound}})
    repos_dir = Path(cfg.repos.directory)

    def scan() -> gitread.ScanResult:
        return gitread.scan_repos(repos_dir, cfg.repos.scan_depth)

    def _repo_config(repo) -> RepoConfig:
        """A repo's own gitflower settings; a broken config falls back to the
        defaults rather than taking the whole page down — the web UI displays,
        it does not enforce, and the hook is where a bad config must be loud."""
        try:
            return load_repo_config(repo.path)
        except ConfigError:
            return default_repo_config()

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
        return respond(request, models.RepoList.of(scan()), fragments.index, "overview")

    @router.get("/repos/", response_model=models.RepoList, summary="Repository list")
    def repo_list(request: Request) -> Response:
        return respond(request, models.RepoList.of(scan()), fragments.repo_list, "repositories")

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
                data = models.TreeView.of(repo, repo_path, ref, subpath)
                return respond(request, data, fragments.tree, f"{repo_path}: {subpath or '/'}")
            found = gitread.blob(repo, ref, subpath)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        raw = found["data"]
        if request.query_params.get("format") == "raw":
            if found["is_binary"]:
                return Response(raw, media_type="application/octet-stream")
            return PlainTextResponse(raw)
        data = models.BlobView.of(repo, repo_path, ref, subpath, found)
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
        response_model=models.CommitDiff,
        summary="Commit detail: metadata and the side-by-side diff — one "
        "column per parent plus the result (?full=1 unfolds unchanged runs). "
        "?parent=N narrows a merge to a single parent's column.",
    )
    def commit(
        request: Request, repo_path: str, sha: str, parent: int | None = None, full: bool = False
    ) -> Response:
        repo = repo_or_404(_validated(repo_path))
        try:
            data = models.CommitDiff.of(repo, repo_path, sha, parent=parent, full=full)
        except gitread.GitReadError as exc:
            raise HTTPException(404, str(exc))
        return respond(request, data, fragments.commit, f"{repo_path}: {data.short}")

    @router.get(
        "/repos/{repo_path:path}/branches/",
        response_model=models.BranchList,
        summary="Branch list: tips, dates and subjects. ?hidden=1 includes the "
        "branches the repository's config hides.",
    )
    def branch_list(request: Request, repo_path: str, hidden: bool = False) -> Response:
        repo_path = _validated(repo_path)
        repo = repo_or_404(repo_path)
        data = models.BranchList.of(repo, repo_path, _repo_config(repo), show_hidden=hidden)
        return respond(request, data, fragments.branches, f"{repo_path}: branches")

    @router.get(
        "/repos/{repo_path:path}/mrs/",
        response_model=models.MrList,
        summary="Merge requests: the empty `MR: …` commits offered for merging, "
        "with the state derived from the graph. ?state= filters.",
    )
    def mr_list(request: Request, repo_path: str, state: str | None = None) -> Response:
        repo_path = _validated(repo_path)
        repo = repo_or_404(repo_path)
        data = models.MrList.of(repo, repo_path, state=state)
        return respond(request, data, fragments.mr_list, f"{repo_path}: merge requests")

    @router.get(
        "/repos/{repo_path:path}/mrs/{oid}",
        response_model=models.MrDetail,
        summary="One merge request by its id — the SHA of its request commit, "
        "abbreviated or in full — with the line of work it offers.",
    )
    def mr_detail(request: Request, repo_path: str, oid: str) -> Response:
        repo_path = _validated(repo_path)
        if not re.fullmatch(r"[0-9a-f]{4,40}", oid):
            raise HTTPException(404, f"not a merge request id: {oid}")
        repo = repo_or_404(repo_path)
        data = models.MrDetail.of(repo, repo_path, oid)
        if data is None:
            raise HTTPException(404, f"no merge request {oid}")
        return respond(request, data, fragments.mr_detail, f"{repo_path}: {data.short}")

    @router.get(
        "/repos/{repo_path:path}/issues/",
        response_model=models.IssueList,
        summary="Issues across branches: markdown files under the issues directory, "
        "one document per id, each branch's version classified against the "
        "default branch. ?q=<JMESPath> filters the documents; ?branch= scopes.",
    )
    def issue_list(
        request: Request, repo_path: str, q: str | None = None, branch: str | None = None
    ) -> Response:
        repo = repo_or_404(_validated(repo_path))
        try:
            model = models.IssueList.of(repo, repo_path, q=q, branch=branch)
        except issuestore.QueryError as exc:
            raise HTTPException(400, str(exc))
        return respond(request, model, fragments.issues, f"{repo_path}: issues")

    @router.get(
        "/repos/{repo_path:path}/issues/{uuid}",
        response_model=models.IssueDetail,
        summary="One issue by its id: versions per branch, transition history, "
        "and the shown version's content. ?at=<commit> pins the version.",
    )
    def issue_detail(
        request: Request, repo_path: str, uuid: str, at: str | None = None
    ) -> Response:
        repo = repo_or_404(_validated(repo_path))
        model = models.IssueDetail.of(repo, repo_path, uuid, at=at)
        if model is None:
            raise HTTPException(404, f"no issue with id {uuid}" + (f" at {at}" if at else ""))
        return respond(request, model, fragments.issue, f"{repo_path}: {model.title}")

    @router.get(
        "/repos/{rest:path}",
        response_model=models.RepoDetail | models.OrgFolder,
        summary="Repository detail (…/name.git: branches, commit graph) or organization folder",
    )
    def repo_or_org(
        request: Request, rest: str, full: bool = False, hidden: bool = False
    ) -> Response:
        rest = rest.rstrip("/")
        if rest.endswith(".git"):
            return _repo_detail(request, _validated(rest), full, hidden)
        return _org_view(request, rest)

    def _repo_detail(
        request: Request, repo_path: str, full: bool, show_hidden: bool
    ) -> Response:
        repo = repo_or_404(repo_path)
        data = models.RepoDetail.of(
            repo,
            repo_path,
            _repo_config(repo),
            full=full,
            show_hidden=show_hidden,
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
        return respond(request, models.OrgFolder.of(org_path, scan()), fragments.org, org_path)

    return router

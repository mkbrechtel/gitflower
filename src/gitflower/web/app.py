"""FastAPI application factory."""

from importlib import resources

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from gitflower import __version__
from gitflower.config import GlobalConfig
from gitflower.web import fragments
from gitflower.web.respond import respond
from gitflower.web.routes import build_router


def create_app(cfg: GlobalConfig | None = None) -> FastAPI:
    cfg = cfg or GlobalConfig()
    app = FastAPI(
        title="gitflower",
        version=__version__,
        description=(
            "The gitflower web API — which is also the frontend: every "
            "endpoint serves JSON, a full HTML page, and an HTML fragment "
            "from the same URL via content negotiation."
        ),
        docs_url=None,  # /api is served below, wrapped in the site chrome
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.cfg = cfg
    app.include_router(build_router(cfg))

    # Swagger UI inside the same page chrome as every other view. The assets
    # are the ones FastAPI's stock docs page uses (swagger-ui-dist via CDN);
    # swagger renders in the light DOM — its JS looks elements up by id, so
    # it does not go through the shadow-DOM view wrapper.
    swagger_body = """
<style>
.swagger-wrap { background: #fff; border-radius: 8px; border: 1px solid var(--border); }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<div class="swagger-wrap"><div id="swagger-ui"></div></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: "/api/openapi.json",
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset].filter(Boolean),
  layout: "BaseLayout",
  deepLinking: true,
});
</script>
"""

    @app.get("/api", include_in_schema=False)
    async def api_docs() -> Response:
        from gitflower.web.html import page

        return Response(page("API", swagger_body), media_type="text/html")

    static = resources.files("gitflower.web") / "static"
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.exception_handler(StarletteHTTPException)
    async def not_found(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code != 404:
            return Response(str(exc.detail), status_code=exc.status_code)
        data = {"detail": str(exc.detail) or str(request.url.path), "status": 404}
        return respond(request, data, fragments.not_found, "not found", status=404)

    return app

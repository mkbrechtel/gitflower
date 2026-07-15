"""Content negotiation: the API is the frontend.

Every browse endpoint serves the same data three ways from one URL:

* JSON            — Accept: application/json, or ?format=json
* HTML fragment   — GF-Fragment: 1 request header (set by the web
                    components), or ?format=fragment
* full HTML page  — everything else (browser navigation), or ?format=html
"""

from typing import Callable

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

FRAGMENT_HEADER = "gf-fragment"


def wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    for part in accept.split(","):
        media = part.split(";")[0].strip()
        if media == "application/json":
            return True
        if media in ("text/html", "*/*"):
            return False
    return False


def respond(
    request: Request,
    data: dict,
    fragment_fn: Callable[[dict], str],
    title: str,
    status: int = 200,
) -> Response:
    fmt = request.query_params.get("format")
    if fmt == "json" or (fmt is None and wants_json(request)):
        return JSONResponse(data, status_code=status)
    if fmt == "fragment" or (
        fmt is None and request.headers.get(FRAGMENT_HEADER) == "1"
    ):
        return HTMLResponse(fragment_fn(data), status_code=status)
    from gitflower.web.html import page

    return HTMLResponse(page(title, fragment_fn(data)), status_code=status)

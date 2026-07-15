"""Read-only git smart-HTTP: real clones, no pushes.

Both endpoints shell out to `git upload-pack --stateless-rpc` — receive-pack
is never spawned, so the transport is read-only by construction (the Go
original stubbed this with a 501; cloning actually works here).
"""

import gzip
import subprocess
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response

UPLOAD_PACK = "git-upload-pack"


def _pkt_line(data: bytes) -> bytes:
    return f"{len(data) + 4:04x}".encode() + data


def advertisement(repo_dir: Path, service: str | None) -> Response:
    if service != UPLOAD_PACK:
        # dumb protocol or a push probe; both are refused
        raise HTTPException(403, "only git-upload-pack is supported (read-only)")
    result = subprocess.run(
        ["git", "upload-pack", "--stateless-rpc", "--advertise-refs", str(repo_dir)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise HTTPException(500, result.stderr.decode(errors="replace"))
    body = _pkt_line(f"# service={UPLOAD_PACK}\n".encode()) + b"0000" + result.stdout
    return Response(
        content=body,
        media_type=f"application/x-{UPLOAD_PACK}-advertisement",
        headers={"Cache-Control": "no-cache"},
    )


async def upload_pack(repo_dir: Path, request: Request) -> Response:
    body = await request.body()
    if request.headers.get("content-encoding") == "gzip":
        body = gzip.decompress(body)
    result = subprocess.run(
        ["git", "upload-pack", "--stateless-rpc", str(repo_dir)],
        input=body,
        capture_output=True,
    )
    if result.returncode != 0:
        raise HTTPException(500, result.stderr.decode(errors="replace"))
    return Response(
        content=result.stdout,
        media_type=f"application/x-{UPLOAD_PACK}-result",
        headers={"Cache-Control": "no-cache"},
    )

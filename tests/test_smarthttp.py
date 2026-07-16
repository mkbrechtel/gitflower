"""Read-only smart-HTTP clone endpoints."""

import pytest
from fastapi.testclient import TestClient

from gitflower import gitread
from gitflower.config import GlobalConfig, ReposConfig
from gitflower.web.app import create_app
from tests.conftest import git


@pytest.fixture
def hosted(tmp_path):
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    (work / "README.md").write_text("hello\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "initial")
    git(work, "push", "origin", "main")
    return root


@pytest.fixture
def client(hosted):
    cfg = GlobalConfig(repos=ReposConfig(directory=str(hosted)))
    return TestClient(create_app(cfg))


def test_advertisement_pkt_line_framing(client):
    response = client.get("/repos/app.git/info/refs?service=git-upload-pack")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-git-upload-pack-advertisement"
    body = response.content
    # first pkt-line: length-prefixed "# service=git-upload-pack\n", then flush
    first = b"# service=git-upload-pack\n"
    assert body.startswith(f"{len(first) + 4:04x}".encode() + first + b"0000")
    assert b"refs/heads/main" in body


def test_other_services_are_refused(client):
    assert (
        client.get("/repos/app.git/info/refs?service=git-receive-pack").status_code == 403
    )
    assert client.get("/repos/app.git/info/refs").status_code == 403


def test_advertisement_for_missing_repo_is_404(client):
    assert client.get("/repos/ghost.git/info/refs?service=git-upload-pack").status_code == 404


def test_upload_pack_stateless_rpc(client, hosted):
    """A real want/done exchange through the POST endpoint returns a pack."""
    import pygit2

    repo = pygit2.Repository(str(hosted / "app.git"))
    tip = str(repo.branches.local["main"].target)
    want = f"want {tip} multi_ack_detailed side-band-64k agent=gitflower-test\n"
    body = (
        f"{len(want) + 4:04x}".encode() + want.encode()
        + b"0000"
        + b"0009done\n"
    )
    response = client.post(
        "/repos/app.git/git-upload-pack",
        content=body,
        headers={"Content-Type": "application/x-git-upload-pack-request"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-git-upload-pack-result"
    assert b"PACK" in response.content  # a packfile came back


def test_live_clone(hosted, tmp_path):
    """Full `git clone` against a live uvicorn — the end-to-end proof."""
    import socket
    import subprocess
    import sys
    import time

    from tests.conftest import SRC

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    config = tmp_path / "config.yaml"
    config.write_text(
        f"repos:\n  directory: {hosted}\nweb:\n  address: 127.0.0.1:{port}\n"
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "gitflower", "--config", str(config), "web"],
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(SRC),
            "http_proxy": "",
            "https_proxy": "",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        clone = tmp_path / "cloned"
        result = subprocess.run(
            [
                "git",
                "-c",
                "http.proxy=",
                "clone",
                f"http://127.0.0.1:{port}/repos/app.git",
                str(clone),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert (clone / "README.md").read_text() == "hello\n"
        # and pushing is refused: receive-pack is never spawned
        push = subprocess.run(
            ["git", "-C", str(clone), "-c", "http.proxy=", "push", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert push.returncode != 0
    finally:
        server.terminate()
        server.wait(timeout=10)

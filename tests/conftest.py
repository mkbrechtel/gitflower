"""Hermetic git environment for the whole suite.

Every git subprocess and pygit2 call must be isolated from the developer's
real configuration — hooks and workflow checks shell out to git, and a
signing or fsmonitor setting from ~/.gitconfig would leak into assertions.
"""

import os
import subprocess
from pathlib import Path

import pytest

# wherever the gitflower package under test actually lives — src/ in a dev
# checkout, pybuild's build dir during a package build
import gitflower

SRC = Path(gitflower.__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def git_env(tmp_path_factory):
    home = tmp_path_factory.mktemp("home")
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_AUTHOR_DATE": "2026-01-02T03:04:05+00:00",
        "GIT_COMMITTER_DATE": "2026-01-02T03:04:05+00:00",
        # tripwire: anything that tries the network fails fast
        "http_proxy": "http://127.0.0.1:9/",
        "https_proxy": "http://127.0.0.1:9/",
        "no_proxy": "",
    }
    old = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    os.environ.pop("GITFLOWER_CONFIG", None)
    yield
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check
    )


@pytest.fixture
def work_repo(tmp_path):
    """A live repository with one commit on main."""
    repo = tmp_path / "work"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "README.md").write_text("hello\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
def bare_repo(tmp_path):
    """A bare repository, standing alone — where per-repo config lives."""
    repo = tmp_path / "bare.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(repo))
    return repo


@pytest.fixture
def bare_remote(tmp_path, work_repo):
    """A bare remote wired up as `origin` of work_repo."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    git(work_repo, "remote", "add", "origin", str(remote))
    return remote


@pytest.fixture
def gitflower_bin(tmp_path):
    """A wrapper script standing in for the installed console script.

    The hook shim invokes $GITFLOWER_BIN; during tests the package is not
    installed, so the wrapper runs `python3 -m gitflower` with src/ on path.
    """
    import sys

    wrapper = tmp_path / "bin" / "gitflower"
    wrapper.parent.mkdir()
    wrapper.write_text(
        "#!/bin/sh\n"
        f'PYTHONPATH="{SRC}" exec "{sys.executable}" -m gitflower "$@"\n'
    )
    wrapper.chmod(0o755)
    return wrapper

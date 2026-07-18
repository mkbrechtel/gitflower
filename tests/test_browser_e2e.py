"""Browser end-to-end tests: selenium + system chromium (headless).

Debian carries no python3-playwright; python3-selenium + chromium-driver is
the apt-only substitute. Excluded from the default run and from package
builds (pyproject deselects the e2e marker); run with `pytest -m e2e`.
"""

import socket
import subprocess
import sys
import time

import pytest

from gitflower import gitread
from tests.conftest import SRC, git

pytestmark = pytest.mark.e2e

selenium = pytest.importorskip("selenium")


@pytest.fixture(scope="module", autouse=True)
def localhost_unproxied():
    """The suite-wide proxy tripwire must not catch selenium↔chromedriver
    (and browser↔uvicorn) traffic — everything here is loopback."""
    import os

    old = os.environ.get("no_proxy")
    os.environ["no_proxy"] = "localhost,127.0.0.1"
    yield
    os.environ["no_proxy"] = old if old is not None else ""

from selenium.webdriver import Chrome, ChromeOptions  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

CHROMIUM = "/usr/bin/chromium"
CHROMEDRIVER = "/usr/bin/chromedriver"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("e2e")
    root = tmp_path / "repos"
    root.mkdir()
    gitread.create_repository(root, "app.git")
    work = tmp_path / "seed"
    git(tmp_path, "clone", str(root / "app.git"), str(work))
    git(work, "checkout", "-b", "main")
    for n in range(8):
        (work / "README.md").write_text(f"revision {n}\n")
        git(work, "add", ".")
        git(work, "commit", "-m", f"commit {n}")
    git(work, "push", "origin", "main")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = tmp_path / "config.yaml"
    config.write_text(f"repos:\n  directory: {root}\nweb:\n  address: 127.0.0.1:{port}\n")
    import os

    proc = subprocess.Popen(
        [sys.executable, "-m", "gitflower", "--config", str(config), "web"],
        env={**os.environ, "PYTHONPATH": str(SRC), "http_proxy": "", "https_proxy": ""},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser(server):
    options = ChromeOptions()
    options.binary_location = CHROMIUM  # Debian's system chromium
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = Chrome(options=options, service=Service(executable_path=CHROMEDRIVER))
    driver.set_window_size(1280, 900)
    yield driver
    driver.quit()


def shadow_text(driver) -> str:
    """All text across the open shadow roots on the page."""
    return driver.execute_script(
        "return [...document.querySelectorAll('gf-view')]"
        ".map(v => v.shadowRoot ? v.shadowRoot.textContent : '').join(' ')"
    )


def test_spa_navigation_swaps_fragments(browser, server):
    browser.get(server + "/")
    WebDriverWait(browser, 5).until(lambda d: "app.git" in shadow_text(d))

    # click through to the repo page — the URL changes, the chrome stays
    browser.execute_script(
        "document.querySelector('gf-view').shadowRoot"
        ".querySelector('a[href=\"/repos/app.git\"]').click()"
    )
    WebDriverWait(browser, 5).until(lambda d: d.current_url.endswith("/repos/app.git"))
    WebDriverWait(browser, 5).until(lambda d: "Clone (read-only)" in shadow_text(d))

    # back button re-fetches the previous fragment
    browser.back()
    WebDriverWait(browser, 5).until(lambda d: d.current_url.rstrip("/") == server)
    WebDriverWait(browser, 5).until(lambda d: "Repositories" in shadow_text(d))


def test_graph_renders_and_folds(browser, server):
    browser.get(server + "/repos/app.git")
    WebDriverWait(browser, 5).until(
        lambda d: d.execute_script(
            "const v = document.querySelector('gf-view');"
            "return v && v.shadowRoot && !!v.shadowRoot.querySelector('.graph-svg')"
        )
    )
    assert "⋯" in shadow_text(browser)  # linear stretch folded


def test_graph_hover_highlights_lane(browser, server):
    browser.get(server + "/repos/app.git")
    WebDriverWait(browser, 5).until(
        lambda d: d.execute_script(
            "const v = document.querySelector('gf-view');"
            "return v && v.shadowRoot && !!v.shadowRoot.querySelector('.graph-row')"
        )
    )
    focused = browser.execute_script(
        "const root = document.querySelector('gf-view').shadowRoot;"
        "const row = root.querySelector('.graph-row');"
        "row.dispatchEvent(new Event('mouseenter'));"
        "return root.querySelector('.graph-svg').classList.contains('focused');"
    )
    assert focused


def test_theme_palette_is_active(browser, server):
    browser.get(server + "/")
    accent = browser.execute_script(
        "return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()"
    )
    assert accent  # the palette custom properties are live


PATCH_WHITE_SPACE = (
    "const v = document.querySelector('gf-view');"
    "const p = v && v.shadowRoot && v.shadowRoot.querySelector('pre.patch');"
    "return p ? getComputedStyle(p).whiteSpace : null"
)


def test_full_width_and_wrap_toggle(browser, server):
    browser.get(server + "/repos/app.git")
    WebDriverWait(browser, 5).until(
        lambda d: d.execute_script(
            "const v = document.querySelector('gf-view');"
            "return v && v.shadowRoot && !!v.shadowRoot.querySelector('.graph-sha')"
        )
    )
    # the page uses the whole viewport width
    assert browser.execute_script(
        "return document.getElementById('gf-main').getBoundingClientRect().width"
        " === document.documentElement.clientWidth"
    )

    # a commit's patch soft-wraps by default
    browser.execute_script(
        "document.querySelector('gf-view').shadowRoot.querySelector('.graph-sha').click()"
    )
    WebDriverWait(browser, 5).until(
        lambda d: d.execute_script(PATCH_WHITE_SPACE) == "pre-wrap"
    )

    # the JS-revealed toggle switches to horizontal scrolling…
    browser.execute_script(
        "const root = document.querySelector('gf-view').shadowRoot;"
        "root.querySelector('.wrap-toggle input').click()"
    )
    WebDriverWait(browser, 5).until(lambda d: d.execute_script(PATCH_WHITE_SPACE) == "pre")

    # …and the choice survives a full page load
    browser.refresh()
    WebDriverWait(browser, 5).until(lambda d: d.execute_script(PATCH_WHITE_SPACE) == "pre")
    browser.execute_script("localStorage.removeItem('gf-wrap')")

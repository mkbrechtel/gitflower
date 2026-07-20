"""The repository chrome: breadcrumbs and the section tabs.

A presentation primitive that sits below the view fragments — fragments
import it, nothing imports a fragment. It renders `models.TABS`, so the
sections a repository has are defined once and every surface reads that one
list; only which tab is current is decided here, per page.

The bar is emitted inside the fragment rather than in the page chrome
(html.page) on purpose: the SPA loader swaps `#gf-main` and never re-renders
the chrome, so a tab bar up there could never highlight the page you just
navigated to.
"""

from gitflower.models import TABS
from gitflower.web.html import esc

CHROME_CSS = """
.crumbs { color: var(--fg-dim); margin: 0 0 0.5rem; font-size: 0.85rem; }
.repo-tabs { display: flex; margin: 0 0 1.4rem; border-bottom: 1px solid var(--border); overflow-x: auto; font-size: 0.9rem; gap: 0.2rem; }
.repo-tabs a { padding: 0.5rem 0.9rem; color: var(--fg); white-space: nowrap; border-bottom: 2px solid transparent; margin-bottom: -1px; border-radius: 6px 6px 0 0; }
.repo-tabs a:hover { background: var(--code-bg); text-decoration: none; }
.repo-tabs a.on { border-bottom-color: var(--accent); color: var(--accent); font-weight: 600; }
.repo-tabs .count { color: var(--fg-dim); font-size: 0.78rem; margin-left: 0.35em; font-weight: 400; }
"""


def repo_url(path: str) -> str:
    return "/repos/" + "/".join(esc(p) for p in path.split("/"))


def crumbs(*parts: tuple[str, str | None]) -> str:
    out = []
    for label, url in parts:
        out.append(f'<a href="{url}">{esc(label)}</a>' if url else esc(label))
    return f'<p class="crumbs">{" / ".join(out)}</p>'


def _repo_crumbs(path: str, tail: tuple[tuple[str, str | None], ...]) -> str:
    """repos / org / … / name.git / <page>, with each folder linked."""
    url = repo_url(path)
    parts: list[tuple[str, str | None]] = [("repos", "/repos/")]
    segments = path.split("/")
    for i, segment in enumerate(segments[:-1]):
        parts.append((segment, "/repos/" + "/".join(esc(s) for s in segments[: i + 1])))
    parts.append((segments[-1], url if tail else None))
    parts.extend(tail)
    return crumbs(*parts)


def repo_header(
    path: str,
    active: str,
    *tail: tuple[str, str | None],
    counts: dict[str, int] | None = None,
) -> str:
    """Breadcrumbs and the section tabs for a repository page.

    `active` is one of the TABS keys. `tail` adds page-specific crumbs after
    the repository — the ref and subpath of a file, a commit's short id.
    """
    url = repo_url(path)
    counts = counts or {}
    links = []
    for key, label, suffix in TABS:
        count = counts.get(key)
        badge = f'<span class="count">{count}</span>' if count else ""
        on = ' class="on"' if key == active else ""
        links.append(f'<a{on} href="{url}{suffix}">{esc(label)}{badge}</a>')
    return f'{_repo_crumbs(path, tail)}<nav class="tabs repo-tabs">{"".join(links)}</nav>'

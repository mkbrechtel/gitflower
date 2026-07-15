"""View fragments: Python render functions instead of a template engine.

Each function takes the same dict the JSON representation serves and returns
an HTML fragment wrapped in a declarative shadow root (see html.view), so its
<style> is browser-scoped. Shared look comes from the :root custom properties
in gitflower.css — custom properties pierce the shadow boundary; rules don't.
"""

from gitflower.web.html import esc, view

# style snippets shared by several fragments (still emitted per-fragment —
# each shadow root is its own scope)
BASE_CSS = """
:host { display: block; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2 { font-weight: 600; }
h1 { font-size: 1.4rem; margin: 0 0 0.8rem; }
h2 { font-size: 1.05rem; margin: 1.6rem 0 0.6rem; }
code { font-family: var(--mono); background: var(--code-bg); padding: 0.1em 0.35em; border-radius: 4px; font-size: 0.9em; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th { text-align: left; color: var(--fg-dim); font-weight: 500; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
th, td { padding: 0.45rem 0.8rem 0.45rem 0; border-bottom: 1px solid var(--border); }
.dim { color: var(--fg-dim); font-size: 0.85rem; }
.crumbs { color: var(--fg-dim); margin: 0 0 1rem; }
.empty { color: var(--fg-dim); font-style: italic; }
pre { background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px; padding: 0.8rem 1rem; overflow-x: auto; font-family: var(--mono); font-size: 0.82rem; line-height: 1.45; }
"""


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _repo_url(path: str) -> str:
    return "/repos/" + "/".join(esc(p) for p in path.split("/"))


def _crumbs(*parts: tuple[str, str | None]) -> str:
    out = []
    for label, url in parts:
        out.append(f'<a href="{url}">{esc(label)}</a>' if url else esc(label))
    return f'<p class="crumbs">{" / ".join(out)}</p>'


def _repo_table(repos: list[dict]) -> str:
    if not repos:
        return '<p class="empty">No repositories found. Create one with <code>gitflower create myproject.git</code>.</p>'
    rows = []
    for repo in repos:
        status = "OK" if repo["is_valid"] else f"ERROR: {repo['error']}"
        link = _repo_url(repo["path"])
        rows.append(
            f'<tr><td><a href="{link}">{esc(repo["path"])}</a></td>'
            f'<td>{repo["branch_count"]}</td><td>{repo["mr_count"]}</td>'
            f'<td>{_size(repo["size"])}</td>'
            f'<td class="dim">{esc((repo["last_update"] or "")[:10])}</td>'
            f'<td class="dim">{esc(status)}</td></tr>'
        )
    return (
        "<table><thead><tr><th>path</th><th>branches</th><th>MR</th>"
        "<th>size</th><th>last update</th><th>status</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def index(data: dict) -> str:
    body = f"""
<h1>gitflower</h1>
<p>A git-based development platform — local-first, git-centric.
Branch workflows enforced by hooks, repositories browsable below.</p>
<h2>Repositories</h2>
{_repo_table(data["repos"])}
"""
    return view(BASE_CSS, body)


def repo_list(data: dict) -> str:
    warnings = "".join(
        f'<p class="dim">⚠ {esc(w)}</p>' for w in data.get("warnings", [])
    )
    return view(BASE_CSS, f"<h1>Repositories</h1>{warnings}{_repo_table(data['repos'])}")


def org(data: dict) -> str:
    body = f"""
{_crumbs(("repos", "/repos/"), (data["org"], None))}
<h1>{esc(data["org"])}/</h1>
{_repo_table(data["repos"])}
"""
    return view(BASE_CSS, body)


GRAPH_CSS = """
.graph { position: relative; overflow-x: auto; margin: 1rem 0; border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0; }
.graph-svg { position: absolute; top: 0.4rem; left: 0; }
.graph-svg path { transition: opacity 0.15s; }
.graph-svg.focused path { opacity: 0.25; }
.graph-svg.focused path.hot { opacity: 1; }
.graph-rows { list-style: none; margin: 0; padding: 0; }
.graph-row { display: flex; align-items: center; gap: 0.5rem; height: var(--graph-row); padding-left: var(--graph-gutter); padding-right: 0.6rem; font-size: 0.82rem; line-height: var(--graph-row); white-space: nowrap; }
.graph-row:hover { background: var(--code-bg); }
.graph-sha { flex: none; color: var(--fg-dim); background: none; padding: 0; }
.graph-subject { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.graph-subject a { color: var(--fg); }
.graph-when { flex: none; color: var(--fg-dim); font-size: 0.75rem; }
.graph-gap a { font-family: var(--mono); color: var(--fg-dim); }
.graph-note { font-size: 0.8rem; color: var(--fg-dim); }
.ref { flex: none; font-family: var(--mono); font-size: 0.72rem; padding: 0 0.4em; border: 1px solid var(--accent); border-radius: 8px; color: var(--accent); }
@media (max-width: 640px) { .graph-row .graph-when { display: none; } }
"""


def _graph_svg(graph: dict, repo_url: str, tips: dict, full: bool) -> str:
    """The commit graph: an SVG of lanes behind fixed-height rows (cyblox
    pattern). Edges carry data-lanes, rows data-lane — components.js uses
    them for hover highlighting."""
    edges = []
    for edge in graph["edges"]:
        dash = ' stroke-dasharray="2 3" opacity="0.5"' if edge["stub"] else ""
        lanes = " ".join(str(lane) for lane in edge["lanes"])
        edges.append(
            f'<path d="{edge["d"]}" fill="none" stroke="{edge["color"]}" '
            f'stroke-width="1.6" data-lanes="{lanes}"{dash}/>'
        )
    shapes = []
    rows = []
    for row in graph["rows"]:
        if row["kind"] == "gap":
            shapes.append(
                f'<rect x="{row["x"] - 3.5}" y="{row["y"] - 8}" width="7" height="16" rx="3.5" '
                f'fill="var(--bg)" stroke="{row["color"]}" stroke-width="1.6" stroke-dasharray="2 2"/>'
            )
            rows.append(
                f'<li class="graph-row graph-gap" data-lane="{row["lane"]}">'
                f'<a href="{repo_url}?full=1">⋯ {row["count"]} commits</a>'
                f'<span class="graph-when">{esc(row["last"]["date"][:10])} – {esc(row["first"]["date"][:10])}</span>'
                "</li>"
            )
            continue
        commit = row["commit"]
        shapes.append(
            f'<circle cx="{row["x"]}" cy="{row["y"]}" r="{graph["dot"]}" '
            f'fill="var(--bg)" stroke="{row["color"]}" stroke-width="1.8"/>'
        )
        chips = "".join(
            f'<span class="ref">{esc(name)}</span>' for name in tips.get(commit["sha"], [])
        )
        commit_url = f"{repo_url}/commit/{esc(commit['sha'])}"
        rows.append(
            f'<li class="graph-row" data-lane="{row["lane"]}" id="c-{esc(commit["short"])}">'
            f'<code class="graph-sha">{esc(commit["short"])}</code>{chips}'
            f'<span class="graph-subject"><a href="{commit_url}">{esc(commit["subject"])}</a></span>'
            f'<span class="graph-when">{esc(commit["author"])} · {esc(commit["date"][:10])}</span>'
            "</li>"
        )
    note = f"{len(graph['rows'])} rows."
    if graph["collapsed"]:
        note = (
            f'{graph["collapsed"]} linear commits folded away — '
            f'<a href="{repo_url}?full=1">show every commit</a>.'
        )
    elif full:
        note = f'<a href="{repo_url}">fold linear stretches</a>.'
    return f"""
<div class="graph" style="--graph-row: {graph["row_height"]}px; --graph-gutter: {graph["width"] + 10}px;">
  <svg class="graph-svg" width="{graph["width"]}" height="{graph["height"]}" viewBox="0 0 {graph["width"]} {graph["height"]}" aria-hidden="true">
    {"".join(edges)}{"".join(shapes)}
  </svg>
  <ol class="graph-rows">{"".join(rows)}</ol>
</div>
<p class="graph-note">{note}</p>
"""


def repo(data: dict) -> str:
    url = _repo_url(data["path"])
    tips: dict[str, list[str]] = {}
    for branch in data["branches"]:
        tips.setdefault(branch["sha"], []).append(branch["name"])
    branch_rows = "".join(
        f'<tr><td><a href="{url}/tree/{esc(b["name"])}/">{esc(b["name"])}</a></td>'
        f'<td><code>{esc(b["short"])}</code></td>'
        f'<td class="dim">{esc(b["date"][:10])}</td>'
        f"<td>{esc(b['subject'])}</td></tr>"
        for b in data["branches"]
    )
    branches = (
        "<table><thead><tr><th>branch</th><th>tip</th><th>last commit</th>"
        f'<th>subject</th></tr></thead><tbody>{branch_rows}</tbody></table>'
        if data["branches"]
        else '<p class="empty">Empty repository — push something first.</p>'
    )
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], None))}
<h1>{esc(data["path"])}</h1>
<h2>Graph</h2>
{_graph_svg(data["graph"], url, tips, data["full"])}
<h2>Branches</h2>
{branches}
<h2>Clone (read-only)</h2>
<pre>git clone {esc(data["clone_url"])}</pre>
"""
    return view(BASE_CSS + GRAPH_CSS, body)


TREE_CSS = """
.icon { width: 1.2em; display: inline-block; }
"""


def tree(data: dict) -> str:
    url = _repo_url(data["path"])
    ref = esc(data["ref"])
    subpath = data["subpath"]
    rows = []
    if subpath:
        parent = "/".join(subpath.split("/")[:-1])
        up = f"{url}/tree/{ref}/{esc(parent)}{'/' if parent else ''}"
        rows.append(f'<tr><td><span class="icon">📁</span><a href="{up}">..</a></td><td></td><td></td></tr>')
    for entry in data["entries"]:
        base = f"{url}/tree/{ref}/{esc(subpath)}{'/' if subpath else ''}{esc(entry['name'])}"
        if entry["type"] == "dir":
            rows.append(
                f'<tr><td><span class="icon">📁</span><a href="{base}/">{esc(entry["name"])}/</a></td>'
                f'<td class="dim">{entry["mode"]}</td><td></td></tr>'
            )
        else:
            rows.append(
                f'<tr><td><span class="icon">📄</span><a href="{base}">{esc(entry["name"])}</a></td>'
                f'<td class="dim">{entry["mode"]}</td><td class="dim">{_size(entry["size"])}</td></tr>'
            )
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], url), (data["ref"], f"{url}/tree/{ref}/"), (subpath or ".", None))}
<h1>{esc(data["path"])} <span class="dim">@ {ref}</span></h1>
<table><thead><tr><th>name</th><th>mode</th><th>size</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
"""
    return view(BASE_CSS + TREE_CSS, body)


def blob(data: dict) -> str:
    url = _repo_url(data["path"])
    ref = esc(data["ref"])
    if data["is_binary"]:
        content = f'<p class="empty">Binary file not shown ({_size(data["size"])}).</p>'
    else:
        content = f"<pre>{esc(data['content'])}</pre>"
    raw = f"{url}/tree/{ref}/{esc(data['subpath'])}?format=raw"
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], url), (data["ref"], f"{url}/tree/{ref}/"), (data["subpath"], None))}
<h1>{esc(data["subpath"])} <span class="dim">@ {ref}</span></h1>
<p class="dim">{_size(data["size"])} · <a href="{raw}">raw</a></p>
{content}
"""
    return view(BASE_CSS, body)


DIFF_CSS = """
.patch .add { color: var(--diff-add); }
.patch .del { color: var(--diff-del); }
.patch .hunk { color: var(--accent); }
.patch .head { color: var(--fg-dim); }
"""


def _colorize_patch(patch: str) -> str:
    lines = []
    for line in patch.splitlines():
        cls = ""
        if line.startswith("+") and not line.startswith("+++"):
            cls = "add"
        elif line.startswith("-") and not line.startswith("---"):
            cls = "del"
        elif line.startswith("@@"):
            cls = "hunk"
        elif line.startswith(("diff ", "index ", "+++", "---")):
            cls = "head"
        lines.append(f'<span class="{cls}">{esc(line)}</span>' if cls else esc(line))
    return "\n".join(lines)


def commit(data: dict) -> str:
    url = _repo_url(data["path"])
    parents = (
        " ".join(
            f'<a href="{url}/commit/{esc(p)}"><code>{esc(p[:7])}</code></a>'
            for p in data["parents"]
        )
        or '<span class="dim">none (initial commit)</span>'
    )
    patch = (
        f'<pre class="patch">{_colorize_patch(data["patch"])}</pre>'
        if data["patch"]
        else '<p class="empty">No changes to display.</p>'
    )
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], url), (data["short"], None))}
<h1>{esc(data["subject"])}</h1>
<p class="dim">{esc(data["author"])} &lt;{esc(data["author_email"])}&gt; · {esc(data["date"])}</p>
<p><code>{esc(data["sha"])}</code> · parents: {parents} ·
<a href="{url}/tree/{esc(data["sha"])}/">browse tree</a></p>
<pre>{esc(data["message"].strip())}</pre>
<h2>Changes</h2>
{patch}
"""
    return view(BASE_CSS + DIFF_CSS, body)


def docs(data: dict) -> str:
    body = """
<h1>Documentation</h1>
<h2>Getting started</h2>
<pre>gitflower init       # initialize workflows in a repository
gitflower install    # install the pre-push hook
gitflower create myproject.git
gitflower list
gitflower web</pre>
<h2>Branch workflows</h2>
<p>Branch rules in <code>.gitflower/config.yaml</code> route each pushed
branch to a workflow — <code>protected</code>, <code>issue-tracker</code> or
<code>release-manager</code>. Unconfigured branches are rejected: the rule
list is an allow-list.</p>
<h2>The API is the frontend</h2>
<p>Every page on this site is also an API endpoint: request it with
<code>Accept: application/json</code> (or <code>?format=json</code>) for the
data, <code>?format=fragment</code> for the bare HTML fragment, and
<code>?format=raw</code> on file views for the raw bytes.
The interactive schema lives at <a href="/api">/api</a>.</p>
"""
    return view(BASE_CSS, body)


def not_found(data: dict) -> str:
    body = f"""
<h1>404 — Not Found</h1>
<p>No such page: <code>{esc(data["detail"])}</code></p>
<p><a href="/repos/">Back to the repositories</a>.</p>
"""
    return view(BASE_CSS, body)

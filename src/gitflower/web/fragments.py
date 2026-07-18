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
.graph { position: relative; margin: 1rem 0; border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0; }
.graph-svg { position: absolute; top: 0.4rem; left: 0; }
.graph-svg path { transition: opacity 0.15s; }
.graph-svg.focused path { opacity: 0.25; }
.graph-svg.focused path.hot { opacity: 1; }
.graph-rows { list-style: none; margin: 0; padding: 0; }
.graph-row { display: flex; align-items: center; gap: 0.5rem; height: var(--graph-row); padding-left: var(--graph-gutter); padding-right: 0.6rem; font-size: 0.82rem; line-height: var(--graph-row); white-space: nowrap; }
.graph-row:hover { background: var(--code-bg); }
.graph-sha { flex: none; }
.graph-sha code { color: var(--fg-dim); background: none; padding: 0; }
.graph-sha:hover code { color: var(--accent); }
.graph-subject { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.graph-subject a { color: var(--fg); }
.graph-when { flex: none; color: var(--fg-dim); font-size: 0.75rem; }
.graph-gap a { font-family: var(--mono); color: var(--fg-dim); }
.graph-dimmed { opacity: 0.55; }
.graph-note { font-size: 0.8rem; color: var(--fg-dim); }
.ref { flex: none; font-family: var(--mono); font-size: 0.72rem; padding: 0 0.4em; border: 1px solid var(--accent); border-radius: 8px; color: var(--accent); }
@media (max-width: 640px) { .graph-row .graph-when { display: none; } }
"""


def _on_branch(row: dict) -> str:
    """Branch attribution as a tooltip + data attribute, when known."""
    branch = row.get("branch")
    if not branch:
        return ""
    return f' data-branch="{esc(branch)}" title="on {esc(branch)}"'


def _qs(**flags: bool) -> str:
    """Query string for the repo view's toggles: only the raised ones."""
    on = [f"{name}=1" for name, raised in flags.items() if raised]
    return "?" + "&".join(on) if on else ""


def _graph_svg(
    graph: dict, repo_url: str, tips: dict, full: bool, show_hidden: bool, hidden_count: int
) -> str:
    """The commit graph: an SVG of lanes behind fixed-height rows (cyblox
    pattern). Edges carry data-lanes, rows data-lane — components.js uses
    them for hover highlighting. Pinned branches' commits are filled dots."""
    edges = []
    for edge in graph["edges"]:
        dash = ' stroke-dasharray="2 3"' if edge["stub"] else ""
        faint = "0.35" if edge.get("dimmed") else "0.5" if edge["stub"] else ""
        opacity = f' opacity="{faint}"' if faint else ""
        lanes = " ".join(str(lane) for lane in edge["lanes"])
        edges.append(
            f'<path d="{edge["d"]}" fill="none" stroke="{edge["color"]}" '
            f'stroke-width="1.6" data-lanes="{lanes}"{dash}{opacity}/>'
        )
    unfold = repo_url + _qs(full=True, hidden=show_hidden)
    shapes = []
    rows = []
    for row in graph["rows"]:
        faded = ' opacity="0.4"' if row.get("dimmed") else ""
        dim_cls = " graph-dimmed" if row.get("dimmed") else ""
        if row["kind"] == "gap":
            shapes.append(
                f'<rect x="{row["x"] - 3.5}" y="{row["y"] - 8}" width="7" height="16" rx="3.5" '
                f'fill="var(--bg)" stroke="{row["color"]}" stroke-width="1.6" '
                f'stroke-dasharray="2 2"{faded}/>'
            )
            rows.append(
                f'<li class="graph-row graph-gap{dim_cls}" '
                f'data-lane="{row["lane"]}"{_on_branch(row)}>'
                f'<a href="{unfold}">⋯ {row["count"]} commits</a>'
                f'<span class="graph-when">{esc(row["last"]["date"][:10])} – {esc(row["first"]["date"][:10])}</span>'
                "</li>"
            )
            continue
        commit = row["commit"]
        fill = row["color"] if row.get("pinned") else "var(--bg)"
        shapes.append(
            f'<circle cx="{row["x"]}" cy="{row["y"]}" r="{graph["dot"]}" '
            f'fill="{fill}" stroke="{row["color"]}" stroke-width="1.8"{faded}/>'
        )
        chips = "".join(
            f'<span class="ref">{esc(name)}</span>' for name in tips.get(commit["sha"], [])
        )
        commit_url = f"{repo_url}/commit/{esc(commit['sha'])}"
        rows.append(
            f'<li class="graph-row{dim_cls}" data-lane="{row["lane"]}"{_on_branch(row)} id="c-{esc(commit["short"])}">'
            f'<a class="graph-sha" href="{commit_url}"><code>{esc(commit["short"])}</code></a>{chips}'
            f'<span class="graph-subject"><a href="{commit_url}">{esc(commit["subject"])}</a></span>'
            f'<span class="graph-when">{esc(commit["author"])} · {esc(commit["date"][:10])}</span>'
            "</li>"
        )
    note = f"{len(graph['rows'])} rows."
    if graph["collapsed"]:
        note = (
            f'{graph["collapsed"]} linear commits folded away — '
            f'<a href="{unfold}">show every commit</a>.'
        )
    elif full:
        note = f'<a href="{repo_url + _qs(hidden=show_hidden)}">fold linear stretches</a>.'
    if hidden_count:
        plural = "branches" if hidden_count != 1 else "branch"
        if show_hidden:
            note += (
                f' <a href="{repo_url + _qs(full=full)}">'
                f"hide {hidden_count} hidden {plural}</a>."
            )
        else:
            note += (
                f" {hidden_count} hidden {plural} — "
                f'<a href="{repo_url + _qs(full=full, hidden=True)}">show</a>.'
            )
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
        f'<tr><td><a href="{url}/tree/{esc(b["name"])}/">{esc(b["name"])}</a>'
        f'{" <span class=dim>(hidden)</span>" if b["hidden"] else ""}</td>'
        f'<td><a href="{url}/commit/{esc(b["sha"])}"><code>{esc(b["short"])}</code></a></td>'
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
{_graph_svg(data["graph"], url, tips, data["full"], data["show_hidden"], data["hidden_count"])}
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
.changes-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.wrap-toggle { display: flex; align-items: center; gap: 0.4em; font-size: 0.8rem; color: var(--fg-dim); cursor: pointer; user-select: none; }
.wrap-toggle[hidden] { display: none; }
.wrap-toggle input { accent-color: var(--accent); margin: 0; }
pre.patch { white-space: pre-wrap; overflow-wrap: anywhere; }
.changes.nowrap pre.patch { white-space: pre; overflow-wrap: normal; }
.patch .add { color: var(--diff-add); }
.patch .del { color: var(--diff-del); }
.patch .hunk { color: var(--accent); }
.patch .head { color: var(--fg-dim); }
.meta { border: 1px solid var(--border); border-radius: 6px; padding: 0.7rem 1rem; font-size: 0.88rem; display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 1rem; }
.meta dt { color: var(--fg-dim); margin: 0; }
.meta dd { margin: 0; overflow-wrap: anywhere; }
.stat-add { color: var(--diff-add); }
.stat-del { color: var(--diff-del); }
.filelist { list-style: none; margin: 0.6rem 0; padding: 0; font-size: 0.88rem; }
.filelist li { display: flex; gap: 0.7rem; padding: 0.15rem 0; font-family: var(--mono); }
.filelist .counts { margin-left: auto; white-space: nowrap; }
.status { flex: none; width: 1.2em; text-align: center; font-weight: 700; border-radius: 4px; font-size: 0.8em; line-height: 1.6; }
.status-A { color: var(--diff-add); }
.status-D { color: var(--diff-del); }
.status-M, .status-R { color: var(--accent); }
details.file { border: 1px solid var(--border); border-radius: 6px; margin: 0.8rem 0; overflow: hidden; }
details.file > summary { cursor: pointer; padding: 0.5rem 0.9rem; background: var(--code-bg); font-family: var(--mono); font-size: 0.85rem; display: flex; gap: 0.7rem; align-items: baseline; flex-wrap: wrap; }
details.file > summary .counts { margin-left: auto; }
details.file > pre { margin: 0; border: none; border-radius: 0; }
"""


def _wrap_toggle() -> str:
    # hidden until components.js wires it up — without JS the default
    # (soft-wrapped) presentation stands
    return (
        '<label class="wrap-toggle" hidden>'
        '<input type="checkbox" checked> soft-wrap lines</label>'
    )


def _counts(additions: int, deletions: int) -> str:
    return (
        f'<span class="counts"><span class="stat-add">+{additions}</span> '
        f'<span class="stat-del">−{deletions}</span></span>'
    )


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


TABS_CSS = """
.tabs { display: flex; margin: 1.2rem 0 0.4rem; border: 1px solid var(--border); border-radius: 6px; overflow-x: auto; width: max-content; max-width: 100%; font-size: 0.85rem; }
.tabs a { padding: 0.4rem 0.9rem; color: var(--fg); border-right: 1px solid var(--border); white-space: nowrap; }
.tabs a:last-child { border-right: none; }
.tabs a:hover { background: var(--code-bg); text-decoration: none; }
.tabs a.on { background: var(--code-bg); color: var(--accent); font-weight: 600; }
"""


def _commit_meta(url: str, data: dict, parents_html: str) -> str:
    committer = ""
    if (data["committer"], data["committer_email"]) != (data["author"], data["author_email"]):
        committer = (
            "<dt>committer</dt>"
            f'<dd>{esc(data["committer"])} &lt;{esc(data["committer_email"])}&gt;</dd>'
        )
    return f"""
<dl class="meta">
<dt>author</dt><dd>{esc(data["author"])} &lt;{esc(data["author_email"])}&gt; · {esc(data["date"])}</dd>
{committer}
<dt>commit</dt><dd><a href="{url}/commit/{esc(data["sha"])}"><code>{esc(data["sha"])}</code></a></dd>
<dt>parents</dt><dd>{parents_html}</dd>
<dt>tree</dt><dd><a href="{url}/tree/{esc(data["sha"])}/">browse the repository at this commit</a></dd>
</dl>
"""


def _message_body(data: dict) -> str:
    # the message body beyond the subject line, if there is one
    body_text = data["message"].strip()
    body_text = body_text[len(data["subject"]):].strip() if body_text.startswith(data["subject"]) else body_text
    return f"<pre>{esc(body_text)}</pre>" if body_text else ""


def _tab(label: str, href: str, on: bool) -> str:
    cls = ' class="on"' if on else ""
    return f'<a{cls} href="{href}">{label}</a>'


def _parent_tabs(url: str, sha: str, parents: list[tuple[str, str]], active: int) -> str:
    """The merge-commit view switcher: 0 = side-by-side, N = diff vs parent N."""
    base = f"{url}/commit/{esc(sha)}"
    tabs = [_tab("side by side", base, active == 0)]
    for i, (_psha, short) in enumerate(parents, 1):
        tabs.append(
            _tab(f"diff vs parent {i} <code>{esc(short)}</code>", f"{base}?parent={i}", active == i)
        )
    return f'<nav class="tabs">{"".join(tabs)}</nav>'


def commit(data: dict) -> str:
    url = _repo_url(data["path"])
    parents = (
        " ".join(
            f'<a href="{url}/commit/{esc(p)}"><code>{esc(p[:7])}</code></a>'
            for p in data["parents"]
        )
        or '<span class="dim">none (initial commit)</span>'
    )
    tabs = ""
    if len(data["parents"]) > 1:
        active = data["diff_parent"]
        pairs = [(p, p[:7]) for p in data["parents"]]
        tabs = _parent_tabs(url, data["sha"], pairs, active) + (
            f'<p class="dim">Showing changes against parent {active} '
            f"<code>{esc(pairs[active - 1][1])}</code>.</p>"
        )

    stats = data["stats"]
    filelist = "".join(
        f'<li><span class="status status-{esc(f["status"])}">{esc(f["status"])}</span>'
        f'<a href="#f-{i}">{_file_label(f)}</a>{_counts(f["additions"], f["deletions"])}</li>'
        for i, f in enumerate(data["files"])
    )
    sections = "".join(_file_section(url, data["sha"], i, f) for i, f in enumerate(data["files"]))
    changes = (
        f"""
<p class="dim">{stats["files_changed"]} file{"s" if stats["files_changed"] != 1 else ""} changed,
<span class="stat-add">+{stats["additions"]}</span> <span class="stat-del">−{stats["deletions"]}</span></p>
<ul class="filelist">{filelist}</ul>
{sections}"""
        if data["files"]
        else '<p class="empty">No changes to display.</p>'
    )
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], url), (data["short"], None))}
<h1>{esc(data["subject"])}</h1>
{_commit_meta(url, data, parents)}
{_message_body(data)}
{tabs}
<div class="changes-head"><h2>Changes</h2>{_wrap_toggle()}</div>
<div class="changes">
{changes}
</div>
"""
    return view(BASE_CSS + DIFF_CSS + TABS_CSS, body)


def _file_label(f: dict) -> str:
    if f["status"] == "R":
        return f"{esc(f['old_path'])} → {esc(f['path'])}"
    return esc(f["path"] if f["status"] != "D" else f["old_path"])


def _file_section(url: str, sha: str, i: int, f: dict) -> str:
    if f["binary"]:
        content = '<pre><span class="dim">Binary file not shown.</span></pre>'
    elif f["patch"]:
        content = f'<pre class="patch">{_colorize_patch(f["patch"])}</pre>'
    else:
        content = '<pre><span class="dim">No textual changes.</span></pre>'
    file_link = (
        f' <a href="{url}/tree/{esc(sha)}/{esc(f["path"])}">view file</a>'
        if f["status"] != "D"
        else ""
    )
    return f"""
<details class="file" id="f-{i}" open>
<summary><span class="status status-{esc(f["status"])}">{esc(f["status"])}</span>
{_file_label(f)}{_counts(f["additions"], f["deletions"])}{file_link}</summary>
{content}
</details>"""


MERGE_CSS = """
.parentstats code { font-size: 0.85em; }
.legend { font-size: 0.82rem; }
.merge-wrap { overflow-x: auto; }
table.merge { border-collapse: collapse; font-family: var(--mono); font-size: 0.78rem; line-height: 1.55; width: 100%; }
table.merge th { font-size: 0.72rem; padding: 0.35rem 0.6rem; border-bottom: 1px solid var(--border); border-left: 1px solid var(--border); }
table.merge td { padding: 0 0.6rem; border-bottom: none; border-left: 1px solid var(--border); white-space: pre-wrap; overflow-wrap: anywhere; vertical-align: top; }
.changes.nowrap table.merge td { white-space: pre; overflow-wrap: normal; }
table.merge th:first-child, table.merge td:first-child { border-left: none; }
table.merge .ln { display: inline-block; min-width: 2.4em; margin-right: 0.7em; text-align: right; color: var(--fg-dim); user-select: none; }
table.merge td.changed, table.merge td.removed { color: var(--diff-del); background: var(--diff-del-bg); }
table.merge td.absent { background: repeating-linear-gradient(45deg, transparent 0 6px, var(--code-bg) 6px 8px); }
table.merge td.res .sign { display: inline-block; width: 1em; color: var(--diff-add); font-weight: 700; user-select: none; }
table.merge td.res.add { background: var(--diff-add-bg); }
table.merge td.res.gone { background: var(--diff-del-bg); }
.flag { color: var(--accent); margin-left: 0.5em; }
tr.fold td { border-left: none; background: var(--code-bg); text-align: center; padding: 0.3rem; font-size: 0.75rem; }
"""


def _merge_table(url: str, data: dict, f: dict) -> str:
    n = len(data["parents"])
    head = (
        "".join(
            f'<th><a href="{url}/commit/{esc(p["sha"])}">parent {i} · {esc(p["short"])}</a></th>'
            for i, p in enumerate(data["parents"], 1)
        )
        + "<th>result</th>"
    )
    rows = []
    for row in f["rows"]:
        if row["kind"] == "fold":
            rows.append(
                f'<tr class="fold"><td colspan="{n + 1}">'
                f'<a href="{url}/commit/{esc(data["sha"])}?full=1">'
                f'⋯ {row["count"]} unchanged lines ({row["start"]}–{row["end"]}) — show</a>'
                "</td></tr>"
            )
            continue
        cells = []
        for cell in row["cells"]:
            if cell["status"] == "same":
                cells.append(
                    f'<td class="same"><span class="ln">{cell["no"]}</span>'
                    f'{esc(row["result_text"] or "")}</td>'
                )
            elif cell["status"] == "absent":
                cells.append('<td class="absent"></td>')
            else:  # changed | removed: this parent's own text
                cells.append(
                    f'<td class="{cell["status"]}"><span class="ln">{cell["no"]}</span>'
                    f'{esc(cell["text"] or "")}</td>'
                )
        flag = (
            ' <span class="flag" title="merge-authored: matches no parent">⚑</span>'
            if row["merge_authored"]
            else ""
        )
        if row["kind"] == "line":
            # the classic diff reading: differing from any parent = an added
            # line on the result side, green with a + sign
            added = any(cell["status"] != "same" for cell in row["cells"])
            classes = "res" + (" add" if added else "") + (" authored" if row["merge_authored"] else "")
            sign = "+" if added else " "
            cells.append(
                f'<td class="{classes}"><span class="ln">{row["result_no"]}</span>'
                f'<span class="sign">{sign}</span>{esc(row["result_text"] or "")}{flag}</td>'
            )
        else:  # only: lines the result dropped — the removal side stays red
            cells.append(f'<td class="res gone">{flag}</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    return (
        '<div class="merge-wrap"><table class="merge">'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def _merge_file_section(url: str, data: dict, i: int, f: dict) -> str:
    labels = []
    for status, p, c in zip(f["statuses"], data["parents"], f["parent_counts"]):
        if status == "=":
            labels.append(f'<span class="dim">= vs {esc(p["short"])}</span>')
        else:
            labels.append(
                f'<span class="status status-{esc(status)}">{esc(status)}</span> '
                f'vs {esc(p["short"])} <span class="stat-add">+{c["additions"]}</span> '
                f'<span class="stat-del">−{c["deletions"]}</span>'
            )
    if f["binary"]:
        content = '<pre><span class="dim">Binary file not shown.</span></pre>'
    elif f["truncated"]:
        content = (
            '<pre><span class="dim">File too large for the side-by-side view — '
            "use the per-parent diff tabs above.</span></pre>"
        )
    elif f["rows"]:
        content = _merge_table(url, data, f)
    else:
        content = '<pre><span class="dim">No textual changes.</span></pre>'
    deleted = "D" in f["statuses"]
    file_link = (
        f' <a href="{url}/tree/{esc(data["sha"])}/{esc(f["path"])}">view file</a>'
        if not deleted
        else ""
    )
    return f"""
<details class="file" id="f-{i}" open>
<summary>{esc(f["path"])} <span class="dim">·</span> {' <span class="dim">·</span> '.join(labels)}{file_link}</summary>
{content}
</details>"""


def merge(data: dict) -> str:
    """A merge commit: side-by-side per-parent columns against the plain
    result. The result column is not a diff — it is the merged content."""
    url = _repo_url(data["path"])
    parents_html = " ".join(
        f'<a href="{url}/commit/{esc(p["sha"])}"><code>{esc(p["short"])}</code></a>'
        for p in data["parents"]
    )
    tabs = _parent_tabs(
        url, data["sha"], [(p["sha"], p["short"]) for p in data["parents"]], active=0
    )
    stat_bits = []
    for i, (p, s) in enumerate(zip(data["parents"], data["parent_stats"]), 1):
        if s["files_changed"] == 0:
            stat_bits.append(
                f'vs parent {i} <code>{esc(p["short"])}</code>: no changes — '
                "the merge took this side as-is"
            )
        else:
            stat_bits.append(
                f'vs parent {i} <code>{esc(p["short"])}</code>: '
                f'{s["files_changed"]} file{"s" if s["files_changed"] != 1 else ""}, '
                f'<span class="stat-add">+{s["additions"]}</span> '
                f'<span class="stat-del">−{s["deletions"]}</span>'
            )
    fold_note = (
        f'<a href="{url}/commit/{esc(data["sha"])}">fold unchanged lines</a>'
        if data["full"]
        else "runs where every parent matches are folded"
    )
    legend = (
        '<p class="dim legend">The result column is the merged content itself: '
        '<span class="stat-add">green +</span> lines differ from at least one parent, '
        '<span class="stat-del">red</span> cells carry a parent\'s own changed or removed text, '
        'and <span class="flag">⚑</span> rows match no parent at all — the merge author wrote '
        f"them. {fold_note.capitalize() if not data['full'] else fold_note}.</p>"
    )
    sections = (
        "".join(_merge_file_section(url, data, i, f) for i, f in enumerate(data["files"]))
        or '<p class="empty">No changes to display.</p>'
    )
    body = f"""
{_crumbs(("repos", "/repos/"), (data["path"], url), (data["short"], None))}
<h1>{esc(data["subject"])}</h1>
{_commit_meta(url, data, parents_html)}
{_message_body(data)}
{tabs}
<div class="changes-head"><h2>Changes</h2>{_wrap_toggle()}</div>
<p class="dim parentstats">{" · ".join(stat_bits)}</p>
{legend}
<div class="changes">
{sections}
</div>
"""
    return view(BASE_CSS + DIFF_CSS + TABS_CSS + MERGE_CSS, body)


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

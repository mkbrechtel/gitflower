"""Lane layout for the commit graph on the repo page.

Ported from cyblox's apps/cyblox_portal/graph.py (same author). Pure
geometry: commits in, SVG coordinates out — no git, no I/O. The input is the
commit list from gitread.commits(), which comes child-before-parent; that
ordering is what makes a single forward pass enough.

Two things happen here:

* **collapse** — a run of consecutive commits that is plainly linear (one
  parent, one child, no ref pointing at it) carries no shape. A run of
  MIN_COLLAPSE or more becomes a single "gap" node, `⋯ 27 commits`, so the
  interesting points — branch points, merges, tips — stay on one screen.
* **lanes** — each node gets a column. A lane is "open" while some commit
  further down is still expected in it; a merge opens one lane per extra
  parent, and a lane closes when its commit is reached. The lane opened for
  an extra parent is the link's *corridor*: the edge rides it the whole way
  and folds into the parent's dot at the end, so a parent link always
  reaches its commit and never runs along another branch's line.
"""

ROW = 26  # px per row; the CSS row height must match, or dots drift off rows
LANE = 15  # px per lane
PAD = 11  # px from the left edge to lane 0
DOT = 4.0
MIN_COLLAPSE = 4

# one colour per lane, cycling; lane 0 (usually the trunk) gets the accent
COLORS = ["#58e6d9", "#d29922", "#a371f7", "#3fb950", "#db6d28", "#58a6ff"]


def _x(lane: int) -> float:
    return PAD + lane * LANE


def _y(row: int) -> float:
    return ROW / 2 + row * ROW


def _color(lane: int) -> str:
    return COLORS[lane % len(COLORS)]


def _node(commit: dict) -> dict:
    return {"id": commit["sha"], "kind": "commit", "parents": commit["parents"], "commit": commit}


def _collapse(commits: list[dict], tips: set[str], min_run: int) -> list[dict]:
    """Fold maximal runs of shapeless linear commits into single gap nodes."""
    # ?full=1 passes a min_run no run can reach (len + 1). Without this the
    # scan below still runs — and it is quadratic when nothing folds, because
    # every commit of a linear stretch rescans the whole stretch and then
    # discards it. Folding off means no runs, so there is nothing to look for.
    if min_run > len(commits):
        return [_node(commit) for commit in commits]

    shown = {c["sha"] for c in commits}
    children: dict[str, int] = {}
    for commit in commits:
        for parent in commit["parents"]:
            if parent in shown:
                children[parent] = children.get(parent, 0) + 1

    def plain(commit: dict) -> bool:
        # nothing points at it, it neither forks nor merges, and its parent
        # is on screen (a commit at the truncation boundary stays visible)
        return (
            commit["sha"] not in tips
            and len(commit["parents"]) == 1
            and children.get(commit["sha"], 0) == 1
            and commit["parents"][0] in shown
        )

    def chained(commit: dict, nxt: dict) -> bool:
        return commit["parents"][0] == nxt["sha"] and plain(nxt)

    nodes: list[dict] = []
    i = 0
    while i < len(commits):
        commit = commits[i]
        if plain(commit):
            end = i
            while end + 1 < len(commits) and chained(commits[end], commits[end + 1]):
                end += 1
            if end - i + 1 >= min_run:
                nodes.append(
                    {
                        # the run's newest sha: whatever pointed at the run
                        # still resolves to the node that replaced it
                        "id": commit["sha"],
                        "kind": "gap",
                        "parents": commits[end]["parents"],
                        "count": end - i + 1,
                        "first": commit,
                        "last": commits[end],
                    }
                )
                i = end + 1
                continue
        nodes.append(_node(commit))
        i += 1
    return nodes


def _free_lane(lanes: list[str | None]) -> int:
    for i, expected in enumerate(lanes):
        if expected is None:
            return i
    lanes.append(None)
    return len(lanes) - 1


def _place(nodes: list[dict]) -> list[dict]:
    """Assign every node a row and a lane, walking newest to oldest — and
    record, for every merge's extra parent, the **corridor**: the lane its
    link line travels. A lane that is waiting for a sha never receives any
    other commit, so a corridor is collision-free by construction; _edges
    routes the link down it and folds into the parent's dot at the end.

    A fresh corridor is inserted directly beside the child whenever the
    lanes it would shift hold nothing drawn yet — the link then runs
    parallel to its neighbours instead of crossing them."""
    lanes: list[str | None] = []  # lane -> the sha it is waiting for
    fresh: list[int | None] = []  # reserved-at row, while no dot sits on the lane
    pending: list[list] = []  # [child row dict, parent sha, corridor lane]
    rows: list[dict] = []

    def free_lane() -> int:
        lane = _free_lane(lanes)
        if lane == len(fresh):
            fresh.append(None)
        return lane

    def corridor_lane(after: int) -> int:
        """A lane for a new parent link: right beside the child when the
        shift moves nothing already drawn, else the leftmost free lane
        beyond it, else the far right."""
        pos = after + 1

        def clean(i: int) -> bool:
            # shifting lane i to column i+1 must not put its pending
            # stretch across dots already drawn in that column
            if lanes[i] is None:
                return True
            if fresh[i] is None:
                return False  # a drawn line continues below a dot: pinned
            return not any(r["lane"] == i + 1 and r["row"] >= fresh[i] for r in rows)

        if all(clean(i) for i in range(pos, len(lanes))):
            lanes.insert(pos, None)
            fresh.insert(pos, None)
            for link in pending:
                if link[2] >= pos:
                    link[2] += 1
            return pos
        for i in range(pos, len(lanes)):
            if lanes[i] is None:
                return i
        lanes.append(None)
        fresh.append(None)
        return len(lanes) - 1

    for row, node in enumerate(nodes):
        waiting = [i for i, expected in enumerate(lanes) if expected == node["id"]]
        if waiting:
            lane = waiting[0]
            for merged_in in waiting[1:]:
                lanes[merged_in] = None  # those branches end here
                fresh[merged_in] = None
        else:
            lane = free_lane()  # a tip: nothing was expecting it

        # links waiting for this commit now know their final corridor
        for link in pending:
            if link[1] == node["id"]:
                link[0]["corridors"][link[1]] = link[2]
        pending = [link for link in pending if link[1] != node["id"]]

        placed = {**node, "row": row, "lane": lane, "corridors": {}}
        parents = node["parents"]
        lanes[lane] = parents[0] if parents else None
        fresh[lane] = None  # a dot sits here; the stretch below hangs off it
        for parent in parents[1:]:  # a merge forks a lane per extra parent
            if parent in lanes:
                corridor = lanes.index(parent)  # ride the parent's own line
            else:
                corridor = corridor_lane(lane)
                lanes[corridor] = parent
                fresh[corridor] = row
            pending.append([placed, parent, corridor])

        rows.append(placed)
    return rows


def _edges(rows: list[dict]) -> list[dict]:
    """One path per parent link, routed through the link's **corridor** — the
    lane _place reserved for it. A merge's extra parent leaves the child's
    lane within the first row, runs the whole distance down the corridor
    (a waiting lane never carries another commit, so the stretch is clear),
    and folds into the parent's dot within the last row. A commit rejoining
    its own first parent already owns its lane, so it runs straight down and
    bends into the parent at the very end. The link line therefore always
    reaches the parent's dot — never another branch's line."""
    at = {row["id"]: row for row in rows}
    edges = []
    for row in rows:
        x0, y0 = _x(row["lane"]), _y(row["row"])
        for parent in row["parents"]:
            target = at.get(parent)
            if target is None:
                # history is truncated here — a stub says "it goes on"
                edges.append(
                    {
                        "d": f"M {x0},{y0} V {y0 + ROW * 0.6:.0f}",
                        "color": _color(row["lane"]),
                        "lanes": [row["lane"]],
                        "stub": True,
                    }
                )
                continue
            corridor = row["corridors"].get(parent, row["lane"])
            x1, y1 = _x(target["lane"]), _y(target["row"])
            xc = _x(corridor)
            if corridor == row["lane"]:
                if target["lane"] == row["lane"]:
                    d = f"M {x0},{y0} V {y1}"
                else:
                    # the child's own line rejoining its parent: straight
                    # down, bend at the very end
                    bend = max(y0, y1 - ROW)
                    d = f"M {x0},{y0} V {bend} C {x0},{bend + ROW / 2} {x1},{bend + ROW / 2} {x1},{y1}"
            elif corridor == target["lane"]:
                # the parent sits at the corridor's foot: bend out, run down
                bend = y0 + ROW
                d = f"M {x0},{y0} C {x0},{y0 + ROW / 2} {xc},{y0 + ROW / 2} {xc},{bend} V {y1}"
            elif y1 - y0 <= ROW:
                # adjacent rows leave no room for a corridor: one direct bend
                d = f"M {x0},{y0} C {x0},{y0 + ROW / 2} {x1},{y0 + ROW / 2} {x1},{y1}"
            else:
                # the parent landed on another lane: bend out, ride the
                # corridor, fold into the dot over the last row
                out, fold = y0 + ROW, y1 - ROW
                d = (
                    f"M {x0},{y0} C {x0},{y0 + ROW / 2} {xc},{y0 + ROW / 2} {xc},{out}"
                    f" V {fold} C {xc},{fold + ROW / 2} {x1},{fold + ROW / 2} {x1},{y1}"
                )
            edges.append(
                {
                    "d": d,
                    "color": _color(corridor),
                    "lanes": sorted({row["lane"], corridor, target["lane"]}),
                    "stub": False,
                }
            )
    return edges


def build(commits: list[dict], tips: set[str], collapse: bool = True) -> dict:
    """Lay out `commits` (newest first, parents after children). `tips` are the
    shas a ref points at — they are never folded away."""
    nodes = _collapse(commits, tips, MIN_COLLAPSE if collapse else len(commits) + 1)
    rows = _place(nodes)
    for row in rows:
        row["x"] = _x(row["lane"])
        row["y"] = _y(row["row"])
        row["color"] = _color(row["lane"])
    edges = _edges(rows)
    # a corridor can be the rightmost lane while carrying no dots
    lanes_used = [row["lane"] for row in rows]
    for edge in edges:
        lanes_used.extend(edge["lanes"])
    width = _x(max(lanes_used, default=0)) + PAD
    return {
        "rows": rows,
        "edges": edges,
        "width": width,
        "height": len(rows) * ROW,
        "row_height": ROW,
        "dot": DOT,
        "collapsed": sum(row["count"] - 1 for row in rows if row["kind"] == "gap"),
    }

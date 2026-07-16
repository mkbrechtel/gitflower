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
  parent, and a lane closes when its commit is reached.
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
    """Assign every node a row and a lane, walking newest to oldest."""
    lanes: list[str | None] = []  # lane -> the sha it is waiting for
    rows = []
    for row, node in enumerate(nodes):
        waiting = [i for i, expected in enumerate(lanes) if expected == node["id"]]
        if waiting:
            lane = waiting[0]
            for merged_in in waiting[1:]:
                lanes[merged_in] = None  # those branches end here
        else:
            lane = _free_lane(lanes)  # a tip: nothing was expecting it

        parents = node["parents"]
        lanes[lane] = parents[0] if parents else None
        for parent in parents[1:]:  # a merge forks a lane per extra parent
            if parent not in lanes:
                lanes[_free_lane(lanes)] = parent

        rows.append({**node, "row": row, "lane": lane})
    return rows


def _edges(rows: list[dict]) -> list[dict]:
    """One path per parent link. Which end bends depends on who owns the lane
    below the child:

    * A **merge's extra parent** (`parents[1:]`) has to leave the child's lane
      at once — the first parent keeps that lane going down, so anything else
      lingering in it would draw straight over the first-parent line and any
      commit sitting on it. So these bend immediately and then run straight
      down the *target* lane. Lanes opening to the right (a fresh merge lane)
      do the same.
    * A **child rejoining its own parent** (its first/only parent, moving left)
      owns its lane all the way down — nothing else is in it — so it runs
      straight down that lane and bends into the parent at the very end.

    Either way the long stretch sits in a lane of its own instead of running
    over someone else's."""
    at = {row["id"]: row for row in rows}
    edges = []
    for row in rows:
        x0, y0 = _x(row["lane"]), _y(row["row"])
        for index, parent in enumerate(row["parents"]):
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
            x1, y1 = _x(target["lane"]), _y(target["row"])
            if target["lane"] == row["lane"]:
                d = f"M {x0},{y0} V {y1}"
            elif target["lane"] > row["lane"] or index > 0:
                # opening right, or a merge's extra parent heading down-left:
                # bend out of the child's lane now, then straight down the target
                bend = y0 + ROW
                d = f"M {x0},{y0} C {x0},{y0 + ROW / 2} {x1},{y0 + ROW / 2} {x1},{bend} V {y1}"
            else:
                # the child's own line rejoining its parent: stay, bend at the end
                bend = max(y0, y1 - ROW)
                d = f"M {x0},{y0} V {bend} C {x0},{bend + ROW / 2} {x1},{bend + ROW / 2} {x1},{y1}"
            edges.append(
                {
                    "d": d,
                    "color": _color(max(row["lane"], target["lane"])),
                    "lanes": sorted({row["lane"], target["lane"]}),
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
    width = _x(max((row["lane"] for row in rows), default=0)) + PAD
    return {
        "rows": rows,
        "edges": _edges(rows),
        "width": width,
        "height": len(rows) * ROW,
        "row_height": ROW,
        "dot": DOT,
        "collapsed": sum(row["count"] - 1 for row in rows if row["kind"] == "gap"),
    }

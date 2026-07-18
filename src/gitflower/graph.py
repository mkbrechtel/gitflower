"""Lane layout for the commit graph on the repo page.

Ported from cyblox's apps/cyblox_portal/graph.py (same author). Pure
geometry: commits in, SVG coordinates out — no git, no I/O. The input is the
commit list from gitread.commits(), which comes child-before-parent; that
ordering is what makes a single forward pass enough.

Three things happen here:

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
* **untangle** — the forward pass hands out columns greedily (leftmost free
  lane wins), which can leave lines crossing each other for no reason. A
  post-pass reorders the columns right of the pinned block to minimize
  the number of edge crossings, then the sideways travel. The pinned
  branches' reserved leftmost columns never move; the travel tiebreak
  pulls every other line toward the lanes it forks from, folds into, and
  merges from — a short-lived branch ends up hugging the pinned block,
  not parked at the far edge. Moving a column wholesale keeps every
  invariant the forward pass established — a corridor's guaranteed-empty
  stretch travels with its column — so the result is the same graph,
  combed.
"""

import zlib

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


def _branch_color(branch: str | None, trunk: str | None, lane: int) -> str:
    """The trunk always wears the accent; other branches hash their name to
    a stable non-accent colour, so a line keeps its colour across reloads
    even as lanes shuffle. Unattributed lines fall back to lane colours."""
    if branch is None:
        return _color(lane)
    if branch == trunk:
        return COLORS[0]
    return COLORS[1 + zlib.crc32(branch.encode()) % (len(COLORS) - 1)]


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


def _place(nodes: list[dict], branch_of: dict[str, str], pin_lane: dict[str, int]) -> list[dict]:
    """Assign every node a row and a lane, walking newest to oldest — and
    record, for every merge's extra parent, the **corridor**: the lane its
    link line travels. A lane that is waiting for a sha never receives any
    other commit, so a corridor is collision-free by construction; _edges
    routes the link down it and folds into the parent's dot at the end.

    A fresh corridor is inserted directly beside the child whenever the
    lanes it would shift hold nothing drawn yet — the link then runs
    parallel to its neighbours instead of crossing them.

    Branch attribution (`branch_of`, may be empty) refines two guesses:
    the leftmost lanes are held for the pinned branches whose commits are
    shown — one lane each, per `pin_lane` — and a commit with several lanes
    waiting for it lands on its own branch's lane instead of simply the
    leftmost.

    Every row and corridor also gets a **segment** id: one id per
    continuous line, from the row or merge that opens a lane to the fold
    or root that closes it. A lane reused later is a new segment. The
    untangle pass moves segments, not lanes — two lines that happen to
    share a column at different times are free to part ways."""
    lanes: list[str | None] = []  # lane -> the sha it is waiting for
    fresh: list[int | None] = []  # reserved-at row, while no dot sits on the lane
    lane_branch: list[str | None] = []  # the branch whose line rides the lane
    lane_seg: list[int | None] = []  # the segment whose line rides the lane
    pending: list[list] = []  # [child row dict, parent sha, corridor lane, segment]
    rows: list[dict] = []
    reserved = len(pin_lane)
    segments = 0

    def grow() -> int:
        lanes.append(None)
        fresh.append(None)
        lane_branch.append(None)
        lane_seg.append(None)
        return len(lanes) - 1

    def free_lane(branch: str | None) -> int:
        for i in range(reserved, len(lanes)):
            if lanes[i] is None:
                return i
        while len(lanes) < reserved:
            grow()  # keep the reserved lanes held for the pinned branches
        return grow()

    def corridor_lane(after: int) -> int:
        """A lane for a new parent link: right beside the child when the
        shift moves nothing already drawn (never inside the reserved
        columns), else the leftmost free lane beyond it, else the far
        right."""
        pos = max(after + 1, reserved)
        while len(lanes) < pos:
            grow()  # an insert beyond the end would clamp and skew the index

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
            lane_branch.insert(pos, None)
            lane_seg.insert(pos, None)
            for link in pending:
                if link[2] >= pos:
                    link[2] += 1
            return pos
        for i in range(pos, len(lanes)):
            if lanes[i] is None:
                return i
        return grow()

    for row, node in enumerate(nodes):
        branch = branch_of.get(node["id"])
        waiting = [i for i, expected in enumerate(lanes) if expected == node["id"]]
        pin = pin_lane.get(branch)
        if pin is not None:
            while len(lanes) <= pin:
                grow()
        if pin is not None and (lanes[pin] is None or pin in waiting):
            # a pinned branch lives on its reserved lane — claim it whenever
            # it is open, even if branch lines were waiting for this commit
            # elsewhere (they fold into the dot here, like any convergence)
            lane = pin
        elif waiting:
            # of the lanes expecting this commit, its own branch's line
            # gets the dot; the others fold into it
            matched = [i for i in waiting if branch is not None and lane_branch[i] == branch]
            lane = (matched or waiting)[0]
        else:
            lane = free_lane(branch)  # a tip: nothing was expecting it
        if lane in waiting:
            seg = lane_seg[lane]  # the line waiting here continues
        else:
            seg, segments = segments, segments + 1  # a line begins
        for merged_in in waiting:
            if merged_in != lane:
                lanes[merged_in] = None  # those branches end here
                fresh[merged_in] = None
                lane_branch[merged_in] = None
                lane_seg[merged_in] = None

        # links waiting for this commit now know their final corridor
        for link in pending:
            if link[1] == node["id"]:
                link[0]["corridors"][link[1]] = link[2]
                link[0]["corridor_seg"][link[1]] = link[3]
        pending = [link for link in pending if link[1] != node["id"]]

        placed = {
            **node,
            "row": row,
            "lane": lane,
            "branch": branch,
            "seg": seg,
            "corridors": {},
            "corridor_seg": {},
        }
        parents = node["parents"]
        lanes[lane] = parents[0] if parents else None
        fresh[lane] = None  # a dot sits here; the stretch below hangs off it
        lane_branch[lane] = branch
        lane_seg[lane] = seg if parents else None
        for parent in parents[1:]:  # a merge forks a lane per extra parent
            if parent in lanes:
                corridor = lanes.index(parent)  # ride the parent's own line
                corridor_seg = lane_seg[corridor]
            else:
                corridor = corridor_lane(lane)
                corridor_seg, segments = segments, segments + 1
                lanes[corridor] = parent
                fresh[corridor] = row
                # a corridor is a link, not a branch line — left unattributed
                # so the dot prefers the parent's real line when one waits
                lane_branch[corridor] = None
                lane_seg[corridor] = corridor_seg
            pending.append([placed, parent, corridor, corridor_seg])

        rows.append(placed)
    return rows


def _strands(rows: list[dict]) -> tuple[list[tuple], dict[int, list[int]], dict[int, list[int]]]:
    """The layout's geometry, reduced to what can cross: **bends** — the one
    row-gap where an edge slides sideways, `(gap, from line, to line)` —
    and **runs** — per row-gap, the lines passing straight through. Lines
    are named by segment id, not lane, so the untangle pass can move each
    line on its own. Also gathered: every segment's row **extent**, the
    stretch it needs its column for — two segments may share a column
    exactly when their extents do not meet. The case analysis mirrors
    _edges; a gap `g` is the space between rows `g` and `g+1`."""
    at = {row["id"]: row for row in rows}
    bends: list[tuple] = []
    runs: dict[int, list[int]] = {}
    extents: dict[int, list[int]] = {}

    def touch(seg: int, top: int, bottom: int) -> None:
        span = extents.setdefault(seg, [top, bottom])
        span[0], span[1] = min(span[0], top), max(span[1], bottom)

    def run(seg: int, top: int, bottom: int) -> None:
        touch(seg, top, bottom)
        for gap in range(top, bottom):
            runs.setdefault(gap, []).append(seg)

    def bend(gap: int, top_seg: int, bottom_seg: int) -> None:
        touch(top_seg, gap, gap)  # the bend leaves its column at the gap
        bends.append((gap, top_seg, bottom_seg))

    for row in rows:
        r0, sc = row["row"], row["seg"]
        touch(sc, r0, r0)
        for parent in row["parents"]:
            target = at.get(parent)
            if target is None:
                run(sc, r0, r0 + 1)  # the truncation stub hangs into the gap
                continue
            corridor = row["corridors"].get(parent, row["lane"])
            sk = row["corridor_seg"].get(parent, sc)
            r1, plane, sp = target["row"], target["lane"], target["seg"]
            if corridor == row["lane"] == plane:
                run(sc, r0, r1)
            elif corridor == row["lane"]:
                run(sc, r0, r1 - 1)
                bend(r1 - 1, sc, sp)
            elif corridor == plane:
                bend(r0, sc, sk)
                run(sp, r0 + 1, r1)
            elif r1 - r0 == 1:
                bend(r0, sc, sp)
            else:
                bend(r0, sc, sk)
                run(sk, r0 + 1, r1 - 1)
                bend(r1 - 1, sk, sp)
    return bends, runs, extents


def _columns(rows: list[dict]) -> dict[int, int]:
    """Each segment's column, read off the placed rows and corridors. A
    corridor whose parent fell past the truncation limit resolves to no
    drawn geometry at all and stays absent — there is nothing to move."""
    col: dict[int, int] = {}
    for row in rows:
        col[row["seg"]] = row["lane"]
        for parent, seg in row["corridor_seg"].items():
            col.setdefault(seg, row["corridors"][parent])
    return col


def _rivals(bends: list[tuple], runs: dict[int, list[int]]) -> list[tuple]:
    """Every pair of lines that shares a row-gap and so *could* cross,
    flattened to 4-tuples of segments `(top, bottom, top', bottom')`.
    Which pairs exist never changes while lines change columns — only
    where each line sits does — so the search precomputes this once and
    re-scores assignments cheaply. A straight run is a bend that goes
    nowhere; runs never meet other runs (two lines cannot converge
    without bending), so only bend×run and bend×bend pairs are kept."""
    pairs: list[tuple] = []
    by_gap: dict[int, list[tuple[int, int]]] = {}
    for gap, top, bottom in bends:
        for seg in set(runs.get(gap, ())):
            pairs.append((top, bottom, seg, seg))
        by_gap.setdefault(gap, []).append((top, bottom))
    for group in by_gap.values():
        for i, (t1, b1) in enumerate(group):
            for t2, b2 in group[i + 1 :]:
                pairs.append((t1, b1, t2, b2))
    return pairs


def _tangles(pairs: list[tuple], col: list[int]) -> int:
    """How many rival pairs cross when segment `s` sits on column `col[s]`.
    Two lines sharing a row-gap cross when their order flips between the
    gap's top and bottom: `(top - top') * (bottom - bottom') < 0`. Shared
    endpoints (a fan-in folding into one dot) give zero, not a crossing."""
    return sum(
        1 for t1, b1, t2, b2 in pairs if (col[t1] - col[t2]) * (col[b1] - col[b2]) < 0
    )


def _untangle(rows: list[dict], reserved: int) -> None:
    """Move the lines so the edges cross as few times as possible — and
    among equal-crossing layouts, travel sideways the least and keep left.
    The forward pass fixed everything that matters — what is a line, where
    corridors run — so lines can change columns freely without breaking
    any of it. The pinned branches' reserved columns stay the leftmost,
    untouched; crossings over them that only moving a reserved column
    could undo are the accepted price. Everything else optimizes within
    that restraint, at two grains: whole columns swap or slide past each
    other, and a single segment hops to any column whose occupants don't
    overlap its rows — so a short-lived branch ends up right beside the
    pinned block it merges into, even when the column that greedily held
    it must stay out for other lines. Hill-climb, keeping strict
    improvements, until no move helps (or the eval budget runs out — each
    improvement lowers a bounded non-negative score, so this
    terminates)."""
    width = 1 + max(
        (max(row["lane"], *row["corridors"].values(), 0) for row in rows), default=0
    )
    if width - reserved < 2:
        return
    bends, runs, extents = _strands(rows)
    if not bends:
        return  # nothing bends, so nothing can cross and nothing travels
    pairs = _rivals(bends, runs)
    col = _columns(rows)
    movable = sorted(seg for seg, c in col.items() if c >= reserved)

    def scored(assign: dict[int, int]) -> tuple[int, int, int]:
        wire = sum(abs(assign[top] - assign[bottom]) for _, top, bottom in bends)
        return (_tangles(pairs, assign), wire, sum(assign.values()))

    def fits(seg: int, target: int) -> bool:
        lo, hi = extents[seg]
        return not any(
            other != seg
            and col[other] == target
            and extents[other][0] <= hi
            and lo <= extents[other][1]
            for other in extents
        )

    best = scored(col)
    # each trial costs one pass over the rival pairs, so a dense graph gets
    # fewer trials — pages must render even when the history is spaghetti
    budget = max(64, min(4000, 1_000_000 // max(1, len(pairs))))
    improved = True
    while improved and budget > 0:
        improved = False
        # whole columns swap or slide past each other…
        for i in range(reserved, width):
            for j in range(reserved, width):
                if i == j or budget == 0:
                    continue
                if j > i:  # slide column i out to j…
                    remap = {c: j if c == i else c - 1 if i < c <= j else c for c in range(width)}
                else:  # …or back in before it
                    remap = {c: j if c == i else c + 1 if j <= c < i else c for c in range(width)}
                trial = {seg: remap[c] for seg, c in col.items()}
                budget -= 1
                score = scored(trial)
                if score < best:
                    col, best, improved = trial, score, True
                elif j > i and budget > 0:  # the plain swap of the two
                    trial = {seg: j if c == i else i if c == j else c for seg, c in col.items()}
                    budget -= 1
                    score = scored(trial)
                    if score < best:
                        col, best, improved = trial, score, True
        # …and single lines hop to any column with room for their rows
        for seg in movable:
            for target in range(reserved, width):
                if budget == 0 or target == col[seg] or not fits(seg, target):
                    continue
                trial = dict(col)
                trial[seg] = target
                budget -= 1
                score = scored(trial)
                if score < best:
                    col, best, improved = trial, score, True
    for row in rows:
        row["lane"] = col[row["seg"]]
        row["corridors"] = {p: col[s] for p, s in row["corridor_seg"].items()}


def _edges(rows: list[dict], trunk: str | None = None) -> list[dict]:
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
                        "color": _branch_color(row["branch"], trunk, row["lane"]),
                        "lanes": [row["lane"]],
                        "stub": True,
                        "dimmed": row.get("dimmed", False),
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
            line = row["branch"] if corridor == row["lane"] else target["branch"]
            edges.append(
                {
                    "d": d,
                    "color": _branch_color(line, trunk, corridor),
                    "lanes": sorted({row["lane"], corridor, target["lane"]}),
                    "stub": False,
                    "dimmed": row.get("dimmed", False),
                }
            )
    return edges


def build(
    commits: list[dict],
    tips: set[str],
    collapse: bool = True,
    branch_of: dict[str, str] | None = None,
    trunk: str | None = None,
    pinned: list[str] | None = None,
    dimmed: set[str] | None = None,
) -> dict:
    """Lay out `commits` (newest first, parents after children). `tips` are the
    shas a ref points at — they are never folded away. `branch_of` (from
    gitread.born_on) attributes commits to branches: the trunk keeps the
    accent colour, every branch keeps a stable colour of its own. `pinned`
    branches (exact names, in display order) hold the leftmost lanes and
    their commits render as filled dots; without it the trunk alone holds
    lane 0 — either way the remaining columns are then reordered to
    minimize edge crossings, lines settling as close as possible to the
    lanes they interact with. `dimmed` shas (commits only hidden branches
    reach) grey out."""
    pin_order = list(pinned) if pinned else ([trunk] if trunk else [])
    nodes = _collapse(commits, tips, MIN_COLLAPSE if collapse else len(commits) + 1)
    present = {(branch_of or {}).get(node["id"]) for node in nodes}
    pin_lane = {b: i for i, b in enumerate(b for b in pin_order if b in present)}
    rows = _place(nodes, branch_of or {}, pin_lane)
    _untangle(rows, len(pin_lane))
    pin_set = set(pinned or [])
    dimmed = dimmed or set()
    for row in rows:
        row["x"] = _x(row["lane"])
        row["y"] = _y(row["row"])
        row["color"] = _branch_color(row["branch"], trunk, row["lane"])
        row["pinned"] = row["branch"] in pin_set
        if row["kind"] == "gap":
            row["dimmed"] = row["first"]["sha"] in dimmed and row["last"]["sha"] in dimmed
        else:
            row["dimmed"] = row["id"] in dimmed
    edges = _edges(rows, trunk)
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

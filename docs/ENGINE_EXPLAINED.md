# How the routing engine works

This is the plain-English version of `backend/pathable/engine/cost.py` and
`backend/pathable/engine/search.py`. Read this before the demo; the code is commented so
you can point to the exact place a choice is made.

## 1. The graph

OpenStreetMap is turned into a **directed multigraph**:

- Each intersection or geometry node is a graph node.
- Each walkable way segment is a directed edge. A two-way sidewalk contributes two
  edges, one in each direction.
- `MultiDiGraph` means two edges can connect the same pair of nodes (for example, a
  sidewalk and a parallel path). The engine considers each edge separately, so the
  cheaper one can win.

Two objectives are computed for the same request:

- **Shortest**: minimize length only. This is the comparison route. It is allowed to use
  steps, restricted access, or anything else; it is useful precisely because it shows
  what a naive router would do.
- **Preferred**: minimize the user's generalized cost. Hard blocks remove edges from
  this search only.

## 2. From OSM tags to features

`graph/features.py` normalizes tags into an `EdgeFeatures` object. The normalization
rules are deliberately conservative:

- **Lists.** OSMnx simplification can merge ways and turn a tag into a list. If values
  disagree:
  - any `steps` value makes the edge steps;
  - the roughest surface class wins;
  - the narrowest width wins;
  - contradicting incline directions make the sign unknown.
- **Direction.** `incline=up` is relative to the OSM way direction. OSMnx marks the
  reverse edge with `reversed=True`; the sign is flipped there. A test builds a
  two-direction edge and checks that the uphill cost differs by direction.
- **Missing is unknown.** Absence is stored as `None` + `Provenance.UNKNOWN`. The cost
  model prices that risk; it never treats missing as "fine".
- **Elevation.** A mapped incline is used first. If it is missing, a DEM estimate may
  fill it, marked `DEM_ESTIMATED`. If the edge is shorter than the DEM resolution or the
  implied grade is implausible, it stays unknown. DEM grades never hard-block.

## 3. Cost: a breakdown, not a number

`compute_edge_cost` builds a `CostBreakdown`:

```
base length + each multiplier's added m-eq + each fixed penalty = total m-eq
```

Each term records:

- its name (`grade`, `surface`, `unknown_width`, …),
- whether it is a multiplier or a fixed penalty,
- its value and the resulting m-eq,
- a human-readable reason,
- the provenance of the input.

A hard block is a separate field, not infinity. The segment inspector can therefore show
"BLOCKED - mapped steps (highway=steps)" and still show the base length and any terms
computed before the block.

The unit is **meter-equivalents**. A multiplier of 1.25 on 100 m adds 25 m-eq; a fixed
penalty of 100 m-eq means "as bad as another 100 m of ideal walking."

## 4. Search

### Dijkstra

Dijkstra expands the node with the smallest known cost. It is the reference algorithm:
with non-negative edge costs, it finds the minimum. The implementation keeps a best-cost
dictionary, a predecessor dictionary, and a heap. A monotonic counter breaks ties, and
neighbors are visited in sorted order, so equal-cost paths resolve deterministically.

### A*

A* is Dijkstra plus a guess of the remaining cost. The guess here is the haversine
distance from the current node to the goal. For the **length** objective, the guess is
exactly a lower bound on the remaining length. For the **cost** objective, every edge
costs at least its length, so the remaining cost is also at least the remaining straight-
line distance. The guess never overestimates.

That makes the heuristic **admissible**. It is also consistent: moving along an edge can
reduce the straight-line distance by at most that edge's length, and length ≤ cost. A*
therefore returns the same optimal cost as Dijkstra. The test suite checks this on random
graphs (Hypothesis) and compares both with NetworkX's shortest-path oracle.

### Snap

`snap_to_node` finds the nearest routable node by haversine distance. It returns the
distance and refuses if it is greater than `routing.max_snap_m` (default 300 m). The
response includes the snap distances so the user knows the route starts at the network,
not at the exact address pin. Ties are broken by node ID for reproducibility.

### No route

If the preferred search finds nothing, the API returns a structured `NoFeasibleRoute`
with a reason. It does not silently relax a hard constraint. If a relaxed alternative is
offered, it is labeled, lists which constraints were relaxed, and is never presented as a
normal result. A disconnected graph and "only connections contain steps" are different
cases.

## 5. Reports and sensitivity

Community reports are turned into fixed per-edge penalties before the search. A report
influences edges whose midpoint is within 40 m, while it is unverified or reviewed and
not expired. Unverified reports count half; resolved/rejected count zero. The report IDs
appear in the explanation.

The sensitivity view reruns the preferred search at nearby values of one setting (for
example ±1 percentage point of the hard slope limit). It uses the same start, end,
profile, risk, and reports; only that setting changes. It is a deterministic check, not a
prediction. This is how the interface can say "at 7.3% the route is unchanged" instead of
guessing.

## 6. Why not just use NetworkX?

NetworkX is an excellent graph library, but the project's point is the cost model and the
explanation. Implementing the search directly makes the objective and the admissibility
argument visible, lets the engine return the explored count and the exact edge sequence,
and avoids hiding a profile-specific decision inside a library call. NetworkX is still
used in the tests as an independent oracle, which is a stronger check than comparing the
implementation with itself.

## 7. Limits

- The graph is only as good as OSM. A missing sidewalk may mean no route, not a blocked
  one.
- Snapping to the nearest node can put the start on the wrong side of a street. The
  response exposes the snap distance; the UI does not hide it.
- DEM grades are coarse and cannot see a curb, a bridge deck, or a temporary obstruction.
- The sensitivity check varies one setting at a time. It does not explore every
  combination of settings.
- The search minimizes a scalar cost. It cannot know whether a particular ramp is usable
  by a particular chair, or whether a user will feel safe on a given block.

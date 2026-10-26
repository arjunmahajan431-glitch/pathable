# The cost model

`backend/pathable/engine/cost.py` returns a **breakdown**, not a bare number. This
document explains the units, the order of operations, and the invariant that keeps A*
correct. Defaults and their sources are in `docs/STANDARDS.md`.

## Units: meter-equivalents

One **m-eq** is the effort of walking one meter on an ideal path: flat, smooth, fully
mapped, no barrier, no crossing. A fixed penalty of 100 m-eq means "as bad as walking an
extra 100 m on that ideal path."

Every multiplier is dimensionless and **≥ 1**. Every fixed penalty is **≥ 0**. Nothing
in the cost model gives a discount. This is deliberate: it makes the cost easy to
explain, keeps "stricter profile never cheaper" true, and keeps haversine admissible for
A*.

For one directed edge:

```
cost = length_m × multiplier_1 × … × multiplier_n + penalty_1 + … + penalty_m
```

A hard block is a separate `hard_block` flag. It is **not** `inf`, `NaN`, or a magic
negative number. The breakdown still includes base length and any terms computed before
the block, so the inspector can explain why the edge fails.

### What a 5% slope means in plain language

A 5% slope rises 5 cm for every 1 m you walk (a 1 in 20 grade). It is not a 5% chance of
anything, and it is not 5 degrees. The wheelchair profile uses **5.0% as a soft
threshold**: at or below 5%, slope adds no cost. Above 5%, each extra percent adds 25% of
that segment's length to its effort score, until the 8.33% hard limit. For example, a
6% grade on a 100 m segment adds 25 m-eq. Above 8.33%, a mapped grade blocks the
wheelchair profile; a DEM-estimated grade is penalized but never blocks, because 30 m
elevation data is not a sidewalk measurement.

Risk settings also use percentages. **Direct** prices an unknown value at one third
(33%) of its balanced price, **Balanced** at the full price (100%), and **Cautious** at
2.67 times the price (267%). These numbers scale only the price of missing data. They
never turn an unknown into "safe" or into a barrier.

## Application order

The order is fixed and reflected in the interface:

1. Access / foot restrictions (hard block when mapped as prohibited).
2. Barriers (impassable barriers block; passable barriers add a fixed penalty).
3. Steps (block or penalize, per profile).
4. Unknown steps (multiplier when `highway` is absent).
5. OSM `wheelchair=no` (block if the profile respects it) or `wheelchair=limited`.
6. Grade (uphill or downhill, using the signed directed grade).
7. Surface / smoothness roughness (multiplier), plus unknown-surface and
   unknown-smoothness multipliers.
8. Width (multiplier if mapped below the profile minimum; unknown-width multiplier if
   not mapped).
9. Crossings: kerb penalty at the arrival node, crossing-control penalty, unknown terms.
10. Lighting, if the profile prefers lit paths.
11. Community reports within the influence radius.

## Terms

### Grade

- At or below the soft threshold: no term.
- Between soft and hard: multiplier `1 + factor × (|grade| − soft)`.
- Above hard:
  - a **mapped** grade can hard-block when `hard_grade_action = "block"`;
  - a **DEM-estimated** grade never hard-blocks, because 30 m elevation data is not a
    sidewalk measurement. It gets the capped multiplier plus
    `hard_grade_penalty_m × dem_confidence` (default 0.6).
  - a profile can choose `"penalize"` instead of blocking even for mapped grades.
- Unknown grade: multiplier `1 + unknown_grade_factor × risk_scale`.

The signed grade is directional. `incline=up` is relative to the OSM way direction;
`reversed=True` edges flip it. If merged tags disagree about direction, the magnitude may
survive but the sign becomes UNKNOWN; the cost model then uses the unknown-grade term.

### Roughness

`surface` and `smoothness` are both mapped to one of four classes; the **worst** class
wins. Multipliers are per profile (wheelchair 1.0 / 1.35 / 2.2 / 4.0). If neither tag is
recognized, the class is unknown and the unknown-surface/unknown-smoothness multipliers
apply. The class table is in `backend/pathable/graph/features.py`.

### Width

If mapped width is below `min_width_m`:

```
multiplier = 1 + width_penalty_factor × (min_width_m − width_m) / min_width_m
```

With the default factor 0.5, a zero-width edge would only reach 1.5×; the width term is
intended to express discomfort, not to pretend a measurement is a hard barrier. A
zero-width value is almost certainly bad data, so it is treated as a strong penalty
rather than a block.

### Kerbs and crossings

Only crossing edges are charged. `kerb=lowered|flush|no` is free. `raised|yes|damaged`
adds the raised-kerb penalty. Missing/unknown adds
`kerb_unknown_penalty_m × risk_scale`. Crossing control adds a fixed penalty for
uncontrolled/unmarked crossings, or a smaller unknown penalty when the type is missing.

The kerb comes from the **arrival node** of the directed edge (`v`). Each direction has
its own arrival node, so an edge in the opposite direction can have a different kerb
cost.

### Community reports

Each report has a category penalty from the profile. The weight is:

| Status | Weight |
|---|---:|
| `reviewed` | 1.0 |
| `unverified` | 0.5 |
| `resolved` | 0.0 |
| `rejected` | 0.0 |

Only reports within `reports.influence_radius_m` of an edge midpoint and confirmed
within `reports.expiry_days` are included. Multiple reports on one edge sum. The report
IDs and the half-weight rule appear in the explanation, so the user can see that the
influence is not a verified fact.

### Hard blocks

Hard blocks are used for:

- mapped `access`/`foot` restrictions that prohibit public pedestrian use;
- impassable mapped barriers (stile, turnstile, kissing gate, block, log, debris);
- mapped `highway=steps` when the profile's `steps = "block"`;
- mapped `wheelchair=no` when the profile respects that tag;
- mapped grades above the hard limit when the profile chooses `"block"`.

An unknown value never hard-blocks. It is priced as risk. A missing kerb is not a
missing ramp; it is an unknown.

## Why cost ≥ length (and why A* stays correct)

Every multiplier is ≥ 1, so the product is ≥ 1 and `length × product ≥ length`. Every
penalty is ≥ 0, so adding penalties cannot reduce cost. Therefore every directed edge's
cost is at least its length.

A* uses the haversine distance to the goal as its heuristic. The true remaining cost from
any node is at least the true remaining **length**, which is at least the straight-line
haversine distance (earth geometry). The heuristic is therefore admissible: it never
overestimates the remaining cost. With non-negative edge costs, A* returns an optimal
route. `tests/test_search.py` also compares A* with Dijkstra and with a NetworkX oracle
on random graphs.

## Worked examples

The synthetic diamond fixture (`backend/tests/fixtures/diamond.py`) is the hand-checked
oracle. With the test profile:

| Route | Length | Cost | Why |
|---|---:|---:|---|
| 1 via A | 300 m | blocked | last edge is mapped steps |
| 2 via B | 380 m | 405 m-eq | 280 m flat + 100 m at 6% → 100 × 1.25 |
| 3 via C | 340 m | 640 m-eq | 190 m flat + 150 m very rough × 3.0 |
| 4 via D | 520 m | 545 / 595 / 720 | 520 + unknown-kerb penalty 25 / 75 / 200 |

These values are hard-coded in the tests with the arithmetic in comments. They are not
derived by running the implementation. See `tests/test_cost.py` and
`tests/test_search.py`.

The demo route in the interface is real sample-graph data (Woodbury, Minnesota): the
length-only route is 1,035 m and uses a segment whose DEM-estimated uphill grade is
9.3%, above the wheelchair profile's 8.3% threshold. The preferred route is 1,173 m
(+13%) and takes a gentler way around. The interface's numbers are produced by the same
cost function, not by a special demo path.

## What the model deliberately does not do

- It does not model camber, cross slope, tactile paving quality, door widths, or indoor
  navigation. Those are out of scope.
- It does not claim that a low-cost route is accessible. It prices the attributes it
  knows and the gaps it does not.
- It does not learn from users or call an external text service. Every explanation is a
  template filled from the breakdown.

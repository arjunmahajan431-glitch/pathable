# Data coverage

Coverage answers one narrow question:

> For this route and this profile, what fraction of the route's length has a **known**
> value for each attribute the cost model uses?

It does **not** answer "is this route accessible?" or "is this route safe?". A route can
have 100% coverage and still be unusable, because a known value can describe a barrier.
A route can have 20% coverage and be the best available option, because unknown values
are priced as risk rather than assumed safe.

## Definition

For each relevant attribute `a` on a route:

```
coverage_a = (sum of lengths of edges whose provenance for a is not UNKNOWN)
             / (sum of lengths of all relevant edges)
```

- The denominator is length in meters, so a long block counts more than a short curb
  ramp. This is intentional: a missing width tag on a 100 m path is a bigger gap than a
  missing width tag on a 3 m crossing.
- `kerb` is only counted on crossing edges. Its denominator is the crossing length, not
  the whole route. This is shown in the interface as a note.
- `lit` is only included when the active profile has `avoid_unlit = true`.
- `coverage` is `null` when the denominator is zero (e.g. a route with no crossings has
  no kerb denominator).
- **Overall coverage** is the unweighted mean of the per-attribute coverages that are
  not `null`. This gives each attribute equal influence; it is not a length-weighted
  average across attributes.

## Relevant attributes

| Attribute | Known when | Notes |
|---|---|---|
| `steps` | `highway` is present in OSM (including `steps`) | A missing `highway` is unknown. |
| `surface` | a recognized OSM `surface` value exists | Unknown values are not silently treated as smooth. |
| `smoothness` | a recognized OSM `smoothness` value exists | |
| `width` | a parseable width exists | Field audit width overrides OSM and is `FIELD_AUDIT`. |
| `grade` | a mapped incline, a trusted DEM estimate, or a field measurement exists | DEM estimates count as known, but are labeled. |
| `kerb` | a recognized node `kerb` exists on a crossing | Only crossing edges are in the denominator. |
| `lit` | a recognized `lit` value exists | Only for profiles that prefer lighting. |

## Provenance and confidence

Coverage treats `DEM_ESTIMATED` as known because it is a value with a documented source.
That does **not** make it a sidewalk measurement. The UI says:

> Some slopes are estimated from 30 m elevation data; this is not a measurement of the
> sidewalk and can be wrong near bridges, underpasses and buildings.

`FIELD_AUDIT` is the highest tier. `OSM_MAPPED` is next. `COMMUNITY_REPORT` is not an
attribute value; it is a separate influence on cost and is labeled unverified/reviewed.
`UNKNOWN` is the absence of a value and is priced by the risk setting.

## Worked example

Suppose a preferred route has:

- 100 m of edge with known surface and 100 m without → surface coverage 50%.
- 200 m total, all edges have a known `highway` → steps coverage 100%.
- One 10 m crossing with an unknown kerb and one 10 m crossing with `kerb=lowered` →
  kerb coverage 50% (denominator is 20 m, not 200 m).
- No width tags → width coverage 0%.

The per-attribute values are 50%, 100%, 50%, 0%; overall is the unweighted mean of the
non-null values, 50%. That overall number is **not** a safety score.

## Where it appears

- API: each `RouteOut.coverage` has `attributes` and `overall`.
- Frontend: comparison cards, the "Data coverage by attribute" disclosure, and the
  segment inspector.
- Evaluation: `scripts/evaluate.py` averages per-route coverage across seeded routes and
  writes the table to `docs/EVALUATION.md` (Woodbury) and
  `docs/EVALUATION-saint-paul-mn.md` (Saint Paul). Those tables are descriptive, not
  benchmarks.

## Reporting rule

If you quote coverage in the demo video or submission, say what it measures:
"X% of this route's length has a mapped value for the attributes this profile uses;
that is a mapping statistic, not a safety or accessibility rating." Do not call a
low-coverage route "unknown, therefore unsafe" or a high-coverage route "accessible".

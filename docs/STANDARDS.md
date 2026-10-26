# Defaults, sources, and scope

PathAble packages two starting profiles. **Every default below is adjustable in the
interface.** This file records where each number came from and, just as importantly,
what it does *not* mean. It is not legal, medical, or engineering advice.

Checked: **2026-10-25**. Sources are linked; section numbers are the ones shown on the
publisher's page at that time.

## The short version

- The **5% running slope** starting point matches the pedestrian-route guidance in
  PROWAG R302.4 and the ADA Standards' walking-surface slope (§403.3), both 1:20.
- The **8.33% hard slope** is the maximum for a **curb ramp or ramp run**, not a universal
  legal limit for every sidewalk. PathAble uses it only as an initial warning/block
  reference because it is familiar and easy to explain. It is adjustable.
- The **1.22 m width** starting point is PROWAG R302.2's continuous clear width for a
  pedestrian access route. The ADA Standards' 36 in (0.915 m) value for accessible
  routes on a site is shown for comparison, not used as the default.
- PROWAG's legal force depends on adoption. The Access Board publishes it as guidance;
  DOT adopted it for transit stops in the public right-of-way in December 2024, and GSA
  adopted it in July 2024. It is **not** a universal federal mandate for every sidewalk
  in every jurisdiction. The 2010 ADA Standards remain the enforceable federal standard
  for facilities and site elements they cover.
- Numbers marked **ASSUMPTION** are project choices. They are not measurements, standards,
  or medical recommendations. Change them for your body, equipment, and judgement.

## Sources

1. U.S. Access Board, *2010 ADA Standards for Accessible Design*, Chapter 4,
   <https://www.access-board.gov/ada/chapter/ch04/>.
2. U.S. Department of Justice, *2010 ADA Standards for Accessible Design*,
   <https://www.ada.gov/law-and-regs/design-standards/2010-stds/> (published
   September 15, 2010).
3. U.S. Access Board, *Guide to the ADA Accessibility Standards, Chapter 4: Ramps and
   Curb Ramps*, <https://www.access-board.gov/ada/guides/chapter-4-ramps-and-curb-ramps/>.
4. U.S. Access Board, *Public Right-of-Way Accessibility Guidelines (PROWAG)*, About page,
   <https://www.access-board.gov/prowag/> (final rule August 8, 2023; DOT transit-stop
   adoption December 18, 2024; GSA adoption July 3, 2024).
5. U.S. Access Board, *PROWAG Chapter 3: Technical Requirements*,
   <https://www.access-board.gov/prowag/technical.html>.
6. OpenStreetMap Wiki, key documentation for `highway`, `footway`, `surface`,
   `smoothness`, `incline`, `kerb`, `crossing`, `width`, `access`, and `wheelchair`
   (used for tag semantics, not for engineering limits).

## Default table

| Setting | Default | Source and section | Scope | Type | Why this value |
|---|---:|---|---|---|---|
| Wheelchair `soft_grade_up_pct` | 5.0% | PROWAG R302.4.1/R302.4.2 (1:20); ADA 2010 §403.3 (1:20) | Pedestrian access route / walking surface | Design guidance / standard | Starting point where a slope begins to add cost. |
| Wheelchair `hard_grade_up_pct` | 8.33% | ADA 2010 §405.2; PROWAG R304.2.1 (1:12) | **Ramp and curb-ramp runs only** | Design standard / guidance | Reference point for a strong warning or block; *not* a universal sidewalk limit. |
| Wheelchair `soft_grade_down_pct` | 8.0% | - | - | **ASSUMPTION** | Downhill tolerance is not the same as uphill; no standard was found that maps it to effort. |
| Wheelchair `hard_grade_down_pct` | 12.0% | - | - | **ASSUMPTION** | Adjustable; descent can be harder to control. |
| `grade_factor_up` | 0.25 per % | - | - | **ASSUMPTION** | At 6% with a 5% soft threshold the multiplier is 1.25; matches the hand-calculated fixture. |
| `grade_factor_down` | 0.15 per % | - | - | **ASSUMPTION** | Lower than uphill because the direction and control demands differ. |
| Wheelchair `min_width_m` | 1.22 m | PROWAG R302.2 (48 in / 1220 mm) | Pedestrian access route in public right-of-way | Design guidance | Public-sidewalk starting point. ADA 2010 §403.5.1 gives 36 in / 0.915 m for accessible routes on a site; that is narrower and is not used as the default. |
| Limited-mobility `min_width_m` | 1.22 m | PROWAG R302.2 | Pedestrian access route in public right-of-way | Design guidance | Same starting point; the user can lower it. |
| `surface_multipliers` | 1.0 / 1.35 / 2.2 / 4.0 | - | - | **ASSUMPTION** | Smooth / moderate / rough / very rough. OSM tags are mapped to classes in `backend/pathable/graph/features.py`; no standard converts surface type to effort. |
| `kerb_raised_penalty_m` | 150 m-eq | - | - | **ASSUMPTION** | A raised or damaged kerb at a crossing is a large fixed cost. |
| `kerb_unknown_penalty_m` | 100 m-eq | - | - | **ASSUMPTION** | Missing kerb data is priced as risk, then scaled by the risk setting. |
| `crossing_uncontrolled_penalty_m` | 20 m-eq | - | - | **ASSUMPTION** | Crossing without signal control is less predictable. |
| `crossing_unknown_penalty_m` | 10 m-eq | - | - | **ASSUMPTION** | Missing crossing type is a small risk price. |
| `walking_speed_mps` (wheelchair) | 0.80 m/s | - | - | **ASSUMPTION** | Used only for a labeled time estimate, never for route choice. |
| `walking_speed_mps` (limited mobility) | 1.10 m/s | - | - | **ASSUMPTION** | Same caveat. |
| Risk scale direct / balanced / cautious | 0.333 / 1.0 / 2.667 | - | - | **ASSUMPTION** | Multiplies the unknown-attribute and unknown-kerb prices. |
| `max_snap_m` | 300 m | - | - | **ASSUMPTION** | Refuse to route if a point is farther than this from the network. A larger limit can attach a point to a farther path; the response returns the snap distance and warns above `snap_warning_m`. |
| Report influence radius | 40 m | - | - | **ASSUMPTION** | A report affects edges whose midpoint is within this distance. |
| Report expiry | 180 days | - | - | **ASSUMPTION** | Unconfirmed reports stop influencing routing after this. |
| DEM minimum edge length | 20 m | - | - | **ASSUMPTION** | SRTM 30 m cannot resolve shorter edges; those stay UNKNOWN. |
| DEM maximum absolute grade | 20% | - | - | **ASSUMPTION** | Implausible values at this resolution are rejected, not clamped. |

## What the numbers do *not* say

- A route that passes these checks is **not** certified accessible. It may still have a
  lip, a missing ramp, a parked car, a construction closure, or a slope that the DEM
  smoothed away.
- A missing tag is **unknown**, not "compliant" and not "blocked". The user's risk
  setting decides how much the unknown value costs.
- The 8.33% value is a **ramp** maximum. A sidewalk that rises at 8% is not automatically
  illegal, and a route at 7% is not automatically usable. The hard threshold is a
  personal setting, not a legal determination.
- PROWAG is guidance unless a jurisdiction has adopted it. The app does not know which
  codes apply to a given block.
- Width and slope are measured differently in the field (cross slope vs. running slope,
  clear width vs. total width). The app's `width` is treated as clear width; OSM's
  `width` tag is not guaranteed to mean that. Field audits can override it, with
  provenance shown in the interface.

## Per-profile summaries

### Wheelchair (starting point)

- Steps: hard block.
- Uphill: 5% soft, 8.33% hard, hard action = block for mapped grades.
- Downhill: 8% soft, 12% hard.
- Surface multipliers: 1.0 / 1.35 / 2.2 / 4.0.
- Raised kerb 150 m-eq, unknown kerb 100 m-eq × risk scale.
- Minimum width 1.22 m.

### Limited mobility / cane / walker (starting point)

- Steps: penalized 600 m-eq + 10 m-eq per mapped step, not blocked by default.
- Uphill: 6% soft, 12% hard, hard action = fixed penalty.
- Downhill: 8% soft, 15% hard.
- Surface multipliers: 1.0 / 1.2 / 1.7 / 2.5.
- Minimum width 1.22 m.
- Lighting preference is on by default; unlit segments add 40 m-eq.

All of these values can be changed with the sliders. The server validates ranges and
rejects invalid profiles with HTTP 422 rather than silently repairing them.

## Elevation and time

- DEM grades use **SRTM 30 m** through the free OpenTopoData public API
  (<https://www.opentopodata.org/datasets/srtm/>). SRTM is a U.S. government dataset;
  check the current USGS/NASA terms before redistributing derived data. The public API
  allows up to 100 locations per request and about one request per second; the fetch
  script obeys both and caches results.
- SRTM is a 30 m surface model. It is **not** a sidewalk measurement and can be wrong at
  bridges, underpasses, retaining walls, and building edges. Estimated grades are
  labeled `DEM_ESTIMATED`, get a reduced penalty, and can never hard-block a route.
- Walking time is an estimate from the profile's speed assumption. It is shown with the
  speed and the word "estimate"; it is not a promise of arrival time.

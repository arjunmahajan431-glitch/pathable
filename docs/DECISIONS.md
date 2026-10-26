# Design decisions

Brief notes for defending the project. Each entry says what was chosen, why, and what
was rejected. Dates are when the decision was made (October 2026 unless noted).

## Routing and data model

### Directed `MultiDiGraph` with an `EdgeFeatures` object

**Chosen.** Keep OSMnx's directed multigraph, normalize each edge into a typed
`EdgeFeatures` object, and store provenance per attribute. Parallel edges are considered
separately.

**Why.** A sidewalk can have two directions with different grades, and a merged way can
contain several parallel paths. Keeping each directed edge separate is the only way to
represent "uphill in this direction, downhill in the other" honestly. A typed object
makes the provenance impossible to forget when a new cost term is added.

**Rejected.** A simple undirected graph (loses direction), a DataFrame of tags (easy to
drop provenance), or selecting "the best" parallel edge up front (hides the choice).

### `network_type="walk"`, bounding box + exact haversine circle

**Chosen.** Download a walk network with OSMnx, then keep nodes within the configured
radius measured by haversine.

**Why.** OSMnx's `dist_type="network"` requires scikit-learn for nearest-node search;
this keeps the dependency set smaller and gives an exact circle. The bounding box is
larger than the circle but is filtered before caching.

**Rejected.** `dist_type="network"` (extra dependency, slower), or trusting a bbox as the
area (corners would be outside the stated radius).

### Explicit useful-tag list

**Chosen.** Extend `ox.settings.useful_tags_way` and `useful_tags_node` before download
with every tag the router uses.

**Why.** OSMnx drops tags by default. A missing tag would silently become "unknown" even
when OSM had it. The list is in `graph/loader.py`.

**Rejected.** Loading with the defaults and adding tags later (impossible after the
download) or fetching every tag (noisy and slower).

### Normalize merged list tags conservatively

**Chosen.** If merged values disagree: any `steps` wins, the roughest surface wins, the
narrowest width wins, and a conflicting incline direction becomes UNKNOWN.

**Why.** Simplification can merge ways. Picking the first list item would make the result
depend on XML order. The conservative rule never claims a path is easier than one of its
components. The rule is documented in the module docstring and tested.

**Rejected.** "First value wins" (arbitrary), "last value wins" (arbitrary), or throwing
away the edge (loses a real path).

### Flip incline on `reversed=True`

**Chosen.** Read OSMnx's `reversed` attribute and flip the sign of `incline=up/down` for
edges that run against the way direction.

**Why.** OSM's incline is relative to the way, not the edge direction. Without the flip,
the same street would be uphill both ways. A dedicated test constructs forward and
reverse edges and checks the cost difference.

**Rejected.** Ignoring incline on reversed edges (loses data) or trusting the raw tag
(produces wrong grades).

### `DEM_ESTIMATED` never hard-blocks

**Chosen.** A DEM-derived grade above the hard limit gets a capped multiplier and a
reduced fixed penalty, not a hard block. A mapped grade can block when the profile says
so.

**Why.** SRTM 30 m cannot see a sidewalk, a curb, a bridge deck, or a retaining wall. It
is useful as a coarse signal and irresponsible as a hard prohibition. The UI labels it
and explains the lower confidence.

**Rejected.** Treating DEM like a measured incline (overclaims certainty) or ignoring DEM
entirely (most OSM edges have no incline tag).

### 1.22 m default minimum width; 8.33% as a ramp reference only

**Chosen.** Default `min_width_m=1.22` from PROWAG R302.2. Default hard uphill slope
8.33% is labeled as a curb-ramp/ramp reference, not a universal sidewalk limit.

**Why.** The project is about public pedestrian routes. The ADA's 36 in (0.915 m)
accessible-route width is a building/site value; PROWAG's 48 in is the public
right-of-way guidance. The 1:12 ramp maximum is familiar but its scope is ramps. Presenting
it as a universal legal limit would be wrong. Both values and their scopes are recorded
in `docs/STANDARDS.md`.

**Rejected.** Using 0.915 m as the default (narrower than the public-right-of-way
guidance), using a made-up "comfortable" width, or hiding the legal scope in a tooltip.

## Cost and search

### Generalized cost in meter-equivalents

**Chosen.** `cost = length × multipliers + fixed penalties`, in m-eq, with a full
breakdown per edge.

**Why.** It combines distance, effort, roughness, crossings, and uncertainty in one
number while staying explainable. A user can see "this 34 m stairway is blocked" or
"unknown width adds 9.6 m-eq". It also gives A* a simple admissible heuristic.

**Rejected.** Time-only cost (walking speed is an assumption and hides effort), pure
distance (cannot express barriers), or a weighted score with arbitrary weights that
cannot be interpreted.

### Multipliers ≥ 1, penalties ≥ 0, hard blocks explicit

**Chosen.** No rewards or negative terms. A hard block is a flag, not infinity.

**Why.** It guarantees cost ≥ length, which makes haversine admissible. It also makes
"stricter profile never lowers a cost" true and keeps the arithmetic easy to audit. The
breakdown still works for a blocked edge.

**Rejected.** Negative rewards for good attributes (breaks admissibility and encourages
detours for points), `inf` sentinel (hard to serialize and explain), or silently dropping
blocked edges (hides why a route is unavailable).

### Own Dijkstra and A*; NetworkX only as an oracle

**Chosen.** Implement both searches in `engine/search.py`, deterministic tie-breaking,
and compare with NetworkX in tests.

**Why.** The project's value is the cost model and explanation. Implementing the search
keeps the objective and the admissibility argument visible. Using NetworkX in tests as
an independent oracle is stronger than comparing the implementation with itself.

**Rejected.** `nx.shortest_path` for production (hides the cost function), `nx.astar_path`
(same), or no oracle tests (a bug could be self-consistent).

### Deterministic tie-break

**Chosen.** Sorted neighbor iteration plus a monotonic counter in the heap.

**Why.** Equal-cost routes should not flicker between runs, and tests/screenshots should
be reproducible. The tie-break is documented, not accidental.

**Rejected.** Heap comparison of node objects (can raise for non-comparable types) or
random tie-breaking (irreproducible).

### Sensitivity: one parameter at a time

**Chosen.** Recompute the preferred route at two nearby hard-slope values, with
everything else fixed.

**Why.** It is a deterministic, explainable check that answers "would a slightly different
limit change my route?" It avoids pretending to explore a high-dimensional space.

**Rejected.** A full grid search (slow, hard to explain), a Monte Carlo simulation
(randomness obscures the single setting), or no sensitivity view (the user cannot see
how fragile the choice is).

## Data, reports, and field audits

### Labeled demo extract instead of fake live data

**Chosen.** If the real area/graph is missing or Overpass fails, serve a committed OSM
extract with a persistent demo warning, source, date, and a placeholder-area warning.

**Why.** The brief forbids silently substituting fake data. A labeled sample is useful
for development and a demo, and it is honest. The evaluation marks it as demo data.

**Rejected.** Fabricating a street grid (worse), silently failing (unusable demo), or
blocking all work until the student supplies an area (violates the brief's autonomy).

### SQLite reports, no accounts

**Chosen.** Reports are stored in SQLite with category, description, time, status, and a
rotating client hash. No names, emails, IPs, or route endpoints. Admin review needs
`PATHABLE_ADMIN_TOKEN`.

**Why.** It meets the privacy requirement and keeps setup free. A report is not a verified
fact; unverified reports get half weight, reviewed reports full weight, resolved/rejected
zero, and expiry after 180 days.

**Rejected.** A hosted database/account system (overkill, privacy risk), storing raw IPs
for rate limiting (unnecessary personal data), or letting new reports immediately count
as fact (misleading).

### Field audit as CSV/GeoJSON overlay, not a second graph

**Chosen.** Import rows into a SQLite `audits` table, snap each to the nearest edge
segment, and overlay the values at graph load. Keep the OSM value for comparison.

**Why.** It is the smallest workflow a student can actually use: a spreadsheet and one
command. Keeping both values enables the headline OSM-vs-audit comparison.

**Rejected.** Editing GraphML by hand (error-prone), a web admin UI (scope creep), or
replacing OSM values silently (loses the comparison and the provenance story).

### Sample audit clearly labeled

**Chosen.** `data/fixtures/sample_field_audit.csv` is fabricated and every row's notes
say "SAMPLE DATA". The evaluator labels it "SAMPLE DATA, NOT A FINDING."

**Why.** The harness needs data to test the import and comparison. Presenting fabricated
rows as a real finding would violate the truthfulness rules. The user must replace it
with their own audit.

## Frontend and UX

### Leaflet + OpenStreetMap tiles, not a paid map SDK

**Chosen.** React-Leaflet with public OSM tiles and visible attribution.

**Why.** Free, no API key, and the tile usage policy is documented. The project has no
budget and the brief forbids paid APIs.

**Rejected.** Mapbox/Google (keys, billing, terms), or a static image (not interactive).
Public tiles are for light/demo use; the README says how to swap providers.

### Text-first route description alongside the map

**Chosen.** A full segment list, coordinate inputs, address search, and keyboard flow in
addition to map clicks. Route lines differ by color, dash pattern, and labels.

**Why.** Map-only input is an accessibility failure. A screen-reader user must be able to
plan, compare, inspect, and report without the map. The Playwright suite includes a
keyboard-only run and an axe scan with zero serious/critical violations.

**Rejected.** Map-only (excludes keyboard/screen-reader users), color-only route styling
(fails color-vision users), or a separate "accessible mode" (worse than one accessible
interface).

### Deterministic template explanations, no external text service

**Chosen.** Explanations are built from the cost breakdown and coverage numbers with
fixed templates.

**Why.** The brief forbids an external text-generation API in the app. Templates are
reproducible, testable, cheap, and auditable. A reviewer can trace every sentence to a number.

**Rejected.** A generated prose summary (non-deterministic, privacy/cost risk, violates
the brief), or no explanation (removes the differentiator).

## Project and evaluation choices

### Whole-city areas are Woodbury and Saint Paul, Minnesota

**Chosen.** `config/areas.yaml` defines two public, non-school areas: `woodbury-mn`,
centered on Woodbury City Hall and Central Park, and `saint-paul-mn`, centered on Saint
Paul City Hall. Each area supplies an OpenStreetMap city boundary GeoJSON, so the boundary
is the real routing and report limit. The radius is only a generous bounding circle for
address search. The committed citywide samples, elevation caches, screenshots, and
evaluation use these areas.

**Why.** The student asked for all of Woodbury and all of Saint Paul, not a small pilot
circle. A city boundary is the honest limit of a citywide map, while a radius would
either miss neighborhoods or include neighboring towns. The centers are public
landmarks, not a home or school.

**Rejected.** A 1.5 km or 3 km circle presented as the whole city; guessing a home
address or school (privacy and explicit brief restriction); and treating a city name as
an unbounded download (the graph would cover neighboring towns and exceed the 12 km
technical guardrail).

### Seeded 40-pair evaluation

**Chosen.** 40 seeded pairs per city, seed 20261025, sampled from mapped pedestrian
nodes inside the city boundary and at least 250 m apart. The reports use `--demo`, so they
describe the committed city snapshots rather than whatever live cache happens to exist.

**Why.** Sampling real network nodes keeps every pair on the graph and inside the real
city limit; a radius-only circle can put points in a lake, a field, or a neighboring
town. The sample is small enough to run in a few minutes, large enough to show the shape
of the results, and reproducible. The report labels it descriptive, not a benchmark.

**Rejected.** A single demo route (not an evaluation), points from a radius-only circle,
thousands of pairs (slow and still one graph snapshot), or unseeded randomness (not
reproducible).

### E2E tests boot the real backend in demo mode

**Chosen.** Playwright starts FastAPI with a temporary SQLite database and Vite, then
drives the real UI. Screenshots are generated from that run.

**Why.** Mocking the API would not catch a CORS, serialization, or provenance-label
regression. A temporary database keeps the developer's reports untouched.

**Rejected.** Mock-only component tests (already present for fast feedback), or pointing
tests at a deployed server (flaky and not hermetic).

## Things deliberately not built

- Turn-by-turn voice navigation, native apps, indoor routing, transit, user accounts, or
  paid APIs.
- A "safe route" badge. The product says what is known and unknown, not that a route is
  accessible.
- Automatic OSM edits from reports. Reports influence this app's routing after review;
  they are not pushed back to OSM.

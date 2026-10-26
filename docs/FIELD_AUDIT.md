# Field audit: schema and import

A field audit is your own measurement from a real block. It is the highest provenance
tier (`FIELD_AUDIT`) and overrides OSM values in the cost model while keeping the original
OSM values for comparison.

The committed sample file
[`data/fixtures/sample_field_audit.csv`](../data/fixtures/sample_field_audit.csv) is
**fabricated demo data**, not a finding. Its points sit on public sidewalk edges inside
Woodbury so the importer and comparison code can be exercised end to end. Do not quote
its percentages; collect and import your own rows inside the active city.

## Before you go out

- Audit only public places you can legally and safely access. Follow traffic rules and
  do not step into live traffic.
- Do not put your school, home, your name, your email, or any personal information in
  the file. Use a public landmark or street name in notes if you need one.
- Measure the running slope along the direction of travel, not the cross slope. If you
  can measure both, record the running slope in `measured_slope_pct` and put the cross
  slope in `notes` (the current cost model uses running grade).
- `clear_width_m` means the narrowest clear passage, excluding parked cars and movable
  furniture that you observed. Record the date; a measurement is a snapshot.
- `photo_ref` is a filename or identifier you control (for example `audit/block-04.jpg`).
  The app stores the string, not the image, and the repository should not contain photos
  of identifiable people.

## CSV columns

The header is required. Unknown/blank values stay unknown; do not fill them with guesses.

| Column | Required | Type / allowed values | Meaning |
|---|---|---|---|
| `lat` | yes | decimal degrees, −90…90 | WGS84 latitude of the observation |
| `lon` | yes | decimal degrees, −180…180 | WGS84 longitude |
| `curb_ramp` | no | `yes`, `no`, `damaged`, `lowered`, `flush`, `raised`, `missing`, or blank | Condition at a crossing. `yes`/`lowered`/`flush` map to a lowered kerb; `no`/`raised`/`missing` to a raised kerb; `damaged` stays damaged. |
| `measured_slope_pct` | no | number, −100…100 | Running slope in percent, positive uphill in the direction you walked |
| `clear_width_m` | no | number, 0…50 | Narrowest clear width in meters |
| `obstacle` | no | text, ≤120 chars | A short obstacle code, e.g. `bollard`, `construction`, `parked_car` |
| `date` | no | ISO date `YYYY-MM-DD` | Date of the observation |
| `photo_ref` | no | text, ≤300 chars | Your filename/identifier; no personal data |
| `notes` | no | text, ≤500 chars | Context, cross slope, temporary conditions |

Example:

```csv
lat,lon,curb_ramp,measured_slope_pct,clear_width_m,obstacle,date,photo_ref,notes
44.905915,-92.959914,yes,4.5,1.35,,2026-10-24,audit/block-01.jpg,New ramp; cross slope about 1.5%
44.906421,-92.958668,damaged,6.0,0.95,,2026-10-24,audit/block-01.jpg,Flare broken
```

GeoJSON is also accepted: a `FeatureCollection` of `Point` features whose `properties`
use the same names (coordinates are `[lon, lat]`).

## Import

```bash
# validate and snap without writing
backend/.venv/bin/python scripts/import_audit.py my_audit.csv --dry-run

# write to the configured database
backend/.venv/bin/python scripts/import_audit.py my_audit.csv

# only for the clearly labeled sample, when no real graph is cached
backend/.venv/bin/python scripts/import_audit.py \
  data/fixtures/sample_field_audit.csv --allow-demo
```

- The point is snapped to the nearest **edge segment**, not merely the nearest node. The
  snap distance is stored and printed. A row farther than `routing.max_snap_m` (default
  300 m) is rejected; it is not attached to an unrelated block.
- Re-importing the **same filename** replaces the rows previously imported from that
  filename. Fix a typo and rerun; there is no duplicate pile-up.
- The script refuses to write real field data onto the demo extract unless you pass
  `--allow-demo`. That flag is for the labeled sample only.
- The API loads audits at startup. Restart the API after importing.
- The default database is `data/cache/pathable.db` (gitignored). Set
  `PATHABLE_DATABASE=/path/to/file.db` to use another one.

## What the overlay changes

`graph/features.py::apply_audit`:

- `curb_ramp` changes `kerb` and its provenance;
- `measured_slope_pct` changes `grade_pct` and its provenance;
- `clear_width_m` changes `width_m` and its provenance;
- `obstacle` changes `barrier` and its provenance.

The original values are kept in `osm_kerb`, `osm_grade_pct`, and `osm_width_m` on the
feature. `scripts/evaluate.py` uses those to count how often OSM was missing or
disagreed. The interface shows `Field audit` badges and `FIELD_AUDIT` provenance on the
segment inspector.

## Limits

- One observation is one point in time. A ramp can be repaired or blocked later.
- The audit is attached to the nearest edge; a point at an intersection can be closer to
  the wrong edge. Check the printed snap distance and keep points away from ambiguous
  corners when possible.
- The cost model uses running slope. A measured cross slope belongs in `notes` until the
  model supports it.
- A sample of 10-20 blocks in one part of a city cannot describe the whole city. Report it
  as a local finding with the sample size.

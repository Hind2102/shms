# Site layout (concept map, v1.5.0)

**Concept layout only — roads, equipment and facility positions are indicative and require a verified site plot plan.**

The site map is an **illustrative concept based on public photographs**. It is not a verified plot plan.
- Positions, sizes and distances are indicative.
- Zone codes, zone boundaries and the PPE lists of each zone are **project assumptions**.
- No confidential drawings or geographic survey data were used.

The project owner approved this map on 25 Nov 2026. It replaces the earlier invented schematic.

## Source and generation

| | |
|---|---|
| Image | [`shms/static/ata_concept_map.svg`](../shms/static/ata_concept_map.svg), 1920 × 1080 drawing units, origin top left |
| Generator | [`scripts/site_plan/make_map5.py`](../scripts/site_plan/make_map5.py), copied from the owner's `map_proposal/make_map5.py`. Its only change is an optional output path. It is excluded from ruff so that it stays as approved. |
| Regenerate | `python scripts/site_plan/make_map5.py shms/static/ata_concept_map.svg` |
| Approved file | `map_proposal/ata_concept_map.svg` is byte-identical to the generator output once its embedded C2PA provenance block and an empty `<metadata>` tag are removed (checked 25 Nov 2026) |

The title strip, coast, legend and footer note are part of the image. The app draws its own layers on top:
- overlay strips;
- zone outlines for selection;
- pins;
- the suggested route.

## Zones

[`shms/site_layout.py`](../shms/site_layout.py) reads every `<g id="zone-CODE" data-code data-name
data-reporting data-points>` group from the SVG. The polygons are used for:
- the site plan;
- the dashboard heat map;
- pin validation, which uses point in polygon with the outline counting as inside;
- routing.

| Code | Zone (name from the map) | Reporting | Required PPE (project assumption) |
|---|---|---|---|
| BXH | Bauxite storage & handling | yes | base PPE, dust mask, hearing protection |
| DIG | Digestion | yes | base PPE, face shield over glasses (caustic), chemical gloves |
| GRD | Grinding & slurry preparation | yes | base PPE, hearing protection |
| CLR | Clarification | yes | base PPE, face shield over glasses (caustic), chemical gloves |
| FLT | Security filtration | yes | base PPE, face shield over glasses (caustic), chemical gloves |
| PRC | Precipitation | yes | base PPE, chemical gloves |
| EVP | Evaporation (new) | yes | hard hat, face shield, chemical gloves |
| CAL | Calcination | yes | base PPE, heat-resistant gloves, dust mask |
| HYD | Hydrate filtration (new) | yes | hard hat, face shield, chemical gloves |
| ALS | Alumina storage (new) | yes | hard hat, safety glasses, gloves, dust mask |
| TNK | Caustic & reagents | yes | base PPE, face shield (caustic transfers), chemical suit |
| LIM | Lime handling (new) | yes | hard hat, goggles, gloves, dust mask |
| PWR | Water & utilities | yes | base PPE, hearing protection, arc-rated clothing (switchrooms) |
| WKS | Workshops & stores (new) | yes | hard hat, safety glasses, gloves, hearing protection |
| WTR | Water basins (new) | yes | hard hat, safety glasses, life jacket (near open water) |
| LAB | Laboratory & offices | no – support area, no hazard totals | – |

Base PPE: hard hat, safety glasses, gloves, safety boots, flame-resistant coverall.

AI checks in every zone are limited to the PPE checks the release gate approved.

Migration `0009_ata_site_map`:
- renamed the nine existing areas (codes, ids, hazards and pins kept);
- added the six new zones; each new zone's owner is the owner of a neighbouring process area;
- moved existing report pins proportionally from the old 1200 × 800 rectangles into the new polygons.

## Overlays (unchanged rules)

Each overlay states its calculation, window, site total and number of hazards counted.
- *Open risk*, *Overdue* and *Reports* are shaded relative to the highest zone.
- Hatching means no matching records. It is not a statement about conditions.
- Report volume uses a neutral colour, because it shows how much people report, not danger.
- Pins show active cases with a reported point. Pins within 48 map units of each other in the same zone are grouped.

## Route from the south gate

The road graph is built from the road centre-lines in the map's `<g id="roads">` group:
- the perimeter road;
- the main access road (vertical, east of the process blocks, opening to the south gate);
- the main road above the water basins;
- the service roads.

Lines are split at:
- junctions;
- zone extents;
- zone entrances. An entrance is the zone centre projected onto each road within 30 map units of the zone.

The route starts at the **south gate** (1458, 1000) and uses Dijkstra's algorithm, with edge length in map units.

It avoids every stretch of road beside a zone with an **active High or Extreme** hazard (open, planned or awaiting
verification), whatever the display window or level filter. The route ends at the nearest entrance of the
destination and steps onto its outline.

When there is no route, the panel says why and directs the user to the Area Owner:
- the destination itself has active High or Extreme hazards, or
- the flagged zones block every road approach.

The approved map shows no muster points, so the area card shows none.

Limits: the junction at the south gate is never closed. Rounded road corners are treated as square, which is
indicative only.

**Illustrative routing on a concept layout – follow site rules and permits.** The app has none of the following:
- live access restrictions;
- gas or wind data;
- clearance checks;
- emergency-routing authority.

## Controls

- Select a zone on the map, or choose it under **Check before entering**. The panel shows:
  - required PPE (marked as a project assumption);
  - open hazards;
  - overdue work;
  - recent verified closures;
  - a link for the suggested route.
- Zoom with + and −.
- Pan with the arrow keys or the buttons once zoomed. Pointer users can also drag.
- Home or **Reset view** restores the whole map.
- The map, its controls and the native zone selector work at phone width. `docs/screenshots/audit_ui.py` checks
  390 px and 1366 px with axe-core.

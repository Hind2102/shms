# Illustrative refinery plan

**Illustrative layout – not an actual site plan.** The project draws an invented shoreline, equipment arrangement, roads and pedestrian network. It uses local SVG and a 1200 × 800 drawing coordinate system with its origin at the top left. The north arrow, wind arrow and approximate scale provide orientation within the drawing. Wind is illustrative. No geographic coordinates or operating facility plans were used.

## Process arrangement

Bauxite arrives at the jetty and stockpile. Grinding and pre-desilication prepare the feed for digestion. The drawing shows high-pressure digesters, flash tanks and heat exchangers. Clarification separates residue from liquor. Counter-current decantation washes residue before storage at the edge of the drawing. Security filtration leads to precipitation, hydrate classification and product, coarse-seed and fine-seed disc filtration. Calcination precedes the product silos and ship loader. Evaporation recovers spent liquor for reuse. Select **Process flow** to see the material paths and dashed liquor return.

The process order follows the Australian Aluminium Council’s public introduction to digestion, clarification, precipitation and calcination. The more detailed equipment groupings and all relative positions are educational design choices. [Australian Aluminium Council, Alumina refining](https://aluminium.org.au/about-aluminium/how-aluminium-is-made/alumina-refining/)

## Reporting coverage

| Reporting code | Physical group |
| --- | --- |
| BXH | Bauxite handling, jetty and stockpile |
| GRD | Grinding and pre-desilication |
| DIG | Digestion, flashing and heat exchange |
| CLR | Clarification |
| FLT | Security filtration |
| PRC | Precipitation |
| CAL | Calcination |
| TNK | Caustic unloading and storage |
| PWR | Powerhouse, steam and utilities |

The residue wash train, residue storage, hydrate classification, disc filters, evaporation, product silos, water treatment, control room, workshop, warehouse, administration and gatehouse provide physical context. They have no separate hazard totals. Each reporting lot has a code and metric strip. Values compare areas within the selected view. Hatching denotes no matching records. Report counts use neutral shading. The entry panel shows hazards, PPE, overdue work and recent verified closures across report dates and levels.

## Coordinates and pedestrian routing

The reporting form and site view draw the same unit geometry from [site_layout.py](../shms/site_layout.py). A hazard point records a location in these drawing units inside its reporting lot. Reports without a point contribute to area totals. Legacy database rectangle columns describe the earlier schematic.

Pedestrian traffic follows the dashed frontage walks, entrance spurs and perimeter connections. Roads with one-way arrows, service racks and conveyors are separate features. A route starts at the gatehouse and ends at the selected reporting lot entrance. The site view uses Dijkstra’s algorithm with edge length in drawing units. It excludes every frontage node serving an area with an active High or Extreme case (open, planned or pending verification), regardless of display window or risk-level filter. Both incident walkway segments and the area entrance spur become unavailable. If the destination is flagged or all approaches are blocked, the panel explains why and directs the user to the Area Owner. Muster points and emergency gates are orientation symbols.

**Illustrative routing on a synthesized layout – follow site rules and permits.** Case reports cover recorded observations only. The app has no live access restrictions, wind measurements, clearance checks or emergency-routing authority.

## Controls

Select a reporting lot or choose a named area under **Check before entering**. The panel links to the full area board and individual cases. Use + and − to zoom, the arrow keys or buttons to pan a zoomed view, and Home or **Reset view** to restore the whole drawing. Pointer users can drag to pan after zooming. Above-map controls and the searchable native area selector remain available at phone widths.

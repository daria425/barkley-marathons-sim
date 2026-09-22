---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

## Direction contract

THESIS: The live-race dashboard is a broadcast command center, not a monitoring grid — one instrument (the map, with its real-vs-believed position gap) leads, the runner's vitals and reasoning are side instruments an operator glances at, and time/control are a fixed bottom rail. It refuses the generic equal-weight card-grid ("Grafana-style") default this category always ships.

OWN-WORLD: Ground #000 with #38383a secondary surfaces, #00aec7 cyan as the sole accent (map markers, active states, links). Ubuntu-family sans throughout. Background carries a soft grey-to-transparent dotted gradient, built as a lightweight inline SVG `<pattern>` of dots under a fade mask/gradient — never a raster image. Panels (map, watch-face card, monologue card, bottom control strip) sit at a consistent, restrained elevation via soft shadow, one shadow language across all panels, none "louder" than another. Component base is shadcn/ui, retheme to these tokens rather than shadcn's default look. Register: Nike/Scarpa/Adidas-grade athletic-performance clarity, not decorative.

STORY: A general AI-curious visitor (not necessarily an ultrarunner) opens the dashboard and immediately reads: where the runner thinks they are vs. where they actually are, how their body is doing (HR/pace/glycogen/hydration), what they're currently thinking (monologue), and at what speed sim-time is passing. No action required of the visitor beyond adjusting speed/start/quit.

FIRST VIEWPOINT: Map fills ~60% of the width on the left, showing real dot, ghost/believed dot, and the connecting gap line, elevated on its own panel. Right rail (~40%) stacks a watch-face card (HR, pace, elapsed, glycogen, hydration) above a monologue feed card. A full-width bottom strip anchors clock/elapsed time, speed control (1x/60x/600x), and start/quit, elevated above the dotted-gradient ground.

FORM: Command Center — my #3-ranked grounded structural candidate for this surface, dealt as the lead by the roll (seed key 72ef17a3), chosen over Full-Bleed HUD and Broadcast Ticker at the confirmed decision round (key 10f57c86).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

# ADR-0013: Endless runner scene beside the map, using React Three Fiber

**Date**: 2026-09-23
**Status**: accepted
**Deciders**: Daria, Codex

## Context

The frontend already displays the course, runner physiology, and monologue history.
Daria requested a sliding map panel whose second slide shows one runner in an endless
3D landscape, with a speech bubble and animation driven by actual pace. The references
combine cartoon runners with atmospheric natural environments. The first version must
work with the existing static mock workflow as well as live WebSocket snapshots.

## Decision

Use Three.js with React Three Fiber in a lazily loaded second slide, keeping the map
as the first slide. Build the initial character and repeating woodland tiles from
geometry in code; external Blender assets and accurate geographic terrain are deferred.
Use the existing generated runner/environment types and Redux monologue data without
changing the backend schema.

The camera follows a runner facing down the trail. Scenery recycles behind the camera
using a bounded set of tiles and instanced decorations. Animation converts pace to
visual speed with an upper bound and smooth transitions; a positive rest decision
stops movement because the backend still reports a theoretical pace during rest.
Simulation time acceleration is not multiplied into the character animation.

The speech bubble shows an excerpt of the latest real monologue with an option to
expand it. The full feed remains beside the viewer. Hidden scenes/tabs suspend the
continuous render loop. The map remains mounted to preserve its camera position.

**2026-09-24 review update:** Daria requested removal of the local play/pause control.
The visible scene now animates automatically, including when reduced motion is enabled;
the slider transition still respects reduced motion. Hidden scenes/tabs suspend rendering.

## Alternatives Considered

### Alternative 1: Direct Three.js integration

- **Pros**: One fewer runtime dependency.
- **Cons**: More manual lifecycle, resizing, and scene ownership code in this React app.
- **Why not**: Fiber lets scene components follow the existing React structure.

### Alternative 2: Import animated Blender models immediately

- **Pros**: Potentially more detailed characters and authored running animation.
- **Cons**: Requires asset selection, licensing checks, rig compatibility, and loading work
  before reviewing the basic scene.
- **Why not**: A code-built cartoon character is enough to review the visual direction;
  an imported character can replace it later.

## Consequences

### Positive

- A working visual slice uses existing live/mock data and needs no backend changes.
- Bounded scenery and instancing avoid growing memory use as the runner moves.
- No model downloads are needed for the first review.

### Negative

- Adds `three`, `@react-three/fiber`, and development types `@types/three`.
- The landscape is illustrative, not a reconstruction of the runner's coordinates.
- The initial gait and scenery are intentionally stylized.

### Risks

- GPU/browser capability varies: cap pixel ratio, suspend inactive animation, and provide
  a fallback message while keeping the map usable.
- Long thoughts can obscure the character: use an expandable excerpt and bounded text area.
- Validate with production build/lint and desktop/mobile browser checks, including
  slide switching, pace changes, rest, and long monologues.

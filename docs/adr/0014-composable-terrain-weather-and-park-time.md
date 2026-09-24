# ADR-0014: Compose terrain, weather, and park time in the runner scene

**Date**: 2026-09-23
**Status**: accepted
**Deciders**: Daria, Codex

## Context

The first runner view (ADR-0013) has one woodland landscape and a simple day/night light.
Daria requested distinct scenes for all eight course terrain labels plus off-trail brush,
each able to reflect the five weather conditions and the park's current time. The backend
now broadcasts `RunnerState.current_terrain` and `FrozenHeadStatePark.local_time` in
`Day N, H:MM AM/PM ET` format. Preview controls must be easy to remove after review.

## Decision

Compose independent terrain, atmosphere, and precipitation layers inside the existing
Three.js/Fiber scene. Use the new broadcast fields directly, with OpenAPI-generated types;
parse the fictional park clock explicitly without `Date`, browser timezone conversion,
or an assumed race start hour. Invalid/missing times fall back to the broadcast daylight
flag, and unknown terrain/weather labels have safe visual defaults.

Terrain presets define path width/curvature, slope, ridge sides, vegetation, rocks, and
water. Morph a fixed pool of geometry/instances between presets rather than remounting
the world. Blend sky, fog, sunlight, rain, wind, and surface wetness independently. Scene
motion remains driven by pace, with no change to the simulation or its RNG.

The initial review used a separate mock-only `ScenePreviewControls` wrapper with local
overrides and no Redux/backend writes. **2026-09-24 review update:** Daria approved its
removal, along with manual scene play/pause. The wrapper, stylesheet, and conditional
integration are removed; both mock and live modes now render `RunnerScene` directly.

## Alternatives Considered

### Alternative 1: Separate complete scenes for each terrain/weather/time combination

- **Pros**: Each scene can be authored in isolation.
- **Cons**: Duplicates assets and rendering logic across dozens of combinations; transitions
  and fixes become harder to maintain.
- **Why not**: Independent layers provide the requested combinations with bounded resources.

### Alternative 2: Add another numeric time field to the backend

- **Pros**: Avoids parsing formatted text.
- **Cons**: Duplicates the newly supplied park clock and requires another schema change.
- **Why not**: Daria explicitly chose the existing `local_time` string; a small validated
  parser handles noon/midnight and ignores race-day/timezone labels without guesswork.

## Consequences

### Positive

- Every terrain works with every weather state and time of day.
- Live scenes use actual broadcast conditions; mock data supports local UI development.
- No new dependencies or backend changes are required for this frontend slice.

### Negative

- Terrain remains illustrative and repeating, not a geographic reconstruction.
- The frontend parser depends on the documented `local_time` format.
- Transitions temporarily update instance matrices; fixed pools bound the work and memory.

### Risks

- Abrupt state changes: blend during animation; apply conditions immediately while hidden
  so returning to the scene shows current conditions.
- Night readability: keep a soft sky fill while retaining distinct dark lighting.
- Regressions: cover clock boundaries and fallbacks with Node tests, then inspect all nine
  terrains, five weather states, and representative daylight/night frames in the browser.

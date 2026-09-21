// Re-exports of the OpenAPI-generated schemas (src/types/api.d.ts, `npm run gen:types`) under
// their plain names — never hand-write these shapes, regenerate whenever server/models.py
// changes (CLAUDE.md's Type sync note).
import type { components } from "./api";

export type RaceState = components["schemas"]["RaceState"];
export type RunnerState = components["schemas"]["RunnerState"];
export type PhysiologyState = components["schemas"]["PhysiologyState"];
export type FrozenHeadStatePark = components["schemas"]["FrozenHeadStatePark"];
export type Decision = components["schemas"]["Decision"];
export type CourseGeometry = components["schemas"]["CourseGeometry"];
export type CourseBook = components["schemas"]["CourseBook"];

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

// These pure modules have no runtime imports. Use the project's compiler so Node 20
// can test them without adding a test framework or a second TS execution dependency.
async function loadTypescript(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
}
const { parseLocalHour, sceneConditions } = await loadTypescript("../src/components/scene/conditions.ts");
const { terrainProfile, TERRAIN_PROFILES } = await loadTypescript("../src/components/scene/terrain.ts");

test("park time correctly distinguishes midnight, noon, and fractional hours", () => {
  assert.equal(parseLocalHour("Day 1, 12:00 AM ET"), 0);
  assert.equal(parseLocalHour("Day 2, 12:00 PM ET"), 12);
  assert.equal(parseLocalHour("Day 2, 3:15 AM ET"), 3.25);
  assert.equal(parseLocalHour("Day 2, 3:15 PM ET"), 15.25);
  assert.equal(parseLocalHour("Day 9, 11:59 PM ET"), 23 + 59 / 60);
  assert.equal(parseLocalHour("Day 10, 12:00 AM ET"), 0);
});

test("race day and host timezone do not affect the park's hour", () => {
  const previous = process.env.TZ;
  try {
    for (const timezone of ["UTC", "Pacific/Honolulu", "Asia/Tokyo"]) {
      process.env.TZ = timezone;
      assert.equal(parseLocalHour("Day 1, 7:30 AM ET"), 7.5);
      assert.equal(parseLocalHour("Day 500, 7:30 AM ET"), 7.5);
    }
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test("invalid clocks fall back to broadcast day/night, never the computer clock", () => {
  for (const value of [undefined, "", "Day 1, 0:30 AM ET", "Day 1, 13:00 PM ET", "Day 1, 1:60 PM ET", "Day 1, 1:00 PM UTC"]) {
    assert.equal(parseLocalHour(value), null);
    assert.equal(sceneConditions({ local_time: value, is_daylight: false }).hour, 0);
    assert.equal(sceneConditions({ local_time: value, is_daylight: true }).hour, 12);
  }
  assert.equal(sceneConditions(null).hour, 12);
});

test("unknown weather and terrain safely fall back without accepting inherited keys", () => {
  assert.equal(sceneConditions({ weather: "hail", fog_pct: 500 }).weather, "clear");
  assert.equal(sceneConditions({ fog_pct: 500 }).fog, 100);
  assert.equal(sceneConditions({ fog_pct: -2 }).fog, 0);
  for (const value of [undefined, "new backend terrain", "toString", "__proto__"]) {
    assert.equal(terrainProfile(value).name, "overgrown singletrack");
  }
});

test("all nine terrain states resolve; off trail removes the path", () => {
  assert.equal(Object.keys(TERRAIN_PROFILES).length, 9);
  for (const name of Object.keys(TERRAIN_PROFILES)) assert.equal(terrainProfile(name).name, name);
  assert.equal(terrainProfile("thick brush, no trail in sight").width, 0);
  assert.ok(terrainProfile("creek crossing").water > 0);
  assert.ok(terrainProfile("pine thicket").pine > 0);
});

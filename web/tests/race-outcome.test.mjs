import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function loadTypescript(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
}
const { completedLoops, endStatus, formatElapsed, outcomeMessage } = await loadTypescript("../src/lib/raceOutcome.ts");
const { runnerSpeed } = await loadTypescript("../src/components/scene/motion.ts");
const fixture = JSON.parse(await readFile(new URL("../src/mocks/mockRaceState.json", import.meta.url), "utf8")).runners.Hank;

test("loop is the current loop, not completed loops, including the finish sentinel", () => {
  for (const [loop, completed] of [[1, 0], [4, 3], [5, 4], [6, 5]]) {
    assert.equal(completedLoops({ ...fixture, loop }), completed);
  }
});

test("terminal snapshots stop movement even with stale pace and a non-rest decision", () => {
  for (const status of ["finished", "dnf_cutoff", "dnf_quit"]) {
    assert.equal(runnerSpeed({ ...fixture, status }), 0);
    assert.equal(endStatus({ ...fixture, status }), status);
  }
  assert.ok(runnerSpeed(fixture) > 0);
  assert.equal(runnerSpeed({ ...fixture, last_decision: { ...fixture.last_decision, rest_min: 5 } }), 0);
});

test("idle and older snapshots keep existing behavior", () => {
  assert.equal(endStatus(), undefined);
  assert.equal(runnerSpeed(), 0);
  assert.equal(endStatus({ ...fixture, status: undefined }), undefined);
  assert.ok(runnerSpeed({ ...fixture, status: undefined }) > 0);
  assert.equal(outcomeMessage(fixture), undefined);
});

test("outcomes use final runner time and actual completed count", () => {
  const runner = { ...fixture, physiology: { ...fixture.physiology, elapsed_min: 3443.75 } };
  assert.equal(outcomeMessage({ ...runner, status: "finished", loop: 6 }), "Race complete! Hank finished 5 loops successfully in 57h 23m.");
  assert.equal(outcomeMessage({ ...runner, status: "dnf_cutoff", loop: 4 }), "Race complete! Hank completed only 3/5 loops in 60 hours.");
  assert.equal(outcomeMessage({ ...runner, status: "dnf_quit" }), "Race complete! Hank did not finish the race and quit at 57h 23m.");
  assert.equal(formatElapsed(59.75), "0h 59m");
  assert.equal(formatElapsed(60), "1h 0m");
  assert.equal(formatElapsed(3600), "60h 0m");
});

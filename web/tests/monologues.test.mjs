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
const { MAX_MONOLOGUES, canLoadOlder, capNewest, fromHistory, mergeLatest, mergeOlder } =
  await loadTypescript("../src/lib/monologues.ts");

const hist = (from, to) => Array.from({ length: to - from }, (_, i) => ({ id: from + i, elapsedMin: (from + i) >> 1, text: `t${from + i}` }));
const live = (texts, startSeq = 1) => texts.map((text, i) => ({ elapsedMin: 0, text, seq: startSeq + i }));
const texts = (entries) => entries.map((e) => e.text);

test("fromHistory maps the wire shape and keeps the row id as the cursor", () => {
  const [e] = fromHistory({ entries: [{ id: 7, elapsed_min: 3, text: "hi" }], has_more: false });
  assert.deepEqual(e, { id: 7, elapsedMin: 3, text: "hi" });
});

test("first load with a live replay entry the page already covers shows it once", () => {
  const merged = mergeLatest(live(["t9"]), hist(0, 10), 1);
  assert.deepEqual(texts(merged), hist(0, 10).map((e) => e.text));
});

test("live entries newer than the page survive, in order, after the page", () => {
  const existing = live(["t9", "t10", "t11"]);
  assert.deepEqual(texts(mergeLatest(existing, hist(0, 10), 1)), [...texts(hist(0, 10)), "t10", "t11"]);
});

test("with no overlap only entries that arrived after the request was issued are kept", () => {
  const existing = live(["stale-a", "stale-b", "fresh"], 1); // seq 1..3
  assert.deepEqual(texts(mergeLatest(existing, hist(100, 103), 2)), ["t100", "t101", "t102", "fresh"]);
});

test("a reconnect replaces the store with the page instead of duplicating it", () => {
  const before = mergeLatest([], hist(0, 50), 0);
  const again = mergeLatest(before, hist(0, 50), 0);
  assert.deepEqual(texts(again), texts(before));
});

test("older pages go in front and dedupe against what is already loaded", () => {
  const merged = mergeOlder(hist(50, 100), hist(0, 51));
  assert.deepEqual(texts(merged), hist(0, 100).map((e) => e.text));
});

test("the store never exceeds the cap: live overflow drops the oldest", () => {
  const capped = capNewest(hist(0, MAX_MONOLOGUES + 25));
  assert.equal(capped.length, MAX_MONOLOGUES);
  assert.equal(capped[0].text, "t25");
  assert.equal(capped.at(-1).text, `t${MAX_MONOLOGUES + 24}`);
});

test("loading older can never push the store past the cap", () => {
  const existing = hist(1000, 1000 + MAX_MONOLOGUES - 10);
  const merged = mergeOlder(existing, hist(0, 50));
  assert.equal(merged.length, MAX_MONOLOGUES);
  assert.equal(merged[0].text, "t40"); // only the 10 entries nearest the existing ones fit
});

test("load older is offered only when more exists and there is room", () => {
  assert.equal(canLoadOlder(hist(0, 10), true), true);
  assert.equal(canLoadOlder(hist(0, 10), false), false);
  assert.equal(canLoadOlder(hist(0, MAX_MONOLOGUES), true), false);
});

import assert from "node:assert/strict";
import test from "node:test";
import { isoToUs, usToIso } from "./usDate.ts";

test("isoToUs formats US month/day/year", () => {
  assert.equal(isoToUs("2026-09-03"), "09/03/2026");
});

test("usToIso rejects impossible dates", () => {
  assert.equal(usToIso("02/31/2026"), null);
  assert.equal(usToIso("09/03/2026"), "2026-09-03");
});

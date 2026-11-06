import { test } from "node:test";
import assert from "node:assert/strict";

import { Backoff } from "../src/backoff.ts";

test("doubles from 1 s and caps at 30 s", () => {
  const backoff = new Backoff(1000, 30000);
  assert.equal(backoff.attempts, 0);
  assert.equal(backoff.next(), 1000);
  assert.equal(backoff.next(), 2000);
  assert.equal(backoff.next(), 4000);
  assert.equal(backoff.next(), 8000);
  assert.equal(backoff.next(), 16000);
  assert.equal(backoff.next(), 30000);
  assert.equal(backoff.next(), 30000);
  assert.equal(backoff.attempts, 7);
});

test("reset clears the attempt count", () => {
  const backoff = new Backoff(1000, 30000);
  backoff.next();
  backoff.next();
  backoff.reset();
  assert.equal(backoff.attempts, 0);
  assert.equal(backoff.next(), 1000);
});

test("custom initial and cap are honoured", () => {
  const backoff = new Backoff(50, 300);
  assert.equal(backoff.next(), 50);
  assert.equal(backoff.next(), 100);
  assert.equal(backoff.next(), 200);
  assert.equal(backoff.next(), 300);
  assert.equal(backoff.next(), 300);
});

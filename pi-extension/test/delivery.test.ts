import { test } from "node:test";
import assert from "node:assert/strict";

import { Delivery, contentHash } from "../src/delivery.ts";

test("head match consumes", () => {
  const delivery = new Delivery();
  delivery.track("c1", "hello", 0, 100);
  assert.equal(delivery.observe("hello", 0), "c1");
  assert.equal(delivery.pending(), 0);
});

test("non-matching message consumes nothing", () => {
  const delivery = new Delivery();
  delivery.track("c1", "hello", 0, 100);
  assert.equal(delivery.observe("goodbye", 0), null);
  assert.equal(delivery.pending(), 1);
});

test("duplicates consume one per message", () => {
  const delivery = new Delivery();
  delivery.track("c1", "hello", 0, 100);
  delivery.track("c2", "hello", 0, 100);
  assert.equal(delivery.observe("hello", 0), "c1");
  assert.equal(delivery.observe("hello", 0), "c2");
  assert.equal(delivery.pending(), 0);
});

test("settle returns unconfirmed once", () => {
  const delivery = new Delivery();
  delivery.track("c1", "hello", 0, 100);
  assert.deepEqual(delivery.settle().map((entry) => entry.commandId), ["c1"]);
  assert.deepEqual(delivery.settle(), []);
});

test("resent entry later observed is not re-sent", () => {
  const delivery = new Delivery();
  delivery.track("c1", "hello", 0, 100);
  delivery.settle();
  assert.equal(delivery.observe("hello", 0), "c1");
  assert.deepEqual(delivery.settle(), []);
});

test("content hash normalizes whitespace and counts images", () => {
  assert.equal(contentHash("  hello\r\nworld  ", 0), contentHash("hello\nworld", 0));
  assert.notEqual(contentHash("hello", 1), contentHash("hello", 0));
});

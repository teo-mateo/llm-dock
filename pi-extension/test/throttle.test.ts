import { test } from "node:test";
import assert from "node:assert/strict";

import { ToolThrottle } from "../src/throttle.ts";

test("tool updates are throttled to four per second", () => {
  const throttle = new ToolThrottle();
  assert.equal(throttle.allow("call", 1000), true);
  assert.equal(throttle.allow("call", 1100), false);
  assert.equal(throttle.allow("call", 1250), true);
  throttle.done("call");
  assert.equal(throttle.allow("call", 1250), true);
});

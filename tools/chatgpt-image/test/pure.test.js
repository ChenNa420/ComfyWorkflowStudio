import assert from "node:assert/strict";
import test from "node:test";

import { candidateKey, diffCandidates } from "../chatgpt-page.js";
import { validateChatGPTUrl } from "../config.js";
import { composeGenerationPrompt } from "../image-generator.js";
import { extensionForMime } from "../image-capture.js";

test("allows only ChatGPT HTTPS URLs", () => {
  assert.equal(new URL(validateChatGPTUrl("https://chatgpt.com/")).hostname, "chatgpt.com");
  assert.throws(() => validateChatGPTUrl("http://chatgpt.com/"));
  assert.throws(() => validateChatGPTUrl("https://example.com/"));
});

test("candidate diff keeps only unseen images", () => {
  const old = { source: "https://example.test/a.png" };
  const fresh = { source: "https://example.test/b.png" };
  const before = new Set([candidateKey(old)]);
  assert.deepEqual(diffCandidates(before, [old, fresh, fresh]), [fresh]);
});

test("prompt composition includes consistency and current shot", () => {
  const value = composeGenerationPrompt({
    prompt: "A puppy in a kitchen",
    characterProfile: "golden puppy",
    styleProfile: "soft 2D animation",
    negativePrompt: "text",
    aspectRatio: "16:9",
  });
  assert.match(value, /golden puppy/);
  assert.match(value, /soft 2D animation/);
  assert.match(value, /A puppy in a kitchen/);
  assert.match(value, /16:9/);
});

test("maps supported image MIME extensions", () => {
  assert.equal(extensionForMime("image/jpeg"), "jpg");
  assert.equal(extensionForMime("image/webp"), "webp");
  assert.equal(extensionForMime("image/png"), "png");
});

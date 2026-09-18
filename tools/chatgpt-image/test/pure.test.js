import assert from "node:assert/strict";
import test from "node:test";

import { candidateKey, diffCandidates, sessionPayloadAuthenticated } from "../chatgpt-page.js";
import { DEFAULT_CHATGPT_IMAGE_CDP_URL, DEFAULT_CHATGPT_IMAGE_URL, loadConfig, validateCdpUrl, validateChatGPTUrl } from "../config.js";
import { composeGenerationPrompt, validateSourcePageUrl } from "../image-generator.js";
import { extensionForMime } from "../image-capture.js";

test("allows only ChatGPT HTTPS URLs", () => {
  assert.equal(new URL(validateChatGPTUrl("https://chatgpt.com/")).hostname, "chatgpt.com");
  assert.throws(() => validateChatGPTUrl("http://chatgpt.com/"));
  assert.throws(() => validateChatGPTUrl("https://example.com/"));
});

test("allows CDP only on local HTTP(S)", () => {
  assert.equal(validateCdpUrl(""), "");
  assert.equal(validateCdpUrl("http://127.0.0.1:9222"), "http://127.0.0.1:9222");
  assert.equal(validateCdpUrl("http://localhost:9222/"), "http://localhost:9222");
  assert.throws(() => validateCdpUrl("ws://127.0.0.1:9222"));
  assert.throws(() => validateCdpUrl("http://192.168.1.5:9222"));
});

test("defaults to Tongyu GPT and local CDP", () => {
  const config = loadConfig({});
  assert.equal(config.cdpUrl, DEFAULT_CHATGPT_IMAGE_CDP_URL);
  assert.equal(config.chatgptUrl, DEFAULT_CHATGPT_IMAGE_URL);
  assert.match(config.chatgptUrl, /^https:\/\/chatgpt\.com\/g\//);
});

test("allows explicit CDP opt-out", () => {
  const config = loadConfig({ CWS_CHATGPT_IMAGE_CDP_URL: "off" });
  assert.equal(config.cdpUrl, "");
});

test("allows source page downloads only from local HTTP", () => {
  assert.equal(new URL(validateSourcePageUrl("http://127.0.0.1:8100/api/page/1")).hostname, "127.0.0.1");
  assert.equal(new URL(validateSourcePageUrl("http://localhost:8100/api/page/1")).hostname, "localhost");
  assert.throws(() => validateSourcePageUrl("https://127.0.0.1:8100/api/page/1"));
  assert.throws(() => validateSourcePageUrl("http://example.com/page.jpg"));
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


test("detects persisted ChatGPT session payload", () => {
  assert.equal(sessionPayloadAuthenticated({ user: { id: "user-1" }, expires: "2099-01-01" }), true);
  assert.equal(sessionPayloadAuthenticated({ user: { email: "a@example.test" } }), true);
  assert.equal(sessionPayloadAuthenticated({}), false);
  assert.equal(sessionPayloadAuthenticated(null), false);
});

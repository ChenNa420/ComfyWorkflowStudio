import assert from "node:assert/strict";
import test from "node:test";

import { candidateKey, diffCandidates, parseStoryJson, parseStoryJsonDetailed, sessionPayloadAuthenticated, storyRepairPrompt, validateStoryResult } from "../chatgpt-page.js";
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


test("direct keyframe prompt is sent to GPT unchanged", () => {
  const prompt = "A puppy in a warm kitchen, cinematic 2D children's animation.";
  const value = composeGenerationPrompt({
    prompt,
    promptMode: "direct",
    characterProfile: "this must not be injected",
    styleProfile: "this must not be injected",
    negativePrompt: "this must not be injected",
    aspectRatio: "9:16",
  });
  assert.equal(value, prompt);
});

test("maps supported image MIME extensions", () => {
  assert.equal(extensionForMime("image/jpeg"), "jpg");
  assert.equal(extensionForMime("image/webp"), "webp");
  assert.equal(extensionForMime("image/png"), "png");
});

test("parses fenced story JSON and validates production shape", () => {
  const value = parseStoryJson(`\`\`\`json
{"sourceUnderstanding":{},"creativeStory":{"title":"Demo"},"characterDefinitions":[],"sceneDefinitions":[],"shots":[{"shotId":"S01","imagePrompt":"frame","videoPrompt":"motion","sourcePages":[1]}]}
\`\`\``);
  assert.equal(validateStoryResult(value), value);
});

test("story parser locally repairs unescaped dialogue quotes without changing content", () => {
  const malformed = '{"sourceUnderstanding":{},"creativeStory":{"title":"Demo"},"characterDefinitions":[],"sceneDefinitions":[],"shots":[{"shotId":"S01","english":"Bobo, "wait!"","imagePrompt":"frame","videoPrompt":"motion","sourcePages":[1]}]}';
  const parsed = parseStoryJsonDetailed(malformed);
  assert.equal(parsed.repaired, true);
  assert.equal(parsed.repairMethod, "local_quote_escape");
  assert.equal(parsed.value.shots[0].english, 'Bobo, "wait!"');
  assert.equal(parsed.value.shots[0].imagePrompt, "frame");
  assert.equal(validateStoryResult(parsed.value), parsed.value);
});

test("story parser keeps punctuation after repaired dialogue quotes", () => {
  const malformed = '{"sourceUnderstanding":{},"creativeStory":{"title":"Demo"},"characterDefinitions":[],"sceneDefinitions":[],"shots":[{"shotId":"S01","english":"He said "wait!", then ran.","imagePrompt":"frame","videoPrompt":"motion","sourcePages":[1]}]}';
  const parsed = parseStoryJsonDetailed(malformed);
  assert.equal(parsed.repaired, true);
  assert.equal(parsed.value.shots[0].english, 'He said "wait!", then ran.');
  assert.equal(validateStoryResult(parsed.value), parsed.value);
});

test("story parser still rejects text that contains no JSON object", () => {
  assert.throws(() => parseStoryJson("not json at all"), /does not contain a JSON object/);
});

test("GPT repair prompt remains available as the last-resort fallback", () => {
  const malformed = '{"english":"Bobo, "wait!""}';
  const prompt = storyRepairPrompt("Unexpected token", malformed);
  assert.match(prompt, /只修复 JSON 语法/);
  assert.match(prompt, /待修复原文开始/);
  assert.match(prompt, /Bobo/);
  assert.match(prompt, /\\\"wait!/);
});


test("detects persisted ChatGPT session payload", () => {
  assert.equal(sessionPayloadAuthenticated({ user: { id: "user-1" }, expires: "2099-01-01" }), true);
  assert.equal(sessionPayloadAuthenticated({ user: { email: "a@example.test" } }), true);
  assert.equal(sessionPayloadAuthenticated({}), false);
  assert.equal(sessionPayloadAuthenticated(null), false);
});

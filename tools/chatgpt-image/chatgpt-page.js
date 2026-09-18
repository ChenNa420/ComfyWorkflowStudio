import { createHash } from "node:crypto";

import { ImageWorkerError } from "./errors.js";

export const IMAGE_SELECTOR = "main img, [role='main'] img, article img";
export const SELECTORS = Object.freeze({
  prompt: [
    "#prompt-textarea",
    "[data-testid='prompt-textarea']",
    "textarea[placeholder*='Message']",
    "textarea[placeholder*='消息']",
    "div[contenteditable='true'][role='textbox']",
  ].join(", "),
  send: [
    "[data-testid='send-button']",
    "button[aria-label='Send prompt']",
    "button[aria-label='发送提示']",
    "button[aria-label='发送']",
  ].join(", "),
  generating: [
    "[data-testid='stop-button']",
    "button[aria-label*='Stop']",
    "button[aria-label*='停止']",
  ].join(", "),
  loggedOut: [
    "button:text-is('登录')",
    "a:text-is('登录')",
    "button:text-is('Log in')",
    "a:text-is('Log in')",
    "button:text-is('免费注册')",
    "a:text-is('免费注册')",
    "button:text-is('Sign up')",
    "a:text-is('Sign up')",
  ].join(", "),
});

export function compactImageSource(source) {
  const value = String(source || "");
  if (value.length <= 500) return value;
  return `${value.slice(0, 240)}::${value.length}::${value.slice(-240)}`;
}

export function candidateKey(candidate) {
  return compactImageSource(candidate?.source || "");
}

export function diffCandidates(beforeKeys, candidates) {
  const seen = new Set();
  return candidates.filter((candidate) => {
    const key = candidateKey(candidate);
    if (!key || beforeKeys.has(key) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function sessionPayloadAuthenticated(value) {
  if (!value || typeof value !== "object") return false;
  const user = value.user && typeof value.user === "object" ? value.user : null;
  return Boolean(
    user && (user.id || user.email || user.name)
    || value.accessToken
    || value.expires
    || value.authenticated === true
  );
}

async function sessionAuthenticationState(page) {
  try {
    const value = await page.evaluate(async () => {
      try {
        const response = await fetch("/api/auth/session", {
          credentials: "include",
          cache: "no-store",
          headers: { "Accept": "application/json" },
        });
        if (!response.ok) return { known: false, status: response.status };
        const payload = await response.json();
        return { known: true, payload };
      } catch {
        return { known: false };
      }
    });
    if (!value?.known) return null;
    return sessionPayloadAuthenticated(value.payload);
  } catch {
    return null;
  }
}

async function listImageCandidates(page) {
  const rows = await page.locator(IMAGE_SELECTOR).evaluateAll((images) =>
    images.map((image) => {
      const rect = image.getBoundingClientRect();
      return {
        source: image.currentSrc || image.src || "",
        width: Math.max(image.naturalWidth || 0, Math.round(rect.width)),
        height: Math.max(image.naturalHeight || 0, Math.round(rect.height)),
        visible: rect.width > 0 && rect.height > 0,
      };
    }),
  );
  return rows.filter((row) => row.source && row.visible && row.width >= 256 && row.height >= 256);
}

async function findPromptBox(page, timeoutMs) {
  const box = page.locator(SELECTORS.prompt).first();
  try {
    await box.waitFor({ state: "visible", timeout: timeoutMs });
    return box;
  } catch {
    throw new ImageWorkerError(
      "ChatGPT prompt box is unavailable. Run the login command and sign in with the dedicated browser profile.",
      "CHATGPT_LOGIN_REQUIRED",
    );
  }
}

async function hasVisibleLoggedOutMarker(page) {
  const markers = page.locator(SELECTORS.loggedOut);
  const count = await markers.count().catch(() => 0);
  for (let index = 0; index < count; index += 1) {
    if (await markers.nth(index).isVisible().catch(() => false)) return true;
  }
  return false;
}

async function assertAuthenticated(page, timeoutMs = 20000) {
  await findPromptBox(page, timeoutMs);
  const sessionState = await sessionAuthenticationState(page);
  if (sessionState === true) {
    return { ok: true, ready: true, authenticated: true, authCheck: "session", url: page.url() };
  }
  if (sessionState === false) {
    throw new ImageWorkerError(
      "ChatGPT session endpoint reports that the dedicated browser profile is not signed in.",
      "CHATGPT_LOGIN_REQUIRED",
    );
  }
  if (await hasVisibleLoggedOutMarker(page)) {
    throw new ImageWorkerError(
      "ChatGPT appears signed out in the dedicated browser profile.",
      "CHATGPT_LOGIN_REQUIRED",
    );
  }
  return { ok: true, ready: true, authenticated: true, authCheck: "composer-fallback", url: page.url() };
}

async function waitUntilAuthenticated(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const promptVisible = await page.locator(SELECTORS.prompt).first().isVisible().catch(() => false);
    if (promptVisible) {
      const sessionState = await sessionAuthenticationState(page);
      if (sessionState === true) {
        return { ok: true, ready: true, authenticated: true, authCheck: "session", url: page.url() };
      }
      if (sessionState === null && !(await hasVisibleLoggedOutMarker(page))) {
        return { ok: true, ready: true, authenticated: true, authCheck: "composer-fallback", url: page.url() };
      }
    }
    await page.waitForTimeout(1000);
  }
  throw new ImageWorkerError(
    "Timed out waiting for ChatGPT sign-in. Complete login in the dedicated browser window, then retry.",
    "CHATGPT_LOGIN_REQUIRED",
  );
}

async function waitForNewImage(page, beforeKeys, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableSignature = "";
  let stableSince = 0;
  while (Date.now() < deadline) {
    const candidates = diffCandidates(beforeKeys, await listImageCandidates(page)).slice(0, 1);
    const signature = candidates.map(candidateKey).join("|");
    if (signature && signature === stableSignature) stableSince ||= Date.now();
    else {
      stableSignature = signature;
      stableSince = signature ? Date.now() : 0;
    }
    const generating = await page.locator(SELECTORS.generating).count().catch(() => 0);
    if (candidates.length && !generating && Date.now() - stableSince >= 4000) return candidates[0];
    await page.waitForTimeout(1000);
  }
  throw new ImageWorkerError("Timed out waiting for a newly generated ChatGPT image", "IMAGE_GENERATION_TIMEOUT");
}

function textHash(text) {
  return createHash("sha256").update(String(text || ""), "utf8").digest("hex");
}

async function assistantSnapshot(page) {
  const turns = page.locator("[data-message-author-role='assistant']");
  const count = await turns.count().catch(() => 0);
  const text = count > 0 ? (await turns.last().innerText().catch(() => "")).trim() : "";
  return { count, text, lastHash: textHash(text) };
}

async function isGenerating(page) {
  const locators = page.locator(SELECTORS.generating);
  const count = await locators.count().catch(() => 0);
  for (let index = 0; index < count; index += 1) {
    if (await locators.nth(index).isVisible().catch(() => false)) return true;
  }
  return false;
}

export function parseStoryJson(text) {
  const raw = String(text || "").trim();
  const unfenced = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
  const start = unfenced.indexOf("{");
  const end = unfenced.lastIndexOf("}");
  if (start < 0 || end <= start) {
    throw new ImageWorkerError("GPT response does not contain a JSON object", "DIRECTOR_INVALID_JSON");
  }
  try {
    return JSON.parse(unfenced.slice(start, end + 1));
  } catch (error) {
    throw new ImageWorkerError(
      "GPT returned invalid JSON: " + String(error?.message || error),
      "DIRECTOR_INVALID_JSON",
    );
  }
}

export function validateStoryResult(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ImageWorkerError("Production result must be a JSON object", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  if (Object.prototype.hasOwnProperty.call(value, "error")) {
    throw new ImageWorkerError("Production result returned an error object", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  if (!value.sourceUnderstanding || typeof value.sourceUnderstanding !== "object" || Array.isArray(value.sourceUnderstanding)) {
    throw new ImageWorkerError("Production result is missing sourceUnderstanding", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  if (!value.creativeStory || typeof value.creativeStory !== "object" || Array.isArray(value.creativeStory)) {
    throw new ImageWorkerError("Production result is missing creativeStory", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  if (!Array.isArray(value.characterDefinitions) || !Array.isArray(value.sceneDefinitions)) {
    throw new ImageWorkerError("Production result is missing characterDefinitions or sceneDefinitions", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  if (!Array.isArray(value.shots) || value.shots.length < 1 || value.shots.length > 24) {
    throw new ImageWorkerError("Production result shots must contain 1-24 items", "DIRECTOR_INVALID_PRODUCTION_JSON");
  }
  const ids = new Set();
  for (const [index, shot] of value.shots.entries()) {
    if (!shot || typeof shot !== "object" || Array.isArray(shot)) {
      throw new ImageWorkerError(`Shot ${index + 1} must be an object`, "DIRECTOR_INVALID_PRODUCTION_JSON");
    }
    const shotId = String(shot.shotId ?? "").trim();
    if (!shotId || ids.has(shotId)) {
      throw new ImageWorkerError(`Invalid or duplicate shotId at shot ${index + 1}`, "DIRECTOR_INVALID_PRODUCTION_JSON");
    }
    ids.add(shotId);
    if (!String(shot.imagePrompt || "").trim() || !String(shot.videoPrompt || "").trim()) {
      throw new ImageWorkerError(`Shot ${shotId} is missing imagePrompt or videoPrompt`, "DIRECTOR_INVALID_PRODUCTION_JSON");
    }
    if (!Array.isArray(shot.sourcePages) || !shot.sourcePages.length) {
      throw new ImageWorkerError(`Shot ${shotId} is missing sourcePages`, "DIRECTOR_INVALID_PRODUCTION_JSON");
    }
  }
  return value;
}

export function storyRepairPrompt(parseError, originalText) {
  return [
    "你刚才返回的内容外形是 JSON，但无法被标准 JSON.parse() 解析。",
    "下面附上刚才完整原文。只修复 JSON 语法，不改变故事、角色、场景、镜头数量、对白和各类 Prompt 内容。",
    "重点检查 JSON 字符串内部的英文双引号，必须写成 \\"。",
    '例如不能写： "english": "Bobo, "wait!""',
    '必须写成： "english": "Bobo, \\"wait!\\""。',
    "不要解释，不要 Markdown 代码围栏，只返回一个完整合法 JSON 对象。",
    parseError ? "解析错误：" + String(parseError).slice(0, 500) : "",
    "",
    "===== 待修复原文开始 =====",
    String(originalText || ""),
    "===== 待修复原文结束 =====",
  ].filter(Boolean).join("\n");
}

async function waitForAssistantChange(page, baseline, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableHash = "";
  let stableSince = 0;
  while (Date.now() < deadline) {
    const current = await assistantSnapshot(page);
    const changed = current.count > Number(baseline?.count || 0)
      || (current.text && current.lastHash !== String(baseline?.lastHash || ""));
    if (changed) {
      const generating = await isGenerating(page);
      if (current.lastHash === stableHash) {
        if (!stableSince) stableSince = Date.now();
      } else {
        stableHash = current.lastHash;
        stableSince = Date.now();
      }
      if (!generating && current.text && Date.now() - stableSince >= 1800) return current;
    }
    await page.waitForTimeout(650);
  }
  throw new ImageWorkerError("Timed out waiting for repaired GPT story JSON", "DIRECTOR_JSON_REPAIR_TIMEOUT");
}

async function sendRepair(page, originalText, parseError) {
  const baseline = await assistantSnapshot(page);
  const box = await findPromptBox(page, 20000);
  const prompt = storyRepairPrompt(parseError, originalText);
  try { await box.fill(prompt); }
  catch {
    await box.click();
    await page.keyboard.insertText(prompt);
  }
  const send = page.locator(SELECTORS.send).last();
  if ((await send.count()) > 0 && (await send.isVisible().catch(() => false))) await send.click();
  else await page.keyboard.press("Enter");
  return waitForAssistantChange(page, baseline, 180000);
}

async function uploadFiles(page, filePaths) {
  if (!Array.isArray(filePaths) || !filePaths.length) {
    throw new ImageWorkerError("At least one source image is required", "SOURCE_IMAGES_REQUIRED");
  }

  let input = page.locator("input[type='file']").first();
  if (!(await input.count())) {
    const addButton = page.locator([
      "[data-testid='composer-plus-btn']",
      "button[aria-label*='Attach']",
      "button[aria-label*='上传']",
      "button[aria-label*='添加']",
    ].join(", ")).first();
    if (await addButton.count() && await addButton.isVisible().catch(() => false)) {
      await addButton.click().catch(() => {});
      await page.waitForTimeout(500);
    }
    input = page.locator("input[type='file']").first();
  }

  if (!(await input.count())) {
    throw new ImageWorkerError("ChatGPT file upload input was not found", "CHATGPT_UPLOAD_INPUT_MISSING");
  }

  await input.setInputFiles(filePaths);
  await page.waitForTimeout(Math.min(15000, 2200 + filePaths.length * 650));
}

export class ChatGPTPage {
  constructor(page, config) {
    this.page = page;
    this.config = config;
  }

  async assertReady(timeoutMs = 20000) {
    return assertAuthenticated(this.page, timeoutMs);
  }

  async waitForLogin(timeoutMs) {
    return waitUntilAuthenticated(this.page, timeoutMs);
  }

  async prepareDraft(prompt, filePaths) {
    await assertAuthenticated(this.page, 20000);
    const assistantBaseline = await assistantSnapshot(this.page);
    await uploadFiles(this.page, filePaths);
    const box = await findPromptBox(this.page, 20000);
    try { await box.fill(prompt); }
    catch {
      await box.click();
      await this.page.keyboard.insertText(prompt);
    }
    await this.page.waitForTimeout(500);
    return {
      ok: true,
      prepared: true,
      sent: false,
      attachmentCount: filePaths.length,
      promptLength: String(prompt || "").length,
      assistantBaseline: { count: assistantBaseline.count, lastHash: assistantBaseline.lastHash },
      url: this.page.url(),
    };
  }

  async collectStory(baseline) {
    await assertAuthenticated(this.page, 20000);
    const current = await assistantSnapshot(this.page);
    const changed = current.count > Number(baseline?.count || 0)
      || (current.text && current.lastHash !== String(baseline?.lastHash || ""));
    if (!changed || await isGenerating(this.page)) {
      return { ok: true, pending: true, repaired: false };
    }

    let result;
    let repaired = false;
    try {
      result = validateStoryResult(parseStoryJson(current.text));
    } catch (error) {
      if (!(error instanceof ImageWorkerError) || error.code !== "DIRECTOR_INVALID_JSON") throw error;
      const repairedReply = await sendRepair(this.page, current.text, error.message);
      try {
        result = validateStoryResult(parseStoryJson(repairedReply.text));
        repaired = true;
      } catch (secondError) {
        if (secondError instanceof ImageWorkerError && secondError.code === "DIRECTOR_INVALID_JSON") {
          throw new ImageWorkerError(
            "GPT returned invalid JSON after one automatic repair: " + secondError.message,
            "DIRECTOR_JSON_REPAIR_FAILED",
          );
        }
        throw secondError;
      }
    }
    return {
      ok: true,
      pending: false,
      repaired,
      result,
      assistant: { count: current.count, lastHash: current.lastHash },
      url: this.page.url(),
    };
  }

  async generate(prompt) {
    await assertAuthenticated(this.page, 20000);
    const box = await findPromptBox(this.page, 20000);
    const before = new Set((await listImageCandidates(this.page)).map(candidateKey));
    try { await box.fill(prompt); }
    catch {
      await box.click();
      await this.page.keyboard.insertText(prompt);
    }
    const send = this.page.locator(SELECTORS.send).last();
    if ((await send.count()) > 0 && (await send.isVisible().catch(() => false))) await send.click();
    else await this.page.keyboard.press("Enter");
    return waitForNewImage(this.page, before, this.config.timeoutMs);
  }
}

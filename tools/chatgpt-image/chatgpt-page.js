import { createHash } from "node:crypto";
import path from "node:path";
import { jsonrepair } from "jsonrepair";

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

export function escapeBareQuotesInJsonStrings(text) {
  const source = String(text || "");
  let result = "";
  let inString = false;
  let escaped = false;

  const isWhitespace = (value) => /\s/.test(value || "");
  const startsJsonLiteral = (index) => {
    const tail = source.slice(index);
    return /^(?:true|false|null)(?=\s*[,\]}]|\s*$)/.test(tail);
  };
  const commaLooksStructural = (index) => {
    let cursor = index + 1;
    while (cursor < source.length && isWhitespace(source[cursor])) cursor += 1;
    const next = source[cursor];
    if (next === undefined) return true;
    return next === '"'
      || next === "{"
      || next === "["
      || next === "]"
      || next === "}"
      || next === "-"
      || /[0-9]/.test(next)
      || startsJsonLiteral(cursor);
  };

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];

    if (!inString) {
      result += char;
      if (char === '"') inString = true;
      continue;
    }

    if (escaped) {
      result += char;
      escaped = false;
      continue;
    }

    if (char === "\\") {
      result += char;
      escaped = true;
      continue;
    }

    if (char !== '"') {
      result += char;
      continue;
    }

    let cursor = index + 1;
    while (cursor < source.length && isWhitespace(source[cursor])) cursor += 1;
    const next = source[cursor];
    const closesString = next === undefined
      || next === ":"
      || next === "}"
      || next === "]"
      || (next === "," && commaLooksStructural(cursor));

    if (closesString) {
      result += char;
      inString = false;
    } else {
      result += '\\"';
    }
  }

  return result;
}

export function extractStoryJsonText(text) {
  const raw = String(text || "").trim();
  const unfenced = raw.replace(/^\`\`\`(?:json)?\\s*/i, "").replace(/\\s*\`\`\`$/i, "").trim();
  const start = unfenced.indexOf("{");
  const end = unfenced.lastIndexOf("}");
  if (start < 0 || end <= start) {
    throw new ImageWorkerError("GPT response does not contain a JSON object", "DIRECTOR_INVALID_JSON");
  }
  return unfenced.slice(start, end + 1);
}

export function repairGptJsonText(text) {
  const candidate = extractStoryJsonText(text);

  try {
    JSON.parse(candidate);
    return {
      jsonText: candidate,
      repaired: false,
      repairMethod: null,
    };
  } catch (parseError) {
    const quoteEscaped = escapeBareQuotesInJsonStrings(candidate);
    if (quoteEscaped !== candidate) {
      try {
        JSON.parse(quoteEscaped);
        return {
          jsonText: quoteEscaped,
          repaired: true,
          repairMethod: "local_quote_escape",
        };
      } catch {
        // Keep the quote-escaped candidate and let jsonrepair handle the
        // remaining common LLM JSON mistakes without asking GPT to rewrite it.
      }
    }

    try {
      const repairedText = jsonrepair(quoteEscaped);
      JSON.parse(repairedText);
      return {
        jsonText: repairedText,
        repaired: true,
        repairMethod: quoteEscaped !== candidate
          ? "local_quote_escape_then_jsonrepair"
          : "local_jsonrepair",
      };
    } catch (repairError) {
      throw new ImageWorkerError(
        "GPT returned invalid JSON: "
          + String(parseError?.message || parseError)
          + "; local repair failed: "
          + String(repairError?.message || repairError),
        "DIRECTOR_INVALID_JSON",
      );
    }
  }
}

export function parseStoryJsonDetailed(text) {
  const repaired = repairGptJsonText(text);
  return {
    value: JSON.parse(repaired.jsonText),
    jsonText: repaired.jsonText,
    repaired: repaired.repaired,
    repairMethod: repaired.repairMethod,
  };
}

export function parseStoryJson(text) {
  return parseStoryJsonDetailed(text).value;
}

export function normalizeStoryResultShape(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;

  const story = value.creativeStory && typeof value.creativeStory === "object" && !Array.isArray(value.creativeStory)
    ? value.creativeStory
    : {};
  const normalizedStory = {
    title: String(story.title ?? "").trim(),
    summary: String(story.summary ?? ""),
    story: String(story.story ?? ""),
    adaptationNotes: Array.isArray(story.adaptationNotes)
      ? story.adaptationNotes.map((item) => String(item))
      : story.adaptationNotes == null || story.adaptationNotes === ""
        ? []
        : [String(story.adaptationNotes)],
  };

  const normalizedShots = Array.isArray(value.shots)
    ? value.shots.map((shot) => {
      const item = shot && typeof shot === "object" && !Array.isArray(shot) ? shot : {};
      return {
        shotId: item.shotId,
        title: String(item.title ?? ""),
        duration: item.duration,
        storyPurpose: String(item.storyPurpose ?? ""),
        speaker: item.speaker == null ? null : String(item.speaker),
        english: String(item.english ?? ""),
        chinese: String(item.chinese ?? ""),
        keyframeDescription: String(item.keyframeDescription ?? ""),
        imagePrompt: String(item.imagePrompt ?? ""),
        videoPrompt: String(item.videoPrompt ?? ""),
        negativePrompt: String(item.negativePrompt ?? ""),
        sourcePages: Array.isArray(item.sourcePages) ? item.sourcePages : [],
      };
    })
    : value.shots;

  return {
    sourceUnderstanding: value.sourceUnderstanding && typeof value.sourceUnderstanding === "object" && !Array.isArray(value.sourceUnderstanding)
      ? value.sourceUnderstanding
      : {},
    creativeStory: normalizedStory,
    characterDefinitions: Array.isArray(value.characterDefinitions) ? value.characterDefinitions : [],
    sceneDefinitions: Array.isArray(value.sceneDefinitions) ? value.sceneDefinitions : [],
    shots: normalizedShots,
  };
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
    '重点检查 JSON 字符串内部的英文双引号，必须写成 \\"。',
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

async function composerScope(page) {
  const box = await findPromptBox(page, 20000);
  const form = box.locator("xpath=ancestor::form[1]");
  if (await form.count()) return form;
  return page.locator("form").last();
}

const ATTACHMENT_EVIDENCE_SELECTOR = [
  "[data-testid*='attachment']",
  "[data-testid*='file']",
  "button[aria-label*='Remove attachment']",
  "button[aria-label*='remove attachment']",
  "button[aria-label*='Remove file']",
  "button[aria-label*='remove file']",
  "button[aria-label*='Remove image']",
  "button[aria-label*='remove image']",
  "button[aria-label*='移除附件']",
  "button[aria-label*='删除附件']",
  "button[aria-label*='删除文件']",
  "button[aria-label*='移除图片']",
  "img[src^='blob:']",
  "img[src*='files.oaiusercontent']",
].join(", ");

async function attachmentEvidence(page, filePaths) {
  const scope = await composerScope(page);
  const names = filePaths.map((filePath) => path.basename(filePath).toLowerCase());
  const scopeText = (await scope.innerText().catch(() => "")).toLowerCase();
  const pageText = (await page.locator("body").innerText().catch(() => "")).toLowerCase();
  const matchedNames = names.filter((name) => scopeText.includes(name)).length;
  const pageMatchedNames = names.filter((name) => pageText.includes(name)).length;
  const visualCount = await scope.locator(ATTACHMENT_EVIDENCE_SELECTOR).count().catch(() => 0);
  const pageVisualCount = await page.locator(ATTACHMENT_EVIDENCE_SELECTOR).count().catch(() => 0);
  const imageCount = await scope.locator("img").count().catch(() => 0);
  const pageImageCount = await page.locator("img").count().catch(() => 0);
  return { matchedNames, pageMatchedNames, visualCount, pageVisualCount, imageCount, pageImageCount };
}

export function attachmentEvidenceCount(baseline, evidence) {
  const scopeImageDelta = Math.max(0, Number(evidence?.imageCount || 0) - Number(baseline?.imageCount || 0));
  const pageImageDelta = Math.max(0, Number(evidence?.pageImageCount || 0) - Number(baseline?.pageImageCount || 0));
  const scopeVisualDelta = Math.max(0, Number(evidence?.visualCount || 0) - Number(baseline?.visualCount || 0));
  const pageVisualDelta = Math.max(0, Number(evidence?.pageVisualCount || 0) - Number(baseline?.pageVisualCount || 0));
  return Math.max(
    Number(evidence?.matchedNames || 0),
    Number(evidence?.pageMatchedNames || 0),
    scopeImageDelta,
    pageImageDelta,
    scopeVisualDelta,
    pageVisualDelta,
  );
}

async function waitForAttachmentEvidence(page, filePaths, baseline, timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const evidence = await attachmentEvidence(page, filePaths);
    const count = attachmentEvidenceCount(baseline, evidence);
    if (count >= filePaths.length) return count;
    await page.waitForTimeout(350);
  }
  return 0;
}

async function chooseComposerFileInput(page) {
  const preferred = page.locator([
    "input[type='file'][accept*='image']",
    "input[type='file'][multiple]",
    "input[type='file']",
  ].join(", "));
  const count = await preferred.count();
  return count ? preferred.nth(count - 1) : null;
}

async function uploadViaComposerInput(page, filePaths, baseline) {
  const input = await chooseComposerFileInput(page);
  if (!input) return 0;
  try {
    // ChatGPT may clear the native file input immediately after handling the
    // change event, so input.files.length is not a reliable success signal.
    // Set the files, then verify the visible attachment UI instead.
    await input.setInputFiles(filePaths);
  } catch {
    return 0;
  }
  return waitForAttachmentEvidence(page, filePaths, baseline);
}

async function uploadViaFileChooser(page, filePaths, baseline) {
  const addButton = page.locator([
    "[data-testid='composer-plus-btn']",
    "button[aria-label*='Attach']",
    "button[aria-label*='attach']",
    "button[aria-label*='上传']",
    "button[aria-label*='添加']",
    "button[aria-label*='附件']",
  ].join(", ")).last();

  if (!(await addButton.count()) || !(await addButton.isVisible().catch(() => false))) return 0;

  // Some ChatGPT layouts open the native chooser immediately from the plus button.
  const directChooser = page.waitForEvent("filechooser", { timeout: 1600 }).catch(() => null);
  await addButton.click().catch(() => {});
  let chooser = await directChooser;

  if (!chooser) {
    await page.waitForTimeout(300);
    const menuItem = page.getByText(
      /Add photos|Add files|Upload files|Upload from computer|Attach files|上传文件|上传照片|添加照片|添加文件|照片和文件|从计算机上传|从电脑上传/i,
    ).last();
    if (await menuItem.count() && await menuItem.isVisible().catch(() => false)) {
      const pendingChooser = page.waitForEvent("filechooser", { timeout: 5000 }).catch(() => null);
      await menuItem.click().catch(() => {});
      chooser = await pendingChooser;
    }
  }

  if (!chooser) return 0;
  await chooser.setFiles(filePaths);
  return waitForAttachmentEvidence(page, filePaths, baseline);
}

async function uploadFiles(page, filePaths) {
  if (!Array.isArray(filePaths) || !filePaths.length) {
    throw new ImageWorkerError("At least one source image is required", "SOURCE_IMAGES_REQUIRED");
  }

  const baseline = await attachmentEvidence(page, filePaths);
  let visibleCount = await uploadViaComposerInput(page, filePaths, baseline);
  if (visibleCount < filePaths.length) {
    // Re-check before using the chooser fallback so a slow UI render cannot
    // duplicate attachments that already finished uploading.
    visibleCount = await waitForAttachmentEvidence(page, filePaths, baseline, 1800);
  }
  if (visibleCount < filePaths.length) {
    visibleCount = await uploadViaFileChooser(page, filePaths, baseline);
  }

  if (visibleCount < filePaths.length) {
    const finalEvidence = await attachmentEvidence(page, filePaths).catch(() => null);
    throw new ImageWorkerError(
      `ChatGPT did not show all uploaded source images (${visibleCount}/${filePaths.length}). `
        + `url=${page.url()} evidence=${JSON.stringify(finalEvidence || {})}`,
      "CHATGPT_ATTACHMENT_NOT_VISIBLE",
      {
        currentUrl: page.url(),
        sourcePageCount: filePaths.length,
        attachmentEvidence: finalEvidence,
        promptBoxFound: Boolean(await page.locator(SELECTORS.prompt).count().catch(() => 0)),
      },
    );
  }

  await page.waitForTimeout(Math.min(12000, 1000 + filePaths.length * 450));
  return visibleCount;
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
    const attachmentCount = await uploadFiles(this.page, filePaths);
    const box = await findPromptBox(this.page, 20000);
    try {
      await box.fill(prompt);
    } catch {
      try {
        await box.click();
        await this.page.keyboard.insertText(prompt);
      } catch (error) {
        throw new ImageWorkerError(
          "ChatGPT source images were attached, but the story prompt could not be placed in the composer: "
            + String(error?.message || error),
          "CHATGPT_PROMPT_FILL_FAILED",
        );
      }
    }
    await this.page.waitForTimeout(500);
    const evidence = await attachmentEvidence(this.page, filePaths);
    return {
      ok: true,
      prepared: true,
      sent: false,
      attachmentCount,
      promptLength: String(prompt || "").length,
      attachmentEvidence: evidence,
      promptBoxFound: true,
      assistantBaseline: { count: assistantBaseline.count, lastHash: assistantBaseline.lastHash },
      url: this.page.url(),
    };
  }

  async collectStory(baseline, useLatest = false) {
    await assertAuthenticated(this.page, 20000);
    const current = await assistantSnapshot(this.page);
    const baselineCount = Number(baseline?.count || 0);
    const changed = current.count > baselineCount
      || (current.text && current.lastHash !== String(baseline?.lastHash || ""));
    const generating = await isGenerating(this.page);

    if (generating) {
      return {
        ok: true,
        pending: true,
        repaired: false,
        reason: "GPT_STILL_GENERATING",
        assistantCount: current.count,
        baselineCount,
      };
    }
    if ((!useLatest && !changed) || !current.text) {
      return {
        ok: true,
        pending: true,
        repaired: false,
        reason: current.text ? "NO_NEW_ASSISTANT_REPLY" : "ASSISTANT_REPLY_NOT_FOUND",
        assistantCount: current.count,
        baselineCount,
      };
    }

    // Guard against layouts where the stop/generating marker disappears briefly
    // while the assistant text is still streaming. Only parse a stable snapshot.
    await this.page.waitForTimeout(1800);
    const stable = await assistantSnapshot(this.page);
    if (
      await isGenerating(this.page)
      || !stable.text
      || stable.count !== current.count
      || stable.lastHash !== current.lastHash
    ) {
      return {
        ok: true,
        pending: true,
        repaired: false,
        reason: "ASSISTANT_REPLY_NOT_STABLE",
        assistantCount: stable.count,
        baselineCount,
      };
    }

    let result;
    let repaired = false;
    let repairMethod = null;
    try {
      const parsed = parseStoryJsonDetailed(stable.text);
      result = validateStoryResult(normalizeStoryResultShape(parsed.value));
      repaired = parsed.repaired;
      repairMethod = parsed.repairMethod;
    } catch (error) {
      if (!(error instanceof ImageWorkerError) || error.code !== "DIRECTOR_INVALID_JSON") throw error;

      // A manual "force fetch latest" must be read-only: never send another
      // message to ChatGPT while the operator is trying to pull an existing
      // completed reply back into the Studio. Return the local parse/repair
      // failure immediately so it is visible instead of appearing to hang for
      // up to three minutes inside GPT repair.
      if (useLatest) {
        throw new ImageWorkerError(
          "Latest GPT reply could not be parsed after local JSON repair: " + error.message,
          "DIRECTOR_LOCAL_JSON_REPAIR_FAILED",
        );
      }

      const repairedReply = await sendRepair(this.page, stable.text, error.message);
      try {
        const parsed = parseStoryJsonDetailed(repairedReply.text);
        result = validateStoryResult(normalizeStoryResultShape(parsed.value));
        repaired = true;
        repairMethod = parsed.repaired ? "gpt_then_local_jsonrepair" : "gpt";
      } catch (secondError) {
        if (secondError instanceof ImageWorkerError && secondError.code === "DIRECTOR_INVALID_JSON") {
          throw new ImageWorkerError(
            "GPT returned invalid JSON after local repair and one GPT repair: " + secondError.message,
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
      repairMethod,
      result,
      assistant: { count: stable.count, lastHash: stable.lastHash },
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

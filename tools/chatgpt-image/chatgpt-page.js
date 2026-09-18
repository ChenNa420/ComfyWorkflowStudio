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

export class ChatGPTPage {
  constructor(page, config) {
    this.page = page;
    this.config = config;
  }

  async assertReady(timeoutMs = 20000) {
    await findPromptBox(this.page, timeoutMs);
    return { ok: true, ready: true, url: this.page.url() };
  }

  async generate(prompt) {
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

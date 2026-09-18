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
    "button:has-text('登录')",
    "a:has-text('登录')",
    "button:has-text('Log in')",
    "a:has-text('Log in')",
    "button:has-text('免费注册')",
    "a:has-text('免费注册')",
    "button:has-text('Sign up')",
    "a:has-text('Sign up')",
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

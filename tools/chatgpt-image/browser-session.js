import fs from "node:fs/promises";
import { chromium } from "playwright-core";
import { ImageWorkerError } from "./errors.js";

function isChatGPTPage(page) {
  try {
    const host = new URL(page.url()).hostname.toLowerCase();
    return host === "chatgpt.com" || host.endsWith(".chatgpt.com");
  } catch {
    return false;
  }
}

export class BrowserSession {
  constructor(config) {
    this.config = config;
    this.browser = null;
    this.context = null;
    this.ownsContext = false;
  }

  get mode() {
    return this.config.cdpUrl ? "cdp" : "dedicated_profile";
  }

  async getContext() {
    if (this.context) return this.context;

    if (this.config.cdpUrl) {
      try {
        this.browser = await chromium.connectOverCDP(this.config.cdpUrl);
        this.context = this.browser.contexts()[0];
        if (!this.context) {
          throw new ImageWorkerError("Chrome CDP endpoint has no browser context", "CDP_CONTEXT_MISSING");
        }
        return this.context;
      } catch (error) {
        if (error instanceof ImageWorkerError) throw error;
        throw new ImageWorkerError(
          "Could not connect to the dedicated Chrome CDP endpoint. Start tools/chatgpt-image/start-cdp-chrome.cmd first.",
          "CDP_CONNECT_FAILED",
          { cause: String(error?.message || error || "") },
        );
      }
    }

    await fs.mkdir(this.config.profileDir, { recursive: true, mode: 0o700 });
    const channels = [...new Set([
      this.config.browserChannel,
      ...(process.platform === "win32" ? ["msedge", "chrome"] : ["chrome"]),
    ])];
    let lastError = null;
    for (const channel of channels) {
      try {
        this.context = await chromium.launchPersistentContext(this.config.profileDir, {
          channel,
          headless: this.config.headless,
          acceptDownloads: true,
          viewport: { width: 1440, height: 1100 },
        });
        this.ownsContext = true;
        return this.context;
      } catch (error) {
        lastError = error;
      }
    }
    throw new ImageWorkerError(
      `Could not start a dedicated Chromium browser (${channels.join(", ")}). Set CWS_CHATGPT_IMAGE_CHANNEL to an installed Playwright channel.`,
      "BROWSER_START_FAILED",
      { cause: String(lastError?.message || lastError || "") },
    );
  }

  async getPage(targetUrl) {
    const context = await this.getContext();
    const pages = context.pages();
    const page = pages.find(isChatGPTPage) || pages[0] || (await context.newPage());
    if (page.url() !== targetUrl) {
      try {
        await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
      } catch {
        throw new ImageWorkerError("Could not open ChatGPT in the dedicated browser", "CHATGPT_NAVIGATION_FAILED");
      }
    }
    return page;
  }

  async close() {
    if (this.ownsContext && this.context) await this.context.close().catch(() => {});
    // CDP mode attaches to a browser owned by the operator; never close that browser here.
    this.context = null;
    this.browser = null;
    this.ownsContext = false;
  }
}

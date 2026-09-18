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
    this.context = null;
  }

  async getContext() {
    if (this.context) return this.context;
    await fs.mkdir(this.config.profileDir, { recursive: true, mode: 0o700 });
    try {
      this.context = await chromium.launchPersistentContext(this.config.profileDir, {
        channel: this.config.browserChannel,
        headless: this.config.headless,
        acceptDownloads: true,
        viewport: { width: 1440, height: 1100 },
      });
      return this.context;
    } catch (error) {
      throw new ImageWorkerError(
        `Could not start the dedicated ${this.config.browserChannel} browser. Set CWS_CHATGPT_IMAGE_CHANNEL=msedge if Chrome is unavailable.`,
        "BROWSER_START_FAILED",
      );
    }
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
    if (this.context) await this.context.close().catch(() => {});
    this.context = null;
  }
}

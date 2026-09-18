import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { BrowserSession } from "./browser-session.js";
import { ChatGPTPage } from "./chatgpt-page.js";
import { captureImage } from "./image-capture.js";

export function composeGenerationPrompt(input) {
  const sections = [
    "Generate exactly one standalone image from this production brief. Return an image, not a text-only answer.",
  ];
  if (String(input.characterProfile || "").trim()) {
    sections.push(`[Character consistency]\n${String(input.characterProfile).trim()}`);
  }
  if (String(input.styleProfile || "").trim()) {
    sections.push(`[Visual style]\n${String(input.styleProfile).trim()}`);
  }
  sections.push(`[Current shot]\n${String(input.prompt || "").trim()}`);
  if (String(input.negativePrompt || "").trim()) {
    sections.push(`[Avoid]\n${String(input.negativePrompt).trim()}`);
  }
  if (String(input.aspectRatio || "").trim()) {
    sections.push(`[Aspect ratio]\n${String(input.aspectRatio).trim()}`);
  }
  sections.push("No collage, contact sheet, subtitles, labels, logo, watermark, or visible shot number.");
  return sections.join("\n\n");
}

export class ImageGenerator {
  constructor(config, dependencies = {}) {
    this.config = config;
    this.session = dependencies.session || new BrowserSession(config);
    this.tail = Promise.resolve();
  }

  serialize(action) {
    const task = this.tail.then(action);
    this.tail = task.catch(() => {});
    return task;
  }

  check(timeoutMs = 20000) {
    return this.serialize(async () => {
      const page = await this.session.getPage(this.config.chatgptUrl);
      return {
        ...(await new ChatGPTPage(page, this.config).assertReady(timeoutMs)),
        browserMode: this.session.mode,
      };
    });
  }

  login() {
    return this.serialize(async () => {
      const page = await this.session.getPage(this.config.chatgptUrl);
      return {
        ...(await new ChatGPTPage(page, this.config).waitForLogin(this.config.loginTimeoutMs)),
        browserMode: this.session.mode,
      };
    });
  }

  generate(input) {
    return this.serialize(async () => {
      const prompt = composeGenerationPrompt(input);
      const jobId = randomUUID();
      const outputDir = path.join(this.config.outputDir, jobId);
      await fs.mkdir(outputDir, { recursive: true, mode: 0o700 });
      const page = await this.session.getPage(this.config.chatgptUrl);
      const candidate = await new ChatGPTPage(page, this.config).generate(prompt);
      const image = await captureImage(page, candidate, outputDir, this.config.maxImageBytes);
      return { ok: true, jobId, promptLength: prompt.length, browserMode: this.session.mode, image };
    });
  }

  async close() {
    await this.session.close();
  }
}

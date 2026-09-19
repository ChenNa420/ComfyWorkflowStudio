import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

import { BrowserSession } from "./browser-session.js";
import { ChatGPTPage } from "./chatgpt-page.js";
import { captureImage } from "./image-capture.js";
import { validateChatGPTUrl } from "./config.js";
import { ImageWorkerError } from "./errors.js";

export function validateSourcePageUrl(value) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    throw new ImageWorkerError("Invalid source page URL", "INVALID_SOURCE_PAGE_URL");
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "http:" || !["127.0.0.1", "localhost", "::1", "[::1]"].includes(host)) {
    throw new ImageWorkerError("Source page URL must use local HTTP", "INVALID_SOURCE_PAGE_URL");
  }
  return parsed.toString();
}

function extensionForContentType(value) {
  const mime = String(value || "").split(";", 1)[0].trim().toLowerCase();
  if (mime === "image/png") return "png";
  if (mime === "image/webp") return "webp";
  if (mime === "image/jpeg" || mime === "image/jpg") return "jpg";
  throw new ImageWorkerError("Unsupported source page image MIME", "SOURCE_IMAGE_MIME_UNSUPPORTED");
}

async function downloadSourcePages(outputDir, sources) {
  if (!Array.isArray(sources) || !sources.length) {
    throw new ImageWorkerError("No source pages were provided", "SOURCE_IMAGES_REQUIRED");
  }
  const files = [];
  for (const source of sources) {
    const page = Number(source?.page);
    const url = validateSourcePageUrl(source?.url);
    const response = await fetch(url, { headers: { "Accept": "image/png,image/webp,image/jpeg" } });
    if (!response.ok) {
      throw new ImageWorkerError(`Source page ${page || "?"} download failed (${response.status})`, "SOURCE_IMAGE_DOWNLOAD_FAILED");
    }
    const extension = extensionForContentType(response.headers.get("content-type"));
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!bytes.length) {
      throw new ImageWorkerError(`Source page ${page || "?"} is empty`, "SOURCE_IMAGE_EMPTY");
    }
    const filePath = path.join(outputDir, `page-${String(page || files.length + 1).padStart(3, "0")}.${extension}`);
    await fs.writeFile(filePath, bytes);
    files.push(filePath);
  }
  return files;
}

export function composeGenerationPrompt(input) {
  const currentShot = String(input?.prompt || "").trim();
  if (!currentShot) {
    throw new ImageWorkerError("Shot image prompt is required", "IMAGE_PROMPT_REQUIRED");
  }

  // Legacy direct mode is kept for compatibility and still sends the exact
  // reviewed imagePrompt unchanged.
  const promptMode = String(input?.promptMode || "").toLowerCase();
  if (promptMode === "direct") {
    return currentShot;
  }

  // The faithful comic GPT uses an explicit task router. Keep the reviewed
  // imagePrompt verbatim inside a small routing envelope so the same custom GPT
  // can safely distinguish story JSON generation from single-shot image work.
  if (promptMode === "keyframe_task") {
    const sections = ["TASK_MODE: KEYFRAME_IMAGE"];
    if (String(input?.taskId || "").trim()) sections.push(`Task ID: ${String(input.taskId).trim()}`);
    if (String(input?.shotId || "").trim()) sections.push(`Shot ID: ${String(input.shotId).trim()}`);
    if (String(input?.aspectRatio || "").trim()) sections.push(`Aspect ratio: ${String(input.aspectRatio).trim()}`);
    sections.push(
      "Generate exactly one standalone keyframe image.",
      "Use the imagePrompt below as the fixed visual specification. Do not rewrite the story, replace characters, or combine multiple shots.",
      "[IMAGE PROMPT]",
      currentShot,
    );
    return sections.join("\n\n");
  }

  const sections = [
    "Generate exactly one standalone image from this production brief. Return an image, not a text-only answer.",
  ];
  if (String(input.characterProfile || "").trim()) {
    sections.push(`[Character consistency]\n${String(input.characterProfile).trim()}`);
  }
  if (String(input.styleProfile || "").trim()) {
    sections.push(`[Visual style]\n${String(input.styleProfile).trim()}`);
  }
  sections.push(`[Current shot]\n${currentShot}`);
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

  prepareStory(input) {
    return this.serialize(async () => {
      const prompt = String(input?.prompt || "").trim();
      if (!prompt) throw new ImageWorkerError("Story prompt is required", "STORY_PROMPT_REQUIRED");
      const targetUrl = validateChatGPTUrl(String(input?.gptUrl || this.config.chatgptUrl));
      const jobId = randomUUID();
      const outputDir = path.join(this.config.outputDir, "story-drafts", jobId);
      await fs.mkdir(outputDir, { recursive: true, mode: 0o700 });
      const files = await downloadSourcePages(outputDir, input?.sourcePages || []);
      const page = await this.session.getPage(targetUrl);
      let prepared;
      try {
        prepared = await new ChatGPTPage(page, this.config).prepareDraft(prompt, files);
      } catch (error) {
        error.details = {
          ...(error?.details || {}),
          currentUrl: page.url(),
          sourcePageCount: (input?.sourcePages || []).length,
          downloadedCount: files.length,
        };
        throw error;
      }
      return {
        ...prepared,
        ok: true,
        jobId,
        browserMode: this.session.mode,
        sourcePages: (input?.sourcePages || []).map((item) => Number(item?.page)).filter(Number.isInteger),
      };
    });
  }

  collectStory(input) {
    return this.serialize(async () => {
      const targetUrl = validateChatGPTUrl(String(input?.gptUrl || this.config.chatgptUrl)).toString();
      const page = await this.session.getExistingChatGPTPage(targetUrl);
      const collected = await new ChatGPTPage(page, this.config).collectStory(
        input?.assistantBaseline || {},
        input?.useLatest === true,
      );
      return {
        ...collected,
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
      const targetUrl = validateChatGPTUrl(String(input?.gptUrl || this.config.chatgptUrl)).toString();
      let page = null;
      try {
        const existing = await this.session.getExistingChatGPTPage(targetUrl);
        const target = new URL(targetUrl);
        const current = new URL(existing.url());
        const targetPath = target.pathname.replace(/\/$/, "");
        const currentPath = current.pathname.replace(/\/$/, "");
        if (
          current.hostname.toLowerCase() === target.hostname.toLowerCase()
          && (currentPath === targetPath || currentPath.startsWith(targetPath + "/"))
        ) {
          page = existing;
        }
      } catch (error) {
        if (error?.code !== "CHATGPT_PAGE_NOT_FOUND") throw error;
      }
      if (!page) page = await this.session.getPage(targetUrl);
      const candidate = await new ChatGPTPage(page, this.config).generate(prompt);
      const image = await captureImage(page, candidate, outputDir, this.config.maxImageBytes);
      return { ok: true, jobId, promptLength: prompt.length, browserMode: this.session.mode, image };
    });
  }

  async close() {
    await this.session.close();
  }
}

import path from "node:path";
import { fileURLToPath } from "node:url";

import { ImageWorkerError } from "./errors.js";

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(toolRoot, "../..");

function positiveInt(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

export function validateChatGPTUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new ImageWorkerError("Invalid ChatGPT URL", "INVALID_CHATGPT_URL");
  }
  const host = parsed.hostname.toLowerCase();
  if (parsed.protocol !== "https:" || (host !== "chatgpt.com" && !host.endsWith(".chatgpt.com"))) {
    throw new ImageWorkerError("Only HTTPS chatgpt.com URLs are allowed", "INVALID_CHATGPT_URL");
  }
  return parsed.toString();
}

export function loadConfig(env = process.env) {
  return {
    profileDir: path.resolve(env.CWS_CHATGPT_IMAGE_PROFILE_DIR || path.join(repoRoot, "storage", "chatgpt-image-browser", "profile")),
    outputDir: path.resolve(env.CWS_CHATGPT_IMAGE_OUTPUT_DIR || path.join(repoRoot, "storage", "chatgpt-image-worker")),
    chatgptUrl: validateChatGPTUrl(env.CWS_CHATGPT_IMAGE_URL || "https://chatgpt.com/"),
    browserChannel: env.CWS_CHATGPT_IMAGE_CHANNEL || "chrome",
    headless: env.CWS_CHATGPT_IMAGE_HEADLESS === "1",
    timeoutMs: positiveInt(env.CWS_CHATGPT_IMAGE_TIMEOUT_MS, 240000, 30000, 600000),
    loginTimeoutMs: positiveInt(env.CWS_CHATGPT_IMAGE_LOGIN_TIMEOUT_MS, 600000, 30000, 900000),
    maxImageBytes: positiveInt(env.CWS_CHATGPT_IMAGE_MAX_BYTES, 25 * 1024 * 1024, 1024 * 1024, 50 * 1024 * 1024),
  };
}

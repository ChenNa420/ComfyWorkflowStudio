import fs from "node:fs/promises";
import path from "node:path";

import { candidateKey, compactImageSource, IMAGE_SELECTOR } from "./chatgpt-page.js";
import { ImageWorkerError } from "./errors.js";

const MIME_EXTENSIONS = new Map([
  ["image/png", "png"],
  ["image/jpeg", "jpg"],
  ["image/webp", "webp"],
]);

export function extensionForMime(mime) {
  return MIME_EXTENSIONS.get(String(mime || "").toLowerCase()) || "png";
}

async function findImageHandle(page, candidate) {
  const target = candidateKey(candidate);
  const handles = await page.locator(IMAGE_SELECTOR).elementHandles();
  for (const handle of handles) {
    const source = await handle.evaluate((image) => image.currentSrc || image.src || "");
    if (compactImageSource(source) === target) return handle;
  }
  return null;
}

async function authenticatedFetch(page, handle) {
  return page.evaluate(async (image) => {
    const source = image.currentSrc || image.src || "";
    if (!source) return null;
    try {
      const response = await fetch(source, { credentials: "include" });
      if (!response.ok) return { ok: false, error: `HTTP ${response.status}` };
      const blob = await response.blob();
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      });
      const comma = String(dataUrl).indexOf(",");
      return {
        ok: comma > 0,
        mimeType: blob.type || "image/png",
        base64: comma > 0 ? String(dataUrl).slice(comma + 1) : "",
      };
    } catch (error) {
      return { ok: false, error: String(error?.message || error) };
    }
  }, handle);
}

export async function captureImage(page, candidate, outputDir, maxBytes) {
  await fs.mkdir(outputDir, { recursive: true, mode: 0o700 });
  const handle = await findImageHandle(page, candidate);
  if (!handle) throw new ImageWorkerError("Generated image disappeared before capture", "IMAGE_MISSING");

  const payload = await authenticatedFetch(page, handle);
  if (payload?.ok && payload.base64) {
    const content = Buffer.from(payload.base64, "base64");
    if (content.length <= maxBytes) {
      const mime = MIME_EXTENSIONS.has(payload.mimeType) ? payload.mimeType : "image/png";
      const filePath = path.join(outputDir, `frame.${extensionForMime(mime)}`);
      await fs.writeFile(filePath, content, { mode: 0o600 });
      return {
        filePath,
        mimeType: mime,
        bytes: content.length,
        width: candidate.width,
        height: candidate.height,
        captureMethod: "authenticated_image_fetch",
      };
    }
  }

  const filePath = path.join(outputDir, "frame.png");
  await handle.screenshot({ path: filePath, type: "png" });
  const stat = await fs.stat(filePath);
  if (stat.size > maxBytes) {
    await fs.rm(filePath, { force: true });
    throw new ImageWorkerError("Generated image exceeds configured size limit", "IMAGE_TOO_LARGE");
  }
  return {
    filePath,
    mimeType: "image/png",
    bytes: stat.size,
    width: candidate.width,
    height: candidate.height,
    captureMethod: "visible_element_screenshot",
  };
}

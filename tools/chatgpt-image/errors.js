export class ImageWorkerError extends Error {
  constructor(message, code = "IMAGE_WORKER_ERROR", details = undefined) {
    super(message);
    this.name = "ImageWorkerError";
    this.code = code;
    this.details = details;
  }
}

export function safeError(error) {
  return {
    ok: false,
    code: error?.code || "IMAGE_WORKER_ERROR",
    message: String(error?.message || error || "Unknown image worker error"),
    ...(error?.details && typeof error.details === "object" ? { details: error.details } : {}),
  };
}

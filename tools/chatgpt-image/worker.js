#!/usr/bin/env node
import { loadConfig } from "./config.js";
import { safeError } from "./errors.js";
import { ImageGenerator } from "./image-generator.js";

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const value = Buffer.concat(chunks).toString("utf8").trim();
  return value ? JSON.parse(value) : {};
}

async function main() {
  const command = process.argv[2] || "check";
  const config = loadConfig();
  const generator = new ImageGenerator(config);
  try {
    let result;
    if (command === "login") result = await generator.login();
    else if (command === "check") result = await generator.check();
    else if (command === "prepare-story") result = await generator.prepareStory(await readStdin());
    else if (command === "collect-story") result = await generator.collectStory(await readStdin());
    else if (command === "generate") result = await generator.generate(await readStdin());
    else throw Object.assign(new Error(`Unknown command: ${command}`), { code: "UNKNOWN_COMMAND" });
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify(safeError(error))}\n`);
    process.exitCode = 1;
  } finally {
    await generator.close();
  }
}

main()
  .then(() => {
    // A Playwright CDP transport keeps Node's event loop alive even after the
    // command is complete. Exit this short-lived worker without closing the
    // operator-owned Chrome process.
    process.exit(process.exitCode || 0);
  })
  .catch((error) => {
    process.stdout.write(`${JSON.stringify(safeError(error))}\n`, () => process.exit(1));
  });

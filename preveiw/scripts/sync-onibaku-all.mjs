import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const previewRoot = resolve(__dirname, "..");

function run(scriptName) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn("node", [resolve(__dirname, scriptName)], {
      cwd: previewRoot,
      stdio: "inherit",
    });

    child.on("exit", (code) => {
      if (code === 0) {
        resolvePromise(undefined);
        return;
      }

      reject(new Error(`${scriptName} failed with exit code ${code}`));
    });
  });
}

await run("sync-onibaku-ep01.mjs");
await run("sync-onibaku-ep02.mjs");

console.log("Synced all onibaku episodes");

import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const previewRoot = resolve(__dirname, "..");
const repoRoot = resolve(previewRoot, "..");

const sourceRoot = resolve(
  repoRoot,
  "projects/onibaku/manga/ep01-yobimizu/production/output/latest",
);
const sourcePages = resolve(sourceRoot, "pages");
const targetRoot = resolve(previewRoot, "public/onibaku/ep01");
const targetPages = resolve(targetRoot, "pages");

await rm(targetPages, { recursive: true, force: true });
await mkdir(targetPages, { recursive: true });

for (let page = 1; page <= 16; page += 1) {
  const pageNumber = String(page).padStart(2, "0");
  await copyFile(
    resolve(sourcePages, `page_${pageNumber}.png`),
    resolve(targetPages, `page_${pageNumber}.png`),
  );
}

await copyFile(resolve(sourceRoot, "book.pdf"), resolve(targetRoot, "book.pdf"));

console.log(`Synced onibaku ep01 pages to ${targetRoot}`);

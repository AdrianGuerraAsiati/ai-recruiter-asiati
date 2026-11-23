import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The shared axios client already uses baseURL "/api". A call such as
// api.post("/api/import-batches") becomes "/api/api/import-batches" and 404s in
// production while mocked unit tests still pass.
const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const DOUBLE_PREFIX = /\bapi\.(get|post|put|patch|delete)\(\s*[`"']\/api\//;

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sourceFiles(path);
    return /\.(jsx?|tsx?)$/.test(name) ? [path] : [];
  });
}

describe("API client paths", () => {
  it("never repeat the /api base prefix", () => {
    const offenders = sourceFiles(SRC).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .map((line, index) => ({ line, index }))
        .filter(({ line }) => DOUBLE_PREFIX.test(line))
        .map(({ index }) => `${relative(SRC, file)}:${index + 1}`),
    );
    expect(offenders).toEqual([]);
  });
});

#!/usr/bin/env node
/**
 * Build-time generator: parse the BLOCK_MAP defined in
 *   /app/frontend/src/components/ui/blocks/index.js
 * and write a JSON manifest the backend consumes at
 *   /app/backend/data/block_sources.json
 *
 * This keeps the frontend BLOCK_MAP (the source of truth) and the backend
 * `_BLOCK_SOURCES` map in lock-step. Run via:
 *   yarn sync:blocks
 *
 * Output schema:
 *   {
 *     "generated_at": "ISO-8601",
 *     "blocks": {
 *       "<block_id>": { "file": "SpotlightHero.jsx", "named_export": null|str }
 *     }
 *   }
 */
const fs = require("fs");
const path = require("path");

const BLOCKS_DIR = path.resolve(
  __dirname, "..", "frontend", "src", "components", "ui", "blocks"
);
const INDEX_FILE = path.join(BLOCKS_DIR, "index.js");
const OUT_FILE = path.resolve(
  __dirname, "..", "backend", "data", "block_sources.json"
);

function readIndex() {
  if (!fs.existsSync(INDEX_FILE)) {
    console.error(`[sync:blocks] index.js not found at ${INDEX_FILE}`);
    process.exit(2);
  }
  return fs.readFileSync(INDEX_FILE, "utf-8");
}

function parseImports(src) {
  const out = { default: {}, named: {} };
  // 1. Default-only: `import Name from "./File";`
  const reDefault = /import\s+([A-Za-z_$][\w$]*)\s+from\s+["']\.\/([^"']+)["']/g;
  let m;
  while ((m = reDefault.exec(src)) !== null) {
    const [, name, modPath] = m;
    out.default[name] = ensureExt(modPath);
  }
  // 2. Named imports — possibly multi-line: `import { A, B, C } from "./File";`
  //    Use [\s\S] to span newlines.
  const reNamed = /import\s*\{([\s\S]+?)\}\s*from\s+["']\.\/([^"']+)["']/g;
  while ((m = reNamed.exec(src)) !== null) {
    const [, body, modPath] = m;
    const file = ensureExt(modPath);
    body.split(",").map((s) => s.trim()).filter(Boolean).forEach((n) => {
      const clean = n.split(/\s+as\s+/)[0].trim();
      if (clean) out.named[clean] = file;
    });
  }
  return out;
}

function ensureExt(p) {
  return /\.(jsx?|tsx?)$/.test(p) ? p : `${p}.jsx`;
}

function parseBlockMap(src) {
  // Find the real export, not BLOCK_MAP mentioned in a JSDoc comment.
  const exportMatch = src.match(/export\s+const\s+BLOCK_MAP\s*=\s*\{/);
  if (!exportMatch) return {};
  const braceStart = exportMatch.index + exportMatch[0].length - 1;
  // Walk forward respecting nested braces.
  let depth = 0;
  let end = -1;
  for (let i = braceStart; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") {
      depth -= 1;
      if (depth === 0) { end = i; break; }
    }
  }
  if (end === -1) return {};
  const body = src.slice(braceStart + 1, end);
  // Entries are `"<id>": ComponentName,`
  const entryRe = /["']([^"']+)["']\s*:\s*([A-Za-z_$][\w$]*)/g;
  const map = {};
  let m;
  while ((m = entryRe.exec(body)) !== null) {
    map[m[1]] = m[2];
  }
  return map;
}

function main() {
  const src = readIndex();
  const imports = parseImports(src);
  const blockMap = parseBlockMap(src);

  const blocks = {};
  for (const [blockId, compName] of Object.entries(blockMap)) {
    if (imports.default[compName]) {
      blocks[blockId] = { file: imports.default[compName], named_export: null };
    } else if (imports.named[compName]) {
      blocks[blockId] = {
        file: imports.named[compName],
        named_export: compName,
      };
    } else {
      console.warn(
        `[sync:blocks] WARN: ${blockId} → ${compName} (no import found, skipping)`
      );
    }
  }

  const out = {
    generated_at: new Date().toISOString(),
    source_of_truth: "frontend/src/components/ui/blocks/index.js BLOCK_MAP",
    count: Object.keys(blocks).length,
    blocks,
  };

  fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
  fs.writeFileSync(OUT_FILE, JSON.stringify(out, null, 2) + "\n");
  console.log(
    `[sync:blocks] wrote ${out.count} block(s) → ${OUT_FILE}`
  );
}

main();

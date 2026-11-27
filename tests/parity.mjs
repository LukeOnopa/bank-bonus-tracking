// The Refresh offers button reads the bonus roundups with a TypeScript copy of the Python scraper's parsers
// (supabase/functions/refresh-offers/roundups.ts). This checks both read the same pages the same way.
// Pages: the samples in tests/test_scrape.py, plus any saved real pages passed as arguments (doc.html fs.html).
// Run: node tests/parity.mjs [doc.html fs.html]
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { DOMParser } from "linkedom";
import { parseDoc, parseFs } from "../supabase/functions/refresh-offers/roundups.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const [docFile, fsFile] = process.argv.slice(2);
const py = `
import json, sys
sys.path.insert(0, "tests"); sys.path.insert(0, "scripts")
import scrape, test_scrape
doc = open(sys.argv[1]).read() if len(sys.argv) > 1 else test_scrape.DOC
fs = open(sys.argv[2]).read() if len(sys.argv) > 2 else test_scrape.FS
print(json.dumps({"docHtml": doc, "fsHtml": fs, "doc": scrape.parse_doc(doc), "fs": scrape.parse_fs(fs)}))`;
const out = JSON.parse(execFileSync("python3", ["-c", py, ...(docFile ? [docFile, fsFile] : [])], { cwd: root, maxBuffer: 64 << 20 }).toString());
const ts = { doc: parseDoc(out.docHtml, DOMParser), fs: parseFs(out.fsHtml, DOMParser) };
const FIELDS = ["b", "amt", "st", "url", "srcUrl", "dd", "mindd", "mdd", "win", "tx", "cd", "fee", "pull", "exp", "branch"];
let bad = 0;
for (const k of ["doc", "fs"]) {
  if (out[k].length !== ts[k].length) { console.log(`${k}: Python found ${out[k].length} offers, TypeScript ${ts[k].length}`); bad++; }
  for (let i = 0; i < Math.min(out[k].length, ts[k].length); i++) {
    for (const f of FIELDS) {
      const a = JSON.stringify(out[k][i][f] ?? null), b = JSON.stringify(ts[k][i][f] ?? null);
      if (a !== b) { if (bad < 20) console.log(`${k} #${i} ${out[k][i].b} ${f}: python=${a} typescript=${b}`); bad++; }
    }
  }
  console.log(`${k}: ${out[k].length} offers compared`);
}
if (bad) { console.log(`${bad} differences — update roundups.ts to match scripts/scrape.py`); process.exit(1); }
console.log("Python and TypeScript roundup parsers agree");

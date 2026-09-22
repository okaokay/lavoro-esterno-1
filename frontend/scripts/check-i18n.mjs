import console from "node:console";
import process from "node:process";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath, URL } from "node:url";

const root = fileURLToPath(new URL("../src/", import.meta.url));
const englishUi = /\b(?:Loading|Retry|Cancel|Delete|Saving|Creating|Updating|Failed to|No (?:records|sources|users|history|occurrences|data)|System status|Notifications|Sign in|Sign out|Advanced Filters|Clear all|Last seen|First seen|Export selected|Export all|Source Origin|Verification Status|Never|Just now|Are you sure|Changed|Initial snapshot|Compared with|View Detailed|Apply interval|Updated|\d+ hours?|\d+ days?|Hide run|Show run|consecutive failed|Check robots|Pause|Duplicate|Disable|Enable|Authorization reference|Reason|Username \(optional\)|Complete the)\b/i;
const accessibleProperty = /\b(?:aria-label|title|placeholder)\s*=\s*["'`]([^"'`]+)["'`]/g;

function files(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? files(path) : /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

const violations = [];
for (const path of files(root)) {
  const source = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  source.split(/\r?\n/).forEach((line, index) => {
    const jsxText = line.match(/>\s*([^<{]+?)\s*</)?.[1];
    if (jsxText && englishUi.test(jsxText)) violations.push([path, index + 1, jsxText.trim()]);
    for (const match of line.matchAll(accessibleProperty)) {
      if (englishUi.test(match[1])) violations.push([path, index + 1, match[1]]);
    }
  });
}

if (violations.length) {
  for (const [path, line, text] of violations) {
    console.error(`${relative(root, path)}:${line}: testo UI inglese: ${text}`);
  }
  process.exit(1);
}

console.log("Controllo i18n superato: nessuna stringa UI inglese nota.");

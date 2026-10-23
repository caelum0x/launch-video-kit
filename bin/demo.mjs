#!/usr/bin/env node
// `npx launch-video-kit demo <url>` — the fast path before the full toolchain install.
//
// Runs only tools/brand-from-url.mjs (pure Node + Puppeteer, already a dependency of this
// package). No ffmpeg, no uv/whisper-cpp, no torch, no Python venv — those are only needed
// once you render the actual film. This exists to move the first value moment (seeing your
// own colours/fonts/logo/copy pulled out of your own site) before the ~10-minute local
// toolchain install in README.md's "Start here", per STRATEGY-2026-10-23.md move 1.
//
//   node bin/demo.mjs demo <url> [--out brand] [--no-fonts] [--max-images 8]
//   npm run demo -- <url>

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

function usage() {
  console.error('Usage: launch-video-kit demo <url> [--out brand] [--no-fonts] [--max-images 8]');
  console.error('');
  console.error('Extracts a brand kit from <url> (colours, fonts, logo, copy, screenshots) and');
  console.error('writes a one-sheet preview. Needs only Node + this package\'s own Puppeteer');
  console.error('dependency — no ffmpeg, whisper-cpp, uv or torch required for this step.');
}

const argv = process.argv.slice(2);
const cmd = argv[0];

if (cmd === '-h' || cmd === '--help' || argv.length === 0) {
  usage();
  process.exit(argv.length === 0 ? 1 : 0);
}

if (cmd !== 'demo') {
  console.error(`launch-video-kit: unknown command "${cmd}"`);
  usage();
  process.exit(1);
}

const rest = argv.slice(1);
if (rest.length === 0 || rest[0].startsWith('-')) {
  usage();
  process.exit(1);
}

const outIdx = rest.indexOf('--out');
const outDir = outIdx >= 0 && rest[outIdx + 1] ? rest[outIdx + 1] : 'brand';

const brandTool = path.join(ROOT, 'tools', 'brand-from-url.mjs');
if (!existsSync(brandTool)) {
  console.error(`launch-video-kit: expected ${brandTool} — is this running inside a clone of the kit?`);
  process.exit(1);
}

const t0 = Date.now();
const child = spawn(process.execPath, [brandTool, ...rest], {
  stdio: 'inherit',
  cwd: ROOT,
});

child.on('error', (err) => {
  console.error(`launch-video-kit: failed to start brand extraction — ${err.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  if (signal) {
    console.error(`launch-video-kit: brand extraction killed by signal ${signal}`);
    process.exit(1);
  }
  if (code === 0) {
    const previewAbs = path.join(ROOT, outDir, 'preview.html');
    const previewRel = path.relative(process.cwd(), previewAbs);
    console.log(`\ndemo: brand extracted in ${secs}s -> ${previewRel}`);
    if (existsSync(previewAbs)) {
      console.log('Open the preview:');
      console.log(`  open "${previewRel}"       # macOS`);
      console.log(`  xdg-open "${previewRel}"   # Linux`);
    }
  }
  process.exit(code ?? 1);
});

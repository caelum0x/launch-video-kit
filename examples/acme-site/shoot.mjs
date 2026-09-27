#!/usr/bin/env node
// Screenshot the 3 fictional Acme product screens.
//   node examples/acme-site/shoot.mjs
// Writes film/assets/screens/{inbox,board,roadmap}.png at 3840x2400 (2x, crisp under camera pushes)
// and examples/acme-site/img/*.png at 1920x1200 for the landing page.
import path from 'node:path';
import fs from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const film = path.join(root, 'film/assets/screens');
const site = path.join(here, 'img');
await fs.mkdir(film, { recursive: true });
await fs.mkdir(site, { recursive: true });

const browser = await puppeteer.launch({ headless: true, args: ['--allow-file-access-from-files', '--hide-scrollbars', '--font-render-hinting=none'] });
try {
  const page = await browser.newPage();
  for (const name of ['inbox', 'board', 'roadmap']) {
    const url = pathToFileURL(path.join(here, `app-${name}.html`)).href;
    for (const [dpr, dir] of [[2, film], [1, site]]) {
      await page.setViewport({ width: 1920, height: 1200, deviceScaleFactor: dpr });
      await page.goto(url, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(dir, `${name}.png`) });
    }
    console.log(`${name}: film/assets/screens/${name}.png, examples/acme-site/img/${name}.png`);
  }
} finally {
  await browser.close();
}

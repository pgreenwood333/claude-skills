// Render a real 3D iPhone 17 Pro Max with a screenshot on its screen -> transparent PNG.
//
//   node render_device.mjs --screen cap.png --out phone.png [--rotY -28 --rotX 8 --rotZ 0
//        --width 1800 --height 2800 --fov 22 --distance 6.2 --frameColor '#c9c9ce']
//
// Uses Playwright's Chromium (headless WebGL). Set PLAYWRIGHT_PKG to a node_modules dir that
// has `playwright` (default: /Volumes/PGExtHD/tools/appscreen-mcp/mcp-server/node_modules) and
// PLAYWRIGHT_BROWSERS_PATH to where Chromium lives (default /Volumes/PGExtHD/ms-playwright).
import { createRequire } from 'module';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ||= '/Volumes/PGExtHD/ms-playwright';
const pkgDir = process.env.PLAYWRIGHT_PKG || '/Volumes/PGExtHD/tools/appscreen-mcp/mcp-server/node_modules';
const require = createRequire(path.join(pkgDir, 'x.js'));
const { chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) =>
  (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1]]] : a), []));
const num = (k, d) => (args[k] !== undefined ? Number(args[k]) : d);
const opts = {
  width: num('width', 1800), height: num('height', 2800),
  rotX: num('rotX', 0), rotY: num('rotY', 0), rotZ: num('rotZ', 0),
  baseRotX: num('baseRotX', 0), baseRotY: num('baseRotY', 0),
  fov: num('fov', 22), distance: num('distance', 6.2), exposure: num('exposure', 1.0),
  keyLight: num('keyLight', 1.6), frameColor: args.frameColor || null,
  inset: num('inset', 0.035), cornerRadius: num('cornerRadius', 0.13), frontSign: num('frontSign', -1),
  pops: args.pops ? JSON.parse(args.pops) : [],
  debug: args.debug ? JSON.parse(args.debug) : null, hide: args.hide ? args.hide.split(',') : null,
};
const toData = (p, mime) => `data:${mime};base64,${fs.readFileSync(p).toString('base64')}`;
opts.model = toData(args.model || path.join(here, 'iphone-17-pro-max.glb'), 'model/gltf-binary');
opts.screen = toData(args.screen, 'image/png');

// Uses the installed Google Chrome (no Chromium download needed); override with CHROME_CHANNEL=''.
const browser = await chromium.launch({ channel: process.env.CHROME_CHANNEL ?? 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: opts.width, height: opts.height } });
page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text()); });
await page.goto('file://' + path.join(here, 'render_device.html'));
await page.waitForFunction(() => typeof window.RENDER === 'function', null, { timeout: 60000 });
await page.evaluate((o) => window.RENDER(o), opts);
await page.waitForFunction(() => window.DONE === true, null, { timeout: 120000 });
const hits = await page.evaluate(() => window.SCREEN_HITS);
await page.locator('canvas').screenshot({ path: args.out, omitBackground: true });
await browser.close();
console.log(`wrote ${args.out} (screen materials replaced: ${hits})`);

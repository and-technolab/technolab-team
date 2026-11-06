import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

const { positionals, values } = parseArgs({ allowPositionals: true, options: { browser: { type: 'string' } } });
if (positionals.length !== 2) {
  console.error('Usage: node render.mjs <deck.html> <output-directory> [--browser /path/to/chromium]');
  process.exit(2);
}
let chromium;
try { ({ chromium } = await import('playwright')); }
catch {
  console.error('Install dependencies in the tlab-deck folder: npm install --prefix <skill> --ignore-scripts; npx --prefix <skill> playwright install chromium');
  process.exit(2);
}
const [input, output] = positionals.map(value => resolve(value));
await mkdir(output, { recursive: true });
let browser;
try { browser = await chromium.launch({ headless: true, ...(values.browser ? { executablePath: values.browser } : {}) }); }
catch (error) {
  console.error('Chromium could not start. Install the Playwright browser or run this command in a local environment that permits browser processes.');
  console.error(String(error.message).split('\n')[0]);
  process.exit(1);
}
const report = { input, slides: [], errors: [], externalRequests: [], fonts: [], pdf: null };
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  page.on('pageerror', error => report.errors.push(error.message));
  await page.route(/^https?:\/\//, route => {
    report.externalRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto(pathToFileURL(input).href, { waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(window.tlabDeck), null, { timeout: 10000 });
  await page.evaluate(() => Promise.race([
    window.tlabDeck.ready,
    new Promise((_, reject) => setTimeout(() => reject(new Error('Font/image loading timed out')), 15000))
  ]));
  report.fonts = await page.evaluate(() => ['Unbounded', 'Onest', 'JetBrains Mono'].map(family => ({
    family,
    loaded: [...document.fonts].some(face => face.family.replaceAll('"', '').replaceAll("'", '') === family && face.status === 'loaded')
  })));
  const count = await page.evaluate(() => window.tlabDeck.count);
  for (let index = 0; index < count; index++) {
    await page.evaluate(index => window.tlabDeck.go(index), index);
    const issues = await page.evaluate(() => {
      const slide = document.querySelector('.slide.active');
      const bounds = slide.getBoundingClientRect();
      const found = [];
      for (const el of slide.querySelectorAll('*')) {
        if (el.closest('svg') || !el.textContent.trim() || !el.getClientRects().length) continue;
        const box = el.getBoundingClientRect();
        const label = el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).trim().replaceAll(' ', '.') : '');
        if (box.left < bounds.left - 1 || box.top < bounds.top - 1 || box.right > bounds.right + 1 || box.bottom > bounds.bottom + 1)
          found.push(label + ': outside slide');
        if (el.clientWidth && el.scrollWidth > el.clientWidth + 2) found.push(label + ': horizontal overflow');
        if (el.clientHeight && el.scrollHeight > el.clientHeight + 2) found.push(label + ': vertical overflow');
      }
      return [...new Set(found)];
    });
    const filename = `slide-${String(index + 1).padStart(2, '0')}.png`;
    await page.screenshot({ path: resolve(output, filename), animations: 'disabled' });
    report.slides.push({ number: index + 1, image: filename, issues });
  }
  await page.emulateMedia({ media: 'print' });
  const printCheck = await page.evaluate(() => ({
    visibleSlides: [...document.querySelectorAll('.slide')].filter(el => getComputedStyle(el).display !== 'none').length,
    navigationHidden: getComputedStyle(document.querySelector('.chrome')).display === 'none'
  }));
  report.print = printCheck;
  if (printCheck.visibleSlides !== count || !printCheck.navigationHidden) report.errors.push('Print mode is incomplete');
  await page.pdf({ path: resolve(output, 'deck.pdf'), printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
  report.pdf = 'deck.pdf';
  const failed = report.errors.length || report.externalRequests.length || report.fonts.some(font => !font.loaded) || report.slides.some(slide => slide.issues.length);
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ slides: count, fonts: report.fonts, externalRequests: report.externalRequests.length, issues: report.slides.flatMap(slide => slide.issues), errors: report.errors, output }, null, 2));
  if (failed) process.exitCode = 1;
} finally { await browser.close(); }


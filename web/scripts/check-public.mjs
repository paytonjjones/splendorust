import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

// Use the normal public UI. No test bridge, seed override, or private state input.
const url = process.argv[2] ?? 'https://splendorust.pages.dev';
const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1365, height: 768 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [], uploads = [], actions = {};
let boardBefore = '';
let metrics = null;
const loadingProgress = [];
page.on('worker', worker => {
  if (!worker.url().includes('game.worker-')) return;
  void worker.evaluate(() => {
    const original = self.postMessage.bind(self);
    self.postMessage = (message, ...rest) => {
      if (message.type === 'progress') console.debug('PUBLIC_ENGINE_PROGRESS ' + JSON.stringify(message.progress));
      if (message.type === 'state') console.debug('PUBLIC_SEARCH_METRICS ' + JSON.stringify(message.metrics));
      return original(message, ...rest);
    };
  });
});
page.on('console', message => {
  const text = message.text();
  if (text.startsWith('PUBLIC_ENGINE_PROGRESS ')) loadingProgress.push(JSON.parse(text.slice('PUBLIC_ENGINE_PROGRESS '.length)));
  if (text.startsWith('PUBLIC_SEARCH_METRICS ')) {
    const next = JSON.parse(text.slice('PUBLIC_SEARCH_METRICS '.length));
    if (next.botTurnMs.length > (metrics?.botTurnMs.length ?? 0)) console.log(JSON.stringify({ turn: next.botTurnMs.length, ms: next.botTurnMs.at(-1), simulations: next.botSimulations.at(-1) }));
    metrics = next;
  }
});
const mark = async () => { boardBefore = await page.getByRole('main', { name: 'Two-player Splendor game' }).innerHTML(); };
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => {
  if (new URL(response.url()).pathname === '/api/games' && response.request().method() === 'POST') uploads.push(response.status());
});
const wait = async () => {
  await page.waitForFunction(before => {
    const title = document.querySelector('.action-title')?.textContent ?? '';
    return document.querySelector('main')?.innerHTML !== before && /^(Your turn|Choose your payment|Return \d+|Choose a noble|Game complete)/.test(title) &&
      !document.querySelector('.thinking-dock') &&
      (title === 'Game complete' || [...document.querySelectorAll('button:not(:disabled)')].some(button => button.matches('[data-bank-color], .card-buy, .return-token, .payment-option, .eligible-noble')));
  }, boardBefore);
};
const record = kind => { actions[kind] = (actions[kind] ?? 0) + 1; };
try {
  await page.goto(url);
  if (await page.getByLabel("Engine time for new games").inputValue() !== "10000") throw new Error("The default engine time is not 10 seconds.");
  await page.getByRole('main', { name: 'Two-player Splendor game' }).waitFor();
  if (await page.evaluate(() => typeof window.splendorTest !== 'undefined')) throw new Error('Production exposes a test bridge.');
  await wait();
  const reserve = page.locator('[data-market-slot="0"]').getByRole('button', { name: /^Reserve / });
  await mark(); await reserve.click(); record('reserve');
  await page.getByRole('timer').waitFor();
  await page.waitForFunction(() => parseFloat(document.querySelector('[role="timer"]')?.textContent || '0') >= .3);
  await page.screenshot({ path: resolve('../docs/web/screenshots/engine-thinking-1365x768.png'), fullPage: true });
  await wait();
  for (let step = 0; step < 180; step++) {
    const title = await page.locator('.action-title').innerText();
    if (title === 'Game complete') break;
    if (title === 'Choose your payment') {
      await mark(); await page.getByRole('button', { name: /^Pay / }).first().click(); record('pay');
    } else if (title.startsWith('Return ')) {
      const amount = Number(title.match(/\d+/)[0]);
      let remaining = amount;
      const tokens = page.locator('.return-token');
      for (let color = 0; color < await tokens.count() && remaining; color++) {
        const held = Number((await tokens.nth(color).getAttribute('aria-label')).match(/(\d+) held/)[1]);
        for (let count = 0; count < Math.min(held, remaining); count++) await tokens.nth(color).click();
        remaining -= Math.min(held, remaining);
      }
      await mark(); await page.getByRole('button', { name: title, exact: true }).click(); record('return');
    } else if (title === 'Choose a noble') {
      await mark(); await page.locator('.eligible-noble:not(:disabled)').first().click(); record('noble');
    } else {
      const buys = page.locator('.card-buy:not(:disabled)[aria-label^="Buy "]');
      const count = await buys.count();
      if (count) {
        const names = await buys.evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-label')));
        const best = names.map((name,index) => ({ index, points: Number(name.match(/(\d+) prestige/)[1]) })).sort((a,b) => b.points - a.points)[0];
        await mark(); await buys.nth(best.index).click(); record('buy');
      } else {
        const tokens = page.locator('[data-bank-color]:not(:disabled)');
        const amount = Math.min(3, await tokens.count());
        if (!amount) throw new Error('No gem take or purchase is available.');
        for (let index = 0; index < amount; index++) await tokens.nth(index).click();
        await mark(); await page.getByRole('button', { name: `Take ${amount} ${amount === 1 ? 'gem' : 'gems'}`, exact: true }).click(); record('take');
      }
    }
    await wait();
  }
  if (await page.locator('.action-title').innerText() !== 'Game complete') throw new Error('Public game did not complete.');
  const result = await page.getByRole('dialog').innerText();
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  await page.getByText('Moves saved for research.', { exact: true }).waitFor();
  const downloadTask = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download your games' }).click();
  const download = await downloadTask;
  const output = resolve('../local/web-games/tuning-public-browser.jsonl');
  mkdirSync(resolve('../local/web-games'), { recursive: true });
  await download.saveAs(output);
  await page.screenshot({ path: resolve('../docs/web/screenshots/engine-public-game-1365x768.png'), fullPage: true });
  const privateGet = await page.request.get(`${url}/api/games`);
  if (privateGet.status() !== 405) throw new Error('The journal endpoint permits reads.');
  if (errors.length || !uploads.length || uploads.some(status => status !== 200 && status !== 202)) throw new Error(JSON.stringify({ errors, uploads }));
  if (!metrics?.botTurnMs.length || metrics.botTurnMs.some(ms => ms > 10000)) throw new Error('Missing metrics or bot turn exceeded 10 seconds.');
  const replayBytes = readFileSync(output);
  const recordData = JSON.parse(replayBytes.toString().trim().split('\n').at(-1));
  if (recordData.effectiveSearch.inferenceBackend !== 'webgpu-f32' || recordData.effectiveSearch.turnBudgetMs !== 10000) throw new Error('Public game used unexpected engine settings.');
  for (const detail of ['Downloading runtime', 'Downloading engine weights']) {
    if (!loadingProgress.some(p => p.detail === detail && p.total > 0 && p.loaded === p.total)) throw new Error(`Missing real progress for ${detail}`);
  }
  const report = { replaySha256: createHash('sha256').update(replayBytes).digest('hex'), engineId: recordData.champion.id, effectiveSearch: recordData.effectiveSearch, loadingProgress, browser: browser.version(), metrics, schema: 'splendor-web-public-check-v1', checkedAt: new Date().toISOString(), url, result, actions, uploads, errors, testBridgeAbsent: true, publicReadsStatus: privateGet.status() };
  writeFileSync(resolve('../research/webgpu-20261006/tuning-public-check.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
  console.log(`Browser JSONL: ${output}`);
} catch (error) {
  const failure = { error: String(error), metrics, actions, uploads, errors, body: await page.locator('body').innerText() };
  writeFileSync(resolve('../local/research/webgpu-20261006/public-failure.json'), JSON.stringify(failure, null, 2) + '\n');
  await page.screenshot({ path: resolve('../local/research/webgpu-20261006/public-failure.png'), fullPage: true });
  console.log(JSON.stringify(failure));
  throw error;
} finally {
  await context.close(); await browser.close();
}

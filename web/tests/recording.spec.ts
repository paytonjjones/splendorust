import { expect, test, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import type { GameSnapshot, LegalAction, RecordedGame } from '../src/types';
import { arrowTo } from './support/keyboard';

type Exported = Omit<RecordedGame, 'writeToken'>;
async function open(page: Page, uploads = false) {
  await page.goto(`/?test=1${uploads ? '&uploadLogs=1' : ''}`);
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  return page.evaluate(() => window.splendorTest!.waitForHuman());
}
async function records(page: Page): Promise<Exported[]> {
  return (await page.evaluate(() => window.splendorTest!.exportGames())).trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}
function validate(rows: Exported[], file: string) {
  writeFileSync(file, rows.map(row => JSON.stringify(row)).join('\n') + '\n');
  const output = execFileSync('cargo', ['run', '--release', '--locked', '-p', 'splendor-arena', '--example', 'validate_web_records', '--', file], {
    cwd: path.resolve(process.cwd(), '..'), encoding: 'utf8', timeout: 120_000,
  });
  expect(output).toContain('rejected=0');
}
async function act(page: Page, action: LegalAction) {
  await page.evaluate(id => window.splendorTest!.act(id), action.id);
  return page.evaluate(() => window.splendorTest!.waitForHuman());
}
function choose(state: GameSnapshot): LegalAction {
  const actions = state.legalActions;
  if (state.stage !== 'main') return actions[0];
  const buys = actions.filter(a => a.kind === 'buy_visible' || a.kind === 'buy_reserved');
  const player = state.players[state.humanSeat];
  const cardFor = (a: LegalAction) => a.kind === 'buy_visible' ? state.market[a.slot!] : player.reserved[a.reservedIndex!]?.card;
  const progress = (bonus: number) => state.nobles.reduce((score, noble) => score + Number(player.bonuses[bonus] < noble.requirements[bonus]), 0);
  if (buys.length) return buys.sort((a,b) => {
    const ac = cardFor(a)!, bc = cardFor(b)!;
    return bc.points * 10 + progress(bc.bonus) * 4 - ac.points * 10 - progress(ac.bonus) * 4;
  })[0];
  const targets = [...state.market.filter(Boolean), ...player.reserved.flatMap(r => r?.card ? [r.card] : [])];
  const need = (card: NonNullable<typeof targets[number]>) => card.cost.map((n,c) => Math.max(0, n - player.tokens[c] - player.bonuses[c]));
  const target = targets.sort((a,b) => need(a!).reduce((s,n)=>s+n,0) - need(b!).reduce((s,n)=>s+n,0))[0];
  const takes = actions.filter(a => a.kind === 'take');
  const value = (a: LegalAction) => a.take!.reduce((s,n,c) => s + Math.min(n, target ? need(target)[c] : n) * 10 + n, 0);
  return takes.length ? takes.sort((a,b) => value(b) - value(a))[0] : actions[0];
}

async function keyboardAction(page: Page, state: GameSnapshot, action: LegalAction) {
  if (action.kind === 'take') {
    for (let color = 0; color < 5; color++) for (let n = 0; n < action.take![color]; n++) {
      await arrowTo(page, page.locator(`[data-bank-color="${color}"]`));
      await page.keyboard.press('Enter');
    }
    const amount = action.take!.reduce((s,n)=>s+n,0);
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('button', { name: `Take ${amount} gems`, exact: true })).toBeFocused();
  } else if (action.kind === 'return') {
    for (let color = 0; color < 6; color++) for (let n = 0; n < action.returns![color]; n++) {
      await arrowTo(page, page.locator('.return-token').nth(color));
      await page.keyboard.press('Enter');
    }
    await page.keyboard.press('ArrowDown');
  } else if (action.kind === 'reserve_visible') {
    await arrowTo(page, page.locator(`[data-market-slot="${action.slot}"]`).getByRole('button', { name: /^Reserve / }));
  } else if (action.kind === 'buy_visible') {
    await arrowTo(page, page.locator(`[data-market-slot="${action.slot}"]`).getByRole('button', { name: /^Buy / }));
  } else if (action.kind === 'buy_reserved') {
    await arrowTo(page, page.getByRole('button', { name: new RegExp(`^Buy your reserved card ${action.reservedIndex! + 1},`) }));
  } else if (action.kind === 'reserve_deck') {
    await arrowTo(page, page.getByRole('button', { name: new RegExp(`^Reserve a hidden tier ${action.tier} card`) }));
  } else if (action.kind === 'pay') {
    // A native select keeps its own Up/Down operation. Pay the visible first option.
    await arrowTo(page, page.getByRole('button', { name: /^Pay / }).first());
  } else if (action.kind === 'noble') {
    await arrowTo(page, page.locator(`[data-noble="${action.nobleId}"]`));
  } else throw new Error(`No keyboard flow for ${action.kind}`);
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.splendorTest!.state()?.revision), { timeout: 30_000 }).toBeGreaterThan(state.revision);
  return page.evaluate(() => window.splendorTest!.waitForHuman());
}

test('a complete game uses arrows and Enter, and its download replays in native Rust', async ({ page }, info) => {
  test.setTimeout(180_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page);
  await page.evaluate(() => window.splendorTest!.restart('91337', 0));
  let state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  const kinds = new Set<string>();
  for (let step = 0; !state.result && step < 180; step++) {
    const action = step === 0 ? state.legalActions.find(a => a.kind === 'reserve_visible')! : choose(state);
    kinds.add(action.kind);
    state = await keyboardAction(page, state, action);
  }
  expect(state.result?.status).toBe('finished');
  expect(kinds.has('take')).toBe(true);
  expect(kinds.has('buy_visible')).toBe(true);
  expect(kinds.has('reserve_visible')).toBe(true);
  await expect(page.getByRole('dialog', { name: /^(You win|SplendoRust wins|An even match\.)$/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  const downloadTask = page.waitForEvent('download');
  await arrowTo(page, page.getByRole('button', { name: 'Download your games' }));
  await page.keyboard.press('Enter');
  const download = await downloadTask;
  expect(download.suggestedFilename()).toMatch(/^splendorust-games-.*\.jsonl$/);
  const file = info.outputPath('keyboard-games.jsonl');
  await download.saveAs(file);
  const rows = readFileSync(file, 'utf8').trim().split('\n').map(line => JSON.parse(line)) as Exported[];
  expect(rows.some(row => row.status === 'finished')).toBe(true);
  expect(rows.every(row => !('writeToken' in row) && !('ownerId' in row))).toBe(true);
  const complete = rows.find(row => row.status === 'finished')!;
  expect(complete.replay.revision).toBe(complete.replay.actions.length);
  expect(complete.replay.actions.some(a => a[0] === 5)).toBe(true); // Forced and chosen payments.
  validate(rows, info.outputPath('native-validation.jsonl'));
});

test('reset and refresh retain exact u64 seeds and unfinished histories', async ({ page }, info) => {
  await open(page);
  await page.evaluate(() => window.splendorTest!.restart('18446744073709551615', 0));
  let state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  state = await act(page, state.legalActions.find(a => a.kind === 'take')!);
  const before = (await records(page)).at(-1)!;
  expect(before.replay.seed).toBe('18446744073709551615');
  expect(before.replay.revision).toBe(state.revision);
  await expect(page.evaluate(() => window.splendorTest!.act('invalid'))).rejects.toThrow();
  expect((await records(page)).at(-1)!.replay).toEqual(before.replay);
  await page.reload();
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  await expect.poll(async () => (await records(page)).find(row => row.gameId === before.gameId)?.status).toBe('abandoned');
  const rows = await records(page);
  expect(rows.find(row => row.gameId === before.gameId)!.replay).toEqual(before.replay);
  validate(rows, info.outputPath('refresh-games.jsonl'));
});

test('failed uploads survive refresh and retry without leaking export credentials', async ({ page }, info) => {
  let fail = true;
  const uploaded: RecordedGame[] = [];
  await page.route('**/api/games', async route => {
    const body = route.request().postDataJSON() as RecordedGame;
    if (fail) return route.fulfill({ status: 503, json: { error: 'Offline fixture' } });
    uploaded.push(body);
    await route.fulfill({ json: { storedVersion: body.version } });
  });
  let state = await open(page, true);
  state = await act(page, state.legalActions.find(a => a.kind === 'reserve_visible')!);
  const old = (await records(page)).at(-1)!;
  await page.evaluate(() => window.splendorTest!.retryUploads());
  await expect.poll(() => page.evaluate(() => window.splendorTest!.recorder().status)).toBe('queued');
  await page.reload();
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  fail = false;
  await page.evaluate(() => window.splendorTest!.retryUploads());
  await expect.poll(() => page.evaluate(() => window.splendorTest!.recorder().pendingUploads)).toBe(0);
  const recovered = uploaded.filter(row => row.gameId === old.gameId).at(-1)!;
  expect(recovered.status).toBe('abandoned');
  expect(recovered.replay).toEqual(old.replay);
  expect(recovered.writeToken).toMatch(/^[a-f0-9]{64}$/);
  expect(uploaded.every(row => !('ownerId' in row) && !('uploadedVersion' in row))).toBe(true);
  validate(await records(page), info.outputPath('retry-games.jsonl'));
});

test('an older upload reply leaves newer moves pending', async ({ page }) => {
  const arrivals: RecordedGame[] = [];
  let release!: () => void;
  const hold = new Promise<void>(resolve => { release = resolve; });
  let delay = true;
  await page.route('**/api/games', async route => {
    const body = route.request().postDataJSON() as RecordedGame;
    arrivals.push(body);
    if (delay) await hold;
    await route.fulfill({ json: { storedVersion: body.version } });
  });
  let state = await open(page, true);
  await page.evaluate(() => window.splendorTest!.retryUploads());
  await expect.poll(() => arrivals.length).toBeGreaterThan(0);
  state = await act(page, state.legalActions.find(a => a.kind === 'take')!);
  const newest = (await records(page)).at(-1)!;
  expect(newest.version).toBeGreaterThan(arrivals[0].version);
  delay = false; release();
  await expect.poll(() => arrivals.some(row => row.version === newest.version)).toBe(true);
  await expect.poll(() => page.evaluate(() => window.splendorTest!.recorder().pendingUploads)).toBe(0);
});

test('controls disable before a delayed worker receives a mouse action', async ({ page }) => {
  await page.addInitScript(() => {
    const original = Worker.prototype.postMessage;
    Worker.prototype.postMessage = function(message: unknown) {
      if (message && typeof message === 'object' && 'type' in message && message.type === 'act') {
        setTimeout(() => original.call(this, message), 250);
      } else original.call(this, message);
    };
  });
  const initial = await open(page);
  for (let color = 0; color < 3; color++) await page.locator(`[data-bank-color="${color}"]`).click();
  await page.getByRole('button', { name: 'Take 3 gems', exact: true }).click();
  await expect(page.locator('[data-bank-color="0"]')).toBeDisabled();
  await expect(page.locator('[data-market-slot="0"] .reserve-card')).toBeDisabled();
  const next = await page.evaluate(() => window.splendorTest!.waitForHuman());
  expect(next.revision).toBeGreaterThan(initial.revision);
  expect(next.players[next.humanSeat].tokens.slice(0, 3)).toEqual([1, 1, 1]);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('other tabs stay active and storage failure still permits play and upload', async ({ page, context }) => {
  await open(page);
  const first = (await records(page)).at(-1)!;
  const second = await context.newPage();
  const copiedOwner = await page.evaluate(() => sessionStorage.getItem('splendor-web-log-tab-owner'));
  await second.addInitScript(owner => sessionStorage.setItem('splendor-web-log-tab-owner', owner!), copiedOwner);
  await open(second);
  expect((await records(second)).find(row => row.gameId === first.gameId)!.status).toBe('in_progress');
  await second.close();
  await page.close();
  const unavailable = await context.newPage();
  await unavailable.addInitScript(() => Object.defineProperty(window, 'indexedDB', { get: () => undefined }));
  const uploaded: RecordedGame[] = [];
  await unavailable.route('**/api/games', async route => {
    const body = route.request().postDataJSON() as RecordedGame;
    uploaded.push(body);
    await route.fulfill({ json: { storedVersion: body.version } });
  });
  const state = await open(unavailable, true);
  const next = await act(unavailable, state.legalActions.find(a => a.kind === 'take')!);
  await unavailable.evaluate(() => window.splendorTest!.retryUploads());
  await expect.poll(() => uploaded.some(row => row.replay.revision === next.revision)).toBe(true);
  expect((await records(unavailable)).at(-1)!.replay.revision).toBe(next.revision);
  expect(await unavailable.evaluate(() => window.splendorTest!.recorder().status)).toBe('error');
});

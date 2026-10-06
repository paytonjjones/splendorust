import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

// Use the production search budget. Other UI tests can use small budgets.
test("registered champion runs 6400 simulations in a responsive worker", async ({ page, browser }) => {
  test.setTimeout(3_600_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest), undefined, { timeout: 60_000 });
  await page.evaluate(async () => {
    await window.splendorTest!.restart("91337", 0);
    window.splendorTest!.skipWaits(true);
    await window.splendorTest!.waitForHuman();
  });
  const result = await page.evaluate(async () => {
    const bridge = window.splendorTest!;
    const action = bridge.actions().find(a => a.kind === "take")!;
    let ticks = 0;
    let maxGap = 0;
    let previous = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      maxGap = Math.max(maxGap, now - previous);
      previous = now;
      ticks++;
    }, 20);
    const start = performance.now();
    await bridge.act(action.id);
    await bridge.waitForHuman();
    clearInterval(timer);
    return { action: action.id, events: bridge.events(), elapsedMs: performance.now() - start, ticks, maxGapMs: maxGap, metrics: bridge.metrics(), games: await bridge.exportGames() };
  });
  expect(result.action).toBe("take:1,1,1,0,0");
  expect(result.events.find(event => event.actor === 1)?.actionId).toBe("take:0,0,0,2,0");
  expect(result.metrics.botSimulations[0]).toBe(6400);
  expect(result.ticks).toBeGreaterThan(10);
  expect(result.maxGapMs).toBeLessThan(1000);
  expect(result.events.some(event => event.actor === 1)).toBe(true);
  const games = result.games.trim().split("\n").filter(Boolean).map((row: string) => JSON.parse(row));
  const evidence = { generatedAt: new Date().toISOString(), browser: browser.version(), viewport: "390x844", seed: "91337", cpuThrottle: 1, ...result, games: games.map((game: Record<string, unknown>) => { const { writeToken: _secret, ...publicGame } = game; return publicGame; }) };
  await writeFile("../research/browser-champion-20261006/browser.json", JSON.stringify(evidence, null, 2) + "\n");
  console.log(`CHAMPION_BROWSER ${JSON.stringify({ elapsedMs: result.elapsedMs, ticks: result.ticks, maxGapMs: result.maxGapMs, metrics: result.metrics })}`);
});

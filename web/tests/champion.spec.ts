import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

// Use the production search budget. Other UI tests can use small budgets.
test("WebGPU champion uses a full-turn deadline in a responsive worker", async ({ page, browser }) => {
  test.setTimeout(180_000);
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
  expect(result.metrics.botSimulations[0]).toBeGreaterThan(128);
  expect(result.metrics.botSimulations[0]).toBeLessThanOrEqual(6400);
  expect(result.metrics.botTurnMs[0]).toBeLessThanOrEqual(10000);
  expect(result.ticks).toBeGreaterThan(10);
  expect(result.maxGapMs).toBeLessThan(1000);
  expect(result.events.some(event => event.actor === 1)).toBe(true);
  const games = result.games.trim().split("\n").filter(Boolean).map((row: string) => JSON.parse(row));
  const evidence = { generatedAt: new Date().toISOString(), browser: browser.version(), viewport: "390x844", seed: "91337", cpuThrottle: 1, ...result, games: games.map((game: Record<string, unknown>) => { const { writeToken: _secret, ...publicGame } = game; return publicGame; }) };
  await writeFile("../research/webgpu-20261006/browser.json", JSON.stringify(evidence, null, 2) + "\n");
  console.log(`CHAMPION_BROWSER ${JSON.stringify({ elapsedMs: result.elapsedMs, ticks: result.ticks, maxGapMs: result.maxGapMs, metrics: result.metrics })}`);
});

for (const seed of ["17798000007", "17798000019"]) {
  test(`WebGPU full-turn limit for fresh seed ${seed}`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/?test=1");
    await page.waitForFunction(() => Boolean(window.splendorTest));
    const result = await page.evaluate(async (seed) => {
      const bridge = window.splendorTest!;
      bridge.skipWaits(true);
      await bridge.restart(seed, 1);
      await bridge.waitForHuman();
      return { metrics: bridge.metrics(), games: await bridge.exportGames() };
    }, seed);
    expect(result.metrics.botTurnMs).toHaveLength(1);
    expect(result.metrics.botTurnMs[0]).toBeLessThanOrEqual(10000);
    expect(result.metrics.botSimulations[0]).toBeGreaterThan(128);
    await writeFile(`../research/webgpu-20261006/browser-${seed}.json`, JSON.stringify({ seed, ...result, games: result.games.trim().split("\n").map(row => JSON.parse(row)) }, null, 2) + "\n");
  });
}


test("WebGPU loss of support gives an error before play", async ({ page }) => {
  const injected: Promise<void>[] = [];
  page.on("worker", worker => {
    if (!worker.url().includes("game.worker-")) return;
    injected.push(worker.evaluate(() => Object.defineProperty(navigator, "gpu", { value: undefined })).then(() => {}));
  });
  await page.goto("/?test=1");
  await expect(page.getByText("This browser does not support WebGPU.", { exact: true })).toBeVisible({ timeout: 20000 });
  await Promise.all(injected);
  expect(injected).toHaveLength(1);
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("WebGPU device loss permits a restart", async ({ page }) => {
  test.setTimeout(120_000);
  const inject = (worker: import("@playwright/test").Worker) => {
    if (!worker.url().includes("gpu.worker-")) return;
    void worker.evaluate(() => {
      const requestAdapter = navigator.gpu.requestAdapter.bind(navigator.gpu);
      navigator.gpu.requestAdapter = async (...args) => {
        const adapter = await requestAdapter(...args);
        if (adapter) {
          const requestDevice = adapter.requestDevice.bind(adapter);
          adapter.requestDevice = async (...args) => {
            const device = await requestDevice(...args);
            setTimeout(() => device.destroy(), 2000);
            return device;
          };
        }
        return adapter;
      };
    });
  };
  page.on("worker", inject);
  await page.goto("/?test=1");
  await expect(page.getByText(/WebGPU device lost/)).toBeVisible({ timeout: 60000 });
  page.off("worker", inject);
  await page.getByRole("button", { name: /Try again|Restart this game/ }).click();
  await expect(page.getByRole("main", { name: "Two-player Splendor game" })).toBeVisible({ timeout: 60000 });
});

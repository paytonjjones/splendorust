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
    const timerSamples: string[] = [];
    let previous = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      maxGap = Math.max(maxGap, now - previous);
      previous = now;
      ticks++;
      const text = document.querySelector('[role="timer"]')?.textContent;
      if (text) timerSamples.push(text);
    }, 20);
    const start = performance.now();
    await bridge.act(action.id);
    await bridge.waitForHuman();
    clearInterval(timer);
    return { timerSamples, action: action.id, events: bridge.events(), elapsedMs: performance.now() - start, ticks, maxGapMs: maxGap, metrics: bridge.metrics(), games: await bridge.exportGames() };
  });
  expect(result.timerSamples.some(text => parseFloat(text) >= 1 && text.endsWith("/ 10 s"))).toBe(true);
  await expect(page.getByRole("timer")).toHaveCount(0);
  await page.screenshot({ path: "../docs/web/screenshots/engine-settings-390x844.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(result.action).toBe("take:1,1,1,0,0");
  expect(result.metrics.botSimulations[0]).toBeGreaterThan(128);
  expect(result.metrics.botSimulations[0]).toBeLessThanOrEqual(6400);
  expect(result.metrics.botTurnMs[0]).toBeLessThanOrEqual(10000);
  expect(result.ticks).toBeGreaterThan(10);
  expect(result.maxGapMs).toBeLessThan(1000);
  expect(result.events.some(event => event.actor === 1)).toBe(true);
  const games = result.games.trim().split("\n").filter(Boolean).map((row: string) => JSON.parse(row));
  const evidence = { generatedAt: new Date().toISOString(), browser: browser.version(), viewport: "390x844", seed: "91337", cpuThrottle: 1, ...result, games: games.map((game: Record<string, unknown>) => { const { writeToken: _secret, ...publicGame } = game; return publicGame; }) };
  await writeFile("../research/webgpu-20261006/tuning-browser.json", JSON.stringify(evidence, null, 2) + "\n");
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
    await writeFile(`../research/webgpu-20261006/tuning-browser-${seed}.json`, JSON.stringify({ seed, ...result, games: result.games.trim().split("\n").map(row => { const { writeToken: _secret, ...game } = JSON.parse(row); return game; }) }, null, 2) + "\n");
  });
}


test("No WebGPU uses the smaller model and records its backend", async ({ page }) => {
  test.setTimeout(90000);
  const injected: Promise<void>[] = [];
  page.on("worker", worker => {
    if (!worker.url().includes("game.worker-")) return;
    injected.push(worker.evaluate(() => Object.defineProperty(navigator, "gpu", { value: undefined })).then(() => {}));
  });
  await page.context().route("**/*splendor_web_bg*.wasm", async route => { await Promise.all(injected); await route.continue(); });
  await page.goto("/?test=1");
  await expect(page.getByText(/Smaller engine E81/)).toBeVisible({ timeout: 60000 });
  const record = await page.evaluate(async () => { const b = window.splendorTest!; await b.waitForHuman(); await b.act(b.actions().find(a => a.kind === "take")!.id); await b.waitForHuman(); return { record: JSON.parse((await b.exportGames()).trim().split("\n")[0]), metrics: b.metrics() }; });
  expect(record.record.champion.id).toBe("E81");
  expect(record.record.effectiveSearch.inferenceBackend).toBe("wasm-cpu");
  expect(record.record.effectiveSearch.turnBudgetMs).toBe(10000);
  expect(record.metrics.botTurnMs[0]).toBeLessThanOrEqual(10000);
  expect(record.metrics.botSimulations[0]).toBeGreaterThan(0);
  expect(record.metrics.botSimulations[0]).toBeLessThanOrEqual(128);
  await writeFile("../research/webgpu-20261006/tuning-fallback.json", JSON.stringify({ ...record, record: { ...record.record, writeToken: undefined } }, null, 2) + "\n");
  await Promise.all(injected);
  expect(injected).toHaveLength(1);

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

for (const seconds of [5, 30]) {
  test(`New games use the ${seconds} second limit`, async ({ page }) => {
    test.setTimeout(120000);
    await page.goto('/?test=1');
    await expect(page.getByRole('main', { name: 'Two-player Splendor game' })).toBeVisible({ timeout: 60000 });
    await page.getByLabel('Engine time for new games').selectOption(String(seconds * 1000));
    const result = await page.evaluate(async () => {
      const bridge = window.splendorTest!;
      bridge.skipWaits(true);
      await bridge.restart('17798000007', 1);
      await bridge.waitForHuman();
      return { metrics: bridge.metrics(), game: JSON.parse((await bridge.exportGames()).trim().split('\n').at(-1)!) };
    });
    expect(result.game.effectiveSearch.turnBudgetMs).toBe(seconds * 1000);
    expect(result.metrics.botTurnMs[0]).toBeLessThanOrEqual(seconds * 1000);
    expect(result.metrics.botSimulations[0]).toBeGreaterThan(128);
    await page.reload();
    await expect(page.getByLabel('Engine time for new games')).toHaveValue(String(seconds * 1000));
  });
}

test("Engine loading shows download progress", async ({ page }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.context().route('**/onnxruntime/*.bin', async route => {
    await new Promise(resolve => setTimeout(resolve, 800));
    await route.continue();
  });
  await page.goto('/?test=1');
  await expect(page.getByRole('heading', { name: 'Loading the WebGPU engine' })).toBeVisible();
  const progress = page.getByRole('progressbar', { name: 'Downloading runtime' });
  await expect(progress).toHaveAttribute('max', '6605903');
  await expect(progress).toHaveAttribute('value', '0');
  await page.screenshot({ path: '../docs/web/screenshots/engine-loading-390x844.png', fullPage: true });
  await expect(page.getByRole('main', { name: 'Two-player Splendor game' })).toBeVisible({ timeout: 60000 });
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  expect(await page.locator('body').innerText()).not.toMatch(/champion/i);
});

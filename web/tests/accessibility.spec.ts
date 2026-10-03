import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

type TestBridge = {
  actions: () => Array<{ id: string; kind: string }>;
  act: (id: string) => Promise<unknown>;
  metrics: () => {
    wasmInitMs: number | null;
    modelLoadMs: number | null;
    botDecisionMs: number[];
    botTurnMs: number[];
  };
  restart: (seed?: string | number, seat?: number) => Promise<unknown>;
  state: () => {
    activePlayer: number;
    humanSeat: number;
    players: Array<{
      tokens: number[];
      reservedCount: number;
      ownedCards: Array<{ id: number }>;
    }>;
  } | null;
  skipWaits: (skip?: boolean) => void;
};

async function startGame(page: Page): Promise<void> {
  await page.goto("/?test=1");
  await page.getByRole("main", { name: "Two-player Splendor game" }).waitFor({
    state: "visible",
    timeout: 60_000,
  });
  await page.evaluate(() => {
    (window as unknown as { splendorTest: TestBridge }).splendorTest.skipWaits();
  });
}

test("board fits key desktop and mobile widths", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await startGame(page);

  const screenshots = path.resolve(process.cwd(), "../docs/web/screenshots");
  await mkdir(screenshots, { recursive: true });
  const viewports = [
    { name: "desktop-1728x1117", width: 1728, height: 1117 },
    { name: "laptop-1365x768", width: 1365, height: 768 },
    { name: "mobile-390x844", width: 390, height: 844 },
    { name: "mobile-320x844", width: 320, height: 844 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("main", { name: "Two-player Splendor game" })).toBeVisible();
    await page.screenshot({
      path: path.join(screenshots, `${viewport.name}.png`),
      fullPage: true,
      animations: "disabled",
    });
    const dimensions = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
    }));
    expect(dimensions.document, `${viewport.name} document overflow`).toBeLessThanOrEqual(
      dimensions.viewport,
    );
    expect(dimensions.body, `${viewport.name} body overflow`).toBeLessThanOrEqual(
      dimensions.viewport,
    );
  }
  expect(errors, "browser console and page errors").toEqual([]);
});

test("board has no WCAG A or AA violations @a11y", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await startGame(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map((violation) => {
    const targets = violation.nodes
      .slice(0, 6)
      .map((node) => node.target.join(" "))
      .join(" | ");
    return `${violation.id} (${violation.impact}, ${violation.nodes.length} nodes): ${targets}`;
  });
  expect(summary).toEqual([]);
});

test("keyboard can select gems, take them, and use the help dialog", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await startGame(page);
  const initialTokens = await page.evaluate(() => {
    const state = (window as unknown as { splendorTest: TestBridge }).splendorTest.state();
    if (!state) throw new Error("The test bridge has no game state.");
    return state.players[state.humanSeat].tokens.reduce((sum, count) => sum + count, 0);
  });

  const bank = page.getByRole("region", { name: "Shared gem bank" });
  const labels = await bank.locator("button:not([disabled])").evaluateAll((buttons) =>
    buttons
      .filter((button) => button.getAttribute("aria-label")?.includes("in bank"))
      .slice(0, 3)
      .map((button) => button.getAttribute("aria-label")),
  );
  expect(labels).toHaveLength(3);
  for (const label of labels) {
    if (!label) throw new Error("A bank token control has no accessible name.");
    const button = page.getByRole("button", { name: label, exact: true });
    await button.focus();
    await page.keyboard.press("Enter");
  }

  const take = page.getByRole("button", { name: "Take 3 gems" });
  await expect(take).toBeEnabled();
  await take.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction((expectedTokens) => {
    const state = (window as unknown as { splendorTest: TestBridge }).splendorTest.state();
    return (
      state !== null &&
      state.activePlayer === state.humanSeat &&
      state.players[state.humanSeat].tokens.reduce((sum, count) => sum + count, 0) >=
        expectedTokens
    );
  }, initialTokens + 3);
  const afterTake = await page.evaluate(() =>
    (window as unknown as { splendorTest: TestBridge }).splendorTest.state(),
  );
  expect(afterTake).not.toBeNull();
  expect(afterTake!.players[afterTake!.humanSeat].tokens.reduce((sum, count) => sum + count, 0)).toBe(
    initialTokens + 3,
  );

  const help = page.getByRole("button", { name: "How to play" });
  await help.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "A little strategy. A lot of gems." });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(help).toBeFocused();
});

test("keyboard can reserve a market card", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await startGame(page);
  const stateBefore = await page.evaluate(() =>
    (window as unknown as { splendorTest: TestBridge }).splendorTest.state(),
  );
  expect(stateBefore).not.toBeNull();

  const reserve = page.getByRole("button", { name: /^Reserve market slot/ }).first();
  await expect(reserve).toBeEnabled();
  await reserve.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction((expectedReserved) => {
    const state = (window as unknown as { splendorTest: TestBridge }).splendorTest.state();
    return (
      state !== null &&
      state.activePlayer === state.humanSeat &&
      state.players[state.humanSeat].reservedCount === expectedReserved
    );
  }, stateBefore!.players[stateBefore!.humanSeat].reservedCount + 1);
  const stateAfter = await page.evaluate(() =>
    (window as unknown as { splendorTest: TestBridge }).splendorTest.state(),
  );
  expect(stateAfter).not.toBeNull();
  expect(stateAfter!.players[stateAfter!.humanSeat].reservedCount).toBe(
    stateBefore!.players[stateBefore!.humanSeat].reservedCount + 1,
  );
});

test("keyboard can buy an affordable card", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await startGame(page);
  const readyToBuy = await page.evaluate(async () => {
    const bridge = (window as unknown as { splendorTest: TestBridge }).splendorTest;
    await bridge.restart("0x53504c454e440101", 0);
    bridge.skipWaits();
    for (let turn = 0; turn < 24; turn += 1) {
      if (bridge.actions().some((action) => action.kind === "buy_visible")) return true;
      const take = bridge.actions().find((action) => action.kind === "take");
      if (!take) throw new Error("The human player has no legal gem take while setting up a card buy.");
      await bridge.act(take.id);
    }
    return bridge.actions().some((action) => action.kind === "buy_visible");
  });
  expect(readyToBuy).toBe(true);
  const before = await page.evaluate(() => {
    const state = (window as unknown as { splendorTest: TestBridge }).splendorTest.state();
    if (!state) throw new Error("The test bridge has no game state.");
    return state.players[state.humanSeat].ownedCards.length;
  });
  const buy = page.getByRole("button", { name: /^Buy market slot/ }).first();
  await expect(buy).toBeEnabled();
  await buy.focus();
  await page.keyboard.press("Enter");

  const payment = page.getByRole("dialog", { name: "How would you like to pay?" });
  if (await payment.isVisible().catch(() => false)) {
    const choice = payment.getByRole("button", { name: /^Pay / }).first();
    await choice.focus();
    await page.keyboard.press("Enter");
  }
  await page.waitForFunction((ownedCount) => {
    const state = (window as unknown as { splendorTest: TestBridge }).splendorTest.state();
    return (
      state !== null &&
      state.activePlayer === state.humanSeat &&
      state.players[state.humanSeat].ownedCards.length > ownedCount
    );
  }, before);
});

test("real champion replies on a CPU-throttled mobile viewport @perf", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const session = await page.context().newCDPSession(page);
  await session.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  try {
    const response = await page.request.get("/champion.json");
    expect(response.ok()).toBe(true);
    const metadata = await response.json();
    expect(metadata.id).toBe("e81");
    expect(metadata.search).toMatchObject({
      agent: "flywheel-gumbel",
      iterations: 128,
      depth: 16,
      world_pool: 3,
      gumbel_max_considered: 16,
      gumbel_cvisit: 50,
      gumbel_cscale: 0.1,
      gumbel_root_noise: 0,
    });

    await startGame(page);
    const initialState = await page.evaluate(() =>
      (window as unknown as { splendorTest: TestBridge }).splendorTest.state(),
    );
    expect(initialState).not.toBeNull();
    const takeAction = await page.evaluate(() =>
      (window as unknown as { splendorTest: TestBridge }).splendorTest
        .actions()
        .find((action) => action.kind === "take")?.id,
    );
    if (!takeAction) throw new Error("The champion test game has no legal gem take.");
    await page.evaluate((id) =>
      (window as unknown as { splendorTest: TestBridge }).splendorTest.act(id),
      takeAction,
    );
    const metrics = await page.evaluate(() =>
      (window as unknown as { splendorTest: TestBridge }).splendorTest.metrics(),
    );
    expect(metrics.wasmInitMs).toBeGreaterThan(0);
    expect(metrics.modelLoadMs).toBeGreaterThan(0);
    expect(metrics.botDecisionMs.length).toBeGreaterThan(0);
    expect(metrics.botTurnMs.length).toBeGreaterThan(0);
    console.log(`WEB_PERF ${JSON.stringify({ champion: metadata.id, search: metadata.search, metrics })}`);
  } finally {
    await session.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await session.detach();
  }
});

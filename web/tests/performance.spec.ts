import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { ChampionMetadata, GameSnapshot, LegalAction } from "../src/types";

declare global {
  interface Window {
    __splendorPerf?: {
      searching: boolean;
      gaps: number[];
      searchGaps: number[];
      previous: number | null;
    };
  }
}

function percentile(values: number[], fraction: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.ceil(fraction * sorted.length) - 1)];
}

function summarize(values: number[]) {
  return {
    count: values.length,
    p50: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    max: values.length ? Math.max(...values) : null,
  };
}

function getCard(state: GameSnapshot, action: LegalAction) {
  if (action.kind === "buy_visible") return state.market[action.slot ?? -1] ?? null;
  if (action.kind === "buy_reserved") {
    return state.players[state.humanSeat].reserved[action.reservedIndex ?? -1]?.card ?? null;
  }
  return null;
}

function chooseMainAction(state: GameSnapshot): LegalAction {
  const actions = state.legalActions;
  const buys = actions.filter((action) => action.kind === "buy_visible" || action.kind === "buy_reserved");
  if (buys.length) {
    return [...buys].sort((a, b) => {
      const aCard = getCard(state, a);
      const bCard = getCard(state, b);
      return (bCard?.points ?? 0) - (aCard?.points ?? 0) || (aCard?.id ?? 0) - (bCard?.id ?? 0);
    })[0];
  }
  const takes = actions.filter((action) => action.kind === "take");
  if (takes.length) {
    return [...takes].sort((a, b) => {
      const score = (action: LegalAction) => (action.take ?? []).filter((count) => count > 0).length;
      return score(b) - score(a) || a.id.localeCompare(b.id);
    })[0];
  }
  const reserve = actions.find((action) => action.kind === "reserve_visible") ?? actions[0];
  if (!reserve) throw new Error("The human player has no legal action.");
  return reserve;
}

test("E81 midgame search keeps the mobile UI responsive @midgame-perf", async ({ page, browser }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const probe = { searching: false, gaps: [] as number[], searchGaps: [] as number[], previous: null as number | null };
    window.__splendorPerf = probe;
    const tick = (now: number) => {
      if (probe.previous !== null) {
        const gap = now - probe.previous;
        probe.gaps.push(gap);
        if (probe.searching) probe.searchGaps.push(gap);
      }
      probe.previous = now;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });

  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  try {
    const metadataResponse = await page.request.get("/champion.json");
    expect(metadataResponse.ok()).toBe(true);
    const champion = (await metadataResponse.json()) as ChampionMetadata;
    expect(champion.id).toBe("e81");
    expect(champion.model.sha256).toBe("e0e9e3b170c7d811a0474a8ce8927aa97d9f87d10db75e6c5b5cf418eaa1e5c8");
    expect(champion.search).toEqual({
      agent: "flywheel-gumbel",
      iterations: 128,
      depth: 16,
      world_pool: 3,
      gumbel_max_considered: 16,
      gumbel_cvisit: 50,
      gumbel_cscale: 0.1,
      gumbel_root_noise: 0,
    });

    await page.goto("/?test=1");
    await page.getByRole("main", { name: "Two-player Splendor game" }).waitFor({ state: "visible", timeout: 60_000 });
    await page.waitForFunction(() => Boolean(window.splendorTest));
    await page.evaluate(() => window.splendorTest!.skipWaits(true));
    await page.evaluate(() => window.splendorTest!.waitForHuman());

    const seed = "0x53504c454e440a21";
    await page.evaluate(async (gameSeed) => {
      const bridge = window.splendorTest!;
      await bridge.restart(gameSeed, 0);
      bridge.skipWaits(true);
      await bridge.waitForHuman();
    }, seed);

    const humanMoves: Array<{ kind: string; turn: number; cardsOwned: number }> = [];
    const decisionSamples: number[] = [];
    const turnSamples: number[] = [];
    for (let index = 0; index < 20; index += 1) {
      let state = await page.evaluate(() => window.splendorTest!.state());
      if (!state || state.result || state.stage === "finished" || state.stage === "blocked") break;
      if (state.activePlayer !== state.humanSeat || state.stage !== "main") {
        throw new Error(`Expected the human main phase before move ${index + 1}.`);
      }
      const action = chooseMainAction(state);
      const metricsBefore = await page.evaluate(() => window.splendorTest!.metrics());
      humanMoves.push({ kind: action.kind, turn: state.turn, cardsOwned: state.players[state.humanSeat].ownedCards.length });

      await page.evaluate(() => { window.__splendorPerf!.searching = true; });
      await page.evaluate(async (actionId) => {
        await window.splendorTest!.act(actionId);
        await window.splendorTest!.waitForHuman();
      }, action.id);

      state = await page.evaluate(() => window.splendorTest!.state());
      if (!state) throw new Error("The game state disappeared during the bot reply.");

      while (state.stage !== "main" && !state.result && state.stage !== "finished" && state.stage !== "blocked") {
        const followup = state.legalActions[0];
        if (!followup) throw new Error(`No legal follow-up action in ${state.stage} phase.`);
        await page.evaluate(async (actionId) => {
          await window.splendorTest!.act(actionId);
          await window.splendorTest!.waitForHuman();
        }, followup.id);
        state = await page.evaluate(() => window.splendorTest!.state());
        if (!state) throw new Error("The game state disappeared during a follow-up action.");
      }
      const metricsAfter = await page.evaluate(() => {
        window.__splendorPerf!.searching = false;
        return window.splendorTest!.metrics();
      });
      decisionSamples.push(...metricsAfter.botDecisionMs.slice(metricsBefore.botDecisionMs.length));
      turnSamples.push(...metricsAfter.botTurnMs.slice(metricsBefore.botTurnMs.length));
      if (state.result || state.stage === "finished" || state.stage === "blocked") break;
    }

    expect(humanMoves.length, "midgame human moves reached").toBeGreaterThanOrEqual(16);
    expect(decisionSamples.length).toBeGreaterThan(0);
    expect(turnSamples.length).toBeGreaterThan(0);
    expect(decisionSamples.every((value) => Number.isFinite(value) && value >= 0)).toBe(true);
    expect(turnSamples.every((value) => Number.isFinite(value) && value >= 0)).toBe(true);
    const midgame = await page.evaluate(() => window.splendorTest!.state());
    if (!midgame) throw new Error("No midgame snapshot is available for screenshots.");

    const screenshots = path.resolve(process.cwd(), "../docs/web/screenshots");
    await mkdir(screenshots, { recursive: true });
    const viewports = [
      { name: "midgame-desktop-1728x1117", width: 1728, height: 1117 },
      { name: "midgame-laptop-1365x768", width: 1365, height: 768 },
      { name: "midgame-mobile-390x844", width: 390, height: 844 },
    ];
    for (const viewport of viewports) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(screenshots, `${viewport.name}.png`), fullPage: true, animations: "disabled" });
    }

    const probe = await page.evaluate(() => window.__splendorPerf!);
    const metrics = await page.evaluate(() => window.splendorTest!.metrics());
    const evidence = {
      schema: "splendor-web-midgame-performance-v1",
      generatedAt: new Date().toISOString(),
      champion: { id: champion.id, sha256: champion.model.sha256, search: champion.search },
      environment: {
        browser: "Chromium",
        browserVersion: browser.version(),
        platform: process.platform,
        viewportDuringMeasurement: { width: 390, height: 844 },
        cpuThrottle: "4x via Chrome DevTools Protocol",
        seed,
      },
      humanMovesRequested: 20,
      humanMovesCompleted: humanMoves.length,
      humanMoves,
      startupMs: { wasmInit: metrics.wasmInitMs, modelLoad: metrics.modelLoadMs },
      bot: { decisionMs: summarize(decisionSamples), turnMs: summarize(turnSamples), decisionSamples, turnSamples },
      mainThread: {
        frameGapMs: summarize(probe.gaps),
        frameGapsDuringBotSearchMs: summarize(probe.searchGaps),
        frameGapsOver50ms: probe.searchGaps.filter((gap) => gap > 50).length,
        frameGapsOver100ms: probe.searchGaps.filter((gap) => gap > 100).length,
        method: "requestAnimationFrame intervals measured in the window while each bot reply was active",
      },
      midgame: {
        turn: midgame.turn,
        humanCards: midgame.players[midgame.humanSeat].ownedCards.length,
        humanPrestige: midgame.players[midgame.humanSeat].score,
        championCards: midgame.players[1 - midgame.humanSeat].ownedCards.length,
        championPrestige: midgame.players[1 - midgame.humanSeat].score,
        screenshots: viewports.map((viewport) => `docs/web/screenshots/${viewport.name}.png`),
      },
      note: "Measurements are descriptive for this browser and machine. No machine-specific latency limit is applied.",
    };
    const evidencePath = path.resolve(process.cwd(), "../docs/web/performance.json");
    await mkdir(path.dirname(evidencePath), { recursive: true });
    await writeFile(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`);
    expect(probe.searchGaps.length).toBeGreaterThan(0);
    console.log(`WEB_MIDGAME_PERF ${JSON.stringify({ bot: evidence.bot, mainThread: evidence.mainThread, moves: humanMoves.length })}`);
  } finally {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await cdp.detach();
  }
});

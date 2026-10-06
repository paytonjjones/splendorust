import { expect, test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { GameEvent, GameSnapshot, LegalAction } from "../src/types";
import { arrowTo } from "./support/keyboard";

declare global {
  interface Window {
    splendorTest?: {
      state(): GameSnapshot | null;
      actions(): LegalAction[];
      act(id: string): Promise<void>;
      restart(seed?: string | number, seat?: number, testSearchBudget?: { iterations: number; depth: number }): Promise<void>;
      waitForHuman(): Promise<GameSnapshot>;
      status(): "loading" | "ready" | "thinking" | "error";
      metrics(): { wasmInitMs: number | null; modelLoadMs: number | null; botDecisionMs: number[]; botSimulations: number[]; botTurnMs: number[] };
      events(): GameEvent[];
      clearEvents(): void;
      skipWaits(skip?: boolean): void;
      exportGames(): Promise<string>;
      recorder(): import("../src/types").GameRecorderUpdate;
      retryUploads(): void;
    };
  }
}

type FlowCounts = Record<string, number>;
type GameResultRecord = {
  seed: string;
  status: "finished" | "blocked" | "error";
  turns: number;
  humanActions: number;
  winnerMask: number | null;
  scores: number[] | null;
  actionKinds: FlowCounts;
  botActionKinds: FlowCounts;
  tokenStatesChecked: number;
  cardPartitionsChecked: number;
  voluntaryGoldPayments: number;
  paymentChoices: number;
  nobleChoices: number;
  voluntaryGoldChoices: number;
  error?: string;
};

const report = {
  schema: "splendorust-browser-playtest-v1",
  generatedAt: new Date().toISOString(),
  appUrl: "http://127.0.0.1:4174/?test=1",
  championId: "unknown",
  requestedGames: Number(process.env.PLAYTEST_GAMES ?? 30),
  completedGames: 0,
  statusCounts: { finished: 0, blocked: 0, error: 0 } as FlowCounts,
  humanEventKinds: {} as FlowCounts,
  actionKinds: {} as FlowCounts,
  botActionKinds: {} as FlowCounts,
  championModelSha256: "unknown",
  wasmInitMs: null as number | null,
  modelLoadMs: null as number | null,
  botDecisionMs: [] as number[],
  botTurnMs: [] as number[],
  totalElapsedMs: 0,
  games: [] as GameResultRecord[],
  assertions: {
    exactActionIds: true,
    publicTokenConservation: true,
    publicCardPartition: true,
    botBlindReservationsRedacted: true,
    refreshRestartsGame: false,
    resetCancelsInFlightAction: false,
    paymentDialogControl: false,
    tokenReturnControls: false,
    nobleChoiceControl: false,
    invalidActionRecovers: false,
    championFactoryParitySeed91337: false,
    nobleChoiceFixtureProfile: "unrun",
  },
};

test.describe.configure({ mode: "serial" });
let fullGameRunStarted = false;

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function record(counts: FlowCounts, value: string): void {
  counts[value] = (counts[value] ?? 0) + 1;
}

function getCard(state: GameSnapshot, action: LegalAction) {
  if (action.kind === "buy_visible" || action.kind === "reserve_visible") {
    return state.market[action.slot ?? -1] ?? null;
  }
  if (action.kind === "buy_reserved") {
    return state.players[state.humanSeat].reserved[action.reservedIndex ?? -1]?.card ?? null;
  }
  return null;
}

function nobleProgress(state: GameSnapshot, bonus: number): number {
  const player = state.players[state.humanSeat];
  let progress = 0;
  for (const noble of state.nobles) {
    const before = sum(noble.requirements.map((needed, color) => Math.max(0, needed - player.bonuses[color])));
    const after = sum(noble.requirements.map((needed, color) => Math.max(0, needed - player.bonuses[color] - Number(color === bonus))));
    progress = Math.max(progress, before - after);
  }
  return progress;
}

function chooseAction(state: GameSnapshot, gameIndex: number): LegalAction {
  const actions = state.legalActions;
  if (actions.length === 0) throw new Error(`Human has no legal action at stage ${state.stage}.`);
  const player = state.players[state.humanSeat];
  const mode = gameIndex % 3;

  if (state.stage === "payment") {
    const candidates = actions.map((action) => {
      const card = state.pendingCard;
      const required = card?.cost.map((amount, color) => Math.max(0, amount - player.bonuses[color])) ?? [];
      const goldUse = Math.max(0, sum(required) - sum(action.payment ?? []));
      return { action, goldUse };
    });
    // Some seeds prefer gold to exercise substitution, even when colored payment is legal.
    const preferGold = gameIndex % 2 === 0;
    candidates.sort((a, b) => preferGold ? b.goldUse - a.goldUse : a.goldUse - b.goldUse);
    return candidates[0].action;
  }

  if (state.stage === "return") {
    return [...actions].sort((a, b) => {
      const aLoss = (a.returns ?? []).reduce((value, count, color) => value + count * (player.tokens[color] > 1 ? 1 : 3), 0);
      const bLoss = (b.returns ?? []).reduce((value, count, color) => value + count * (player.tokens[color] > 1 ? 1 : 3), 0);
      return aLoss - bLoss;
    })[0];
  }

  if (state.stage === "noble") return actions[0];

  // Reserve a visible card or a tier-one card in one third of seeded games.
  if (state.turn <= 1 && player.reservedCount === 0) {
    if (mode === 0) {
      const visible = actions.filter((action) => action.kind === "reserve_visible");
      if (visible.length) {
        return [...visible].sort((a, b) => {
          const aCard = getCard(state, a);
          const bCard = getCard(state, b);
          return sum(aCard?.cost ?? []) - sum(bCard?.cost ?? []);
        })[0];
      }
    }
    if (mode === 1) {
      const blind = actions.find((action) => action.kind === "reserve_deck" && action.tier === 1);
      if (blind) return blind;
    }
  }

  const buy = actions.filter((action) => action.kind === "buy_visible" || action.kind === "buy_reserved");
  if (buy.length) {
    return [...buy].sort((a, b) => {
      const aCard = getCard(state, a);
      const bCard = getCard(state, b);
      const aValue = (aCard?.points ?? 0) * 10 + (aCard ? nobleProgress(state, aCard.bonus) * 18 : 0) + (aCard && player.bonuses[aCard.bonus] === 0 ? 3 : 0);
      const bValue = (bCard?.points ?? 0) * 10 + (bCard ? nobleProgress(state, bCard.bonus) * 18 : 0) + (bCard && player.bonuses[bCard.bonus] === 0 ? 3 : 0);
      return bValue - aValue;
    })[0];
  }

  const targets = [
    ...state.market.filter((card) => card !== null),
    ...player.reserved.flatMap((reservation) => reservation?.card ? [reservation.card] : []),
  ];
  const target = targets
    .map((card) => ({
      card,
      deficit: sum(card.cost.map((amount, color) => Math.max(0, amount - player.bonuses[color] - player.tokens[color]))),
    }))
    .sort((a, b) =>
      (a.deficit - a.card.points * 0.2 - nobleProgress(state, a.card.bonus) * 1.5) -
      (b.deficit - b.card.points * 0.2 - nobleProgress(state, b.card.bonus) * 1.5),
    )[0];

  const takes = actions.filter((action) => action.kind === "take");
  if (takes.length) {
    return [...takes].sort((a, b) => {
      const score = (action: LegalAction) => {
        const take = action.take ?? [];
        const useful = target
          ? sum(take.map((count, color) => Math.min(count, Math.max(0, target.card.cost[color] - player.bonuses[color] - player.tokens[color]))))
          : sum(take);
        const size = sum(take);
        return useful * 10 + (size === 2 ? 1 : 0);
      };
      return score(b) - score(a);
    })[0];
  }
  return actions[0];
}

async function snapshot(page: Page): Promise<GameSnapshot> {
  const state = await page.evaluate(() => window.splendorTest?.state() ?? null);
  if (!state) throw new Error("The browser test bridge has no game snapshot.");
  return state;
}

function assertPublicInvariants(state: GameSnapshot, tokenTotal: number): void {
  expect(sum(state.bank) + state.players.reduce((value, player) => value + sum(player.tokens), 0)).toBe(tokenTotal);
  const cards =
    sum(state.deckCounts) +
    state.market.filter(Boolean).length +
    state.players.reduce((value, player) => value + player.ownedCards.length + player.reservedCount, 0);
  expect(cards).toBe(90);
  const opponent = state.players[1 - state.humanSeat];
  for (const reservation of opponent.reserved) {
    if (reservation?.hidden) expect(reservation.card).toBeNull();
  }
  const human = state.players[state.humanSeat];
  for (const reservation of human.reserved) {
    if (reservation) {
      expect(reservation.hidden).toBe(false);
      expect(reservation.card).not.toBeNull();
    }
  }
}

function writeReport(): void {
  // A targeted UI check must not replace the retained full-game report with zero games.
  if (!fullGameRunStarted) return;
  report.generatedAt = new Date().toISOString();
  const path = fileURLToPath(new URL("../../docs/web/playtest.json", import.meta.url));
  writeFileSync(path, `${JSON.stringify(report, null, 2)}\n`);
}

async function openTestGame(
  page: Page,
  seed: string,
  seat = 0,
  testSearchBudget?: { iterations: number; depth: number },
): Promise<GameSnapshot> {
  await page.evaluate(
    ({ seed: gameSeed, seat: humanSeat, budget }) => window.splendorTest!.restart(gameSeed, humanSeat, budget),
    { seed, seat, budget: testSearchBudget },
  );
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  return page.evaluate(() => window.splendorTest!.waitForHuman());
}

async function driveUntil(
  page: Page,
  seed: string,
  gameIndex: number,
  predicate: (state: GameSnapshot) => boolean,
  seat = 0,
  testSearchBudget?: { iterations: number; depth: number },
): Promise<GameSnapshot> {
  let state = await openTestGame(page, seed, seat, testSearchBudget);
  await page.evaluate(() => window.splendorTest!.clearEvents());
  for (let steps = 0; steps < 180; steps += 1) {
    if (predicate(state)) return state;
    if (state.result || state.stage === "blocked") {
      throw new Error(`Seed ${seed} ended before the requested ${state.stage} state.`);
    }
    const action = chooseAction(state, gameIndex);
    await page.evaluate((actionId) => window.splendorTest!.act(actionId), action.id);
    state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  }
  throw new Error(`Seed ${seed} did not reach the requested state within 180 actions.`);
}

test("play seeded complete games against the WASM champion", async ({ page }) => {
  fullGameRunStarted = true;
  test.setTimeout(12 * 60 * 1000);
  page.setDefaultTimeout(90_000);
  const startedAt = Date.now();
  const requested = report.requestedGames;
  const games: GameResultRecord[] = [];

  try {
    await page.goto("/?test=1");
    await page.waitForFunction(() => Boolean(window.splendorTest));
    await page.evaluate(() => window.splendorTest!.skipWaits(true));
    await page.evaluate(() => window.splendorTest!.waitForHuman());
    const initial = await snapshot(page);
    const champion = await page.evaluate(async () => fetch("/champion.json", { cache: "no-cache" }).then((response) => response.json()));
    report.championId = champion.id ?? "unknown";
    report.championModelSha256 = champion.model?.sha256 ?? "unknown";
    const tokenTotal = sum(initial.bank) + initial.players.reduce((value, player) => value + sum(player.tokens), 0);
    const firstMetrics = await page.evaluate(() => window.splendorTest!.metrics());
    report.wasmInitMs = firstMetrics.wasmInitMs;
    report.modelLoadMs = firstMetrics.modelLoadMs;

    for (let gameIndex = 0; gameIndex < requested; gameIndex += 1) {
      const seed = `0x53504c454e440${gameIndex.toString(16).padStart(3, "0")}`;
      let state = await openTestGame(page, seed);
      await page.evaluate(() => window.splendorTest!.clearEvents());
      const gameActions: FlowCounts = {};
      const maxActions = 180;
      let humanActions = 0;
      let tokenStatesChecked = 0;
      let cardPartitionsChecked = 0;
      let paymentChoiceSituations = 0;
      let nobleChoiceSituations = 0;
      let voluntaryGoldChoices = 0;
      let status: GameResultRecord["status"] = "error";
      let error: string | undefined;
      let winnerMask: number | null = null;
      let scores: number[] | null = null;

      try {
        while (!state.result && state.stage !== "blocked" && humanActions < maxActions) {
          expect(state.activePlayer).toBe(state.humanSeat);
          assertPublicInvariants(state, tokenTotal);
          tokenStatesChecked += 1;
          cardPartitionsChecked += 1;
          const action = chooseAction(state, gameIndex);
          if (state.stage === "payment" && state.legalActions.length > 1) paymentChoiceSituations += 1;
          if (state.stage === "noble" && state.legalActions.length > 1) nobleChoiceSituations += 1;
          if (state.stage === "payment" && gameIndex % 2 === 0) {
            const player = state.players[state.humanSeat];
            const required = state.pendingCard?.cost.map((amount, color) => Math.max(0, amount - player.bonuses[color])) ?? [];
            const usesGold = (candidate: LegalAction) => Math.max(0, sum(required) - sum(candidate.payment ?? []));
            if (usesGold(action) > 0 && state.legalActions.some((candidate) => usesGold(candidate) === 0)) voluntaryGoldChoices += 1;
          }
          await page.evaluate((actionId) => window.splendorTest!.act(actionId), action.id);
          state = await page.evaluate(() => window.splendorTest!.waitForHuman());
          humanActions += 1;
          record(gameActions, action.kind);
          const events = await page.evaluate(() => window.splendorTest!.events());
          expect(events.some((event) => event.actor === state.humanSeat && event.actionId === action.id)).toBe(true);
          assertPublicInvariants(state, tokenTotal);
          tokenStatesChecked += 1;
          cardPartitionsChecked += 1;
        }
        if (!state.result && state.stage !== "blocked") {
          throw new Error(`Game exceeded ${maxActions} human actions without a result.`);
        }
        status = state.result?.status ?? "blocked";
        winnerMask = state.result?.winnerMask ?? null;
        scores = state.result?.scores ?? null;
      } catch (caught) {
        error = caught instanceof Error ? caught.message : String(caught);
        const current = await snapshot(page).catch(() => state);
        state = current;
      }

      const events = await page.evaluate(() => window.splendorTest!.events()).catch(() => [] as GameEvent[]);
      const botKinds: FlowCounts = {};
      for (const event of events) {
        if (event.actor !== state.humanSeat) record(botKinds, event.kind);
        else record(report.humanEventKinds, event.kind);
      }
      for (const [kind, count] of Object.entries(gameActions)) {
        report.actionKinds[kind] = (report.actionKinds[kind] ?? 0) + count;
      }
      for (const [kind, count] of Object.entries(botKinds)) {
        report.botActionKinds[kind] = (report.botActionKinds[kind] ?? 0) + count;
      }
      const metrics = await page.evaluate(() => window.splendorTest!.metrics()).catch(() => null);
      if (metrics) {
        report.botDecisionMs.push(...metrics.botDecisionMs);
        report.botTurnMs.push(...metrics.botTurnMs);
      }
      const gameRecord: GameResultRecord = {
        seed,
        status: error ? "error" : status,
        turns: state.turn,
        humanActions,
        winnerMask,
        scores,
        actionKinds: gameActions,
        botActionKinds: botKinds,
        tokenStatesChecked,
        cardPartitionsChecked,
        voluntaryGoldPayments: events.filter((event) => event.actor === state.humanSeat && (event.goldPayment ?? 0) > 0).length,
        paymentChoices: paymentChoiceSituations,
        nobleChoices: nobleChoiceSituations,
        voluntaryGoldChoices,
        ...(error ? { error } : {}),
      };
      games.push(gameRecord);
      report.games = [...games];
      report.completedGames = games.length;
      record(report.statusCounts, gameRecord.status);
      writeReport();
      if (error) throw new Error(`Seed ${seed} ended with ${error}`);
    }

    const allHumanKinds = new Set(Object.keys(report.actionKinds));
    expect(report.statusCounts.error ?? 0).toBe(0);
    expect(report.statusCounts.finished ?? 0).toBeGreaterThan(0);
    expect(allHumanKinds.has("take")).toBe(true);
    if (requested >= 3) {
      expect(allHumanKinds.has("reserve_visible")).toBe(true);
      expect(allHumanKinds.has("reserve_deck")).toBe(true);
      expect(allHumanKinds.has("buy_reserved")).toBe(true);
      expect(allHumanKinds.has("pay")).toBe(true);
      expect(allHumanKinds.has("return")).toBe(true);
      expect(games.reduce((value, game) => value + game.voluntaryGoldChoices, 0)).toBeGreaterThan(0);
    }
    expect(report.games.some((game) => game.winnerMask !== null)).toBe(true);
    expect(report.games.every((game) => game.tokenStatesChecked > 0 && game.cardPartitionsChecked > 0)).toBe(true);
  } finally {
    report.totalElapsedMs = Date.now() - startedAt;
    report.games = [...games];
    report.completedGames = games.length;
    writeReport();
  }
});

test("refresh and reset cancel stale worker actions", async ({ page }) => {
  test.setTimeout(120_000);
  page.setDefaultTimeout(90_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const seed = "0x53504c454e440a11";
  const baseline = await openTestGame(page, seed);

  const action = (await page.evaluate(() => window.splendorTest!.actions())).find((candidate) => candidate.kind === "take");
  if (action) {
    await page.evaluate((id) => {
      void window.splendorTest!.act(id).catch(() => undefined);
    }, action.id);
    await page.waitForFunction(() => window.splendorTest!.status() === "thinking", null, { polling: 10, timeout: 30_000 });
    await page.evaluate(() => window.splendorTest!.restart("0x53504c454e440a12", 0, { iterations: 128, depth: 16 }));
    const restarted = await page.evaluate(() => window.splendorTest!.waitForHuman());
    expect(restarted.revision).toBe(0);
    expect(restarted).not.toEqual(baseline);
    await page.waitForTimeout(350);
    expect(await snapshot(page)).toEqual(restarted);
    report.assertions.resetCancelsInFlightAction = true;
  }

  await page.reload();
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const refreshed = await snapshot(page);
  expect(refreshed.revision).toBe(0);
  expect(refreshed.humanSeat).toBe(0);
  report.assertions.refreshRestartsGame = true;
  writeReport();
});

test("an illegal action reports an error and leaves the game usable", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  const firstState = await page.evaluate(() => window.splendorTest!.waitForHuman());
  const firstAction = firstState.legalActions[0];
  expect(firstAction).toBeDefined();
  await page.evaluate((id) => window.splendorTest!.act(id), firstAction.id);
  const before = await page.evaluate(() => window.splendorTest!.waitForHuman());
  expect(before.lastEvents.length).toBeGreaterThan(0);

  await expect(page.evaluate(() => window.splendorTest!.act("not-a-legal-action"))).rejects.toThrow();
  await expect.poll(() => page.evaluate(() => window.splendorTest!.status())).toBe("ready");
  expect(await snapshot(page)).toEqual(before);

  const legalAction = (await page.evaluate(() => window.splendorTest!.actions()))[0];
  expect(legalAction).toBeDefined();
  await page.evaluate((id) => window.splendorTest!.act(id), legalAction.id);
  const after = await page.evaluate(() => window.splendorTest!.waitForHuman());
  expect(after.revision).toBeGreaterThan(before.revision);
  report.assertions.invalidActionRecovers = true;
  writeReport();
});

test("seed 91337 follows the canonical champion factory opening", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  await page.evaluate(() => window.splendorTest!.restart("91337", 0, { iterations: 128, depth: 16 }));
  const state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  const opening = state.legalActions.find((action) => action.kind === "take");
  expect(opening).toBeDefined();

  await page.evaluate(() => window.splendorTest!.clearEvents());
  await page.evaluate((id) => window.splendorTest!.act(id), opening!.id);
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const events = await page.evaluate(() => window.splendorTest!.events());
  expect(events.find((event) => event.actor === 1)?.actionId).toBe("take:0,0,0,2,0");
  report.assertions.championFactoryParitySeed91337 = true;
  writeReport();
});

test("payment alternatives work through the visible payment dialog", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const state = await driveUntil(page, "0x53504c454e440000", 0, (current) => current.stage === "payment" && current.legalActions.length > 1);
  expect(await page.getByRole("dialog", { name: "How would you like to pay?" }).count()).toBe(1);
  const required = state.pendingCard!.cost.map((amount, color) => Math.max(0, amount - state.players[state.humanSeat].bonuses[color]));
  const goldValues = state.legalActions.map((action) => Math.max(0, sum(required) - sum(action.payment ?? [])));
  const gold = Math.max(...goldValues);
  const selector = page.getByLabel("Gold to spend");
  if (new Set(goldValues).size > 1) {
    await arrowTo(page, selector);
    for (let index = 1; index < new Set(goldValues).size; index++) await page.keyboard.press("ArrowDown");
    await expect(selector).toHaveValue(String(gold));
  }
  const payment = page.getByRole("button", { name: /^Pay / }).first();
  await expect(payment).toBeEnabled();
  await arrowTo(page, payment);
  await page.keyboard.press("Enter");
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const events = await page.evaluate(() => window.splendorTest!.events());
  expect(events.some((event) => event.actor === state.humanSeat && event.kind === "pay")).toBe(true);
  report.assertions.paymentDialogControl = true;
  writeReport();
});

test("token returns work through the visible bank controls", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  let state = await openTestGame(page, "0x53504c454e440005");
  for (let step = 0; state.stage !== "return" && step < 10; step += 1) {
    expect(state.result).toBeNull();
    const takes = state.legalActions.filter((candidate) => candidate.kind === "take");
    const action = takes.sort((a, b) => sum(b.take ?? []) - sum(a.take ?? []))[0]
      ?? state.legalActions.find((candidate) => candidate.kind === "reserve_visible")
      ?? state.legalActions[0];
    expect(action).toBeDefined();
    await page.evaluate((actionId) => window.splendorTest!.act(actionId), action.id);
    state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  }
  expect(state.stage).toBe("return");
  const action = state.legalActions[0];
  expect(action?.returns).toBeDefined();
  const choices = page.locator(".return-token");
  for (let color = 0; color < (action.returns?.length ?? 0); color += 1) {
    for (let count = 0; count < (action.returns?.[color] ?? 0); count += 1) {
      await arrowTo(page, choices.nth(color));
      await page.keyboard.press("Enter");
    }
  }
  const amount = sum(action.returns ?? []);
  const submit = page.getByRole("button", { name: `Return ${amount} ${amount === 1 ? "gem" : "gems"}` });
  await expect(submit).toBeEnabled();
  await page.keyboard.press("ArrowDown");
  await expect(submit).toBeFocused();
  await page.keyboard.press("Enter");
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const events = await page.evaluate(() => window.splendorTest!.events());
  expect(events.some((event) => event.actor === state.humanSeat && event.actionId === action.id)).toBe(true);
  report.assertions.tokenReturnControls = true;
  writeReport();
});

test("a multi-noble choice works through the visible noble tiles", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/?test=1");
  await page.waitForFunction(() => Boolean(window.splendorTest));
  await page.evaluate(() => window.splendorTest!.skipWaits(true));
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  // This edge case uses a reduced search budget, while retaining champion model,
  // search agent, and Gumbel settings. The normal full-game suite uses the full profile.
  let state = await openTestGame(page, "10", 0, { iterations: 2, depth: 3 });
  const humanActions = [
    "take:1,0,0,1,1", "take:0,1,0,1,1", "buy-visible:1", "buy-visible:1",
    "take:1,0,1,1,0", "take:0,0,1,1,1", "buy-visible:1", "take:1,0,1,0,1",
    "buy-visible:5", "take:1,0,0,1,1", "buy-visible:1", "buy-visible:2",
    "take:0,1,0,1,1", "buy-visible:7", "buy-visible:1", "buy-visible:1",
    "buy-visible:1", "buy-visible:1", "buy-visible:3", "buy-visible:3",
    "buy-visible:3", "buy-visible:2", "buy-visible:0", "buy-visible:0",
    "buy-visible:0", "buy-visible:5", "buy-visible:5", "buy-visible:11",
  ];
  for (const actionId of humanActions) {
    const action = state.legalActions.find((candidate) => candidate.id === actionId);
    expect(action, `Seed 10 should allow ${actionId} on turn ${state.turn}.`).toBeDefined();
    await page.evaluate((id) => window.splendorTest!.act(id), actionId);
    state = await page.evaluate(() => window.splendorTest!.waitForHuman());
  }
  expect(state.stage).toBe("noble");
  expect(state.legalActions.length).toBeGreaterThan(1);
  const action = state.legalActions.find((candidate) => candidate.kind === "noble");
  expect(action?.nobleId).toBeDefined();
  const tile = page.getByRole("button", { name: new RegExp(`^Noble ${action!.nobleId! + 1}.*Choose this noble\\.$`) });
  await expect(tile).toBeEnabled();
  await arrowTo(page, tile);
  await page.keyboard.press("Enter");
  await page.evaluate(() => window.splendorTest!.waitForHuman());
  const events = await page.evaluate(() => window.splendorTest!.events());
  expect(events.some((event) => event.actor === state.humanSeat && event.actionId === action!.id)).toBe(true);
  report.assertions.nobleChoiceControl = true;
  report.assertions.nobleChoiceFixtureProfile = "champion E81 model and Gumbel settings; iterations=2 depth=3; seed=10";
  writeReport();
});

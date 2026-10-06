import { startGpu } from "./gpu-client";
import type {
  ChampionMetadata,
  ClientMetrics,
  EffectiveSearch,
  GameSnapshot,
  TrainingReplay,
} from "./types";

type StartRequest = {
  type: "start";
  requestId: number;
  seed: string;
  humanSeat: number;
  baseUrl: string;
  testSearchBudget?: { iterations: number; depth: number };
};
type ActRequest = { type: "act"; requestId: number; actionId: string };
type WorkerRequest = StartRequest | ActRequest;

type WorkerMessage =
  | { type: "status"; status: "loading" | "ready" | "thinking"; requestId?: number }
  | {
      type: "state";
      state: GameSnapshot;
      metrics: ClientMetrics;
      requestId?: number;
    }
  | {
      type: "champion";
      champion: ChampionMetadata;
      effectiveSearch: EffectiveSearch;
      metrics: ClientMetrics;
      requestId?: number;
    }
  | {
      type: "trainingRecord";
      replay: TrainingReplay;
      requestId?: number;
    }
  | { type: "ack"; requestId: number }
  | { type: "error"; requestId?: number; error: string };

interface WasmGame {
  snapshot(): string;
  trainingRecord(): string;
  act(actionId: string): string;
  botStep(): string;
  botStepWithDeadline(deadlineMs: number): string;
  searchWork(): string;
}

interface WasmModule {
  default(input?: string | URL | Request | Response | BufferSource): Promise<unknown>;
  WebGame: new (
    seed: string,
    humanSeat: number,
    modelBytes: Uint8Array,
    configJson: string,
  ) => WasmGame;
}

const metrics: ClientMetrics = {
  wasmInitMs: null,
  modelLoadMs: null,
  botDecisionMs: [],
  botSimulations: [],
  botTurnMs: [],
};

let game: WasmGame | null = null;
let champion: ChampionMetadata | null = null;
let busy = false;
let stopGpu: (() => void) | null = null;

function post(message: WorkerMessage): void {
  self.postMessage(message);
}

function postSnapshot(requestId?: number): GameSnapshot {
  if (!game) throw new Error("The game is not ready.");
  const state = JSON.parse(game.snapshot()) as GameSnapshot;
  post({ type: "state", state, metrics: copyMetrics(), requestId });
  return state;
}

function postTrainingRecord(requestId?: number): TrainingReplay {
  if (!game) throw new Error("The game is not ready.");
  const replay = JSON.parse(game.trainingRecord()) as TrainingReplay;
  post({ type: "trainingRecord", replay, requestId });
  return replay;
}

function makeEffectiveSearch(
  metadata: ChampionMetadata,
  testSearchBudget?: { iterations: number; depth: number },
): EffectiveSearch {
  const validTestOverrides =
    (import.meta.env.DEV || import.meta.env.VITE_ENABLE_TEST_BRIDGE === "true") &&
    testSearchBudget &&
    Number.isInteger(testSearchBudget.iterations) &&
    testSearchBudget.iterations > 0 &&
    Number.isInteger(testSearchBudget.depth) &&
    testSearchBudget.depth > 0
      ? testSearchBudget
      : undefined;
  return {
    inferenceBackend: "webgpu-f32",
    turnBudgetMs: 10000,
    agent: metadata.search.agent,
    iterations: validTestOverrides?.iterations ?? metadata.search.iterations,
    depth: validTestOverrides?.depth ?? metadata.search.depth,
    worldPool: metadata.search.world_pool,
    cpuct: metadata.search.cpuct ?? 0.4,
    fpuReduction: metadata.search.fpu_reduction ?? 0.02965,
    dynamicFpu: metadata.search.dynamic_fpu ?? false,
    chanceUniverses: metadata.search.chance_universes ?? 0,
    uniformPrior: metadata.search.uniform_prior ?? 0,
    rootOnly: metadata.search.root_only ?? false,
    rootNoise: metadata.search.root_noise ?? 0,
    gumbelMaxConsidered: metadata.search.gumbel_max_considered ?? 16,
    gumbelCvisit: metadata.search.gumbel_cvisit ?? 50,
    gumbelCscale: metadata.search.gumbel_cscale ?? 0.1,
    gumbelRootNoise: metadata.search.gumbel_root_noise ?? 0,
  };
}

function copyMetrics(): ClientMetrics {
  return {
    wasmInitMs: metrics.wasmInitMs,
    modelLoadMs: metrics.modelLoadMs,
    botDecisionMs: [...metrics.botDecisionMs],
    botSimulations: [...metrics.botSimulations],
    botTurnMs: [...metrics.botTurnMs],
  };
}

function makeConfig(
  metadata: ChampionMetadata,
  testSearchBudget?: { iterations: number; depth: number },
): string {
  const search = makeEffectiveSearch(metadata, testSearchBudget);
  return JSON.stringify({
    searchAgent: search.agent,
    iterations: search.iterations,
    depth: search.depth,
    worldPool: search.worldPool,
    gpuInference: true,
    cpuct: search.cpuct,
    fpuReduction: search.fpuReduction,
    dynamicFpu: search.dynamicFpu,
    chanceUniverses: search.chanceUniverses,
    uniformPrior: search.uniformPrior,
    rootOnly: search.rootOnly,
    rootNoise: search.rootNoise,
    gumbelMaxConsidered: search.gumbelMaxConsidered,
    gumbelCvisit: search.gumbelCvisit,
    gumbelCscale: search.gumbelCscale,
    gumbelRootNoise: search.gumbelRootNoise,
  });
}

function assetUrl(path: string, baseUrl: string): URL {
  const base = new URL(baseUrl, self.location.origin);
  if (path.startsWith("/")) {
    return new URL(`${base.pathname.replace(/\/$/, "")}${path}`, self.location.origin);
  }
  return new URL(path, base);
}

async function loadChampion(baseUrl: string): Promise<{
  metadata: ChampionMetadata;
  modelBytes: Uint8Array;
  loadMs: number;
}> {
  const loadStart = performance.now();
  const metadataResponse = await fetch(assetUrl("champion.json", baseUrl), {
    cache: "no-cache",
  });
  if (!metadataResponse.ok) {
    throw new Error(`Could not load champion metadata (${metadataResponse.status}).`);
  }
  const metadata = (await metadataResponse.json()) as ChampionMetadata;
  if (
    metadata.schema !== "splendor-web-champion-v1" ||
    !metadata.id ||
    !metadata.model?.url ||
    !/^[a-f\d]{64}$/i.test(metadata.model.sha256)
  ) {
    throw new Error("Champion metadata has an unsupported format.");
  }

  const response = await fetch(assetUrl(metadata.model.url, baseUrl), {
    cache: "force-cache",
  });
  if (!response.ok) {
    throw new Error(`Could not load champion model (${response.status}).`);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (metadata.model.bytes > 0 && bytes.byteLength !== metadata.model.bytes) {
    throw new Error("Champion model size does not match its metadata.");
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actualHash = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  if (actualHash.toLowerCase() !== metadata.model.sha256.toLowerCase()) {
    throw new Error("Champion model SHA-256 verification failed.");
  }
  return { metadata, modelBytes: bytes, loadMs: performance.now() - loadStart };
}

async function loadWasm(): Promise<{ module: WasmModule; loadMs: number }> {
  const loadStart = performance.now();
  // @ts-ignore wasm-bindgen generates this module during the web build.
  const wasm = await import("../pkg/splendor_web.js") as WasmModule;
  await wasm.default();
  return { module: wasm, loadMs: performance.now() - loadStart };
}

async function yieldToWorker(): Promise<void> {
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
}

function isTerminal(state: GameSnapshot): boolean {
  return state.stage === "finished" || state.stage === "blocked" || state.result !== null;
}

async function runBot(requestId: number, initialState: GameSnapshot): Promise<void> {
  if (initialState.activePlayer === initialState.humanSeat || isTerminal(initialState)) {
    post({ type: "status", status: "ready", requestId });
    return;
  }

  post({ type: "status", status: "thinking", requestId });
  const turnStart = performance.now();
  let state = initialState;
  while (state.activePlayer !== state.humanSeat && !isTerminal(state)) {
    // Yield between Rust decisions so the main thread can paint each published move.
    await yieldToWorker();
    const before = JSON.parse(game!.searchWork()) as { simulations: number };
    const decisionStart = performance.now();
    const serialized = game!.botStepWithDeadline(turnStart + 9900);
    metrics.botDecisionMs.push(performance.now() - decisionStart);
    const after = JSON.parse(game!.searchWork()) as { simulations: number };
    metrics.botSimulations.push(after.simulations - before.simulations);
    state = JSON.parse(serialized) as GameSnapshot;
    postTrainingRecord(requestId);
    post({ type: "state", state, metrics: copyMetrics(), requestId });
  }
  metrics.botTurnMs.push(performance.now() - turnStart);
  post({ type: "state", state, metrics: copyMetrics(), requestId });
  post({ type: "status", status: "ready", requestId });
}

async function start(request: StartRequest): Promise<void> {
  game = null;
  stopGpu?.();
  stopGpu = null;
  champion = null;
  metrics.wasmInitMs = null;
  metrics.modelLoadMs = null;
  metrics.botDecisionMs = [];
  metrics.botSimulations = [];
  metrics.botTurnMs = [];
  post({ type: "status", status: "loading", requestId: request.requestId });

  const modelStart = performance.now();
  const modelTask = loadChampion(request.baseUrl);
  const [loadedChampion, loadedWasm] = await Promise.all([modelTask, loadWasm()]);
  stopGpu = await startGpu(loadedChampion.metadata.model.sha256, new URL(request.baseUrl, self.location.origin).href, error => {
    stopGpu?.();
    stopGpu = null;
    post({ type: "error", error });
  });
  metrics.modelLoadMs = performance.now() - modelStart;
  metrics.wasmInitMs = loadedWasm.loadMs;
  champion = loadedChampion.metadata;
  const search = makeEffectiveSearch(loadedChampion.metadata, request.testSearchBudget);
  post({
    type: "champion",
    champion,
    effectiveSearch: search,
    metrics: copyMetrics(),
    requestId: request.requestId,
  });
  game = new loadedWasm.module.WebGame(
    request.seed,
    request.humanSeat,
    loadedChampion.modelBytes,
    makeConfig(loadedChampion.metadata, request.testSearchBudget),
  );
  postTrainingRecord(request.requestId);
  const state = postSnapshot(request.requestId);
  await runBot(request.requestId, state);
  post({ type: "ack", requestId: request.requestId });
}

async function act(request: ActRequest): Promise<void> {
  if (!game) throw new Error("The game is not ready. Restart the game to try again.");
  const stateBefore = JSON.parse(game.snapshot()) as GameSnapshot;
  if (stateBefore.activePlayer !== stateBefore.humanSeat || isTerminal(stateBefore)) {
    throw new Error("It is not your turn.");
  }
  const serialized = game.act(request.actionId);
  const stateAfterHuman = JSON.parse(serialized) as GameSnapshot;
  postTrainingRecord(request.requestId);
  // Publish the human result before the opponent starts. The UI can animate the action.
  post({
    type: "state",
    state: stateAfterHuman,
    metrics: copyMetrics(),
    requestId: request.requestId,
  });
  await runBot(request.requestId, stateAfterHuman);
  post({ type: "ack", requestId: request.requestId });
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  if (busy) {
    post({
      type: "error",
      requestId: request.requestId,
      error: "The previous game request is still running.",
    });
    return;
  }
  busy = true;
  const operation = request.type === "start" ? start(request) : act(request);
  void operation
    .catch((error: unknown) => {
      stopGpu?.();
      stopGpu = null;
      const message = error instanceof Error ? error.message : String(error);
      post({ type: "error", requestId: request.requestId, error: message });
    })
    .finally(() => {
      busy = false;
    });
};

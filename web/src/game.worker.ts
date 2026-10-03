import type {
  ChampionMetadata,
  ClientMetrics,
  GameSnapshot,
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
      metrics: ClientMetrics;
      requestId?: number;
    }
  | { type: "ack"; requestId: number }
  | { type: "error"; requestId?: number; error: string };

interface WasmGame {
  snapshot(): string;
  act(actionId: string): string;
  botStep(): string;
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
  botTurnMs: [],
};

let game: WasmGame | null = null;
let champion: ChampionMetadata | null = null;
let busy = false;

function post(message: WorkerMessage): void {
  self.postMessage(message);
}

function postSnapshot(requestId?: number): GameSnapshot {
  if (!game) throw new Error("The game is not ready.");
  const state = JSON.parse(game.snapshot()) as GameSnapshot;
  post({ type: "state", state, metrics: copyMetrics(), requestId });
  return state;
}

function copyMetrics(): ClientMetrics {
  return {
    wasmInitMs: metrics.wasmInitMs,
    modelLoadMs: metrics.modelLoadMs,
    botDecisionMs: [...metrics.botDecisionMs],
    botTurnMs: [...metrics.botTurnMs],
  };
}

function makeConfig(
  metadata: ChampionMetadata,
  testSearchBudget?: { iterations: number; depth: number },
): string {
  const search = metadata.search;
  const testOverrides =
    (import.meta.env.DEV || import.meta.env.VITE_ENABLE_TEST_BRIDGE === "true") &&
    testSearchBudget &&
    Number.isInteger(testSearchBudget.iterations) &&
    testSearchBudget.iterations > 0 &&
    Number.isInteger(testSearchBudget.depth) &&
    testSearchBudget.depth > 0
      ? testSearchBudget
      : undefined;
  return JSON.stringify({
    searchAgent: search.agent,
    iterations: testOverrides?.iterations ?? search.iterations,
    depth: testOverrides?.depth ?? search.depth,
    worldPool: search.world_pool,
    gumbelMaxConsidered: search.gumbel_max_considered,
    gumbelCvisit: search.gumbel_cvisit,
    gumbelCscale: search.gumbel_cscale,
    gumbelRootNoise: search.gumbel_root_noise,
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
    const decisionStart = performance.now();
    const serialized = game!.botStep();
    metrics.botDecisionMs.push(performance.now() - decisionStart);
    state = JSON.parse(serialized) as GameSnapshot;
    post({ type: "state", state, metrics: copyMetrics(), requestId });
  }
  metrics.botTurnMs.push(performance.now() - turnStart);
  post({ type: "state", state, metrics: copyMetrics(), requestId });
  post({ type: "status", status: "ready", requestId });
}

async function start(request: StartRequest): Promise<void> {
  game = null;
  champion = null;
  metrics.wasmInitMs = null;
  metrics.modelLoadMs = null;
  metrics.botDecisionMs = [];
  metrics.botTurnMs = [];
  post({ type: "status", status: "loading", requestId: request.requestId });

  const modelTask = loadChampion(request.baseUrl);
  const [loadedChampion, loadedWasm] = await Promise.all([modelTask, loadWasm()]);
  metrics.modelLoadMs = loadedChampion.loadMs;
  metrics.wasmInitMs = loadedWasm.loadMs;
  champion = loadedChampion.metadata;
  post({
    type: "champion",
    champion,
    metrics: copyMetrics(),
    requestId: request.requestId,
  });
  game = new loadedWasm.module.WebGame(
    request.seed,
    request.humanSeat,
    loadedChampion.modelBytes,
    makeConfig(loadedChampion.metadata, request.testSearchBudget),
  );
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
      const message = error instanceof Error ? error.message : String(error);
      post({ type: "error", requestId: request.requestId, error: message });
    })
    .finally(() => {
      busy = false;
    });
};

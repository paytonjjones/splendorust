import type {
  ChampionMetadata,
  ClientMetrics,
  GameEvent,
  GameClientUpdate,
  GameSnapshot,
  LegalAction,
} from "./types";

interface WorkerStatusMessage {
  type: "status";
  status: "loading" | "ready" | "thinking";
  requestId?: number;
}
interface WorkerStateMessage {
  type: "state";
  state: GameSnapshot;
  metrics: ClientMetrics;
  requestId?: number;
}
interface WorkerChampionMessage {
  type: "champion";
  champion: ChampionMetadata;
  metrics: ClientMetrics;
  requestId?: number;
}
interface WorkerAckMessage {
  type: "ack";
  requestId: number;
}
interface WorkerErrorMessage {
  type: "error";
  requestId?: number;
  error: string;
}
type WorkerMessage =
  | WorkerStatusMessage
  | WorkerStateMessage
  | WorkerChampionMessage
  | WorkerAckMessage
  | WorkerErrorMessage;

interface PendingRequest {
  kind: "start" | "act";
  resolve: () => void;
  reject: (error: Error) => void;
}

export type GameClientListener = (update: GameClientUpdate) => void;

/** Public game transport boundary. A future remote client can implement the same UI contract. */
export interface GameClientPort {
  subscribe(listener: GameClientListener): () => void;
  start(seed?: string | number, humanSeat?: number): Promise<void>;
  act(actionId: string): Promise<void>;
  reset(seed?: string | number, humanSeat?: number): Promise<void>;
  newGame(seed?: string | number, humanSeat?: number): Promise<void>;
  retry(): Promise<void>;
  dispose(): void;
  setSkipWaits(skip: boolean): void;
  readonly skipWaits: boolean;
}

function freshMetrics(): ClientMetrics {
  return {
    wasmInitMs: null,
    modelLoadMs: null,
    botDecisionMs: [],
    botTurnMs: [],
  };
}

function copyMetrics(metrics: ClientMetrics): ClientMetrics {
  return {
    wasmInitMs: metrics.wasmInitMs,
    modelLoadMs: metrics.modelLoadMs,
    botDecisionMs: [...metrics.botDecisionMs],
    botTurnMs: [...metrics.botTurnMs],
  };
}

function createSeed(): string {
  const words = new Uint32Array(2);
  crypto.getRandomValues(words);
  return `0x${words[0].toString(16).padStart(8, "0")}${words[1].toString(16).padStart(8, "0")}`;
}

function abortError(): Error {
  return new DOMException("The game was reset.", "AbortError");
}

export class GameClient implements GameClientPort {
  private worker: Worker | null = null;
  private requestCounter = 0;
  private activeRequest: number | null = null;
  private listeners = new Set<GameClientListener>();
  private pending = new Map<number, PendingRequest>();
  private update: GameClientUpdate = {
    state: null,
    status: "loading",
    champion: null,
    metrics: freshMetrics(),
  };
  private lastOptions: { seed: string; humanSeat: number } = {
    seed: "",
    humanSeat: 0,
  };
  private disposed = false;
  private fastMode = false;
  private testEventLog: GameEvent[] | null = null;

  constructor() {
    this.attachTestBridgeWhenRequested();
  }

  subscribe(listener: GameClientListener): () => void {
    this.listeners.add(listener);
    listener(this.getUpdate());
    return () => this.listeners.delete(listener);
  }

  getUpdate(): GameClientUpdate {
    return {
      ...this.update,
      metrics: copyMetrics(this.update.metrics),
    };
  }

  start(seed?: string | number, humanSeat = 0): Promise<void> {
    return this.launch({ seed: seed === undefined ? createSeed() : String(seed), humanSeat });
  }

  reset(seed?: string | number, humanSeat = this.lastOptions.humanSeat): Promise<void> {
    const resolvedSeed = seed === undefined ? createSeed() : String(seed);
    return this.launch({ seed: resolvedSeed, humanSeat });
  }

  newGame(seed?: string | number, humanSeat = this.lastOptions.humanSeat): Promise<void> {
    return this.reset(seed, humanSeat);
  }

  retry(): Promise<void> {
    return this.launch({ ...this.lastOptions });
  }

  act(actionId: string): Promise<void> {
    if (this.disposed) return Promise.reject(new Error("This game client was disposed."));
    if (!this.worker) return Promise.reject(new Error("Start a game before sending an action."));
    if (this.update.status !== "ready") {
      return Promise.reject(new Error("Wait until the game is ready before sending an action."));
    }
    if (this.activeRequest !== null) {
      return Promise.reject(new Error("The previous game action is still running."));
    }
    const requestId = ++this.requestCounter;
    return this.send({ type: "act", requestId, actionId });
  }

  /** Set by the development bridge so the UI can omit optional animation waits in test runs. */
  setSkipWaits(skip: boolean): void {
    this.fastMode = skip;
  }

  get skipWaits(): boolean {
    return this.fastMode;
  }

  dispose(): void {
    this.disposed = true;
    this.stopWorker();
    this.listeners.clear();
  }

  private launch(
    options: { seed: string; humanSeat: number },
    testSearchBudget?: { iterations: number; depth: number },
  ): Promise<void> {
    if (this.disposed) return Promise.reject(new Error("This game client was disposed."));
    if (!Number.isInteger(options.humanSeat) || options.humanSeat < 0 || options.humanSeat > 1) {
      return Promise.reject(new Error("The human seat must be 0 or 1."));
    }
    this.stopWorker();
    this.lastOptions = options;
    this.update = {
      state: null,
      status: "loading",
      champion: null,
      metrics: freshMetrics(),
    };
    this.publish();

    const worker = new Worker(new URL("./game.worker.ts", import.meta.url), {
      type: "module",
      name: "splendor-game",
    });
    this.worker = worker;
    worker.onmessage = (event: MessageEvent<WorkerMessage>) => this.handleMessage(worker, event.data);
    worker.onerror = (event) => {
      event.preventDefault();
      this.failAll(new Error(event.message || "The game worker stopped unexpectedly."));
    };
    worker.onmessageerror = () => this.failAll(new Error("The game worker sent an unreadable message."));

    const requestId = ++this.requestCounter;
    const baseUrl = import.meta.env.BASE_URL;
    return this.send(
      {
        type: "start",
        requestId,
        seed: options.seed,
        humanSeat: options.humanSeat,
        baseUrl,
        ...(testSearchBudget ? { testSearchBudget } : {}),
      },
      worker,
    );
  }

  private send(message: { type: "start" | "act"; requestId: number } & Record<string, unknown>, worker = this.worker): Promise<void> {
    if (!worker || worker !== this.worker) return Promise.reject(abortError());
    return new Promise<void>((resolve, reject) => {
      this.activeRequest = message.requestId;
      this.pending.set(message.requestId, { kind: message.type, resolve, reject });
      worker.postMessage(message);
    });
  }

  private handleMessage(worker: Worker, message: WorkerMessage): void {
    if (worker !== this.worker || this.disposed) return;
    switch (message.type) {
      case "status":
        this.update = { ...this.update, status: message.status, error: undefined };
        // The worker emits ready immediately before its request acknowledgement.
        // Its event loop has finished the operation before it can receive the next action.
        if (message.status === "ready" && message.requestId === this.activeRequest) {
          this.activeRequest = null;
        }
        this.publish();
        break;
      case "champion":
        this.update = {
          ...this.update,
          champion: message.champion,
          metrics: copyMetrics(message.metrics),
        };
        this.publish();
        break;
      case "state":
        // Every worker decision emits one immutable snapshot for display and animation.
        if (this.testEventLog) {
          const seen = new Set(this.testEventLog.map((item) => `${item.revision}:${item.actionId}`));
          for (const item of message.state.lastEvents) {
            const key = `${item.revision}:${item.actionId}`;
            if (!seen.has(key)) this.testEventLog.push(structuredClone(item));
          }
        }
        this.update = {
          ...this.update,
          state: message.state,
          metrics: copyMetrics(message.metrics),
        };
        this.publish();
        break;
      case "ack":
        this.finishRequest(message.requestId);
        break;
      case "error": {
        const error = new Error(message.error);
        const pending = message.requestId === undefined ? undefined : this.pending.get(message.requestId);
        const currentState = this.update.state;
        const recoverableActionError =
          pending?.kind === "act" &&
          currentState !== null &&
          currentState.activePlayer === currentState.humanSeat &&
          currentState.result === null &&
          currentState.stage !== "blocked";
        this.update = {
          ...this.update,
          status: recoverableActionError ? "ready" : "error",
          error: message.error,
        };
        this.publish();
        if (message.requestId === undefined) this.failAll(error);
        else this.failRequest(message.requestId, error);
        break;
      }
    }
  }

  private publish(): void {
    const update = this.getUpdate();
    for (const listener of this.listeners) listener(update);
  }

  private finishRequest(requestId: number): void {
    const request = this.pending.get(requestId);
    if (!request) return;
    this.pending.delete(requestId);
    if (this.activeRequest === requestId) this.activeRequest = null;
    request.resolve();
    this.publish();
  }

  private failRequest(requestId: number, error: Error): void {
    const request = this.pending.get(requestId);
    if (!request) return;
    this.pending.delete(requestId);
    if (this.activeRequest === requestId) this.activeRequest = null;
    request.reject(error);
    this.publish();
  }

  private failAll(error: Error): void {
    for (const [requestId, request] of this.pending) {
      this.pending.delete(requestId);
      if (this.activeRequest === requestId) this.activeRequest = null;
      request.reject(error);
    }
    if (this.worker) {
      this.update = { ...this.update, status: "error", error: error.message };
      this.publish();
    }
  }

  private stopWorker(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
    for (const [requestId, request] of this.pending) {
      this.pending.delete(requestId);
      if (this.activeRequest === requestId) this.activeRequest = null;
      request.reject(abortError());
    }
  }

  private attachTestBridgeWhenRequested(): void {
    if (
      !(import.meta.env.DEV || import.meta.env.VITE_ENABLE_TEST_BRIDGE === "true") ||
      new URLSearchParams(window.location.search).get("test") !== "1"
    ) return;
    this.testEventLog = [];

    const waitForHuman = (): Promise<GameSnapshot> =>
      new Promise((resolve, reject) => {
        let settled = false;
        let unsubscribe = () => {};
        const check = (update: GameClientUpdate) => {
          if (settled) return;
          if (update.status === "error") {
            settled = true;
            unsubscribe();
            reject(new Error(update.error ?? "The game stopped before the next human turn."));
            return;
          }
          const state = update.state;
          if (!state) return;
          const terminal = state.result !== null || state.stage === "finished" || state.stage === "blocked";
          if (terminal || (update.status === "ready" && state.activePlayer === state.humanSeat && this.pending.size === 0)) {
            settled = true;
            unsubscribe();
            resolve(structuredClone(state));
          }
        };
        unsubscribe = this.subscribe(check);
        if (settled) unsubscribe();
      });

    const bridge = {
      state: () => (this.update.state ? structuredClone(this.update.state) : null),
      actions: (): LegalAction[] => structuredClone(this.update.state?.legalActions ?? []),
      act: (id: string) => this.act(id),
      restart: (
        seed?: string | number,
        seat = this.lastOptions.humanSeat,
        testSearchBudget?: { iterations: number; depth: number },
      ) => this.launch({ seed: seed === undefined ? createSeed() : String(seed), humanSeat: seat }, testSearchBudget),
      waitForHuman,
      status: () => this.update.status,
      metrics: () => copyMetrics(this.update.metrics),
      events: (): GameEvent[] => structuredClone(this.testEventLog ?? []),
      clearEvents: () => { this.testEventLog?.splice(0); },
      skipWaits: (skip = true) => this.setSkipWaits(skip),
    };
    Object.defineProperty(window, "splendorTest", {
      configurable: true,
      value: bridge,
    });
  }
}

export function createGameClient(): GameClient {
  return new GameClient();
}

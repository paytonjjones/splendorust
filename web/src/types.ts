import type { EngineProgress } from "./engine-download";
export type GemColor = 0 | 1 | 2 | 3 | 4;
export type BankColor = GemColor | 5;
export type CardTier = 1 | 2 | 3;
export type ColorCounts = [number, number, number, number, number];
export type TokenCounts = [number, number, number, number, number, number];
export type TierCounts = [number, number, number];

export interface Card {
  id: number;
  tier: CardTier;
  bonus: GemColor;
  points: number;
  cost: ColorCounts;
}

export interface Noble {
  id: number;
  requirements: ColorCounts;
}

export interface Reservation {
  hidden: boolean;
  tier: CardTier;
  card: Card | null;
}

export interface PlayerSnapshot {
  seat: number;
  tokens: TokenCounts;
  bonuses: ColorCounts;
  score: number;
  ownedCards: Card[];
  reservedCount: number;
  reserved: Array<Reservation | null>;
}

export type ActionKind =
  | "take"
  | "reserve_visible"
  | "reserve_deck"
  | "buy_visible"
  | "buy_reserved"
  | "pay"
  | "return"
  | "noble";

export interface LegalAction {
  id: string;
  kind: ActionKind;
  take?: ColorCounts;
  slot?: number;
  tier?: CardTier;
  reservedIndex?: number;
  payment?: ColorCounts;
  returns?: TokenCounts;
  nobleId?: number;
}

export interface GameEvent {
  revision: number;
  actor: number;
  actionId: string;
  kind: ActionKind;
  take?: ColorCounts;
  payment?: ColorCounts;
  goldPayment?: number;
  returns?: TokenCounts;
  slot?: number;
  tier?: CardTier;
  cardId?: number;
  nobleId?: number;
}

export type GameStage = "main" | "payment" | "return" | "noble" | "finished" | "blocked";

export interface GameResult {
  status: "finished" | "blocked";
  winnerMask: number;
  ranks: [number, number];
  scores: [number, number];
  reason?: "no_legal_action" | "decision_limit";
}

export type CanonicalAction = [number, number, number, number, number, number, number];

/** Complete Rust replay state. This contains the private seed and state debug text. */
export interface TrainingReplay {
  schema: "splendor-web-replay-v1";
  engine: string;
  players: 2;
  seed: string;
  actions: CanonicalAction[];
  revision: number;
  turns: number;
  stateDebug: string;
  result: GameResult | null;
}

export interface EffectiveSearch {
  inferenceBackend: "webgpu-f32" | "wasm-cpu";
  turnBudgetMs: 5000 | 10000 | 30000;
  agent: string;
  iterations: number;
  depth: number;
  worldPool: number;
  cpuct: number;
  fpuReduction: number;
  dynamicFpu: boolean;
  chanceUniverses: number;
  uniformPrior: number;
  rootOnly: boolean;
  rootNoise: number;
  gumbelMaxConsidered: number;
  gumbelCvisit: number;
  gumbelCscale: number;
  gumbelRootNoise: number;
}

export type RecordedGameStatus =
  | "in_progress"
  | "finished"
  | "blocked"
  | "abandoned"
  | "error";

/** Durable client/backend envelope. Never display replay.seed or stateDebug in the UI. */
export interface RecordedGame {
  schema: "splendor-web-game-v1";
  gameId: string;
  writeToken: string;
  version: number;
  startedAt: string;
  updatedAt: string;
  humanSeat: number;
  champion: ChampionMetadata;
  effectiveSearch: EffectiveSearch;
  runtime: "production" | "test";
  status: RecordedGameStatus;
  replay: TrainingReplay;
}

export interface GameRecorderUpdate {
  status: "idle" | "saving" | "saved" | "queued" | "uploading" | "error";
  pendingUploads: number;
  storedGames: number;
  error?: string;
}

/** Public game information plus the human player's private reserved cards. */
export interface GameSnapshot {
  revision: number;
  turn: number;
  activePlayer: number;
  humanSeat: number;
  stage: GameStage;
  finalRound: boolean;
  bank: TokenCounts;
  market: Array<Card | null>;
  deckCounts: TierCounts;
  nobles: Noble[];
  players: [PlayerSnapshot, PlayerSnapshot];
  pendingCard: Card | null;
  legalActions: LegalAction[];
  result: GameResult | null;
  lastEvents: GameEvent[];
}

export interface ChampionMetadata {
  schema: "splendor-web-champion-v1";
  id: string;
  name?: string;
  model: {
    url: string;
    sha256: string;
    bytes: number;
  };
  search: {
    agent: string;
    iterations: number;
    depth: number;
    world_pool: number;
    cpuct?: number;
    fpu_reduction?: number;
    dynamic_fpu?: boolean;
    chance_universes?: number;
    uniform_prior?: number;
    root_only?: boolean;
    root_noise?: number;
    gumbel_max_considered: number | null;
    gumbel_cvisit: number | null;
    gumbel_cscale: number | null;
    gumbel_root_noise: number | null;
  };
  source?: {
    path: string;
    sha256: string;
    checkpoint?: string;
    scope?: string;
  };
}

export type ClientStatus = "loading" | "ready" | "thinking" | "error";

export interface ClientMetrics {
  wasmInitMs: number | null;
  modelLoadMs: number | null;
  botDecisionMs: number[];
  botSimulations: number[];
  botTurnMs: number[];
}

export interface GameClientUpdate {
  progress?: EngineProgress;
  effectiveSearch?: EffectiveSearch;
  state: GameSnapshot | null;
  status: ClientStatus;
  requestPending: boolean;
  error?: string;
  champion: ChampionMetadata | null;
  metrics: ClientMetrics;
  recorder: GameRecorderUpdate;
}

export interface GameStartOptions {
  seed?: string | number;
  humanSeat?: number;
}

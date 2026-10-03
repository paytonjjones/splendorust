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
    gumbel_max_considered: number;
    gumbel_cvisit: number;
    gumbel_cscale: number;
    gumbel_root_noise: number;
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
  botTurnMs: number[];
}

export interface GameClientUpdate {
  state: GameSnapshot | null;
  status: ClientStatus;
  error?: string;
  champion: ChampionMetadata | null;
  metrics: ClientMetrics;
}

export interface GameStartOptions {
  seed?: string | number;
  humanSeat?: number;
}

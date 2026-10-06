const MAX_BODY_BYTES = 512 * 1024;
const MAX_ACTIONS = 8192;
const MAX_DEBUG_BYTES = 256 * 1024;
const UINT32_MAX = 0xffff_ffff;
const UINT64_MAX = 0xffff_ffff_ffff_ffffn;

interface D1Result {
  success?: boolean;
  meta?: { changes?: number };
}

interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  run(): Promise<D1Result>;
}

interface D1Database {
  prepare(sql: string): D1Statement;
}

interface GameLogEnvironment {
  GAME_LOGS: D1Database;
}

interface PagesFunctionContext {
  request: Request;
  env: GameLogEnvironment;
}

type ResultStatus = "finished" | "blocked";
type GameStatus = "in_progress" | "finished" | "blocked" | "abandoned" | "error";
type Runtime = "production" | "test";
type CanonicalAction = [number, number, number, number, number, number, number];

interface SearchSettings {
  inferenceBackend?: "webgpu-f32";
  turnBudgetMs?: number;
  cpuct?: number;
  fpuReduction?: number;
  dynamicFpu?: boolean;
  chanceUniverses?: number;
  uniformPrior?: number;
  rootOnly?: boolean;
  rootNoise?: number;
  agent: string;
  iterations: number;
  depth: number;
  worldPool: number;
  gumbelMaxConsidered: number;
  gumbelCvisit: number;
  gumbelCscale: number;
  gumbelRootNoise: number;
}

interface Champion {
  schema: "splendor-web-champion-v1";
  id: string;
  name?: string;
  model: { url: string; sha256: string; bytes: number };
  search: {
    cpuct?: number;
    fpu_reduction?: number;
    dynamic_fpu?: boolean;
    chance_universes?: number;
    uniform_prior?: number;
    root_only?: boolean;
    root_noise?: number;
    agent: string;
    iterations: number;
    depth: number;
    world_pool: number;
    gumbel_max_considered?: number | null;
    gumbel_cvisit?: number | null;
    gumbel_cscale?: number | null;
    gumbel_root_noise?: number | null;
  };
  [key: string]: unknown;
}

interface GamePayload {
  schema: "splendor-web-game-v1";
  gameId: string;
  writeToken: string;
  version: number;
  startedAt: string;
  updatedAt: string;
  humanSeat: number;
  champion: Champion;
  effectiveSearch: SearchSettings;
  runtime: Runtime;
  status: GameStatus;
  replay: {
    schema: "splendor-web-replay-v1";
    engine: string;
    players: 2;
    seed: string;
    actions: CanonicalAction[];
    revision: number;
    turns: number;
    stateDebug: string;
    result: {
      status: ResultStatus;
      winnerMask: number;
      ranks: [number, number];
      scores: [number, number];
      reason?: "no_legal_action" | "decision_limit";
    } | null;
  };
}

interface ExistingGame {
  game_id: string;
  write_token_hash: string;
  version: number;
  revision: number;
  status: GameStatus;
  runtime: Runtime;
  human_seat: number;
  engine_version: string;
  champion_id: string;
  model_sha256: string;
  client_started_at: string;
  client_updated_at: string;
  metadata_json: string;
  journal_json: string;
  actions_json: string;
  snapshot_json: string;
  snapshot_sha256: string;
  server_created_at: string;
  server_updated_at: string;
}

class RequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function readBody(request: Request): Promise<string> {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    if (!/^\d+$/.test(contentLength)) throw new RequestError(400, "invalid_content_length");
    if (Number(contentLength) > MAX_BODY_BYTES) throw new RequestError(413, "body_too_large");
  }
  const encoding = request.headers.get("content-encoding");
  if (encoding && encoding.toLowerCase() !== "identity") {
    throw new RequestError(415, "unsupported_content_encoding");
  }
  if (!request.body) throw new RequestError(400, "empty_body");

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_BODY_BYTES) {
        await reader.cancel();
        throw new RequestError(413, "body_too_large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new RequestError(400, "invalid_utf8");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const found = Object.keys(value).sort();
  return found.length === keys.length && found.every((key, index) => key === [...keys].sort()[index]);
}

function finiteInteger(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
}

function finiteNumber(value: unknown, minimum: number, maximum: number, exclusiveMinimum = false): value is number {
  return typeof value === "number" && Number.isFinite(value) && (exclusiveMinimum ? value > minimum : value >= minimum) && value <= maximum;
}

function canonicalTimestamp(value: unknown): value is string {
  return typeof value === "string" && value.length === 24 &&
    /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

function deepStable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(deepStable);
  if (!isRecord(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, deepStable(value[key])]));
}

function stableJson(value: unknown): string {
  return JSON.stringify(deepStable(value));
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function sameAction(a: CanonicalAction, b: CanonicalAction): boolean {
  return a.every((value, index) => value === b[index]);
}

function validateAction(action: unknown): action is CanonicalAction {
  if (!Array.isArray(action) || action.length !== 7 || !action.every((value) => finiteInteger(value, 0, 255))) {
    return false;
  }
  const [tag, a, b, c, d, e, f] = action as CanonicalAction;
  switch (tag) {
    case 0: // Take, five color counts.
      return [a, b, c, d, e].every((value) => value <= 2) && a + b + c + d + e >= 1 && a + b + c + d + e <= 3 && f === 0;
    case 1: // ReserveVisible(slot)
    case 3: // BuyVisible(slot)
      return a < 12 && b === 0 && c === 0 && d === 0 && e === 0 && f === 0;
    case 2: // ReserveDeck(tier)
      return a < 3 && b === 0 && c === 0 && d === 0 && e === 0 && f === 0;
    case 4: // BuyReserved(slot)
      return a < 3 && b === 0 && c === 0 && d === 0 && e === 0 && f === 0;
    case 5: // Pay, five color counts.
      return [a, b, c, d, e].every((value) => value <= 10) && f === 0;
    case 6: // Return, five colors plus gold.
      return [a, b, c, d, e, f].every((value) => value <= 10);
    case 7: // Noble(id)
      return a < 10 && b === 0 && c === 0 && d === 0 && e === 0 && f === 0;
    default:
      return false;
  }
}

function validateChampion(value: unknown): value is Champion {
  if (!isRecord(value) || value.schema !== "splendor-web-champion-v1" ||
      typeof value.id !== "string" || !/^[a-z0-9][a-z0-9._-]{0,63}$/i.test(value.id) ||
      !isRecord(value.model) || !isRecord(value.search)) return false;
  const model = value.model;
  const search = value.search;
  if (typeof model.url !== "string" || !/^\/models\/[a-f0-9]{64}\.bin$/i.test(model.url) ||
      typeof model.sha256 !== "string" || !/^[a-f0-9]{64}$/i.test(model.sha256) ||
      !model.url.toLowerCase().endsWith(`${model.sha256.toLowerCase()}.bin`) ||
      !finiteInteger(model.bytes, 1, 20 * 1024 * 1024) ||
      typeof search.agent !== "string" || search.agent.length < 1 || search.agent.length > 64 ||
      !finiteInteger(search.iterations, 1, 1_000_000) || !finiteInteger(search.depth, 1, 100_000) ||
      !finiteInteger(search.world_pool, 1, 128)) return false;
  if (search.agent === "flywheel-best") {
    if (!validPuct(search.cpuct, search.fpu_reduction, search.dynamic_fpu, search.chance_universes, search.uniform_prior, search.root_only, search.root_noise)) return false;
  } else if (!finiteInteger(search.gumbel_max_considered, 1, 128) ||
      !finiteNumber(search.gumbel_cvisit, 0, 1_000_000) || !finiteNumber(search.gumbel_cscale, 0, 1_000_000, true) ||
      !finiteNumber(search.gumbel_root_noise, 0, 1)) return false;
  if (value.name !== undefined && (typeof value.name !== "string" || value.name.length > 100)) return false;
  return byteLength(stableJson(value)) <= 16 * 1024;
}

function validPuct(cpuct: unknown, fpu: unknown, dynamic: unknown, chance: unknown, uniform: unknown, rootOnly: unknown, noise: unknown): boolean {
  return finiteNumber(cpuct, 0, 1_000_000) && finiteNumber(fpu, 0, 1_000_000) &&
    typeof dynamic === "boolean" && finiteInteger(chance, 0, 64) && finiteNumber(uniform, 0, 1) &&
    typeof rootOnly === "boolean" && noise === 0;
}

function validateSearch(value: unknown): value is SearchSettings {
  const legacy = ["agent", "iterations", "depth", "worldPool", "gumbelMaxConsidered", "gumbelCvisit", "gumbelCscale", "gumbelRootNoise"];
  const puct = ["cpuct", "fpuReduction", "dynamicFpu", "chanceUniverses", "uniformPrior", "rootOnly", "rootNoise"];
  if (!isRecord(value)) return false;
  const hasGpu = exactKeys(value, [...legacy, ...puct, "inferenceBackend", "turnBudgetMs"]);
  if (hasGpu && (value.inferenceBackend !== "webgpu-f32" || value.turnBudgetMs !== 10000 || value.agent !== "flywheel-best")) return false;
  const hasPuct = hasGpu || exactKeys(value, [...legacy, ...puct]);
  if (!hasPuct && (!exactKeys(value, legacy) || value.agent === "flywheel-best")) return false;
  if (hasPuct && !validPuct(value.cpuct, value.fpuReduction, value.dynamicFpu, value.chanceUniverses, value.uniformPrior, value.rootOnly, value.rootNoise)) return false;
  return typeof value.agent === "string" && value.agent.length > 0 && value.agent.length <= 64 &&
    finiteInteger(value.iterations, 1, 1_000_000) && finiteInteger(value.depth, 1, 100_000) &&
    finiteInteger(value.worldPool, 1, 128) && finiteInteger(value.gumbelMaxConsidered, 1, 128) &&
    finiteNumber(value.gumbelCvisit, 0, 1_000_000) && finiteNumber(value.gumbelCscale, 0, 1_000_000, true) &&
    finiteNumber(value.gumbelRootNoise, 0, 1);
}

function searchMatchesChampion(search: SearchSettings, champion: Champion["search"], allowBudgetOverride: boolean): boolean {
  return search.agent === champion.agent &&
    (allowBudgetOverride || search.iterations === champion.iterations) &&
    (allowBudgetOverride || search.depth === champion.depth) &&
    search.worldPool === champion.world_pool &&
    search.gumbelMaxConsidered === (champion.gumbel_max_considered ?? 16) &&
    search.gumbelCvisit === (champion.gumbel_cvisit ?? 50) &&
    search.gumbelCscale === (champion.gumbel_cscale ?? 0.1) &&
    search.gumbelRootNoise === (champion.gumbel_root_noise ?? 0) &&
    (search.cpuct === undefined || (
      search.cpuct === (champion.cpuct ?? 0.4) && search.fpuReduction === (champion.fpu_reduction ?? 0.02965) &&
      search.dynamicFpu === (champion.dynamic_fpu ?? false) && search.chanceUniverses === (champion.chance_universes ?? 0) &&
      search.uniformPrior === (champion.uniform_prior ?? 0) && search.rootOnly === (champion.root_only ?? false) &&
      search.rootNoise === (champion.root_noise ?? 0)
    ));
}

function validateResult(value: unknown): value is GamePayload["replay"]["result"] {
  if (value === null) return true;
  if (!isRecord(value) || !["finished", "blocked"].includes(String(value.status)) ||
      !finiteInteger(value.winnerMask, 0, 3) || !Array.isArray(value.ranks) || value.ranks.length !== 2 ||
      !value.ranks.every((item) => finiteInteger(item, 0, 2)) || !Array.isArray(value.scores) || value.scores.length !== 2 ||
      !value.scores.every((item) => finiteInteger(item, 0, 255))) return false;
  if (value.reason !== undefined && value.reason !== "no_legal_action" && value.reason !== "decision_limit") return false;
  if (value.status === "finished" && value.reason !== undefined) return false;
  if (value.status === "finished" && value.winnerMask === 0) return false;
  if (value.status === "blocked" && (value.winnerMask !== 0 || value.ranks.some(rank => rank !== 0) || value.reason === undefined)) return false;
  return true;
}

function validatePayload(value: unknown): GamePayload {
  if (!isRecord(value) || !exactKeys(value, [
    "schema", "gameId", "writeToken", "version", "startedAt", "updatedAt", "humanSeat",
    "champion", "effectiveSearch", "runtime", "status", "replay",
  ])) throw new RequestError(422, "unsupported_schema");
  if (value.schema !== "splendor-web-game-v1") throw new RequestError(422, "unsupported_schema");
  if (typeof value.gameId !== "string" || !/^[a-f\d]{8}-[a-f\d]{4}-[1-8][a-f\d]{3}-[89ab][a-f\d]{3}-[a-f\d]{12}$/i.test(value.gameId)) {
    throw new RequestError(400, "invalid_game_id");
  }
  if (typeof value.writeToken !== "string" || !/^[a-f\d]{64}$/i.test(value.writeToken)) {
    throw new RequestError(400, "invalid_write_token");
  }
  if (!finiteInteger(value.version, 1, 0x7fff_ffff) || !finiteInteger(value.humanSeat, 0, 1)) {
    throw new RequestError(400, "invalid_version_or_seat");
  }
  if (!canonicalTimestamp(value.startedAt) || !canonicalTimestamp(value.updatedAt) || value.updatedAt < value.startedAt) {
    throw new RequestError(400, "invalid_timestamp");
  }
  if (value.runtime !== "production" && value.runtime !== "test") throw new RequestError(400, "invalid_runtime");
  const statuses: GameStatus[] = ["in_progress", "finished", "blocked", "abandoned", "error"];
  if (typeof value.status !== "string" || !statuses.includes(value.status as GameStatus)) throw new RequestError(400, "invalid_status");
  if (!validateChampion(value.champion) || !validateSearch(value.effectiveSearch)) throw new RequestError(400, "invalid_champion_or_search");
  if (!searchMatchesChampion(value.effectiveSearch, value.champion.search, value.runtime === "test")) {
    throw new RequestError(400, "search_does_not_match_champion");
  }

  const replay = value.replay;
  if (!isRecord(replay) || !exactKeys(replay, ["schema", "engine", "players", "seed", "actions", "revision", "turns", "stateDebug", "result"]) ||
      replay.schema !== "splendor-web-replay-v1" || typeof replay.engine !== "string" ||
      !/^splendorust-v[1-9]\d{0,3}$/.test(replay.engine) || replay.players !== 2 || typeof replay.seed !== "string" ||
      !/^(0|[1-9]\d{0,19})$/.test(replay.seed) || !Array.isArray(replay.actions) || replay.actions.length > MAX_ACTIONS ||
      !finiteInteger(replay.revision, 0, UINT32_MAX) || replay.revision !== replay.actions.length ||
      !finiteInteger(replay.turns, 0, UINT32_MAX) || typeof replay.stateDebug !== "string" ||
      byteLength(replay.stateDebug) === 0 || byteLength(replay.stateDebug) > MAX_DEBUG_BYTES ||
      !validateResult(replay.result)) throw new RequestError(400, "invalid_replay");
  try {
    if (BigInt(replay.seed) > UINT64_MAX) throw new Error("seed range");
  } catch {
    throw new RequestError(400, "invalid_replay_seed");
  }
  if (!replay.actions.every(validateAction)) throw new RequestError(400, "invalid_action_encoding");
  if (value.status === "finished" && (!replay.result || replay.result.status !== "finished")) {
    throw new RequestError(400, "finished_status_requires_result");
  }
  if (value.status === "blocked" && (!replay.result || replay.result.status !== "blocked")) {
    throw new RequestError(400, "blocked_status_requires_result");
  }
  if (!["finished", "blocked"].includes(value.status) && replay.result !== null) {
    throw new RequestError(400, "nonterminal_status_requires_null_result");
  }

  return value as unknown as GamePayload;
}

function identityFor(payload: GamePayload): Record<string, unknown> {
  return {
    schema: payload.schema,
    gameId: payload.gameId.toLowerCase(),
    startedAt: payload.startedAt,
    humanSeat: payload.humanSeat,
    champion: payload.champion,
    effectiveSearch: payload.effectiveSearch,
    runtime: payload.runtime,
    replay: {
      schema: payload.replay.schema,
      engine: payload.replay.engine,
      players: payload.replay.players,
      seed: payload.replay.seed,
    },
  };
}

function snapshotWithoutToken(payload: GamePayload): Record<string, unknown> {
  return {
    schema: payload.schema,
    gameId: payload.gameId.toLowerCase(),
    version: payload.version,
    startedAt: payload.startedAt,
    updatedAt: payload.updatedAt,
    humanSeat: payload.humanSeat,
    champion: payload.champion,
    effectiveSearch: payload.effectiveSearch,
    runtime: payload.runtime,
    status: payload.status,
    replay: payload.replay,
  };
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hashWriteToken(token: string): Promise<string> {
  return sha256(token.toLowerCase());
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let index = 0; index < a.length; index += 1) mismatch |= a.charCodeAt(index) ^ b.charCodeAt(index);
  return mismatch === 0;
}

function verifyPrefix(payload: GamePayload, row: ExistingGame): boolean {
  try {
    const oldActions = JSON.parse(row.actions_json) as CanonicalAction[];
    if (payload.replay.actions.length < oldActions.length) return false;
    return oldActions.every((action, index) => sameAction(action, payload.replay.actions[index]));
  } catch {
    return false;
  }
}

function makeRow(payload: GamePayload, tokenHash: string): Omit<ExistingGame, "server_created_at" | "server_updated_at"> {
  const sanitizedSnapshot = snapshotWithoutToken(payload);
  return {
    game_id: payload.gameId.toLowerCase(),
    write_token_hash: tokenHash,
    version: payload.version,
    revision: payload.replay.revision,
    status: payload.status,
    runtime: payload.runtime,
    human_seat: payload.humanSeat,
    engine_version: payload.replay.engine,
    champion_id: payload.champion.id,
    model_sha256: payload.champion.model.sha256.toLowerCase(),
    client_started_at: payload.startedAt,
    client_updated_at: payload.updatedAt,
    metadata_json: stableJson(identityFor(payload)),
    journal_json: stableJson(payload.replay),
    actions_json: stableJson(payload.replay.actions),
    snapshot_json: stableJson(sanitizedSnapshot),
    snapshot_sha256: "",
  };
}

async function parseSnapshot(payload: GamePayload, tokenHash: string) {
  const row = makeRow(payload, tokenHash);
  row.snapshot_sha256 = await sha256(row.snapshot_json);
  return row;
}

async function insertRow(db: D1Database, row: Omit<ExistingGame, "server_created_at" | "server_updated_at">, now: string): Promise<number> {
  const result = await db.prepare(`
    INSERT INTO games (
      game_id, write_token_hash, version, revision, status, runtime, human_seat,
      engine_version, champion_id, model_sha256, client_started_at, client_updated_at,
      metadata_json, journal_json, actions_json, snapshot_json, snapshot_sha256,
      server_created_at, server_updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(game_id) DO NOTHING
  `).bind(
    row.game_id, row.write_token_hash, row.version, row.revision, row.status, row.runtime,
    row.human_seat, row.engine_version, row.champion_id, row.model_sha256, row.client_started_at,
    row.client_updated_at, row.metadata_json, row.journal_json, row.actions_json,
    row.snapshot_json, row.snapshot_sha256, now, now,
  ).run();
  return result.meta?.changes ?? 0;
}

async function updateRow(db: D1Database, row: Omit<ExistingGame, "server_created_at" | "server_updated_at">,
  previous: ExistingGame, now: string): Promise<number> {
  const result = await db.prepare(`
    UPDATE games SET
      version = ?, revision = ?, status = ?, runtime = ?, human_seat = ?, engine_version = ?,
      champion_id = ?, model_sha256 = ?, client_started_at = ?, client_updated_at = ?,
      metadata_json = ?, journal_json = ?, actions_json = ?, snapshot_json = ?,
      snapshot_sha256 = ?, server_updated_at = ?
    WHERE game_id = ? AND write_token_hash = ? AND version = ? AND revision = ?
      AND actions_json = ? AND metadata_json = ? AND snapshot_sha256 = ?
  `).bind(
    row.version, row.revision, row.status, row.runtime, row.human_seat, row.engine_version,
    row.champion_id, row.model_sha256, row.client_started_at, row.client_updated_at,
    row.metadata_json, row.journal_json, row.actions_json, row.snapshot_json, row.snapshot_sha256, now,
    previous.game_id, previous.write_token_hash, previous.version, previous.revision,
    previous.actions_json, previous.metadata_json, previous.snapshot_sha256,
  ).run();
  return result.meta?.changes ?? 0;
}

async function findGame(db: D1Database, id: string): Promise<ExistingGame | null> {
  return db.prepare("SELECT * FROM games WHERE game_id = ? LIMIT 1").bind(id).first<ExistingGame>();
}

async function writePayload(db: D1Database, payload: GamePayload): Promise<Response> {
  const tokenHash = await hashWriteToken(payload.writeToken);
  const row = await parseSnapshot(payload, tokenHash);
  const id = row.game_id;

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const previous = await findGame(db, id);
    if (!previous) {
      const created = await insertRow(db, row, new Date().toISOString());
      if (created === 1) return jsonResponse(202, { ok: true, storedVersion: row.version });
      continue;
    }

    if (!constantTimeEqual(previous.write_token_hash, tokenHash)) {
      throw new RequestError(409, "conflict");
    }
    if (previous.metadata_json !== row.metadata_json) throw new RequestError(409, "conflict");
    if (payload.version < previous.version) {
      const oldActions = JSON.parse(previous.actions_json) as CanonicalAction[];
      const isStoredPrefix = payload.replay.actions.length <= oldActions.length &&
        payload.replay.actions.every((action, index) => sameAction(action, oldActions[index]));
      const sameState = payload.replay.revision !== previous.revision || row.journal_json === previous.journal_json;
      if (isStoredPrefix && sameState) return jsonResponse(200, { ok: true, unchanged: true, storedVersion: previous.version });
      throw new RequestError(409, "conflict");
    }
    if (payload.updatedAt < previous.client_updated_at ||
        payload.replay.revision < previous.revision || !verifyPrefix(payload, previous)) {
      throw new RequestError(409, "conflict");
    }
    if (payload.version === previous.version) {
      if (row.snapshot_sha256 === previous.snapshot_sha256) {
        return jsonResponse(200, { ok: true, unchanged: true, storedVersion: previous.version });
      }
      throw new RequestError(409, "conflict");
    }
    if (["finished", "blocked"].includes(previous.status) &&
        (row.status !== previous.status || row.journal_json !== previous.journal_json)) {
      throw new RequestError(409, "conflict");
    }

    const changed = await updateRow(db, row, previous, new Date().toISOString());
    if (changed === 1) return jsonResponse(202, { ok: true, storedVersion: row.version });
  }
  return jsonResponse(503, { ok: false, error: "retry_snapshot" });
}

export async function onRequest({ request, env }: PagesFunctionContext): Promise<Response> {
  if (request.method !== "POST") {
    return jsonResponse(405, { ok: false, error: "method_not_allowed" });
  }
  if (request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    return jsonResponse(415, { ok: false, error: "json_required" });
  }

  try {
    const source = await readBody(request);
    let value: unknown;
    try {
      value = JSON.parse(source);
    } catch {
      throw new RequestError(400, "invalid_json");
    }
    const payload = validatePayload(value);
    return await writePayload(env.GAME_LOGS, payload);
  } catch (error) {
    if (error instanceof RequestError) return jsonResponse(error.status, { ok: false, error: error.code });
    return jsonResponse(500, { ok: false, error: "storage_unavailable" });
  }
}

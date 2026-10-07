import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, renameSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { pathToFileURL } from 'node:url';

const temporary = mkdtempSync(join(tmpdir(), 'splendor-logs-test-'));
try {
  execFileSync('./node_modules/.bin/tsc', ['--ignoreConfig', 'functions/api/games.ts', '--target', 'ES2023', '--module', 'ESNext', '--moduleResolution', 'Bundler', '--skipLibCheck', '--outDir', temporary], { stdio: 'inherit' });
  renameSync(join(temporary, 'games.js'), join(temporary, 'games.mjs'));
  const { onRequest } = await import(pathToFileURL(join(temporary, 'games.mjs')).href);
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(readFileSync('migrations/0001_game_logs.sql', 'utf8'));
  const database = {
    prepare(sql) {
      let values = [];
      return {
        bind(...parameters) { values = parameters; return this; },
        async first() { return sqlite.prepare(sql).get(...values) ?? null; },
        async run() { const result = sqlite.prepare(sql).run(...values); return { success: true, meta: { changes: Number(result.changes) } }; },
      };
    },
  };
  const champion = JSON.parse(readFileSync('public/champion.json', 'utf8'));
  const search = champion.search;
  const base = {
    schema: 'splendor-web-game-v1', gameId: crypto.randomUUID(), writeToken: 'a'.repeat(64), version: 1,
    startedAt: '2026-10-03T00:00:00.000Z', updatedAt: '2026-10-03T00:00:00.000Z', humanSeat: 0,
    champion, effectiveSearch: { agent: search.agent, iterations: search.iterations, depth: search.depth, worldPool: search.world_pool, gumbelMaxConsidered: search.gumbel_max_considered ?? 16, gumbelCvisit: search.gumbel_cvisit ?? 50, gumbelCscale: search.gumbel_cscale ?? 0.1, gumbelRootNoise: search.gumbel_root_noise ?? 0, cpuct: search.cpuct ?? 0.4, fpuReduction: search.fpu_reduction ?? 0.02965, dynamicFpu: search.dynamic_fpu ?? false, chanceUniverses: search.chance_universes ?? 0, uniformPrior: search.uniform_prior ?? 0, rootOnly: search.root_only ?? false, rootNoise: search.root_noise ?? 0 },
    runtime: 'test', status: 'in_progress',
    replay: { schema: 'splendor-web-replay-v1', engine: 'splendorust-v2', players: 2, seed: '18446744073709551615', actions: [], revision: 0, turns: 0, stateDebug: 'structural test fixture', result: null },
  };
  let checks = 0;
  const request = async (payload, expected, method = 'POST') => {
    const response = await onRequest({ request: new Request('https://splendorust.pages.dev/api/games', { method, ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: typeof payload === 'string' ? payload : JSON.stringify(payload) } : {}) }), env: { GAME_LOGS: database } });
    assert.equal(response.status, expected, await response.clone().text());
    assert.equal(response.headers.get('cache-control'), 'no-store');
    checks++;
    return response.json();
  };
  for (const [key, value] of [["dynamicFpu", false], ["chanceUniverses", 0], ["cpuct", 0.5]]) {
    await request({ ...base, runtime: "production", gameId: crypto.randomUUID(), effectiveSearch: { ...base.effectiveSearch, [key]: value } }, 400);
  }
  const oldChampion = { schema: 'splendor-web-champion-v1', id: 'e81', model: { url: '/models/' + 'e'.repeat(64) + '.bin', sha256: 'e'.repeat(64), bytes: 569624 }, search: { agent: 'flywheel-gumbel', iterations: 128, depth: 16, world_pool: 3, gumbel_max_considered: 16, gumbel_cvisit: 50, gumbel_cscale: 0.1, gumbel_root_noise: 0 } };
  const oldSearch = oldChampion.search;
  await request({ ...base, gameId: crypto.randomUUID(), champion: oldChampion, effectiveSearch: { agent: oldSearch.agent, iterations: oldSearch.iterations, depth: oldSearch.depth, worldPool: oldSearch.world_pool, gumbelMaxConsidered: oldSearch.gumbel_max_considered, gumbelCvisit: oldSearch.gumbel_cvisit, gumbelCscale: oldSearch.gumbel_cscale, gumbelRootNoise: oldSearch.gumbel_root_noise } }, 202);
  const gpuSearch = { ...base.effectiveSearch, inferenceBackend: "webgpu-f32", turnBudgetMs: 10000 };
  for (const turnBudgetMs of [5000, 10000, 30000]) {
    await request({ ...base, gameId: crypto.randomUUID(), effectiveSearch: { ...gpuSearch, turnBudgetMs } }, 202);
    await request({ ...base, gameId: crypto.randomUUID(), champion: oldChampion, effectiveSearch: { ...gpuSearch, agent: oldSearch.agent, iterations: 128, depth: 16, worldPool: 3, cpuct: 0.4, fpuReduction: 0.02965, dynamicFpu: false, chanceUniverses: 0, uniformPrior: 0, rootOnly: false, rootNoise: 0, inferenceBackend: "wasm-cpu", turnBudgetMs } }, 202);
  }
  await request({ ...base, gameId: crypto.randomUUID(), effectiveSearch: { ...gpuSearch, inferenceBatchSize: 8 } }, 202);
  await request({ ...base, gameId: crypto.randomUUID(), effectiveSearch: { ...gpuSearch, inferenceBatchSize: 7 } }, 400);
  for (const invalid of [{ turnBudgetMs: 10001 }, { inferenceBackend: "cpu" }, { turnBudgetMs: undefined }]) {
    await request({ ...base, gameId: crypto.randomUUID(), effectiveSearch: { ...gpuSearch, ...invalid } }, 400);
  }
  await request(base, 202);
  await request(base, 200);
  const row = sqlite.prepare('SELECT * FROM games WHERE game_id = ?').get(base.gameId);
  assert.notEqual(row.write_token_hash, base.writeToken);
  assert.equal(row.write_token_hash.length, 64);
  assert.equal(JSON.stringify(row).includes('"writeToken"'), false);
  assert.equal(row.snapshot_json.includes(base.writeToken), false);
  await request({ ...base, writeToken: 'b'.repeat(64) }, 409);
  await request({ ...base, version: 2, replay: { ...base.replay, seed: '1' } }, 409);
  const next = { ...base, version: 2, updatedAt: '2026-10-03T00:00:01.000Z', replay: { ...base.replay, actions: [[0, 1, 1, 1, 0, 0, 0]], revision: 1, turns: 1, stateDebug: 'second fixture state' } };
  await request(next, 202);
  await request(base, 200); // A delayed valid prefix must not overwrite the newer row.
  assert.equal(sqlite.prepare('SELECT revision FROM games WHERE game_id = ?').get(base.gameId).revision, 1);
  await request({ ...next, version: 3, replay: { ...next.replay, actions: [[0, 0, 1, 1, 1, 0, 0]] } }, 409);
  await request({ ...next, version: 3, replay: { ...next.replay, actions: [], revision: 0 } }, 409);
  await request({ ...next, updatedAt: '2026-10-03T00:00:02.000Z' }, 409);
  await request({ ...next, version: 3, status: 'abandoned' }, 202);
  await request({}, 405, 'GET');
  await request('{}', 422);
  await request('{', 400);
  await request({ ...base, gameId: crypto.randomUUID(), replay: { ...base.replay, seed: '18446744073709551616' } }, 400);
  await request({ ...base, gameId: crypto.randomUUID(), replay: { ...base.replay, actions: [[1, 0, 1, 0, 0, 0, 0]], revision: 1 } }, 400);
  await request({ ...base, gameId: crypto.randomUUID(), uploadEnabled: true }, 422);
  await request(' '.repeat(512 * 1024 + 1), 413);
  const terminal = { ...next, gameId: crypto.randomUUID(), status: 'finished', replay: { ...next.replay, result: { status: 'finished', winnerMask: 1, ranks: [1, 2], scores: [15, 8] } } };
  await request(terminal, 202);
  await request({ ...terminal, version: 3 }, 202);
  await request({ ...terminal, version: 4, replay: { ...terminal.replay, actions: [...terminal.replay.actions, [0, 1, 1, 1, 0, 0, 0]], revision: 2 } }, 409);
  await request({ ...terminal, gameId: crypto.randomUUID(), status: 'in_progress' }, 400);
  await request({ ...base, gameId: crypto.randomUUID(), status: 'blocked', replay: { ...base.replay, result: { status: 'blocked', winnerMask: 1, ranks: [0, 0], scores: [1, 2], reason: 'no_legal_action' } } }, 400);
  const racing = { ...base, gameId: crypto.randomUUID() };
  await request(racing, 202);
  const versions = [2, 3, 4].map(version => ({ ...racing, version, replay: { ...racing.replay, actions: Array.from({ length: version - 1 }, () => [0, 1, 1, 1, 0, 0, 0]), revision: version - 1, turns: version - 1, stateDebug: `race ${version}` } }));
  const replies = await Promise.all(versions.map(payload => onRequest({ request: new Request('https://splendorust.pages.dev/api/games', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), env: { GAME_LOGS: database } })));
  assert(replies.every(reply => [200, 202, 409].includes(reply.status)));
  assert.equal(sqlite.prepare('SELECT version FROM games WHERE game_id = ?').get(racing.gameId).version, 4);
  checks++;
  sqlite.close();
  console.log(`${checks} game-log backend checks passed, including concurrent writes and private exports.`);
} finally {
  rmSync(temporary, { recursive: true, force: true });
}

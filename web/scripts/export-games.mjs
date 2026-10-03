import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { closeSync, existsSync, mkdirSync, openSync, rmSync, writeFileSync, writeSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
let output, includeTest = false, local = false;
for (let index = 0; index < args.length; index++) {
  if (args[index] === '--out') output = args[++index];
  else if (args[index] === '--include-test') includeTest = true;
  else if (args[index] === '--local') local = true;
  else throw new Error(`Unknown argument: ${args[index]}`);
}
if (!output) throw new Error('Usage: npm run logs:export -- --out /path/games.jsonl [--include-test] [--local]');
output = resolve(output);
const manifestPath = `${output}.manifest.json`;
if (existsSync(output) || existsSync(manifestPath)) throw new Error('The export path already exists. Choose a new path.');
mkdirSync(dirname(output), { recursive: true });
const environment = { ...process.env, WRANGLER_SEND_METRICS: 'false' };
// The Ring Pages token has no D1 scope. Use the existing account-authenticated OAuth session.
delete environment.CLOUDFLARE_API_TOKEN;
const quote = value => `'${String(value).replaceAll("'", "''")}'`;
const cutoff = new Date().toISOString();
const manifest = {
  schema: 'splendor-web-export-v1', exportedAt: cutoff, database: 'splendorust-game-logs',
  source: local ? 'local' : 'remote', includeTest, records: 0,
  statusCounts: { finished: 0, blocked: 0, in_progress: 0, abandoned: 0, error: 0 },
  runtimeCounts: { production: 0, test: 0 }, engines: {}, models: {}, sha256: '',
  consistency: 'Latest row snapshots read in pages. Concurrent updates can occur during export.',
};
const digest = createHash('sha256');
let file, outputCreated = false, cursorTime = '', cursorId = '';
try {
  file = openSync(output, 'wx', 0o600);
  outputCreated = true;
  while (true) {
    const query = `SELECT game_id, server_created_at, snapshot_json, snapshot_sha256 FROM games
      WHERE server_created_at <= ${quote(cutoff)} ${includeTest ? '' : "AND runtime = 'production'"}
      AND (server_created_at > ${quote(cursorTime)} OR (server_created_at = ${quote(cursorTime)} AND game_id > ${quote(cursorId)}))
      ORDER BY server_created_at, game_id LIMIT 100`;
    const result = JSON.parse(execFileSync(resolve(webDirectory, 'node_modules/.bin/wrangler'), ['d1', 'execute', 'splendorust-game-logs', local ? '--local' : '--remote', '--command', query, '--json'], { cwd: webDirectory, env: environment, encoding: 'utf8', maxBuffer: 128 * 1024 * 1024 }));
    const batches = Array.isArray(result) ? result : [result];
    if (batches.some(batch => batch.success === false)) throw new Error('D1 rejected the export query.');
    const rows = batches.flatMap(batch => batch.results ?? []);
    for (const row of rows) {
      if (createHash('sha256').update(row.snapshot_json).digest('hex') !== row.snapshot_sha256) throw new Error(`Snapshot hash mismatch for ${row.game_id}`);
      const record = JSON.parse(row.snapshot_json);
      if (record.schema !== 'splendor-web-game-v1' || 'writeToken' in record || !(record.status in manifest.statusCounts) || !(record.runtime in manifest.runtimeCounts)) throw new Error(`Invalid stored envelope for ${row.game_id}`);
      const line = `${row.snapshot_json}\n`;
      writeSync(file, line); digest.update(line);
      manifest.records++;
      manifest.statusCounts[record.status]++;
      manifest.runtimeCounts[record.runtime]++;
      manifest.engines[record.replay.engine] = (manifest.engines[record.replay.engine] ?? 0) + 1;
      const model = record.champion.model.sha256;
      manifest.models[model] = (manifest.models[model] ?? 0) + 1;
      cursorTime = row.server_created_at; cursorId = row.game_id;
    }
    if (rows.length < 100) break;
  }
  closeSync(file); file = undefined;
  manifest.sha256 = digest.digest('hex');
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
  console.log(`Exported ${manifest.records} games to ${output}`);
  console.log(`Manifest: ${manifestPath}`);
  console.log(`SHA-256: ${manifest.sha256}`);
} catch (error) {
  if (file !== undefined) closeSync(file);
  if (outputCreated) rmSync(output, { force: true });
  throw error;
}

CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY NOT NULL CHECK (length(game_id) = 36),
  write_token_hash TEXT NOT NULL CHECK (length(write_token_hash) = 64),
  version INTEGER NOT NULL CHECK (version >= 1),
  revision INTEGER NOT NULL CHECK (revision >= 0),
  status TEXT NOT NULL CHECK (status IN ('in_progress', 'finished', 'blocked', 'abandoned', 'error')),
  runtime TEXT NOT NULL CHECK (runtime IN ('production', 'test')),
  human_seat INTEGER NOT NULL CHECK (human_seat IN (0, 1)),
  engine_version TEXT NOT NULL,
  champion_id TEXT NOT NULL,
  model_sha256 TEXT NOT NULL CHECK (length(model_sha256) = 64),
  client_started_at TEXT NOT NULL,
  client_updated_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
  journal_json TEXT NOT NULL CHECK (json_valid(journal_json)),
  actions_json TEXT NOT NULL CHECK (json_valid(actions_json)),
  snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
  snapshot_sha256 TEXT NOT NULL CHECK (length(snapshot_sha256) = 64),
  server_created_at TEXT NOT NULL,
  server_updated_at TEXT NOT NULL
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS games_training_export_idx
  ON games (runtime, status, server_updated_at, game_id);

CREATE INDEX IF NOT EXISTS games_export_order_idx
  ON games (runtime, server_created_at, game_id);

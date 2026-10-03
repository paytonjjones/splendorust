use serde::{Deserialize, Serialize};
use serde_json::Value;
use splendor_arena::{History, replay};
use splendor_core::{ActionSet, ENGINE_VERSION, GameOutcome, GameState};
use std::{io::BufRead, process::ExitCode};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
struct WebResult {
    status: String,
    winner_mask: u8,
    ranks: [u8; 2],
    scores: [u8; 2],
    reason: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct WebReplay {
    schema: String,
    engine: String,
    players: u8,
    seed: String,
    actions: Vec<[u8; 7]>,
    revision: u32,
    turns: u32,
    state_debug: String,
    result: Option<WebResult>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct WebGameEnvelope {
    schema: String,
    status: String,
    champion: Value,
    human_seat: u8,
    replay: WebReplay,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct VerifiedRecord {
    status: String,
    decisions: usize,
    turns: u32,
}

fn is_blocked(state: &GameState) -> bool {
    if state.is_terminal() {
        return false;
    }
    if state.turns() == u32::MAX {
        return true;
    }
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    legal.is_empty()
}

fn expected_result(state: &GameState) -> Option<WebResult> {
    if let Some(GameOutcome {
        winners,
        ranks,
        scores,
    }) = state.outcome()
    {
        return Some(WebResult {
            status: "finished".into(),
            winner_mask: winners,
            ranks: [ranks[0], ranks[1]],
            scores: [scores[0], scores[1]],
            reason: None,
        });
    }
    if is_blocked(state) {
        let observation = state.observe(0);
        return Some(WebResult {
            status: "blocked".into(),
            winner_mask: 0,
            ranks: [0, 0],
            scores: [observation.players[0].score, observation.players[1].score],
            reason: Some(if state.turns() == u32::MAX {
                "decision_limit".into()
            } else {
                "no_legal_action".into()
            }),
        });
    }
    None
}

fn validate_replay(record: WebReplay) -> Result<VerifiedRecord, String> {
    if record.schema != "splendor-web-replay-v1" {
        return Err("unsupported replay schema".into());
    }
    if record.engine != ENGINE_VERSION {
        return Err("engine version does not match this validator".into());
    }
    if record.players != 2 {
        return Err("web records must contain exactly two players".into());
    }
    let seed = record
        .seed
        .parse::<u64>()
        .map_err(|_| "seed must be an unsigned decimal u64".to_owned())?;
    if seed.to_string() != record.seed {
        return Err("seed must use canonical decimal formatting".into());
    }
    let decisions = record.actions.len();
    let revision = u32::try_from(decisions)
        .map_err(|_| "action count exceeds the revision field".to_owned())?;
    if record.revision != revision {
        return Err("revision does not match the action count".into());
    }
    if record.state_debug.is_empty() {
        return Err("stateDebug must contain the exact diagnostic state".into());
    }
    let history = History {
        format: 1,
        engine: record.engine,
        players: record.players,
        seed,
        actions: record.actions,
        state_debug: record.state_debug,
    };
    let state = replay(&history).map_err(|e| format!("replay rejected: {e}"))?;
    if state.turns() != record.turns {
        return Err("turn count does not match the replayed state".into());
    }
    let expected = expected_result(&state);
    if expected != record.result {
        return Err("result does not match replayed outcome or blocked status".into());
    }
    Ok(VerifiedRecord {
        status: expected.map_or_else(|| "unfinished".into(), |result| result.status),
        decisions,
        turns: state.turns(),
    })
}

fn validate_line(line: &str) -> Result<VerifiedRecord, String> {
    let value: Value = serde_json::from_str(line).map_err(|e| format!("invalid JSON: {e}"))?;
    match value.get("schema").and_then(Value::as_str) {
        Some("splendor-web-replay-v1") => {
            let record: WebReplay =
                serde_json::from_value(value).map_err(|e| format!("invalid replay: {e}"))?;
            validate_replay(record)
        }
        Some("splendor-web-game-v1") => {
            let envelope: WebGameEnvelope =
                serde_json::from_value(value).map_err(|e| format!("invalid game envelope: {e}"))?;
            if envelope.schema != "splendor-web-game-v1" {
                return Err("unsupported game envelope schema".into());
            }
            if envelope.human_seat > 1 {
                return Err("humanSeat must be 0 or 1".into());
            }
            let _champion_metadata = envelope.champion;
            let verified = validate_replay(envelope.replay)?;
            let status_matches = match verified.status.as_str() {
                "finished" | "blocked" => envelope.status == verified.status,
                "unfinished" => matches!(
                    envelope.status.as_str(),
                    "in_progress" | "abandoned" | "error"
                ),
                _ => false,
            };
            if !status_matches {
                return Err("envelope status does not match the replayed game status".into());
            }
            Ok(VerifiedRecord {
                status: envelope.status,
                ..verified
            })
        }
        _ => Err("unsupported JSONL record schema".into()),
    }
}

#[derive(Default)]
struct Counts {
    verified: usize,
    rejected: usize,
    finished: usize,
    blocked: usize,
    nonterminal: std::collections::BTreeMap<String, usize>,
}

fn main() -> ExitCode {
    let mut args = std::env::args_os().skip(1);
    let Some(path) = args.next() else {
        eprintln!(
            "usage: cargo run --release -p splendor-arena --example validate_web_records -- <records.jsonl>"
        );
        return ExitCode::from(2);
    };
    if args.next().is_some() {
        eprintln!("expected one JSONL input path");
        return ExitCode::from(2);
    }
    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) => {
            eprintln!("could not open JSONL input: {error}");
            return ExitCode::from(2);
        }
    };
    let mut counts = Counts::default();
    for (line_index, line) in std::io::BufReader::new(file).lines().enumerate() {
        let line_number = line_index + 1;
        let line = match line {
            Ok(line) if line.trim().is_empty() => continue,
            Ok(line) => line,
            Err(error) => {
                counts.rejected += 1;
                eprintln!("line {line_number}: rejected: could not read line: {error}");
                continue;
            }
        };
        match validate_line(&line) {
            Ok(record) => {
                counts.verified += 1;
                match record.status.as_str() {
                    "finished" => counts.finished += 1,
                    "blocked" => counts.blocked += 1,
                    status => *counts.nonterminal.entry(status.to_owned()).or_default() += 1,
                }
                println!(
                    "line {line_number}: verified status={} decisions={} turns={}",
                    record.status, record.decisions, record.turns
                );
            }
            Err(error) => {
                counts.rejected += 1;
                eprintln!("line {line_number}: rejected: {error}");
            }
        }
    }
    println!(
        "verified={} rejected={} finished={} blocked={} nonterminal={:?}",
        counts.verified, counts.rejected, counts.finished, counts.blocked, counts.nonterminal
    );
    println!("champion identity metadata is retained as opaque input and is not authenticated");
    if counts.rejected == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_arena::{decode, encode};

    fn completed_replay() -> WebReplay {
        let fixture = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/seed42-v2.json");
        let history: History = serde_json::from_slice(&std::fs::read(fixture).unwrap()).unwrap();
        let state = replay(&history).unwrap();
        let result = expected_result(&state).unwrap();
        WebReplay {
            schema: "splendor-web-replay-v1".into(),
            engine: history.engine,
            players: history.players,
            seed: history.seed.to_string(),
            revision: history.actions.len() as u32,
            turns: state.turns(),
            state_debug: history.state_debug,
            actions: history.actions,
            result: Some(result),
        }
    }

    #[test]
    fn completed_envelope_replays_all_actions_and_checks_real_result() {
        let record = completed_replay();
        assert_eq!(record.result.as_ref().unwrap().status, "finished");
        assert!(record.actions.iter().any(|action| action[0] == 5));
        let envelope = serde_json::json!({
            "schema": "splendor-web-game-v1",
            "status": "finished",
            "champion": {"id": "e81"},
            "humanSeat": 0,
            "replay": record,
        });
        let verified = validate_line(&envelope.to_string()).unwrap();
        assert_eq!(verified.status, "finished");
        assert_eq!(verified.decisions, 101);
        assert_eq!(verified.turns, 60);
    }

    #[test]
    fn partial_replay_stays_unfinished_and_bad_decision_count_is_rejected() {
        let mut record = completed_replay();
        record.actions.truncate(7);
        record.revision = record.actions.len() as u32;
        record.result = None;
        let partial_history = History {
            format: 1,
            engine: record.engine.clone(),
            players: record.players,
            seed: record.seed.parse().unwrap(),
            actions: record.actions.clone(),
            state_debug: String::new(),
        };
        let state = replay(&partial_history).unwrap();
        record.turns = state.turns();
        record.state_debug = format!("{:?}", state);
        let record_value = serde_json::to_value(&record).unwrap();
        for status in ["in_progress", "abandoned", "error"] {
            let envelope = serde_json::json!({
                "schema": "splendor-web-game-v1",
                "status": status,
                "champion": {"id": "test"},
                "humanSeat": 0,
                "replay": record_value.clone(),
            });
            let verified = validate_line(&envelope.to_string()).unwrap();
            assert_eq!(verified.status, status);
            assert_eq!(verified.decisions, 7);
        }
        assert!(
            validate_line(
                &serde_json::json!({
                    "schema": "splendor-web-game-v1",
                    "status": "finished",
                    "champion": {"id": "test"},
                    "humanSeat": 0,
                    "replay": record_value.clone(),
                })
                .to_string()
            )
            .is_err()
        );
        record.revision += 1;
        assert!(validate_line(&serde_json::to_string(&record).unwrap()).is_err());
    }

    #[test]
    fn replay_actions_use_the_canonical_seven_byte_arena_encoding() {
        let record = completed_replay();
        for &encoded in &record.actions {
            assert_eq!(encode(decode(encoded).unwrap()), encoded);
        }
    }
}

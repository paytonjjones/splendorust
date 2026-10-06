//! JSON-lines adapter boundary for agents that receive only a canonical Observation.
//! The referee keeps GameState private and accepts only an action in its legal list.
use clap::Parser;
use serde_json::{Value, json};
use splendor_core::{Action, ActionSet, GameState, NONE, Observation, Phase, Source};
use std::io::{self, BufRead, Write};

#[derive(Parser)]
struct Args {
    #[arg(long)]
    seed: u64,
    /// Stop after this many canonical actions. A stopped game has no outcome.
    #[arg(long, default_value_t = 20000)]
    max_decisions: usize,
    /// Apply the first legal action at every step. This is a protocol smoke only.
    #[arg(long, default_value_t = false)]
    scripted_first_legal: bool,
}

fn phase_name(phase: Phase) -> &'static str {
    match phase {
        Phase::Main => "main",
        Phase::Payment(_) => "payment",
        Phase::Return => "return",
        Phase::Noble => "noble",
        Phase::Terminal => "terminal",
    }
}

fn bit_ids(bits: u128, limit: usize) -> Vec<usize> {
    (0..limit).filter(|&i| bits & (1u128 << i) != 0).collect()
}

fn action_json(action: Action) -> Value {
    match action {
        Action::Take(v) => json!({"kind":"take", "values":v}),
        Action::ReserveVisible(i) => json!({"kind":"reserve_visible", "values":[i]}),
        Action::ReserveDeck(i) => json!({"kind":"reserve_deck", "values":[i]}),
        Action::BuyVisible(i) => json!({"kind":"buy_visible", "values":[i]}),
        Action::BuyReserved(i) => json!({"kind":"buy_reserved", "values":[i]}),
        Action::Pay(v) => json!({"kind":"pay", "values":v}),
        Action::Return(v) => json!({"kind":"return", "values":v}),
        Action::Noble(i) => json!({"kind":"noble", "values":[i]}),
    }
}

fn observation_json(o: &Observation, decision_id: usize, legal: &ActionSet) -> Value {
    let players: Vec<Value> = (0..o.count as usize)
        .map(|seat| {
            let p = &o.players[seat];
            let reserved: Vec<Value> = p.reserved[..o.reserved_counts[seat] as usize]
                .iter()
                .map(|r| {
                    json!({
                        "card_id": if r.card == NONE { None } else { Some(r.card) },
                        "tier": r.tier,
                        "public": r.public,
                    })
                })
                .collect();
            json!({
                "tokens": p.tokens,
                "bonuses": p.bonuses,
                "score": p.score,
                "owned_card_ids": bit_ids(p.owned, 90),
                "nobles": bit_ids(p.nobles as u128, 10),
                "reserved": reserved,
            })
        })
        .collect();
    let market: Vec<Option<u8>> = o.market.iter().map(|&c| (c != NONE).then_some(c)).collect();
    let pending_card_id = match o.phase {
        Phase::Payment(Source::Market(slot)) => o.market[slot as usize],
        Phase::Payment(Source::Reserved(slot)) => {
            o.players[o.viewer as usize].reserved[slot as usize].card
        }
        _ => NONE,
    };
    json!({
        "schema": "ahin-referee-observation-v1",
        "turn_id": o.turns,
        "decision_id": decision_id,
        "terminal": false,
        "pending_card_id": (pending_card_id != NONE).then_some(pending_card_id),
        "viewer": o.viewer,
        "current": o.current,
        "count": o.count,
        "phase": phase_name(o.phase),
        "final_round": o.final_round,
        "turns": o.turns,
        "bank": o.bank,
        "market": market,
        "remaining": o.remaining,
        "nobles": bit_ids(o.nobles as u128, 10),
        "players": players,
        "legal_actions": legal.iter().copied().map(action_json).collect::<Vec<_>>(),
    })
}

fn choose_action(legal: &ActionSet, response: &Value) -> Result<Action, String> {
    let requested = response
        .get("action")
        .ok_or_else(|| "response is missing action".to_string())?;
    legal
        .iter()
        .copied()
        .find(|&a| action_json(a) == *requested)
        .ok_or_else(|| "response action is not in the canonical legal-action list".to_string())
}

fn emit(value: &Value) -> Result<(), String> {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    serde_json::to_writer(&mut out, value).map_err(|e| e.to_string())?;
    out.write_all(b"\n").map_err(|e| e.to_string())?;
    out.flush().map_err(|e| e.to_string())
}

fn run(args: Args) -> Result<(), String> {
    let stdin = io::stdin();
    let mut input = stdin.lock();
    let mut line = String::new();
    let mut state = GameState::new(2, args.seed).map_err(|e| e.to_string())?;
    let mut legal = ActionSet::new();
    for decision in 0..args.max_decisions {
        if let Some(outcome) = state.outcome() {
            emit(&json!({
                "schema":"ahin-referee-result-v1",
                "status":"complete",
                "decisions":decision,
                "scores":outcome.scores[..2],
                "winners":bit_ids(outcome.winners as u128, 2),
            }))?;
            return Ok(());
        }
        state.legal_actions(&mut legal);
        if legal.is_empty() {
            emit(
                &json!({"schema":"ahin-referee-result-v1", "status":"no_legal_action", "decisions":decision}),
            )?;
            return Ok(());
        }
        let seat = state.current_player();
        emit(&observation_json(&state.observe(seat), decision, &legal))?;
        let action = if args.scripted_first_legal {
            legal[0]
        } else {
            line.clear();
            if input.read_line(&mut line).map_err(|e| e.to_string())? == 0 {
                return Err("agent input ended before a game result".into());
            }
            let response: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            choose_action(&legal, &response)?
        };
        state.apply_action(action).map_err(|e| e.to_string())?;
    }
    let status = if state.is_terminal() {
        "complete"
    } else {
        "decision_limit"
    };
    let outcome = state.outcome();
    emit(&json!({
        "schema":"ahin-referee-result-v1",
        "status":status,
        "decisions":args.max_decisions,
        "scores":outcome.map(|o| o.scores[..2].to_vec()),
        "winners":outcome.map(|o| bit_ids(o.winners as u128, 2)),
    }))
}

fn main() {
    if let Err(error) = run(Args::parse()) {
        eprintln!("ahin referee error: {error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::Action;

    #[test]
    fn blind_opponent_reservation_is_redacted_but_tier_remains() {
        let mut state = GameState::new(2, 0xaced_1234).unwrap();
        state.apply_action(Action::ReserveDeck(1)).unwrap();
        let observation = state.observe(1);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let wire = observation_json(&observation, 1, &legal);
        let slot = &wire["players"][0]["reserved"][0];
        assert!(slot["card_id"].is_null());
        assert_eq!(slot["tier"], 1);
        assert_eq!(slot["public"], false);
        assert!(wire.get("deck").is_none());
        assert!(wire.get("seed").is_none());
    }

    #[test]
    fn own_blind_reservation_is_visible_to_its_owner() {
        let mut state = GameState::new(2, 0xaced_1234).unwrap();
        state.apply_action(Action::ReserveDeck(2)).unwrap();
        let observation = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let wire = observation_json(&observation, 1, &legal);
        assert!(wire["players"][0]["reserved"][0]["card_id"].is_u64());
        assert_eq!(wire["players"][0]["reserved"][0]["tier"], 2);
    }

    #[test]
    fn rejects_action_outside_current_legal_list() {
        let mut legal = ActionSet::new();
        legal.push(Action::Take([1, 1, 1, 0, 0]));
        let response = json!({"action":{"kind":"take", "values":[0,0,0,1,1]}});
        assert!(choose_action(&legal, &response).is_err());
    }
}

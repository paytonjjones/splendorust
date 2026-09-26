//! Export privileged complete-turn cases for the offline independent-engine audit.
//! These records are test data only and must never be supplied to an agent.
use serde_json::{Value, json};
use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::encode;
use splendor_core::{ActionSet, ENGINE_VERSION, GameState, NONE, Phase};
use std::io::{self, BufWriter, Write};

fn snapshot(state: &GameState) -> Value {
    let o = state.observe(state.current_player());
    let players: Vec<_> = (0..state.player_count())
        .map(|i| {
            let p = state.observe(i).players[i];
            json!({"tokens": p.tokens, "bonuses": p.bonuses, "score": p.score,
                "owned": (0..90).filter(|c| p.owned & (1u128 << c) != 0).collect::<Vec<_>>(),
                "nobles": (0..10).filter(|n| p.nobles & (1 << n) != 0).collect::<Vec<_>>(),
                "reserved": p.reserved.iter().filter(|r| r.card != NONE)
                    .map(|r| json!({"card": r.card, "public": r.public})).collect::<Vec<_>>()})
        })
        .collect();
    json!({"players": players, "current": o.current, "bank": o.bank, "market": o.market,
        "remaining": o.remaining, "nobles": (0..10).filter(|n| o.nobles & (1 << n) != 0).collect::<Vec<_>>(),
        "terminal": state.is_terminal(), "final_round": o.final_round, "turns": o.turns})
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let games: u64 = args.next().unwrap_or_else(|| "20".into()).parse()?;
    let seed: u64 = args.next().unwrap_or_else(|| "92000000".into()).parse()?;
    let mut out = BufWriter::new(io::stdout().lock());
    writeln!(
        out,
        "{}",
        json!({"format": 1, "engine": ENGINE_VERSION,
        "source_id": env!("SPLENDOR_SOURCE_ID"), "games_per_player_count": games, "seed": seed})
    )?;
    for count in 2..=4 {
        for game in 0..games {
            let setup = seed.wrapping_add(count as u64 * 1_000_000 + game);
            let mut state = GameState::new(count, setup)?;
            let policy = if game % 2 == 0 { "strong" } else { "random" };
            let mut agent = make_agent(policy, setup, &SearchConfig::default())?;
            for _ in 0..1000 {
                if state.is_terminal() {
                    break;
                }
                let before = snapshot(&state);
                let mut actions = Vec::new();
                loop {
                    let mut legal = ActionSet::new();
                    state.legal_actions(&mut legal);
                    if legal.is_empty() {
                        break;
                    }
                    let action =
                        agent.select_action(&state.observe(state.current_player()), &legal);
                    state.apply_action(action)?;
                    state.check_invariants()?;
                    actions.push(encode(action));
                    if matches!(state.phase(), Phase::Main | Phase::Terminal) {
                        break;
                    }
                }
                if actions.is_empty() {
                    break;
                }
                writeln!(
                    out,
                    "{}",
                    json!({"seed": setup, "policy": policy,
                    "before": before, "actions": actions, "after": snapshot(&state)})
                )?;
            }
        }
    }
    Ok(())
}

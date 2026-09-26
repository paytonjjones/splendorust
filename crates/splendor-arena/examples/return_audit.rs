//! Offline, privileged audit of a return choice and the next opponent turn.
use serde_json::{Value, json};
use splendor_arena::{History, encode, replay};
use splendor_core::{Action, ActionSet, GameState, Phase};

fn replies(state: &GameState, actor: usize, path: &mut Vec<[u8; 7]>, out: &mut Vec<Value>) {
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    if state.is_terminal() || state.current_player() == actor || legal.is_empty() {
        let purchases = legal
            .iter()
            .filter(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
            .count();
        out.push(json!({"reply": path, "current": state.current_player(),
            "terminal": state.is_terminal(), "winners": state.outcome().map(|o| o.winners),
            "legal": legal.iter().copied().map(encode).collect::<Vec<_>>(),
            "purchases": purchases, "blocked": legal.is_empty() && !state.is_terminal()}));
        return;
    }
    assert!(path.len() < 4, "unexpected compound turn length");
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        next.check_invariants().unwrap();
        path.push(encode(action));
        replies(&next, actor, path, out);
        path.pop();
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let file = args
        .next()
        .ok_or("usage: return_audit HISTORY PREFIX_LENGTH")?;
    let length: usize = args.next().ok_or("missing prefix length")?.parse()?;
    let mut history: History = serde_json::from_slice(&std::fs::read(file)?)?;
    // Verify the archived full history before examining an earlier decision.
    replay(&history)?;
    if length >= history.actions.len() {
        return Err("prefix must precede a recorded action".into());
    }
    let recorded = history.actions[length];
    history.actions.truncate(length);
    history.state_debug.clear();
    let state = replay(&history)?;
    if state.player_count() != 2 || state.phase() != Phase::Return {
        return Err("requires a two-player return phase".into());
    }
    let actor = state.current_player();
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    let mut branches = Vec::new();
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action)?;
        next.check_invariants()?;
        let mut outcomes = Vec::new();
        replies(&next, actor, &mut Vec::new(), &mut outcomes);
        branches.push(json!({"return": encode(action), "outcomes": outcomes}));
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "engine": history.engine, "source_id": env!("SPLENDOR_SOURCE_ID"),
            "seed": history.seed, "prefix_length": length, "actor": actor,
            "recorded_return": recorded, "branches": branches
        }))?
    );
    Ok(())
}

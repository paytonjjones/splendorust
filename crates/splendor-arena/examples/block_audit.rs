//! Exhaustive bounded, privileged block diagnosis. This is not an agent.
use serde_json::json;
use splendor_arena::{History, encode, replay};
use splendor_core::{ActionSet, GameState};

#[derive(Default)]
struct Counts {
    nodes: u64,
    actor_blocked: u64,
    opponent_blocked: u64,
    terminal: u64,
    horizon: u64,
}

// True means the opponent can force this actor to have no legal action within
// the remaining decision horizon, against every actor choice. A cutoff is not
// a block or a victory. The fixed real deck is privileged diagnostic input.
fn forced_block(
    state: &GameState,
    actor: usize,
    remaining: u8,
    counts: &mut Counts,
) -> Result<bool, String> {
    counts.nodes += 1;
    if counts.nodes > 10_000_000 {
        return Err("node limit reached; no exhaustive result".into());
    }
    if state.is_terminal() {
        counts.terminal += 1;
        return Ok(false);
    }
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    if legal.is_empty() {
        if state.current_player() == actor {
            counts.actor_blocked += 1;
            return Ok(true);
        }
        counts.opponent_blocked += 1;
        return Ok(false);
    }
    if remaining == 0 {
        counts.horizon += 1;
        return Ok(false);
    }
    let actor_choice = state.current_player() == actor;
    let mut forced = actor_choice;
    // Do not short-circuit: retain complete, unweighted leaf counts.
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).map_err(|e| format!("{e:?}"))?;
        next.check_invariants().map_err(|e| format!("{e:?}"))?;
        let child = forced_block(&next, actor, remaining - 1, counts)?;
        if actor_choice {
            forced &= child;
        } else {
            forced |= child;
        }
    }
    Ok(forced)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let file = args
        .next()
        .ok_or("usage: block_audit HISTORY PREFIX DECISIONS")?;
    let length: usize = args.next().ok_or("missing prefix")?.parse()?;
    let decisions: u8 = args.next().ok_or("missing decision horizon")?.parse()?;
    if decisions == 0 || decisions > 12 {
        return Err("decision horizon must be 1..=12".into());
    }
    let mut history: History = serde_json::from_slice(&std::fs::read(file)?)?;
    replay(&history)?;
    if length >= history.actions.len() {
        return Err("prefix must precede a recorded action".into());
    }
    let recorded = history.actions[length];
    history.actions.truncate(length);
    history.state_debug.clear();
    let state = replay(&history)?;
    if state.player_count() != 2 {
        return Err("requires two players".into());
    }
    let actor = state.current_player();
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    let mut branches = Vec::new();
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action)?;
        next.check_invariants()?;
        let mut counts = Counts::default();
        let forced = forced_block(&next, actor, decisions - 1, &mut counts)?;
        branches.push(
            json!({"action": encode(action), "opponent_can_force_actor_block": forced,
            "nodes": counts.nodes, "actor_blocked_leaves": counts.actor_blocked,
            "opponent_blocked_leaves": counts.opponent_blocked, "terminal_leaves": counts.terminal,
            "horizon_leaves": counts.horizon}),
        );
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "engine": history.engine, "source_id": env!("SPLENDOR_SOURCE_ID"),
            "seed": history.seed, "prefix_length": length, "actor": actor,
            "decision_horizon": decisions, "recorded_action": recorded, "branches": branches
        }))?
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn history() -> History {
        serde_json::from_str(include_str!("../tests/fixtures/blocked-e11-v1.json")).unwrap()
    }

    #[test]
    fn cutoff_is_not_a_block_but_a_real_block_is_detected_at_zero_depth() {
        let mut h = history();
        let blocked = replay(&h).unwrap();
        let actor = blocked.current_player();
        let mut counts = Counts::default();
        assert!(forced_block(&blocked, actor, 0, &mut counts).unwrap());
        assert_eq!(counts.actor_blocked, 1);
        assert_eq!(counts.horizon, 0);
        assert_eq!(blocked.outcome(), None);
        h.actions.truncate(32);
        h.state_debug.clear();
        let playable = replay(&h).unwrap();
        let mut counts = Counts::default();
        assert!(!forced_block(&playable, actor, 0, &mut counts).unwrap());
        assert_eq!(counts.actor_blocked, 0);
        assert_eq!(counts.horizon, 1);
    }

    #[test]
    fn earlier_takes_have_different_forced_block_risks() {
        let mut h = history();
        h.actions.truncate(32);
        h.state_debug.clear();
        let state = replay(&h).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let expected = [(false, 2), (false, 0), (true, 12), (false, 4), (true, 10)];
        assert_eq!(legal.len(), expected.len());
        for (action, (forced, blocked)) in legal.into_iter().zip(expected) {
            let mut next = state.clone();
            next.apply_action(action).unwrap();
            let mut counts = Counts::default();
            assert_eq!(
                forced_block(&next, state.current_player(), 6, &mut counts).unwrap(),
                forced
            );
            assert_eq!(counts.actor_blocked, blocked);
            assert_eq!(counts.terminal, 0);
        }
    }
}

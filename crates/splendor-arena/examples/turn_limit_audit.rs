//! Diagnose the v1 turn-counter boundary using a proven legal token cycle.
//! This is a privileged audit, not an agent or a claim about game outcomes.
use serde_json::json;
use splendor_arena::{History, replay};
use splendor_core::{Action, ENGINE_VERSION, Rng};
use std::panic::{AssertUnwindSafe, catch_unwind};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let history: History =
        serde_json::from_str(include_str!("../tests/fixtures/return-cycle-v1.json"))?;
    let mut state = replay(&history)?;
    let viewer = state.current_player();
    let cycle = [
        Action::Return([0, 0, 1, 0, 1, 0]),
        Action::Take([0, 0, 1, 0, 1]),
        Action::Return([0, 0, 1, 0, 1, 0]),
        Action::Take([0, 0, 1, 0, 1]),
    ];
    let original = state.observe(viewer);
    for action in cycle {
        state.apply_action(action)?;
        state.check_invariants()?;
    }
    let mut repeated = state.observe(viewer);
    assert_eq!(repeated.turns, original.turns + 2);
    repeated.turns = original.turns;
    assert_eq!(repeated, original);
    // This cycle draws no cards, changes no ownership, and restores both hands.
    // Advancing by an even number of turns is therefore a reachable repetition.
    let mut boundary = original.clone();
    boundary.turns = u32::MAX - (u32::MAX - original.turns) % 2;
    let skipped_cycles = (boundary.turns - original.turns) / 2;
    let mut state = boundary.determinize(&mut Rng::new(42))?;
    assert_eq!(state.observe(viewer), boundary);
    let start_turns = state.turns();
    let mut transitions = Vec::new();
    for action in cycle {
        let before = state.observe(viewer);
        let result = catch_unwind(AssertUnwindSafe(|| state.apply_action(action)));
        let status = match result {
            Ok(Ok(())) => "accepted".to_string(),
            Ok(Err(error)) => format!("error: {error}"),
            Err(_) => "panic".to_string(),
        };
        let invariant_error = state.check_invariants().err().map(|e| e.to_string());
        transitions.push(json!({
            "action": format!("{action:?}"), "status": status,
            "before_turns": before.turns, "after_turns": state.turns(),
            "state_changed": before != state.observe(viewer),
            "counter_wrapped": state.turns() < before.turns,
            "invariant_error": invariant_error,
            "has_outcome": state.outcome().is_some(),
        }));
        if status != "accepted" || state.turns() < before.turns {
            break;
        }
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "engine": ENGINE_VERSION, "source_id": env!("SPLENDOR_SOURCE_ID"),
            "debug_assertions": cfg!(debug_assertions), "original_turns": original.turns,
            "skipped_cycles": skipped_cycles, "start_turns": start_turns,
            "transitions": transitions,
        }))?
    );
    Ok(())
}

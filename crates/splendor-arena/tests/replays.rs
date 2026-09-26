use splendor_arena::{History, replay};
use splendor_core::{ActionSet, Phase};
#[test]
fn golden_completed_game_and_all_prefix_snapshots() {
    let history: History = serde_json::from_str(include_str!("fixtures/seed42.json")).unwrap();
    let state = replay(&history).unwrap();
    assert!(state.is_terminal());
    let mut saw_payment = false;
    for len in 0..history.actions.len() {
        let mut prefix = history.clone();
        prefix.actions.truncate(len);
        prefix.state_debug.clear();
        let state = replay(&prefix).unwrap();
        if matches!(state.phase(), Phase::Payment(_)) {
            saw_payment = true;
        }
        prefix.state_debug = format!("{state:?}");
        let decoded: History =
            serde_json::from_str(&serde_json::to_string(&prefix).unwrap()).unwrap();
        assert_eq!(replay(&decoded).unwrap(), state);
    }
    assert!(saw_payment);
    let mut corrupt = history;
    corrupt.state_debug.push('!');
    assert!(replay(&corrupt).is_err());
}
#[test]
fn published_rule_gap_is_a_reproducible_blocked_state_not_a_victory() {
    for fixture in [
        include_str!("fixtures/blocked.json"),
        include_str!("fixtures/blocked-search-v1.json"),
    ] {
        let history: History = serde_json::from_str(fixture).unwrap();
        let state = replay(&history).unwrap();
        state.check_invariants().unwrap();
        assert!(!state.is_terminal());
        assert_eq!(state.outcome(), None);
        let mut actions = ActionSet::new();
        state.legal_actions(&mut actions);
        assert!(actions.is_empty());
        let o = state.observe(state.current_player());
        assert_eq!(o.bank[..5], [0; 5]);
        assert_eq!(o.reserved_counts[o.current as usize], 3);
    }
}

#[test]
fn recorded_search_cycle_preserves_state_except_turn_count() {
    use splendor_core::Action;
    let history: History =
        serde_json::from_str(include_str!("fixtures/return-cycle-v1.json")).unwrap();
    let mut state = replay(&history).unwrap();
    let viewer = state.current_player();
    let before = state.observe(viewer);
    for action in [
        Action::Return([0, 0, 1, 0, 1, 0]),
        Action::Take([0, 0, 1, 0, 1]),
        Action::Return([0, 0, 1, 0, 1, 0]),
        Action::Take([0, 0, 1, 0, 1]),
    ] {
        state.apply_action(action).unwrap();
        state.check_invariants().unwrap();
    }
    let mut after = state.observe(viewer);
    assert_eq!(after.turns, before.turns + 2);
    after.turns = before.turns;
    assert_eq!(after, before);
    assert_eq!(state.outcome(), None);
}

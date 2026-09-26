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

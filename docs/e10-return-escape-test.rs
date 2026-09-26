#[test]
fn return_escape_changes_only_a_repeated_return_choice() {
    use splendor_agents::{SearchConfig, make_agent};
    let history: History =
        serde_json::from_str(include_str!("fixtures/return-cycle-v1.json")).unwrap();
    let state = replay(&history).unwrap();
    assert_eq!(state.phase(), Phase::Return);
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    assert!(legal.len() > 1);
    let original = state.observe(state.current_player());
    let mut baseline = make_agent("search", 42, &SearchConfig::default()).unwrap();
    let mut candidate = make_agent("search-return-escape", 42, &SearchConfig::default()).unwrap();
    let preferred = baseline.select_action(&original, &legal);
    assert_eq!(candidate.select_action(&original, &legal), preferred);
    let mut repeated = original.clone();
    repeated.turns += state.player_count() as u32;
    let alternative = candidate.select_action(&repeated, &legal);
    assert!(legal.contains(&alternative));
    assert_ne!(alternative, preferred);
    let mut applied = state.clone();
    applied.apply_action(alternative).unwrap();
    applied.check_invariants().unwrap();
    // A changed public market is not the same observation.
    let mut changed = original;
    changed.market.swap(0, 1);
    assert_eq!(
        candidate.select_action(&changed, &legal),
        baseline.select_action(&changed, &legal)
    );
}

use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{History, replay};
use splendor_core::{Action, ActionSet, Rng};
#[test]
fn learned_cycle_uses_only_observed_history_and_selects_a_legal_purchase() {
    let mut history: History =
        serde_json::from_str(include_str!("../../../research/e23/smoke-cap/18-1.json")).unwrap();
    history.actions.truncate(86);
    history.state_debug.clear();
    let state = replay(&history).unwrap();
    let o = state.observe(state.current_player());
    let alternative = o.determinize(&mut Rng::new(728)).unwrap();
    let other = alternative.observe(state.current_player());
    assert_eq!(o, other);
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    for iterations in [0, 1, 128] {
        let config = SearchConfig {
            iterations,
            ..Default::default()
        };
        let mut a = make_agent("learned-cycle", 183, &config).unwrap();
        let mut b = make_agent("learned-cycle", 183, &config).unwrap();
        assert_eq!(a.select_action(&o, &legal), b.select_action(&other, &legal));
        let action = a.select_action(&o, &legal);
        assert_eq!(action, b.select_action(&other, &legal));
        assert!(legal.contains(&action));
        assert!(matches!(
            action,
            Action::BuyVisible(_) | Action::BuyReserved(_)
        ));
    }
}

//! Verify named teacher budgets and Observation-only decisions before arena runs.
use splendor_agents::{SearchConfig, make_agent};
use splendor_core::{Action, ActionSet, GameState, Rng};
fn main() {
    let mut state = GameState::new(2, 1210000007).unwrap();
    state.apply_action(Action::ReserveDeck(0)).unwrap();
    let o = state.observe(state.current_player());
    let alternate = o.determinize(&mut Rng::new(19)).unwrap();
    let hidden = alternate.observe(state.current_player());
    assert_eq!(o, hidden);
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    let config = SearchConfig {
        iterations: 17,
        depth: 16,
        ..Default::default()
    };
    for (name, budget) in [
        ("flywheel-best128", 128),
        ("flywheel-best256", 256),
        ("flywheel-best800", 800),
    ] {
        let mut a = make_agent(name, 123, &config).unwrap();
        let mut b = make_agent(name, 123, &config).unwrap();
        let chosen = a.select_action(&o, &legal);
        assert_eq!(chosen, b.select_action(&hidden, &legal));
        assert!(legal.contains(&chosen));
        assert_eq!(a.work_counts().0, budget);
        assert_eq!(a.work_counts(), b.work_counts());
        println!(
            "{}",
            serde_json::json!({"agent":name,"requested_shared_iterations":17,"actual_simulations":a.work_counts().0,"inference_calls":a.work_counts().1,"hidden_world_choice_equal":true,"source":env!("SPLENDOR_SOURCE_ID")})
        );
    }
}

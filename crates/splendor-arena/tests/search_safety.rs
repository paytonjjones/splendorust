use splendor_agents::{Agent, SearchAgent, SearchConfig};
use splendor_arena::{History, RunConfig, play_game, replay};
use splendor_core::{Action, ActionSet, GameState, Phase, Rng};

fn blocked_history() -> History {
    serde_json::from_str(include_str!("fixtures/blocked-three-player-v2.json")).unwrap()
}

// Branch through complete opponent turns, including payment/return/noble choices.
// A blocked opponent is still an incomplete game; do not award an outcome.
fn check_replies(state: &GameState, root: usize, endpoints: &mut usize) {
    state.check_invariants().unwrap();
    if state.is_terminal() {
        return;
    }
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    if state.current_player() == root && state.phase() == Phase::Main {
        assert!(!legal.is_empty());
        *endpoints += 1;
        return;
    }
    if legal.is_empty() {
        assert_eq!(state.outcome(), None);
        return;
    }
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        check_replies(&next, root, endpoints);
    }
}

#[test]
fn e18_safe_take_keeps_a_legal_reply_against_every_opponent_action() {
    let original = blocked_history();
    let end = replay(&original).unwrap();
    let mut legal = ActionSet::new();
    end.legal_actions(&mut legal);
    assert!(legal.is_empty());
    assert_eq!(end.outcome(), None);
    let mut prefix = original;
    prefix.actions.truncate(83);
    prefix.state_debug.clear();
    let state = replay(&prefix).unwrap();
    let root = state.current_player();
    let o = state.observe(root);
    state.legal_actions(&mut legal);
    let alternative = o.determinize(&mut Rng::new(125000000)).unwrap();
    assert_eq!(o, alternative.observe(root));
    for iterations in [0, 1, 128] {
        for seed in 0..16 {
            let config = SearchConfig {
                iterations,
                ..Default::default()
            };
            let action = SearchAgent::new(seed, config.clone()).select_action(&o, &legal);
            assert_eq!(
                action,
                SearchAgent::new(seed, config).select_action(&alternative.observe(root), &legal)
            );
            assert!(legal.contains(&action));
            // Blue makes a card affordable; the recorded unsafe take omits it.
            assert!(matches!(action, Action::Take(t) if t[1] == 1));
        }
    }
    let mut endpoints = 0;
    // All six blue-containing takes make a current market card affordable.
    // Check all of them, including alternatives the seeded agents did not pick.
    for &action in &legal {
        if !matches!(action, Action::Take(t) if t[1] == 1) {
            continue;
        }
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        check_replies(&next, root, &mut endpoints);
    }
    assert!(endpoints > 0);
}

#[test]
fn e18_previously_blocked_game_completes_with_search_safety() {
    let config = RunConfig {
        names: vec!["search".into(), "strong".into(), "strong".into()],
        games: 3,
        seed: 132000000,
        threads: 1,
        max_decisions: 20000,
        check: true,
        search: SearchConfig {
            iterations: 128,
            ..Default::default()
        },
    };
    let (record, history) = play_game(&config, 818, 2, 11622764811484448866, true).unwrap();
    assert_eq!(record.status, "complete");
    let end = replay(&history.unwrap()).unwrap();
    assert!(end.is_terminal());
    assert_eq!(end.outcome().unwrap().winners, record.winners);
}

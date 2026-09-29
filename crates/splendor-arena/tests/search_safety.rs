use splendor_agents::{Agent, SearchAgent, SearchConfig, StrongHeuristicAgent};
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

#[test]
fn e19_two_player_blocks_are_preserved_and_changed_policies_complete() {
    let config = RunConfig {
        names: vec!["search".into(), "strong".into()],
        games: 2,
        seed: 1136000000,
        threads: 1,
        max_decisions: 20000,
        check: true,
        search: SearchConfig {
            iterations: 128,
            ..Default::default()
        },
    };
    for (text, block, rotation) in [
        (include_str!("fixtures/blocked-two-786-v2.json"), 786, 1),
        (include_str!("fixtures/blocked-two-6349-v2.json"), 6349, 0),
        (include_str!("fixtures/blocked-two-2310-v2.json"), 2310, 1),
        (include_str!("fixtures/blocked-two-4285-v2.json"), 4285, 1),
    ] {
        let original: History = serde_json::from_str(text).unwrap();
        let end = replay(&original).unwrap();
        let mut legal = ActionSet::new();
        end.legal_actions(&mut legal);
        assert!(legal.is_empty());
        assert_eq!(end.outcome(), None);
        assert_eq!((end.current_player() + rotation) % 2, 1);
        let (record, history) = play_game(&config, block, rotation, original.seed, true).unwrap();
        assert_eq!(record.status, "complete", "{block}");
        assert!(replay(&history.unwrap()).unwrap().is_terminal());
    }
}

#[test]
fn e19_strong_safe_takes_survive_every_opponent_reply_and_hide_decks() {
    for (text, prefix) in [
        (include_str!("fixtures/blocked-two-786-v2.json"), 47),
        (include_str!("fixtures/blocked-two-6349-v2.json"), 31),
    ] {
        let mut h: History = serde_json::from_str(text).unwrap();
        let old = splendor_arena::decode(h.actions[prefix]).unwrap();
        h.actions.truncate(prefix);
        h.state_debug.clear();
        let state = replay(&h).unwrap();
        let root = state.current_player();
        let o = state.observe(root);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let action = StrongHeuristicAgent.select_action(&o, &legal);
        assert_ne!(action, old);
        assert!(legal.contains(&action));
        for seed in 0..16 {
            let other = o.determinize(&mut Rng::new(seed)).unwrap();
            assert_eq!(o, other.observe(root));
            assert_eq!(
                StrongHeuristicAgent.select_action(&other.observe(root), &legal),
                action
            );
        }
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        let mut endpoints = 0;
        check_replies(&next, root, &mut endpoints);
        assert!(endpoints > 0);
    }
}

#[test]
fn e20_search_does_not_empty_bank_into_a_known_opponent_block() {
    for (text, prefix) in [
        (include_str!("fixtures/blocked-two-2310-v2.json"), 52),
        (include_str!("fixtures/blocked-two-4285-v2.json"), 70),
    ] {
        let mut h: History = serde_json::from_str(text).unwrap();
        h.actions.truncate(prefix);
        h.state_debug.clear();
        let state = replay(&h).unwrap();
        let root = state.current_player();
        let o = state.observe(root);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        for iterations in [0, 1, 128] {
            for seed in 0..16 {
                let config = SearchConfig {
                    iterations,
                    ..Default::default()
                };
                let action = SearchAgent::new(seed, config.clone()).select_action(&o, &legal);
                assert!(matches!(
                    action,
                    Action::BuyVisible(_) | Action::BuyReserved(_)
                ));
                let other = o.determinize(&mut Rng::new(seed)).unwrap();
                assert_eq!(
                    SearchAgent::new(seed, config).select_action(&other.observe(root), &legal),
                    action
                );
                let mut next = state.clone();
                next.apply_action(action).unwrap();
                // Purchases have mandatory payment; check all complete continuations.
                check_no_block_until_opponent(&next, root);
            }
        }
    }
}
fn check_no_block_until_opponent(state: &GameState, root: usize) {
    state.check_invariants().unwrap();
    if state.is_terminal() {
        return;
    }
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    assert!(!legal.is_empty());
    if state.current_player() != root {
        return;
    }
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        check_no_block_until_opponent(&next, root);
    }
}

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

#[test]
fn a_legal_cycle_can_ignore_affordable_purchases() {
    use splendor_core::Action;
    let history: History =
        serde_json::from_str(include_str!("fixtures/main-cycle-v1.json")).unwrap();
    let mut state = replay(&history).unwrap();
    assert_eq!(state.phase(), Phase::Main);
    let before = state.observe(state.current_player());
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    assert!(
        legal
            .iter()
            .any(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
    );
    for action in [
        Action::Take([0, 1, 0, 0, 0]),
        Action::Return([0, 1, 0, 0, 0, 0]),
        Action::Take([0, 1, 0, 0, 0]),
        Action::Return([0, 1, 0, 0, 0, 0]),
    ] {
        state.apply_action(action).unwrap();
        state.check_invariants().unwrap();
    }
    let mut after = state.observe(state.current_player());
    assert_eq!(after.turns, before.turns + 2);
    after.turns = before.turns;
    assert_eq!(before, after);
    assert_eq!(state.outcome(), None);
}

#[test]
fn threshold_observations_allow_pending_nobles_but_require_completed_round_flag() {
    use splendor_core::{Rng, RuleError};
    let history: History =
        serde_json::from_str(include_str!("fixtures/threshold-noble-v1.json")).unwrap();
    let state = replay(&history).unwrap();
    let current = state.current_player();
    let observed = state.observe(current);
    assert_eq!(observed.phase, Phase::Noble);
    assert!(observed.players[current].score >= 15);
    assert!(!observed.final_round);
    for viewer in 0..state.player_count() {
        let observation = state.observe(viewer);
        let sampled = observation.determinize(&mut Rng::new(42)).unwrap();
        assert_eq!(sampled.observe(viewer), observation);
    }
    // The same threshold score cannot be an ordinary start-of-turn position
    // without the final-round flag.
    let mut bad = observed;
    bad.phase = Phase::Main;
    assert_eq!(
        bad.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("missing final round"))
    );
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    assert!(legal.len() >= 2);
    for choice in legal {
        let mut finished = state.clone();
        finished.apply_action(choice).unwrap();
        finished.check_invariants().unwrap();
        let mut observation = finished.observe(finished.current_player());
        assert_eq!(observation.phase, Phase::Main);
        assert!(observation.final_round);
        observation.determinize(&mut Rng::new(42)).unwrap();
        observation.final_round = false;
        assert_eq!(
            observation.determinize(&mut Rng::new(42)),
            Err(RuleError::Invariant("missing final round"))
        );
    }
}

#[test]
fn finished_round_observation_cannot_restart_main_phase() {
    use splendor_core::{Rng, RuleError};
    let history: History = serde_json::from_str(include_str!("fixtures/seed42.json")).unwrap();
    let state = replay(&history).unwrap();
    assert!(state.is_terminal());
    let mut observation = state.observe(0);
    observation.determinize(&mut Rng::new(42)).unwrap();
    observation.phase = Phase::Main;
    assert_eq!(
        observation.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("terminal phase"))
    );
}

#[test]
fn legal_histories_cross_high_tier_depletion_and_leave_empty_market_slots() {
    use splendor_arena::decode;
    use splendor_core::{Action, GameState, NONE};
    for (tier, raw) in [
        (1, include_str!("fixtures/depleted-tier-2-v1.json")),
        (2, include_str!("fixtures/depleted-tier-3-v1.json")),
    ] {
        let history: History = serde_json::from_str(raw).unwrap();
        let expected = replay(&history).unwrap();
        let mut state = GameState::new(history.players, history.seed).unwrap();
        let mut removal = None;
        let mut final_draws = 0;
        let mut empty_buys = 0;
        let mut empty_reserves = 0;
        for encoded in &history.actions {
            let action = decode(*encoded).unwrap();
            if let Action::BuyVisible(slot) | Action::ReserveVisible(slot) = action
                && usize::from(slot) / 4 == tier
            {
                let remaining = state.observe(state.current_player()).remaining[tier];
                removal = Some((usize::from(slot), remaining));
                if remaining == 0 {
                    if matches!(action, Action::BuyVisible(_)) {
                        empty_buys += 1;
                    } else {
                        empty_reserves += 1;
                    }
                }
            }
            state.apply_action(action).unwrap();
            state.check_invariants().unwrap();
            if state.phase() == Phase::Main
                && let Some((slot, remaining)) = removal.take()
            {
                let o = state.observe(state.current_player());
                if remaining == 0 {
                    assert_eq!(o.market[slot], NONE);
                }
                if remaining == 1 {
                    final_draws += 1;
                    assert_eq!(o.remaining[tier], 0);
                    assert_ne!(o.market[slot], NONE);
                }
            }
        }
        assert_eq!(state, expected);
        assert_eq!(final_draws, 1);
        assert!(empty_buys > 0 && empty_reserves > 0);
        assert_eq!(state.outcome(), None);
    }
}

#[test]
fn final_round_requires_a_threshold_player_who_already_finished_this_round() {
    use splendor_core::{Rng, RuleError};
    let history: History =
        serde_json::from_str(include_str!("fixtures/threshold-noble-v1.json")).unwrap();
    let state = replay(&history).unwrap();
    let original = state.observe(state.current_player());
    assert_eq!(original.current, 2);
    assert_eq!(original.phase, Phase::Noble);
    assert!(original.players[2].score >= 15);
    assert!(original.players[..2].iter().all(|p| p.score < 15));
    let mut premature = original.clone();
    premature.final_round = true;
    // The current player's turn is still waiting for a noble choice.
    assert_eq!(
        premature.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("final round trigger order"))
    );
    // A threshold player in a later seat cannot have triggered this round.
    let mut later = premature;
    later.current = 1;
    later.turns -= 1;
    later.phase = Phase::Main;
    assert_eq!(
        later.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("final round trigger order"))
    );
    // The valid pending state and all completed noble choices stay valid.
    original.determinize(&mut Rng::new(42)).unwrap();
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).unwrap();
        let o = next.observe(next.current_player());
        assert!(o.final_round);
        o.determinize(&mut Rng::new(42)).unwrap();
    }
}

#[test]
fn final_round_cannot_put_threshold_scores_in_unplayed_seats() {
    use splendor_core::{Rng, RuleError};
    let h: History =
        serde_json::from_str(include_str!("fixtures/final-round-ties-v1.json")).unwrap();
    let state = replay(&h).unwrap();
    assert!(state.is_terminal());
    let mut observation = state.observe(0);
    assert_eq!(
        observation.players[..3]
            .iter()
            .map(|p| p.score)
            .collect::<Vec<_>>(),
        [16, 16, 14]
    );
    observation.phase = Phase::Main;
    observation.current = 1;
    observation.turns -= 2;
    // Seat zero is a valid earlier trigger, but seat one has not played yet.
    assert_eq!(
        observation.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("final round trigger order"))
    );
    observation.players.swap(1, 2);
    observation.reserved_counts.swap(1, 2);
    // An earlier trigger cannot make a future threshold score valid either.
    assert_eq!(
        observation.determinize(&mut Rng::new(42)),
        Err(RuleError::Invariant("final round trigger order"))
    );
}

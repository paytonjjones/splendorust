//! Explicit benchmark compatibility hooks. Normal actions and replay stay unchanged.
use super::*;

impl GameState {
    /// Inject a complete setup for a versioned external benchmark corpus.
    ///
    /// Each slice lists every card in its tier exactly once, in draw order:
    /// the first four IDs become market slots 0..4 for that tier. Noble IDs
    /// contain exactly player-count plus one distinct entries. Players start
    /// empty, player zero acts first, and all other setup rules stay standard.
    /// This API does not expose hidden setup information through Observation.
    pub fn new_benchmark_setup(
        count: u8,
        draw_order: [&[u8]; 3],
        noble_ids: &[u8],
    ) -> Result<Self, RuleError> {
        if !(2..=4).contains(&count) {
            return Err(RuleError::PlayerCount);
        }
        let mut seen = 0_u128;
        for (tier, cards) in draw_order.iter().enumerate() {
            if cards.len() != [40, 30, 20][tier] {
                return Err(RuleError::InvalidBenchmarkSetup);
            }
            for &id in *cards {
                if id >= 90
                    || CARDS[usize::from(id)].tier as usize != tier
                    || seen & (1_u128 << id) != 0
                {
                    return Err(RuleError::InvalidBenchmarkSetup);
                }
                seen |= 1_u128 << id;
            }
        }
        if seen != (1_u128 << 90) - 1 || noble_ids.len() != usize::from(count) + 1 {
            return Err(RuleError::InvalidBenchmarkSetup);
        }
        let mut nobles = 0_u16;
        for &id in noble_ids {
            if id >= 10 || nobles & (1_u16 << id) != 0 {
                return Err(RuleError::InvalidBenchmarkSetup);
            }
            nobles |= 1_u16 << id;
        }
        // Reuse standard setup defaults. This setup-only shuffle is overwritten;
        // it is outside the transition hot path and has no observable effect.
        let mut state = Self::new(count, 0)?;
        state.market = [NONE; 12];
        state.decks = [[NONE; 40]; 3];
        state.remaining = [40, 30, 20];
        for (tier, cards) in draw_order.iter().enumerate() {
            for (slot, &id) in cards.iter().rev().enumerate() {
                state.decks[tier][slot] = id;
            }
            for slot in 0..4 {
                state.market[tier * 4 + slot] = state.draw(tier);
            }
        }
        state.nobles = nobles;
        state.initial_nobles = nobles;
        state.check_invariants()?;
        Ok(state)
    }

    /// Experimental forced pass for an explicit benchmark rules profile.
    ///
    /// The published rules do not specify this behavior. This is not a legal
    /// Action and is never offered by legal_actions. A caller must record the
    /// compatibility version/profile and stop/report a full no-action cycle
    /// without awarding a stalemate victory. Existing final-round completion
    /// still applies through the normal end-turn path.
    pub fn apply_no_action_pass(&mut self) -> Result<(), RuleError> {
        if self.phase != Phase::Main || self.is_terminal() {
            return Err(RuleError::IllegalAction);
        }
        let mut actions = ActionSet::new();
        self.legal_actions(&mut actions);
        if !actions.is_empty() {
            return Err(RuleError::IllegalAction);
        }
        self.end_turn();
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decks() -> [Vec<u8>; 3] {
        [(0..40).collect(), (40..70).collect(), (70..90).collect()]
    }

    #[test]
    fn injected_setup_is_deterministic_and_draws_in_supplied_order() {
        let decks = decks();
        for count in 2..=4 {
            let nobles: Vec<_> = (0..count + 1).collect();
            let order = [&decks[0][..], &decks[1][..], &decks[2][..]];
            let state = GameState::new_benchmark_setup(count, order, &nobles).unwrap();
            assert_eq!(
                state,
                GameState::new_benchmark_setup(count, order, &nobles).unwrap()
            );
            state.check_invariants().unwrap();
            assert_eq!(state.market, [0, 1, 2, 3, 40, 41, 42, 43, 70, 71, 72, 73]);
            assert_eq!(state.nobles.count_ones(), u32::from(count) + 1);
            let mut next = state.clone();
            next.apply_action(Action::ReserveDeck(0)).unwrap();
            assert_eq!(next.players[0].reserved[0].card, 4);
            assert_eq!(next.market, state.market);
            next.check_invariants().unwrap();
            let mut visible = state.clone();
            visible.apply_action(Action::ReserveVisible(4)).unwrap();
            assert_eq!(visible.market[4], 44);
            visible.check_invariants().unwrap();
        }
        assert_eq!(ENGINE_VERSION, "splendorust-v1");
        assert_ne!(ENGINE_VERSION, BENCHMARK_COMPAT_ENGINE_VERSION);
    }

    #[test]
    fn injected_setup_rejects_invalid_permutations_and_nobles() {
        let original = decks();
        let check = |decks: &[Vec<u8>; 3], nobles: &[u8]| {
            GameState::new_benchmark_setup(2, [&decks[0], &decks[1], &decks[2]], nobles)
        };
        for (tier, index, value) in [(0, 0, 1), (0, 0, 40), (1, 0, 255), (2, 0, 69)] {
            let mut bad = original.clone();
            bad[tier][index] = value;
            assert_eq!(
                check(&bad, &[0, 1, 2]),
                Err(RuleError::InvalidBenchmarkSetup)
            );
        }
        let mut short = original.clone();
        short[0].pop();
        assert_eq!(
            check(&short, &[0, 1, 2]),
            Err(RuleError::InvalidBenchmarkSetup)
        );
        let mut long = original.clone();
        long[1].push(40);
        assert_eq!(
            check(&long, &[0, 1, 2]),
            Err(RuleError::InvalidBenchmarkSetup)
        );
        for nobles in [&[0, 1][..], &[0, 1, 1], &[0, 1, 10], &[0, 1, 2, 3]] {
            assert_eq!(
                check(&original, nobles),
                Err(RuleError::InvalidBenchmarkSetup)
            );
        }
        assert_eq!(
            GameState::new_benchmark_setup(1, [&original[0], &original[1], &original[2]], &[0, 1]),
            Err(RuleError::PlayerCount)
        );
    }

    #[test]
    fn experimental_pass_rejects_openings_and_non_main_without_mutation() {
        let mut state = GameState::new(2, 42).unwrap();
        let before = state.clone();
        assert_eq!(state.apply_no_action_pass(), Err(RuleError::IllegalAction));
        assert_eq!(state, before);
        for phase in [
            Phase::Return,
            Phase::Noble,
            Phase::Payment(Source::Market(0)),
            Phase::Terminal,
        ] {
            state.phase = phase;
            let before = state.clone();
            assert_eq!(state.apply_no_action_pass(), Err(RuleError::IllegalAction));
            assert_eq!(state, before);
        }
    }

    #[test]
    fn experimental_pass_resumes_a_reachable_block_without_inventing_an_outcome() {
        let mut found = None;
        for seed in 0..128 {
            let mut state = GameState::new(2, seed).unwrap();
            let mut rng = Rng::new(seed ^ 0xabc);
            let mut actions = ActionSet::new();
            for _ in 0..20_000 {
                state.legal_actions(&mut actions);
                if actions.is_empty() {
                    if !state.is_terminal() && !state.final_round {
                        found = Some(state);
                    }
                    break;
                }
                state
                    .apply_action(actions[rng.index(actions.len())])
                    .unwrap();
            }
            if found.is_some() {
                break;
            }
        }
        let mut state = found.expect("seeded corpus must reach a published-rule block");
        state.check_invariants().unwrap();
        let before = state.clone();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        assert!(legal.is_empty());
        state.apply_no_action_pass().unwrap();
        let mut expected = before;
        expected.end_turn();
        assert_eq!(state, expected);
        assert_eq!(state.phase, Phase::Main);
        assert!(state.outcome().is_none());
        state.check_invariants().unwrap();
    }
}

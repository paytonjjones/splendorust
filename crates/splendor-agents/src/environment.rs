//! Environment boundary used by the same information-set PUCT implementation.
//! Rules, legal actions, observation sampling, encoding and rewards live here.
use crate::native_environment as native;
use splendor_core::{Action, ActionSet, GameState, Observation, Phase, Rng};
use std::{fmt::Debug, hash::Hash};

pub trait Environment {
    type State: Clone;
    type Observation: Clone;
    type Action: Copy + Eq + Debug;
    type Key: Eq + Hash;
    type Legal: AsRef<[Self::Action]>;
    fn observe(state: &Self::State, viewer: usize) -> Self::Observation;
    fn current(state: &Self::State) -> usize;
    fn turns(state: &Self::State) -> u32;
    fn main(state: &Self::State) -> bool;
    fn rewards(state: &Self::State) -> Option<[f64; 2]>;
    fn legal(state: &Self::State) -> Self::Legal;
    fn apply(state: &mut Self::State, action: Self::Action, rng: &mut Rng);
    /// Apply a search transition with a fixed chance universe when supported.
    /// Other environments retain their normal transition behavior.
    fn apply_with_chance_seed(
        state: &mut Self::State,
        action: Self::Action,
        rng: &mut Rng,
        _chance_seed: Option<u64>,
    ) {
        Self::apply(state, action, rng);
    }
    fn determinize(o: &Self::Observation, rng: &mut Rng) -> Self::State;
    fn key(o: &Self::Observation, transferred: bool) -> Self::Key;
    fn action_index(a: Self::Action) -> usize;
    fn public_event(
        before: &Self::Observation,
        action: Self::Action,
        after: &Self::Observation,
    ) -> [f32; 32];
    fn full_public_event(
        before: &Self::Observation,
        action: Self::Action,
        after: &Self::Observation,
    ) -> [f32; 32] {
        Self::public_event(before, action, after)
    }
}

pub struct Canonical;
impl Environment for Canonical {
    type State = GameState;
    type Observation = Observation;
    type Action = Action;
    type Key = [u8; 192];
    type Legal = ActionSet;
    fn observe(s: &GameState, v: usize) -> Observation {
        s.observe(v)
    }
    fn current(s: &GameState) -> usize {
        s.current_player()
    }
    fn turns(s: &GameState) -> u32 {
        s.turns()
    }
    fn main(s: &GameState) -> bool {
        s.phase() == Phase::Main
    }
    fn rewards(s: &GameState) -> Option<[f64; 2]> {
        s.outcome().map(|o| {
            std::array::from_fn(|seat| {
                if o.winners & (1 << seat) != 0 {
                    1. / f64::from(o.winners.count_ones())
                } else {
                    0.
                }
            })
        })
    }
    fn legal(s: &GameState) -> ActionSet {
        let mut a = ActionSet::new();
        s.legal_actions(&mut a);
        a
    }
    fn apply(s: &mut GameState, a: Action, _: &mut Rng) {
        s.apply_action(a).expect("canonical legal action");
    }
    fn determinize(o: &Observation, r: &mut Rng) -> GameState {
        o.determinize(r).expect("valid observation")
    }
    fn key(o: &Observation, transferred: bool) -> [u8; 192] {
        let mut k = crate::neural_search::key(o);
        if transferred {
            k[188..192].copy_from_slice(&o.turns.to_le_bytes());
        }
        k
    }
    fn action_index(a: Action) -> usize {
        crate::neural::action_index(a).expect("canonical Main action")
    }
    fn public_event(before: &Observation, action: Action, after: &Observation) -> [f32; 32] {
        crate::public_history::canonical(before, action, after)
    }
    fn full_public_event(before: &Observation, action: Action, after: &Observation) -> [f32; 32] {
        crate::public_history::canonical_v2(before, action, after)
    }
}

pub struct AlphaZeroNative;
impl Environment for AlphaZeroNative {
    type State = native::State;
    type Observation = native::Observation;
    type Action = u8;
    type Key = native::Observation;
    type Legal = Vec<u8>;
    fn observe(s: &native::State, v: usize) -> native::Observation {
        s.observe(v as u8)
    }
    fn current(s: &native::State) -> usize {
        s.current_player()
    }
    fn turns(s: &native::State) -> u32 {
        s.turns()
    }
    fn main(_: &native::State) -> bool {
        true
    }
    fn rewards(s: &native::State) -> Option<[f64; 2]> {
        s.rewards().map(|r| r.map(|v| (v + 1.) / 2.))
    }
    fn legal(s: &native::State) -> Vec<u8> {
        s.legal()
    }
    fn apply(s: &mut native::State, a: u8, r: &mut Rng) {
        s.apply(a, r, None).expect("native legal action");
    }
    fn apply_with_chance_seed(s: &mut native::State, a: u8, r: &mut Rng, chance_seed: Option<u64>) {
        s.apply(a, r, chance_seed).expect("native legal action");
    }
    fn determinize(o: &native::Observation, r: &mut Rng) -> native::State {
        o.determinize(r).expect("valid native observation")
    }
    fn key(o: &native::Observation, _: bool) -> native::Observation {
        o.clone()
    }
    fn action_index(a: u8) -> usize {
        a as usize
    }
    fn public_event(
        before: &native::Observation,
        action: u8,
        after: &native::Observation,
    ) -> [f32; 32] {
        crate::public_history::native(before, action, after)
    }
    fn full_public_event(
        before: &native::Observation,
        action: u8,
        after: &native::Observation,
    ) -> [f32; 32] {
        crate::public_history::native_v2(before, action, after)
    }
}

/// Policy/value evaluation is independent of rules and search exploration.
pub trait PolicyValue<E: Environment> {
    type Policy: AsRef<[f32]>;
    fn evaluate(&mut self, o: &E::Observation) -> (Self::Policy, f64);
    fn evaluate_batch(&mut self, observations: &[E::Observation]) -> Vec<(Self::Policy, f64)> {
        observations.iter().map(|o| self.evaluate(o)).collect()
    }
    fn choices(o: &E::Observation, legal: &[E::Action]) -> Option<Vec<E::Action>>;
    fn rollout_action(&mut self, o: &E::Observation, legal: &[E::Action]) -> E::Action;
}

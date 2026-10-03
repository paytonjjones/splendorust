//! Explicit benchmark-only information intervention. No future deck order.
use crate::{
    environment::{AlphaZeroNative, Environment},
    native_environment as native,
};
use splendor_core::Rng;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Observation {
    pub observation: native::Observation,
    pub decks: [u128; 3],
}
impl Observation {
    pub fn state(&self) -> Result<native::State, &'static str> {
        native::State::from_partition(self.observation.clone(), self.decks)
    }
}
pub struct PrivilegedNative;
impl Environment for PrivilegedNative {
    type State = native::State;
    type Observation = Observation;
    type Action = u8;
    type Key = Observation;
    type Legal = Vec<u8>;
    fn observe(s: &native::State, viewer: usize) -> Observation {
        let (observation, decks) = s.partition(viewer as u8);
        Observation { observation, decks }
    }
    fn current(s: &native::State) -> usize {
        AlphaZeroNative::current(s)
    }
    fn turns(s: &native::State) -> u32 {
        AlphaZeroNative::turns(s)
    }
    fn main(s: &native::State) -> bool {
        AlphaZeroNative::main(s)
    }
    fn rewards(s: &native::State) -> Option<[f64; 2]> {
        AlphaZeroNative::rewards(s)
    }
    fn legal(s: &native::State) -> Vec<u8> {
        AlphaZeroNative::legal(s)
    }
    fn apply(s: &mut native::State, a: u8, r: &mut Rng) {
        AlphaZeroNative::apply(s, a, r);
    }
    fn determinize(o: &Observation, _: &mut Rng) -> native::State {
        o.state().expect("validated privileged partition")
    }
    fn key(o: &Observation, _: bool) -> Observation {
        o.clone()
    }
    fn action_index(a: u8) -> usize {
        a as usize
    }
    fn public_event(before: &Observation, action: u8, after: &Observation) -> [f32; 32] {
        AlphaZeroNative::public_event(&before.observation, action, &after.observation)
    }
    fn full_public_event(before: &Observation, action: u8, after: &Observation) -> [f32; 32] {
        AlphaZeroNative::full_public_event(&before.observation, action, &after.observation)
    }
}

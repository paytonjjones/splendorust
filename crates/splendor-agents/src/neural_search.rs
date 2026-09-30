//! Observation-keyed information-set PUCT. New determinization for each simulation.
use super::{
    Agent, SearchConfig, best,
    neural::{ACTIONS, INPUTS, action_index, features},
    safe_choices,
};
use splendor_core::{Action, ActionSet, GameState, Observation, Phase, Rng};
use std::{
    collections::{HashMap, VecDeque},
    sync::OnceLock,
};
struct Layer {
    input: usize,
    output: usize,
    weights: Vec<f32>,
    bias: Vec<f32>,
}
impl Layer {
    fn read(input: usize, output: usize, values: &mut impl Iterator<Item = f32>) -> Self {
        Self {
            input,
            output,
            weights: values.take(input * output).collect(),
            bias: values.take(output).collect(),
        }
    }
    fn apply(&self, x: &[f32], out: &mut [f32]) {
        for (row, y) in out.iter_mut().enumerate().take(self.output) {
            let weights = &self.weights[row * self.input..(row + 1) * self.input];
            let (wc, wr) = weights.as_chunks::<8>();
            let (xc, xr) = x.as_chunks::<8>();
            let mut sums = [0f32; 8];
            for (w, x) in wc.iter().zip(xc) {
                for j in 0..8 {
                    sums[j] += w[j] * x[j];
                }
            }
            *y = self.bias[row]
                + sums.iter().sum::<f32>()
                + wr.iter().zip(xr).map(|(w, x)| w * x).sum::<f32>();
        }
    }
}
pub struct Model {
    stem: Layer,
    first: Layer,
    second: Layer,
    policy: Layer,
    value: Layer,
}
impl Model {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let inputs = match bytes.len() {
            316176 => INPUTS,
            332560 => 322,
            _ => panic!("model byte length"),
        };
        let mut values = bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|&c| f32::from_le_bytes(c));
        let model = Self {
            stem: Layer::read(inputs, 128, &mut values),
            first: Layer::read(128, 128, &mut values),
            second: Layer::read(128, 128, &mut values),
            policy: Layer::read(128, ACTIONS, &mut values),
            value: Layer::read(128, 1, &mut values),
        };
        assert!(values.next().is_none());
        model
    }
    pub fn infer(&self, x: &[f32]) -> ([f32; ACTIONS], f32) {
        assert_eq!(x.len(), self.stem.input);
        let mut h = [0f32; 128];
        let mut a = [0f32; 128];
        let mut b = [0f32; 128];
        self.stem.apply(x, &mut h);
        h.iter_mut().for_each(|x| *x = x.max(0.0));
        self.first.apply(&h, &mut a);
        a.iter_mut().for_each(|x| *x = x.max(0.0));
        self.second.apply(&a, &mut b);
        for i in 0..128 {
            h[i] = (h[i] + b[i]).max(0.0);
        }
        let mut policy = [0f32; ACTIONS];
        let mut value = [0f32; 1];
        self.policy.apply(&h, &mut policy);
        self.value.apply(&h, &mut value);
        if self.stem.input == 322 {
            value[0] += x[INPUTS..]
                .iter()
                .zip(super::value_weights::WEIGHTS)
                .map(|(x, w)| *x * w as f32)
                .sum::<f32>();
        }
        (policy, value[0])
    }
}
fn model() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e25.bin")))
}
struct Edge {
    action: Action,
    prior: f64,
    visits: u32,
    sum: f64,
}
struct Node {
    edges: Vec<Edge>,
    visits: u32,
    value: f64,
}
pub struct NeuralAgent {
    rng: Rng,
    config: SearchConfig,
    history: VecDeque<Observation>,
    simulations: u64,
    calls: u64,
    pub logistic: bool,
    pub enhanced: bool,
    pub rollout_depth: u32,
}
impl NeuralAgent {
    pub fn new(seed: u64, config: SearchConfig) -> Self {
        Self {
            rng: Rng::new(seed),
            config,
            history: VecDeque::new(),
            simulations: 0,
            calls: 0,
            logistic: false,
            enhanced: false,
            rollout_depth: 0,
        }
    }
    fn leaf(&mut self, o: &Observation) -> ([f32; ACTIONS], f64) {
        self.calls += 1;
        let (p, v) = if self.enhanced {
            model_v2().infer(&super::neural::enhanced_features(o))
        } else {
            model().infer(&features(o))
        };
        if self.logistic {
            return (
                p,
                super::learned::predict(o, o.viewer as usize, &super::value_weights::WEIGHTS),
            );
        }
        (p, 1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp()))
    }
    fn expand(&mut self, o: &Observation, legal: &[Action]) -> Node {
        let (logits, value) = self.leaf(o);
        let max = legal
            .iter()
            .map(|&a| logits[action_index(a).unwrap()])
            .fold(f32::NEG_INFINITY, f32::max);
        let weights: Vec<_> = legal
            .iter()
            .map(|&a| f64::from((logits[action_index(a).unwrap()] - max).exp()))
            .collect();
        let total: f64 = weights.iter().sum();
        Node {
            edges: legal
                .iter()
                .zip(weights)
                .map(|(&action, w)| Edge {
                    action,
                    prior: 0.98 * w / total + 0.02 / legal.len() as f64,
                    visits: 0,
                    sum: 0.0,
                })
                .collect(),
            visits: 0,
            value,
        }
    }
    fn rollout(&mut self, state: &GameState) -> [f64; 2] {
        let seat = state.current_player();
        let mut s = state.clone();
        let start = s.turns();
        let mut legal = ActionSet::new();
        for _ in 0..self.rollout_depth * 4 {
            if s.is_terminal()
                || s.turns() == u32::MAX
                || (s.turns() - start >= self.rollout_depth && s.phase() == Phase::Main)
            {
                break;
            }
            s.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = s.observe(s.current_player());
            s.apply_action(best(&o, &legal, true)).unwrap();
        }
        if let Some(outcome) = s.outcome() {
            return std::array::from_fn(|p| {
                if outcome.winners & (1 << p) != 0 {
                    1.0 / f64::from(outcome.winners.count_ones())
                } else {
                    0.0
                }
            });
        }
        let (_, v) = self.leaf(&s.observe(seat));
        let mut values = [1.0 - v; 2];
        values[seat] = v;
        values
    }
    fn simulate(
        &mut self,
        state: &mut GameState,
        depth: u32,
        nodes: &mut Vec<Node>,
        index: &mut HashMap<[u8; 192], usize>,
    ) -> [f64; 2] {
        if let Some(outcome) = state.outcome() {
            return std::array::from_fn(|seat| {
                if outcome.winners & (1 << seat) != 0 {
                    1.0 / f64::from(outcome.winners.count_ones())
                } else {
                    0.0
                }
            });
        }
        let seat = state.current_player();
        let o = state.observe(seat);
        if depth == 0 || state.turns() == u32::MAX {
            let (_, v) = self.leaf(&o);
            let mut result = [1.0 - v; 2];
            result[seat] = v;
            return result;
        }
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        if legal.is_empty() {
            let (_, v) = self.leaf(&o);
            let mut result = [1.0 - v; 2];
            result[seat] = v;
            return result;
        }
        if state.phase() != Phase::Main {
            let safe = safe_choices(&o, &legal);
            let action = best(&o, safe.as_deref().unwrap_or(&legal), true);
            let old = state.turns();
            state.apply_action(action).unwrap();
            return self.simulate(state, depth - u32::from(state.turns() != old), nodes, index);
        }
        let key = key(&o);
        let i = if let Some(&i) = index.get(&key) {
            i
        } else {
            let safe = safe_choices(&o, &legal);
            let mut node = self.expand(&o, safe.as_deref().unwrap_or(&legal));
            if self.rollout_depth > 0 {
                node.value = self.rollout(state)[seat];
            }
            let mut result = [1.0 - node.value; 2];
            result[seat] = node.value;
            index.insert(key, nodes.len());
            nodes.push(node);
            return result;
        };
        let node = &nodes[i];
        let edge = (0..node.edges.len())
            .max_by(|&a, &b| {
                let score = |j: usize| {
                    let e = &node.edges[j];
                    let q = if e.visits == 0 {
                        node.value
                    } else {
                        e.sum / f64::from(e.visits)
                    };
                    q + 1.5 * e.prior * f64::from(node.visits + 1).sqrt() / f64::from(e.visits + 1)
                };
                score(a).total_cmp(&score(b))
            })
            .unwrap();
        let action = node.edges[edge].action;
        debug_assert!(legal.contains(&action));
        let old = state.turns();
        state.apply_action(action).unwrap();
        let values = self.simulate(state, depth - u32::from(state.turns() != old), nodes, index);
        let node = &mut nodes[i];
        node.visits += 1;
        node.edges[edge].visits += 1;
        node.edges[edge].sum += values[seat];
        values
    }
}
fn key(o: &Observation) -> [u8; 192] {
    debug_assert_eq!(o.phase, Phase::Main);
    let mut bytes = [0u8; 192];
    let mut offset = 0;
    let mut put = |part: &[u8]| {
        bytes[offset..offset + part.len()].copy_from_slice(part);
        offset += part.len();
    };
    for p in &o.players {
        put(&p.tokens);
        put(&p.bonuses);
        put(&[p.score]);
        put(&p.owned.to_le_bytes());
        put(&p.nobles.to_le_bytes());
        for r in &p.reserved {
            put(&[r.card, r.tier, u8::from(r.public)]);
        }
    }
    put(&o.reserved_counts);
    put(&[o.count, o.viewer, o.current, u8::from(o.final_round)]);
    put(&o.bank);
    put(&o.market);
    put(&o.remaining);
    put(&o.nobles.to_le_bytes());
    bytes
}

impl Agent for NeuralAgent {
    fn work_counts(&self) -> (u64, u64) {
        (self.simulations, self.calls)
    }
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        if o.count != 2 || o.phase != Phase::Main || legal.len() == 1 || o.turns == u32::MAX {
            let safe = safe_choices(o, legal);
            return best(o, safe.as_deref().unwrap_or(legal), true);
        }
        let mut normalized = o.clone();
        normalized.turns = 0;
        let repeated = self.history.contains(&normalized);
        if self.history.len() == 16 {
            self.history.pop_front();
        }
        self.history.push_back(normalized);
        let safe = safe_choices(o, legal);
        let mut choices = safe.unwrap_or_else(|| legal.to_vec());
        if repeated {
            let buys: Vec<_> = choices
                .iter()
                .copied()
                .filter(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                .collect();
            if !buys.is_empty() {
                choices = buys;
            }
        }
        let mut nodes = vec![self.expand(o, &choices)];
        let mut index = HashMap::new();
        index.insert(key(o), 0);
        let start = std::time::Instant::now();
        for simulation in 0..self.config.iterations {
            if simulation > 0
                && self
                    .config
                    .time_budget
                    .is_some_and(|t| start.elapsed() >= t)
            {
                break;
            }
            let mut state = o.determinize(&mut self.rng).expect("valid observation");
            self.simulate(&mut state, self.config.depth.max(1), &mut nodes, &mut index);
            self.simulations += 1;
        }
        nodes[0]
            .edges
            .iter()
            .max_by(|a, b| {
                a.visits
                    .cmp(&b.visits)
                    .then_with(|| a.prior.total_cmp(&b.prior))
            })
            .unwrap()
            .action
    }
}

pub fn value(o: &Observation) -> f64 {
    let (_, v) = model().infer(&features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

fn model_v2() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e26.bin")))
}
pub fn value_v2(o: &Observation) -> f64 {
    let (_, v) = model_v2().infer(&super::neural::enhanced_features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compact_keys_preserve_exact_observation_identity() {
        let mut seen = HashMap::new();
        let mut rng = Rng::new(771);
        for seed in 0..100 {
            let mut state = GameState::new(2, seed).unwrap();
            let mut legal = ActionSet::new();
            for _ in 0..200 {
                state.legal_actions(&mut legal);
                if legal.is_empty() {
                    break;
                }
                if state.phase() == Phase::Main {
                    let mut o = state.observe(state.current_player());
                    o.turns = 0;
                    if let Some(old) = seen.insert(key(&o), o.clone()) {
                        assert_eq!(old, o);
                    }
                }
                state.apply_action(legal[rng.index(legal.len())]).unwrap();
            }
        }
    }
    #[test]
    fn neural_tree_choices_match_across_hidden_worlds() {
        let mut s = GameState::new(2, 492).unwrap();
        let mut rng = Rng::new(917);
        let mut legal = ActionSet::new();
        for _ in 0..80 {
            s.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = s.observe(s.current_player());
            let other = o.determinize(&mut rng).unwrap().observe(s.current_player());
            assert_eq!(o, other);
            let config = SearchConfig {
                iterations: 8,
                depth: 8,
                ..Default::default()
            };
            let mut a = NeuralAgent::new(1, config.clone());
            let mut b = NeuralAgent::new(1, config);
            let action = a.select_action(&o, &legal);
            assert_eq!(action, b.select_action(&other, &legal));
            assert!(legal.contains(&action));
            s.apply_action(legal[rng.index(legal.len())]).unwrap();
        }
    }
}

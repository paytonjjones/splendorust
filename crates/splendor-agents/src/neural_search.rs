//! Observation-keyed information-set PUCT. New determinization for each simulation.
use super::{
    Agent, SearchConfig, best,
    neural::{ACTIONS, INPUTS, action_index, features},
    safe_choices,
};
use splendor_core::{Action, Observation, Phase, Rng};
use std::{
    collections::{HashMap, HashSet, VecDeque},
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
#[cfg(not(all(feature = "external-model-only", target_arch = "wasm32")))]
fn model() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e25.bin")))
}
#[cfg(all(feature = "external-model-only", target_arch = "wasm32"))]
fn model() -> &'static Model {
    panic!("embedded neural checkpoints are disabled in this build")
}
struct Edge<A = Action> {
    action: A,
    prior: f64,
    visits: u32,
    sum: f64,
}
struct Node<A = Action> {
    edges: Vec<Edge<A>>,
    visits: u32,
    value: f64,
}
struct PendingLeaf<O, A, K> {
    observation: O,
    legal: Option<Vec<A>>,
    key: Option<K>,
    seat: usize,
    path: Vec<(usize, usize, usize)>,
}
type PendingEnvironmentLeaf<E> = PendingLeaf<
    <E as crate::environment::Environment>::Observation,
    <E as crate::environment::Environment>::Action,
    (<E as crate::environment::Environment>::Key, u64),
>;
const SEARCH_ACTION_CAPACITY: usize = 81;
impl<A> Node<A> {
    /// Appendix D mixed value; unvisited actions have no invented empirical Q.
    fn mixed_value(&self) -> f64 {
        let n: u32 = self.edges.iter().map(|e| e.visits).sum();
        if n == 0 {
            return self.value;
        }
        let mass: f64 = self
            .edges
            .iter()
            .filter(|e| e.visits > 0)
            .map(|e| e.prior.max(f64::MIN_POSITIVE))
            .sum();
        let weighted: f64 = self
            .edges
            .iter()
            .filter(|e| e.visits > 0)
            .map(|e| e.prior.max(f64::MIN_POSITIVE) * e.sum / f64::from(e.visits) / mass)
            .sum();
        (self.value + f64::from(n) * weighted) / f64::from(n + 1)
    }
    fn completed_scores(&self, cvisit: f64, cscale: f64) -> [f64; SEARCH_ACTION_CAPACITY] {
        let mut scores = [0.0; SEARCH_ACTION_CAPACITY];
        let mixed = self.mixed_value();
        let mut lo = f64::INFINITY;
        let mut hi = f64::NEG_INFINITY;
        let mut max_visits = 0;
        for (i, e) in self.edges.iter().enumerate() {
            let q = if e.visits == 0 {
                mixed
            } else {
                e.sum / f64::from(e.visits)
            };
            scores[i] = q;
            lo = lo.min(q);
            hi = hi.max(q);
            max_visits = max_visits.max(e.visits);
        }
        let scale = (cvisit + f64::from(max_visits)) * cscale / (hi - lo).max(1e-8);
        for (i, e) in self.edges.iter().enumerate() {
            scores[i] = e.prior.max(f64::MIN_POSITIVE).ln() + scale * (scores[i] - lo);
        }
        scores
    }
    fn improved_policy(&self, cvisit: f64, cscale: f64) -> [f64; SEARCH_ACTION_CAPACITY] {
        let mut policy = self.completed_scores(cvisit, cscale);
        let max = policy[..self.edges.len()]
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        let mut total = 0.0;
        for v in &mut policy[..self.edges.len()] {
            *v = (*v - max).exp();
            total += *v;
        }
        for v in &mut policy[..self.edges.len()] {
            *v /= total;
        }
        policy
    }
}

/// Diagnostic root labels. Values are acting-player win credits, not signed values.
/// Unvisited edges have no Q label. Capturing these labels changes no search choice.
#[derive(Clone, Debug, PartialEq)]
pub struct SearchTargets {
    pub visits: [u32; ACTIONS],
    pub q: [Option<f32>; ACTIONS],
    pub root_value: f32,
    pub network_value: f32,
}

pub struct NeuralAgent {
    pub clock: Option<fn() -> f64>,
    deadline_ms: Option<f64>,
    rng: Rng,
    config: SearchConfig,
    history: VecDeque<Observation>,
    public_events: VecDeque<[f32; 32]>,
    simulations: u64,
    calls: u64,
    pub logistic: bool,
    pub enhanced: bool,
    pub expert: bool,
    pub self_play: bool,
    pub transferred: bool,
    pub external_model: Option<&'static super::transfer::Model>,
    pub cpuct: f64,
    pub fpu_reduction: f64,
    pub uniform_prior: f64,
    pub dynamic_fpu: bool,
    pub world_pool: usize,
    /// Opt-in leaf batch size for observation-only environment search.
    pub inference_batch_size: usize,
    /// Number of search waves observed at each request count.
    pub inference_batch_histogram: [u64; 9],
    /// Requests for an information set already queued in the same wave.
    pub duplicate_leaf_inferences: u64,
    #[cfg(test)]
    force_batch_search: bool,
    /// Deterministic chance universes cycled across native root simulations.
    /// Zero preserves the ordinary per-transition random refill behavior.
    pub chance_universes: usize,
    pub rollout_depth: u32,
    pub persistent: bool,
    /// Gumbel planning with completed-Q policy targets (E72).
    pub root_only: bool,
    pub belief_root: bool,
    pub belief_calls: u64,
    root_evaluation: bool,
    pub correction_calls: u64,
    pub gumbel: bool,
    pub gumbel_noise: f64,
    pub gumbel_max_considered: usize,
    pub gumbel_cvisit: f64,
    pub gumbel_cscale: f64,
    cached_nodes: Vec<Node>,
    cached_index: HashMap<([u8; 192], u64), usize>,
    root_policy: Option<[f32; ACTIONS]>,
    root_value: Option<f32>,
    pub capture_search_targets: bool,
    pub search_targets: Option<SearchTargets>,
}
impl NeuralAgent {
    /// Change an opt-in self-play cap. This does not reset policy RNG or history.
    pub fn set_search_iterations(&mut self, iterations: u32) {
        assert!(self.config.time_budget.is_none());
        self.config.iterations = iterations;
    }
    pub fn new(seed: u64, config: SearchConfig) -> Self {
        Self {
            clock: None,
            deadline_ms: None,
            rng: Rng::new(seed),
            config,
            history: VecDeque::new(),
            public_events: VecDeque::new(),
            simulations: 0,
            calls: 0,
            logistic: false,
            enhanced: false,
            expert: false,
            self_play: false,
            transferred: false,
            external_model: None,
            cpuct: 1.5,
            fpu_reduction: 0.0,
            uniform_prior: 0.02,
            dynamic_fpu: false,
            world_pool: 0,
            inference_batch_size: 1,
            inference_batch_histogram: [0; 9],
            duplicate_leaf_inferences: 0,
            #[cfg(test)]
            force_batch_search: false,
            chance_universes: 0,
            rollout_depth: 0,
            persistent: false,
            root_only: false,
            belief_root: false,
            belief_calls: 0,
            root_evaluation: false,
            correction_calls: 0,
            gumbel: false,
            gumbel_noise: 0.0,
            gumbel_max_considered: 16,
            gumbel_cvisit: 50.0,
            gumbel_cscale: 0.1,
            cached_nodes: Vec::new(),
            cached_index: HashMap::new(),
            root_policy: None,
            root_value: None,
            capture_search_targets: false,
            search_targets: None,
        }
    }
    fn history_hash(&self) -> u64 {
        if !self.external_model.is_some_and(|m| m.uses_history_bridge()) {
            return 0;
        }
        self.public_events
            .iter()
            .flatten()
            .fold(0xcbf29ce484222325u64, |h, v| {
                (h ^ u64::from(v.to_bits())).wrapping_mul(0x100000001b3)
            })
    }
    pub fn observe_event(&mut self, event: [f32; 32]) {
        if self.public_events.len() == 16 {
            self.public_events.pop_front();
        }
        self.public_events.push_back(event);
    }
    fn history_tensor(&self, current: u8) -> [[f32; 32]; 16] {
        let mut result = [[0.0; 32]; 16];
        for (target, event) in result[16 - self.public_events.len()..]
            .iter_mut()
            .zip(&self.public_events)
        {
            *target = *event;
            target[1] = f32::from(event[1] != f32::from(current));
        }
        result
    }
    fn apply_environment<E: crate::environment::Environment>(
        &mut self,
        state: &mut E::State,
        action: E::Action,
        chance_seed: Option<u64>,
    ) -> Option<VecDeque<[f32; 32]>> {
        if !self.external_model.is_some_and(|m| m.uses_history_bridge()) {
            E::apply_with_chance_seed(state, action, &mut self.rng, chance_seed);
            return None;
        }
        let old = self.public_events.clone();
        let actor = E::current(state);
        let before = E::observe(state, actor);
        E::apply_with_chance_seed(state, action, &mut self.rng, chance_seed);
        let after = E::observe(state, actor);
        let event = if self
            .external_model
            .is_some_and(|m| m.uses_full_public_history())
        {
            E::full_public_event(&before, action, &after)
        } else {
            E::public_event(&before, action, &after)
        };
        self.observe_event(event);
        Some(old)
    }
    fn make_chance_seeds(&mut self) -> Vec<u64> {
        if self.chance_universes == 0 {
            return Vec::new();
        }
        (0..self.chance_universes)
            .map(|_| self.rng.next_u64().max(1))
            .collect()
    }
    fn chance_seed_for(seeds: &[u64], simulation: usize) -> Option<u64> {
        (!seeds.is_empty()).then(|| seeds[simulation % seeds.len()])
    }
    fn restore_history(&mut self, old: Option<VecDeque<[f32; 32]>>) {
        if let Some(old) = old {
            self.public_events = old;
        }
    }
    fn tree_key(&self, o: &Observation) -> ([u8; 192], u64) {
        let mut bytes = key(o);
        if self.transferred {
            // Unlike E26, the transferred network has a turn-counter input.
            bytes[188..192].copy_from_slice(&o.turns.to_le_bytes());
        }
        (bytes, self.history_hash())
    }
    pub(super) fn leaf(&mut self, o: &Observation) -> ([f32; ACTIONS], f64) {
        self.calls += 1;
        if self.transferred {
            if o.turns >= 124 {
                return (
                    [0.0; ACTIONS],
                    super::learned::predict(o, o.viewer as usize, &super::value_weights::WEIGHTS),
                );
            }
            let mut x = super::transfer::encode(o, &mut self.rng);
            if self.belief_root && self.root_evaluation {
                x = super::belief::moments(&x, &super::transfer::public_context(o)).0;
                self.belief_calls += 1;
            }
            let model = self.external_model.unwrap_or_else(model_transferred);
            let (policy, values) = if self.root_only && !self.root_evaluation {
                model.infer_base(&x)
            } else if model.needs_public_context() {
                if model.has_correction() {
                    self.correction_calls += 1;
                }
                model.infer_with_history(
                    &x,
                    &super::transfer::public_context(o),
                    false,
                    &self.history_tensor(o.current),
                    &crate::public_history::canonical_pool(o),
                )
            } else {
                if model.has_correction() {
                    self.correction_calls += 1;
                }
                model.infer(&x)
            };
            let seat = usize::from(o.viewer != o.current);
            return (
                super::transfer::policy_logits(&policy),
                (f64::from(values[seat]) + 1.0) / 2.0,
            );
        }
        let (p, v) = if self.self_play {
            model_self_play().infer(&super::neural::enhanced_features(o))
        } else if self.expert {
            model_expert().infer(&super::neural::enhanced_features(o))
        } else if self.enhanced {
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
    fn expand_root_environment<E: crate::environment::Environment>(
        &mut self,
        o: &E::Observation,
        legal: &[E::Action],
    ) -> Node<E::Action>
    where
        Self: crate::environment::PolicyValue<E>,
    {
        assert!(!self.root_evaluation);
        self.root_evaluation = true;
        let node = self.expand_environment::<E>(o, legal);
        self.root_evaluation = false;
        node
    }
    fn expand_environment<E: crate::environment::Environment>(
        &mut self,
        o: &E::Observation,
        legal: &[E::Action],
    ) -> Node<E::Action>
    where
        Self: crate::environment::PolicyValue<E>,
    {
        let (policy, value) = <Self as crate::environment::PolicyValue<E>>::evaluate(self, o);
        let logits = policy.as_ref();
        let max = legal
            .iter()
            .map(|&a| logits[E::action_index(a)])
            .fold(f32::NEG_INFINITY, f32::max);
        let weights: Vec<_> = legal
            .iter()
            .map(|&a| f64::from((logits[E::action_index(a)] - max).exp()))
            .collect();
        let total: f64 = weights.iter().sum();
        Node {
            edges: legal
                .iter()
                .zip(weights)
                .map(|(&action, w)| Edge {
                    action,
                    prior: (1.0 - self.uniform_prior) * w / total
                        + self.uniform_prior / legal.len() as f64,
                    visits: 0,
                    sum: 0.0,
                })
                .collect(),
            visits: 0,
            value,
        }
    }
    fn rollout_environment<E: crate::environment::Environment>(
        &mut self,
        state: &E::State,
        chance_seed: Option<u64>,
    ) -> [f64; 2]
    where
        Self: crate::environment::PolicyValue<E>,
    {
        let seat = E::current(state);
        let mut s = state.clone();
        let start = E::turns(&s);
        for _ in 0..self.rollout_depth * 4 {
            if E::rewards(&s).is_some()
                || E::turns(&s) == u32::MAX
                || (E::turns(&s) - start >= self.rollout_depth && E::main(&s))
            {
                break;
            }
            let actions = E::legal(&s);
            let legal = actions.as_ref();
            if legal.is_empty() {
                break;
            }
            let o = E::observe(&s, E::current(&s));
            E::apply_with_chance_seed(
                &mut s,
                <Self as crate::environment::PolicyValue<E>>::rollout_action(self, &o, legal),
                &mut self.rng,
                chance_seed,
            );
        }
        if let Some(r) = E::rewards(&s) {
            return r;
        }
        let (_, v) =
            <Self as crate::environment::PolicyValue<E>>::evaluate(self, &E::observe(&s, seat));
        let mut values = [1.0 - v; 2];
        values[seat] = v;
        values
    }
    fn gumbel_root<E: crate::environment::Environment>(
        &mut self,
        o: &E::Observation,
        root: usize,
        nodes: &mut Vec<Node<E::Action>>,
        index: &mut HashMap<(E::Key, u64), usize>,
        worlds: &[E::State],
    ) -> usize
    where
        Self: crate::environment::PolicyValue<E>,
    {
        assert!(!self.persistent, "Gumbel requires a fresh root budget");
        let budget = self.config.iterations as usize;
        let mut noise = [0.0; SEARCH_ACTION_CAPACITY];
        for v in &mut noise[..nodes[root].edges.len()] {
            if self.gumbel_noise > 0.0 {
                let u = ((self.rng.next_u64() >> 11) as f64 + 0.5) / (1u64 << 53) as f64;
                *v = -(-u.ln()).ln() * self.gumbel_noise;
            }
        }
        let mut active: Vec<_> = (0..nodes[root].edges.len()).collect();
        active.sort_by(|&a, &b| {
            (noise[b] + nodes[root].edges[b].prior.max(f64::MIN_POSITIVE).ln())
                .total_cmp(&(noise[a] + nodes[root].edges[a].prior.max(f64::MIN_POSITIVE).ln()))
        });
        if budget == 0 {
            return active[0];
        }
        let chance_seeds = self.make_chance_seeds();
        let mut considered = active.len().min(self.gumbel_max_considered).min(budget);
        while considered > 1
            && budget / ((usize::BITS - (considered - 1).leading_zeros()) as usize) < considered
        {
            considered -= 1;
        }
        active.truncate(considered);
        let mut remaining = budget;
        let mut simulation = 0usize;
        'search: while remaining > 0 {
            let phases = if active.len() == 1 {
                1
            } else {
                (usize::BITS - (active.len() - 1).leading_zeros()) as usize
            };
            let allocation = remaining / phases;
            for turn in 0..allocation {
                if simulation > 0
                    && self
                        .deadline_ms
                        .zip(self.clock)
                        .is_some_and(|(deadline, clock)| clock() >= deadline)
                {
                    let scores =
                        nodes[root].completed_scores(self.gumbel_cvisit, self.gumbel_cscale);
                    active.sort_by(|&a, &b| {
                        (noise[b] + scores[b]).total_cmp(&(noise[a] + scores[a]))
                    });
                    break 'search;
                }
                let edge = active[turn % active.len()];
                let mut state = if worlds.is_empty() {
                    E::determinize(o, &mut self.rng)
                } else {
                    worlds[simulation % worlds.len()].clone()
                };
                let seat = E::current(&state);
                let old = E::turns(&state);
                let chance_seed = Self::chance_seed_for(&chance_seeds, simulation);
                let old_history = self.apply_environment::<E>(
                    &mut state,
                    nodes[root].edges[edge].action,
                    chance_seed,
                );
                let depth = self.config.depth.max(1) - u32::from(E::turns(&state) != old);
                let values =
                    self.simulate_environment::<E>(&mut state, depth, nodes, index, chance_seed);
                self.restore_history(old_history);
                nodes[root].visits += 1;
                nodes[root].edges[edge].visits += 1;
                nodes[root].edges[edge].sum += values[seat];
                self.simulations += 1;
                simulation += 1;
            }
            remaining -= allocation;
            let scores = nodes[root].completed_scores(self.gumbel_cvisit, self.gumbel_cscale);
            active.sort_by(|&a, &b| (noise[b] + scores[b]).total_cmp(&(noise[a] + scores[a])));
            if active.len() > 1 {
                active.truncate(active.len().div_ceil(2));
            }
        }
        active[0]
    }
    fn simulate_environment<E: crate::environment::Environment>(
        &mut self,
        state: &mut E::State,
        depth: u32,
        nodes: &mut Vec<Node<E::Action>>,
        index: &mut HashMap<(E::Key, u64), usize>,
        chance_seed: Option<u64>,
    ) -> [f64; 2]
    where
        Self: crate::environment::PolicyValue<E>,
    {
        if let Some(r) = E::rewards(state) {
            return r;
        }
        let seat = E::current(state);
        let o = E::observe(state, seat);
        if depth == 0 || E::turns(state) == u32::MAX {
            let (_, v) = <Self as crate::environment::PolicyValue<E>>::evaluate(self, &o);
            let mut r = [1.0 - v; 2];
            r[seat] = v;
            return r;
        }
        let actions = E::legal(state);
        let legal = actions.as_ref();
        if legal.is_empty() {
            let (_, v) = <Self as crate::environment::PolicyValue<E>>::evaluate(self, &o);
            let mut r = [1.0 - v; 2];
            r[seat] = v;
            return r;
        }
        if !E::main(state) {
            let choices = <Self as crate::environment::PolicyValue<E>>::choices(&o, legal);
            let action = <Self as crate::environment::PolicyValue<E>>::rollout_action(
                self,
                &o,
                choices.as_deref().unwrap_or(legal),
            );
            let old = E::turns(state);
            let old_history = self.apply_environment::<E>(state, action, chance_seed);
            let values = self.simulate_environment::<E>(
                state,
                depth - u32::from(E::turns(state) != old),
                nodes,
                index,
                chance_seed,
            );
            self.restore_history(old_history);
            return values;
        }
        let key = (E::key(&o, self.transferred), self.history_hash());
        let i = if let Some(&i) = index.get(&key) {
            i
        } else {
            let choices = <Self as crate::environment::PolicyValue<E>>::choices(&o, legal);
            let mut node = self.expand_environment::<E>(&o, choices.as_deref().unwrap_or(legal));
            if self.rollout_depth > 0 {
                node.value = self.rollout_environment::<E>(state, chance_seed)[seat];
            }
            let mut r = [1.0 - node.value; 2];
            r[seat] = node.value;
            index.insert(key, nodes.len());
            nodes.push(node);
            return r;
        };
        let node = &nodes[i];
        let edge = if self.gumbel {
            let policy = node.improved_policy(self.gumbel_cvisit, self.gumbel_cscale);
            (0..node.edges.len())
                .max_by(|&a, &b| {
                    let score = |j: usize| {
                        policy[j] - f64::from(node.edges[j].visits) / f64::from(node.visits + 1)
                    };
                    score(a).total_cmp(&score(b))
                })
                .unwrap()
        } else {
            (0..node.edges.len())
                .max_by(|&a, &b| {
                    let score = |j: usize| {
                        let e = &node.edges[j];
                        let q = if e.visits == 0 {
                            node.value - self.fpu_reduction
                        } else {
                            e.sum / f64::from(e.visits)
                        };
                        q + self.cpuct * e.prior * f64::from(node.visits + 1).sqrt()
                            / f64::from(e.visits + 1)
                    };
                    score(a).total_cmp(&score(b))
                })
                .unwrap()
        };
        let action = node.edges[edge].action;
        debug_assert!(legal.contains(&action));
        let old = E::turns(state);
        let old_history = self.apply_environment::<E>(state, action, chance_seed);
        let values = self.simulate_environment::<E>(
            state,
            depth - u32::from(E::turns(state) != old),
            nodes,
            index,
            chance_seed,
        );
        self.restore_history(old_history);
        let node = &mut nodes[i];
        if self.dynamic_fpu {
            node.value = (f64::from(node.visits + 1) * node.value + values[seat])
                / f64::from(node.visits + 2);
        }
        node.visits += 1;
        node.edges[edge].visits += 1;
        node.edges[edge].sum += values[seat];
        values
    }
    pub(super) fn native_leaf(
        &mut self,
        o: &crate::native_environment::Observation,
    ) -> ([f32; 81], f64) {
        let world = o
            .determinize(&mut self.rng)
            .expect("valid native observation");
        self.native_world_leaf(o, &world)
    }
    fn native_world_leaf(
        &mut self,
        o: &crate::native_environment::Observation,
        world: &crate::native_environment::State,
    ) -> ([f32; 81], f64) {
        self.calls += 1;
        let model = self
            .external_model
            .expect("native environment requires frozen model");
        let mut x = if model.uses_native_noble_order() {
            world.features()
        } else {
            world.model_features()
        };
        if self.belief_root && self.root_evaluation {
            let opponent = 1 - usize::from(o.current);
            let mut context = [0.0; 7];
            for slot in 0..usize::from(o.players[opponent].reserved_count) {
                let r = o.players[opponent].reserved[slot];
                context[slot] = f32::from(!r.public);
                context[slot + 3] = f32::from(r.tier + 1) / 3.0;
                context[6] += context[slot] / 3.0;
            }
            x = super::belief::moments(&x, &context).0;
            self.belief_calls += 1;
        }
        let (policy, values) = if self.root_only && !self.root_evaluation {
            model.infer_base(&x)
        } else if model.needs_public_context() {
            if model.has_correction() {
                self.correction_calls += 1;
            }
            let opponent = 1 - usize::from(o.current);
            let mut context = [0.0; 7];
            for slot in 0..usize::from(o.players[opponent].reserved_count) {
                let r = o.players[opponent].reserved[slot];
                context[slot] = f32::from(!r.public);
                context[slot + 3] = f32::from(r.tier + 1) / 3.0;
                context[6] += context[slot] / 3.0;
            }
            model.infer_with_history(
                &x,
                &context,
                true,
                &self.history_tensor(o.current),
                &crate::public_history::native_pool(o),
            )
        } else {
            if model.has_correction() {
                self.correction_calls += 1;
            }
            model.infer(&x)
        };
        let seat = usize::from(o.viewer != o.current);
        (policy, (f64::from(values[seat]) + 1.0) / 2.0)
    }

    fn canonical_leaf_batch(&mut self, observations: &[Observation]) -> Vec<([f32; ACTIONS], f64)> {
        let Some(model) = self.external_model else {
            return observations.iter().map(|o| self.leaf(o)).collect();
        };
        if observations.iter().any(|o| o.turns >= 124) || !self.transferred {
            return observations.iter().map(|o| self.leaf(o)).collect();
        }
        assert!(!model.uses_history_bridge());
        let features: Vec<_> = observations
            .iter()
            .map(|o| super::transfer::encode(o, &mut self.rng))
            .collect();
        let contexts: Vec<_> = observations
            .iter()
            .map(super::transfer::public_context)
            .collect();
        let pools: Vec<_> = observations
            .iter()
            .map(crate::public_history::canonical_pool)
            .collect();
        let history = [[0.0; 32]; 16];
        let rows: Vec<_> = (0..observations.len())
            .map(|i| super::transfer::InferenceRow {
                features: &features[i],
                context: &contexts[i],
                native_rules: false,
                history: &history,
                pool: &pools[i],
            })
            .collect();
        self.calls += observations.len() as u64;
        model
            .infer_with_history_batch(&rows)
            .into_iter()
            .zip(observations)
            .map(|((policy, values), o)| {
                let seat = usize::from(o.viewer != o.current);
                (
                    super::transfer::policy_logits(&policy),
                    (f64::from(values[seat]) + 1.0) / 2.0,
                )
            })
            .collect()
    }

    fn native_leaf_batch(
        &mut self,
        observations: &[crate::native_environment::Observation],
    ) -> Vec<([f32; 81], f64)> {
        if observations.is_empty() {
            return Vec::new();
        }
        let Some(model) = self.external_model else {
            return observations.iter().map(|o| self.native_leaf(o)).collect();
        };
        assert!(
            !model.uses_history_bridge(),
            "batched leaf evaluation does not accept public-history models yet"
        );
        if !model.needs_public_context() || self.root_only || self.rollout_depth > 0 {
            return observations.iter().map(|o| self.native_leaf(o)).collect();
        }
        let worlds: Vec<_> = observations
            .iter()
            .map(|o| {
                o.determinize(&mut self.rng)
                    .expect("valid native observation")
            })
            .collect();
        self.calls += observations.len() as u64;
        let mut features: Vec<[f32; 392]> = worlds
            .iter()
            .map(|world| {
                if model.uses_native_noble_order() {
                    world.features()
                } else {
                    world.model_features()
                }
            })
            .collect();
        if self.belief_root && self.root_evaluation {
            for (o, x) in observations.iter().zip(&mut features) {
                let context = native_public_context(o);
                *x = super::belief::moments(x, &context).0;
                self.belief_calls += 1;
            }
        }
        let contexts: Vec<_> = observations.iter().map(native_public_context).collect();
        let histories: Vec<_> = observations
            .iter()
            .map(|o| self.history_tensor(o.current))
            .collect();
        let pools: Vec<_> = observations
            .iter()
            .map(crate::public_history::native_pool)
            .collect();
        if model.has_correction() {
            self.correction_calls += observations.len() as u64;
        }
        let rows: Vec<_> = (0..observations.len())
            .map(|i| super::transfer::InferenceRow {
                features: &features[i],
                context: &contexts[i],
                native_rules: true,
                history: &histories[i],
                pool: &pools[i],
            })
            .collect();
        model
            .infer_with_history_batch(&rows)
            .into_iter()
            .zip(observations)
            .map(|((policy, values), o)| {
                let seat = usize::from(o.viewer != o.current);
                (policy, (f64::from(values[seat]) + 1.0) / 2.0)
            })
            .collect()
    }

    #[allow(clippy::too_many_arguments)]
    fn trace_batch_environment<E: crate::environment::Environment>(
        &mut self,
        state: &mut E::State,
        depth: u32,
        nodes: &mut Vec<Node<E::Action>>,
        index: &mut HashMap<(E::Key, u64), usize>,
        chance_seed: Option<u64>,
        path: &mut Vec<(usize, usize, usize)>,
        pending_nodes: &mut [u32],
        pending_edges: &mut HashMap<(usize, usize), u32>,
        leaves: &mut Vec<PendingEnvironmentLeaf<E>>,
    ) -> Option<[f64; 2]>
    where
        Self: crate::environment::PolicyValue<E>,
    {
        if let Some(rewards) = E::rewards(state) {
            return Some(rewards);
        }
        let seat = E::current(state);
        let observation = E::observe(state, seat);
        if depth == 0 || E::turns(state) == u32::MAX {
            leaves.push(PendingLeaf {
                observation,
                legal: None,
                key: None,
                seat,
                path: path.clone(),
            });
            return None;
        }
        let actions = E::legal(state);
        let legal = actions.as_ref();
        if legal.is_empty() {
            leaves.push(PendingLeaf {
                observation,
                legal: None,
                key: None,
                seat,
                path: path.clone(),
            });
            return None;
        }
        if !E::main(state) {
            let choices =
                <Self as crate::environment::PolicyValue<E>>::choices(&observation, legal);
            let action = <Self as crate::environment::PolicyValue<E>>::rollout_action(
                self,
                &observation,
                choices.as_deref().unwrap_or(legal),
            );
            let old_turns = E::turns(state);
            let old_history = self.apply_environment::<E>(state, action, chance_seed);
            let result = self.trace_batch_environment::<E>(
                state,
                depth - u32::from(E::turns(state) != old_turns),
                nodes,
                index,
                chance_seed,
                path,
                pending_nodes,
                pending_edges,
                leaves,
            );
            self.restore_history(old_history);
            return result;
        }

        let key = (E::key(&observation, self.transferred), self.history_hash());
        let Some(&node_index) = index.get(&key) else {
            let choices =
                <Self as crate::environment::PolicyValue<E>>::choices(&observation, legal);
            leaves.push(PendingLeaf {
                observation,
                legal: Some(choices.unwrap_or_else(|| legal.to_vec())),
                key: Some(key),
                seat,
                path: path.clone(),
            });
            return None;
        };
        let edge_index = {
            let node = &nodes[node_index];
            (0..node.edges.len())
                .max_by(|&a, &b| {
                    let score = |edge_index: usize| {
                        let edge = &node.edges[edge_index];
                        let queued = f64::from(
                            pending_edges
                                .get(&(node_index, edge_index))
                                .copied()
                                .unwrap_or(0),
                        );
                        let visits = f64::from(edge.visits) + queued;
                        let q = if visits == 0.0 {
                            node.value - self.fpu_reduction
                        } else {
                            (edge.sum - queued) / visits
                        };
                        q + self.cpuct
                            * edge.prior
                            * (f64::from(node.visits + pending_nodes[node_index] + 1)).sqrt()
                            / (visits + 1.0)
                    };
                    score(a).total_cmp(&score(b))
                })
                .expect("expanded node has legal edges")
        };
        let action = nodes[node_index].edges[edge_index].action;
        debug_assert!(legal.contains(&action));
        *pending_nodes
            .get_mut(node_index)
            .expect("pending node slot") += 1;
        *pending_edges.entry((node_index, edge_index)).or_default() += 1;
        path.push((node_index, edge_index, seat));
        let old_turns = E::turns(state);
        let old_history = self.apply_environment::<E>(state, action, chance_seed);
        let result = self.trace_batch_environment::<E>(
            state,
            depth - u32::from(E::turns(state) != old_turns),
            nodes,
            index,
            chance_seed,
            path,
            pending_nodes,
            pending_edges,
            leaves,
        );
        self.restore_history(old_history);
        path.pop();
        if let Some(values) = result {
            pending_nodes[node_index] -= 1;
            let remove_edge = if let Some(queued) = pending_edges.get_mut(&(node_index, edge_index))
            {
                *queued -= 1;
                *queued == 0
            } else {
                false
            };
            if remove_edge {
                pending_edges.remove(&(node_index, edge_index));
            }
            let node = &mut nodes[node_index];
            if self.dynamic_fpu {
                node.value = (f64::from(node.visits + 1) * node.value + values[seat])
                    / f64::from(node.visits + 2);
            }
            node.visits += 1;
            node.edges[edge_index].visits += 1;
            node.edges[edge_index].sum += values[seat];
        }
        result
    }

    fn finish_batch_leaf<E: crate::environment::Environment>(
        leaf: &PendingEnvironmentLeaf<E>,
        prediction: &(<Self as crate::environment::PolicyValue<E>>::Policy, f64),
        nodes: &mut Vec<Node<E::Action>>,
        index: &mut HashMap<(E::Key, u64), usize>,
        wave_expansion_values: &mut HashMap<(E::Key, u64), f64>,
        uniform_prior: f64,
    ) -> [f64; 2]
    where
        Self: crate::environment::PolicyValue<E>,
        E::Key: Clone,
    {
        let mut value = prediction.1;
        if let (Some(legal), Some(key)) = (&leaf.legal, &leaf.key) {
            if let Some(&first_value) = wave_expansion_values.get(key) {
                // Several paths can reach one unseen information set in a
                // wave. Later rows reuse the first row's expansion value;
                // sequential search would descend after expanding the node.
                value = first_value;
            } else if let Some(&node_index) = index.get(key) {
                value = nodes[node_index].value;
            } else {
                wave_expansion_values.insert(key.clone(), value);
                let logits = prediction.0.as_ref();
                let max = legal
                    .iter()
                    .map(|&action| logits[E::action_index(action)])
                    .fold(f32::NEG_INFINITY, f32::max);
                let weights: Vec<_> = legal
                    .iter()
                    .map(|&action| f64::from((logits[E::action_index(action)] - max).exp()))
                    .collect();
                let total: f64 = weights.iter().sum();
                let node = Node {
                    edges: legal
                        .iter()
                        .zip(weights)
                        .map(|(&action, weight)| Edge {
                            action,
                            prior: (1.0 - uniform_prior) * weight / total
                                + uniform_prior / legal.len() as f64,
                            visits: 0,
                            sum: 0.0,
                        })
                        .collect(),
                    visits: 0,
                    value,
                };
                index.insert(key.clone(), nodes.len());
                nodes.push(node);
            }
        }
        let mut values = [1.0 - value; 2];
        values[leaf.seat] = value;
        values
    }

    fn select_environment_batched<E: crate::environment::Environment>(
        &mut self,
        o: &E::Observation,
        root: usize,
        nodes: &mut Vec<Node<E::Action>>,
        index: &mut HashMap<(E::Key, u64), usize>,
        worlds: &[E::State],
    ) where
        Self: crate::environment::PolicyValue<E>,
        E::Key: Clone,
    {
        let budget = self.config.iterations as usize;
        let batch_size = self.inference_batch_size.max(1);
        assert!(batch_size <= 8, "batch leaf limit is eight");
        let chance_seeds = if budget == 0 {
            Vec::new()
        } else {
            self.make_chance_seeds()
        };
        let mut completed = 0;
        while completed < budget {
            if completed > 0
                && self
                    .deadline_ms
                    .zip(self.clock)
                    .is_some_and(|(deadline, clock)| clock() >= deadline)
            {
                break;
            }
            let wave = batch_size.min(budget - completed);
            let mut leaves = Vec::with_capacity(wave);
            let mut pending_nodes = vec![0u32; nodes.len()];
            let mut pending_edges = HashMap::new();
            for offset in 0..wave {
                let simulation = completed + offset;
                let mut state = if worlds.is_empty() {
                    E::determinize(o, &mut self.rng)
                } else {
                    worlds[simulation % worlds.len()].clone()
                };
                let mut path = Vec::new();
                self.trace_batch_environment::<E>(
                    &mut state,
                    self.config.depth.max(1),
                    nodes,
                    index,
                    Self::chance_seed_for(&chance_seeds, simulation),
                    &mut path,
                    &mut pending_nodes,
                    &mut pending_edges,
                    &mut leaves,
                );
                self.simulations += 1;
            }
            let observations: Vec<_> = leaves.iter().map(|leaf| leaf.observation.clone()).collect();
            if !leaves.is_empty() {
                self.inference_batch_histogram[leaves.len()] += 1;
                let mut seen = HashSet::new();
                self.duplicate_leaf_inferences += leaves
                    .iter()
                    .filter_map(|leaf| leaf.key.as_ref())
                    .filter(|key| !seen.insert(*key))
                    .count() as u64;
            }
            let predictions =
                <Self as crate::environment::PolicyValue<E>>::evaluate_batch(self, &observations);
            assert_eq!(predictions.len(), leaves.len());
            let mut wave_expansion_values = HashMap::new();
            for (leaf, prediction) in leaves.iter().zip(&predictions) {
                let values = Self::finish_batch_leaf::<E>(
                    leaf,
                    prediction,
                    nodes,
                    index,
                    &mut wave_expansion_values,
                    self.uniform_prior,
                );
                for &(node_index, edge_index, seat) in leaf.path.iter().rev() {
                    let node = &mut nodes[node_index];
                    if self.dynamic_fpu {
                        node.value = (f64::from(node.visits + 1) * node.value + values[seat])
                            / f64::from(node.visits + 2);
                    }
                    node.visits += 1;
                    node.edges[edge_index].visits += 1;
                    node.edges[edge_index].sum += values[seat];
                }
            }
            completed += wave;
        }
        debug_assert!(root < nodes.len());
    }
    /// Run the same PUCT kernel in an explicit non-canonical environment.
    /// The caller supplies only a public observation and its legal action set.
    pub fn select_environment<E: crate::environment::Environment>(
        &mut self,
        o: &E::Observation,
        legal: &[E::Action],
    ) -> E::Action
    where
        Self: crate::environment::PolicyValue<E>,
        E::Key: Clone,
    {
        assert!(!legal.is_empty());
        if legal.len() == 1 {
            return legal[0];
        }
        let choices = <Self as crate::environment::PolicyValue<E>>::choices(o, legal);
        let mut nodes =
            vec![self.expand_root_environment::<E>(o, choices.as_deref().unwrap_or(legal))];
        let mut index =
            HashMap::from([((E::key(o, self.transferred), self.history_hash()), 0usize)]);
        let worlds: Vec<_> = (0..self.world_pool)
            .map(|_| E::determinize(o, &mut self.rng))
            .collect();
        if self.gumbel {
            let selected = self.gumbel_root::<E>(o, 0, &mut nodes, &mut index, &worlds);
            return nodes[0].edges[selected].action;
        }
        let batch_search = self.inference_batch_size > 1;
        #[cfg(test)]
        let batch_search = batch_search || self.force_batch_search;
        if batch_search {
            if self.inference_batch_size > 1 {
                assert!(
                    self.external_model
                        .is_some_and(|model| !model.uses_history_bridge()),
                    "batched PUCT currently requires a frozen no-history external model"
                );
                assert!(
                    !self.root_only && self.rollout_depth == 0,
                    "batched PUCT does not support root_only or rollout_depth"
                );
            }
            self.select_environment_batched::<E>(o, 0, &mut nodes, &mut index, &worlds);
            return nodes[0]
                .edges
                .iter()
                .max_by(|a, b| {
                    a.visits
                        .cmp(&b.visits)
                        .then_with(|| a.prior.total_cmp(&b.prior))
                })
                .unwrap()
                .action;
        }
        let chance_seeds = if self.config.iterations == 0 {
            Vec::new()
        } else {
            self.make_chance_seeds()
        };
        for simulation in 0..self.config.iterations {
            if simulation > 0
                && self
                    .deadline_ms
                    .zip(self.clock)
                    .is_some_and(|(deadline, clock)| clock() >= deadline)
            {
                break;
            }
            let mut state = if worlds.is_empty() {
                E::determinize(o, &mut self.rng)
            } else {
                worlds[simulation as usize % worlds.len()].clone()
            };
            self.simulate_environment::<E>(
                &mut state,
                self.config.depth.max(1),
                &mut nodes,
                &mut index,
                Self::chance_seed_for(&chance_seeds, simulation as usize),
            );
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
fn native_public_context(o: &crate::native_environment::Observation) -> [f32; 7] {
    let opponent = 1 - usize::from(o.current);
    let mut context = [0.0; 7];
    for slot in 0..usize::from(o.players[opponent].reserved_count) {
        let reservation = o.players[opponent].reserved[slot];
        context[slot] = f32::from(!reservation.public);
        context[slot + 3] = f32::from(reservation.tier + 1) / 3.0;
        context[6] += context[slot] / 3.0;
    }
    context
}

pub(super) fn key(o: &Observation) -> [u8; 192] {
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
    debug_assert_eq!(offset, 187);
    bytes
}

impl Agent for NeuralAgent {
    fn set_inference_batch_size(&mut self, size: usize) {
        assert!(matches!(size, 1 | 8));
        self.inference_batch_size = size;
    }
    fn set_search_deadline(&mut self, deadline_ms: Option<f64>) {
        self.deadline_ms = deadline_ms;
    }

    fn wants_public_history(&self) -> bool {
        self.external_model.is_some_and(|m| m.uses_history_bridge())
    }
    fn observe_public_action(&mut self, before: &Observation, action: Action, after: &Observation) {
        let event = if self
            .external_model
            .is_some_and(|m| m.uses_full_public_history())
        {
            crate::public_history::canonical_v2(before, action, after)
        } else {
            crate::public_history::canonical(before, action, after)
        };
        self.observe_event(event);
    }
    fn policy_target(&self) -> Option<[f32; ACTIONS]> {
        self.root_policy
    }
    fn value_target(&self) -> Option<f32> {
        self.root_value
    }
    fn work_counts(&self) -> (u64, u64) {
        (self.simulations, self.calls)
    }
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        self.root_policy = None;
        self.root_value = None;
        self.search_targets = None;
        if o.count != 2
            || o.phase != Phase::Main
            || legal.len() == 1
            || o.turns == u32::MAX
            || (self.transferred && o.turns >= 124)
        {
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
        let (mut nodes, mut index) = if self.persistent && self.cached_nodes.len() <= 32_768 {
            (
                std::mem::take(&mut self.cached_nodes),
                std::mem::take(&mut self.cached_index),
            )
        } else {
            self.cached_nodes.clear();
            self.cached_index.clear();
            (Vec::new(), HashMap::new())
        };
        let root = if let Some(&root) = index.get(&self.tree_key(o)) {
            // The real history can add a purchase-only cycle escape. Cached
            // edges must obey the current legal root restrictions as well.
            nodes[root]
                .edges
                .retain(|edge| choices.contains(&edge.action));
            nodes[root].visits = nodes[root].edges.iter().map(|edge| edge.visits).sum();
            if nodes[root].edges.is_empty() {
                nodes[root] =
                    self.expand_root_environment::<crate::environment::Canonical>(o, &choices);
            }
            root
        } else {
            let root = nodes.len();
            nodes.push(self.expand_root_environment::<crate::environment::Canonical>(o, &choices));
            index.insert(self.tree_key(o), root);
            root
        };
        #[cfg(not(target_arch = "wasm32"))]
        let start = std::time::Instant::now();
        let worlds: Vec<_> = (0..self.world_pool)
            .map(|_| o.determinize(&mut self.rng).expect("valid observation"))
            .collect();
        let gumbel_selected = if self.gumbel {
            Some(self.gumbel_root::<crate::environment::Canonical>(
                o, root, &mut nodes, &mut index, &worlds,
            ))
        } else {
            None
        };
        if !self.gumbel && self.inference_batch_size > 1 {
            let chance_universes = self.chance_universes;
            self.chance_universes = 0;
            self.select_environment_batched::<crate::environment::Canonical>(
                o, root, &mut nodes, &mut index, &worlds,
            );
            self.chance_universes = chance_universes;
        } else if !self.gumbel {
            for simulation in 0..self.config.iterations {
                #[cfg(target_arch = "wasm32")]
                let time_budget_exhausted = false;
                #[cfg(not(target_arch = "wasm32"))]
                let time_budget_exhausted = self
                    .config
                    .time_budget
                    .is_some_and(|t| start.elapsed() >= t);
                let deadline_exhausted = self
                    .deadline_ms
                    .zip(self.clock)
                    .is_some_and(|(deadline, clock)| clock() >= deadline);
                if simulation > 0 && (time_budget_exhausted || deadline_exhausted) {
                    break;
                }
                let mut state = if worlds.is_empty() {
                    o.determinize(&mut self.rng).expect("valid observation")
                } else {
                    worlds[simulation as usize % worlds.len()].clone()
                };
                self.simulate_environment::<crate::environment::Canonical>(
                    &mut state,
                    self.config.depth.max(1),
                    &mut nodes,
                    &mut index,
                    None,
                );
                self.simulations += 1;
            }
        }
        let selected = if let Some(i) = gumbel_selected {
            &nodes[root].edges[i]
        } else {
            nodes[root]
                .edges
                .iter()
                .max_by(|a, b| {
                    a.visits
                        .cmp(&b.visits)
                        .then_with(|| a.prior.total_cmp(&b.prior))
                })
                .unwrap()
        };
        let visits: u32 = nodes[root].edges.iter().map(|e| e.visits).sum();
        if self.capture_search_targets && visits > 0 {
            let mut targets = SearchTargets {
                visits: [0; ACTIONS],
                q: [None; ACTIONS],
                root_value: (nodes[root].edges.iter().map(|e| e.sum).sum::<f64>()
                    / f64::from(visits)) as f32,
                network_value: nodes[root].value as f32,
            };
            for edge in &nodes[root].edges {
                let i = action_index(edge.action).expect("Main action");
                targets.visits[i] = edge.visits;
                if edge.visits > 0 {
                    targets.q[i] = Some((edge.sum / f64::from(edge.visits)) as f32);
                }
            }
            self.search_targets = Some(targets);
        }
        if visits > 0 {
            let mut policy = [0.0; ACTIONS];
            let improved = if self.gumbel {
                Some(nodes[root].improved_policy(self.gumbel_cvisit, self.gumbel_cscale))
            } else {
                None
            };
            for (i, edge) in nodes[root].edges.iter().enumerate() {
                policy[action_index(edge.action).unwrap()] = improved
                    .as_ref()
                    .map_or(edge.visits as f32 / visits as f32, |p| p[i] as f32);
            }
            self.root_policy = Some(policy);
            self.root_value = Some((selected.sum / f64::from(selected.visits)) as f32);
        }
        let action = selected.action;
        if self.persistent {
            self.cached_nodes = nodes;
            self.cached_index = index;
        }
        action
    }
}

pub fn value(o: &Observation) -> f64 {
    let (_, v) = model().infer(&features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

#[cfg(not(all(feature = "external-model-only", target_arch = "wasm32")))]
fn model_v2() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e26.bin")))
}
#[cfg(all(feature = "external-model-only", target_arch = "wasm32"))]
fn model_v2() -> &'static Model {
    panic!("embedded neural checkpoints are disabled in this build")
}
pub fn value_v2(o: &Observation) -> f64 {
    let (_, v) = model_v2().infer(&super::neural::enhanced_features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

#[cfg(not(all(feature = "external-model-only", target_arch = "wasm32")))]
fn model_transferred() -> &'static super::transfer::Model {
    static MODEL: OnceLock<super::transfer::Model> = OnceLock::new();
    MODEL.get_or_init(|| super::transfer::Model::from_bytes(include_bytes!("models/e30.bin")))
}
#[cfg(all(feature = "external-model-only", target_arch = "wasm32"))]
fn model_transferred() -> &'static super::transfer::Model {
    panic!("embedded neural checkpoints are disabled in this build")
}

#[cfg(not(all(feature = "external-model-only", target_arch = "wasm32")))]
fn model_self_play() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e28.bin")))
}
#[cfg(all(feature = "external-model-only", target_arch = "wasm32"))]
fn model_self_play() -> &'static Model {
    panic!("embedded neural checkpoints are disabled in this build")
}

#[cfg(not(all(feature = "external-model-only", target_arch = "wasm32")))]
fn model_expert() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e27.bin")))
}
#[cfg(all(feature = "external-model-only", target_arch = "wasm32"))]
fn model_expert() -> &'static Model {
    panic!("embedded neural checkpoints are disabled in this build")
}
pub fn value_expert(o: &Observation) -> f64 {
    let (_, v) = model_expert().infer(&super::neural::enhanced_features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

/// Immutable checkpoint handles are cached once per process, outside search.
/// The loop records file hashes and does not replace a running process's model.
pub fn flywheel_model(candidate: bool) -> &'static super::transfer::Model {
    static BEST: OnceLock<super::transfer::Model> = OnceLock::new();
    static CANDIDATE: OnceLock<super::transfer::Model> = OnceLock::new();
    let (cache, variable) = if candidate {
        (&CANDIDATE, "SPLENDOR_CANDIDATE_MODEL")
    } else {
        (&BEST, "SPLENDOR_BEST_MODEL")
    };
    cache.get_or_init(|| {
        let path = std::env::var(variable).expect("flywheel checkpoint path is required");
        let bytes = std::fs::read(path).expect("read flywheel checkpoint");
        super::transfer::Model::from_bytes(&bytes)
    })
}

impl crate::environment::PolicyValue<crate::environment::Canonical> for NeuralAgent {
    type Policy = [f32; 67];
    fn evaluate(&mut self, o: &Observation) -> (Self::Policy, f64) {
        self.leaf(o)
    }
    fn evaluate_batch(&mut self, observations: &[Observation]) -> Vec<(Self::Policy, f64)> {
        self.canonical_leaf_batch(observations)
    }
    fn choices(o: &Observation, legal: &[Action]) -> Option<Vec<Action>> {
        safe_choices(o, legal)
    }
    fn rollout_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        best(o, legal, true)
    }
}
impl crate::environment::PolicyValue<crate::environment::AlphaZeroNative> for NeuralAgent {
    type Policy = [f32; 81];
    fn evaluate(&mut self, o: &crate::native_environment::Observation) -> (Self::Policy, f64) {
        self.native_leaf(o)
    }
    fn evaluate_batch(
        &mut self,
        observations: &[crate::native_environment::Observation],
    ) -> Vec<(Self::Policy, f64)> {
        self.native_leaf_batch(observations)
    }
    fn choices(_: &crate::native_environment::Observation, _: &[u8]) -> Option<Vec<u8>> {
        None
    }
    fn rollout_action(&mut self, o: &crate::native_environment::Observation, legal: &[u8]) -> u8 {
        let (policy, _) = self.native_leaf(o);
        legal
            .iter()
            .copied()
            .max_by(|&a, &b| policy[a as usize].total_cmp(&policy[b as usize]))
            .unwrap()
    }
}

#[cfg(feature = "information-benchmark")]
impl crate::environment::PolicyValue<crate::privileged_environment::PrivilegedNative>
    for NeuralAgent
{
    type Policy = [f32; 81];
    fn evaluate(&mut self, o: &crate::privileged_environment::Observation) -> (Self::Policy, f64) {
        self.native_world_leaf(
            &o.observation,
            &o.state().expect("validated privileged partition"),
        )
    }
    fn choices(_: &crate::privileged_environment::Observation, _: &[u8]) -> Option<Vec<u8>> {
        None
    }
    fn rollout_action(
        &mut self,
        o: &crate::privileged_environment::Observation,
        legal: &[u8],
    ) -> u8 {
        let (policy, _) = <Self as crate::environment::PolicyValue<
            crate::privileged_environment::PrivilegedNative,
        >>::evaluate(self, o);
        legal
            .iter()
            .copied()
            .max_by(|&a, &b| policy[a as usize].total_cmp(&policy[b as usize]))
            .unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::environment::Environment;
    #[test]
    fn runtime_deadline_stops_search_and_can_be_cleared() {
        let state = GameState::new(2, 91337).unwrap();
        let o = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        for gumbel in [false, true] {
            let config = SearchConfig {
                iterations: 32,
                depth: 4,
                ..Default::default()
            };
            let mut agent = NeuralAgent::new(77, config);
            agent.gumbel = gumbel;
            agent.clock = Some(|| 10.0);
            agent.set_search_deadline(Some(9.0));
            assert!(legal.contains(&agent.select_action(&o, &legal)));
            assert_eq!(agent.work_counts().0, 1);
            agent.set_search_deadline(None);
            assert!(legal.contains(&agent.select_action(&o, &legal)));
            assert_eq!(agent.work_counts().0, 33);
        }
    }

    #[test]
    fn chance_universe_seeds_are_policy_rng_derived_and_zero_preserves_rng() {
        let mut disabled = NeuralAgent::new(818, SearchConfig::default());
        let mut control = NeuralAgent::new(818, SearchConfig::default());
        assert!(disabled.make_chance_seeds().is_empty());
        assert_eq!(disabled.rng.next_u64(), control.rng.next_u64());

        let mut first = NeuralAgent::new(818, SearchConfig::default());
        let mut second = NeuralAgent::new(818, SearchConfig::default());
        first.chance_universes = 3;
        second.chance_universes = 3;
        let seeds = first.make_chance_seeds();
        assert_eq!(seeds, second.make_chance_seeds());
        assert_eq!(seeds.len(), 3);
        assert!(seeds.iter().all(|seed| *seed != 0));
    }

    #[test]
    fn diagnostic_targets_preserve_search_and_mask_unvisited_edges() {
        let state = GameState::new(2, 42).unwrap();
        let o = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        for gumbel in [false, true] {
            let config = SearchConfig {
                iterations: 32,
                depth: 4,
                ..Default::default()
            };
            let mut original = NeuralAgent::new(77, config.clone());
            let mut captured = NeuralAgent::new(77, config);
            original.gumbel = gumbel;
            captured.gumbel = gumbel;
            captured.capture_search_targets = true;
            assert_eq!(
                original.select_action(&o, &legal),
                captured.select_action(&o, &legal)
            );
            assert_eq!(original.work_counts(), captured.work_counts());
            assert_eq!(original.policy_target(), captured.policy_target());
            assert_eq!(original.value_target(), captured.value_target());
            let t = captured.search_targets.as_ref().unwrap();
            let count: u32 = t.visits.iter().sum();
            assert_eq!(count, 32);
            let mut sum = 0.0f64;
            for i in 0..ACTIONS {
                assert_eq!(t.q[i].is_some(), t.visits[i] > 0);
                if let Some(q) = t.q[i] {
                    assert!((0.0..=1.0).contains(&q));
                    assert!(legal.iter().any(|&a| action_index(a) == Some(i)));
                    sum += f64::from(q) * f64::from(t.visits[i]);
                }
            }
            assert!((sum / f64::from(count) - f64::from(t.root_value)).abs() < 1e-6);
            assert!((0.0..=1.0).contains(&t.network_value));
            captured.select_action(&o, &legal[..1]);
            assert!(captured.search_targets.is_none());
        }
    }

    #[test]
    fn forced_batch_size_one_matches_sequential_environment_search() {
        let state = GameState::new(2, 77123).unwrap();
        let observation = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let config = SearchConfig {
            iterations: 24,
            depth: 8,
            ..Default::default()
        };
        let mut scalar = NeuralAgent::new(902, config.clone());
        let mut queued = NeuralAgent::new(902, config);
        queued.force_batch_search = true;
        scalar.world_pool = 3;
        queued.world_pool = 3;
        scalar.chance_universes = 3;
        queued.chance_universes = 3;
        let expected =
            scalar.select_environment::<crate::environment::Canonical>(&observation, &legal);
        let actual =
            queued.select_environment::<crate::environment::Canonical>(&observation, &legal);
        assert_eq!(actual, expected);
        assert_eq!(queued.work_counts(), scalar.work_counts());
        assert_eq!(queued.rng.next_u64(), scalar.rng.next_u64());
    }

    #[test]
    fn expired_batch_deadline_finishes_one_wave() {
        let state = GameState::new(2, 77125).unwrap();
        let observation = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let mut agent = NeuralAgent::new(
            904,
            SearchConfig {
                iterations: 17,
                depth: 8,
                ..Default::default()
            },
        );
        agent.clock = Some(|| 100.0);
        agent.set_search_deadline(Some(99.0));
        let root =
            agent.expand_root_environment::<crate::environment::Canonical>(&observation, &legal);
        let mut nodes = vec![root];
        let mut index = HashMap::from([(
            (
                crate::environment::Canonical::key(&observation, false),
                agent.history_hash(),
            ),
            0usize,
        )]);
        agent.inference_batch_size = 8;
        agent.select_environment_batched::<crate::environment::Canonical>(
            &observation,
            0,
            &mut nodes,
            &mut index,
            &[],
        );
        assert_eq!(agent.simulations, 8);
        assert_eq!(nodes[0].visits, 8);
        let mut scalar = NeuralAgent::new(
            904,
            SearchConfig {
                iterations: 17,
                depth: 8,
                ..Default::default()
            },
        );
        scalar.clock = Some(|| 100.0);
        scalar.set_search_deadline(Some(99.0));
        let action =
            scalar.select_environment::<crate::environment::Canonical>(&observation, &legal);
        assert!(legal.contains(&action));
        assert_eq!(scalar.simulations, 1);
    }

    #[test]
    fn batched_leaf_waves_consume_exact_simulation_budget() {
        let state = GameState::new(2, 77124).unwrap();
        let observation = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let mut agent = NeuralAgent::new(
            903,
            SearchConfig {
                iterations: 17,
                depth: 8,
                ..Default::default()
            },
        );
        let root =
            agent.expand_root_environment::<crate::environment::Canonical>(&observation, &legal);
        let mut nodes = vec![root];
        let mut index = HashMap::from([(
            (
                crate::environment::Canonical::key(&observation, false),
                agent.history_hash(),
            ),
            0usize,
        )]);
        let worlds: Vec<_> = (0..3)
            .map(|_| crate::environment::Canonical::determinize(&observation, &mut agent.rng))
            .collect();
        agent.world_pool = 3;
        agent.chance_universes = 3;
        agent.inference_batch_size = 8;
        agent.select_environment_batched::<crate::environment::Canonical>(
            &observation,
            0,
            &mut nodes,
            &mut index,
            &worlds,
        );
        assert_eq!(agent.simulations, 17);
        assert_eq!(nodes[0].visits, 17);
        assert_eq!(
            nodes[0].edges.iter().map(|edge| edge.visits).sum::<u32>(),
            17
        );
    }

    #[test]
    fn duplicate_unexpanded_leaves_reuse_first_wave_value() {
        let state = GameState::new(2, 77125).unwrap();
        let observation = state.observe(0);
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let key = (crate::environment::Canonical::key(&observation, false), 0);
        let leaf = PendingLeaf {
            observation,
            legal: Some(legal.iter().copied().collect()),
            key: Some(key),
            seat: 0,
            path: Vec::new(),
        };
        let mut nodes = Vec::new();
        let mut index = HashMap::new();
        let mut frozen = HashMap::new();
        let policy = [0.0; ACTIONS];
        let first = NeuralAgent::finish_batch_leaf::<crate::environment::Canonical>(
            &leaf,
            &(policy, 0.2),
            &mut nodes,
            &mut index,
            &mut frozen,
            0.0,
        );
        let second = NeuralAgent::finish_batch_leaf::<crate::environment::Canonical>(
            &leaf,
            &(policy, 0.8),
            &mut nodes,
            &mut index,
            &mut frozen,
            0.0,
        );
        assert_eq!(nodes.len(), 1);
        assert_eq!(first, second);
        assert_eq!(nodes[0].value, 0.2);
    }
    use splendor_core::{ActionSet, GameState};
    #[test]
    fn completed_q_policy_and_mixed_value() {
        let mut node = Node {
            edges: vec![
                Edge {
                    action: Action::BuyVisible(0),
                    prior: 0.6,
                    visits: 2,
                    sum: 1.6,
                },
                Edge {
                    action: Action::BuyVisible(1),
                    prior: 0.3,
                    visits: 1,
                    sum: 0.2,
                },
                Edge {
                    action: Action::BuyVisible(2),
                    prior: 0.1,
                    visits: 0,
                    sum: 0.0,
                },
            ],
            visits: 3,
            value: 0.4,
        };
        let weighted = (0.6 * 0.8 + 0.3 * 0.2) / 0.9;
        assert!((node.mixed_value() - (0.4 + 3.0 * weighted) / 4.0).abs() < 1e-12);
        let p = node.improved_policy(50.0, 0.1);
        assert!((p[..3].iter().sum::<f64>() - 1.0).abs() < 1e-12);
        assert!(p[2] > 0.0 && p[0] > p[1]);
        for e in &mut node.edges {
            e.visits = 1;
            e.sum = 0.5;
        }
        let p = node.improved_policy(50.0, 0.1);
        for (i, e) in node.edges.iter().enumerate() {
            assert!((p[i] - e.prior).abs() < 1e-12);
        }
        node.edges[0].sum = 0.9;
        node.edges[1].sum = 0.1;
        node.edges[2].sum = 0.4;
        let p = node.improved_policy(50.0, 0.1);
        let original: f64 = node.edges.iter().map(|e| e.prior * e.sum).sum();
        let improved: f64 = node
            .edges
            .iter()
            .enumerate()
            .map(|(i, e)| p[i] * e.sum)
            .sum();
        assert!(improved >= original);
    }
    #[test]
    fn gumbel_exact_budget_legal_targets_and_seed_identity() {
        for budget in [0, 1, 2, 3, 7, 8, 16, 128] {
            let state = GameState::new(2, 4290000000).unwrap();
            let mut legal = ActionSet::new();
            state.legal_actions(&mut legal);
            let o = state.observe(0);
            let config = SearchConfig {
                iterations: budget,
                depth: 4,
                ..Default::default()
            };
            let mut agents = std::array::from_fn::<_, 2, _>(|_| {
                let mut a = NeuralAgent::new(72, config.clone());
                a.transferred = true;
                a.gumbel = true;
                a.gumbel_noise = 1.0;
                a.world_pool = 3;
                a.uniform_prior = 0.0;
                a
            });
            let actions = agents.each_mut().map(|a| a.select_action(&o, &legal));
            assert_eq!(actions[0], actions[1]);
            assert!(legal.contains(&actions[0]));
            assert_eq!(agents[0].simulations, u64::from(budget));
            assert_eq!(agents[0].root_policy, agents[1].root_policy);
            if budget > 0 {
                let p = agents[0].root_policy.unwrap();
                assert!(p.iter().all(|v| v.is_finite() && *v >= 0.0));
                assert!((p.iter().sum::<f32>() - 1.0).abs() < 1e-5);
                for (i, v) in p.iter().enumerate() {
                    if *v > 0.0 {
                        assert!(legal.iter().any(|a| action_index(*a) == Some(i)));
                    }
                }
                let v = agents[0].root_value.unwrap();
                assert!(v.is_finite() && (0.0..=1.0).contains(&v));
            }
        }
    }
    #[test]
    fn correction_runs_once_at_root_and_base_runs_at_leaves() {
        let model = Box::leak(Box::new(super::super::transfer::Model::from_bytes(
            include_bytes!("../../../research/e63/model/model.bin"),
        )));
        let state = GameState::new(2, 4500000000).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let o = state.observe(0);
        for gumbel in [false, true] {
            for root_only in [false, true] {
                let mut a = NeuralAgent::new(
                    77,
                    SearchConfig {
                        iterations: 16,
                        depth: 4,
                        ..Default::default()
                    },
                );
                a.transferred = true;
                a.external_model = Some(model);
                a.gumbel = gumbel;
                a.root_only = root_only;
                a.world_pool = 3;
                let action = a.select_action(&o, &legal);
                assert!(legal.contains(&action));
                assert_eq!(a.simulations, 16);
                if root_only {
                    assert_eq!(a.correction_calls, 1);
                    assert!(a.calls > 1);
                } else {
                    assert_eq!(a.correction_calls, a.calls);
                    assert!(a.correction_calls > 1);
                }
            }
        }
    }
    #[cfg(feature = "information-benchmark")]
    #[test]
    fn privileged_native_leaf_uses_exact_partition_at_every_actor() {
        use crate::environment::{Environment, PolicyValue};
        use crate::native_environment::{Observation as NativeObservation, Player};
        use crate::privileged_environment::PrivilegedNative;
        let c = GameState::new(2, 96).unwrap().observe(0);
        let ids: Vec<_> = (0..10).filter(|id| c.nobles & (1 << id) != 0).collect();
        let native = NativeObservation {
            viewer: 0,
            current: 0,
            turns: 0,
            bank: c.bank,
            market: c.market,
            remaining: c.remaining,
            noble_ids: [ids[2], ids[0], ids[1]],
            nobles: 7,
            players: [Player::default(), Player::default()],
        };
        let model = Box::leak(Box::new(crate::transfer::Model::from_bytes(
            include_bytes!("../../../research/e81/model/model.bin"),
        )));
        let mut world = native.determinize(&mut Rng::new(123)).unwrap();
        let mut agent = NeuralAgent::new(987, SearchConfig::default());
        agent.external_model = Some(model);
        // Both actors have blind reservations; simulated chance changes the
        // partition. Every evaluation must use exactly that simulated state.
        for action in [24, 25, 80, 80] {
            world.apply(action, &mut Rng::new(456), None).unwrap();
            let o = PrivilegedNative::observe(&world, world.current_player());
            assert_eq!(
                PrivilegedNative::determinize(&o, &mut Rng::new(1)).features(),
                world.features()
            );
            assert_eq!(
                PrivilegedNative::determinize(&o, &mut Rng::new(2)).features(),
                world.features()
            );
            let (p, v) = model.infer(&world.model_features());
            let expected = (p, (f64::from(v[0]) + 1.0) / 2.0);
            assert_eq!(
                <NeuralAgent as PolicyValue<PrivilegedNative>>::evaluate(&mut agent, &o),
                expected
            );
            assert_eq!(agent.native_world_leaf(&o.observation, &world), expected);
        }
    }
    #[test]
    fn public_native_leaf_preserves_teacher_noble_order() {
        use crate::native_environment::{Observation as NativeObservation, Player};
        let original = include_bytes!("../../../research/e81/model/model.bin");
        let mut bytes = b"SPPUB751".to_vec();
        bytes.extend(1u32.to_le_bytes());
        for row in original[..56 * 56 * 4].as_chunks::<{ 56 * 4 }>().0 {
            bytes.extend(row);
            bytes.extend([0; 19 * 4]);
        }
        bytes.extend(&original[56 * 56 * 4..]);
        let model = Box::leak(Box::new(crate::transfer::Model::from_bytes(&bytes)));
        assert!(model.uses_native_noble_order());
        let canonical = GameState::new(2, 95).unwrap().observe(0);
        let ids: Vec<_> = (0..10)
            .filter(|id| canonical.nobles & (1 << id) != 0)
            .collect();
        let native = NativeObservation {
            viewer: 0,
            current: 0,
            turns: 0,
            bank: canonical.bank,
            market: canonical.market,
            remaining: canonical.remaining,
            noble_ids: [ids[2], ids[0], ids[1]],
            nobles: 7,
            players: [Player::default(), Player::default()],
        };
        let world = native.determinize(&mut Rng::new(99)).unwrap();
        assert_ne!(world.features(), world.model_features());
        let (policy, value) = model.infer_with_profile(&world.features(), &[0.0; 7], true);
        let mut agent = NeuralAgent::new(99, SearchConfig::default());
        agent.external_model = Some(model);
        assert_eq!(
            agent.native_leaf(&native),
            (policy, (f64::from(value[0]) + 1.0) / 2.0)
        );
        let mut canonical_agent = NeuralAgent::new(
            99,
            SearchConfig {
                iterations: 16,
                depth: 4,
                ..Default::default()
            },
        );
        canonical_agent.transferred = true;
        canonical_agent.external_model = Some(model);
        canonical_agent.gumbel = true;
        canonical_agent.world_pool = 3;
        let state = GameState::new(2, 95).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        assert!(legal.contains(&canonical_agent.select_action(&canonical, &legal)));
        assert_eq!(canonical_agent.simulations, 16);
        assert!(canonical_agent.calls > 1);
    }
    #[test]
    fn learned_public_models_use_only_root_correction() {
        for bytes in [
            include_bytes!("../../../research/e86/initial/model.bin").as_slice(),
            include_bytes!("../../../research/e88/initial/probe.bin").as_slice(),
        ] {
            let model = Box::leak(Box::new(super::super::transfer::Model::from_bytes(bytes)));
            let base = super::super::transfer::Model::from_bytes(include_bytes!(
                "../../../research/e81/model/model.bin"
            ));
            let mut state = GameState::new(2, 4670000000).unwrap();
            state
                .apply_action(splendor_core::Action::ReserveDeck(0))
                .unwrap();
            let mut legal = ActionSet::new();
            state.legal_actions(&mut legal);
            let o = state.observe(state.current_player());
            let context = super::super::transfer::public_context(&o);
            assert!(context[6] > 0.0);
            let mut expected = None;
            for sample in 0..8 {
                let x = super::super::transfer::encode(&o, &mut Rng::new(sample));
                assert_eq!(model.infer_base(&x), base.infer(&x));
                let prediction = model.infer_with_context(&x, &context);
                if let Some(old) = expected {
                    assert_eq!(prediction, old);
                }
                expected = Some(prediction);
            }
            let mut a = NeuralAgent::new(
                86,
                SearchConfig {
                    iterations: 16,
                    depth: 4,
                    ..Default::default()
                },
            );
            a.transferred = true;
            a.external_model = Some(model);
            a.gumbel = true;
            a.root_only = true;
            a.world_pool = 3;
            assert!(legal.contains(&a.select_action(&o, &legal)));
            assert_eq!(a.simulations, 16);
            assert_eq!(a.correction_calls, 1);
            assert!(a.calls > 1);
        }
    }
    #[test]
    fn belief_transform_runs_only_at_the_root() {
        let model = Box::leak(Box::new(super::super::transfer::Model::from_bytes(
            include_bytes!("../../../research/e81/model/model.bin"),
        )));
        let state = GameState::new(2, 4630000000).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let o = state.observe(0);
        let mut a = NeuralAgent::new(
            85,
            SearchConfig {
                iterations: 16,
                depth: 4,
                ..Default::default()
            },
        );
        a.transferred = true;
        a.external_model = Some(model);
        a.gumbel = true;
        a.belief_root = true;
        a.world_pool = 3;
        assert!(legal.contains(&a.select_action(&o, &legal)));
        assert_eq!(a.simulations, 16);
        assert_eq!(a.belief_calls, 1);
        assert!(a.calls > 1);
    }
    #[test]
    fn transferred_keys_include_the_network_turn_input() {
        let state = GameState::new(2, 620000007).unwrap();
        let o = state.observe(0);
        let mut later = o.clone();
        later.turns = 2;
        let mut agent = NeuralAgent::new(1, SearchConfig::default());
        assert_eq!(agent.tree_key(&o), agent.tree_key(&later));
        agent.transferred = true;
        assert_ne!(agent.tree_key(&o), agent.tree_key(&later));
    }
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
    fn persistent_tree_is_observation_only_and_keeps_actions_legal() {
        let mut state = GameState::new(2, 380000007).unwrap();
        let config = SearchConfig {
            iterations: 8,
            depth: 8,
            ..Default::default()
        };
        let mut a = NeuralAgent::new(7, config.clone());
        let mut b = NeuralAgent::new(7, config);
        a.persistent = true;
        b.persistent = true;
        a.enhanced = true;
        b.enhanced = true;
        let mut rng = Rng::new(379);
        let mut legal = ActionSet::new();
        for _ in 0..100 {
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let observation = state.observe(state.current_player());
            let other = observation
                .determinize(&mut rng)
                .unwrap()
                .observe(state.current_player());
            let action = a.select_action(&observation, &legal);
            assert_eq!(action, b.select_action(&other, &legal));
            assert_eq!(a.policy_target(), b.policy_target());
            assert!(legal.contains(&action));
            if observation.phase == Phase::Main && legal.len() > 1 {
                assert!(!a.cached_nodes.is_empty());
                // Query the same information state again to exercise cache reuse.
                let reused = a.select_action(&observation, &legal);
                assert_eq!(reused, b.select_action(&other, &legal));
                assert!(legal.contains(&reused));
            }
            state.apply_action(action).unwrap();
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
            assert_eq!(a.policy_target(), b.policy_target());
            assert_eq!(a.value_target(), b.value_target());
            if let Some(policy) = a.policy_target() {
                assert!((policy.iter().sum::<f32>() - 1.0).abs() < 1e-6);
                for (i, weight) in policy.iter().enumerate() {
                    assert!((0.0..=1.0).contains(weight));
                    if *weight > 0.0 {
                        assert!(legal.iter().any(|&action| action_index(action) == Some(i)));
                    }
                }
                assert!((0.0..=1.0).contains(&a.value_target().unwrap()));
            }
            assert!(legal.contains(&action));
            s.apply_action(legal[rng.index(legal.len())]).unwrap();
        }
    }
}

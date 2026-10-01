//! Observation-keyed information-set PUCT. New determinization for each simulation.
use super::{
    Agent, SearchConfig, best,
    neural::{ACTIONS, INPUTS, action_index, features},
    safe_choices,
};
use splendor_core::{Action, Observation, Phase, Rng};
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
    fn completed_scores(&self) -> [f64; SEARCH_ACTION_CAPACITY] {
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
        let scale = (50.0 + f64::from(max_visits)) * 0.1 / (hi - lo).max(1e-8);
        for (i, e) in self.edges.iter().enumerate() {
            scores[i] = e.prior.max(f64::MIN_POSITIVE).ln() + scale * (scores[i] - lo);
        }
        scores
    }
    fn improved_policy(&self) -> [f64; SEARCH_ACTION_CAPACITY] {
        let mut policy = self.completed_scores();
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

pub struct NeuralAgent {
    rng: Rng,
    config: SearchConfig,
    history: VecDeque<Observation>,
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
    pub rollout_depth: u32,
    pub persistent: bool,
    /// Gumbel planning with completed-Q policy targets (E72).
    pub root_only: bool,
    root_evaluation: bool,
    pub correction_calls: u64,
    pub gumbel: bool,
    pub gumbel_noise: f64,
    cached_nodes: Vec<Node>,
    cached_index: HashMap<[u8; 192], usize>,
    root_policy: Option<[f32; ACTIONS]>,
    root_value: Option<f32>,
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
            expert: false,
            self_play: false,
            transferred: false,
            external_model: None,
            cpuct: 1.5,
            fpu_reduction: 0.0,
            uniform_prior: 0.02,
            dynamic_fpu: false,
            world_pool: 0,
            rollout_depth: 0,
            persistent: false,
            root_only: false,
            root_evaluation: false,
            correction_calls: 0,
            gumbel: false,
            gumbel_noise: 0.0,
            cached_nodes: Vec::new(),
            cached_index: HashMap::new(),
            root_policy: None,
            root_value: None,
        }
    }
    fn tree_key(&self, o: &Observation) -> [u8; 192] {
        let mut bytes = key(o);
        if self.transferred {
            // Unlike E26, the transferred network has a turn-counter input.
            bytes[188..192].copy_from_slice(&o.turns.to_le_bytes());
        }
        bytes
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
            let x = super::transfer::encode(o, &mut self.rng);
            let model = self.external_model.unwrap_or_else(model_transferred);
            let (policy, values) = if model.needs_public_context() {
                model.infer_with_context(&x, &super::transfer::public_context(o))
            } else if self.root_only && !self.root_evaluation {
                model.infer_base(&x)
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
            E::apply(
                &mut s,
                <Self as crate::environment::PolicyValue<E>>::rollout_action(self, &o, legal),
                &mut self.rng,
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
        index: &mut HashMap<E::Key, usize>,
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
        let mut considered = active.len().min(16).min(budget);
        while considered > 1
            && budget / ((usize::BITS - (considered - 1).leading_zeros()) as usize) < considered
        {
            considered -= 1;
        }
        active.truncate(considered);
        let mut remaining = budget;
        let mut simulation = 0usize;
        while remaining > 0 {
            let phases = if active.len() == 1 {
                1
            } else {
                (usize::BITS - (active.len() - 1).leading_zeros()) as usize
            };
            let allocation = remaining / phases;
            for turn in 0..allocation {
                let edge = active[turn % active.len()];
                let mut state = if worlds.is_empty() {
                    E::determinize(o, &mut self.rng)
                } else {
                    worlds[simulation % worlds.len()].clone()
                };
                let seat = E::current(&state);
                let old = E::turns(&state);
                E::apply(&mut state, nodes[root].edges[edge].action, &mut self.rng);
                let depth = self.config.depth.max(1) - u32::from(E::turns(&state) != old);
                let values = self.simulate_environment::<E>(&mut state, depth, nodes, index);
                nodes[root].visits += 1;
                nodes[root].edges[edge].visits += 1;
                nodes[root].edges[edge].sum += values[seat];
                self.simulations += 1;
                simulation += 1;
            }
            remaining -= allocation;
            let scores = nodes[root].completed_scores();
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
        index: &mut HashMap<E::Key, usize>,
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
            E::apply(state, action, &mut self.rng);
            return self.simulate_environment::<E>(
                state,
                depth - u32::from(E::turns(state) != old),
                nodes,
                index,
            );
        }
        let key = E::key(&o, self.transferred);
        let i = if let Some(&i) = index.get(&key) {
            i
        } else {
            let choices = <Self as crate::environment::PolicyValue<E>>::choices(&o, legal);
            let mut node = self.expand_environment::<E>(&o, choices.as_deref().unwrap_or(legal));
            if self.rollout_depth > 0 {
                node.value = self.rollout_environment::<E>(state)[seat];
            }
            let mut r = [1.0 - node.value; 2];
            r[seat] = node.value;
            index.insert(key, nodes.len());
            nodes.push(node);
            return r;
        };
        let node = &nodes[i];
        let edge = if self.gumbel {
            let policy = node.improved_policy();
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
        E::apply(state, action, &mut self.rng);
        let values = self.simulate_environment::<E>(
            state,
            depth - u32::from(E::turns(state) != old),
            nodes,
            index,
        );
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
        self.calls += 1;
        let x = o
            .determinize(&mut self.rng)
            .expect("valid native observation")
            .model_features();
        let model = self
            .external_model
            .expect("native environment requires frozen model");
        let (policy, values) = if model.needs_public_context() {
            let opponent = 1 - usize::from(o.current);
            let mut context = [0.0; 7];
            for slot in 0..usize::from(o.players[opponent].reserved_count) {
                let r = o.players[opponent].reserved[slot];
                context[slot] = f32::from(!r.public);
                context[slot + 3] = f32::from(r.tier + 1) / 3.0;
                context[6] += context[slot] / 3.0;
            }
            model.infer_with_context(&x, &context)
        } else if self.root_only && !self.root_evaluation {
            model.infer_base(&x)
        } else {
            if model.has_correction() {
                self.correction_calls += 1;
            }
            model.infer(&x)
        };
        let seat = usize::from(o.viewer != o.current);
        (policy, (f64::from(values[seat]) + 1.0) / 2.0)
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
    {
        assert!(!legal.is_empty());
        if legal.len() == 1 {
            return legal[0];
        }
        let choices = <Self as crate::environment::PolicyValue<E>>::choices(o, legal);
        let mut nodes =
            vec![self.expand_root_environment::<E>(o, choices.as_deref().unwrap_or(legal))];
        let mut index = HashMap::from([(E::key(o, self.transferred), 0usize)]);
        let worlds: Vec<_> = (0..self.world_pool)
            .map(|_| E::determinize(o, &mut self.rng))
            .collect();
        if self.gumbel {
            let selected = self.gumbel_root::<E>(o, 0, &mut nodes, &mut index, &worlds);
            return nodes[0].edges[selected].action;
        }
        for simulation in 0..self.config.iterations {
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
        if !self.gumbel {
            for simulation in 0..self.config.iterations {
                if simulation > 0
                    && self
                        .config
                        .time_budget
                        .is_some_and(|t| start.elapsed() >= t)
                {
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
        if visits > 0 {
            let mut policy = [0.0; ACTIONS];
            let improved = if self.gumbel {
                Some(nodes[root].improved_policy())
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

fn model_v2() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e26.bin")))
}
pub fn value_v2(o: &Observation) -> f64 {
    let (_, v) = model_v2().infer(&super::neural::enhanced_features(o));
    1.0 / (1.0 + f64::from(-v.clamp(-30.0, 30.0)).exp())
}

fn model_transferred() -> &'static super::transfer::Model {
    static MODEL: OnceLock<super::transfer::Model> = OnceLock::new();
    MODEL.get_or_init(|| super::transfer::Model::from_bytes(include_bytes!("models/e30.bin")))
}

fn model_self_play() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e28.bin")))
}

fn model_expert() -> &'static Model {
    static MODEL: OnceLock<Model> = OnceLock::new();
    MODEL.get_or_init(|| Model::from_bytes(include_bytes!("models/e27.bin")))
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

#[cfg(test)]
mod tests {
    use super::*;
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
        let p = node.improved_policy();
        assert!((p[..3].iter().sum::<f64>() - 1.0).abs() < 1e-12);
        assert!(p[2] > 0.0 && p[0] > p[1]);
        for e in &mut node.edges {
            e.visits = 1;
            e.sum = 0.5;
        }
        let p = node.improved_policy();
        for (i, e) in node.edges.iter().enumerate() {
            assert!((p[i] - e.prior).abs() < 1e-12);
        }
        node.edges[0].sum = 0.9;
        node.edges[1].sum = 0.1;
        node.edges[2].sum = 0.4;
        let p = node.improved_policy();
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

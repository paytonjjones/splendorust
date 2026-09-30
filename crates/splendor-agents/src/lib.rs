#![forbid(unsafe_code)]
//! Agents receive observations only. The engine and setup seed are never passed in.
use splendor_core::{
    Action, ActionSet, GOLD, NONE, Observation, Phase, Player, Rng, Source,
    data::{CARDS, NOBLES},
};
use std::time::{Duration, Instant};

pub mod learned;
pub mod neural;
pub mod neural_search;
mod value_weights;

pub trait Agent: Send {
    fn policy_target(&self) -> Option<[f32; neural::ACTIONS]> {
        None
    }
    fn value_target(&self) -> Option<f32> {
        None
    }
    /// Actual search simulations and learned leaf calls, for research timing.
    fn work_counts(&self) -> (u64, u64) {
        (0, 0)
    }
    fn select_action(&mut self, observation: &Observation, legal: &[Action]) -> Action;
}
pub struct RandomAgent {
    rng: Rng,
}
impl RandomAgent {
    pub fn new(seed: u64) -> Self {
        Self {
            rng: Rng::new(seed),
        }
    }
}
impl Agent for RandomAgent {
    fn select_action(&mut self, _: &Observation, legal: &[Action]) -> Action {
        legal[self.rng.index(legal.len())]
    }
}
#[derive(Default)]
pub struct SimpleGreedyAgent;
#[derive(Default)]
pub struct StrongHeuristicAgent;
impl Agent for SimpleGreedyAgent {
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        best(o, legal, false)
    }
}
impl Agent for StrongHeuristicAgent {
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        let safe = safe_choices(o, legal);
        best(o, safe.as_deref().unwrap_or(legal), true)
    }
}

fn deficit(p: &Player, id: u8) -> i32 {
    (0..5)
        .map(|c| {
            CARDS[id as usize].cost[c]
                .saturating_sub(p.bonuses[c])
                .saturating_sub(p.tokens[c]) as i32
        })
        .sum::<i32>()
        .saturating_sub(p.tokens[GOLD] as i32)
        .max(0)
}
fn target_ids(o: &Observation) -> impl Iterator<Item = u8> + '_ {
    o.market
        .iter()
        .copied()
        .chain(
            o.players[o.current as usize]
                .reserved
                .iter()
                .map(|r| r.card),
        )
        .filter(|&id| id != NONE)
}
fn noble_potential(o: &Observation, p: &Player) -> i32 {
    NOBLES
        .iter()
        .enumerate()
        .filter(|(n, _)| o.nobles & (1 << n) != 0)
        .map(|(_, req)| {
            let gap: i32 = (0..5)
                .map(|c| req[c].saturating_sub(p.bonuses[c]) as i32)
                .sum();
            120 / (gap + 1)
        })
        .max()
        .unwrap_or(0)
}
fn card_worth(p: &Player, id: u8) -> i32 {
    let c = CARDS[id as usize];
    let engine =
        300 / (1 + p.card_count() as i32 / 8) / (1 + p.bonuses[c.bonus as usize] as i32 / 3);
    c.points as i32 * 150 + engine
}
fn potential(o: &Observation, p: &Player) -> i32 {
    let mut top = [0; 3];
    for id in target_ids(o) {
        if p.owned & (1u128 << id) != 0 {
            continue;
        }
        let cost: i32 = (0..5)
            .map(|c| CARDS[id as usize].cost[c].saturating_sub(p.bonuses[c]) as i32)
            .sum();
        let value = card_worth(p, id) * 20 / ((deficit(p, id) + 2) * (cost + 2));
        if value > top[0] {
            top[2] = top[1];
            top[1] = top[0];
            top[0] = value;
        } else if value > top[1] {
            top[2] = top[1];
            top[1] = value;
        } else if value > top[2] {
            top[2] = value;
        }
    }
    top[0] + top[1] / 5 + top[2] / 10
}
// Valid only while bonuses and ownership stay fixed (Main token actions and Return).
struct PotentialTargets {
    targets: [([u8; 5], i32, i32); 15],
    len: usize,
}
impl PotentialTargets {
    fn new(o: &Observation) -> Self {
        let p = &o.players[o.current as usize];
        let mut result = Self {
            targets: [([0; 5], 0, 0); 15],
            len: 0,
        };
        for id in target_ids(o) {
            if p.owned & (1u128 << id) != 0 {
                continue;
            }
            let cost =
                std::array::from_fn(|c| CARDS[id as usize].cost[c].saturating_sub(p.bonuses[c]));
            let total = cost.iter().map(|&v| v as i32).sum::<i32>();
            result.targets[result.len] = (cost, total, card_worth(p, id) * 20);
            result.len += 1;
        }
        result
    }
    fn score(&self, tokens: &[u8; 6]) -> i32 {
        let mut top = [0; 3];
        for &(cost, total, worth) in &self.targets[..self.len] {
            let gap = (0..5)
                .map(|c| cost[c].saturating_sub(tokens[c]) as i32)
                .sum::<i32>()
                .saturating_sub(tokens[GOLD] as i32)
                .max(0);
            let value = worth / ((gap + 2) * (total + 2));
            if value > top[0] {
                top[2] = top[1];
                top[1] = top[0];
                top[0] = value;
            } else if value > top[1] {
                top[2] = top[1];
                top[1] = value;
            } else if value > top[2] {
                top[2] = value;
            }
        }
        top[0] + top[1] / 5 + top[2] / 10
    }
}
fn token_value(o: &Observation, p: &Player, strong: bool) -> i32 {
    if strong {
        potential(o, p) + p.tokens[GOLD] as i32 * 16
    } else {
        (0..5)
            .map(|c| {
                let useful = target_ids(o)
                    .filter(|&id| CARDS[id as usize].cost[c] > p.bonuses[c] + p.tokens[c])
                    .count() as i32;
                p.tokens[c] as i32 * (8 + useful)
            })
            .sum::<i32>()
            + p.tokens[GOLD] as i32 * 25
    }
}
/// Integer scores keep heuristic choices independent of floating-point platforms.
pub fn action_score(o: &Observation, a: Action, strong: bool) -> i32 {
    action_score_cached(o, a, strong, None, None)
}
fn action_score_cached(
    o: &Observation,
    a: Action,
    strong: bool,
    base_potential: Option<i32>,
    targets: Option<&PotentialTargets>,
) -> i32 {
    let p = o.players[o.current as usize];
    let mut q = p;
    match a {
        Action::BuyVisible(i) | Action::BuyReserved(i) => {
            let id = if matches!(a, Action::BuyVisible(_)) {
                o.market[i as usize]
            } else {
                p.reserved[i as usize].card
            };
            let c = CARDS[id as usize];
            q.bonuses[c.bonus as usize] += 1;
            let noble_gain = noble_potential(o, &q) - noble_potential(o, &p);
            if p.score + c.points + if noble_gain >= 60 { 3 } else { 0 } >= 15 {
                return 100_000 + c.points as i32 * 100;
            }
            let cost: i32 = (0..5)
                .map(|j| c.cost[j].saturating_sub(p.bonuses[j]) as i32)
                .sum();
            if strong {
                1000 + card_worth(&p, id) + noble_gain * 3 - cost * 20
            } else {
                1000 + c.points as i32 * 300
                    + 50 / (1 + p.bonuses[c.bonus as usize] as i32)
                    + noble_gain
            }
        }
        Action::Take(t) => {
            for (c, &v) in t.iter().enumerate() {
                q.tokens[c] += v;
            }
            if strong {
                targets.map_or_else(|| potential(o, &q), |t| t.score(&q.tokens))
                    - base_potential.unwrap_or_else(|| potential(o, &p))
                    - (q.token_count().saturating_sub(10) as i32) * 10
            } else {
                token_value(o, &q, false) - token_value(o, &p, false)
            }
        }
        Action::ReserveVisible(i) => {
            if o.bank[GOLD] > 0 {
                q.tokens[GOLD] += 1;
            }
            let id = o.market[i as usize];
            let gap = deficit(&q, id);
            if strong {
                let gold_gain = (targets.map_or_else(|| potential(o, &q), |t| t.score(&q.tokens))
                    - base_potential.unwrap_or_else(|| potential(o, &p)))
                    / 3;
                gold_gain + card_worth(&p, id) / (gap + 4) / 3
                    - 20
                    - o.reserved_counts[o.current as usize] as i32 * 15
            } else {
                if o.bank[GOLD] > 0 { 12 } else { -20 }
            }
        }
        Action::ReserveDeck(_) => {
            if o.bank[GOLD] > 0 {
                -5
            } else {
                -100
            }
        }
        Action::Pay(pay) => {
            let Phase::Payment(src) = o.phase else {
                return i32::MIN;
            };
            let id = match src {
                Source::Market(i) => o.market[i as usize],
                Source::Reserved(i) => p.reserved[i as usize].card,
            };
            let c = CARDS[id as usize];
            let mut gold = 0;
            for (j, &v) in pay.iter().enumerate() {
                q.tokens[j] -= v;
                gold += c.cost[j].saturating_sub(p.bonuses[j]) - v;
            }
            q.tokens[GOLD] -= gold;
            q.bonuses[c.bonus as usize] += 1;
            q.owned |= 1u128 << id;
            token_value(o, &q, strong) - gold as i32 * 10
        }
        Action::Return(r) => {
            for (j, &v) in r.iter().enumerate() {
                q.tokens[j] -= v;
            }
            if strong {
                targets.map_or_else(|| potential(o, &q), |t| t.score(&q.tokens))
                    + q.tokens[GOLD] as i32 * 16
            } else {
                token_value(o, &q, false)
            }
        }
        Action::Noble(n) => {
            // All give three points. Take the tile closest to an opponent first.
            -(0..o.count as usize)
                .filter(|&i| i != o.current as usize)
                .map(|i| {
                    (0..5)
                        .map(|c| {
                            NOBLES[n as usize][c].saturating_sub(o.players[i].bonuses[c]) as i32
                        })
                        .sum::<i32>()
                })
                .min()
                .unwrap_or(0)
        }
    }
}
fn best(o: &Observation, legal: &[Action], strong: bool) -> Action {
    let mut chosen = legal[0];
    let mut score = i32::MIN;
    let targets = (strong && matches!(o.phase, Phase::Main | Phase::Return))
        .then(|| PotentialTargets::new(o));
    let base = (strong && o.phase == Phase::Main).then(|| {
        targets
            .as_ref()
            .unwrap()
            .score(&o.players[o.current as usize].tokens)
    });
    for &a in legal {
        let s = action_score_cached(o, a, strong, base, targets.as_ref());
        if s > score {
            score = s;
            chosen = a;
        }
    }
    chosen
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RolloutPolicy {
    Random,
    Greedy,
    Strong,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Evaluation {
    Score,
    Engine,
}
#[derive(Clone, Debug)]
pub struct SearchConfig {
    pub iterations: u32,
    pub depth: u32,
    pub width: usize,
    pub time_budget: Option<Duration>,
    pub rollout: RolloutPolicy,
    pub evaluation: Evaluation,
}
impl Default for SearchConfig {
    fn default() -> Self {
        Self {
            iterations: 64,
            depth: 8,
            width: 6,
            time_budget: None,
            rollout: RolloutPolicy::Strong,
            evaluation: Evaluation::Engine,
        }
    }
}
/// Root UCB search with fresh determinization per simulation and policy rollouts.
/// This is a flat Monte Carlo baseline, not a persistent information-set tree.
pub struct SearchAgent {
    rng: Rng,
    pub config: SearchConfig,
    pub simulations: u64,
    pub inference_calls: u64,
    pub neural_value: bool,
    pub enhanced_value: bool,
    pub root_value: Option<f32>,
    pub root_policy: Option<[f32; neural::ACTIONS]>,
    pub value_weights: Option<[f64; learned::FEATURES]>,
}
impl SearchAgent {
    pub fn new(seed: u64, config: SearchConfig) -> Self {
        Self {
            rng: Rng::new(seed),
            config,
            simulations: 0,
            inference_calls: 0,
            neural_value: false,
            enhanced_value: false,
            root_value: None,
            root_policy: None,
            value_weights: None,
        }
    }
}
fn evaluation(o: &Observation, root: usize, kind: Evaluation) -> f64 {
    let value = |p: &Player| {
        p.score as f64
            + if kind == Evaluation::Engine {
                p.bonuses
                    .iter()
                    .map(|&x| (x.min(4) as f64) * 0.28)
                    .sum::<f64>()
                    + p.tokens.iter().sum::<u8>() as f64 * 0.06
            } else {
                0.0
            }
    };
    let own = value(&o.players[root]);
    let others = (0..o.count as usize)
        .filter(|&i| i != root)
        .map(|i| value(&o.players[i]))
        .fold(f64::NEG_INFINITY, f64::max);
    ((own - others) / 20.0 + 0.5).clamp(0.0, 1.0)
}
// A sufficient bound, not a prediction of opponent policy. To empty B colored
// tokens, opponents need at least ceil(B/3) taking turns. Each other turn can
// remove at most one affordable market card. Own reservations cannot be removed.
fn preserves_next_turn(o: &Observation, take: [u8; 5]) -> bool {
    let mut p = o.players[o.current as usize];
    let mut bank = 0usize;
    for (c, &amount) in take.iter().enumerate() {
        p.tokens[c] += amount;
        bank += usize::from(o.bank[c] - amount);
    }
    // A required return can change affordability and the bank. Do not certify it.
    if p.token_count() > 10 {
        return false;
    }
    preserves_with_tokens(o, &p, bank)
}
fn preserves_with_tokens(o: &Observation, p: &Player, bank: usize) -> bool {
    let opponents = usize::from(o.count - 1);
    if bank > 3 * opponents
        || p.reserved
            .iter()
            .any(|r| r.card != NONE && deficit(p, r.card) == 0)
    {
        return true;
    }
    let affordable = o
        .market
        .iter()
        .filter(|&&id| id != NONE && deficit(p, id) == 0)
        .count();
    affordable > opponents - bank.div_ceil(3)
}
fn safe_takes(o: &Observation, legal: &[Action]) -> Option<Vec<Action>> {
    if o.reserved_counts[o.current as usize] != 3
        || !legal.iter().all(|a| matches!(a, Action::Take(_)))
    {
        return None;
    }
    let safe: Vec<_> = legal
        .iter()
        .copied()
        .filter(|a| matches!(a, Action::Take(t) if preserves_next_turn(o, *t)))
        .collect();
    // Without a certified alternative, retain the original legal choices.
    (!safe.is_empty() && safe.len() < legal.len()).then_some(safe)
}
// Only reject a take when the next actor's lack of a legal action is public.
// Blind reservations are unknown, so they prevent this certification.
fn blocks_next_actor(o: &Observation, a: Action) -> bool {
    let actor = &o.players[o.current as usize];
    let noble_finishes = actor.score >= 12
        && NOBLES
            .iter()
            .enumerate()
            .any(|(n, req)| o.nobles & (1 << n) != 0 && (0..5).all(|c| actor.bonuses[c] >= req[c]));
    if o.current + 1 == o.count && (o.final_round || noble_finishes) {
        return false;
    }
    let Action::Take(take) = a else {
        return false;
    };
    if o.players[o.current as usize].token_count() + take.iter().sum::<u8>() > 10
        || (0..5).any(|c| o.bank[c] != take[c])
    {
        return false;
    }
    let next = (usize::from(o.current) + 1) % usize::from(o.count);
    let p = &o.players[next];
    o.reserved_counts[next] == 3
        && p.reserved.iter().all(|r| r.card != NONE)
        && p.reserved.iter().all(|r| deficit(p, r.card) != 0)
        && o.market.iter().all(|&id| id == NONE || deficit(p, id) != 0)
}
fn safe_choices(o: &Observation, legal: &[Action]) -> Option<Vec<Action>> {
    let surviving = safe_token_actions(o, legal);
    let choices = surviving.as_deref().unwrap_or(legal);
    let safe: Vec<_> = choices
        .iter()
        .copied()
        .filter(|&a| !blocks_next_actor(o, a))
        .collect();
    if !safe.is_empty() && safe.len() < choices.len() {
        Some(safe)
    } else {
        surviving
    }
}
fn safe_token_actions(o: &Observation, legal: &[Action]) -> Option<Vec<Action>> {
    if o.phase != Phase::Return {
        return safe_takes(o, legal);
    }
    if o.reserved_counts[o.current as usize] != 3 {
        return None;
    }
    let safe: Vec<_> = legal
        .iter()
        .copied()
        .filter(|a| {
            let Action::Return(returned) = a else {
                return false;
            };
            let mut p = o.players[o.current as usize];
            let mut bank = 0usize;
            for (c, &amount) in returned.iter().enumerate() {
                p.tokens[c] -= amount;
                if c < 5 {
                    bank += usize::from(o.bank[c] + amount);
                }
            }
            preserves_with_tokens(o, &p, bank)
        })
        .collect();
    (!safe.is_empty() && safe.len() < legal.len()).then_some(safe)
}
impl Agent for SearchAgent {
    fn policy_target(&self) -> Option<[f32; neural::ACTIONS]> {
        self.root_policy
    }
    fn value_target(&self) -> Option<f32> {
        self.root_value
    }
    fn work_counts(&self) -> (u64, u64) {
        (self.simulations, self.inference_calls)
    }
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        self.root_value = None;
        self.root_policy = None;
        if o.phase != Phase::Main || legal.len() == 1 || o.turns == u32::MAX {
            let safe = safe_choices(o, legal);
            return best(o, safe.as_deref().unwrap_or(legal), true);
        }
        let safe = safe_choices(o, legal);
        let legal = safe.as_deref().unwrap_or(legal);
        if self.config.iterations == 0 {
            return best(o, legal, true);
        }
        let targets = PotentialTargets::new(o);
        let base = Some(targets.score(&o.players[o.current as usize].tokens));
        let mut ranked: Vec<_> = legal
            .iter()
            .map(|&a| (action_score_cached(o, a, true, base, Some(&targets)), a))
            .collect();
        ranked.sort_by_key(|&(score, _)| std::cmp::Reverse(score));
        let candidates: Vec<_> = ranked
            .into_iter()
            .take(self.config.width.max(1))
            .map(|(_, a)| a)
            .collect();
        let mut sums = vec![0.0; candidates.len()];
        let mut visits = vec![0u32; candidates.len()];
        let start = Instant::now();
        for iter in 0..self.config.iterations {
            if iter > 0
                && self
                    .config
                    .time_budget
                    .is_some_and(|d| start.elapsed() >= d)
            {
                break;
            }
            let j = if (iter as usize) < candidates.len() {
                iter as usize
            } else {
                (0..candidates.len())
                    .max_by(|&a, &b| {
                        let ucb = |i: usize| {
                            sums[i] / visits[i] as f64
                                + (2.0 * ((iter + 1) as f64).ln() / visits[i] as f64).sqrt()
                        };
                        ucb(a).total_cmp(&ucb(b))
                    })
                    .unwrap()
            };
            let mut state = o.determinize(&mut self.rng).expect("engine observation");
            state.apply_action(candidates[j]).expect("root legal");
            let mut aa = ActionSet::new();
            for _ in 0..self.config.depth.saturating_mul(4).max(4) {
                if state.is_terminal()
                    || state.turns() == u32::MAX
                    || (state.turns() - o.turns >= self.config.depth
                        && state.phase() == Phase::Main)
                {
                    break;
                }
                state.legal_actions(&mut aa);
                if aa.is_empty() {
                    break;
                }
                let obs = state.observe(state.current_player());
                let a = match self.config.rollout {
                    RolloutPolicy::Random => aa[self.rng.index(aa.len())],
                    RolloutPolicy::Greedy => best(&obs, &aa, false),
                    RolloutPolicy::Strong => best(&obs, &aa, true),
                };
                state.apply_action(a).unwrap();
            }
            let reward = if let Some(result) = state.outcome() {
                if result.winners & (1 << o.current) != 0 {
                    1.0 / result.winners.count_ones() as f64
                } else {
                    0.0
                }
            } else if self.neural_value && o.count == 2 {
                self.inference_calls += 1;
                if self.enhanced_value {
                    neural_search::value_v2(&state.observe(o.current as usize))
                } else {
                    neural_search::value(&state.observe(o.current as usize))
                }
            } else if let Some(weights) = &self.value_weights {
                self.inference_calls += 1;
                learned::predict(
                    &state.observe(o.current as usize),
                    o.current as usize,
                    weights,
                )
            } else {
                evaluation(
                    &state.observe(o.current as usize),
                    o.current as usize,
                    self.config.evaluation,
                )
            };
            sums[j] += reward;
            visits[j] += 1;
            self.simulations += 1;
        }
        let j = (0..candidates.len())
            .filter(|&i| visits[i] > 0)
            .max_by(|&a, &b| (sums[a] / visits[a] as f64).total_cmp(&(sums[b] / visits[b] as f64)))
            .unwrap_or(0);
        self.root_value = Some((sums[j] / f64::from(visits[j])) as f32);
        let mut policy = [0f32; neural::ACTIONS];
        let max = sums[j] / f64::from(visits[j]);
        let mut total = 0.0;
        for (i, &action) in candidates.iter().enumerate() {
            if visits[i] > 0 {
                let w = ((sums[i] / f64::from(visits[i]) - max) / 0.1).exp() as f32;
                policy[neural::action_index(action).unwrap()] = w;
                total += w;
            }
        }
        policy.iter_mut().for_each(|p| *p /= total);
        self.root_policy = Some(policy);
        candidates[j]
    }
}
/// Experimental E24 policy memory. It never declares a game outcome.
struct LearnedCycleAgent {
    search: SearchAgent,
    history: std::collections::VecDeque<Observation>,
}
impl Agent for LearnedCycleAgent {
    fn policy_target(&self) -> Option<[f32; neural::ACTIONS]> {
        self.search.policy_target()
    }
    fn value_target(&self) -> Option<f32> {
        self.search.value_target()
    }
    fn work_counts(&self) -> (u64, u64) {
        self.search.work_counts()
    }
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        if o.phase != Phase::Main {
            return self.search.select_action(o, legal);
        }
        let mut normalized = o.clone();
        normalized.turns = 0;
        let repeated = self.history.contains(&normalized);
        if self.history.len() == 16 {
            self.history.pop_front();
        }
        self.history.push_back(normalized);
        if repeated {
            let buys: Vec<_> = legal
                .iter()
                .copied()
                .filter(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                .collect();
            if !buys.is_empty() {
                return self.search.select_action(o, &buys);
            }
        }
        self.search.select_action(o, legal)
    }
}
pub fn make_agent(name: &str, seed: u64, search: &SearchConfig) -> Result<Box<dyn Agent>, String> {
    Ok(match name {
        "random" => Box::new(RandomAgent::new(seed)),
        "greedy" | "simple-greedy" => Box::new(SimpleGreedyAgent),
        "strong" | "strong-heuristic" => Box::new(StrongHeuristicAgent),
        "search" | "mcts" => Box::new(SearchAgent::new(seed, search.clone())),
        "search128" | "search512" => {
            let config = SearchConfig {
                iterations: if name == "search128" { 128 } else { 512 },
                ..Default::default()
            };
            Box::new(SearchAgent::new(seed, config))
        }
        "neural" => Box::new(neural_search::NeuralAgent::new(seed, search.clone())),
        "neural-logistic"
        | "neural-policy"
        | "neural-v2"
        | "neural-rollout"
        | "neural-rollout-logistic" => {
            let mut config = search.clone();
            if name == "neural-policy" {
                config.iterations = 0;
            }
            let mut agent = neural_search::NeuralAgent::new(seed, config);
            agent.logistic = name == "neural-logistic" || name == "neural-rollout-logistic";
            agent.enhanced = name == "neural-v2" || name.starts_with("neural-rollout");
            if name.starts_with("neural-rollout") {
                agent.rollout_depth = 8;
            }
            Box::new(agent)
        }
        "learned-cycle" | "learned128" | "neural-flat" | "neural-flat-v2" => {
            let config = if name == "learned128" {
                SearchConfig {
                    iterations: 128,
                    ..Default::default()
                }
            } else {
                search.clone()
            };
            let mut agent = SearchAgent::new(seed, config);
            agent.value_weights = Some(value_weights::WEIGHTS);
            agent.neural_value = name == "neural-flat" || name == "neural-flat-v2";
            agent.enhanced_value = name == "neural-flat-v2";
            Box::new(LearnedCycleAgent {
                search: agent,
                history: std::collections::VecDeque::new(),
            })
        }
        "learned" => {
            let mut agent = SearchAgent::new(seed, search.clone());
            agent.value_weights = Some(value_weights::WEIGHTS);
            Box::new(agent)
        }
        _ => return Err(format!("unknown agent: {name}")),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::GameState;
    fn noble_finish_observation(last: bool) -> Observation {
        let mut o = GameState::new(2, 0).unwrap().observe(0);
        o.players = [Player::default(); 4];
        let actor = usize::from(last);
        let opponent = 1 - actor;
        o.current = actor as u8;
        o.viewer = actor as u8;
        o.turns = 10 + actor as u32;
        o.final_round = false;
        o.phase = Phase::Main;
        o.bank = [0, 1, 0, 0, 0, 5];
        o.players[actor].tokens = [2, 2, 1, 2, 2, 0];
        o.players[actor].bonuses = [4, 4, 0, 0, 4];
        o.players[actor].score = 12;
        o.players[actor].nobles = 1;
        for id in [16, 17, 18, 19, 8, 9, 10, 11, 0, 1, 71, 73] {
            o.players[actor].owned |= 1u128 << id;
        }
        o.players[opponent].tokens = [2, 1, 3, 2, 2, 0];
        o.reserved_counts = [0; 4];
        o.reserved_counts[opponent] = 3;
        o.market = [3, 7, 15, 23, 40, 41, 42, 43, 70, 72, 74, 75];
        for (r, id) in o.players[opponent].reserved.iter_mut().zip([31, 39, 44]) {
            *r = splendor_core::Reservation {
                card: id,
                tier: CARDS[id as usize].tier,
                public: true,
            };
        }
        // One noble was claimed before this turn; a second remains eligible.
        o.nobles = (1 << 4) | (1 << 1);
        o.remaining = [0; 3];
        let mut known = o.players[actor].owned;
        for id in o.market {
            known |= 1u128 << id;
        }
        for r in o.players[opponent].reserved {
            known |= 1u128 << r.card;
        }
        for (id, card) in CARDS.iter().enumerate() {
            if known & (1u128 << id) == 0 {
                o.remaining[card.tier as usize] += 1;
            }
        }
        o
    }
    #[test]
    fn noble_threshold_take_ends_only_from_the_last_seat() {
        let take = Action::Take([0, 1, 0, 0, 0]);
        for last in [false, true] {
            for multiple in [false, true] {
                let mut o = noble_finish_observation(last);
                if multiple {
                    o.nobles = (1 << 4) | (1 << 9);
                }
                let mut state = o.determinize(&mut Rng::new(1)).unwrap();
                state.check_invariants().unwrap();
                assert_eq!(blocks_next_actor(&o, take), !last);
                state.apply_action(take).unwrap();
                state.check_invariants().unwrap();
                let mut successors = vec![state.clone()];
                if multiple {
                    assert_eq!(state.phase(), Phase::Noble);
                    let mut legal = ActionSet::new();
                    state.legal_actions(&mut legal);
                    assert_eq!(legal.len(), 2);
                    successors = legal
                        .iter()
                        .map(|&a| {
                            let mut next = state.clone();
                            next.apply_action(a).unwrap();
                            next
                        })
                        .collect();
                }
                for end in successors {
                    end.check_invariants().unwrap();
                    assert_eq!(end.is_terminal(), last);
                    if last {
                        assert_eq!(end.observe(1).players[1].score, 15);
                        assert!(end.outcome().is_some());
                    } else {
                        let mut legal = ActionSet::new();
                        end.legal_actions(&mut legal);
                        assert!(legal.is_empty());
                        assert_eq!(end.outcome(), None);
                    }
                }
            }
        }
    }
    #[test]
    fn public_block_filter_never_guesses_blind_reservations() {
        let mut o = GameState::new(2, 0).unwrap().observe(0);
        o.bank = [0, 1, 0, 0, 0, 5];
        o.market = [NONE; 12];
        o.players[0] = Player::default();
        o.players[1] = Player::default();
        o.reserved_counts[1] = 3;
        for r in &mut o.players[1].reserved {
            r.card = 6;
        }
        let take = Action::Take([0, 1, 0, 0, 0]);
        assert!(blocks_next_actor(&o, take));
        o.players[1].reserved[0].card = NONE;
        assert!(!blocks_next_actor(&o, take));
        o.players[1].reserved[0].card = 6;
        o.players[1].tokens[2] = 3;
        assert!(!blocks_next_actor(&o, take));
        o.players[1].tokens[2] = 0;
        o.market[0] = 6;
        o.players[1].tokens[2] = 3;
        assert!(!blocks_next_actor(&o, take));
        o.players[1].tokens[2] = 0;
        o.players[0].tokens = [2, 2, 2, 2, 2, 0];
        assert!(!blocks_next_actor(&o, take)); // A mandatory return restores bank tokens.
        o.players[0].tokens = [0; 6];
        o.current = 1;
        o.final_round = true;
        assert!(!blocks_next_actor(&o, take)); // The game ends before the next actor.
    }
    #[test]
    fn return_filter_uses_complete_bundles_and_keeps_uncertified_choices() {
        let mut o = GameState::new(2, 0).unwrap().observe(0);
        o.phase = Phase::Return;
        o.reserved_counts[0] = 3;
        o.players[0] = Player::default();
        o.players[0].tokens = [8, 0, 3, 0, 0, 0];
        o.players[0].reserved[0].card = 6;
        o.market = [NONE; 12];
        o.bank = [0; 6];
        let legal = [
            Action::Return([1, 0, 0, 0, 0, 0]),
            Action::Return([0, 0, 1, 0, 0, 0]),
        ];
        assert_eq!(safe_token_actions(&o, &legal), Some(vec![legal[0]]));
        o.players[0].reserved[0].card = NONE;
        assert_eq!(safe_token_actions(&o, &legal), None);
    }
    #[test]
    fn next_turn_bound_counts_depletion_and_market_removal_separately() {
        // Isolate the public-information bound: card 6 costs three green.
        for (count, bank, affordable, safe) in [
            (2, 0, 1, false), // One opponent can remove the only card.
            (2, 0, 2, true),
            (2, 3, 1, true), // Emptying the bank uses the opponent's only turn.
            (2, 4, 0, true), // The bank cannot be emptied in one turn.
            (3, 0, 2, false),
            (3, 0, 3, true),
            (3, 3, 1, false), // One take and one card removal are possible.
            (3, 3, 2, true),
            (3, 6, 0, false),
            (3, 6, 1, true), // Both opponents must take to empty the bank.
            (3, 7, 0, true),
            (4, 3, 2, false),
            (4, 3, 3, true),
            (4, 6, 1, false),
            (4, 6, 2, true),
            (4, 9, 1, true),
            (4, 10, 0, true),
        ] {
            let mut o = GameState::new(count, 0).unwrap().observe(0);
            o.players[0] = Player::default();
            o.players[0].tokens[2] = 3;
            o.market = [NONE; 12];
            o.market[..affordable].fill(6);
            o.bank = [bank, 0, 0, 0, 0, 0];
            assert_eq!(preserves_next_turn(&o, [0; 5]), safe);
        }
        for count in 2..=4 {
            let mut o = GameState::new(count, 0).unwrap().observe(0);
            o.players[0] = Player::default();
            o.players[0].tokens[2] = 3;
            o.market = [NONE; 12];
            o.bank = [0; 6];
            o.players[0].reserved[0].card = 6;
            assert!(preserves_next_turn(&o, [0; 5]));
            o.players[0].tokens[2] = 2;
            assert!(!preserves_next_turn(&o, [0; 5]));
            o.players[0].tokens[GOLD] = 1;
            assert!(preserves_next_turn(&o, [0; 5]));
            o.players[0].tokens[0] = 8;
            assert!(!preserves_next_turn(&o, [0; 5]));
        }
    }
    #[test]
    fn take_filter_keeps_uncertified_choices_without_a_safe_alternative() {
        let mut o = GameState::new(3, 0).unwrap().observe(0);
        o.players[0] = Player::default();
        o.market = [NONE; 12];
        o.bank = [2; 6];
        o.reserved_counts[0] = 3;
        let legal = [Action::Take([1, 1, 1, 0, 0]), Action::Take([0, 0, 1, 1, 1])];
        assert_eq!(safe_takes(&o, &legal), None);
        o.bank = [1, 1, 1, 1, 1, 0];
        assert_eq!(safe_takes(&o, &legal), None);
        assert_eq!(safe_takes(&o, &[Action::BuyVisible(0), legal[0]]), None);
        o.reserved_counts[0] = 2;
        assert_eq!(safe_takes(&o, &legal), None);
    }
    #[test]
    fn cached_scores_equal_uncached_scores_for_every_legal_action() {
        let mut phases = [false; 4];
        for count in 2..=4 {
            for seed in 0..32 {
                let mut state = GameState::new(count, seed).unwrap();
                let mut rng = Rng::new(seed ^ 116000000);
                let mut legal = ActionSet::new();
                for _ in 0..1000 {
                    state.legal_actions(&mut legal);
                    if legal.is_empty() {
                        break;
                    }
                    let o = state.observe(state.current_player());
                    let phase = match o.phase {
                        Phase::Main => 0,
                        Phase::Payment(_) => 1,
                        Phase::Return => 2,
                        Phase::Noble => 3,
                        Phase::Terminal => unreachable!(),
                    };
                    phases[phase] = true;
                    let base = potential(&o, &o.players[o.current as usize]);
                    let targets = PotentialTargets::new(&o);
                    assert_eq!(targets.score(&o.players[o.current as usize].tokens), base);
                    for &action in &legal {
                        for strong in [false, true] {
                            assert_eq!(
                                action_score_cached(&o, action, strong, Some(base), Some(&targets)),
                                action_score(&o, action, strong)
                            );
                        }
                    }
                    state.apply_action(legal[rng.index(legal.len())]).unwrap();
                }
            }
        }
        assert_eq!(phases, [true; 4]);
    }
    #[test]
    fn search_stops_at_counter_capacity_without_panicking() {
        let mut state = GameState::new(2, 123).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let mut observation = state.observe(0);
        observation.turns = u32::MAX - 1;
        observation.determinize(&mut Rng::new(42)).unwrap();
        let mut agent = SearchAgent::new(
            42,
            SearchConfig {
                iterations: 4,
                ..Default::default()
            },
        );
        assert!(legal.contains(&agent.select_action(&observation, &legal)));
        assert_eq!(agent.simulations, 4);
        state.apply_action(legal[0]).unwrap();
        state.legal_actions(&mut legal);
        observation = state.observe(1);
        observation.turns = u32::MAX;
        observation.determinize(&mut Rng::new(42)).unwrap();
        assert_eq!(
            agent.select_action(&observation, &legal),
            best(&observation, &legal, true)
        );
        assert_eq!(agent.simulations, 4);
    }
    #[test]
    fn large_search_depth_does_not_wrap_at_nonzero_turn() {
        let mut state = GameState::new(2, 123).unwrap();
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        state.apply_action(legal[0]).unwrap();
        assert_eq!(state.turns(), 1);
        state.legal_actions(&mut legal);
        let observation = state.observe(state.current_player());
        for seed in 0..8 {
            let config = SearchConfig {
                iterations: 4,
                depth: 1024,
                width: 4,
                ..Default::default()
            };
            let mut bounded = SearchAgent::new(seed, config.clone());
            let mut large = SearchAgent::new(
                seed,
                SearchConfig {
                    depth: u32::MAX,
                    ..config
                },
            );
            assert_eq!(
                bounded.select_action(&observation, &legal),
                large.select_action(&observation, &legal)
            );
            assert_eq!(bounded.simulations, large.simulations);
        }
    }
    #[test]
    fn every_agent_chooses_legal_and_is_reproducible() {
        for name in [
            "random",
            "greedy",
            "strong",
            "search",
            "learned",
            "learned-cycle",
            "neural",
        ] {
            let config = SearchConfig {
                iterations: 8,
                depth: 2,
                ..Default::default()
            };
            let mut a = make_agent(name, 42, &config).unwrap();
            let mut b = make_agent(name, 42, &config).unwrap();
            let mut s = GameState::new(2, 123).unwrap();
            let mut aa = ActionSet::new();
            for _ in 0..120 {
                s.legal_actions(&mut aa);
                if aa.is_empty() {
                    break;
                }
                let o = s.observe(s.current_player());
                let x = a.select_action(&o, &aa);
                assert_eq!(x, b.select_action(&o, &aa));
                assert!(aa.contains(&x));
                s.apply_action(x).unwrap();
                s.check_invariants().unwrap();
            }
        }
    }
    #[test]
    fn search_cannot_distinguish_unknown_decks() {
        let s = GameState::new(2, 123).unwrap();
        let o = s.observe(0);
        let alternative = o.determinize(&mut Rng::new(987)).unwrap();
        let mut aa = ActionSet::new();
        s.legal_actions(&mut aa);
        let config = SearchConfig {
            iterations: 16,
            depth: 3,
            ..Default::default()
        };
        let mut a = SearchAgent::new(4, config.clone());
        let mut b = SearchAgent::new(4, config);
        assert_eq!(
            a.select_action(&o, &aa),
            b.select_action(&alternative.observe(0), &aa)
        );
    }
}

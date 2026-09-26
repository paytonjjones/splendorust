#![forbid(unsafe_code)]
//! Agents receive observations only. The engine and setup seed are never passed in.
use splendor_core::{
    Action, ActionSet, GOLD, NONE, Observation, Phase, Player, Rng, Source,
    data::{CARDS, NOBLES},
};
use std::time::{Duration, Instant};

pub trait Agent: Send {
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
        best(o, legal, true)
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
    action_score_cached(o, a, strong, None)
}
fn action_score_cached(
    o: &Observation,
    a: Action,
    strong: bool,
    base_potential: Option<i32>,
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
                potential(o, &q)
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
                let gold_gain =
                    (potential(o, &q) - base_potential.unwrap_or_else(|| potential(o, &p))) / 3;
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
            token_value(o, &q, strong)
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
    let base =
        (strong && o.phase == Phase::Main).then(|| potential(o, &o.players[o.current as usize]));
    for &a in legal {
        let s = action_score_cached(o, a, strong, base);
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
}
impl SearchAgent {
    pub fn new(seed: u64, config: SearchConfig) -> Self {
        Self {
            rng: Rng::new(seed),
            config,
            simulations: 0,
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
impl Agent for SearchAgent {
    fn select_action(&mut self, o: &Observation, legal: &[Action]) -> Action {
        if o.phase != Phase::Main
            || legal.len() == 1
            || self.config.iterations == 0
            || o.turns == u32::MAX
        {
            return best(o, legal, true);
        }
        let base = Some(potential(o, &o.players[o.current as usize]));
        let mut ranked: Vec<_> = legal
            .iter()
            .map(|&a| (action_score_cached(o, a, true, base), a))
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
        candidates[j]
    }
}
pub fn make_agent(name: &str, seed: u64, search: &SearchConfig) -> Result<Box<dyn Agent>, String> {
    Ok(match name {
        "random" => Box::new(RandomAgent::new(seed)),
        "greedy" | "simple-greedy" => Box::new(SimpleGreedyAgent),
        "strong" | "strong-heuristic" => Box::new(StrongHeuristicAgent),
        "search" | "mcts" => Box::new(SearchAgent::new(seed, search.clone())),
        _ => return Err(format!("unknown agent: {name}")),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::GameState;
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
                    for &action in &legal {
                        for strong in [false, true] {
                            assert_eq!(
                                action_score_cached(&o, action, strong, Some(base)),
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
        for name in ["random", "greedy", "strong", "search"] {
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

#![forbid(unsafe_code)]
//! Tournament/replay layer. All serialization and wall-clock measurement live here.
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use splendor_agents::{SearchConfig, make_agent};
use splendor_core::{Action, ActionSet, ENGINE_VERSION, GameState, Rng};
use std::{path::Path, time::Instant};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct History {
    pub format: u32,
    pub engine: String,
    pub players: u8,
    pub seed: u64,
    /// Canonical action tag followed by payload, padded with zeroes.
    pub actions: Vec<[u8; 7]>,
    /// Versioned, diagnostic full state; seed+actions are the authoritative snapshot.
    pub state_debug: String,
}
pub fn encode(a: Action) -> [u8; 7] {
    let mut x = [0; 7];
    match a {
        Action::Take(v) => {
            x[0] = 0;
            x[1..6].copy_from_slice(&v);
        }
        Action::ReserveVisible(i) => {
            x[0] = 1;
            x[1] = i;
        }
        Action::ReserveDeck(i) => {
            x[0] = 2;
            x[1] = i;
        }
        Action::BuyVisible(i) => {
            x[0] = 3;
            x[1] = i;
        }
        Action::BuyReserved(i) => {
            x[0] = 4;
            x[1] = i;
        }
        Action::Pay(v) => {
            x[0] = 5;
            x[1..6].copy_from_slice(&v);
        }
        Action::Return(v) => {
            x[0] = 6;
            x[1..7].copy_from_slice(&v);
        }
        Action::Noble(i) => {
            x[0] = 7;
            x[1] = i;
        }
    }
    x
}
pub fn decode(x: [u8; 7]) -> Result<Action, String> {
    let a = match x[0] {
        0 => Action::Take(x[1..6].try_into().unwrap()),
        1 => Action::ReserveVisible(x[1]),
        2 => Action::ReserveDeck(x[1]),
        3 => Action::BuyVisible(x[1]),
        4 => Action::BuyReserved(x[1]),
        5 => Action::Pay(x[1..6].try_into().unwrap()),
        6 => Action::Return(x[1..7].try_into().unwrap()),
        7 => Action::Noble(x[1]),
        _ => return Err("unknown action tag".into()),
    };
    if encode(a) != x {
        return Err("noncanonical action padding".into());
    }
    Ok(a)
}
pub fn replay(h: &History) -> Result<GameState, String> {
    if h.format != 1 || h.engine != ENGINE_VERSION {
        return Err("unsupported replay version".into());
    }
    let mut s = GameState::new(h.players, h.seed).map_err(|e| e.to_string())?;
    for (i, &x) in h.actions.iter().enumerate() {
        s.apply_action(decode(x)?)
            .map_err(|e| format!("action {i}: {e}"))?;
        s.check_invariants()
            .map_err(|e| format!("action {i}: {e}"))?;
    }
    if !h.state_debug.is_empty() && format!("{s:?}") != h.state_debug {
        return Err("replayed state does not match snapshot".into());
    }
    Ok(s)
}
pub fn save_history(h: &History, path: &Path) -> Result<(), String> {
    std::fs::write(
        path,
        serde_json::to_vec_pretty(h).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GameRecord {
    pub block: usize,
    pub rotation: usize,
    pub seed: u64,
    pub seats: Vec<usize>,
    pub scores: Vec<u8>,
    pub ranks: Vec<u8>,
    pub winners: u8,
    pub turns: u32,
    pub decisions: usize,
    pub status: String,
    pub trajectory_hash: String,
}
#[derive(Clone, Debug)]
pub struct RunConfig {
    pub names: Vec<String>,
    pub games: usize,
    pub seed: u64,
    pub threads: usize,
    pub max_decisions: usize,
    pub check: bool,
    pub search: SearchConfig,
}
impl RunConfig {
    pub fn validate(&self) -> Result<(), String> {
        if !(2..=4).contains(&self.names.len()) {
            return Err("provide 2 to 4 agents".into());
        }
        if self.games == 0 || !self.games.is_multiple_of(self.names.len()) {
            return Err(
                "games must be positive and divisible by player count for complete seat rotations"
                    .into(),
            );
        }
        if self.threads == 0 || self.max_decisions == 0 {
            return Err("threads and max-decisions must be positive".into());
        }
        for n in &self.names {
            make_agent(n, 0, &self.search)?;
        }
        Ok(())
    }
}
pub fn play_game(
    config: &RunConfig,
    block: usize,
    rotation: usize,
    seed: u64,
    record: bool,
) -> Result<(GameRecord, Option<History>), String> {
    let n = config.names.len();
    let seats: Vec<_> = (0..n).map(|seat| (seat + rotation) % n).collect();
    let mut agents = seats
        .iter()
        .map(|&identity| {
            make_agent(
                &config.names[identity],
                Rng::new(seed ^ (identity as u64 + 1).wrapping_mul(0xd1342543de82ef95)).next_u64(),
                &config.search,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut s = GameState::new(n as u8, seed).map_err(|e| e.to_string())?;
    let mut aa = ActionSet::new();
    let mut hash = 0xcbf29ce484222325u64;
    let mut decisions = 0;
    let mut status = "decision_limit";
    let mut history = History {
        format: 1,
        engine: ENGINE_VERSION.into(),
        players: n as u8,
        seed,
        actions: Vec::new(),
        state_debug: String::new(),
    };
    // Capture audit/timed runs so every failure includes the exact decisions.
    let capture = record || config.check || config.search.time_budget.is_some();
    for _ in 0..config.max_decisions {
        if s.is_terminal() {
            status = "complete";
            break;
        }
        s.legal_actions(&mut aa);
        if aa.is_empty() {
            status = "no_legal_action";
            break;
        }
        let pi = s.current_player();
        let a = agents[pi].select_action(&s.observe(pi), &aa);
        let wire = encode(a);
        if capture {
            history.actions.push(wire);
        }
        if let Err(e) = s.apply_action(a) {
            return Err(format!(
                "seed={seed} block={block} rotation={rotation} decision={decisions}: {e}; actions={:?}",
                history.actions
            ));
        }
        if config.check {
            s.check_invariants().map_err(|e| {
                format!(
                    "seed={seed} decision={decisions} {e}; actions={:?}",
                    history.actions
                )
            })?;
        }
        for byte in wire {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
        decisions += 1;
    }
    if s.is_terminal() {
        status = "complete";
    }
    let o = s.observe(0);
    let scores = o.players[..n].iter().map(|p| p.score).collect();
    let outcome = s.outcome();
    let result = GameRecord {
        block,
        rotation,
        seed,
        seats,
        scores,
        ranks: outcome
            .map(|o| o.ranks[..n].to_vec())
            .unwrap_or_else(|| vec![0; n]),
        winners: outcome.map(|o| o.winners).unwrap_or(0),
        turns: s.turns(),
        decisions,
        status: status.into(),
        trajectory_hash: format!("{hash:016x}"),
    };
    if record {
        history.state_debug = format!("{s:?}");
    }
    Ok((result, record.then_some(history)))
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AgentStats {
    pub identity: usize,
    pub agent: String,
    pub wins: usize,
    pub shared_wins: usize,
    pub win_share: f64,
    pub win_rate: f64,
    pub ci95: [f64; 2],
    pub average_position: f64,
    pub average_score: f64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Report {
    pub source_id: String,
    pub max_decisions: usize,
    pub invariants_checked: bool,
    pub engine: String,
    pub seed: u64,
    pub players: usize,
    pub requested_games: usize,
    pub completed_games: usize,
    pub incomplete_games: usize,
    pub independent_blocks: usize,
    pub ci_method: String,
    pub agents: Vec<AgentStats>,
    pub average_turns: f64,
    pub average_decisions: f64,
    pub runtime_seconds: f64,
    pub games_per_second: f64,
    pub decisions_per_second: f64,
    pub threads: usize,
    pub search_config: String,
    pub reproducible: bool,
    pub promotion: String,
    pub records: Vec<GameRecord>,
}
/// Conservative empirical Bernstein interval for independent bounded block means.
/// Seat rotations are clustered, never treated as independent observations.
/// Maurer-Pontil (2009), Theorem 4, with alpha/2 for each tail.
pub fn interval(xs: &[f64]) -> [f64; 2] {
    if xs.len() < 2 {
        return [0.0, 1.0];
    }
    let n = xs.len() as f64;
    let mean = xs.iter().sum::<f64>() / n;
    let var = xs.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let log = (4.0f64 / 0.05).ln();
    let half = (2.0 * var * log / n).sqrt() + 7.0 * log / (3.0 * (n - 1.0));
    [(mean - half).max(0.0), (mean + half).min(1.0)]
}
pub fn tournament(config: &RunConfig) -> Result<Report, String> {
    config.validate()?;
    let start = Instant::now();
    let n = config.names.len();
    let blocks = config.games / n;
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(config.threads)
        .build()
        .map_err(|e| e.to_string())?;
    let results: Vec<Result<GameRecord, String>> = pool.install(|| {
        (0..config.games)
            .into_par_iter()
            .map(|i| {
                let block = i / n;
                let seed = Rng::new(config.seed.wrapping_add(block as u64)).next_u64();
                play_game(config, block, i % n, seed, false).map(|x| x.0)
            })
            .collect()
    });
    let records = results.into_iter().collect::<Result<Vec<_>, _>>()?;
    let elapsed = start.elapsed().as_secs_f64();
    let complete: Vec<_> = records.iter().filter(|r| r.status == "complete").collect();
    let mut agents = Vec::new();
    for identity in 0..n {
        let mut wins = 0;
        let mut shared = 0;
        let mut credit = 0.0;
        let mut rank = 0;
        let mut score = 0;
        for r in &complete {
            let seat = r.seats.iter().position(|&id| id == identity).unwrap();
            if r.winners & (1 << seat) != 0 {
                credit += 1.0 / r.winners.count_ones() as f64;
                if r.winners.count_ones() == 1 {
                    wins += 1;
                } else {
                    shared += 1;
                }
            }
            rank += r.ranks[seat] as usize;
            score += r.scores[seat] as usize;
        }
        // Unfinished games have unknown credit. Bound them by 0 and 1;
        // never condition the interval on successful completion.
        let block_credits = |unknown: f64| -> Vec<f64> {
            records
                .chunks(n)
                .map(|block| {
                    block
                        .iter()
                        .map(|r| {
                            if r.status != "complete" {
                                return unknown;
                            }
                            let seat = r.seats.iter().position(|&id| id == identity).unwrap();
                            if r.winners & (1 << seat) != 0 {
                                1.0 / r.winners.count_ones() as f64
                            } else {
                                0.0
                            }
                        })
                        .sum::<f64>()
                        / n as f64
                })
                .collect()
        };
        let lower = interval(&block_credits(0.0))[0];
        let upper = interval(&block_credits(1.0))[1];
        let denominator = complete.len().max(1) as f64;
        agents.push(AgentStats {
            identity,
            agent: config.names[identity].clone(),
            wins,
            shared_wins: shared,
            win_share: credit,
            win_rate: credit / denominator,
            ci95: [lower, upper],
            average_position: rank as f64 / denominator,
            average_score: score as f64 / denominator,
        });
    }
    let completed = complete.len();
    let turns = records.iter().map(|r| r.turns as f64).sum::<f64>();
    let decisions = records.iter().map(|r| r.decisions as f64).sum::<f64>();
    let promotion = if completed != config.games {
        "reject: incomplete games"
    } else if config.search.time_budget.is_some() {
        "manual: timed search is not reproducible"
    } else if agents[0].ci95[0] > 1.0 / n as f64 {
        "candidate exceeds equal-seat baseline"
    } else if agents[0].ci95[1] < 1.0 / n as f64 {
        "candidate below equal-seat baseline"
    } else {
        "inconclusive"
    }
    .to_string();
    Ok(Report {
        source_id: env!("SPLENDOR_SOURCE_ID").into(),
        max_decisions: config.max_decisions,
        invariants_checked: config.check,engine:ENGINE_VERSION.into(),seed:config.seed,players:n,requested_games:config.games,completed_games:completed,incomplete_games:config.games-completed,independent_blocks:blocks,ci_method:"95% empirical Bernstein over independent setup blocks; rotations clustered; shared wins split; unfinished credit bounded by 0 and 1".into(),agents,average_turns:turns/config.games as f64,average_decisions:decisions/config.games as f64,runtime_seconds:elapsed,games_per_second:config.games as f64/elapsed,decisions_per_second:decisions/elapsed,threads:config.threads,search_config:format!("{:?}",config.search),reproducible:config.search.time_budget.is_none(),promotion,records})
}
pub fn summary(r: &Report) -> String {
    let mut s = format!(
        "{}: {}/{} complete, {} players, {} setup blocks\n",
        r.engine, r.completed_games, r.requested_games, r.players, r.independent_blocks
    );
    for a in &r.agents {
        s += &format!(
            "  #{} {}: {:.2}% win credit among completed games, 95% unconditional CI [{:.2}, {:.2}]%, wins {}, shared {}, mean rank {:.3}, score {:.3}\n",
            a.identity,
            a.agent,
            100.0 * a.win_rate,
            100.0 * a.ci95[0],
            100.0 * a.ci95[1],
            a.wins,
            a.shared_wins,
            a.average_position,
            a.average_score
        );
    }
    s += &format!(
        "  {:.2} turns/game, {:.2}s, {:.1} games/s, {:.0} decisions/s\n  {}\n",
        r.average_turns, r.runtime_seconds, r.games_per_second, r.decisions_per_second, r.promotion
    );
    s
}
#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> RunConfig {
        RunConfig {
            names: vec!["random".into(), "greedy".into()],
            games: 20,
            seed: 42,
            threads: 1,
            max_decisions: 20000,
            check: true,
            search: SearchConfig::default(),
        }
    }
    #[test]
    fn replay_roundtrip_and_reject_version_and_corruption() {
        let c = config();
        let (_, h) = play_game(&c, 0, 0, 42, true).unwrap();
        let h = h.unwrap();
        let text = serde_json::to_string(&h).unwrap();
        let mut decoded: History = serde_json::from_str(&text).unwrap();
        let s = replay(&decoded).unwrap();
        assert!(s.is_terminal());
        assert_eq!(format!("{s:?}"), h.state_debug);
        decoded.format = 2;
        assert!(replay(&decoded).is_err());
        decoded.format = 1;
        decoded.actions[0] = [255; 7];
        assert!(replay(&decoded).is_err());
    }
    #[test]
    fn parallel_results_match_serial_bit_for_bit() {
        let mut c = config();
        let a = tournament(&c).unwrap();
        c.threads = 4;
        let b = tournament(&c).unwrap();
        assert_eq!(a.records, b.records);
        assert_eq!(a.completed_games, 20);
        assert_eq!(a.agents[0].win_rate, b.agents[0].win_rate);
        for block in a.records.chunks(2) {
            assert_eq!(block[0].seed, block[1].seed);
            assert_eq!(block[0].seats, vec![0, 1]);
            assert_eq!(block[1].seats, vec![1, 0]);
        }
    }
    #[test]
    fn incomplete_games_cannot_promote() {
        let mut c = config();
        c.max_decisions = 1;
        let r = tournament(&c).unwrap();
        assert_eq!(r.completed_games, 0);
        assert!(r.promotion.starts_with("reject"));
        assert!(r.records.iter().all(|x| x.winners == 0));
    }
    #[test]
    fn confidence_interval_keeps_uncertainty_at_boundaries() {
        assert_eq!(interval(&[]), [0.0, 1.0]);
        let ci = interval(&vec![1.0; 1000]);
        assert!(ci[0] < 1.0 && ci[0] > 0.98);
        assert_eq!(ci[1], 1.0);
        let ci = interval(&vec![0.5; 1000]);
        assert!(ci[0] < 0.5 && ci[1] > 0.5);
    }
    #[test]
    fn wire_roundtrip_all_actions() {
        for a in [
            Action::Take([1, 0, 1, 0, 1]),
            Action::ReserveVisible(11),
            Action::ReserveDeck(2),
            Action::BuyVisible(9),
            Action::BuyReserved(2),
            Action::Pay([1, 2, 3, 0, 0]),
            Action::Return([0, 1, 0, 0, 0, 1]),
            Action::Noble(9),
        ] {
            assert_eq!(decode(encode(a)).unwrap(), a);
        }
        assert!(decode([1, 2, 1, 0, 0, 0, 0]).is_err());
    }
}

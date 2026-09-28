//! Explicit benchmark profile; no policy or rules change in the standard engine.
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use splendor_core::{
    Action, ActionSet, GameState, NONE, Phase, Rng,
    data::{CARDS, NOBLES},
};
use std::{fs, time::Instant};

#[derive(Deserialize)]
struct Case {
    seed: u64,
    policy_seed: u64,
    decks: Vec<Vec<u8>>,
    nobles: Vec<u8>,
}
#[derive(Deserialize)]
struct Corpus {
    profile: String,
    cases: Vec<Case>,
}
#[derive(Serialize, PartialEq, Eq)]
struct Player {
    tokens: [u8; 6],
    bonuses: [u8; 5],
    score: u8,
    reserved: Vec<u8>,
}
#[derive(Serialize, PartialEq, Eq)]
struct Snapshot {
    bank: [u8; 6],
    players: Vec<Player>,
    market: Vec<u8>,
    remaining: [u8; 3],
    nobles: Vec<u8>,
    current: u8,
    turns: u32,
    terminal: bool,
}
fn snapshot(s: &GameState) -> Snapshot {
    let o = s.observe(s.current_player());
    let mut market: Vec<_> = o.market.into_iter().filter(|&x| x != NONE).collect();
    market.sort_unstable();
    Snapshot {
        bank: o.bank,
        players: o.players[..2]
            .iter()
            .map(|p| {
                let mut reserved: Vec<_> = p
                    .reserved
                    .iter()
                    .filter(|r| r.card != NONE)
                    .map(|r| r.card)
                    .collect();
                reserved.sort_unstable();
                Player {
                    tokens: p.tokens,
                    bonuses: p.bonuses,
                    score: p.score,
                    reserved,
                }
            })
            .collect(),
        market,
        remaining: o.remaining,
        nobles: (0..10).filter(|n| o.nobles & (1 << n) != 0).collect(),
        current: o.current,
        turns: o.turns,
        terminal: s.is_terminal(),
    }
}
#[derive(Serialize)]
struct Record {
    seed: u64,
    status: String,
    decisions: u64,
    turns: u32,
    latency_seconds: f64,
    final_state: Option<Snapshot>,
    trace: Vec<Snapshot>,
    action_keys: Vec<u32>,
    legal_keys: Vec<Vec<u32>>,
}
fn setup(c: &Case) -> GameState {
    GameState::new_benchmark_setup(2, [&c.decks[0], &c.decks[1], &c.decks[2]], &c.nobles).unwrap()
}
fn play(c: &Case, s: &mut GameState, policy: &str, trace: bool, check: bool) -> Record {
    let start = Instant::now();
    let mut rng = Rng::new(c.policy_seed);
    let mut legal = ActionSet::new();
    let mut history = Vec::new();
    let mut keys = Vec::new();
    let mut legal_keys = Vec::new();
    let mut decisions = 0;
    let mut status = "decision_limit";
    if trace {
        history.push(snapshot(s));
    }
    for _ in 0..20000 {
        if s.is_terminal() {
            status = "complete";
            break;
        }
        assert_eq!(s.phase(), Phase::Main);
        let o = s.observe(s.current_player());
        let p = &o.players[s.current_player()];
        s.legal_actions(&mut legal);
        let mut projected = Vec::new();
        for &action in &legal {
            let key = match action {
                Action::BuyVisible(i) => Some(u32::from(o.market[i as usize])),
                Action::BuyReserved(i) => Some(100 + u32::from(p.reserved[i as usize].card)),
                Action::ReserveVisible(i) if p.token_count() + u8::from(o.bank[5] > 0) <= 10 => {
                    Some(2000 + u32::from(o.market[i as usize]))
                }
                Action::Take(q)
                    if q.iter().sum::<u8>() == 3 && p.token_count() <= 7
                        || q.iter().sum::<u8>() == 2 && q.contains(&2) && p.token_count() < 8 =>
                {
                    Some(
                        1000 + q
                            .iter()
                            .enumerate()
                            .map(|(i, &x)| u32::from(x) * 3u32.pow(i as u32))
                            .sum::<u32>(),
                    )
                }
                _ => None,
            };
            if let Some(key) = key {
                projected.push((key, action));
            }
        }
        projected.sort_unstable_by_key(|x| x.0);
        if trace {
            legal_keys.push(projected.iter().map(|x| x.0).collect());
        }
        if projected.is_empty() {
            status = if legal.is_empty() {
                "no_legal_action"
            } else {
                "profile_blocked"
            };
            break;
        }
        let index = if policy == "random" {
            rng.index(projected.len())
        } else if projected[0].0 < 1000 {
            0
        } else {
            let mut best = None;
            let mut best_value = i32::MIN;
            for (i, (_, action)) in projected.iter().enumerate() {
                if let Action::Take(q) = action {
                    let value: i32 = (0..5)
                        .map(|c| i32::from(q[c]) * (8 - i32::from(p.tokens[c])))
                        .sum();
                    if value > best_value {
                        best = Some(i);
                        best_value = value;
                    }
                }
            }
            best.unwrap_or(0)
        };
        let (key, action) = projected[index];
        // Payment is a policy choice from the complete published action space.
        let payment = match action {
            Action::BuyVisible(i) => Some(o.market[i as usize]),
            Action::BuyReserved(i) => Some(p.reserved[i as usize].card),
            _ => None,
        }
        .map(|id| {
            std::array::from_fn(|color| {
                CARDS[id as usize].cost[color]
                    .saturating_sub(p.bonuses[color])
                    .min(p.tokens[color])
            })
        });
        if let Some(id) = match action {
            Action::BuyVisible(i) => Some(o.market[i as usize]),
            Action::BuyReserved(i) => Some(p.reserved[i as usize].card),
            _ => None,
        } {
            let mut bonuses = p.bonuses;
            bonuses[CARDS[id as usize].bonus as usize] += 1;
            let eligible = (0..10)
                .filter(|&n| {
                    o.nobles & (1 << n) != 0
                        && (0..5).all(|color| bonuses[color] >= NOBLES[n][color])
                })
                .count();
            if eligible > 1 {
                status = "unsupported_noble_choice";
                break;
            }
        }
        s.apply_action(action).unwrap();
        decisions += 1;
        if let Some(payment) = payment {
            assert!(matches!(s.phase(), Phase::Payment(_)));
            s.apply_action(Action::Pay(payment)).unwrap();
            decisions += 1;
        }
        if s.phase() == Phase::Noble {
            s.legal_actions(&mut legal);
            s.apply_action(legal[0]).unwrap();
            decisions += 1;
        }
        assert!(matches!(s.phase(), Phase::Main | Phase::Terminal));
        if check {
            s.check_invariants().unwrap();
        }
        if trace {
            keys.push(key);
            history.push(snapshot(s));
        }
    }
    if s.is_terminal() {
        status = "complete";
    }
    let latency_seconds = start.elapsed().as_secs_f64();
    Record {
        seed: c.seed,
        status: status.into(),
        decisions,
        turns: s.turns(),
        latency_seconds,
        final_state: None,
        trace: history,
        action_keys: keys,
        legal_keys,
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let get = |flag: &str, default: &str| {
        args.iter()
            .position(|s| s == flag)
            .map_or(default.to_owned(), |i| args[i + 1].clone())
    };
    let corpus: Corpus =
        serde_json::from_str(&fs::read_to_string(get("--corpus", "")).unwrap()).unwrap();
    assert_eq!(corpus.profile, "seal256-intersection-v1");
    let policy = get("--policy", "random");
    assert!(["random", "fixed"].contains(&policy.as_str()));
    let threads: usize = get("--threads", "1").parse().unwrap();
    let repetitions: usize = get("--repetitions", "1").parse().unwrap();
    let trace = args.iter().any(|x| x == "--trace");
    let check = args.iter().any(|x| x == "--check");
    assert!(threads > 0 && repetitions > 0);
    let pool_start = Instant::now();
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    pool.broadcast(|_| ());
    let pool_seconds = pool_start.elapsed().as_secs_f64();
    // Warm-up is outside all repetitions.
    pool.install(|| {
        play(
            &corpus.cases[0],
            &mut setup(&corpus.cases[0]),
            &policy,
            false,
            false,
        );
    });
    let mut samples = Vec::new();
    for _ in 0..repetitions {
        let setup_start = Instant::now();
        let mut states: Vec<_> = corpus.cases.iter().map(setup).collect();
        let setup_seconds = setup_start.elapsed().as_secs_f64();
        let start = Instant::now();
        let mut records: Vec<_> = pool.install(|| {
            corpus
                .cases
                .par_iter()
                .zip(states.par_iter_mut())
                .map(|(c, s)| play(c, s, &policy, trace, check))
                .collect()
        });
        let seconds = start.elapsed().as_secs_f64();
        for (record, state) in records.iter_mut().zip(&states) {
            record.final_state = Some(snapshot(state));
        }
        let complete = records.iter().filter(|r| r.status == "complete").count();
        let mut statuses = std::collections::BTreeMap::new();
        for r in &records {
            *statuses.entry(&r.status).or_insert(0usize) += 1;
        }
        samples.push(serde_json::json!({"seconds":seconds,"setup_seconds":setup_seconds,"count":records.len(),"completed":complete,"statuses":statuses,"turns":records.iter().map(|r|u64::from(r.turns)).sum::<u64>(),"decisions":records.iter().map(|r|r.decisions).sum::<u64>(),"records":records}));
    }
    println!(
        "{}",
        serde_json::json!({"engine":"splendorust","profile":corpus.profile,"profile_engine_version":splendor_core::BENCHMARK_COMPAT_ENGINE_VERSION,"policy":policy,"threads":threads,"pool_startup_seconds":pool_seconds,"samples":samples,"timing_boundary":"full legal generation (injected setup before timer), policy projection, checked apply, per-game clock, ordered records; final snapshot extraction and JSON serialization excluded"})
    );
}

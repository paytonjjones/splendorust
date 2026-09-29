//! JSON-lines benchmark interface. Does not change engine or agent behavior.
use rayon::prelude::*;
use serde::Deserialize;
use serde_json::json;
use splendor_agents::{Agent, SearchAgent, SearchConfig, SimpleGreedyAgent};
use splendor_core::{Action, ActionSet, GameState, Rng};
use std::{
    hint::black_box,
    io::{self, BufRead, Write},
    time::Instant,
};

#[derive(Deserialize)]
struct Request {
    workload: String,
    #[serde(default = "default_count")]
    count: u64,
    #[serde(default = "default_players")]
    players: u8,
    #[serde(default = "default_seed")]
    seed: u64,
    #[serde(default)]
    check: bool,
    #[serde(default)]
    latency: bool,
    #[serde(default = "default_cap")]
    cap: u32,
}
fn default_count() -> u64 {
    1000
}
fn default_players() -> u8 {
    2
}
fn default_seed() -> u64 {
    910000001
}
fn default_cap() -> u32 {
    20000
}
struct Record {
    decisions: u64,
    turns: u64,
    status: usize,
    digest: u64,
    seconds: f64,
    simulations: u64,
}
fn game(q: &Request, index: u64) -> Record {
    let start = q.latency.then(Instant::now);
    // Corpus index is global and never depends on worker scheduling.
    let setup = Rng::new(q.seed.wrapping_add(index)).next_u64();
    let policy_seed = setup ^ 0xd1b54a32d192ed03;
    let mut state = GameState::new(q.players, setup).unwrap();
    let mut rng = Rng::new(policy_seed);
    let mut search: Vec<_> = (0..if q.workload == "search32" {
        q.players
    } else {
        0
    })
        .map(|seat| {
            SearchAgent::new(
                policy_seed.wrapping_add(u64::from(seat)),
                SearchConfig {
                    iterations: 32,
                    ..SearchConfig::default()
                },
            )
        })
        .collect();
    let mut legal = ActionSet::new();
    let mut decisions = 0;
    let mut status = 2; // limit; never a winner
    while decisions < u64::from(q.cap) {
        if state.is_terminal() {
            status = 0;
            break;
        }
        state.legal_actions(&mut legal);
        if legal.is_empty() {
            status = 1;
            break;
        }
        let action = match q.workload.as_str() {
            "random" => legal[rng.index(legal.len())],
            "greedy" => {
                SimpleGreedyAgent.select_action(&state.observe(state.current_player()), &legal)
            }
            "search32" => search[state.current_player()]
                .select_action(&state.observe(state.current_player()), &legal),
            _ => unreachable!(),
        };
        state.apply_action(action).unwrap();
        if q.check {
            state.check_invariants().unwrap();
        }
        decisions += 1;
    }
    // Correct classification even if last allowed decision terminates the game.
    if state.is_terminal() {
        status = 0;
    }
    let seconds = start.map_or(0.0, |s| s.elapsed().as_secs_f64());
    // Result digest is outside the individual latency timer, but inside batch time.
    let mut digest = 0xcbf29ce484222325u64;
    let observation = state.observe(state.current_player());
    for byte in observation
        .bank
        .iter()
        .chain(&observation.market)
        .chain(&observation.remaining)
        .chain(
            observation
                .players
                .iter()
                .flat_map(|p| p.tokens.iter().chain(&p.bonuses)),
        )
    {
        digest = (digest ^ u64::from(*byte)).wrapping_mul(0x100000001b3);
    }
    digest ^= (u64::from(observation.nobles) << 32) ^ decisions ^ u64::from(state.turns());
    for player in observation.players.iter().take(q.players as usize) {
        digest =
            (digest ^ u64::from(player.score) ^ player.owned as u64 ^ (player.owned >> 64) as u64)
                .wrapping_mul(0x100000001b3);
    }
    Record {
        decisions,
        turns: u64::from(state.turns()),
        status,
        digest,
        seconds,
        simulations: search.iter().map(|a| a.simulations).sum(),
    }
}
fn opening_fixture() -> GameState {
    let s = GameState::new(2, 42).unwrap();
    let before = s.observe(0);
    assert_eq!(before.bank, [4, 4, 4, 4, 4, 5]);
    assert_eq!(before.players[0].tokens, [0; 6]);
    let mut after = s.clone();
    after.apply_action(Action::Take([1, 1, 1, 0, 0])).unwrap();
    after.check_invariants().unwrap();
    let o = after.observe(0);
    assert_eq!(o.bank, [3, 3, 3, 4, 4, 5]);
    assert_eq!(o.players[0].tokens, [1, 1, 1, 0, 0, 0]);
    assert_eq!(o.current, 1);
    assert_eq!(o.turns, 1);
    assert_eq!(before.market, o.market);
    assert_eq!(before.remaining, o.remaining);
    assert_eq!(before.nobles, o.nobles);
    assert_eq!(o.players[0].bonuses, [0; 5]);
    assert_eq!(o.players[1], before.players[1]);
    s
}
fn run(q: &Request) -> serde_json::Value {
    assert!(q.count > 0 && q.cap > 0 && (2..=4).contains(&q.players));
    if q.workload == "opening_clone_take" {
        assert_eq!(q.players, 2);
        let fixture = opening_fixture();
        let start = Instant::now();
        let checksum: u64 = (0..rayon::current_num_threads())
            .into_par_iter()
            .map(|worker| {
                let n = q.count / rayon::current_num_threads() as u64
                    + u64::from((worker as u64) < q.count % rayon::current_num_threads() as u64);
                let mut check = 0;
                for _ in 0..n {
                    let mut state = black_box(&fixture).clone();
                    state
                        .apply_action(black_box(Action::Take([1, 1, 1, 0, 0])))
                        .unwrap();
                    check += black_box(&state).turns() as u64;
                    black_box(state);
                }
                check
            })
            .sum();
        return json!({"workload":q.workload,"count":q.count,"seconds":start.elapsed().as_secs_f64(),
            "transitions":q.count,"checksum":checksum,"verified":true,
            "normalized_after":{"bank":[3,3,3,4,4,5],"tokens":[1,1,1,0,0,0],"current":1,"turns":1},
            "timing_boundary":"clone + validated apply + consume result; pool dispatch/reduction included"});
    }
    if q.workload == "setup" {
        let start = Instant::now();
        let checksum: u64 = (0..q.count)
            .into_par_iter()
            .map(|i| {
                let s = GameState::new(q.players, q.seed.wrapping_add(i)).unwrap();
                let observed = black_box(&s).observe(0).market[0] as u64;
                black_box(s);
                observed
            })
            .sum();
        return json!({"workload":"setup","count":q.count,"seconds":start.elapsed().as_secs_f64(),"checksum":checksum,
            "timing_boundary":"setup + observation of market checksum + scheduling; not setup alone"});
    }
    assert!(["random", "greedy", "search32"].contains(&q.workload.as_str()));
    let start = Instant::now();
    let records: Vec<_> = (0..q.count).into_par_iter().map(|i| game(q, i)).collect();
    let seconds = start.elapsed().as_secs_f64();
    let mut statuses = [0_u64; 3];
    let mut digest = 0xcbf29ce484222325u64;
    for r in &records {
        statuses[r.status] += 1;
        digest = (digest ^ r.digest).wrapping_mul(0x100000001b3);
    }
    let mut latencies: Vec<_> = records.iter().map(|r| r.seconds).collect();
    latencies.sort_by(f64::total_cmp);
    let quantile = |p: f64| latencies[((q.count - 1) as f64 * p) as usize];
    json!({"workload":q.workload,"players":q.players,"count":q.count,"seed":q.seed,
        "seconds":seconds,"decisions":records.iter().map(|r|r.decisions).sum::<u64>(),
        "turns":records.iter().map(|r|r.turns).sum::<u64>(),"completed":statuses[0],
        "blocked":statuses[1],"capped":statuses[2],"illegal":0,"digest":format!("{digest:016x}"),
        "simulations":records.iter().map(|r|r.simulations).sum::<u64>(),"check":q.check,
        "latency_seconds":q.latency.then(||json!({"p50":quantile(0.5),"p95":quantile(0.95),"p99":quantile(0.99),"min":latencies[0],"max":latencies[latencies.len()-1]})),
        "timing_boundary":"setup, policy, legal generation, validated apply, final public observation/hash, ordered records; no serialization, logging or invariant checks unless check=true"})
}
fn main() {
    let threads: usize = std::env::args()
        .nth(1)
        .unwrap_or("1".into())
        .parse()
        .unwrap();
    assert!(threads > 0);
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build_global()
        .unwrap();
    // Force lazy worker startup before readiness.
    rayon::broadcast(|_| ());
    println!(
        "{}",
        json!({"ready":true,"engine_version":splendor_core::ENGINE_VERSION,"source_fingerprint":env!("SPLENDOR_SOURCE_ID"),"threads":threads})
    );
    io::stdout().flush().unwrap();
    for line in io::stdin().lock().lines() {
        let q: Request = serde_json::from_str(&line.unwrap()).unwrap();
        println!("{}", run(&q));
        io::stdout().flush().unwrap();
    }
}

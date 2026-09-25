use clap::{Args, Parser, Subcommand};
use splendor_agents::{Evaluation, RolloutPolicy, SearchConfig};
use splendor_arena::{History, RunConfig, play_game, replay, save_history, summary, tournament};
use splendor_core::{ActionSet, GameState, Rng};
use std::{
    hint::black_box,
    path::PathBuf,
    time::{Duration, Instant},
};
#[derive(Parser)]
#[command(
    name = "splendor",
    version,
    about = "Deterministic Splendor engine and paired agent arena"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    /// One game. The replay file is an exact state snapshot at its final decision.
    Play {
        #[command(flatten)]
        common: Common,
        #[arg(long, default_value = "game.json")]
        output: PathBuf,
        #[arg(long)]
        trace: bool,
    },
    /// Rotate all agent identities through every seat on each setup.
    Tournament {
        #[command(flatten)]
        common: Common,
        #[arg(long, default_value_t = 1000)]
        games: usize,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    /// One candidate against N-1 baseline opponents. Candidate gets every seat.
    Compare {
        #[command(flatten)]
        common: Common,
        #[arg(long, default_value = "strong")]
        agent_a: String,
        #[arg(long, default_value = "greedy")]
        agent_b: String,
        #[arg(long, default_value_t = 2)]
        players: u8,
        #[arg(long, default_value_t = 1000)]
        games: usize,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    Replay {
        file: PathBuf,
    },
    /// Core microbenchmarks plus parallel random arena throughput.
    Benchmark {
        #[arg(long, default_value_t = 10000)]
        games: usize,
        #[arg(long, default_value_t = 2)]
        players: u8,
        #[arg(long, default_value_t = 12345)]
        seed: u64,
        #[arg(long, default_value_t = 1)]
        threads: usize,
    },
    /// Large seeded random audit, checking invariants after each decision.
    Audit {
        #[arg(long, default_value_t = 100000)]
        games: usize,
        #[arg(long, default_value_t = 12345)]
        seed: u64,
        #[arg(long, default_value_t = 4)]
        threads: usize,
    },
}
#[derive(Args)]
struct Common {
    #[arg(long, value_delimiter = ',', default_value = "greedy,random")]
    agents: Vec<String>,
    #[arg(long, default_value_t = 12345)]
    seed: u64,
    #[arg(long, default_value_t = 1)]
    threads: usize,
    #[arg(long, default_value_t = 20000)]
    max_decisions: usize,
    #[arg(long)]
    check: bool,
    #[arg(long, default_value_t = 64)]
    iterations: u32,
    #[arg(long, default_value_t = 8)]
    depth: u32,
    #[arg(long, default_value_t = 6)]
    width: usize,
    #[arg(long)]
    search_ms: Option<u64>,
    #[arg(long,default_value="strong",value_parser=["random","greedy","strong"])]
    rollout: String,
    #[arg(long,default_value="engine",value_parser=["score","engine"])]
    evaluation: String,
}
impl Common {
    fn config(self, games: usize) -> RunConfig {
        RunConfig {
            names: self.agents,
            games,
            seed: self.seed,
            threads: self.threads,
            max_decisions: self.max_decisions,
            check: self.check,
            search: SearchConfig {
                iterations: self.iterations,
                depth: self.depth,
                width: self.width,
                time_budget: self.search_ms.map(Duration::from_millis),
                rollout: match self.rollout.as_str() {
                    "random" => RolloutPolicy::Random,
                    "greedy" => RolloutPolicy::Greedy,
                    _ => RolloutPolicy::Strong,
                },
                evaluation: if self.evaluation == "score" {
                    Evaluation::Score
                } else {
                    Evaluation::Engine
                },
            },
        }
    }
}
fn write_report(config: RunConfig, output: Option<PathBuf>) -> Result<(), String> {
    let r = tournament(&config)?;
    print!("{}", summary(&r));
    if let Some(p) = output {
        std::fs::write(p, serde_json::to_vec_pretty(&r).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    }
    if r.incomplete_games > 0 {
        return Err(format!("{} games did not complete", r.incomplete_games));
    }
    Ok(())
}
fn audit_report(config: RunConfig, output: Option<PathBuf>) -> Result<(), String> {
    let r = tournament(&config)?;
    print!("{}", summary(&r));
    let blocked = r
        .records
        .iter()
        .filter(|g| g.status == "no_legal_action")
        .count();
    println!(
        "Run: {} completed; {} blocked; {}",
        r.completed_games,
        blocked,
        if config.check {
            "invariants checked after every decision"
        } else {
            "invariant checks disabled"
        }
    );
    if let Some(p) = output {
        std::fs::write(p, serde_json::to_vec_pretty(&r).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
    }
    if r.records.iter().any(|g| g.status == "decision_limit") {
        return Err("audit decision limit reached".into());
    }
    Ok(())
}
fn run() -> Result<(), String> {
    match Cli::parse().command {
        Command::Play {
            common,
            output,
            trace,
        } => {
            let n = common.agents.len();
            let c = common.config(n);
            c.validate()?;
            let (r, h) = play_game(&c, 0, 0, c.seed, true)?;
            let h = h.unwrap();
            save_history(&h, &output)?;
            if trace {
                for (i, a) in h.actions.iter().enumerate() {
                    println!("{i}: {:?}", splendor_arena::decode(*a)?);
                }
            }
            println!("{}", serde_json::to_string_pretty(&r).unwrap());
            println!("Replay: {}", output.display());
            if r.status != "complete" {
                return Err(r.status);
            }
        }
        Command::Tournament {
            common,
            games,
            output,
        } => write_report(common.config(games), output)?,
        Command::Compare {
            common,
            agent_a,
            agent_b,
            players,
            games,
            output,
        } => {
            if !(2..=4).contains(&players) {
                return Err("players must be 2, 3, or 4".into());
            }
            let mut c = common.config(games);
            c.names = vec![agent_b; players as usize];
            c.names[0] = agent_a;
            write_report(c, output)?;
        }
        Command::Replay { file } => {
            let h: History =
                serde_json::from_slice(&std::fs::read(file).map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())?;
            let s = replay(&h)?;
            println!(
                "Verified {} decisions, {} turns; outcome {:?}",
                h.actions.len(),
                s.turns(),
                s.outcome()
            );
        }
        Command::Benchmark {
            games,
            players,
            seed,
            threads,
        } => {
            if !(2..=4).contains(&players) {
                return Err("players must be 2, 3, or 4".into());
            }
            let s = GameState::new(players, seed).unwrap();
            let mut aa = ActionSet::new();
            s.legal_actions(&mut aa);
            let action = aa[0];
            let iters = 1_000_000;
            let start = Instant::now();
            for _ in 0..iters {
                black_box(&s).legal_actions(black_box(&mut aa));
            }
            println!(
                "legal/opening: {:.1} ns/op",
                start.elapsed().as_nanos() as f64 / iters as f64
            );
            let start = Instant::now();
            for _ in 0..iters {
                let mut t = black_box(&s).clone();
                t.apply_action(black_box(action)).unwrap();
                black_box(t);
            }
            println!(
                "clone/apply: {:.1} ns/op; state {} bytes, action {} bytes",
                start.elapsed().as_nanos() as f64 / iters as f64,
                std::mem::size_of::<GameState>(),
                std::mem::size_of::<splendor_core::Action>()
            );
            let start = Instant::now();
            let mut nodes = 0u64;
            let mut completed = 0;
            let mut blocked = 0;
            for i in 0..games {
                let mut s = GameState::new(players, seed.wrapping_add(i as u64)).unwrap();
                let mut rng = Rng::new(i as u64);
                for _ in 0..20000 {
                    s.legal_actions(&mut aa);
                    if aa.is_empty() {
                        break;
                    }
                    s.apply_action(aa[rng.index(aa.len())]).unwrap();
                    nodes += 1;
                }
                if s.is_terminal() {
                    completed += 1;
                } else if aa.is_empty() {
                    blocked += 1;
                } else {
                    return Err(format!(
                        "benchmark seed {} exceeded limit",
                        seed.wrapping_add(i as u64)
                    ));
                }
                black_box(s);
            }
            let elapsed = start.elapsed().as_secs_f64();
            println!("core outcomes: {completed} completed, {blocked} blocked (no winner)");
            println!(
                "core random: {:.1} games/s, {:.0} decisions/s ({games} games)",
                games as f64 / elapsed,
                nodes as f64 / elapsed
            );
            audit_report(
                RunConfig {
                    names: vec!["random".into(); players as usize],
                    games,
                    seed,
                    threads,
                    max_decisions: 20000,
                    check: false,
                    search: SearchConfig::default(),
                },
                None,
            )?;
        }
        Command::Audit {
            games,
            seed,
            threads,
        } => {
            for players in 2..=4 {
                let n = games / 3 / players * players;
                if n == 0 {
                    return Err("audit needs at least 12 games".into());
                }
                audit_report(
                    RunConfig {
                        names: vec!["random".into(); players],
                        games: n,
                        seed: seed.wrapping_add(players as u64 * 1_000_000),
                        threads,
                        max_decisions: 20000,
                        check: true,
                        search: SearchConfig::default(),
                    },
                    None,
                )?;
            }
        }
    }
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

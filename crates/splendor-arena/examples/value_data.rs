//! Generate outcome labels from independent setup and policy RNG streams.
use splendor_agents::{SearchConfig, learned::features, make_agent};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::{
    io::{BufWriter, Write},
    time::Instant,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    let games: usize = a[1].parse()?;
    let seed: u64 = a[2].parse()?;
    let policy = &a[3];
    let mut out = BufWriter::new(std::fs::File::create(&a[4])?);
    let policy_seed: u64 = a[5].parse()?;
    let mut policy_rng = Rng::new(policy_seed);
    let mut complete = 0;
    let mut blocked = 0;
    let mut capped = 0;
    let mut rows = 0;
    let start = Instant::now();
    for g in 0..games {
        let setup = Rng::new(seed.wrapping_add(g as u64)).next_u64();
        let mut state = GameState::new(2, setup)?;
        let config = SearchConfig {
            iterations: 128,
            ..Default::default()
        };
        let mut agents = [
            make_agent(policy, policy_rng.next_u64(), &config)?,
            make_agent(policy, policy_rng.next_u64(), &config)?,
        ];
        let mut samples = Vec::new();
        let mut legal = ActionSet::new();
        for _ in 0..2000 {
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let seat = state.current_player();
            let o = state.observe(seat);
            if o.phase == Phase::Main && o.turns % 4 < 2 {
                samples.push((seat, features(&o, seat, 1 - seat)));
            }
            let action = agents[seat].select_action(&o, &legal);
            state.apply_action(action)?;
        }
        if let Some(result) = state.outcome() {
            complete += 1;
            for (seat, x) in samples {
                let y = if result.winners & (1 << seat) != 0 {
                    1.0 / f64::from(result.winners.count_ones())
                } else {
                    0.0
                };
                writeln!(
                    out,
                    "{}",
                    serde_json::json!({"setup":setup.to_string(),"x":x,"y":y})
                )?;
                rows += 1;
            }
        } else {
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                blocked += 1;
            } else {
                capped += 1;
            }
        }
    }
    out.flush()?;
    println!(
        "{}",
        serde_json::json!({"games":games,"complete":complete,"blocked":blocked,"capped":capped,"rows":rows,"seed":seed,"policy_seed":policy_seed,"policy":policy,"seconds":start.elapsed().as_secs_f64(),"source":env!("SPLENDOR_SOURCE_ID")})
    );
    Ok(())
}

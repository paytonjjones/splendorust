//! Teacher distillation. Binary rows contain only observation features and labels.
use rayon::prelude::*;
use splendor_agents::{
    SearchConfig, make_agent,
    neural::{ACTIONS, action_index, baseline_logit, enhanced_features},
};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::{
    io::{BufWriter, Write},
    time::Instant,
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    let games: usize = a[1].parse()?;
    let seed: u64 = a[2].parse()?;
    let policy_seed: u64 = a[3].parse()?;
    let iterations: u32 = a[4].parse()?;
    let policy = &a[5];
    let output = &a[6];
    let depth: u32 = a.get(7).map(|s| s.parse()).transpose()?.unwrap_or(8);
    let mut out = BufWriter::new(std::fs::File::create(output)?);
    let start = Instant::now();
    let mut counts = [0usize; 3];
    let mut rows = 0;
    let pool = rayon::ThreadPoolBuilder::new().num_threads(4).build()?;
    // Bounded batches preserve deterministic order without retaining the full dataset.
    for batch in (0..games).step_by(128) {
        let results: Vec<_> = pool.install(|| {
            (batch..(batch + 128).min(games))
                .into_par_iter()
                .map(|g| {
                    let setup = Rng::new(seed.wrapping_add(g as u64)).next_u64();
                    let mut prng = Rng::new(policy_seed.wrapping_add(g as u64));
                    let config = SearchConfig {
                        iterations,
                        depth,
                        ..Default::default()
                    };
                    let mut agents = [
                        make_agent(policy, prng.next_u64(), &config).unwrap(),
                        make_agent(policy, prng.next_u64(), &config).unwrap(),
                    ];
                    let mut s = GameState::new(2, setup).unwrap();
                    let mut legal = ActionSet::new();
                    let mut samples = Vec::new();
                    for _ in 0..2000 {
                        s.legal_actions(&mut legal);
                        if legal.is_empty() {
                            break;
                        }
                        let seat = s.current_player();
                        let o = s.observe(seat);
                        let chosen = agents[seat].select_action(&o, &legal);
                        if o.phase == Phase::Main && o.turns % 4 < 2 {
                            let mut mask = [0f32; ACTIONS];
                            for &action in &legal {
                                mask[action_index(action).unwrap()] = 1.0;
                            }
                            samples.push((
                                seat,
                                enhanced_features(&o),
                                mask,
                                {
                                    let mut p = [0.0; ACTIONS];
                                    p[action_index(chosen).unwrap()] = 1.0;
                                    agents[seat].policy_target().unwrap_or(p)
                                },
                                agents[seat]
                                    .value_target()
                                    .unwrap_or_else(|| 1.0 / (1.0 + (-baseline_logit(&o)).exp())),
                                baseline_logit(&o),
                            ));
                        }
                        s.apply_action(chosen).unwrap();
                    }
                    s.legal_actions(&mut legal);
                    let result = s.outcome();
                    let status = if result.is_some() {
                        0
                    } else if legal.is_empty() {
                        1
                    } else {
                        2
                    };
                    let mut bytes = Vec::new();
                    for (seat, x, mask, policy, teacher, baseline) in samples {
                        let y = result
                            .map(|r| {
                                if r.winners & (1 << seat) != 0 {
                                    1.0 / r.winners.count_ones() as f32
                                } else {
                                    0.0
                                }
                            })
                            .unwrap_or(f32::NAN);
                        bytes.extend(setup.to_le_bytes());
                        for value in x
                            .into_iter()
                            .chain(mask)
                            .chain(policy)
                            .chain([teacher, baseline, y])
                        {
                            bytes.extend(value.to_le_bytes());
                        }
                    }
                    (status, bytes)
                })
                .collect()
        });
        for (status, bytes) in results {
            counts[status] += 1;
            rows += bytes.len() / 1844;
            out.write_all(&bytes)?;
        }
    }
    out.flush()?;
    println!(
        "{}",
        serde_json::json!({"games":games,"complete":counts[0],"blocked":counts[1],"capped":counts[2],"rows":rows,"seed":seed,"policy_seed":policy_seed,"iterations":iterations,"depth":depth,"policy":policy,"seconds":start.elapsed().as_secs_f64(),"source":env!("SPLENDOR_SOURCE_ID"),"row_bytes":1844,"format":"u64 setup, f32[322] features, f32[67] legal mask, f32[67] policy target, f32 teacher value, f32 baseline logit, f32 outcome (NaN if incomplete), little endian"})
    );
    Ok(())
}

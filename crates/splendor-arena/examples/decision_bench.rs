//! Fixed observation workload; per-agent timing, not a playing-strength claim.
use splendor_agents::{SearchConfig, make_agent};
use splendor_core::{ActionSet, GameState, Phase};
use std::{hint::black_box, time::Instant};
fn main() {
    let mut positions = Vec::new();
    let config = SearchConfig {
        iterations: 128,
        ..Default::default()
    };
    for seed in 0..10 {
        let mut s = GameState::new(2, 240000000 + seed).unwrap();
        let mut strong = make_agent("strong", 0, &config).unwrap();
        let mut legal = ActionSet::new();
        for _ in 0..150 {
            s.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = s.observe(s.current_player());
            if o.phase == Phase::Main {
                positions.push((o.clone(), legal.clone()));
            }
            s.apply_action(strong.select_action(&o, &legal)).unwrap();
        }
    }
    for repeat in 0..3 {
        let names = if repeat == 1 {
            [
                "learned-cycle",
                "learned",
                "search512",
                "search128",
                "strong",
            ]
        } else {
            [
                "strong",
                "search128",
                "search512",
                "learned",
                "learned-cycle",
            ]
        };
        for name in names {
            let mut agent = make_agent(name, 241000000, &config).unwrap();
            let start = Instant::now();
            for (o, legal) in &positions {
                black_box(agent.select_action(black_box(o), black_box(legal)));
            }
            let seconds = start.elapsed().as_secs_f64();
            let (simulations, inference_calls) = agent.work_counts();
            println!(
                "{}",
                serde_json::json!({"agent":name,"repeat":repeat,"decisions":positions.len(),"seconds":seconds,"decisions_per_second":positions.len() as f64/seconds,"simulations":simulations,"inference_calls":inference_calls,"source":env!("SPLENDOR_SOURCE_ID")})
            );
        }
    }
}

//! Fixed observation costs for frozen Search128 and a learned endpoint.
use splendor_agents::{SearchConfig, make_agent};
use splendor_core::{ActionSet, GameState, Phase};
use std::{hint::black_box, time::Instant};
fn main() {
    let budget_sweep = false;
    let mut positions = Vec::new();
    for seed in 0..10 {
        let mut state = GameState::new(2, 240000000 + seed).unwrap();
        let mut strong = make_agent("strong", 0, &SearchConfig::default()).unwrap();
        let mut legal = ActionSet::new();
        for _ in 0..150 {
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = state.observe(state.current_player());
            if o.phase == Phase::Main {
                positions.push((o.clone(), legal.clone()));
            }
            state
                .apply_action(strong.select_action(&o, &legal))
                .unwrap();
        }
    }
    for repeat in 0..3 {
        let mut settings = vec![
            ("flywheel-belief-gumbel-candidate", 128),
            ("flywheel-gumbel", 128),
        ];
        if budget_sweep {
            settings = vec![("flywheel-best128", 128)];
            settings.extend((8..=128).step_by(8).map(|n| ("flywheel-candidate", n)));
        }
        if repeat == 1 {
            settings.reverse();
        }
        for (name, iterations) in settings {
            let config = SearchConfig {
                iterations,
                depth: 16,
                ..Default::default()
            };
            let mut agent = make_agent(name, 241000000, &config).unwrap();
            let start = Instant::now();
            for (o, legal) in &positions {
                black_box(agent.select_action(black_box(o), black_box(legal)));
            }
            let (simulations, inference_calls) = agent.work_counts();
            println!(
                "{}",
                serde_json::json!({"agent":name,"iterations":iterations,"repeat":repeat,"decisions":positions.len(),"seconds":start.elapsed().as_secs_f64(),"simulations":simulations,"inference_calls":inference_calls,"source_id":"library search source preserved in plan.json","budget_sweep":budget_sweep,"workload":"Fixed Strong-game Main observations; E81 sampled versus public first-moment root input,128 iterations/depth16; shared-host timing"})
            );
        }
    }
}

//! Fixed public-observation action-label stability. No training or promotion.
use rayon::prelude::*;
use splendor_agents::{SearchConfig, make_agent, neural::action_index, neural_search, transfer};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::time::Instant;
fn main() {
    let start = Instant::now();
    let mut positions = Vec::new();
    let actor_config = SearchConfig {
        iterations: 128,
        depth: 16,
        ..Default::default()
    };
    for game in 0..8 {
        let mut state = GameState::new(2, 4_770_000_000 + game).unwrap();
        let mut actors = [
            make_agent(
                "flywheel-root-gumbel-best",
                4_770_100_000 + 2 * game,
                &actor_config,
            )
            .unwrap(),
            make_agent(
                "flywheel-root-gumbel-best",
                4_770_100_001 + 2 * game,
                &actor_config,
            )
            .unwrap(),
        ];
        let mut legal = ActionSet::new();
        let mut main_count = 0;
        let mut captured = 0;
        for _ in 0..2000 {
            if state.is_terminal() || state.turns() >= 124 {
                break;
            }
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = state.observe(state.current_player());
            if o.phase == Phase::Main {
                if main_count % 2 == 0 && captured < 32 {
                    positions.push((game, o.clone(), legal.clone()));
                    captured += 1;
                }
                main_count += 1;
            }
            let chosen = actors[o.current as usize].select_action(&o, &legal);
            state.apply_action(chosen).unwrap();
        }
    }
    let model = neural_search::flywheel_model(false);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(14)
        .build()
        .unwrap();
    let rows:Vec<_> = pool.install(|| positions.par_iter().enumerate().map(|(i,(game,o,legal))| {
        let context = transfer::public_context(o);
        let x = transfer::encode(o,&mut Rng::new(4_780_100_000+i as u64*8));
        let (native,value) = model.infer_with_context(&x,&context);
        let prior = transfer::policy_logits(&native);
        for encoding in 1..8 {
            let y = transfer::encode(o,&mut Rng::new(4_780_100_000+i as u64*8+encoding));
            let (pi,v) = model.infer_with_context(&y,&context);
            assert_eq!(native,pi);assert_eq!(value,v);
        }
        let prior_action = action_index(*legal.iter().max_by(|a,b|prior[action_index(**a).unwrap()].total_cmp(&prior[action_index(**b).unwrap()])).unwrap()).unwrap();
        let mut searches = Vec::new();
        for iterations in [128,800] {
            let config = SearchConfig {iterations,depth:16,..Default::default()};
            for replicate in 0..8 {
                let seed = 4_780_000_000+i as u64*4096+u64::from(iterations)*16+replicate;
                let mut agent = make_agent("flywheel-root-gumbel-best",seed,&config).unwrap();
                let chosen = agent.select_action(o,legal);
                let chosen_id = action_index(chosen).unwrap();
                let policy = agent.policy_target().unwrap();
                assert!(policy.iter().all(|v|v.is_finite() && *v>=0.0));
                let (simulations,inferences) = agent.work_counts();assert_eq!(simulations,u64::from(iterations));
                searches.push(serde_json::json!({"iterations":iterations,"replicate":replicate,"seed":seed,"chosen_index":chosen_id,"policy":policy.as_slice(),"value":agent.value_target(),"simulations":simulations,"inference_calls":inferences}));
            }
        }
        serde_json::json!({"index":i,"game":game,"turn":o.turns,"observation":format!("{o:?}"),"legal_indices":legal.iter().map(|a|action_index(*a).unwrap()).collect::<Vec<_>>(),"context":context,"root_prior":prior.as_slice(),"root_value":value,"root_argmax":prior_action,"native_encoding_invariant":true,"searches":searches})
    }).collect());
    println!(
        "{}",
        serde_json::json!({"schema":"teacher-label-stability-v1","model":"E88","setup_seed":4770000000u64,"actor_iterations":128,"teacher_budgets":[128,800],"depth":16,"replicates":8,"threads":14,"positions":rows.len(),"seconds":start.elapsed().as_secs_f64(),"scope":"fresh E88 trajectories; fixed conditional observation cohort; no strength claim or training","observations":rows})
    );
}

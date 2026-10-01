//! Check whether reservation visibility survives the transferred encoder.
use splendor_agents::{SearchConfig, make_agent, transfer};
use splendor_core::{Action, ActionSet, GameState, Phase, Rng};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let model = transfer::Model::from_bytes(&std::fs::read(&args[1])?);
    let config = SearchConfig {
        iterations: 800,
        depth: 16,
        ..Default::default()
    };
    let mut records = Vec::new();
    for trajectory in 0..4 {
        let mut state = GameState::new(2, 4_240_000_000 + trajectory)?;
        let mut strong = make_agent("strong", 0, &SearchConfig::default())?;
        let mut legal = ActionSet::new();
        for _ in 0..200 {
            if state.is_terminal() || state.turns() >= 124 {
                break;
            }
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = state.observe(state.current_player());
            let opponent = 1 - o.current as usize;
            let blind = o.players[opponent]
                .reserved
                .iter()
                .take(o.reserved_counts[opponent] as usize)
                .filter(|r| !r.public)
                .count();
            if o.phase == Phase::Main
                && o.turns.is_multiple_of(8)
                && blind > 0
                && records.len() < 32
            {
                let encoder_seed = 4_250_000_000 + trajectory * 10000 + u64::from(o.turns);
                let sampled = o.determinize(&mut Rng::new(encoder_seed))?;
                let sampled_owner = sampled.observe(opponent);
                let mut known = o.clone();
                for slot in 0..o.reserved_counts[opponent] as usize {
                    if !known.players[opponent].reserved[slot].public {
                        known.players[opponent].reserved[slot].card =
                            sampled_owner.players[opponent].reserved[slot].card;
                        known.players[opponent].reserved[slot].public = true;
                    }
                }
                let fixed = known.determinize(&mut Rng::new(encoder_seed))?;
                let mut fixed_legal = ActionSet::new();
                fixed.legal_actions(&mut fixed_legal);
                assert_eq!(legal, fixed_legal);
                let x = transfer::encode(&o, &mut Rng::new(encoder_seed));
                let y = transfer::encode(&known, &mut Rng::new(encoder_seed));
                assert_eq!(x, y);
                let (pi, v) = model.infer(&x);
                let (other_pi, other_v) = model.infer(&y);
                assert_eq!(pi, other_pi);
                assert_eq!(v, other_v);
                let mut policies = vec![Vec::new(), Vec::new()];
                let mut values = vec![Vec::new(), Vec::new()];
                for replicate in 0..8 {
                    let seed =
                        4_260_000_000 + trajectory * 10000 + u64::from(o.turns) * 8 + replicate;
                    for (condition, observation) in [&o, &known].into_iter().enumerate() {
                        let mut teacher = make_agent("flywheel-best", seed, &config)?;
                        let action = teacher.select_action(observation, &legal);
                        assert!(legal.contains(&action));
                        let policy = teacher.policy_target().unwrap_or_else(|| {
                            let mut p = [0.0; 67];
                            p[splendor_agents::neural::action_index(action).unwrap()] = 1.0;
                            p
                        });
                        policies[condition].push(policy.to_vec());
                        values[condition].push(teacher.value_target());
                    }
                }
                records.push(serde_json::json!({"trajectory":trajectory,"turn":o.turns,"opponent_blind":blind,"encoder_seed":encoder_seed,"encoded_input":x.as_slice(),"sampled_public_counterpart":known.players[opponent].reserved.map(|r|serde_json::json!({"card":r.card,"tier":r.tier,"public":r.public})),"input_exact":true,"outputs_exact":true,"policies":policies,"values":values}));
            }
            let forced = if o.phase == Phase::Main && o.turns < 6 {
                legal
                    .iter()
                    .copied()
                    .find(|a| matches!(a, Action::ReserveDeck(_)))
            } else {
                None
            };
            state.apply_action(forced.unwrap_or_else(|| strong.select_action(&o, &legal)))?;
        }
    }
    assert!(!records.is_empty());
    std::fs::write(
        &args[2],
        serde_json::to_vec(
            &serde_json::json!({"source_id":env!("SPLENDOR_SOURCE_ID"),"iterations":800,"replicates":8,"scope":"Exact encoding collisions and finite teacher-label contrast on fixed blind stress observations; no prevalence or playing-strength claim","observations":records}),
        )?,
    )?;
    Ok(())
}

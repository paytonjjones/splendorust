//! Same Observation, independently sampled legal hidden worlds; no true hidden input.
use splendor_agents::{SearchConfig, make_agent, neural::action_index, transfer};
use splendor_core::{Action, ActionSet, GameState, Phase, Rng};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let model = transfer::Model::from_bytes(&std::fs::read(&args[1])?);
    let ids = transfer::policy_logits(&std::array::from_fn(|i| i as f32));
    let mut rows = Vec::new();
    for stress in [false, true] {
        for seed in 0..16 {
            let mut state = GameState::new(2, 1_290_000_000 + seed).unwrap();
            let mut agent = make_agent("strong", 0, &SearchConfig::default()).unwrap();
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
                if o.phase == Phase::Main {
                    let opponent = 1 - o.current as usize;
                    let blind = o.players[opponent]
                        .reserved
                        .iter()
                        .take(o.reserved_counts[opponent] as usize)
                        .filter(|r| !r.public)
                        .count();
                    let mut mask = [false; 81];
                    for &a in &legal {
                        let i = action_index(a).unwrap();
                        mask[ids[i] as usize] = true;
                    }
                    let mut policies = Vec::new();
                    let mut values = Vec::new();
                    let mut encodings = Vec::new();
                    for view in 0..8 {
                        let x = transfer::encode(
                            &o,
                            &mut Rng::new(
                                1_340_000_000 + seed * 10000 + u64::from(o.turns) * 8 + view,
                            ),
                        );
                        let (logits, value) = model.infer(&x);
                        let max = logits
                            .iter()
                            .zip(mask)
                            .filter(|(_, m)| *m)
                            .map(|(v, _)| *v)
                            .fold(f32::NEG_INFINITY, f32::max);
                        let mut p: Vec<_> = logits
                            .iter()
                            .zip(mask)
                            .map(|(v, m)| if m { (*v - max).exp() } else { 0.0 })
                            .collect();
                        let total: f32 = p.iter().sum();
                        for v in &mut p {
                            *v /= total;
                        }
                        policies.push(p);
                        values.push(value);
                        encodings.push(x.to_vec());
                    }
                    rows.push(serde_json::json!({"stress":stress,"master":seed,"turn":o.turns,"opponent_blind":blind,"policy":policies,"value":values,"x":encodings}));
                }
                let forced = if stress && state.turns() < 6 {
                    legal
                        .iter()
                        .copied()
                        .find(|a| matches!(a, Action::ReserveDeck(_)))
                } else {
                    None
                };
                let chosen = forced.unwrap_or_else(|| agent.select_action(&o, &legal));
                state.apply_action(chosen).unwrap();
            }
        }
    }
    std::fs::write(
        &args[2],
        serde_json::to_vec(
            &serde_json::json!({"source_id":env!("SPLENDOR_SOURCE_ID"),"views":8,"cohorts":"Strong play; first-six-turn blind-reservation stress","observations":rows}),
        )?,
    )?;
    Ok(())
}

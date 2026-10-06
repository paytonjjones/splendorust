use splendor_agents::{Agent, StrongHeuristicAgent, belief, transfer};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::path::Path;

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes = std::fs::read(root.join(
        "web/public/models/57f6e227f8ac0382b7fa67dba6b58ec6663d1f635c7b9f583937867cd6692deb.bin",
    ))
    .unwrap();
    let model = transfer::Model::from_bytes(&bytes);
    let mut rows = Vec::new();
    for seed in [17798000000, 17798000001] {
        let mut state = GameState::new(2, seed).unwrap();
        let mut heuristic = StrongHeuristicAgent;
        let mut rng = Rng::new(seed ^ 0x574542475055);
        for ply in 0..48 {
            if state.is_terminal() {
                break;
            }
            let o = state.observe(state.current_player());
            let mut legal = ActionSet::new();
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            if state.phase() == Phase::Main && state.turns().is_multiple_of(4) {
                let x = transfer::encode(&o, &mut rng);
                let context = transfer::public_context(&o);
                let (mean, public) = belief::moments(&x, &context);
                let mut input = [0.0; 525];
                input[..392].copy_from_slice(&mean);
                input[392..519].copy_from_slice(&public[392..]);
                let tokens = transfer::entity_tokens(&input);
                let (logits, values) = model.infer_with_profile(&x, &context, false);
                rows.push(serde_json::json!({"seed": seed.to_string(), "ply": ply, "turn": state.turns(), "tokens": tokens, "logits": logits.as_slice(), "values": values}));
            }
            let action = heuristic.select_action(&o, &legal);
            state.apply_action(action).unwrap();
        }
    }
    let path = root.join("research/webgpu-20261006/fixtures.json");
    std::fs::write(&path, serde_json::to_string(&rows).unwrap() + "\n").unwrap();
    println!("Saved {} public fixtures to {}", rows.len(), path.display());
}

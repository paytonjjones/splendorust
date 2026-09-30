use splendor_agents::learned::{FEATURES, predict};
use splendor_core::{ActionSet, GameState, Rng};
use std::{hint::black_box, time::Instant};
fn main() {
    let mut state = GameState::new(2, 42).unwrap();
    let mut rng = Rng::new(912);
    let mut positions = Vec::new();
    let mut legal = ActionSet::new();
    for _ in 0..100 {
        state.legal_actions(&mut legal);
        if legal.is_empty() {
            break;
        }
        positions.push(state.observe(state.current_player()));
        state.apply_action(legal[rng.index(legal.len())]).unwrap();
    }
    let weights = [0.1; FEATURES];
    let start = Instant::now();
    for i in 0..1_000_000 {
        let o = &positions[i % positions.len()];
        black_box(predict(
            black_box(o),
            o.viewer as usize,
            black_box(&weights),
        ));
    }
    println!(
        "{}",
        serde_json::json!({"calls":1000000,"seconds":start.elapsed().as_secs_f64(),"positions":positions.len(),"weight_bytes":std::mem::size_of_val(&weights),"source":env!("SPLENDOR_SOURCE_ID")})
    );
}

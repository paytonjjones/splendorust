//! Verify retained canonical actions without running a policy or revealing state.
use serde_json::{Value, json};
use splendor_arena::decode;
use splendor_core::GameState;
use std::io::{self, BufRead, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let stdin = io::stdin();
    let mut out = io::stdout().lock();
    for line in stdin.lock().lines() {
        let v: Value = serde_json::from_str(&line?)?;
        let mut state = GameState::new(
            u8::try_from(v["players"].as_u64().ok_or("players")?)?,
            v["seed"].as_u64().ok_or("seed")?,
        )?;
        for x in v["actions"].as_array().ok_or("actions")? {
            state.apply_action(decode(serde_json::from_value(x.clone())?)?)?;
            state.check_invariants()?;
        }
        let o = state.observe(state.current_player());
        writeln!(
            out,
            "{}",
            json!({"scores":o.players[..o.count as usize].iter().map(|p|p.score).collect::<Vec<_>>(),"turns":o.turns,
            "winners":state.outcome().map(|x|x.winners)})
        )?;
        out.flush()?;
    }
    Ok(())
}

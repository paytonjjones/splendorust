//! Full-state validation process. Never used to choose benchmark moves.
mod native_wire;
use serde_json::{Value, json};
use splendor_agents::native_environment::State;
use splendor_core::Rng;
use std::io::{self, BufRead, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut out = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let v: Value = serde_json::from_str(&line?)?;
        let result: Result<Value, Box<dyn std::error::Error>> = (|| {
            let o = native_wire::read(v["observation"].clone())?;
            let ids: [Vec<u8>; 3] = serde_json::from_value(v["decks"].clone())?;
            let mut decks = [0u128; 3];
            for (mask, ids) in decks.iter_mut().zip(ids) {
                for id in ids {
                    if id >= 90 || *mask & (1u128 << id) != 0 {
                        return Err("invalid fixture deck".into());
                    }
                    *mask |= 1u128 << id;
                }
            }
            let mut s = State::from_fixture(o, decks)?;
            if !v["action"].is_null() {
                s.apply(
                    u8::try_from(v["action"].as_u64().ok_or("action")?)?,
                    &mut Rng::new(0),
                    Some(v["chance_seed"].as_u64().ok_or("chance seed")?),
                )?;
            }
            Ok(
                json!({"observations":[native_wire::write(&s.observe(0)),native_wire::write(&s.observe(1))],"legal":s.legal(),"features":s.features().as_slice(),"rewards":s.rewards()}),
            )
        })();
        writeln!(
            out,
            "{}",
            result.unwrap_or_else(|e| json!({"error":e.to_string()}))
        )?;
        out.flush()?;
    }
    Ok(())
}

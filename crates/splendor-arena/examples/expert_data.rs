//! Convert independent expert match records to redacted observation supervision.
use splendor_agents::neural::{ACTIONS, action_index, baseline_logit, enhanced_features};
use splendor_arena::decode;
use splendor_core::{ActionSet, GameState, Phase};
use std::io::{BufRead, BufReader, BufWriter, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    let mut lines = BufReader::new(std::fs::File::open(&a[1])?).lines();
    let header: serde_json::Value = serde_json::from_str(&lines.next().ok_or("missing header")??)?;
    if header["players"] != 2 || header["external"] != "alphazero" {
        return Err("two-player AlphaZero records required".into());
    }
    // Block the frozen external evaluation schedules at the data boundary.
    let master = header["seed"].as_u64().ok_or("seed")?;
    if master < 100_000_000 {
        return Err("reserved benchmark schedules cannot be training data".into());
    }
    let mut out = BufWriter::new(std::fs::File::create(&a[2])?);
    let mut rows = 0;
    let mut games = 0;
    let mut complete = 0;
    for line in lines {
        let r: serde_json::Value = serde_json::from_str(&line?)?;
        games += 1;
        let setup = r["setup_seed"].as_u64().ok_or("setup seed")?;
        let seats = r["seats"].as_array().ok_or("seats")?;
        let mut s = GameState::new(2, setup)?;
        let mut legal = ActionSet::new();
        let mut samples = Vec::new();
        for encoded in r["actions"].as_array().ok_or("actions")? {
            let encoded: [u8; 7] = serde_json::from_value(encoded.clone())?;
            let action = decode(encoded)?;
            s.legal_actions(&mut legal);
            if s.phase() == Phase::Main {
                let o = s.observe(s.current_player());
                let mut mask = [0f32; ACTIONS];
                let mut policy = [0f32; ACTIONS];
                for &a in &legal {
                    mask[action_index(a).unwrap()] = 1.0;
                }
                if seats[s.current_player()] == "alphazero" {
                    policy[action_index(action).ok_or("not a main action")?] = 1.0;
                }
                samples.push((
                    s.current_player(),
                    enhanced_features(&o),
                    mask,
                    policy,
                    baseline_logit(&o),
                ));
            }
            s.apply_action(action)?;
        }
        s.check_invariants()?;
        let result = if r["status"] == "complete" {
            complete += 1;
            Some(s.outcome().ok_or("false terminal record")?)
        } else {
            None
        };
        for (seat, x, mask, policy, baseline) in samples {
            let outcome = result
                .map(|r| {
                    if r.winners & (1 << seat) != 0 {
                        1.0 / r.winners.count_ones() as f32
                    } else {
                        0.0
                    }
                })
                .unwrap_or(f32::NAN);
            out.write_all(&setup.to_le_bytes())?;
            // NaN teacher marks expert rows: only genuine outcomes train the value head.
            for value in
                x.into_iter()
                    .chain(mask)
                    .chain(policy)
                    .chain([f32::NAN, baseline, outcome])
            {
                out.write_all(&value.to_le_bytes())?;
            }
            rows += 1;
        }
    }
    assert_eq!(
        games,
        header["games"].as_u64().unwrap() as usize,
        "incomplete scheduled file"
    );
    out.flush()?;
    println!(
        "{}",
        serde_json::json!({"games":games,"complete":complete,"incomplete":games-complete,"rows":rows,"source":env!("SPLENDOR_SOURCE_ID"),"setup_master":master,"policy_source":"alphazero only; opponent rows have zero policy weight","value_source":"verified canonical terminal outcome only; missing remains NaN","row_bytes":1844})
    );
    Ok(())
}

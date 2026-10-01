//! Explicit privileged-information benchmark worker. Never accepts deck order.
mod native_wire;
use serde_json::{Value, json};
use splendor_agents::{
    Agent, SearchConfig,
    neural_search::NeuralAgent,
    privileged_environment::{Observation as PrivilegedObservation, PrivilegedNative},
    transfer::Model,
};
use std::io::{self, BufRead, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let model_path = std::env::args().nth(1).ok_or("model path required")?;
    let model = Box::leak(Box::new(Model::from_bytes(&std::fs::read(model_path)?)));
    let mut agent = NeuralAgent::new(0, SearchConfig::default());
    let mut out = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let v: Value = serde_json::from_str(&line?)?;
        let result: Result<Value, Box<dyn std::error::Error>> = (|| match v["op"]
            .as_str()
            .ok_or("op")?
        {
            "reset" => {
                agent = NeuralAgent::new(
                    v["seed"].as_u64().ok_or("policy seed")?,
                    SearchConfig {
                        iterations: u32::try_from(v["iterations"].as_u64().ok_or("iterations")?)?,
                        depth: u32::try_from(v["depth"].as_u64().ok_or("depth")?)?,
                        ..Default::default()
                    },
                );
                agent.transferred = true;
                agent.external_model = Some(model);
                agent.world_pool = 3;
                agent.cpuct = 0.4;
                agent.fpu_reduction = 0.02965;
                agent.uniform_prior = 0.;
                agent.root_only = v["root_only"].as_bool().unwrap_or(false);
                match v["search"].as_str().unwrap_or("puct") {
                    "puct" => {}
                    "gumbel" => {
                        agent.gumbel = true;
                        agent.gumbel_noise = 0.0;
                    }
                    _ => return Err("unknown search profile".into()),
                }
                Ok(json!({"ok":true}))
            }
            "choose" => {
                let o = read_partition(&v)?;
                if o.observation.viewer != o.observation.current {
                    return Err("actor observation required".into());
                }
                let legal: Vec<u8> = serde_json::from_value(v["legal"].clone())?;
                let generated = o.state()?.legal();
                if legal != generated {
                    return Err("native legal set mismatch".into());
                }
                let before = agent.work_counts();
                let action = agent.select_environment::<PrivilegedNative>(&o, &legal);
                let after = agent.work_counts();
                Ok(
                    json!({"action":action,"simulations":after.0-before.0,"inferences":after.1-before.1}),
                )
            }
            "sample" => {
                let o = read_partition(&v)?;
                let state = o.state()?;
                Ok(
                    json!({"features":state.features().as_slice(), "model_features":state.model_features().as_slice(),"public_observation":native_wire::write(&state.observe(o.observation.viewer))}),
                )
            }
            _ => Err("unknown policy operation".into()),
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

fn read_partition(v: &Value) -> Result<PrivilegedObservation, Box<dyn std::error::Error>> {
    let allowed = if v["op"] == "choose" {
        vec!["op", "observation", "decks", "legal"]
    } else {
        vec!["op", "observation", "decks"]
    };
    if v.as_object()
        .ok_or("object required")?
        .keys()
        .any(|k| !allowed.contains(&k.as_str()))
    {
        return Err("unknown privileged request field".into());
    }
    let observation = native_wire::read(v["observation"].clone())?;
    let ids: [Vec<u8>; 3] = serde_json::from_value(v["decks"].clone())?;
    let mut decks = [0u128; 3];
    for (mask, ids) in decks.iter_mut().zip(ids) {
        for id in ids {
            if id >= 90 || *mask & (1u128 << id) != 0 {
                return Err("invalid unordered deck membership".into());
            }
            *mask |= 1u128 << id;
        }
    }
    let o = PrivilegedObservation { observation, decks };
    o.state()?;
    Ok(o)
}

//! The policy process accepts only public native observations, never fixtures.
mod native_wire;
use serde_json::{Value, json};
use splendor_agents::{
    Agent, SearchConfig, environment::AlphaZeroNative, neural_search::NeuralAgent, transfer::Model,
};
use splendor_core::Rng;
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
                let o = native_wire::read(v["observation"].clone())?;
                o.validate()?;
                if o.viewer != o.current {
                    return Err("actor observation required".into());
                }
                let legal: Vec<u8> = serde_json::from_value(v["legal"].clone())?;
                let generated = o.determinize(&mut Rng::new(0))?.legal();
                if legal != generated {
                    return Err("native legal set mismatch".into());
                }
                let before = agent.work_counts();
                let action = agent.select_environment::<AlphaZeroNative>(&o, &legal);
                let after = agent.work_counts();
                Ok(
                    json!({"action":action,"simulations":after.0-before.0,"inferences":after.1-before.1}),
                )
            }
            "sample" => {
                let o = native_wire::read(v["observation"].clone())?;
                let sample =
                    o.determinize(&mut Rng::new(v["seed"].as_u64().ok_or("sampling seed")?))?;
                Ok(
                    json!({"features":sample.features().as_slice(),"observation":native_wire::write(&sample.observe(o.viewer))}),
                )
            }
            "observe" => {
                let before = native_wire::read(v["before"].clone())?;
                let after = native_wire::read(v["after"].clone())?;
                before.validate()?;
                after.validate()?;
                let action = u8::try_from(v["action"].as_u64().ok_or("public action")?)?;
                if before.viewer != after.viewer {
                    return Err("history viewer changed".into());
                }
                let event = if model.uses_full_public_history()
                    || v["history_version"].as_u64() == Some(2)
                {
                    splendor_agents::public_history::native_v2(&before, action, &after)
                } else {
                    splendor_agents::public_history::native(&before, action, &after)
                };
                agent.observe_event(event);
                if v["include_event"].as_bool().unwrap_or(false) {
                    Ok(json!({"ok":true,"public_event":event.as_slice(),
                        "public_pool":splendor_agents::public_history::native_pool(&before).as_slice()}))
                } else {
                    Ok(json!({"ok":true}))
                }
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

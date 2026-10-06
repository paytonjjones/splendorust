//! The policy process accepts only public native observations, never fixtures.
mod native_wire;
use serde_json::{Value, json};
use splendor_agents::{
    Agent, SearchConfig, environment::AlphaZeroNative, neural_search::NeuralAgent, transfer::Model,
};
use splendor_core::Rng;
use std::io::{self, BufRead, Write};

const DEFAULT_WORLD_POOL: u64 = 3;
const DEFAULT_GUMBEL_MAX_CONSIDERED: u64 = 16;
const DEFAULT_CHANCE_UNIVERSES: u64 = 0;
const MAX_WORLD_POOL: u64 = 64;
const MAX_CHANCE_UNIVERSES: u64 = 64;
const MAX_GUMBEL_MAX_CONSIDERED: u64 = 81;
const MAX_DEPTH: u32 = 124;

fn optional_u64(v: &Value, key: &str, default: u64) -> Result<u64, io::Error> {
    if v.get(key).is_none_or(Value::is_null) {
        Ok(default)
    } else {
        v[key].as_u64().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("{key} must be an unsigned integer"),
            )
        })
    }
}

fn optional_bool(v: &Value, key: &str, default: bool) -> Result<bool, io::Error> {
    if v.get(key).is_none_or(Value::is_null) {
        Ok(default)
    } else {
        v[key].as_bool().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("{key} must be a boolean"),
            )
        })
    }
}

fn validate_controls(
    world_pool: u64,
    gumbel_max_considered: u64,
    chance_universes: u64,
) -> Result<(), io::Error> {
    if world_pool > MAX_WORLD_POOL {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("world_pool must be at most {MAX_WORLD_POOL}"),
        ));
    }
    if !(1..=MAX_GUMBEL_MAX_CONSIDERED).contains(&gumbel_max_considered) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("gumbel_max_considered must be in 1..={MAX_GUMBEL_MAX_CONSIDERED}"),
        ));
    }
    if chance_universes > MAX_CHANCE_UNIVERSES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("chance_universes must be at most {MAX_CHANCE_UNIVERSES}"),
        ));
    }
    Ok(())
}

fn validate_depth(depth: u32) -> Result<(), io::Error> {
    if !(1..=MAX_DEPTH).contains(&depth) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("depth must be in 1..={MAX_DEPTH}"),
        ));
    }
    Ok(())
}

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
                let iterations = u32::try_from(v["iterations"].as_u64().ok_or("iterations")?)?;
                let depth = u32::try_from(v["depth"].as_u64().ok_or("depth")?)?;
                validate_depth(depth)?;
                let world_pool = optional_u64(&v, "world_pool", DEFAULT_WORLD_POOL)?;
                let gumbel_max_considered =
                    optional_u64(&v, "gumbel_max_considered", DEFAULT_GUMBEL_MAX_CONSIDERED)?;
                let chance_universes =
                    optional_u64(&v, "chance_universes", DEFAULT_CHANCE_UNIVERSES)?;
                let dynamic_fpu = optional_bool(&v, "dynamic_fpu", false)?;
                validate_controls(world_pool, gumbel_max_considered, chance_universes)?;
                let world_pool = usize::try_from(world_pool)?;
                let gumbel_max_considered = usize::try_from(gumbel_max_considered)?;
                let chance_universes = usize::try_from(chance_universes)?;
                let search = v["search"].as_str().unwrap_or("puct");
                if !matches!(search, "puct" | "gumbel") {
                    return Err(format!("unknown search profile: {search}").into());
                }
                let root_only = v["root_only"].as_bool().unwrap_or(false);
                agent = NeuralAgent::new(
                    v["seed"].as_u64().ok_or("policy seed")?,
                    SearchConfig {
                        iterations,
                        depth,
                        ..Default::default()
                    },
                );
                agent.transferred = true;
                agent.external_model = Some(model);
                agent.world_pool = world_pool;
                agent.chance_universes = chance_universes;
                agent.dynamic_fpu = dynamic_fpu;
                agent.cpuct = 0.4;
                agent.fpu_reduction = 0.02965;
                agent.uniform_prior = 0.;
                agent.root_only = root_only;
                agent.gumbel_max_considered = gumbel_max_considered;
                if search == "gumbel" {
                    agent.gumbel = true;
                    agent.gumbel_noise = 0.0;
                }
                Ok(json!({"ok":true,"settings":{
                    "iterations":iterations,
                    "depth":depth,
                    "world_pool":world_pool,
                    "chance_universes":chance_universes,
                    "dynamic_fpu":dynamic_fpu,
                    "gumbel_max_considered":gumbel_max_considered,
                    "search":search,
                    "root_only":root_only,
                    "gumbel_noise":0.0,
                    "cpuct":0.4,
                    "fpu_reduction":0.02965,
                    "uniform_prior":0.0
                }}))
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

#[cfg(test)]
mod tests {
    use super::{
        DEFAULT_CHANCE_UNIVERSES, DEFAULT_GUMBEL_MAX_CONSIDERED, DEFAULT_WORLD_POOL, MAX_DEPTH,
        optional_bool, optional_u64, validate_controls, validate_depth,
    };
    use serde_json::json;

    #[test]
    fn optional_search_controls_keep_defaults_for_old_reset_requests() {
        let request = json!({"op":"reset", "iterations":128, "depth":16});
        assert_eq!(
            optional_u64(&request, "world_pool", DEFAULT_WORLD_POOL).unwrap(),
            3
        );
        assert_eq!(
            optional_u64(
                &request,
                "gumbel_max_considered",
                DEFAULT_GUMBEL_MAX_CONSIDERED
            )
            .unwrap(),
            16
        );
        assert_eq!(
            optional_u64(&request, "chance_universes", DEFAULT_CHANCE_UNIVERSES).unwrap(),
            0
        );
        assert!(!optional_bool(&request, "dynamic_fpu", false).unwrap());
        validate_controls(3, 16, 0).unwrap();
    }

    #[test]
    fn dynamic_fpu_requires_a_boolean_and_defaults_off() {
        assert!(!optional_bool(&json!({}), "dynamic_fpu", false).unwrap());
        assert!(optional_bool(&json!({"dynamic_fpu": true}), "dynamic_fpu", false).unwrap());
        assert!(!optional_bool(&json!({"dynamic_fpu": false}), "dynamic_fpu", true).unwrap());
        assert!(optional_bool(&json!({"dynamic_fpu": 1}), "dynamic_fpu", false).is_err());
        assert!(optional_bool(&json!({"dynamic_fpu": "true"}), "dynamic_fpu", false).is_err());
    }

    #[test]
    fn search_control_ranges_reject_invalid_values() {
        for (world_pool, considered, chance) in [(65, 16, 0), (3, 0, 0), (3, 82, 0), (3, 16, 65)] {
            assert!(validate_controls(world_pool, considered, chance).is_err());
        }
        for (world_pool, considered, chance) in [(0, 1, 0), (64, 81, 64), (3, 16, 3)] {
            validate_controls(world_pool, considered, chance).unwrap();
        }
        let negative = json!({"world_pool": -1});
        assert!(optional_u64(&negative, "world_pool", 3).is_err());
    }

    #[test]
    fn depth_range_matches_native_game_horizon() {
        for depth in [1, MAX_DEPTH] {
            validate_depth(depth).unwrap();
        }
        for depth in [0, MAX_DEPTH + 1] {
            assert!(validate_depth(depth).is_err());
        }
    }
}

//! Observation-only strength adapter. Default engine and policies are unchanged.
use serde_json::{Value, json};
use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{decode, encode};
use splendor_core::{
    ActionSet, GameState, Observation, Rng,
    data::{CARDS, NOBLES},
};
use std::io::{self, BufRead, Write};

fn observation(o: &Observation) -> Value {
    json!({"count":o.count,"current":o.current,"viewer":o.viewer,"bank":o.bank,
        "market":o.market,"remaining":o.remaining,"turns":o.turns,"phase":format!("{:?}",o.phase),
        "nobles":(0..10).filter(|i| o.nobles & (1<<i)!=0).collect::<Vec<_>>(),
        "players":o.players[..o.count as usize].iter().enumerate().map(|(i,p)|json!({
            "tokens":p.tokens,"bonuses":p.bonuses,"score":p.score,
            "owned":(0..90).filter(|n|p.owned & (1u128<<n)!=0).collect::<Vec<_>>(),
            "nobles":(0..10).filter(|n|p.nobles & (1<<n)!=0).collect::<Vec<_>>(),
            "reserved_count":o.reserved_counts[i],
            "reserved":p.reserved.iter().map(|r|json!({"card":r.card,"tier":r.tier,"public":r.public})).collect::<Vec<_>>()
        })).collect::<Vec<_>>()})
}
fn sample(o: &Observation, rng: &mut Rng) -> Result<Value, splendor_core::RuleError> {
    let world = o.determinize(rng)?;
    assert_eq!(*o, world.observe(o.viewer as usize));
    let mut public = observation(o);
    for i in 0..o.count as usize {
        public["players"][i]["reserved"] =
            observation(&world.observe(i))["players"][i]["reserved"].clone();
    }
    public["sampled_hidden_world"] = json!(true);
    Ok(public)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut state = GameState::new(2, 0)?;
    let mut agents = Vec::new();
    let mut sampling = Rng::new(0);
    let stdin = io::stdin();
    let mut stdout = io::stdout().lock();
    for line in stdin.lock().lines() {
        let v: Value = serde_json::from_str(&line?)?;
        let result: Result<Value, Box<dyn std::error::Error>> = (|| match v["op"]
            .as_str()
            .ok_or("op missing")?
        {
            "data" => Ok(
                json!({"cards":CARDS.iter().map(|c|json!({"tier":c.tier,"bonus":c.bonus,"points":c.points,"cost":c.cost})).collect::<Vec<_>>(),
                    "nobles":NOBLES.iter().map(|n|json!({"cost":n,"points":3})).collect::<Vec<_>>(),
                    "source_id":env!("SPLENDOR_SOURCE_ID"),"engine":splendor_core::ENGINE_VERSION}),
            ),
            "reset" => {
                let count = v["players"].as_u64().ok_or("players")?;
                state = GameState::new(u8::try_from(count)?, v["seed"].as_u64().ok_or("seed")?)?;
                sampling = Rng::new(v["sampling_seed"].as_u64().ok_or("sampling_seed")?);
                agents.clear();
                let config = SearchConfig {
                    iterations: u32::try_from(v["iterations"].as_u64().ok_or("iterations")?)?,
                    depth: u32::try_from(v["depth"].as_u64().unwrap_or(8))?,
                    ..Default::default()
                };
                for (i, name) in v["seats"].as_array().ok_or("seats")?.iter().enumerate() {
                    let name = name.as_str().ok_or("agent name")?;
                    let name = if name == "alphazero" || name == "seal256" {
                        "random"
                    } else {
                        name
                    };
                    agents.push(make_agent(
                        name,
                        v["agent_seeds"][i].as_u64().ok_or("agent_seeds")?,
                        &config,
                    )?);
                }
                Ok(json!({"ok":true}))
            }
            "observe" => {
                let o = state.observe(state.current_player());
                let mut legal = ActionSet::new();
                state.legal_actions(&mut legal);
                Ok(
                    json!({"observation":observation(&o),"legal":legal.iter().copied().map(encode).collect::<Vec<_>>(),
                        "outcome":state.outcome().map(|x|json!({"winners":x.winners,"scores":x.scores[..state.player_count()].to_vec()}))}),
                )
            }
            "sample" => Ok(sample(
                &state.observe(state.current_player()),
                &mut sampling,
            )?),
            "select" => {
                let mut legal = ActionSet::new();
                state.legal_actions(&mut legal);
                if legal.is_empty() {
                    return Err("no legal action".into());
                }
                let a = agents[state.current_player()]
                    .select_action(&state.observe(state.current_player()), &legal);
                if !legal.contains(&a) {
                    return Err("agent selected illegal action".into());
                }
                Ok(json!({"action":encode(a)}))
            }
            "apply" => {
                let a = decode(serde_json::from_value(v["action"].clone())?)?;
                state.apply_action(a)?;
                state.check_invariants()?;
                Ok(json!({"ok":true}))
            }
            _ => Err("unknown op".into()),
        })();
        let out = match result {
            Ok(x) => x,
            Err(e) => json!({"error":e.to_string()}),
        };
        writeln!(stdout, "{out}")?;
        stdout.flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn equal_observations_produce_equal_external_inputs() {
        let mut s = GameState::new(2, 47).unwrap();
        s.apply_action(splendor_core::Action::ReserveDeck(0))
            .unwrap();
        let o = s.observe(1);
        let a = o.determinize(&mut Rng::new(10)).unwrap();
        let b = o.determinize(&mut Rng::new(11)).unwrap();
        assert_ne!(a, b);
        assert_eq!(a.observe(1), b.observe(1));
        assert_eq!(
            sample(&a.observe(1), &mut Rng::new(99)).unwrap(),
            sample(&b.observe(1), &mut Rng::new(99)).unwrap()
        );
        assert_eq!(o.players[0].reserved[0].card, splendor_core::NONE);
        let input = sample(&o, &mut Rng::new(100)).unwrap();
        assert!(input.get("seed").is_none());
        assert!(input.get("decks").is_none());
    }
}

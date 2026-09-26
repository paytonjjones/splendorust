//! Offline replay diagnosis; observations below are not passed to another agent.
use serde_json::{Value, json};
use splendor_arena::{RunConfig, decode, play_game, replay};
use splendor_core::{Action, ActionSet, GOLD, NONE, Observation, Phase, data::CARDS};
use std::collections::VecDeque;

fn affordable_take(o: &Observation, a: Action) -> bool {
    let Action::Take(t) = a else { return false };
    let mut p = o.players[o.current as usize];
    for (c, v) in t.into_iter().enumerate() {
        p.tokens[c] += v;
    }
    p.token_count() <= 10
        && o.market
            .iter()
            .copied()
            .chain(p.reserved.iter().map(|r| r.card))
            .filter(|&id| id != NONE)
            .any(|id| {
                (0..5)
                    .map(|c| {
                        u16::from(
                            CARDS[id as usize].cost[c]
                                .saturating_sub(p.bonuses[c])
                                .saturating_sub(p.tokens[c]),
                        )
                    })
                    .sum::<u16>()
                    <= u16::from(p.tokens[GOLD])
            })
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let screen: Value =
        serde_json::from_slice(&std::fs::read(args.next().ok_or("screen report")?)?)?;
    let control: Value =
        serde_json::from_slice(&std::fs::read(args.next().ok_or("control report")?)?)?;
    let output = std::path::PathBuf::from(args.next().ok_or("new output directory")?);
    std::fs::create_dir(&output)?;
    assert_eq!(screen["source_id"], env!("SPLENDOR_SOURCE_ID"));
    let mut config: RunConfig = serde_json::from_value(screen["run_config"].clone())?;
    let mut base: RunConfig = serde_json::from_value(control["run_config"].clone())?;
    config.check = true;
    base.check = true;
    for block in [223, 237, 855] {
        let expected = screen["records"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["block"] == block && r["status"] == "no_legal_action")
            .unwrap();
        let rotation = expected["rotation"].as_u64().unwrap() as usize;
        let seed = expected["seed"].as_u64().unwrap();
        let baseline_expected = &control["records"][block * 2 + rotation];
        let (record, history) = play_game(&config, block, rotation, seed, true)?;
        let (baseline, baseline_history) = play_game(&base, block, rotation, seed, true)?;
        assert_eq!(serde_json::to_value(&record)?, *expected);
        assert_eq!(serde_json::to_value(&baseline)?, *baseline_expected);
        let history = history.unwrap();
        let baseline_history = baseline_history.unwrap();
        std::fs::write(
            output.join(format!("{block}-candidate.json")),
            serde_json::to_vec(&history)?,
        )?;
        std::fs::write(
            output.join(format!("{block}-control.json")),
            serde_json::to_vec(&baseline_history)?,
        )?;
        let divergence = history
            .actions
            .iter()
            .zip(&baseline_history.actions)
            .position(|(a, b)| a != b);
        let mut prefix = history.clone();
        prefix.actions.clear();
        prefix.state_debug.clear();
        let mut state = replay(&prefix)?;
        let mut main = VecDeque::new();
        let mut returns = VecDeque::new();
        let mut events = Vec::new();
        let mut tail = Vec::new();
        let mut later_purchases = Vec::new();
        let mut legal = ActionSet::new();
        for (index, encoded) in history.actions.iter().enumerate() {
            state.legal_actions(&mut legal);
            let actor = state.current_player();
            let identity = (actor + rotation) % 2;
            let o = state.observe(actor);
            let purchases = legal
                .iter()
                .filter(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                .count();
            if identity == 0 && matches!(o.phase, Phase::Main | Phase::Return) {
                let recent = if o.phase == Phase::Main {
                    &mut main
                } else {
                    &mut returns
                };
                let mut normalized = o.clone();
                normalized.turns = 0;
                let repeated = recent.contains(&normalized);
                if recent.len() == 16 {
                    recent.pop_front();
                }
                recent.push_back(normalized);
                let affordable: Vec<_> = legal
                    .iter()
                    .copied()
                    .filter(|&a| affordable_take(&o, a))
                    .collect();
                let scarcity = o.reserved_counts[actor] == 3
                    && o.bank[..5].iter().map(|&v| u16::from(v)).sum::<u16>() <= 10
                    && legal.iter().all(|a| matches!(a, Action::Take(_)))
                    && !affordable.is_empty();
                if repeated || scarcity {
                    events.push(json!({"index":index,"phase":format!("{:?}",o.phase),"repeated":repeated,
                        "scarcity_eligible":scarcity,"affordable_takes":format!("{affordable:?}"),"purchases":purchases,
                        "action":encoded,"legal_count":legal.len(),"observation":format!("{o:?}")}));
                }
            }
            if index + 8 >= history.actions.len() {
                tail.push(json!({"index":index,"identity":identity,
                "phase":format!("{:?}",o.phase),"legal":format!("{legal:?}"),"action":encoded}));
            }
            if divergence.is_some_and(|d| index > d) {
                let id = match decode(*encoded)? {
                    Action::BuyVisible(i) => Some(o.market[i as usize]),
                    Action::BuyReserved(i) => Some(o.players[actor].reserved[i as usize].card),
                    _ => None,
                };
                if let Some(id) = id {
                    later_purchases.push(json!({"index":index,"identity":identity,"card":id}));
                }
            }
            state.apply_action(decode(*encoded)?)?;
            state.check_invariants()?;
        }
        state.legal_actions(&mut legal);
        assert!(legal.is_empty());
        assert_eq!(state.outcome(), None);
        println!(
            "{}",
            json!({"record":record,"control_record":baseline,"first_action_divergence":divergence,
            "blocked_identity":(state.current_player()+rotation)%2,"candidate_condition_events":events,"tail":tail,"later_purchases":later_purchases})
        );
    }
    Ok(())
}

//! Reproduce capped records and check short legal token cycles.
//! Optional `no_legal_action` mode records blocked endpoints and nearby choices.
//! Diagnostic full-state access only; never an agent or a termination rule.
use serde_json::{Value, json};
use splendor_arena::{Report, decode, play_game, replay};
use splendor_core::{Action, ActionSet, GameState, Phase};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let report: Value = serde_json::from_slice(&std::fs::read(args.next().ok_or("report path")?)?)?;
    let output = std::path::PathBuf::from(args.next().ok_or("new output directory")?);
    let status = args.next().unwrap_or_else(|| "decision_limit".into());
    if !matches!(status.as_str(), "decision_limit" | "no_legal_action") {
        return Err("status must be decision_limit or no_legal_action".into());
    }
    let checked: Report = serde_json::from_value(report.clone())?;
    let mut config = checked.verification_config()?;
    std::fs::create_dir(&output)?;
    let players = config.names.len();
    config.check = true;
    for expected in report["records"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["status"] == status)
    {
        let block = expected["block"].as_u64().ok_or("invalid block")?;
        let rotation = expected["rotation"].as_u64().unwrap() as usize;
        let seed = expected["seed"].as_u64().unwrap();
        let (record, history) = play_game(&config, block as usize, rotation, seed, true)?;
        assert_eq!(serde_json::to_value(&record)?, *expected);
        let history = history.unwrap();
        std::fs::write(
            output.join(format!("{block}-{rotation}.json")),
            serde_json::to_vec(&history)?,
        )?;
        let n = history.actions.len();
        let end = replay(&history)?;
        if status == "no_legal_action" {
            let mut legal = ActionSet::new();
            end.legal_actions(&mut legal);
            assert!(legal.is_empty());
            assert!(!end.is_terminal());
            assert_eq!(end.outcome(), None);
            let mut state = GameState::new(players as u8, seed)?;
            let mut tail = Vec::new();
            for (index, &encoded) in history.actions.iter().enumerate() {
                if index >= n.saturating_sub(12) {
                    state.legal_actions(&mut legal);
                    let mut alternatives = Vec::new();
                    for &action in &legal {
                        let mut next = state.clone();
                        next.apply_action(action)?;
                        next.check_invariants()?;
                        let mut following = ActionSet::new();
                        next.legal_actions(&mut following);
                        alternatives.push(json!({"action":splendor_arena::encode(action),
                            "next_phase":format!("{:?}",next.phase()),
                            "next_player":next.current_player(),"next_legal_count":following.len(),
                            "blocked_immediately":following.is_empty() && !next.is_terminal()}));
                    }
                    tail.push(
                        json!({"index":index,"identity":(state.current_player()+rotation)%players,
                        "phase":format!("{:?}",state.phase()),"action":encoded,
                        "observation":format!("{:?}",state.observe(state.current_player())),
                        "alternatives":alternatives}),
                    );
                }
                state.apply_action(decode(encoded)?)?;
                state.check_invariants()?;
            }
            println!(
                "{}",
                json!({"record":record,"blocked_player":end.current_player(),
                "blocked_identity":(end.current_player()+rotation)%players,
                "endpoint":format!("{:?}",end.observe(end.current_player())),"tail":tail,
                "scope":"Immediate alternative successors only; no forced-block or policy counterfactual claim."})
            );
            continue;
        }
        let period = (1..=16).find(|&p| {
            if n < 80 {
                return false;
            }
            if !(n - 64..n).all(|i| history.actions[i] == history.actions[i - p]) {
                return false;
            }
            let mut next = end.clone();
            for &encoded in &history.actions[n - p..] {
                let action = decode(encoded).unwrap();
                if !matches!(action, Action::Take(_) | Action::Return(_))
                    || next.apply_action(action).is_err()
                {
                    return false;
                }
            }
            (0..players).all(|viewer| {
                let mut a = end.observe(viewer);
                let mut b = next.observe(viewer);
                a.turns = 0;
                b.turns = 0;
                a == b
            })
        });
        let Some(period) = period else {
            println!(
                "{}",
                json!({"record":record,"period_decisions":null,
                "note":"No verified token-only period of at most 16 decisions in the final 64 actions; this is not proof of no recurrence."})
            );
            continue;
        };
        let mut start = n - period;
        while start > 0 && history.actions[start - 1] == history.actions[start - 1 + period] {
            start -= 1;
        }
        let mut state = GameState::new(players as u8, seed)?;
        let mut sample = Vec::new();
        let mut legal = ActionSet::new();
        for (index, encoded) in history.actions.iter().enumerate() {
            if index >= start && index < start + period {
                state.legal_actions(&mut legal);
                let purchases = legal
                    .iter()
                    .filter(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                    .count();
                sample.push(json!({"index":index,"identity":(state.current_player()+rotation)%players,
                    "phase":format!("{:?}",state.phase()),"legal_count":legal.len(),"purchases":purchases,
                    "action":encoded,"observation":format!("{:?}",state.observe(state.current_player()))}));
            }
            state.apply_action(decode(*encoded)?)?;
            state.check_invariants()?;
        }
        // The repeated suffix consists only of token movements, so hidden decks
        // and card identities cannot change. Verify one full period from the end.
        let mut before: Vec<_> = (0..players).map(|i| state.observe(i)).collect();
        let old_turns = state.turns();
        for encoded in &history.actions[n - period..] {
            let action = decode(*encoded)?;
            assert!(matches!(action, Action::Take(_) | Action::Return(_)));
            state.apply_action(action)?;
            state.check_invariants()?;
        }
        let mut after: Vec<_> = (0..players).map(|i| state.observe(i)).collect();
        for o in before.iter_mut().chain(after.iter_mut()) {
            o.turns = 0;
        }
        assert_eq!(before, after);
        assert_eq!(state.outcome(), None);
        assert!(matches!(state.phase(), Phase::Main | Phase::Return));
        println!(
            "{}",
            json!({"record":record,"period_decisions":period,"suffix_start":start,
            "suffix_decisions":n-start,"turns_per_period":state.turns()-old_turns,"cycle":sample})
        );
    }
    Ok(())
}

//! Export privileged complete-turn cases for the offline independent-engine audit.
//! These records are test data only and must never be supplied to an agent.
use serde_json::{Value, json};
use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{History, decode, encode, replay};
use splendor_core::{ActionSet, ENGINE_VERSION, GameState, NONE, Phase};
use std::io::{self, BufWriter, Write};

fn snapshot(state: &GameState) -> Value {
    let o = state.observe(state.current_player());
    let players: Vec<_> = (0..state.player_count())
        .map(|i| {
            let p = state.observe(i).players[i];
            json!({"tokens": p.tokens, "bonuses": p.bonuses, "score": p.score,
                "owned": (0..90).filter(|c| p.owned & (1u128 << c) != 0).collect::<Vec<_>>(),
                "nobles": (0..10).filter(|n| p.nobles & (1 << n) != 0).collect::<Vec<_>>(),
                "reserved": p.reserved.iter().filter(|r| r.card != NONE)
                    .map(|r| json!({"card": r.card, "public": r.public})).collect::<Vec<_>>()})
        })
        .collect();
    json!({"players": players, "current": o.current, "bank": o.bank, "market": o.market,
        "remaining": o.remaining, "nobles": (0..10).filter(|n| o.nobles & (1 << n) != 0).collect::<Vec<_>>(),
        "terminal": state.is_terminal(), "final_round": o.final_round, "turns": o.turns,
        "winner_mask": state.outcome().map(|outcome| outcome.winners)})
}

fn complete_choices(
    state: &GameState,
    actor: usize,
    old_nobles: u16,
    path: &mut Vec<[u8; 7]>,
    out: &mut Vec<Value>,
    include_successors: bool,
) {
    if !path.is_empty() && matches!(state.phase(), Phase::Main | Phase::Terminal) {
        let gained = state.observe(actor).players[actor].nobles & !old_nobles;
        let mut choice = json!({"actions": path, "noble": if gained == 0 { NONE } else { gained.trailing_zeros() as u8 }});
        if include_successors {
            choice["after"] = snapshot(state);
        }
        out.push(choice);
        return;
    }
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    for action in legal {
        let mut next = state.clone();
        next.apply_action(action).expect("generated legal action");
        next.check_invariants().expect("branch invariants");
        path.push(encode(action));
        complete_choices(&next, actor, old_nobles, path, out, include_successors);
        path.pop();
    }
}

fn history_boundaries(file: &str, tier: usize) -> Result<(), Box<dyn std::error::Error>> {
    if tier > 2 {
        return Err("tier must be 0..=2".into());
    }
    let history: History = serde_json::from_slice(&std::fs::read(file)?)?;
    let end = replay(&history)?;
    if end.phase() != Phase::Main || end.observe(end.current_player()).remaining[tier] != 0 {
        return Err("history must end at a nonterminal exhausted-deck Main phase".into());
    }
    let mut state = GameState::new(history.players, history.seed)?;
    let mut out = BufWriter::new(io::stdout().lock());
    writeln!(
        out,
        "{}",
        json!({"format":2,"engine":ENGINE_VERSION,"source_id":env!("SPLENDOR_SOURCE_ID"),
        "choice_successors":true,"winner_checks":true,"choice_interval":0,"depletion_tier":tier})
    )?;
    let mut index = 0;
    loop {
        let before_state = state.clone();
        let before = snapshot(&state);
        let actor = state.current_player();
        let at_end = index == history.actions.len();
        let mut actions = Vec::new();
        if !at_end {
            loop {
                let encoded = history.actions[index];
                state.apply_action(decode(encoded)?)?;
                state.check_invariants()?;
                actions.push(encoded);
                index += 1;
                if matches!(state.phase(), Phase::Main | Phase::Terminal) {
                    break;
                }
            }
        }
        if before_state.observe(actor).remaining[tier] <= 1 {
            let mut choices = Vec::new();
            complete_choices(
                &before_state,
                actor,
                before_state.observe(actor).players[actor].nobles,
                &mut Vec::new(),
                &mut choices,
                true,
            );
            if at_end {
                // At the verified replay endpoint, select one enumerated legal
                // branch as the case's primary path; retain every alternative.
                let first = choices.first().ok_or("exhausted endpoint is blocked")?;
                actions = serde_json::from_value(first["actions"].clone())?;
                for &a in &actions {
                    state.apply_action(decode(a)?)?;
                    state.check_invariants()?;
                }
            }
            writeln!(
                out,
                "{}",
                json!({"seed":history.seed,"policy":"depletion-history",
                "endpoint_branch":at_end,"before":before,"actions":actions,"after":snapshot(&state),"choices":choices})
            )?;
        }
        if at_end {
            break;
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let first = args.next().unwrap_or_else(|| "20".into());
    if first == "--history" {
        let file = args.next().ok_or("missing history path")?;
        let tier = args.next().ok_or("missing zero-based tier")?.parse()?;
        return history_boundaries(&file, tier);
    }
    let games: u64 = first.parse()?;
    let seed: u64 = args.next().unwrap_or_else(|| "92000000".into()).parse()?;
    let choice_interval: u32 = args.next().unwrap_or_else(|| "0".into()).parse()?;
    let include_successors: bool = args.next().unwrap_or_else(|| "false".into()).parse()?;
    let boundary_choices: bool = args.next().unwrap_or_else(|| "false".into()).parse()?;
    if games == 0 {
        return Err("games must be positive".into());
    }
    let mut out = BufWriter::new(io::stdout().lock());
    let mut metadata = json!({"format": 1, "engine": ENGINE_VERSION,
        "source_id": env!("SPLENDOR_SOURCE_ID"), "games_per_player_count": games,
        "seed": seed, "choice_interval": choice_interval, "winner_checks": true});
    if include_successors {
        metadata["format"] = json!(2);
        metadata["choice_successors"] = json!(true);
    }
    if boundary_choices {
        metadata["boundary_choices"] = json!(true);
        metadata["noble_acquisition_choices"] = json!(true);
    }
    writeln!(out, "{metadata}")?;
    for count in 2..=4 {
        for game in 0..games {
            let setup = seed.wrapping_add(count as u64 * 1_000_000 + game);
            let mut state = GameState::new(count, setup)?;
            let policy = if game % 2 == 0 { "strong" } else { "random" };
            let mut agent = make_agent(policy, setup, &SearchConfig::default())?;
            for _ in 0..1000 {
                if state.is_terminal() {
                    break;
                }
                let before_state = state.clone();
                let before = snapshot(&state);
                let mut actions = Vec::new();
                loop {
                    let mut legal = ActionSet::new();
                    state.legal_actions(&mut legal);
                    if legal.is_empty() {
                        break;
                    }
                    let action =
                        agent.select_action(&state.observe(state.current_player()), &legal);
                    state.apply_action(action)?;
                    state.check_invariants()?;
                    actions.push(encode(action));
                    if matches!(state.phase(), Phase::Main | Phase::Terminal) {
                        break;
                    }
                }
                let boundary = boundary_choices
                    && (state.is_terminal()
                        || before_state.observe(before_state.current_player()).nobles
                            != state.observe(state.current_player()).nobles
                        || (!before_state
                            .observe(before_state.current_player())
                            .final_round
                            && state.observe(state.current_player()).final_round));
                let choices = if boundary
                    || (choice_interval > 0 && before_state.turns().is_multiple_of(choice_interval))
                {
                    let actor = before_state.current_player();
                    let mut paths = Vec::new();
                    complete_choices(
                        &before_state,
                        actor,
                        before_state.observe(actor).players[actor].nobles,
                        &mut Vec::new(),
                        &mut paths,
                        include_successors,
                    );
                    Some(paths)
                } else {
                    None
                };
                if actions.is_empty() {
                    writeln!(
                        out,
                        "{}",
                        json!({"seed": setup, "policy": policy,
                        "before": before, "choices": [], "actions": [], "after": snapshot(&state), "status": "no_legal_action"})
                    )?;
                    break;
                }
                writeln!(
                    out,
                    "{}",
                    json!({"seed": setup, "policy": policy,
                    "before": before, "choices": choices, "actions": actions, "after": snapshot(&state)})
                )?;
            }
        }
    }
    Ok(())
}

//! Public-information token features for a recorded decision; no agent change.
use serde_json::{Value, json};
use splendor_agents::action_score;
use splendor_arena::{History, encode, replay};
use splendor_core::{Action, ActionSet, GOLD, NONE, Observation, Player, data::CARDS};

fn targets(o: &Observation, p: &Player) -> Vec<Value> {
    o.market
        .iter()
        .copied()
        .map(|id| (id, false))
        .chain(p.reserved.iter().map(|r| (r.card, true)))
        .filter(|&(id, _)| id != NONE)
        .map(|(id, reserved)| {
            let deficits: [u8; 5] = std::array::from_fn(|c| {
                CARDS[id as usize].cost[c]
                    .saturating_sub(p.bonuses[c])
                    .saturating_sub(p.tokens[c])
            });
            let deficit: u16 = deficits.iter().map(|&v| u16::from(v)).sum();
            json!({"id": id, "reserved": reserved, "colored_deficits": deficits,
                "missing_after_gold": deficit.saturating_sub(u16::from(p.tokens[GOLD]))})
        })
        .collect()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let file = args.next().ok_or("usage: token_audit HISTORY PREFIX")?;
    let length: usize = args.next().ok_or("missing prefix")?.parse()?;
    let mut h: History = serde_json::from_slice(&std::fs::read(file)?)?;
    replay(&h)?;
    if length >= h.actions.len() {
        return Err("prefix must precede recorded action".into());
    }
    h.actions.truncate(length);
    h.state_debug.clear();
    let state = replay(&h)?;
    let o = state.observe(state.current_player());
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    // All feature inputs below come from this observation. No successor state
    // or hidden deck information is consulted.
    let mut takes = Vec::new();
    for action in legal {
        if let Action::Take(take) = action {
            let mut p = o.players[o.current as usize];
            let mut bank = o.bank;
            for c in 0..5 {
                p.tokens[c] += take[c];
                bank[c] -= take[c];
            }
            takes.push(
                json!({"action": encode(action), "strong_score": action_score(&o, action, true),
                "tokens_before_return": p.tokens, "return_required": p.token_count() > 10,
                "bank_after_take": bank, "targets_before_return": targets(&o, &p)}),
            );
        }
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "engine": h.engine, "source_id": env!("SPLENDOR_SOURCE_ID"), "seed": h.seed,
            "prefix_length": length, "actor": o.current, "bank": o.bank,
            "tokens": o.players[o.current as usize].tokens,
            "bonuses": o.players[o.current as usize].bonuses,
            "targets_before": targets(&o, &o.players[o.current as usize]), "takes": takes
        }))?
    );
    Ok(())
}

//! Equal-sample diagnostic continuations, not the production UCB selection trace.
use serde_json::json;
use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{History, encode, replay};
use splendor_core::{Action, ActionSet, Observation, Phase, Rng};

// Mirror the current Engine leaf formula without changing the agent API.
fn value(o: &Observation, root: usize) -> f64 {
    let score = |i: usize| {
        let p = &o.players[i];
        p.score as f64
            + (p.bonuses
                .iter()
                .map(|&x| x.min(4) as f64 * 0.28)
                .sum::<f64>()
                + p.tokens.iter().sum::<u8>() as f64 * 0.06)
    };
    let opponent = (0..o.count as usize)
        .filter(|&i| i != root)
        .map(score)
        .fold(f64::NEG_INFINITY, f64::max);
    ((score(root) - opponent) / 20.0 + 0.5).clamp(0.0, 1.0)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut history: History =
        serde_json::from_slice(&std::fs::read(args.next().ok_or("history")?)?)?;
    let prefix: usize = args.next().ok_or("prefix")?.parse()?;
    let samples: u64 = args.next().ok_or("samples")?.parse()?;
    let depth: u32 = args.next().ok_or("depth")?.parse()?;
    let seed: u64 = args.next().ok_or("seed")?.parse()?;
    if prefix >= history.actions.len() || samples == 0 || depth == 0 || depth > 128 {
        return Err("require a recorded prefix, positive samples, and depth 1..=128".into());
    }
    replay(&history)?;
    history.actions.truncate(prefix);
    history.state_debug.clear();
    let real = replay(&history)?;
    if real.phase() != Phase::Main {
        return Err("requires Main phase".into());
    }
    let root = real.current_player();
    let o = real.observe(root);
    let mut normalized = o.clone();
    normalized.turns = 0;
    let mut legal = ActionSet::new();
    real.legal_actions(&mut legal);
    let mut branches = Vec::new();
    for &first in &legal {
        let mut rewards = Vec::new();
        let mut purchases = std::collections::BTreeMap::new();
        let mut returned_to_root = 0;
        let mut blocked = 0;
        let mut terminal = 0;
        let mut trace = Vec::new();
        for sample in 0..samples {
            let mut state = o.determinize(&mut Rng::new(seed.wrapping_add(sample)))?;
            let mut policy = make_agent("strong", 0, &SearchConfig::default())?;
            let mut first_purchase =
                matches!(first, Action::BuyVisible(_) | Action::BuyReserved(_)).then_some(0);
            state.apply_action(first)?;
            state.check_invariants()?;
            let mut aa = ActionSet::new();
            let mut recurred = false;
            for _ in 0..depth.saturating_mul(4).max(4) {
                if state.is_terminal()
                    || state.turns() == u32::MAX
                    || (state.turns() - o.turns >= depth && state.phase() == Phase::Main)
                {
                    break;
                }
                state.legal_actions(&mut aa);
                if aa.is_empty() {
                    break;
                }
                let obs = state.observe(state.current_player());
                if state.phase() == Phase::Main && state.current_player() == root {
                    let mut current = state.observe(root);
                    current.turns = 0;
                    recurred |= current == normalized;
                }
                let action = policy.select_action(&obs, &aa);
                if state.current_player() == root
                    && matches!(action, Action::BuyVisible(_) | Action::BuyReserved(_))
                    && first_purchase.is_none()
                {
                    first_purchase = Some(state.turns() - o.turns);
                }
                if sample == 0 {
                    trace.push(json!({"turn_offset":state.turns()-o.turns,
                    "seat":state.current_player(),"phase":format!("{:?}",state.phase()),"action":encode(action)}));
                }
                state.apply_action(action)?;
                state.check_invariants()?;
            }
            *purchases
                .entry(first_purchase.map_or_else(|| "none".to_string(), |x| x.to_string()))
                .or_insert(0u64) += 1;
            returned_to_root += u64::from(recurred);
            state.legal_actions(&mut aa);
            blocked += u64::from(aa.is_empty() && !state.is_terminal());
            let reward = if let Some(outcome) = state.outcome() {
                terminal += 1;
                if outcome.winners & (1 << root) != 0 {
                    1.0 / outcome.winners.count_ones() as f64
                } else {
                    0.0
                }
            } else {
                value(&state.observe(root), root)
            };
            rewards.push(reward);
        }
        branches.push(
            json!({"action":encode(first),"mean_reward":rewards.iter().sum::<f64>()/samples as f64,
            "min_reward":rewards.iter().copied().fold(f64::INFINITY,f64::min),
            "max_reward":rewards.iter().copied().fold(f64::NEG_INFINITY,f64::max),
            "first_root_purchase_turn_offset":purchases,"returned_to_root":returned_to_root,
            "blocked":blocked,"terminal":terminal,"first_sample_trace":trace}),
        );
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({"engine":history.engine,
        "source_id":env!("SPLENDOR_SOURCE_ID"),"prefix":prefix,"samples_per_action":samples,
        "depth":depth,"seed":seed,"root":root,"branches":branches,
        "scope":"Same sampled worlds per legal root action, strong rollouts and Engine leaf formula. Not production adaptive UCB visits; no unseen real deck access after root observation."}))?
    );
    Ok(())
}

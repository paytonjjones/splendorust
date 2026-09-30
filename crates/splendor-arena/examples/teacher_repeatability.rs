//! Measure search target variability for the same public observation.
use splendor_agents::{SearchConfig, make_agent};
use splendor_core::{Action, ActionSet, GameState, Phase};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let output = std::env::args().nth(1).ok_or("output path")?;
    let config = SearchConfig {
        iterations: 800,
        depth: 16,
        ..Default::default()
    };
    let mut rows = Vec::new();
    for stress in [false, true] {
        for seed in 0..4 {
            let mut state = GameState::new(2, 3_550_000_000 + seed)?;
            let mut strong = make_agent("strong", 0, &SearchConfig::default())?;
            let mut legal = ActionSet::new();
            for _ in 0..200 {
                if state.is_terminal() || state.turns() >= 124 {
                    break;
                }
                state.legal_actions(&mut legal);
                if legal.is_empty() {
                    break;
                }
                let o = state.observe(state.current_player());
                if o.phase == Phase::Main && o.turns.is_multiple_of(8) {
                    let mut policies = Vec::new();
                    let mut values = Vec::new();
                    for replicate in 0..8 {
                        let sampling_seed =
                            3_560_000_000 + seed * 10000 + u64::from(o.turns) * 8 + replicate;
                        let mut teacher = make_agent("flywheel-best", sampling_seed, &config)?;
                        teacher.select_action(&o, &legal);
                        policies.push(teacher.policy_target().ok_or("missing policy")?.to_vec());
                        values.push(teacher.value_target().ok_or("missing value")?);
                    }
                    let opponent = 1 - o.current as usize;
                    let blind = o.players[opponent]
                        .reserved
                        .iter()
                        .take(o.reserved_counts[opponent] as usize)
                        .filter(|r| !r.public)
                        .count();
                    rows.push(serde_json::json!({"stress":stress,"trajectory":seed,"turn":o.turns,"opponent_blind":blind,"policies":policies,"values":values}));
                }
                let forced = if stress && o.turns < 6 {
                    legal
                        .iter()
                        .copied()
                        .find(|a| matches!(a, Action::ReserveDeck(_)))
                } else {
                    None
                };
                let chosen = forced.unwrap_or_else(|| strong.select_action(&o, &legal));
                state.apply_action(chosen)?;
            }
        }
    }
    std::fs::write(
        output,
        serde_json::to_vec(
            &serde_json::json!({"source_id":env!("SPLENDOR_SOURCE_ID"),"iterations":800,"depth":16,"replicates":8,"scope":"Fixed Strong observations; ordinary and blind stress cohorts; not self-play prevalence or playing strength","observations":rows}),
        )?,
    )?;
    Ok(())
}

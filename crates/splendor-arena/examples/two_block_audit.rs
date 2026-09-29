//! Diagnose fixed recorded block histories using observation-only policy inputs.
use splendor_agents::{Agent, StrongHeuristicAgent};
use splendor_arena::{History, decode, encode};
use splendor_core::{ActionSet, GameState};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    while let Some(file) = args.next() {
        let rotation: usize = args
            .next()
            .ok_or("expected HISTORY ROTATION pairs")?
            .parse()?;
        let h: History = serde_json::from_slice(&std::fs::read(file)?)?;
        let mut state = GameState::new(h.players, h.seed)?;
        let mut legal = ActionSet::new();
        if h.players != 2 || rotation > 1 {
            return Err("two players and rotation 0 or 1 required".into());
        }
        for (index, &recorded) in h.actions.iter().enumerate() {
            state.legal_actions(&mut legal);
            let o = state.observe(state.current_player());
            let chosen = StrongHeuristicAgent.select_action(&o, &legal);
            if (o.current as usize + rotation) % 2 == 1 && encode(chosen) != recorded {
                println!(
                    "{}",
                    serde_json::json!({"seed":h.seed,"index":index,"actor":o.current,"phase":format!("{:?}",o.phase),"recorded":recorded,"chosen":encode(chosen)})
                );
            }
            state.apply_action(decode(recorded)?)?;
            state.check_invariants()?;
        }
    }
    Ok(())
}

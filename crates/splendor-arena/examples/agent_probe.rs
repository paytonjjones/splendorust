//! Seeded action probes at a saved observation; no policy changes or strength claim.
use serde_json::json;
use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{History, encode, replay};
use splendor_core::{ActionSet, Rng};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut history: History =
        serde_json::from_slice(&std::fs::read(args.next().ok_or("history")?)?)?;
    let prefix: usize = args.next().ok_or("prefix")?.parse()?;
    let name = args.next().ok_or("agent")?;
    let iterations: u32 = args.next().ok_or("iterations")?.parse()?;
    let depth: u32 = args.next().ok_or("depth")?.parse()?;
    if prefix >= history.actions.len() {
        return Err("prefix must precede a recorded action".into());
    }
    replay(&history)?;
    history.actions.truncate(prefix);
    history.state_debug.clear();
    let state = replay(&history)?;
    let o = state.observe(state.current_player());
    let alternative = o.determinize(&mut Rng::new(125000000))?;
    assert_eq!(o, alternative.observe(state.current_player()));
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    if legal.is_empty() {
        return Err("no legal action to probe".into());
    }
    let config = SearchConfig {
        iterations,
        depth,
        ..Default::default()
    };
    let mut actions = Vec::new();
    for seed in 0..16 {
        let mut a = make_agent(&name, seed, &config)?;
        let mut b = make_agent(&name, seed, &config)?;
        let action = a.select_action(&o, &legal);
        assert_eq!(
            action,
            b.select_action(&alternative.observe(state.current_player()), &legal)
        );
        assert!(legal.contains(&action));
        actions.push(json!({"agent_seed":seed,"action":encode(action)}));
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({"source_id":env!("SPLENDOR_SOURCE_ID"),
        "agent":name,"prefix":prefix,"iterations":iterations,"depth":depth,"actions":actions,
        "hidden_world_choices_equal":true,"scope":"Development probe, not strength or universal privacy proof."}))?
    );
    Ok(())
}

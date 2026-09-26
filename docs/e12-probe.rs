use splendor_agents::{SearchConfig, make_agent};
use splendor_arena::{History, RunConfig, encode, play_game, replay};
use splendor_core::ActionSet;
fn main() {
    let search = SearchConfig {
        iterations: 128,
        ..SearchConfig::default()
    };
    let mut h: History =
        serde_json::from_str(include_str!("../tests/fixtures/blocked-e11-v1.json")).unwrap();
    h.actions.truncate(32);
    h.state_debug.clear();
    let state = replay(&h).unwrap();
    let o = state.observe(state.current_player());
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    for seed in 0..32 {
        let mut a = make_agent("search-affordable", seed, &search).unwrap();
        let chosen = a.select_action(&o, &legal);
        assert!([legal[0], legal[1], legal[3]].contains(&chosen));
        let mut b = make_agent("search-affordable", seed, &search).unwrap();
        assert_eq!(chosen, b.select_action(&o, &legal));
        println!("seed {seed}: {:?}", encode(chosen));
    }
    let config = RunConfig {
        names: vec!["search-affordable".into(), "search".into()],
        games: 2,
        seed: 101000000,
        threads: 1,
        max_decisions: 20000,
        check: true,
        search,
    };
    let (record, history) = play_game(&config, 30, 1, 811391511434643069, true).unwrap();
    std::fs::write(
        "/tmp/e12-probe-history.json",
        serde_json::to_vec(&history.unwrap()).unwrap(),
    )
    .unwrap();
    println!("{}", serde_json::to_string(&record).unwrap());
}

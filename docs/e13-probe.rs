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
        let mut a = make_agent("search-combined", seed, &search).unwrap();
        let chosen = a.select_action(&o, &legal);
        assert!([legal[0], legal[1], legal[3]].contains(&chosen));
        let mut b = make_agent("search-combined", seed, &search).unwrap();
        assert_eq!(chosen, b.select_action(&o, &legal));
        println!("seed {seed}: {:?}", encode(chosen));
    }
    let config = RunConfig {
        names: vec!["search-combined".into(), "search".into()],
        games: 2,
        seed: 101000000,
        threads: 1,
        max_decisions: 20000,
        check: true,
        search,
    };
    for (block, rotation, seed) in [
        (30, 1, 811391511434643069),
        (179, 0, 17693537631505245311),
        (444, 1, 13785676833834719402),
        (927, 1, 10498548299596937796),
    ] {
        let (record, history) = play_game(&config, block, rotation, seed, true).unwrap();
        std::fs::write(
            format!("/tmp/e13-probe-{block}.json"),
            serde_json::to_vec(&history.unwrap()).unwrap(),
        )
        .unwrap();
        println!("{}", serde_json::to_string(&record).unwrap());
    }
}

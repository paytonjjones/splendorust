use splendor_agents::SearchConfig;
use splendor_arena::{RunConfig, decode, play_game};
use splendor_core::{ActionSet, GameState, Phase};
use std::collections::{BTreeMap, HashMap};
fn main() {
    let config = RunConfig {
        names: vec!["search-return-escape".into(), "search".into()],
        games: 2, seed: 99000000, threads: 1, max_decisions: 20000, check: true,
        search: SearchConfig { iterations:128, ..SearchConfig::default() },
    };
    for (block, rotation, seed) in [
        (253, 1, 3319929256140804277), (375, 0, 3596323141379729727),
        (521, 1, 17691880708187050584), (828, 1, 10309284138245333393),
    ] {
        let (record, history) = play_game(&config, block, rotation, seed, true).unwrap();
        let history = history.unwrap();
        std::fs::write(format!("/tmp/e10-cap-{block}.json"), serde_json::to_vec(&history).unwrap()).unwrap();
        println!("{}", serde_json::to_string(&record).unwrap());
        let mut state = GameState::new(2, seed).unwrap();
        let mut last_seen = HashMap::new();
        let mut distances = BTreeMap::new();
        let mut return_sizes = BTreeMap::new();
        let mut candidate_returns = 0;
        let mut legal = ActionSet::new();
        for (index, encoded) in history.actions.iter().enumerate() {
            state.legal_actions(&mut legal);
            let identity = (state.current_player() as usize + rotation) % 2;
            if identity == 0 && state.phase() == Phase::Return {
                candidate_returns += 1;
                *return_sizes.entry(legal.len()).or_insert(0) += 1;
                let mut observation = state.observe(state.current_player());
                observation.turns = 0;
                let key = format!("{observation:?}");
                if let Some(previous) = last_seen.insert(key, candidate_returns) {
                    *distances.entry(candidate_returns - previous).or_insert(0) += 1;
                }
            }
            if index >= history.actions.len() - 8 {
                println!("decision {index} identity {identity} phase {:?} choices {} action {:?}", state.phase(), legal.len(), decode(*encoded).unwrap());
                if identity == 0 { println!("candidate legal {legal:?}"); println!("candidate observation {:?}", state.observe(state.current_player())); }
            }
            state.apply_action(decode(*encoded).unwrap()).unwrap();
        }
        println!("candidate returns {candidate_returns}; choice counts {return_sizes:?}; repeat distances {distances:?}");
    }
}

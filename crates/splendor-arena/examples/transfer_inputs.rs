//! Fresh information-set fixtures for native-board encoding parity.
use serde_json::json;
use splendor_agents::{Agent, StrongHeuristicAgent, transfer};
use splendor_core::{Action, ActionSet, GameState, Phase, Rng};
fn main() {
    for seed in 0..8 {
        let mut state = GameState::new(2, 610000000 + seed).unwrap();
        let mut rng = Rng::new(617000007 + seed);
        let mut strong = StrongHeuristicAgent;
        let mut legal = ActionSet::new();
        // Ensure the fixtures include opponent blind reservations.
        state
            .apply_action(Action::ReserveDeck((seed % 3) as u8))
            .unwrap();
        for step in 0..120 {
            state.legal_actions(&mut legal);
            if legal.is_empty() {
                break;
            }
            let o = state.observe(state.current_player());
            if o.phase == Phase::Main && o.turns % 5 == 1 && o.turns < 124 {
                let mut mirror = rng;
                let world = o.determinize(&mut mirror).unwrap();
                assert_eq!(o, world.observe(o.viewer as usize));
                let x = transfer::encode(&o, &mut rng);
                let alternative = o.determinize(&mut Rng::new(610900000 + seed)).unwrap();
                let mut check_rng = Rng::new(617000007 + seed + step);
                let mut check_rng_other = check_rng;
                assert_eq!(
                    transfer::encode(&o, &mut check_rng),
                    transfer::encode(
                        &alternative.observe(o.viewer as usize),
                        &mut check_rng_other
                    )
                );
                let players: Vec<_> = (0..2).map(|seat| {
                    let p = world.observe(seat).players[seat];
                    json!({"tokens":p.tokens,"bonuses":p.bonuses,"score":p.score,
                        "owned":(0..90).filter(|id|p.owned & (1u128<<id)!=0).collect::<Vec<_>>(),
                        "nobles":(0..10).filter(|id|p.nobles & (1<<id)!=0).collect::<Vec<_>>(),
                        "reserved":p.reserved.iter().map(|r|json!({"card":r.card,"tier":r.tier,"public":r.public})).collect::<Vec<_>>()})
                }).collect();
                println!(
                    "{}",
                    json!({"x":x.as_slice(),"observation":{"bank":o.bank,"market":o.market,"remaining":o.remaining,"turns":o.turns,"current":o.current,"viewer":o.viewer,"players":players,"nobles":(0..10).filter(|id|o.nobles & (1<<id)!=0).collect::<Vec<_>>()}})
                );
            }
            state
                .apply_action(strong.select_action(&o, &legal))
                .unwrap();
        }
    }
}

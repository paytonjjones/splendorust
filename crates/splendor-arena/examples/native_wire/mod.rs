use serde::Deserialize;
use serde_json::{Value, json};
use splendor_agents::native_environment::{Observation, Player, Reservation};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WireReservation {
    card: u8,
    tier: u8,
    public: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WirePlayer {
    tokens: [u8; 6],
    bonuses: [u8; 5],
    card_points: u8,
    owned: Vec<u8>,
    nobles: u8,
    reserved: [WireReservation; 3],
    reserved_count: u8,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WireObservation {
    viewer: u8,
    current: u8,
    turns: u8,
    bank: [u8; 6],
    market: [u8; 12],
    remaining: [u8; 3],
    noble_ids: [u8; 3],
    nobles: u8,
    players: [WirePlayer; 2],
}
pub fn read(v: Value) -> Result<Observation, Box<dyn std::error::Error>> {
    let o: WireObservation = serde_json::from_value(v)?;
    let mut players = [Player::default(), Player::default()];
    for (p, w) in players.iter_mut().zip(o.players) {
        let mut owned = 0u128;
        for id in w.owned {
            if id >= 90 || owned & (1u128 << id) != 0 {
                return Err("invalid purchased card list".into());
            }
            owned |= 1u128 << id;
        }
        *p = Player {
            tokens: w.tokens,
            bonuses: w.bonuses,
            card_points: w.card_points,
            owned,
            nobles: w.nobles,
            reserved_count: w.reserved_count,
            reserved: w.reserved.map(|r| Reservation {
                card: r.card,
                tier: r.tier,
                public: r.public,
            }),
        };
    }
    Ok(Observation {
        viewer: o.viewer,
        current: o.current,
        turns: o.turns,
        bank: o.bank,
        market: o.market,
        remaining: o.remaining,
        noble_ids: o.noble_ids,
        nobles: o.nobles,
        players,
    })
}
pub fn write(o: &Observation) -> Value {
    json!({"viewer":o.viewer,"current":o.current,"turns":o.turns,"bank":o.bank,"market":o.market,"remaining":o.remaining,"noble_ids":o.noble_ids,"nobles":o.nobles,
        "players":o.players.iter().map(|p|json!({"tokens":p.tokens,"bonuses":p.bonuses,"card_points":p.card_points,"owned":(0..90).filter(|&id|p.owned&(1u128<<id)!=0).collect::<Vec<_>>(),"nobles":p.nobles,"reserved_count":p.reserved_count,
            "reserved":p.reserved.iter().map(|r|json!({"card":r.card,"tier":r.tier,"public":r.public})).collect::<Vec<_>>()})).collect::<Vec<_>>()})
}

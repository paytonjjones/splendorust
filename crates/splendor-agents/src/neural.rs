//! Relative, information-safe policy/value inputs for two-player research.
use splendor_core::{Action, NONE, Observation, data::CARDS};
pub const INPUTS: usize = 290;
pub const ACTIONS: usize = 67;
pub fn action_index(action: Action) -> Option<usize> {
    Some(match action {
        Action::Take(t) => {
            if let Some(c) = t.iter().position(|&n| n == 2) {
                32 + c
            } else {
                t.iter()
                    .enumerate()
                    .fold(0, |mask, (i, &n)| mask | (usize::from(n != 0) << i))
            }
        }
        Action::ReserveVisible(s) => 37 + usize::from(s),
        Action::ReserveDeck(t) => 49 + usize::from(t),
        Action::BuyVisible(s) => 52 + usize::from(s),
        Action::BuyReserved(s) => 64 + usize::from(s),
        _ => return None,
    })
}
fn card(x: &mut Vec<f32>, id: u8, present: bool, tier: u8) {
    x.push(f32::from(present));
    x.push(if id == NONE {
        0.0
    } else {
        f32::from(CARDS[id as usize].points) / 5.0
    });
    x.push(f32::from(tier) / 2.0);
    for c in 0..5 {
        x.push(f32::from(
            id != NONE && CARDS[id as usize].bonus as usize == c,
        ));
    }
    for c in 0..5 {
        x.push(if id == NONE {
            0.0
        } else {
            f32::from(CARDS[id as usize].cost[c]) / 7.0
        });
    }
}
pub fn features(o: &Observation) -> [f32; INPUTS] {
    assert_eq!(o.count, 2, "neural encoder is two-player only");
    let root = o.viewer as usize;
    let mut x = Vec::with_capacity(INPUTS);
    for seat in [root, 1 - root] {
        let p = &o.players[seat];
        x.extend([f32::from(p.score) / 20.0, f32::from(p.card_count()) / 30.0]);
        x.extend(p.tokens.map(|n| f32::from(n) / 10.0));
        x.extend(p.bonuses.map(|n| f32::from(n) / 6.0));
        x.push(f32::from(o.reserved_counts[seat]) / 3.0);
        for (slot, r) in p.reserved.iter().enumerate() {
            let present = slot < o.reserved_counts[seat] as usize;
            // Explicitly mask blind opponent slots even for a malformed caller.
            let id = if seat == root || r.public {
                r.card
            } else {
                NONE
            };
            card(&mut x, id, present, if present { r.tier } else { 0 });
            x.push(f32::from(present && r.public));
        }
    }
    for (slot, &id) in o.market.iter().enumerate() {
        card(&mut x, id, id != NONE, (slot / 4) as u8);
    }
    x.extend(o.bank.map(|n| f32::from(n) / 7.0));
    x.extend(o.remaining.map(|n| f32::from(n) / 40.0));
    x.push(f32::from(o.count) / 4.0);
    x.push(f32::from(o.current == o.viewer));
    x.push(f32::from(o.final_round));
    for n in 0..10 {
        x.push(f32::from(o.nobles & (1 << n) != 0));
    }
    x.try_into().expect("encoder dimension")
}
/// E26 appends explicit observation-only relative progress features.
pub fn enhanced_features(o: &Observation) -> [f32; 322] {
    let raw = features(o);
    let extra = super::learned::features(o, o.viewer as usize, 1 - o.viewer as usize);
    std::array::from_fn(|i| {
        if i < INPUTS {
            raw[i]
        } else {
            extra[i - INPUTS] as f32
        }
    })
}
pub fn baseline_logit(o: &Observation) -> f32 {
    let x = super::learned::features(o, o.viewer as usize, 1 - o.viewer as usize);
    x.iter()
        .zip(super::value_weights::WEIGHTS)
        .map(|(x, w)| x * w)
        .sum::<f64>() as f32
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::{GameState, Rng};
    #[test]
    fn hidden_world_and_blind_ids_do_not_enter_features() {
        let o = GameState::new(2, 42).unwrap().observe(0);
        let sampled = o.determinize(&mut Rng::new(918)).unwrap();
        assert_eq!(features(&o), features(&sampled.observe(0)));
        let mut a = o.clone();
        a.reserved_counts[1] = 1;
        a.players[1].reserved[0].public = false;
        a.players[1].reserved[0].tier = 1;
        a.players[1].reserved[0].card = 40;
        let mut b = a.clone();
        b.players[1].reserved[0].card = 50;
        assert_eq!(features(&a), features(&b));
    }
    #[test]
    fn main_action_indices_are_unique_on_real_positions() {
        use splendor_core::{ActionSet, Phase};
        let mut rng = Rng::new(18);
        for seed in 0..100 {
            let mut s = GameState::new(2, seed).unwrap();
            let mut legal = ActionSet::new();
            for _ in 0..300 {
                s.legal_actions(&mut legal);
                if legal.is_empty() {
                    break;
                }
                if s.phase() == Phase::Main {
                    let mut seen = [false; ACTIONS];
                    for &a in &legal {
                        let i = action_index(a).unwrap();
                        assert!(!seen[i]);
                        seen[i] = true;
                    }
                }
                s.apply_action(legal[rng.index(legal.len())]).unwrap();
            }
        }
    }
}

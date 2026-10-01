//! Public first moments reconstructed from legacy sampled-world encodings.
//! No real hidden card identity, setup seed or deck order enters this transform.
use crate::transfer_data::{CARD_GROUP, CARD_SLOT};
use splendor_core::data::CARDS;

pub fn moments(x: &[f32; 392], context: &[f32; 7]) -> ([f32; 392], [f32; 519]) {
    let mut pool = [false; 90];
    let mut deck = [0usize; 3];
    for (id, c) in CARDS.iter().enumerate() {
        let t = c.tier as usize;
        let g = CARD_GROUP[id] as usize;
        let bits = x[(26 + 2 * t) * 7 + g] as i8 as u8;
        pool[id] = bits & (128 >> CARD_SLOT[id]) != 0;
        deck[t] += usize::from(pool[id]);
    }
    let mut unknown = [None; 3];
    let mut counts = [0usize; 3];
    for slot in 0..3 {
        assert!(context[slot] == 0.0 || context[slot] == 1.0);
        if context[slot] == 0.0 {
            continue;
        }
        let tier = (context[slot + 3] * 3.0).round() as usize - 1;
        assert!(tier < 3);
        let row = 50 + 2 * slot;
        let id = CARDS
            .iter()
            .position(|c| {
                c.tier as usize == tier
                    && c.cost
                        .iter()
                        .enumerate()
                        .all(|(color, &n)| x[row * 7 + color] == f32::from(n))
                    && (0..5).all(|color| {
                        x[(row + 1) * 7 + color] == f32::from(color == c.bonus as usize)
                    })
                    && x[(row + 1) * 7 + 6] == f32::from(c.points)
            })
            .expect("sampled reservation is a catalog card");
        assert!(!pool[id], "sampled reservation cannot remain in deck");
        pool[id] = true;
        unknown[slot] = Some(tier);
        counts[tier] += 1;
    }
    let mut n = [0usize; 3];
    let mut masks = [[0u8; 5]; 3];
    let mut groups = [[0usize; 5]; 3];
    let mut costs = [[0usize; 5]; 3];
    let mut bonuses = [[0usize; 5]; 3];
    let mut points = [0usize; 3];
    for (id, c) in CARDS.iter().enumerate() {
        if !pool[id] {
            continue;
        }
        let t = c.tier as usize;
        let g = CARD_GROUP[id] as usize;
        n[t] += 1;
        groups[t][g] += 1;
        masks[t][g] |= 128 >> CARD_SLOT[id];
        for (color, &cost) in c.cost.iter().enumerate() {
            costs[t][color] += cost as usize;
        }
        bonuses[t][c.bonus as usize] += 1;
        points[t] += c.points as usize;
    }
    let mut mean = *x;
    for t in 0..3 {
        assert_eq!(n[t], deck[t] + counts[t]);
        let p = if n[t] == 0 {
            0.0
        } else {
            deck[t] as f64 / n[t] as f64
        };
        for g in 0..5 {
            mean[(25 + 2 * t) * 7 + g] = (groups[t][g] as f64 * p) as f32;
            mean[(26 + 2 * t) * 7 + g] = (f64::from(masks[t][g] as i8) * p) as f32;
        }
    }
    for (slot, tier) in unknown.into_iter().enumerate() {
        if let Some(t) = tier {
            let row = 50 + 2 * slot;
            for color in 0..5 {
                mean[row * 7 + color] = (costs[t][color] as f64 / n[t] as f64) as f32;
                mean[(row + 1) * 7 + color] = (bonuses[t][color] as f64 / n[t] as f64) as f32;
            }
            mean[(row + 1) * 7 + 6] = (points[t] as f64 / n[t] as f64) as f32;
        }
    }
    let mut features = [0.0; 519];
    for i in 0..392 {
        features[i] = mean[i] * if i == 6 { 1.0 / 124.0 } else { 0.1 };
    }
    for t in 0..3 {
        for g in 0..5 {
            features[(26 + 2 * t) * 7 + g] = 0.0;
        }
    }
    for (id, c) in CARDS.iter().enumerate() {
        if pool[id] {
            let t = c.tier as usize;
            let g = CARD_GROUP[id] as usize;
            features[392 + (t * 5 + g) * 8 + 7 - CARD_SLOT[id] as usize] =
                (deck[t] as f64 / n[t] as f64) as f32;
        }
    }
    features[512..].copy_from_slice(context);
    (mean, features)
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::{Action, ActionSet, GameState, Phase, Rng};
    #[test]
    fn small_pool_exact_moments_and_public_information() {
        let ids = [0usize, 8, 16, 24];
        let context = [1.0, 1.0, 0.0, 1.0 / 3.0, 1.0 / 3.0, 0.0, 2.0 / 3.0];
        let mut sum = [0.0f64; 392];
        let mut count = 0;
        let mut expected = None;
        for &a in &ids {
            for &b in &ids {
                if a == b {
                    continue;
                }
                let mut x = [0.0; 392];
                for (slot, id) in [a, b].into_iter().enumerate() {
                    let row = 50 + 2 * slot;
                    let c = CARDS[id];
                    for (color, cost) in c.cost.into_iter().enumerate() {
                        x[row * 7 + color] = f32::from(cost);
                    }
                    x[(row + 1) * 7 + c.bonus as usize] = 1.0;
                    x[(row + 1) * 7 + 6] = f32::from(c.points);
                }
                let mut masks = [0u8; 5];
                for &id in &ids {
                    if id != a && id != b {
                        let g = CARD_GROUP[id] as usize;
                        x[25 * 7 + g] += 1.0;
                        masks[g] |= 128 >> CARD_SLOT[id];
                    }
                }
                for g in 0..5 {
                    x[26 * 7 + g] = f32::from(masks[g] as i8);
                }
                for i in 0..392 {
                    sum[i] += f64::from(x[i]);
                }
                count += 1;
                let result = moments(&x, &context);
                if let Some(old) = &expected {
                    assert_eq!(&result, old);
                } else {
                    expected = Some(result);
                }
                let mut known = context;
                known[0] = 0.0;
                known[6] = 1.0 / 3.0;
                assert_ne!(result.1, moments(&x, &known).1);
            }
        }
        assert_eq!(count, 12);
        let (mean, features) = expected.unwrap();
        for i in 0..392 {
            assert!((f64::from(mean[i]) - sum[i] / 12.0).abs() < 1e-6);
        }
        assert_eq!(features[392..512].iter().sum::<f32>(), 2.0);
        assert_eq!(features[512..], context);
    }
    #[test]
    fn sampled_world_invariance_and_no_blind_identity() {
        let mut blind = 0;
        let mut changed = 0;
        let mut ordinary = 0;
        for stress in [false, true] {
            for seed in 0..4 {
                let mut state = GameState::new(2, 4640000000 + seed).unwrap();
                let mut actor =
                    crate::make_agent("strong", 0, &crate::SearchConfig::default()).unwrap();
                let mut legal = ActionSet::new();
                for _ in 0..128 {
                    if state.is_terminal() {
                        break;
                    }
                    state.legal_actions(&mut legal);
                    if legal.is_empty() {
                        break;
                    }
                    let o = state.observe(state.current_player());
                    if o.phase == Phase::Main && o.turns < 124 {
                        let context = crate::transfer::public_context(&o);
                        let xs: Vec<_> = (0..8)
                            .map(|i| crate::transfer::encode(&o, &mut Rng::new(4650000000 + i)))
                            .collect();
                        let expected = moments(&xs[0], &context);
                        for x in &xs {
                            assert_eq!(moments(x, &context), expected);
                        }
                        if context[6] == 0.0 {
                            ordinary += 1;
                            assert_eq!(expected.0, xs[0]);
                        } else {
                            blind += 1;
                            changed += usize::from(xs.iter().any(|x| x != &xs[0]));
                        }
                    }
                    let a = if stress && o.phase == Phase::Main && o.turns < 6 {
                        legal
                            .iter()
                            .copied()
                            .find(
                                |a| matches!(a,Action::ReserveDeck(t) if u32::from(*t)==o.turns/2),
                            )
                            .unwrap_or_else(|| actor.select_action(&o, &legal))
                    } else {
                        actor.select_action(&o, &legal)
                    };
                    state.apply_action(a).unwrap();
                }
            }
        }
        assert!(ordinary > 0 && blind > 0 && changed > 0);
    }
}

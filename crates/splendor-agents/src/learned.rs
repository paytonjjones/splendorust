//! E23 observation-only logistic value features. No full state is accepted.
use super::{deficit, noble_potential};
use splendor_core::{NONE, Observation, data::CARDS};
pub const FEATURES: usize = 32;
fn player_features(o: &Observation, seat: usize) -> [f64; 16] {
    let p = &o.players[seat];
    let mut x = [0.0; 16];
    x[0] = f64::from(p.score) / 15.0;
    x[1] = f64::from(p.card_count()) / 20.0;
    x[2] = p.bonuses.iter().map(|&b| f64::from(b.min(4))).sum::<f64>() / 20.0;
    x[3] = f64::from(p.token_count()) / 10.0;
    x[4] = f64::from(p.tokens[5]) / 5.0;
    x[5] = f64::from(noble_potential(o, p)) / 120.0;
    x[6] = f64::from(o.reserved_counts[seat]) / 3.0;
    x[7] = f64::from(o.current as usize == seat);
    for &id in &o.market {
        if id == NONE {
            continue;
        }
        let c = &CARDS[id as usize];
        let d = f64::from(deficit(p, id));
        let tier = c.tier as usize;
        x[8 + tier] = x[8 + tier].max((f64::from(c.points) + 1.0) / (1.0 + d) / 6.0);
        x[11 + tier] += f64::from(d == 0.0) / 4.0;
        x[14] = x[14].max(f64::from(c.points) / (1.0 + d) / 5.0);
    }
    x[15] = f64::from(p.score >= 12);
    x
}
/// Pairwise feature differences; multiplayer inference averages pairwise odds.
pub fn features(o: &Observation, root: usize, other: usize) -> [f64; FEATURES] {
    let a = player_features(o, root);
    let b = player_features(o, other);
    let stage = f64::from(o.players[root].score.max(o.players[other].score)) / 15.0;
    std::array::from_fn(|i| (a[i % 16] - b[i % 16]) * if i < 16 { 1.0 } else { stage })
}
pub fn predict(o: &Observation, root: usize, weights: &[f64; FEATURES]) -> f64 {
    let odds = (0..o.count as usize)
        .filter(|&s| s != root)
        .map(|s| {
            let x = features(o, root, s);
            let z: f64 = x.iter().zip(weights).map(|(a, b)| a * b).sum();
            (-z.clamp(-30.0, 30.0)).exp()
        })
        .sum::<f64>();
    1.0 / (1.0 + odds)
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::{GameState, Rng};
    #[test]
    fn features_do_not_depend_on_sampled_hidden_world() {
        let state = GameState::new(2, 197).unwrap();
        let o = state.observe(0);
        for seed in 0..20 {
            let alternative = o.determinize(&mut Rng::new(seed)).unwrap();
            assert_eq!(features(&o, 0, 1), features(&alternative.observe(0), 0, 1));
        }
    }
    #[test]
    fn pairwise_value_is_symmetric_and_finite() {
        let o = GameState::new(2, 42).unwrap().observe(0);
        let weights = [0.7; FEATURES];
        let a = predict(&o, 0, &weights);
        let b = predict(&o, 1, &weights);
        assert!((a + b - 1.0).abs() < 1e-12);
        assert!(a.is_finite() && (0.0..=1.0).contains(&a));
    }
}

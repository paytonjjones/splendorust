//! Public event tensors. Blind draws have no card identity, even for their actor.
use splendor_core::{Action, NONE, Observation, data::CARDS};

pub fn canonical_pool(o: &Observation) -> [f32; 90] {
    let mut pool = [1.0; 90];
    for &id in &o.market {
        if id != NONE {
            pool[id as usize] = 0.0;
        }
    }
    for (seat, p) in o.players.iter().enumerate().take(o.count as usize) {
        for (id, value) in pool.iter_mut().enumerate() {
            if p.owned & (1u128 << id) != 0 {
                *value = 0.0;
            }
        }
        for r in p.reserved.iter().take(o.reserved_counts[seat] as usize) {
            if (seat == o.viewer as usize || r.public) && r.card != NONE {
                pool[r.card as usize] = 0.0;
            }
        }
    }
    pool
}
pub fn native_pool(o: &crate::native_environment::Observation) -> [f32; 90] {
    let mut pool = [1.0; 90];
    for &id in &o.market {
        if id != NONE {
            pool[id as usize] = 0.0;
        }
    }
    for (seat, p) in o.players.iter().enumerate() {
        for (id, value) in pool.iter_mut().enumerate() {
            if p.owned & (1u128 << id) != 0 {
                *value = 0.0;
            }
        }
        for r in p.reserved.iter().take(p.reserved_count as usize) {
            if (seat == o.viewer as usize || r.public) && r.card != NONE {
                pool[r.card as usize] = 0.0;
            }
        }
    }
    pool
}

pub fn canonical(before: &Observation, action: Action, after: &Observation) -> [f32; 32] {
    let actor = before.current as usize;
    let (kind, mut card, mut tier) = match action {
        Action::Take(_) => (0, NONE, 0.0),
        Action::ReserveVisible(slot) => (1, before.market[slot as usize], 0.0),
        Action::ReserveDeck(tier) => (2, NONE, f32::from(tier + 1) / 3.0),
        Action::BuyVisible(slot) => (3, before.market[slot as usize], 0.0),
        Action::BuyReserved(slot) => {
            let r = before.players[actor].reserved[slot as usize];
            (4, if r.public { r.card } else { NONE }, 0.0)
        }
        Action::Pay(_) => (5, NONE, 0.0),
        Action::Return(_) => (6, NONE, 0.0),
        Action::Noble(_) => (7, NONE, 0.0),
    };
    let bought = after.players[actor].owned & !before.players[actor].owned;
    if bought != 0 {
        card = bought.trailing_zeros() as u8;
    }
    let mut result = [0.0; 32];
    result[0] = 1.0;
    result[1] = actor as f32;
    result[2 + kind] = 1.0;
    if card != NONE {
        let c = CARDS[card as usize];
        for (target, cost) in result[10..15].iter_mut().zip(c.cost) {
            *target = f32::from(cost) / 10.0;
        }
        result[17 + c.bonus as usize] = 0.1;
        result[23] = f32::from(c.points) / 10.0;
        tier = f32::from(c.tier + 1) / 3.0;
    }
    for (color, target) in result[24..30].iter_mut().enumerate() {
        *target = (f32::from(after.players[actor].tokens[color])
            - f32::from(before.players[actor].tokens[color]))
            / 10.0;
    }
    result[30] = tier;
    result[31] = before.turns as f32 / 124.0;
    result
}

pub fn native(
    before: &crate::native_environment::Observation,
    action: u8,
    after: &crate::native_environment::Observation,
) -> [f32; 32] {
    let actor = before.current as usize;
    let (kind, mut card, mut tier) = match action {
        0..12 => (3, before.market[action as usize], 0.0),
        12..24 => (1, before.market[action as usize - 12], 0.0),
        24..27 => (2, NONE, f32::from(action - 23) / 3.0),
        27..30 => (4, NONE, 0.0),
        _ => (0, NONE, 0.0),
    };
    let bought = after.players[actor].owned & !before.players[actor].owned;
    if bought != 0 {
        card = bought.trailing_zeros() as u8;
    }
    let mut result = [0.0; 32];
    result[0] = 1.0;
    result[1] = actor as f32;
    result[2 + kind] = 1.0;
    if card != NONE {
        let c = CARDS[card as usize];
        for (target, cost) in result[10..15].iter_mut().zip(c.cost) {
            *target = f32::from(cost) / 10.0;
        }
        result[17 + c.bonus as usize] = 0.1;
        result[23] = f32::from(c.points) / 10.0;
        tier = f32::from(c.tier + 1) / 3.0;
    }
    for (color, target) in result[24..30].iter_mut().enumerate() {
        *target = (f32::from(after.players[actor].tokens[color])
            - f32::from(before.players[actor].tokens[color]))
            / 10.0;
    }
    result[30] = tier;
    result[31] = f32::from(before.turns) / 124.0;
    result
}

/// Version two retains public action/slot identity without adding private cards.
pub fn canonical_v2(before: &Observation, action: Action, after: &Observation) -> [f32; 32] {
    let mut event = canonical(before, action, after);
    if let Some(index) = crate::neural::action_index(action) {
        event[15] = (index + 1) as f32 / 81.0;
    }
    event[16] = match action {
        Action::BuyVisible(slot) | Action::ReserveVisible(slot) => f32::from(slot + 1) / 12.0,
        Action::BuyReserved(slot) | Action::ReserveDeck(slot) => f32::from(slot + 1) / 3.0,
        Action::Noble(id) => f32::from(id + 1) / 10.0,
        _ => 0.0,
    };
    event
}

pub fn native_v2(
    before: &crate::native_environment::Observation,
    action: u8,
    after: &crate::native_environment::Observation,
) -> [f32; 32] {
    assert!(action < 81, "native public action index");
    let mut event = native(before, action, after);
    event[15] = f32::from(action + 1) / 81.0;
    event[16] = match action {
        0..12 => f32::from(action + 1) / 12.0,
        12..24 => f32::from(action - 11) / 12.0,
        24..27 => f32::from(action - 23) / 3.0,
        27..30 => f32::from(action - 26) / 3.0,
        _ => 0.0,
    };
    event
}

#[cfg(test)]
mod tests {
    use super::*;
    use splendor_core::GameState;
    #[test]
    fn blind_draw_has_no_private_identity() {
        let mut state = GameState::new(2, 812).unwrap();
        let before = state.observe(0);
        state.apply_action(Action::ReserveDeck(0)).unwrap();
        let private = state.observe(0);
        let public = state.observe(1);
        assert_ne!(private.players[0].reserved[0].card, NONE);
        assert_eq!(public.players[0].reserved[0].card, NONE);
        let a = canonical(&before, Action::ReserveDeck(0), &private);
        let b = canonical(&before, Action::ReserveDeck(0), &public);
        assert_eq!(a, b);
        assert!(a[10..24].iter().all(|v| *v == 0.0));
        let a = canonical_v2(&before, Action::ReserveDeck(0), &private);
        let b = canonical_v2(&before, Action::ReserveDeck(0), &public);
        assert_eq!(a, b);
        assert!(a[10..15].iter().chain(&a[17..24]).all(|v| *v == 0.0));
        assert!(a[15] > 0.0);
        assert_eq!(a[16], 1.0 / 3.0);
    }
}

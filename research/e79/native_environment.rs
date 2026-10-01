//! Pinned AlphaZero-native two-player rules. Canonical core rules are untouched.
//! Public observations contain no deck membership or opponent blind card IDs.
use crate::transfer_data::{CARD_GROUP, CARD_SLOT, TAKE_MASKS};
use splendor_core::{
    NONE, Rng,
    data::{CARDS, NOBLES},
};

pub const PROFILE: &str = "alphazero-native-32a27ac-v1";
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Reservation {
    pub card: u8,
    pub tier: u8,
    pub public: bool,
}
impl Default for Reservation {
    fn default() -> Self {
        Self {
            card: NONE,
            tier: 0,
            public: false,
        }
    }
}
#[derive(Clone, Debug, Default, PartialEq, Eq, Hash)]
pub struct Player {
    pub tokens: [u8; 6],
    pub bonuses: [u8; 5],
    pub card_points: u8,
    pub owned: u128,
    pub nobles: u8,
    pub reserved: [Reservation; 3],
    pub reserved_count: u8,
}
impl Player {
    pub fn score(&self) -> u8 {
        self.card_points + 3 * self.nobles.count_ones() as u8
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Observation {
    pub viewer: u8,
    pub current: u8,
    pub turns: u8,
    pub bank: [u8; 6],
    pub market: [u8; 12],
    pub remaining: [u8; 3],
    /// Original native noble slot order is part of the public environment.
    pub noble_ids: [u8; 3],
    pub nobles: u8,
    pub players: [Player; 2],
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct State {
    public: Observation,
    decks: [u128; 3],
}

pub fn tokens(action: u8) -> Option<[u8; 5]> {
    let mut t = [0; 5];
    let mask = match action {
        30..=54 => TAKE_MASKS[(action - 30) as usize],
        60..=74 => TAKE_MASKS[(action - 60) as usize],
        55..=59 => {
            t[(action - 55) as usize] = 2;
            return Some(t);
        }
        75..=79 => {
            t[(action - 75) as usize] = 2;
            return Some(t);
        }
        _ => return None,
    };
    for (c, x) in t.iter_mut().enumerate() {
        *x = u8::from(mask & (1 << c) != 0);
    }
    Some(t)
}
impl Observation {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.viewer > 1 || self.current > 1 || self.turns > 124 || self.current != self.turns % 2
        {
            return Err("invalid native seat/clock");
        }
        if self.noble_ids.iter().any(|&n| n >= 10)
            || self.noble_ids[0] == self.noble_ids[1]
            || self.noble_ids[0] == self.noble_ids[2]
            || self.noble_ids[1] == self.noble_ids[2]
            || self.nobles > 7
        {
            return Err("invalid native nobles");
        }
        let mut seen = 0u128;
        let mut add = |id: u8, tier: Option<u8>| -> Result<(), &'static str> {
            if id >= 90
                || tier.is_some_and(|t| CARDS[id as usize].tier != t)
                || seen & (1u128 << id) != 0
            {
                return Err("invalid or duplicate native card");
            }
            seen |= 1u128 << id;
            Ok(())
        };
        for (slot, &id) in self.market.iter().enumerate() {
            if id != NONE {
                add(id, Some((slot / 4) as u8))?;
            }
        }
        let mut noble_seen = self.nobles;
        let mut unknown = [0u8; 3];
        for (seat, p) in self.players.iter().enumerate() {
            if p.reserved_count > 3
                || p.tokens.iter().map(|&t| u16::from(t)).sum::<u16>() > 10
                || p.nobles > 7
                || noble_seen & p.nobles != 0
            {
                return Err("invalid native player");
            }
            noble_seen |= p.nobles;
            let mut bonuses = [0u8; 5];
            let mut points = 0u8;
            for id in 0..128 {
                if p.owned & (1u128 << id) != 0 {
                    add(id, None)?;
                    let c = CARDS[id as usize];
                    bonuses[c.bonus as usize] += 1;
                    points += c.points;
                }
            }
            if bonuses != p.bonuses || points != p.card_points {
                return Err("native purchase history mismatch");
            }
            for (slot, r) in p.reserved.iter().enumerate() {
                if slot >= p.reserved_count as usize {
                    if *r != Reservation::default() {
                        return Err("native reserved slots not compact");
                    }
                } else {
                    if r.tier >= 3 {
                        return Err("invalid native reserve tier");
                    }
                    if r.card == NONE {
                        if seat == self.viewer as usize || r.public {
                            return Err("actor/public reservation hidden");
                        }
                        unknown[r.tier as usize] += 1;
                    } else {
                        if seat != self.viewer as usize && !r.public {
                            return Err("opponent blind identity supplied");
                        }
                        add(r.card, Some(r.tier))?;
                    }
                }
            }
        }
        if noble_seen != 7 {
            return Err("native noble partition mismatch");
        }
        for c in 0..6 {
            if u16::from(self.bank[c])
                + self
                    .players
                    .iter()
                    .map(|p| u16::from(p.tokens[c]))
                    .sum::<u16>()
                != if c == 5 { 5 } else { 4 }
            {
                return Err("native token supply mismatch");
            }
        }
        for (tier, &hidden) in unknown.iter().enumerate() {
            let available = CARDS
                .iter()
                .enumerate()
                .filter(|&(id, c)| c.tier as usize == tier && seen & (1u128 << id) == 0)
                .count();
            if available != usize::from(self.remaining[tier]) + usize::from(hidden) {
                return Err("native card partition mismatch");
            }
        }
        Ok(())
    }
    pub fn determinize(&self, rng: &mut Rng) -> Result<State, &'static str> {
        self.validate()?;
        let mut public = self.clone();
        let mut occupied = public.players.iter().fold(0u128, |m, p| m | p.owned);
        for &id in &public.market {
            if id != NONE {
                occupied |= 1u128 << id;
            }
        }
        for p in &public.players {
            for r in &p.reserved {
                if r.card != NONE {
                    occupied |= 1u128 << r.card;
                }
            }
        }
        let mut decks = [0u128; 3];
        for (tier, deck) in decks.iter_mut().enumerate() {
            let mut unknown: Vec<_> = CARDS
                .iter()
                .enumerate()
                .filter(|&(id, c)| c.tier as usize == tier && occupied & (1u128 << id) == 0)
                .map(|(id, _)| id as u8)
                .collect();
            rng.shuffle(&mut unknown);
            for p in &mut public.players {
                for r in &mut p.reserved[..p.reserved_count as usize] {
                    if r.card == NONE && r.tier as usize == tier {
                        r.card = unknown.pop().ok_or("missing native blind card")?;
                    }
                }
            }
            for id in unknown {
                *deck |= 1u128 << id;
            }
        }
        let s = State { public, decks };
        assert_eq!(*self, s.observe(self.viewer));
        Ok(s)
    }
}
impl State {
    pub fn current_player(&self) -> usize {
        self.public.current as usize
    }
    pub fn turns(&self) -> u32 {
        u32::from(self.public.turns)
    }
    /// Full hidden fixtures are accepted only by the explicit validation build.
    #[cfg(feature = "environment-validation")]
    pub fn from_fixture(public: Observation, decks: [u128; 3]) -> Result<Self, &'static str> {
        let s = Self { public, decks };
        for viewer in 0..2 {
            s.observe(viewer).validate()?;
        }
        let mut occupied = s.public.players.iter().fold(0u128, |m, p| m | p.owned);
        for &id in &s.public.market {
            if id != NONE {
                occupied |= 1u128 << id;
            }
        }
        for p in &s.public.players {
            for r in &p.reserved[..p.reserved_count as usize] {
                if r.card >= 90 {
                    return Err("fixture reservation missing");
                }
                occupied |= 1u128 << r.card;
            }
        }
        for (tier, &deck) in s.decks.iter().enumerate() {
            if deck.count_ones() != u32::from(s.public.remaining[tier]) || occupied & deck != 0 {
                return Err("fixture deck partition mismatch");
            }
            if deck >> 90 != 0 {
                return Err("fixture deck id");
            }
            for (id, c) in CARDS.iter().enumerate() {
                if deck & (1u128 << id) != 0 && c.tier as usize != tier {
                    return Err("fixture deck tier");
                }
            }
            occupied |= deck;
        }
        if occupied != (1u128 << 90) - 1 {
            return Err("fixture incomplete card partition");
        }
        Ok(s)
    }

    pub fn observe(&self, viewer: u8) -> Observation {
        let mut o = self.public.clone();
        o.viewer = viewer;
        for (seat, p) in o.players.iter_mut().enumerate() {
            if seat != viewer as usize {
                for r in &mut p.reserved[..p.reserved_count as usize] {
                    if !r.public {
                        r.card = NONE;
                    }
                }
            }
        }
        o
    }
    pub fn legal(&self) -> Vec<u8> {
        let p = &self.public.players[self.public.current as usize];
        let count = p.tokens.iter().sum::<u8>();
        let affordable = |id: u8| {
            id != NONE
                && CARDS[id as usize]
                    .cost
                    .iter()
                    .zip(p.bonuses)
                    .zip(p.tokens)
                    .map(|((&cost, bonus), token)| cost.saturating_sub(bonus).saturating_sub(token))
                    .sum::<u8>()
                    <= p.tokens[5]
        };
        let mut legal = Vec::new();
        for action in 0u8..81 {
            let valid = match action {
                0..=11 => affordable(self.public.market[action as usize]),
                12..=23 => {
                    p.reserved_count < 3 && self.public.market[(action - 12) as usize] != NONE
                }
                24..=26 => {
                    p.reserved_count < 3 && self.public.remaining[(action - 24) as usize] > 0
                }
                27..=29 => affordable(p.reserved[(action - 27) as usize].card),
                30..=54 => {
                    let t = tokens(action).unwrap();
                    count + t.iter().sum::<u8>() <= 10
                        && t.iter().zip(self.public.bank).all(|(&n, b)| n <= b)
                }
                55..=59 => count + 2 <= 10 && self.public.bank[(action - 55) as usize] >= 4,
                60..=79 => tokens(action)
                    .unwrap()
                    .iter()
                    .zip(p.tokens)
                    .all(|(&n, t)| n <= t),
                80 => true,
                _ => unreachable!(),
            };
            if valid {
                legal.push(action);
            }
        }
        legal
    }
    fn draw(&mut self, tier: usize, rng: &mut Rng, seed: Option<u64>) -> u8 {
        let mut ids: Vec<_> = (0..90)
            .filter(|&id| self.decks[tier] & (1u128 << id) != 0)
            .collect();
        if ids.is_empty() {
            return NONE;
        }
        ids.sort_by_key(|&id| (CARD_GROUP[id], CARD_SLOT[id]));
        let index = if let Some(seed) = seed.filter(|&s| s != 0) {
            let mut bits = [0u8; 5];
            for &id in &ids {
                bits[CARD_GROUP[id] as usize] |= 128 >> CARD_SLOT[id];
            }
            let hash = bits
                .iter()
                .enumerate()
                .map(|(c, &b)| u64::from(b) << (5 * c))
                .sum::<u64>();
            (4594591u64.wrapping_mul(seed.wrapping_add(hash)) % ids.len() as u64) as usize
        } else {
            rng.index(ids.len())
        };
        let id = ids[index] as u8;
        self.decks[tier] &= !(1u128 << id);
        self.public.remaining[tier] -= 1;
        id
    }
    fn buy(&mut self, id: u8) {
        let c = CARDS[id as usize];
        let seat = self.public.current as usize;
        let p = &mut self.public.players[seat];
        let mut gold = 0;
        for color in 0..5 {
            let cost = c.cost[color].saturating_sub(p.bonuses[color]);
            let paid = cost.min(p.tokens[color]);
            gold += cost - paid;
            p.tokens[color] -= paid;
            self.public.bank[color] += paid;
        }
        p.tokens[5] -= gold;
        self.public.bank[5] += gold;
        p.bonuses[c.bonus as usize] += 1;
        p.card_points += c.points;
        p.owned |= 1u128 << id;
        for slot in 0..3 {
            if self.public.nobles & (1 << slot) != 0
                && NOBLES[self.public.noble_ids[slot] as usize]
                    .iter()
                    .zip(p.bonuses)
                    .all(|(&n, b)| b >= n)
            {
                self.public.nobles &= !(1 << slot);
                p.nobles |= 1 << slot;
            }
        }
    }
    pub fn apply(
        &mut self,
        action: u8,
        rng: &mut Rng,
        chance_seed: Option<u64>,
    ) -> Result<(), &'static str> {
        if self.rewards().is_some() || !self.legal().contains(&action) {
            return Err("illegal native action");
        }
        let seat = self.public.current as usize;
        match action {
            0..=11 => {
                let slot = action as usize;
                self.buy(self.public.market[slot]);
                self.public.market[slot] = self.draw(slot / 4, rng, chance_seed);
            }
            12..=26 => {
                let (id, tier, public) = if action < 24 {
                    let slot = (action - 12) as usize;
                    let id = self.public.market[slot];
                    self.public.market[slot] = self.draw(slot / 4, rng, chance_seed);
                    (id, slot / 4, true)
                } else {
                    let tier = (action - 24) as usize;
                    (self.draw(tier, rng, chance_seed), tier, false)
                };
                let p = &mut self.public.players[seat];
                p.reserved[p.reserved_count as usize] = Reservation {
                    card: id,
                    tier: tier as u8,
                    public,
                };
                p.reserved_count += 1;
                if self.public.bank[5] > 0 && p.tokens.iter().sum::<u8>() <= 9 {
                    p.tokens[5] += 1;
                    self.public.bank[5] -= 1;
                }
            }
            27..=29 => {
                let slot = (action - 27) as usize;
                self.buy(self.public.players[seat].reserved[slot].card);
                let p = &mut self.public.players[seat];
                for i in slot..2 {
                    p.reserved[i] = p.reserved[i + 1];
                }
                p.reserved[2] = Reservation::default();
                p.reserved_count -= 1;
            }
            30..=59 => {
                for (c, n) in tokens(action).unwrap().into_iter().enumerate() {
                    self.public.bank[c] -= n;
                    self.public.players[seat].tokens[c] += n;
                }
            }
            60..=79 => {
                for (c, n) in tokens(action).unwrap().into_iter().enumerate() {
                    self.public.bank[c] += n;
                    self.public.players[seat].tokens[c] -= n;
                }
            }
            80 => {}
            _ => unreachable!(),
        }
        self.public.turns += 1;
        self.public.current ^= 1;
        Ok(())
    }
    /// Exactly the native signed rewards, including 0.01 for a shared win.
    pub fn rewards(&self) -> Option<[f64; 2]> {
        if !self.public.turns.is_multiple_of(2) {
            return None;
        }
        let scores = self.public.players.each_ref().map(Player::score);
        if scores.iter().copied().max().unwrap() < 15 && self.public.turns < 124 {
            return None;
        }
        let ranks = self
            .public
            .players
            .each_ref()
            .map(|p| i32::from(p.score()) * 100 - i32::from(p.bonuses.iter().sum::<u8>()));
        Some(if ranks[0] == ranks[1] {
            [0.01, 0.01]
        } else if ranks[0] > ranks[1] {
            [1.0, -1.0]
        } else {
            [-1.0, 1.0]
        })
    }
    /// The frozen SplendoRust encoder sorts noble IDs. Keep that feature
    /// contract across environments; native rule slots remain unchanged.
    pub fn model_features(&self) -> [f32; 392] {
        let mut x = self.features();
        let mut order = [0usize, 1, 2];
        order.sort_by_key(|&slot| self.public.noble_ids[slot]);
        for base in [31, 36, 39] {
            let rows: [f32; 21] = x[base * 7..(base + 3) * 7].try_into().unwrap();
            for (new, &old) in order.iter().enumerate() {
                x[(base + new) * 7..(base + new + 1) * 7]
                    .copy_from_slice(&rows[old * 7..(old + 1) * 7]);
            }
        }
        x
    }
    pub fn features(&self) -> [f32; 392] {
        let o = &self.public;
        let mut x = [0.0; 392];
        x[..6].copy_from_slice(&o.bank.map(f32::from));
        x[6] = f32::from(o.turns);
        let card = |x: &mut [f32; 392], row: usize, id: u8| {
            if id != NONE {
                let c = CARDS[id as usize];
                for (color, cost) in c.cost.into_iter().enumerate() {
                    x[row * 7 + color] = f32::from(cost);
                }
                x[(row + 1) * 7 + c.bonus as usize] = 1.;
                x[(row + 1) * 7 + 6] = f32::from(c.points);
            }
        };
        for (slot, &id) in o.market.iter().enumerate() {
            card(&mut x, 1 + 2 * slot, id);
        }
        for tier in 0..3 {
            let mut bits = [0u8; 5];
            for id in 0..90 {
                if self.decks[tier] & (1u128 << id) != 0 {
                    let color = CARD_GROUP[id] as usize;
                    x[(25 + 2 * tier) * 7 + color] += 1.;
                    bits[color] |= 128 >> CARD_SLOT[id];
                }
            }
            for (color, b) in bits.into_iter().enumerate() {
                x[(26 + 2 * tier) * 7 + color] = f32::from(b as i8);
            }
        }
        let noble = |x: &mut [f32; 392], row: usize, slot: usize| {
            for (c, n) in NOBLES[o.noble_ids[slot] as usize].into_iter().enumerate() {
                x[row * 7 + c] = f32::from(n);
            }
            x[row * 7 + 6] = 3.;
        };
        for slot in 0..3 {
            if o.nobles & (1 << slot) != 0 {
                noble(&mut x, 31 + slot, slot);
            }
        }
        for relative in 0..2 {
            let p = &o.players[(o.current as usize + relative) % 2];
            for (c, t) in p.tokens.into_iter().enumerate() {
                x[(34 + relative) * 7 + c] = f32::from(t);
            }
            for (c, b) in p.bonuses.into_iter().enumerate() {
                x[(42 + relative) * 7 + c] = f32::from(b);
            }
            x[(42 + relative) * 7 + 6] = f32::from(p.card_points);
            for slot in 0..3 {
                if p.nobles & (1 << slot) != 0 {
                    noble(&mut x, 36 + 3 * relative + slot, slot);
                }
                card(&mut x, 44 + 6 * relative + 2 * slot, p.reserved[slot].card);
            }
        }
        x
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn opening() -> State {
        let market = [0, 1, 2, 3, 40, 41, 42, 43, 70, 71, 72, 73];
        let mut decks = [0u128; 3];
        for (id, c) in CARDS.iter().enumerate() {
            if !market.contains(&(id as u8)) {
                decks[c.tier as usize] |= 1u128 << id;
            }
        }
        State {
            public: Observation {
                viewer: 0,
                current: 0,
                turns: 0,
                bank: [4, 4, 4, 4, 4, 5],
                market,
                remaining: [36, 26, 16],
                noble_ids: [0, 1, 2],
                nobles: 7,
                players: [Player::default(), Player::default()],
            },
            decks,
        }
    }
    #[test]
    fn native_small_takes_returns_and_pass_are_whole_turns() {
        let mut s = opening();
        assert!(s.legal().contains(&30));
        assert!(s.legal().contains(&80));
        let mut r = Rng::new(1);
        s.apply(30, &mut r, None).unwrap();
        s.apply(80, &mut r, None).unwrap();
        assert!(s.legal().contains(&60));
        s.apply(60, &mut r, None).unwrap();
        assert_eq!(s.public.players[0].tokens, [0; 6]);
        assert_eq!(s.public.turns, 3);
        assert_eq!(s.public.current, 1);
        s.observe(1).validate().unwrap();
    }
    #[test]
    fn native_reserve_at_cap_omits_gold_and_takes_do_not_overflow() {
        let mut s = opening();
        s.public.players[0].tokens = [2, 2, 2, 2, 2, 0];
        s.public.bank = [2, 2, 2, 2, 2, 5];
        assert!(s.legal().contains(&24));
        assert!(!s.legal().contains(&30));
        s.apply(24, &mut Rng::new(2), None).unwrap();
        assert_eq!(s.public.players[0].tokens, [2, 2, 2, 2, 2, 0]);
        assert_eq!(s.public.bank[5], 5);
        assert_eq!(s.public.players[0].reserved_count, 1);
        s.observe(1).validate().unwrap();
    }
    #[test]
    fn native_colored_first_payment_and_multiple_nobles_on_purchase_only() {
        let mut s = opening();
        s.public.players[0].bonuses = [5; 5];
        s.public.players[0].tokens = [1, 1, 1, 1, 1, 2];
        s.public.bank = [3, 3, 3, 3, 3, 3];
        let mut take = s.clone();
        take.apply(30, &mut Rng::new(1), None).unwrap();
        assert_eq!(take.public.nobles, 7);
        let mut reserve = s.clone();
        reserve.apply(12, &mut Rng::new(1), None).unwrap();
        assert_eq!(reserve.public.nobles, 7);
        s.apply(0, &mut Rng::new(1), None).unwrap();
        assert_eq!(s.public.nobles, 0);
        assert_eq!(s.public.players[0].nobles, 7);
        assert_eq!(s.public.players[0].tokens, [1, 1, 1, 1, 1, 2]);
        let mut paid = opening();
        let id = paid.public.market[0];
        let c = CARDS[id as usize];
        paid.public.players[0].tokens[..5].copy_from_slice(&c.cost);
        paid.public.players[0].tokens[5] = 2;
        for color in 0..5 {
            paid.public.bank[color] -= c.cost[color];
        }
        paid.public.bank[5] -= 2;
        paid.apply(0, &mut Rng::new(1), None).unwrap();
        assert_eq!(paid.public.players[0].tokens[..5], [0; 5]);
        assert_eq!(paid.public.players[0].tokens[5], 2);
    }
    #[test]
    fn native_cap_and_shared_reward_differ_from_canonical() {
        let mut s = opening();
        s.public.turns = 122;
        s.apply(80, &mut Rng::new(0), None).unwrap();
        assert_eq!(s.rewards(), None);
        s.apply(80, &mut Rng::new(0), None).unwrap();
        assert_eq!(s.rewards(), Some([0.01, 0.01]));
        let before = s.clone();
        assert!(s.apply(80, &mut Rng::new(0), None).is_err());
        assert_eq!(s, before);
        s.public.players[0].card_points = 1;
        assert_eq!(s.rewards(), Some([1., -1.]));
        s.public.players[1].card_points = 1;
        s.public.players[0].bonuses[0] = 1;
        assert_eq!(s.rewards(), Some([-1., 1.]));
    }
    #[test]
    fn native_observation_is_independent_of_real_blind_identity() {
        let mut s = opening();
        s.apply(24, &mut Rng::new(12), None).unwrap();
        let o = s.observe(1);
        assert_eq!(o.players[0].reserved[0].card, NONE);
        let a = o.determinize(&mut Rng::new(20)).unwrap();
        let b = o.determinize(&mut Rng::new(21)).unwrap();
        assert_ne!(a, b);
        assert_eq!(a.observe(1), b.observe(1));
        assert_eq!(
            a.observe(1)
                .determinize(&mut Rng::new(31))
                .unwrap()
                .features(),
            b.observe(1)
                .determinize(&mut Rng::new(31))
                .unwrap()
                .features()
        );
        let mut leak = o.clone();
        leak.players[0].reserved[0].card = s.public.players[0].reserved[0].card;
        assert!(leak.validate().is_err());
        let mut actor = o.clone();
        actor.viewer = 0;
        assert!(actor.validate().is_err());
    }
    #[test]
    fn same_model_feature_contract_in_canonical_and_native_openings() {
        for seed in 0..64 {
            let canonical = splendor_core::GameState::new(2, seed).unwrap().observe(0);
            let ids: Vec<_> = (0..10)
                .filter(|id| canonical.nobles & (1 << id) != 0)
                .collect();
            let native = Observation {
                viewer: 0,
                current: 0,
                turns: 0,
                bank: canonical.bank,
                market: canonical.market,
                remaining: canonical.remaining,
                noble_ids: [ids[2], ids[0], ids[1]],
                nobles: 7,
                players: [Player::default(), Player::default()],
            }
            .determinize(&mut Rng::new(99))
            .unwrap();
            assert_eq!(
                native.model_features(),
                crate::transfer::encode(&canonical, &mut Rng::new(99))
            );
        }
    }
    #[test]
    fn all_eighty_one_native_action_ids_are_supported_without_projection() {
        for a in 0u8..81 {
            match a {
                0..=29 | 80 => assert!(tokens(a).is_none()),
                30..=54 | 60..=74 => {
                    assert!((1..=3).contains(&tokens(a).unwrap().iter().sum::<u8>()))
                }
                55..=59 | 75..=79 => assert_eq!(tokens(a).unwrap().iter().sum::<u8>(), 2),
                _ => unreachable!(),
            }
        }
        let mut s = opening();
        let before = s.clone();
        assert!(s.apply(81, &mut Rng::new(0), None).is_err());
        assert_eq!(s, before);
    }
}

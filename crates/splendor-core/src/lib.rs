#![forbid(unsafe_code)]
//! Deterministic base Splendor. No I/O, clocks, global RNG, or agent dependencies.
pub mod data;
mod rng;
use arrayvec::ArrayVec;
use data::{CARDS, NOBLES};
pub use rng::Rng;

pub const ENGINE_VERSION: &str = "splendorust-v1";
pub const NONE: u8 = 255;
pub const GOLD: usize = 5;
/// Maximum: 252 payments (at most five wild tokens over five colors).
pub type ActionSet = ArrayVec<Action, 256>;
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Action {
    Take([u8; 5]),
    ReserveVisible(u8), // market index 0..12
    ReserveDeck(u8),
    BuyVisible(u8),
    BuyReserved(u8),
    Pay([u8; 5]), // colored payment; gold is the remaining discounted cost
    Return([u8; 6]),
    Noble(u8), // noble ID
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Source {
    Market(u8),
    Reserved(u8),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Main,
    Payment(Source),
    Return,
    Noble,
    Terminal,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Reservation {
    pub card: u8,
    pub tier: u8,
    pub public: bool,
}
impl Reservation {
    const EMPTY: Self = Self {
        card: NONE,
        tier: 0,
        public: false,
    };
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Player {
    pub tokens: [u8; 6],
    pub bonuses: [u8; 5],
    pub score: u8,
    pub owned: u128,
    pub nobles: u16,
    pub reserved: [Reservation; 3],
}
impl Default for Player {
    fn default() -> Self {
        Self {
            tokens: [0; 6],
            bonuses: [0; 5],
            score: 0,
            owned: 0,
            nobles: 0,
            reserved: [Reservation::EMPTY; 3],
        }
    }
}
impl Player {
    pub fn token_count(&self) -> u8 {
        self.tokens.iter().sum()
    }
    pub fn card_count(&self) -> u8 {
        self.owned.count_ones() as u8
    }
    pub fn reserve_count(&self) -> usize {
        self.reserved.iter().filter(|r| r.card != NONE).count()
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GameState {
    players: [Player; 4],
    count: u8,
    current: u8,
    bank: [u8; 6],
    market: [u8; 12],
    decks: [[u8; 40]; 3],
    remaining: [u8; 3],
    nobles: u16,
    initial_nobles: u16,
    phase: Phase,
    final_round: bool,
    turns: u32,
}
/// Contains no seed, RNG state, deck order, or opponent's private card IDs.
/// Public reservations remain known: an agent can remember a visible reservation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Observation {
    pub players: [Player; 4], // hidden reservations have card=NONE, tier retained
    pub reserved_counts: [u8; 4],
    pub count: u8,
    pub viewer: u8,
    pub current: u8,
    pub bank: [u8; 6],
    pub market: [u8; 12],
    pub remaining: [u8; 3],
    pub nobles: u16,
    pub phase: Phase,
    pub final_round: bool,
    pub turns: u32,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RuleError {
    PlayerCount,
    IllegalAction,
    InvalidObservation,
    Invariant(&'static str),
}
impl std::fmt::Display for RuleError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for RuleError {}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GameOutcome {
    pub winners: u8,
    pub ranks: [u8; 4],
    pub scores: [u8; 4],
}

impl GameState {
    pub fn new(count: u8, seed: u64) -> Result<Self, RuleError> {
        if !(2..=4).contains(&count) {
            return Err(RuleError::PlayerCount);
        }
        let supply = [0, 0, 4, 5, 7][count as usize];
        let mut s = Self {
            players: [Player::default(); 4],
            count,
            current: 0,
            bank: [supply; 6],
            market: [NONE; 12],
            decks: [[NONE; 40]; 3],
            remaining: [40, 30, 20],
            nobles: 0,
            initial_nobles: 0,
            phase: Phase::Main,
            final_round: false,
            turns: 0,
        };
        s.bank[GOLD] = 5;
        let mut rng = Rng::new(seed);
        for (t, (start, len)) in [(0, 40), (40, 30), (70, 20)].into_iter().enumerate() {
            for i in 0..len {
                s.decks[t][i] = (start + i) as u8;
            }
            rng.shuffle(&mut s.decks[t][..len]);
            for i in 0..4 {
                s.market[t * 4 + i] = s.draw(t);
            }
        }
        let mut ns = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
        rng.shuffle(&mut ns);
        for &n in &ns[..count as usize + 1] {
            s.nobles |= 1 << n;
        }
        s.initial_nobles = s.nobles;
        Ok(s)
    }
    pub fn current_player(&self) -> usize {
        self.current as usize
    }
    pub fn player_count(&self) -> usize {
        self.count as usize
    }
    pub fn phase(&self) -> Phase {
        self.phase
    }
    pub fn turns(&self) -> u32 {
        self.turns
    }
    pub fn is_terminal(&self) -> bool {
        self.phase == Phase::Terminal
    }
    pub fn observe(&self, viewer: usize) -> Observation {
        assert!(viewer < self.player_count());
        let mut players = self.players;
        let mut reserved_counts = [0; 4];
        for (i, p) in players.iter_mut().enumerate() {
            reserved_counts[i] = p.reserve_count() as u8;
            if i != viewer {
                for r in &mut p.reserved {
                    if !r.public {
                        r.card = NONE;
                    }
                }
            }
        }
        Observation {
            players,
            reserved_counts,
            count: self.count,
            viewer: viewer as u8,
            current: self.current,
            bank: self.bank,
            market: self.market,
            remaining: self.remaining,
            nobles: self.nobles,
            phase: self.phase,
            final_round: self.final_round,
            turns: self.turns,
        }
    }
    fn draw(&mut self, t: usize) -> u8 {
        if self.remaining[t] == 0 {
            return NONE;
        }
        self.remaining[t] -= 1;
        let i = self.remaining[t] as usize;
        let c = self.decks[t][i];
        self.decks[t][i] = NONE;
        c
    }
    fn source_card(&self, source: Source) -> Option<u8> {
        let c = match source {
            Source::Market(i) => *self.market.get(i as usize)?,
            Source::Reserved(i) => {
                self.players[self.current_player()]
                    .reserved
                    .get(i as usize)?
                    .card
            }
        };
        (c != NONE).then_some(c)
    }
    fn cost(&self, card: u8) -> [u8; 5] {
        let p = &self.players[self.current_player()];
        std::array::from_fn(|i| CARDS[card as usize].cost[i].saturating_sub(p.bonuses[i]))
    }
    fn affordable(&self, card: u8) -> bool {
        let p = &self.players[self.current_player()];
        let cost = self.cost(card);
        let deficit: u8 = (0..5).map(|i| cost[i].saturating_sub(p.tokens[i])).sum();
        deficit <= p.tokens[GOLD]
    }
    fn eligible(&self) -> u16 {
        let p = &self.players[self.current_player()];
        let mut mask = 0;
        for (n, req) in NOBLES.iter().enumerate() {
            if self.nobles & (1 << n) != 0 && (0..5).all(|i| p.bonuses[i] >= req[i]) {
                mask |= 1 << n;
            }
        }
        mask
    }
    /// Reuses caller-owned stack storage. Enumeration order is versioned.
    pub fn legal_actions(&self, out: &mut ActionSet) {
        out.clear();
        let p = &self.players[self.current_player()];
        match self.phase {
            Phase::Terminal => {}
            Phase::Main => {
                let available = (0..5).filter(|&i| self.bank[i] > 0).count().min(3) as u32;
                if available > 0 {
                    for mask in 1u8..32 {
                        if mask.count_ones() == available
                            && (0..5).all(|i| mask & (1 << i) == 0 || self.bank[i] > 0)
                        {
                            out.push(Action::Take(std::array::from_fn(|i| {
                                u8::from(mask & (1 << i) != 0)
                            })));
                        }
                    }
                }
                for i in 0..5 {
                    if self.bank[i] >= 4 {
                        let mut take = [0; 5];
                        take[i] = 2;
                        out.push(Action::Take(take));
                    }
                }
                for i in 0..12 {
                    let c = self.market[i];
                    if c != NONE {
                        if self.affordable(c) {
                            out.push(Action::BuyVisible(i as u8));
                        }
                        if p.reserve_count() < 3 {
                            out.push(Action::ReserveVisible(i as u8));
                        }
                    }
                }
                for i in 0..3 {
                    if p.reserved[i].card != NONE && self.affordable(p.reserved[i].card) {
                        out.push(Action::BuyReserved(i as u8));
                    }
                    if p.reserve_count() < 3 && self.remaining[i] > 0 {
                        out.push(Action::ReserveDeck(i as u8));
                    }
                }
            }
            Phase::Payment(source) => {
                let cost = self.cost(self.source_card(source).expect("valid pending card"));
                payments(0, cost, &p.tokens, p.tokens[GOLD], [0; 5], out);
            }
            Phase::Return => returns(0, p.token_count() - 10, &p.tokens, [0; 6], out),
            Phase::Noble => {
                let mask = self.eligible();
                for i in 0..10 {
                    if mask & (1 << i) != 0 {
                        out.push(Action::Noble(i));
                    }
                }
            }
        }
    }
    /// Rejects invalid actions without changing any state. No legal-list scan needed.
    pub fn apply_action(&mut self, a: Action) -> Result<(), RuleError> {
        if !self.valid_action(a) {
            return Err(RuleError::IllegalAction);
        }
        let pi = self.current_player();
        match a {
            Action::Take(t) => {
                for (i, &v) in t.iter().enumerate() {
                    self.bank[i] -= v;
                    self.players[pi].tokens[i] += v;
                }
                self.after_tokens();
            }
            Action::ReserveVisible(i) => {
                let c = self.market[i as usize];
                self.market[i as usize] = self.draw(i as usize / 4);
                self.reserve(c, true);
            }
            Action::ReserveDeck(t) => {
                let c = self.draw(t as usize);
                self.reserve(c, false);
            }
            Action::BuyVisible(i) => self.phase = Phase::Payment(Source::Market(i)),
            Action::BuyReserved(i) => self.phase = Phase::Payment(Source::Reserved(i)),
            Action::Pay(payment) => {
                let Phase::Payment(src) = self.phase else {
                    unreachable!()
                };
                let c = self.source_card(src).unwrap();
                let cost = self.cost(c);
                let gold: u8 = (0..5).map(|i| cost[i] - payment[i]).sum();
                for (i, &v) in payment.iter().enumerate() {
                    self.players[pi].tokens[i] -= v;
                    self.bank[i] += v;
                }
                self.players[pi].tokens[GOLD] -= gold;
                self.bank[GOLD] += gold;
                match src {
                    Source::Market(i) => self.market[i as usize] = self.draw(i as usize / 4),
                    Source::Reserved(i) => {
                        let n = self.players[pi].reserve_count();
                        for j in i as usize..n - 1 {
                            self.players[pi].reserved[j] = self.players[pi].reserved[j + 1];
                        }
                        self.players[pi].reserved[n - 1] = Reservation::EMPTY;
                    }
                }
                let card = CARDS[c as usize];
                self.players[pi].owned |= 1u128 << c;
                self.players[pi].bonuses[card.bonus as usize] += 1;
                self.players[pi].score += card.points;
                self.after_tokens();
            }
            Action::Return(r) => {
                for (i, &v) in r.iter().enumerate() {
                    self.players[pi].tokens[i] -= v;
                    self.bank[i] += v;
                }
                self.after_tokens();
            }
            Action::Noble(n) => {
                self.claim(n);
                self.end_turn();
            }
        }
        Ok(())
    }
    fn valid_action(&self, a: Action) -> bool {
        let p = &self.players[self.current_player()];
        match (self.phase, a) {
            (Phase::Main, Action::Take(t)) => {
                let sum: u16 = t.iter().map(|&x| x as u16).sum();
                if (0..5).any(|i| t[i] > self.bank[i]) {
                    return false;
                }
                (sum == 2 && t.contains(&2) && (0..5).all(|i| t[i] != 2 || self.bank[i] >= 4))
                    || (sum > 0
                        && sum == self.bank[..5].iter().filter(|&&x| x > 0).count().min(3) as u16
                        && t.iter().all(|&x| x <= 1))
            }
            (Phase::Main, Action::ReserveVisible(i)) => {
                p.reserve_count() < 3 && self.market.get(i as usize).is_some_and(|&c| c != NONE)
            }
            (Phase::Main, Action::ReserveDeck(t)) => {
                p.reserve_count() < 3 && self.remaining.get(t as usize).is_some_and(|&n| n > 0)
            }
            (Phase::Main, Action::BuyVisible(i)) => self
                .source_card(Source::Market(i))
                .is_some_and(|c| self.affordable(c)),
            (Phase::Main, Action::BuyReserved(i)) => self
                .source_card(Source::Reserved(i))
                .is_some_and(|c| self.affordable(c)),
            (Phase::Payment(src), Action::Pay(pay)) => {
                let cost = self.cost(self.source_card(src).unwrap());
                if (0..5).any(|i| pay[i] > cost[i] || pay[i] > p.tokens[i]) {
                    return false;
                }
                (0..5).map(|i| cost[i] - pay[i]).sum::<u8>() <= p.tokens[GOLD]
            }
            (Phase::Return, Action::Return(r)) => {
                (0..6).all(|i| r[i] <= p.tokens[i])
                    && r.iter().map(|&v| v as u16).sum::<u16>() == u16::from(p.token_count() - 10)
            }
            (Phase::Noble, Action::Noble(n)) => n < 10 && self.eligible() & (1 << n) != 0,
            _ => false,
        }
    }
    fn reserve(&mut self, c: u8, public: bool) {
        let pi = self.current_player();
        let n = self.players[pi].reserve_count();
        self.players[pi].reserved[n] = Reservation {
            card: c,
            tier: CARDS[c as usize].tier,
            public,
        };
        if self.bank[GOLD] > 0 {
            self.bank[GOLD] -= 1;
            self.players[pi].tokens[GOLD] += 1;
        }
        self.after_tokens();
    }
    fn after_tokens(&mut self) {
        if self.players[self.current_player()].token_count() > 10 {
            self.phase = Phase::Return;
            return;
        }
        let eligible = self.eligible();
        if eligible.count_ones() > 1 {
            self.phase = Phase::Noble;
            return;
        }
        if eligible != 0 {
            self.claim(eligible.trailing_zeros() as u8);
        }
        self.end_turn();
    }
    fn claim(&mut self, n: u8) {
        let pi = self.current_player();
        self.nobles &= !(1 << n);
        self.players[pi].nobles |= 1 << n;
        self.players[pi].score += 3;
    }
    fn end_turn(&mut self) {
        if self.players[self.current_player()].score >= 15 {
            self.final_round = true;
        }
        self.turns += 1;
        self.current = (self.current + 1) % self.count;
        self.phase = if self.current == 0 && self.final_round {
            Phase::Terminal
        } else {
            Phase::Main
        };
    }
    pub fn outcome(&self) -> Option<GameOutcome> {
        if !self.is_terminal() {
            return None;
        }
        let mut ranks = [0; 4];
        let mut scores = [0; 4];
        let mut winners = 0;
        for i in 0..self.player_count() {
            let p = &self.players[i];
            scores[i] = p.score;
            ranks[i] = 1;
            for q in &self.players[..self.player_count()] {
                if q.score > p.score || (q.score == p.score && q.card_count() < p.card_count()) {
                    ranks[i] += 1;
                }
            }
            if ranks[i] == 1 {
                winners |= 1 << i;
            }
        }
        Some(GameOutcome {
            winners,
            ranks,
            scores,
        })
    }
    /// Expensive audit for tests/debug runs. Not used on the normal hot path.
    pub fn check_invariants(&self) -> Result<(), RuleError> {
        let fail = |s| Err(RuleError::Invariant(s));
        if !(2..=4).contains(&self.count) || self.current >= self.count {
            return fail("player index");
        }
        if self.turns % u32::from(self.count) != u32::from(self.current) {
            return fail("turn order");
        }
        if self.final_round
            && !self.players[..self.player_count()]
                .iter()
                .any(|p| p.score >= 15)
        {
            return fail("final round threshold");
        }
        let mut seen = 0u128;
        let mut ns = self.nobles;
        let add = |seen: &mut u128, c: u8| -> bool {
            if c >= 90 || *seen & (1u128 << c) != 0 {
                false
            } else {
                *seen |= 1u128 << c;
                true
            }
        };
        for t in 0..3 {
            if self.remaining[t] as usize > [40, 30, 20][t] {
                return fail("deck size");
            }
            for i in 0..40 {
                let c = self.decks[t][i];
                if i < self.remaining[t] as usize {
                    if !add(&mut seen, c) || CARDS[c as usize].tier as usize != t {
                        return fail("deck card");
                    }
                } else if c != NONE {
                    return fail("deck tail");
                }
            }
        }
        for (i, &c) in self.market.iter().enumerate() {
            if c == NONE && self.remaining[i / 4] > 0 {
                return fail("market refill");
            }
            if c != NONE && (!add(&mut seen, c) || CARDS[c as usize].tier as usize != i / 4) {
                return fail("market card");
            }
        }
        let mut totals = self.bank.map(u16::from);
        for (i, p) in self.players.iter().enumerate() {
            if i >= self.player_count() {
                if *p != Player::default() {
                    return fail("inactive player");
                }
                continue;
            }
            let limit = if i == self.current_player() && self.phase == Phase::Return {
                13
            } else {
                10
            };
            if p.tokens.iter().map(|&x| x as u16).sum::<u16>() > limit {
                return fail("token limit");
            }
            if p.owned >> 90 != 0 {
                return fail("owned bits");
            }
            let mut bonuses = [0; 5];
            let mut score = p.nobles.count_ones() as u16 * 3;
            let mut owned = p.owned;
            while owned != 0 {
                let c = owned.trailing_zeros() as usize;
                owned &= owned - 1;
                if !add(&mut seen, c as u8) {
                    return fail("owned duplicate");
                }
                let card = &CARDS[c];
                bonuses[card.bonus as usize] += 1;
                score += card.points as u16;
            }
            if bonuses != p.bonuses || score != p.score as u16 {
                return fail("score or bonuses");
            }
            let mut empty = false;
            for r in &p.reserved {
                if r.card == NONE {
                    empty = true;
                    if *r != Reservation::EMPTY {
                        return fail("reserve tail");
                    }
                } else if empty || !add(&mut seen, r.card) || CARDS[r.card as usize].tier != r.tier
                {
                    return fail("reserved card");
                }
            }
            if ns & p.nobles != 0 {
                return fail("noble duplicate");
            }
            ns |= p.nobles;
            for (n, req) in NOBLES.iter().enumerate() {
                if p.nobles & (1 << n) != 0 && (0..5).any(|c| p.bonuses[c] < req[c]) {
                    return fail("unearned noble");
                }
            }
            for (c, v) in totals.iter_mut().enumerate() {
                *v += p.tokens[c] as u16;
            }
        }
        if seen != (1u128 << 90) - 1 {
            return fail("missing card");
        }
        if ns != self.initial_nobles || ns >> 10 != 0 || ns.count_ones() != self.count as u32 + 1 {
            return fail("noble set");
        }
        for (i, &total) in totals.iter().enumerate() {
            if total
                != if i == GOLD {
                    5
                } else {
                    [0, 0, 4, 5, 7][self.count as usize]
                }
            {
                return fail("token conservation");
            }
        }
        match self.phase {
            Phase::Return if self.players[self.current_player()].token_count() <= 10 => {
                return fail("return phase");
            }
            Phase::Noble if self.eligible().count_ones() < 2 => return fail("noble phase"),
            Phase::Payment(src) if !self.source_card(src).is_some_and(|c| self.affordable(c)) => {
                return fail("payment phase");
            }
            Phase::Terminal if !self.final_round || self.current != 0 => {
                return fail("terminal phase");
            }
            _ => {}
        }
        Ok(())
    }
}
fn payments(
    i: usize,
    cost: [u8; 5],
    tokens: &[u8; 6],
    gold: u8,
    mut pay: [u8; 5],
    out: &mut ActionSet,
) {
    if i == 5 {
        out.push(Action::Pay(pay));
        return;
    }
    let min = cost[i].saturating_sub(tokens[i]);
    let max = cost[i].min(gold);
    for wild in min..=max {
        pay[i] = cost[i] - wild;
        payments(i + 1, cost, tokens, gold - wild, pay, out);
    }
}
fn returns(i: usize, left: u8, tokens: &[u8; 6], mut r: [u8; 6], out: &mut ActionSet) {
    if i == 5 {
        if left <= tokens[i] {
            r[i] = left;
            out.push(Action::Return(r));
        }
        return;
    }
    for n in 0..=left.min(tokens[i]) {
        r[i] = n;
        returns(i + 1, left - n, tokens, r, out);
    }
}

impl Observation {
    /// Uniform assignment of all unknown cards, conditioned on visible/private cards
    /// and recorded reservation tiers. Does not infer opponents' past strategy.
    pub fn determinize(&self, rng: &mut Rng) -> Result<GameState, RuleError> {
        if !(2..=4).contains(&self.count)
            || self.viewer >= self.count
            || self.current >= self.count
            || self.reserved_counts.iter().any(|&n| n > 3)
        {
            return Err(RuleError::InvalidObservation);
        }
        let mut known = 0u128;
        let mut add = |c: u8| -> Result<(), RuleError> {
            if c >= 90 || known & (1u128 << c) != 0 {
                return Err(RuleError::InvalidObservation);
            }
            known |= 1u128 << c;
            Ok(())
        };
        for &c in &self.market {
            if c != NONE {
                add(c)?;
            }
        }
        for (pi, p) in self.players.iter().enumerate() {
            if p.owned >> 90 != 0 {
                return Err(RuleError::InvalidObservation);
            }
            let mut owned = p.owned;
            while owned != 0 {
                let c = owned.trailing_zeros() as u8;
                owned &= owned - 1;
                add(c)?;
            }
            for (j, r) in p.reserved.iter().enumerate() {
                if j < self.reserved_counts[pi] as usize {
                    if r.tier >= 3 {
                        return Err(RuleError::InvalidObservation);
                    }
                    if r.card != NONE {
                        if pi != self.viewer as usize && !r.public {
                            return Err(RuleError::InvalidObservation);
                        }
                        add(r.card)?;
                    } else if pi == self.viewer as usize || r.public {
                        return Err(RuleError::InvalidObservation);
                    }
                }
            }
        }
        let mut pools = [[NONE; 40]; 3];
        let mut len = [0usize; 3];
        for (c, card) in CARDS.iter().enumerate() {
            if known & (1u128 << c) == 0 {
                let t = card.tier as usize;
                pools[t][len[t]] = c as u8;
                len[t] += 1;
            }
        }
        for t in 0..3 {
            rng.shuffle(&mut pools[t][..len[t]]);
        }
        let mut players = self.players;
        for (pi, p) in players.iter_mut().enumerate() {
            for r in &mut p.reserved[..self.reserved_counts[pi] as usize] {
                if r.card == NONE {
                    let t = r.tier as usize;
                    if len[t] == 0 {
                        return Err(RuleError::InvalidObservation);
                    }
                    len[t] -= 1;
                    r.card = pools[t][len[t]];
                    pools[t][len[t]] = NONE;
                }
            }
        }
        if (0..3).any(|t| len[t] != self.remaining[t] as usize) {
            return Err(RuleError::InvalidObservation);
        }
        let s = GameState {
            players,
            count: self.count,
            current: self.current,
            bank: self.bank,
            market: self.market,
            decks: pools,
            remaining: self.remaining,
            nobles: self.nobles,
            initial_nobles: self.players.iter().fold(self.nobles, |ns, p| ns | p.nobles),
            phase: self.phase,
            final_round: self.final_round,
            turns: self.turns,
        };
        s.check_invariants()?;
        Ok(s)
    }
}
#[cfg(test)]
mod tests;

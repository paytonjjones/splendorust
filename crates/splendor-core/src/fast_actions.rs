//! Production legal-action enumeration.
//!
//! This path preserves the action order of `GameState::legal_actions_reference`.
//! Take actions are precomputed for each bank-availability and double-take
//! threshold mask. Main-phase buying power is computed once, and payment
//! enumeration removes only trailing zero-cost recursion levels. Those levels
//! each have one branch and do not change order. Returns keep the full canonical
//! colored and gold enumeration from the reference routine.
use super::{Action, ActionSet, CARDS, GOLD, GameState, Phase, returns};

#[derive(Clone, Copy)]
struct TakeRow {
    actions: [Action; 10],
    len: usize,
}

impl TakeRow {
    const EMPTY: Self = Self {
        actions: [Action::Take([0; 5]); 10],
        len: 0,
    };
}

const fn take_action(mask: u8) -> Action {
    Action::Take([
        mask & 1,
        (mask >> 1) & 1,
        (mask >> 2) & 1,
        (mask >> 3) & 1,
        (mask >> 4) & 1,
    ])
}

const fn make_take_actions() -> [TakeRow; 32] {
    let mut rows = [TakeRow::EMPTY; 32];
    let mut bank_mask = 0u8;
    while bank_mask < 32 {
        let available = bank_mask.count_ones();
        let count = if available < 3 { available } else { 3 };
        if count != 0 {
            let mut take_mask = 1u8;
            while take_mask < 32 {
                if take_mask.count_ones() == count && take_mask & !bank_mask == 0 {
                    let row = &mut rows[bank_mask as usize];
                    row.actions[row.len] = take_action(take_mask);
                    row.len += 1;
                }
                take_mask += 1;
            }
        }
        bank_mask += 1;
    }
    rows
}

#[derive(Clone, Copy)]
struct DoubleRow {
    actions: [Action; 5],
    len: usize,
}

impl DoubleRow {
    const EMPTY: Self = Self {
        actions: [Action::Take([0; 5]); 5],
        len: 0,
    };
}

const fn make_double_actions() -> [DoubleRow; 32] {
    let mut rows = [DoubleRow::EMPTY; 32];
    let mut threshold_mask = 0u8;
    while threshold_mask < 32 {
        let mut color = 0;
        while color < 5 {
            if threshold_mask & (1 << color) != 0 {
                let mut take = [0; 5];
                take[color] = 2;
                let row = &mut rows[threshold_mask as usize];
                row.actions[row.len] = Action::Take(take);
                row.len += 1;
            }
            color += 1;
        }
        threshold_mask += 1;
    }
    rows
}

const TAKE_ACTIONS: [TakeRow; 32] = make_take_actions();
const DOUBLE_ACTIONS: [DoubleRow; 32] = make_double_actions();

// Base cards cost at most seven tokens of one color. A capacity of seven
// therefore covers every card for that color. Each bit refers to a canonical ID.
const fn make_color_affordability() -> [[u128; 8]; 5] {
    let mut masks = [[0u128; 8]; 5];
    let mut color = 0;
    while color < 5 {
        let mut capacity = 0;
        while capacity < 8 {
            let mut card = 0;
            while card < 90 {
                assert!(CARDS[card].cost[color] <= 7);
                if CARDS[card].cost[color] as usize <= capacity {
                    masks[color][capacity] |= 1u128 << card;
                }
                card += 1;
            }
            capacity += 1;
        }
        color += 1;
    }
    masks
}
const COLOR_AFFORDABILITY: [[u128; 8]; 5] = make_color_affordability();

#[inline(always)]
pub(super) fn legal_actions(state: &GameState, out: &mut ActionSet) {
    out.clear();
    let player = &state.players[state.current_player()];
    match state.phase {
        Phase::Terminal => {}
        Phase::Main => {
            let bank_mask = (0..5).fold(0u8, |mask, color| {
                mask | (u8::from(state.bank[color] > 0) << color)
            });
            let takes = &TAKE_ACTIONS[bank_mask as usize];
            out.try_extend_from_slice(&takes.actions[..takes.len])
                .expect("take actions fit ActionSet capacity");
            let double_mask = (0..5).fold(0u8, |mask, color| {
                mask | (u8::from(state.bank[color] >= 4) << color)
            });
            let doubles = &DOUBLE_ACTIONS[double_mask as usize];
            out.try_extend_from_slice(&doubles.actions[..doubles.len])
                .expect("double-take actions fit ActionSet capacity");

            let reserve_count = player.reserve_count();
            let can_reserve = reserve_count < 3;
            let buying_power: [u16; 5] = std::array::from_fn(|color| {
                u16::from(player.tokens[color]) + u16::from(player.bonuses[color])
            });
            let gold = player.tokens[GOLD];
            let colored_affordable = if gold == 0 {
                (0..5).fold(u128::MAX, |mask, color| {
                    mask & COLOR_AFFORDABILITY[color][buying_power[color].min(7) as usize]
                })
            } else {
                0
            };
            for slot in 0..12 {
                let card = state.market[slot];
                if card != super::NONE {
                    if affordable(card, &buying_power, gold, colored_affordable) {
                        out.push(Action::BuyVisible(slot as u8));
                    }
                    if can_reserve {
                        out.push(Action::ReserveVisible(slot as u8));
                    }
                }
            }
            for tier in 0..3 {
                let reserved_card = player.reserved[tier].card;
                if reserved_card != super::NONE
                    && affordable(reserved_card, &buying_power, gold, colored_affordable)
                {
                    out.push(Action::BuyReserved(tier as u8));
                }
                if can_reserve && state.remaining[tier] > 0 {
                    out.push(Action::ReserveDeck(tier as u8));
                }
            }
        }
        Phase::Payment(source) => {
            let card = state.source_card(source).expect("valid pending card");
            let cost = state.cost(card);
            enumerate_payments(cost, &player.tokens, player.tokens[GOLD], out);
        }
        Phase::Return => returns(0, player.token_count() - 10, &player.tokens, [0; 6], out),
        Phase::Noble => {
            let mask = state.eligible();
            for noble in 0..10 {
                if mask & (1 << noble) != 0 {
                    out.push(Action::Noble(noble));
                }
            }
        }
    }
}

fn affordable(card: u8, buying_power: &[u16; 5], gold: u8, colored_affordable: u128) -> bool {
    let cost = &CARDS[card as usize].cost;
    if gold == 0 {
        let word = if card < 64 {
            colored_affordable as u64
        } else {
            (colored_affordable >> 64) as u64
        };
        return word & (1u64 << (card & 63)) != 0;
    }
    let deficit: u16 = (0..5)
        .map(|color| u16::from(cost[color]).saturating_sub(buying_power[color]))
        .sum();
    deficit <= u16::from(gold)
}

pub(super) fn enumerate_payments(cost: [u8; 5], tokens: &[u8; 6], gold: u8, out: &mut ActionSet) {
    if gold == 0 {
        if (0..5).all(|color| cost[color] <= tokens[color]) {
            out.push(Action::Pay(cost));
        }
        return;
    }

    let Some(last_cost_color) = (0..5).rfind(|&color| cost[color] != 0) else {
        out.push(Action::Pay([0; 5]));
        return;
    };
    enumerate_payments_through(0, last_cost_color, cost, tokens, gold, [0; 5], out);
}

fn enumerate_payments_through(
    index: usize,
    last_cost_color: usize,
    cost: [u8; 5],
    tokens: &[u8; 6],
    gold: u8,
    mut payment: [u8; 5],
    out: &mut ActionSet,
) {
    if index > last_cost_color {
        out.push(Action::Pay(payment));
        return;
    }
    let min_wild = cost[index].saturating_sub(tokens[index]);
    let max_wild = cost[index].min(gold);
    for wild in min_wild..=max_wild {
        payment[index] = cost[index] - wild;
        enumerate_payments_through(
            index + 1,
            last_cost_color,
            cost,
            tokens,
            gold - wild,
            payment,
            out,
        );
    }
}

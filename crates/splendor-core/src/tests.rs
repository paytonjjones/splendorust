use super::*;
use crate::Rng;
use proptest::prelude::*;
fn actions(s: &GameState) -> ActionSet {
    let mut a = ActionSet::new();
    s.legal_actions(&mut a);
    a
}
fn reject(s: &mut GameState, a: Action) {
    let before = s.clone();
    assert_eq!(s.apply_action(a), Err(RuleError::IllegalAction));
    assert_eq!(*s, before);
}
fn tokens(s: &mut GameState, p: usize, t: [u8; 6]) {
    for (c, &v) in t.iter().enumerate() {
        s.bank[c] += s.players[p].tokens[c];
        s.bank[c] -= v;
    }
    s.players[p].tokens = t;
}
fn own(s: &mut GameState, pi: usize, c: u8) {
    let t = CARDS[c as usize].tier as usize;
    if let Some(i) = s.market.iter().position(|&v| v == c) {
        s.market[i] = s.draw(t);
    } else if let Some(i) = s.decks[t][..s.remaining[t] as usize]
        .iter()
        .position(|&v| v == c)
    {
        s.remaining[t] -= 1;
        let last = s.remaining[t] as usize;
        s.decks[t][i] = s.decks[t][last];
        s.decks[t][last] = NONE;
    } else {
        panic!("card unavailable");
    }
    s.players[pi].owned |= 1u128 << c;
    s.players[pi].bonuses[CARDS[c as usize].bonus as usize] += 1;
    s.players[pi].score += CARDS[c as usize].points;
}
#[test]
fn static_data_complete_and_auditable() {
    assert_eq!(CARDS.len(), 90);
    assert_eq!(NOBLES.len(), 10);
    for t in 0..3 {
        let rows: Vec<_> = CARDS.iter().filter(|c| c.tier == t).collect();
        assert_eq!(rows.len(), [40, 30, 20][t as usize]);
        for color in 0..5 {
            assert_eq!(
                rows.iter().filter(|c| c.bonus == color).count(),
                [8, 6, 4][t as usize]
            );
        }
    }
    for (i, c) in CARDS.iter().enumerate() {
        assert!(c.bonus < 5 && c.cost.iter().all(|&n| n <= 7));
        assert!(!CARDS[..i].contains(c));
        assert!(match c.tier {
            0 => c.points <= 1,
            1 => (1..=3).contains(&c.points),
            2 => (3..=5).contains(&c.points),
            _ => false,
        });
    }
    for (i, n) in NOBLES.iter().enumerate() {
        assert!(!NOBLES[..i].contains(n));
        assert!(
            n.iter().filter(|&&x| x == 4).count() == 2
                || n.iter().filter(|&&x| x == 3).count() == 3
        );
    }
    let csv = include_str!("../../../data/cards.csv");
    let colors = ["white", "blue", "green", "red", "black"];
    for (i, line) in csv.lines().skip(1).enumerate() {
        let r: Vec<_> = line.split(',').collect();
        let c = CARDS[i];
        assert_eq!(r[0].parse::<usize>().unwrap(), i);
        assert_eq!(r[1].parse::<u8>().unwrap(), c.tier + 1);
        assert_eq!(r[2], colors[c.bonus as usize]);
        assert_eq!(r[3].parse::<u8>().unwrap(), c.points);
        for j in 0..5 {
            assert_eq!(r[4 + j].parse::<u8>().unwrap(), c.cost[j]);
        }
    }
}
#[test]
fn setup_counts_and_supply() {
    for n in 2..=4 {
        let s = GameState::new(n, 42).unwrap();
        assert_eq!(s.remaining, [36, 26, 16]);
        assert_eq!(s.nobles.count_ones(), n as u32 + 1);
        assert_eq!(
            s.bank,
            [
                match n {
                    2 => 4,
                    3 => 5,
                    _ => 7,
                },
                match n {
                    2 => 4,
                    3 => 5,
                    _ => 7,
                },
                match n {
                    2 => 4,
                    3 => 5,
                    _ => 7,
                },
                match n {
                    2 => 4,
                    3 => 5,
                    _ => 7,
                },
                match n {
                    2 => 4,
                    3 => 5,
                    _ => 7,
                },
                5
            ]
        );
        s.check_invariants().unwrap();
    }
    assert_eq!(GameState::new(1, 0), Err(RuleError::PlayerCount));
    assert_eq!(GameState::new(5, 0), Err(RuleError::PlayerCount));
}
#[test]
fn rng_golden_sequence() {
    let mut r = Rng::new(0);
    assert_eq!(r.next_u64(), 0xe220a8397b1dcdaf);
    assert_eq!(r.next_u64(), 0x6e789e6aa1b965f4);
    assert_eq!(r.next_u64(), 0x06c45d188009454f);
}
#[test]
fn initial_actions_exact() {
    let s = GameState::new(2, 1).unwrap();
    assert_eq!(actions(&s).len(), 30);
}
#[test]
fn different_gems_and_double_threshold() {
    let mut s = GameState::new(2, 1).unwrap();
    reject(&mut s, Action::Take([1, 1, 0, 0, 0]));
    reject(&mut s, Action::Take([2, 1, 0, 0, 0]));
    reject(&mut s, Action::Take([255; 5]));
    s.apply_action(Action::Take([2, 0, 0, 0, 0])).unwrap();
    reject(&mut s, Action::Take([2, 0, 0, 0, 0]));
    s.apply_action(Action::Take([1, 1, 1, 0, 0])).unwrap();
    s.check_invariants().unwrap();
    s.bank = [0, 1, 0, 2, 0, 5];
    assert!(actions(&s).contains(&Action::Take([0, 1, 0, 1, 0])));
    reject(&mut s, Action::Take([0, 1, 0, 0, 0]));
    s.bank = [0, 0, 0, 1, 0, 5];
    assert!(actions(&s).contains(&Action::Take([0, 0, 0, 1, 0])));
    s.bank = [0, 0, 0, 0, 0, 5];
    assert!(!actions(&s).iter().any(|a| matches!(a, Action::Take(_))));
}
#[test]
fn visible_reservation_and_refill() {
    let mut s = GameState::new(2, 9).unwrap();
    let c = s.market[0];
    s.apply_action(Action::ReserveVisible(0)).unwrap();
    assert_eq!(s.players[0].reserved[0].card, c);
    assert!(s.players[0].reserved[0].public);
    assert_ne!(s.market[0], c);
    assert_eq!(s.remaining[0], 35);
    assert_eq!(s.players[0].tokens[GOLD], 1);
    assert_eq!(s.bank[GOLD], 4);
    s.check_invariants().unwrap();
}
#[test]
fn blind_reservation_does_not_refill_market() {
    let mut s = GameState::new(2, 9).unwrap();
    let m = s.market;
    let c = s.decks[1][25];
    s.apply_action(Action::ReserveDeck(1)).unwrap();
    assert_eq!(s.market, m);
    assert_eq!(s.players[0].reserved[0].card, c);
    assert!(!s.players[0].reserved[0].public);
    assert_eq!(s.remaining[1], 25);
    s.check_invariants().unwrap();
}
#[test]
fn reservation_without_gold_and_three_limit() {
    let mut s = GameState::new(2, 9).unwrap();
    tokens(&mut s, 1, [0, 0, 0, 0, 0, 5]);
    for t in 0..3 {
        s.apply_action(Action::ReserveDeck(t)).unwrap();
        // Complete the opponent's turn rather than changing the active seat.
        s.apply_action(Action::ReserveDeck(t)).unwrap();
    }
    assert_eq!(s.current_player(), 0);
    assert_eq!(s.players[0].tokens[GOLD], 0);
    reject(&mut s, Action::ReserveDeck(0));
    reject(&mut s, Action::ReserveVisible(0));
    s.check_invariants().unwrap();
}
#[test]
fn token_returns_allow_old_new_and_gold_tokens() {
    let mut s = GameState::new(2, 9).unwrap();
    tokens(&mut s, 0, [2, 2, 2, 2, 1, 1]);
    s.apply_action(Action::Take([1, 1, 1, 0, 0])).unwrap();
    assert_eq!(s.phase, Phase::Return);
    assert_eq!(s.current, 0);
    assert_eq!(s.turns, 0);
    s.check_invariants().unwrap();
    for a in actions(&s) {
        let mut t = s.clone();
        t.apply_action(a).unwrap();
        assert_eq!(t.players[0].token_count(), 10);
        t.check_invariants().unwrap();
    }
    reject(&mut s, Action::Return([0; 6]));
    reject(&mut s, Action::Return([4, 0, 0, 0, 0, 0]));
    s.apply_action(Action::Return([1, 0, 0, 1, 0, 1])).unwrap();
    assert_eq!(s.current, 1);
    assert_eq!(s.players[0].token_count(), 10);
    s.check_invariants().unwrap();
}
#[test]
fn reserve_at_ten_can_return_the_new_gold() {
    let mut s = GameState::new(2, 9).unwrap();
    tokens(&mut s, 0, [2, 2, 2, 2, 2, 0]);
    s.apply_action(Action::ReserveDeck(2)).unwrap();
    assert_eq!(s.phase, Phase::Return);
    s.apply_action(Action::Return([0, 0, 0, 0, 0, 1])).unwrap();
    assert_eq!(s.bank[GOLD], 5);
    s.check_invariants().unwrap();
}
#[test]
fn buy_payments_include_optional_gold_and_exact_cost() {
    let mut s = GameState::new(2, 9).unwrap();
    s.market[0] = 0;
    s.players[0].tokens = [1, 1, 1, 1, 0, 2];
    s.apply_action(Action::BuyVisible(0)).unwrap();
    let a = actions(&s);
    assert!(a.contains(&Action::Pay([1, 1, 1, 1, 0])));
    assert!(a.contains(&Action::Pay([0, 1, 1, 1, 0])));
    assert!(a.contains(&Action::Pay([0, 0, 1, 1, 0])));
    reject(&mut s, Action::Pay([0; 5]));
    reject(&mut s, Action::Pay([2, 1, 1, 1, 0]));
    s.apply_action(Action::Pay([0, 1, 1, 1, 0])).unwrap();
    assert_eq!(s.players[0].tokens, [1, 0, 0, 0, 0, 1]);
    assert_eq!(s.players[0].bonuses[4], 1);
}
#[test]
fn discounts_and_free_purchase() {
    let mut s = GameState::new(2, 9).unwrap();
    s.market[0] = 0;
    s.players[0].bonuses = [2, 2, 2, 2, 0];
    s.apply_action(Action::BuyVisible(0)).unwrap();
    assert_eq!(actions(&s).as_slice(), &[Action::Pay([0; 5])]);
    s.apply_action(Action::Pay([0; 5])).unwrap();
    assert_eq!(s.players[0].tokens, [0; 6]);
    assert_eq!(s.players[0].bonuses, [2, 2, 2, 2, 1]);
}
#[test]
fn buying_reserved_compacts_slots() {
    let mut s = GameState::new(2, 9).unwrap();
    for _ in 0..3 {
        s.current = 0;
        s.apply_action(Action::ReserveDeck(0)).unwrap();
    }
    s.current = 0;
    s.players[0].bonuses = [7; 5];
    let c = s.players[0].reserved[1].card;
    let last = s.players[0].reserved[2];
    s.apply_action(Action::BuyReserved(1)).unwrap();
    s.apply_action(Action::Pay([0; 5])).unwrap();
    assert_eq!(s.players[0].reserve_count(), 2);
    assert_eq!(s.players[0].reserved[1], last);
    assert_ne!(s.players[0].owned & (1u128 << c), 0);
}
#[test]
fn depleted_decks_leave_empty_slots() {
    let mut s = GameState::new(2, 9).unwrap();
    for c in 0..40 {
        if !s.market.contains(&c) {
            own(&mut s, 1, c);
        }
    }
    assert_eq!(s.remaining[0], 0);
    reject(&mut s, Action::ReserveDeck(0));
    s.apply_action(Action::ReserveVisible(0)).unwrap();
    assert_eq!(s.market[0], NONE);
    reject(&mut s, Action::BuyVisible(0));
    reject(&mut s, Action::ReserveVisible(0));
    s.check_invariants().unwrap();
}
#[test]
fn noble_is_mandatory_and_uses_bonuses_not_tokens() {
    let mut s = GameState::new(2, 9).unwrap();
    s.nobles = 1;
    tokens(&mut s, 0, [4, 4, 0, 0, 0, 0]);
    assert_eq!(s.eligible(), 0);
    s.players[0].bonuses = [4, 4, 0, 0, 0];
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    assert_eq!(s.players[0].nobles, 1);
    assert_eq!(s.players[0].score, 3);
    assert_eq!(s.nobles, 0);
}
#[test]
fn choose_exactly_one_noble_then_next_turn_can_claim_another() {
    let mut s = GameState::new(2, 9).unwrap();
    s.nobles = 3;
    s.players[0].bonuses = [4, 4, 4, 0, 0];
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    assert_eq!(s.phase, Phase::Noble);
    assert_eq!(actions(&s).len(), 2);
    reject(&mut s, Action::Noble(9));
    s.apply_action(Action::Noble(1)).unwrap();
    assert_eq!(s.players[0].score, 3);
    assert_eq!(s.nobles, 1);
    s.current = 0;
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    assert_eq!(s.players[0].score, 6);
}
#[test]
fn final_round_waits_for_returns_and_noble_choice() {
    let mut s = GameState::new(3, 9).unwrap();
    s.players[0].score = 15;
    tokens(&mut s, 0, [2, 2, 2, 2, 2, 0]);
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    assert!(!s.final_round);
    s.apply_action(Action::Return([0, 0, 0, 0, 0, 1])).unwrap();
    assert!(s.final_round);
    assert!(!s.is_terminal());
    for _ in 0..2 {
        s.apply_action(Action::ReserveDeck(0)).unwrap();
    }
    assert!(s.is_terminal());
    assert_eq!(s.turns, 3);
    assert!(actions(&s).is_empty());
    reject(&mut s, Action::ReserveDeck(0));
}
#[test]
fn noble_can_trigger_end_and_last_seat_ends_immediately() {
    let mut s = GameState::new(4, 9).unwrap();
    s.current = 3;
    s.nobles = 3;
    s.players[3].bonuses = [4, 4, 4, 0, 0];
    s.players[3].score = 12;
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    assert_eq!(s.phase, Phase::Noble);
    s.apply_action(Action::Noble(0)).unwrap();
    assert!(s.is_terminal());
    assert_eq!(s.outcome().unwrap().winners, 8);
}
#[test]
fn tie_break_uses_fewest_owned_cards_then_shared_win() {
    let mut s = GameState::new(4, 9).unwrap();
    s.phase = Phase::Terminal;
    s.final_round = true;
    for p in &mut s.players {
        p.score = 15;
        p.owned = 7;
    }
    s.players[0].owned = 3;
    s.players[2].owned = 3;
    s.players[3].score = 14;
    let o = s.outcome().unwrap();
    assert_eq!(o.winners, 5);
    assert_eq!(o.ranks, [1, 3, 1, 4]);
    s.players[1].score = 16;
    assert_eq!(s.outcome().unwrap().winners, 2);
}
#[test]
fn private_information_is_redacted_and_determinization_preserves_observation() {
    let mut s = GameState::new(2, 8).unwrap();
    s.apply_action(Action::ReserveDeck(1)).unwrap();
    s.apply_action(Action::ReserveVisible(0)).unwrap();
    let o = s.observe(1);
    assert_eq!(o.players[0].reserved[0].card, NONE);
    assert_eq!(o.reserved_counts[0], 1);
    assert_ne!(s.observe(0).players[0].reserved[0].card, NONE);
    assert_ne!(s.observe(0).players[1].reserved[0].card, NONE);
    for seed in 0..100 {
        let d = o.determinize(&mut Rng::new(seed)).unwrap();
        assert_eq!(d.observe(1), o);
        d.check_invariants().unwrap();
    }
}
#[test]
fn observations_independent_of_hidden_permutations() {
    let mut s = GameState::new(2, 8).unwrap();
    s.apply_action(Action::ReserveDeck(0)).unwrap();
    let before = s.observe(1);
    s.decks[0].swap(0, 1);
    std::mem::swap(&mut s.players[0].reserved[0].card, &mut s.decks[0][2]);
    assert_eq!(s.observe(1), before);
    s.check_invariants().unwrap();
}
#[test]
fn malformed_indices_do_not_panic_or_mutate() {
    let mut s = GameState::new(2, 8).unwrap();
    for a in [
        Action::BuyVisible(255),
        Action::BuyReserved(255),
        Action::ReserveVisible(255),
        Action::ReserveDeck(255),
        Action::Noble(255),
        Action::Pay([255; 5]),
        Action::Return([255; 6]),
    ] {
        reject(&mut s, a);
    }
}
#[test]
fn payment_capacity_bound() {
    let mut out = ActionSet::new();
    payments(0, [5; 5], &[5; 6], 5, [0; 5], &mut out);
    assert_eq!(out.len(), 252);
    let mut fast = ActionSet::new();
    fast_actions::enumerate_payments([5; 5], &[5; 6], 5, &mut fast);
    assert_eq!(fast, out);
}
#[test]
fn replay_deterministic_every_decision() {
    for n in 2..=4 {
        let mut a = GameState::new(n, 42).unwrap();
        let mut b = a.clone();
        let mut rng = Rng::new(8);
        for _ in 0..2000 {
            let aa = actions(&a);
            assert_eq!(aa, actions(&b));
            if aa.is_empty() {
                break;
            }
            let action = aa[rng.index(aa.len())];
            a.apply_action(action).unwrap();
            b.apply_action(action).unwrap();
            assert_eq!(a, b);
        }
        assert!(a.is_terminal());
    }
}
proptest! {
    #![proptest_config(ProptestConfig::with_cases(128))]
    #[test] fn all_generated_actions_preserve_invariants(seed in any::<u64>(), n in 2u8..=4, steps in 5usize..150) {
        let mut s=GameState::new(n,seed).unwrap();let mut rng=Rng::new(seed^123);
        for step in 0..steps {s.check_invariants().unwrap();let aa=actions(&s);if aa.is_empty(){break;}for &a in &aa {let mut t=s.clone();prop_assert!(t.apply_action(a).is_ok(),"seed={seed}, step={step}, a={a:?}");prop_assert!(t.check_invariants().is_ok(),"seed={seed}, step={step}, a={a:?}, state={t:?}");}
            s.apply_action(aa[rng.index(aa.len())]).unwrap();let o=s.observe(s.current_player());let d=o.determinize(&mut rng).unwrap();prop_assert_eq!(d.observe(d.current_player()),o);
        }
    }
}
#[test]
fn ten_thousand_random_games() {
    let mut finished = 0;
    let mut blocked = 0;
    for seed in 0..10_000 {
        let mut s = GameState::new(2 + (seed % 3) as u8, seed).unwrap();
        let mut rng = Rng::new(seed ^ 0xabc);
        let mut aa = ActionSet::new();
        for step in 0..20_000 {
            s.check_invariants()
                .unwrap_or_else(|e| panic!("seed={seed} step={step}: {e}, {s:?}"));
            s.legal_actions(&mut aa);
            if aa.is_empty() {
                break;
            }
            s.apply_action(aa[rng.index(aa.len())]).unwrap();
        }
        if s.is_terminal() {
            finished += 1;
        } else {
            assert_eq!(s.phase(), Phase::Main);
            assert!(
                actions(&s).is_empty(),
                "seed={seed} exceeded decision limit"
            );
            assert_eq!(s.bank[..5], [0; 5]);
            assert_eq!(s.players[s.current_player()].reserve_count(), 3);
            blocked += 1;
        }
    }
    eprintln!("random audit: {finished} completed, {blocked} blocked by published rules");
    assert!(finished > 5000);
}

#[test]
fn payment_generator_matches_independent_cartesian_reference() {
    // Enumerate all colored payments independently of the production wild-token recursion.
    let mut rng = Rng::new(71);
    for _ in 0..500 {
        let cost = std::array::from_fn(|_| rng.index(5) as u8);
        let tokens = std::array::from_fn(|_| rng.index(6) as u8);
        let mut generated = ActionSet::new();
        payments(0, cost, &tokens, tokens[5], [0; 5], &mut generated);
        let mut fast = ActionSet::new();
        fast_actions::enumerate_payments(cost, &tokens, tokens[5], &mut fast);
        assert_eq!(fast, generated);
        let mut expected = std::collections::HashSet::new();
        for code in 0..3125 {
            let mut code = code;
            let pay = std::array::from_fn(|_| {
                let v = (code % 5) as u8;
                code /= 5;
                v
            });
            if (0..5).all(|i| pay[i] <= cost[i] && pay[i] <= tokens[i])
                && (0..5).map(|i| cost[i] - pay[i]).sum::<u8>() <= tokens[5]
            {
                expected.insert(Action::Pay(pay));
            }
        }
        let actual: std::collections::HashSet<_> = generated.iter().copied().collect();
        assert_eq!(actual.len(), generated.len());
        assert_eq!(actual, expected);
    }
}
#[test]
fn return_generator_matches_independent_cartesian_reference() {
    let mut rng = Rng::new(73);
    for _ in 0..200 {
        let tokens = std::array::from_fn(|_| rng.index(6) as u8);
        let left = 1 + rng.index(3) as u8;
        let mut generated = ActionSet::new();
        returns(0, left, &tokens, [0; 6], &mut generated);
        let mut expected = std::collections::HashSet::new();
        for code in 0..4096 {
            let mut code = code;
            let ret = std::array::from_fn(|_| {
                let v = (code % 4) as u8;
                code /= 4;
                v
            });
            if ret.iter().sum::<u8>() == left && (0..6).all(|i| ret[i] <= tokens[i]) {
                expected.insert(Action::Return(ret));
            }
        }
        let actual: std::collections::HashSet<_> = generated.iter().copied().collect();
        assert_eq!(actual.len(), generated.len());
        assert_eq!(actual, expected);
    }
}
#[test]
fn invalid_observations_are_rejected_without_panics() {
    let original = GameState::new(2, 9).unwrap().observe(0);
    let mut variants = Vec::new();
    let mut o = original.clone();
    o.market[0] = 254;
    variants.push(o);
    let mut o = original.clone();
    o.players[0].tokens = [255; 6];
    variants.push(o);
    let mut o = original.clone();
    o.players[0].owned = 1u128 << 100;
    variants.push(o);
    let mut o = original.clone();
    o.reserved_counts[0] = 4;
    variants.push(o);
    let mut o = original.clone();
    o.current = 4;
    variants.push(o);
    let mut o = original.clone();
    o.remaining[0] = 255;
    variants.push(o);
    let mut o = original.clone();
    o.market[1] = o.market[0];
    variants.push(o);
    for o in variants {
        assert!(o.determinize(&mut Rng::new(8)).is_err());
    }
}
#[test]
fn official_noble_dataset_exact() {
    let expected = [
        [0, 0, 4, 4, 0],
        [0, 4, 4, 0, 0],
        [4, 4, 0, 0, 0],
        [4, 0, 0, 0, 4],
        [0, 0, 0, 4, 4],
        [0, 3, 3, 3, 0],
        [3, 3, 3, 0, 0],
        [3, 3, 0, 0, 3],
        [3, 0, 0, 3, 3],
        [0, 0, 3, 3, 3],
    ];
    for req in expected {
        assert!(NOBLES.contains(&req));
    }
}
#[test]
fn taking_tokens_can_repeat_forever_under_official_rules() {
    // Termination cannot be a universal property of all legal policies.
    let mut s = GameState::new(2, 9).unwrap();
    tokens(&mut s, 0, [2, 2, 2, 2, 2, 0]);
    tokens(&mut s, 1, [1, 1, 1, 1, 1, 5]);
    for _ in 0..20 {
        let who = s.current;
        let before = s.players[who as usize].tokens;
        s.apply_action(Action::Take([1, 1, 1, 0, 0])).unwrap();
        s.apply_action(Action::Return([1, 1, 1, 0, 0, 0])).unwrap();
        assert_eq!(s.players[who as usize].tokens, before);
        assert!(!s.is_terminal());
        s.check_invariants().unwrap();
    }
}
#[test]
fn noble_csv_matches_runtime_data() {
    for (i, line) in include_str!("../../../data/nobles.csv")
        .lines()
        .skip(1)
        .enumerate()
    {
        let cells: Vec<u8> = line.split(',').map(|x| x.parse().unwrap()).collect();
        assert_eq!(cells[0] as usize, i);
        assert_eq!(cells[1], 3);
        assert_eq!(&cells[2..], &NOBLES[i]);
    }
}

#[test]
fn determinization_rejects_disclosed_opponent_blind_reservation() {
    let mut s = GameState::new(2, 8).unwrap();
    s.apply_action(Action::ReserveDeck(1)).unwrap();
    let mut o = s.observe(1);
    o.players[0].reserved[0].card = s.observe(0).players[0].reserved[0].card;
    // A claimed opponent observation cannot contain this private identity.
    assert!(o.determinize(&mut Rng::new(8)).is_err());
}

#[test]
fn determinization_rejects_phantom_reservation_count() {
    let s = GameState::new(2, 8).unwrap();
    let mut o = s.observe(0);
    // Inactive seats have no reservations, even when empty slot data look valid.
    o.reserved_counts[3] = 1;
    assert!(o.determinize(&mut Rng::new(8)).is_err());
}

#[test]
fn determinization_rejects_unlisted_reservation() {
    let mut s = GameState::new(2, 8).unwrap();
    s.apply_action(Action::ReserveVisible(0)).unwrap();
    let mut o = s.observe(0);
    o.reserved_counts[0] = 0;
    assert!(o.determinize(&mut Rng::new(8)).is_err());
}

#[test]
fn determinization_rejects_final_round_without_threshold_score() {
    for phase in [Phase::Main, Phase::Terminal] {
        let mut o = GameState::new(2, 8).unwrap().observe(0);
        o.final_round = true;
        o.phase = phase;
        assert!(o.determinize(&mut Rng::new(8)).is_err(), "{phase:?}");
    }
}

#[test]
fn determinization_rejects_market_gap_with_nonempty_deck() {
    let mut o = GameState::new(2, 8).unwrap().observe(0);
    // Put a visible card back into the unknown pool: the partition is complete,
    // but a nonempty deck must have refilled the market immediately.
    o.market[0] = NONE;
    o.remaining[0] += 1;
    assert!(o.determinize(&mut Rng::new(8)).is_err());
}

#[test]
fn determinization_rejects_seat_turn_mismatch() {
    let mut o = GameState::new(3, 8).unwrap().observe(0);
    o.turns = 1;
    assert!(o.determinize(&mut Rng::new(8)).is_err());
}

#[test]
fn counter_capacity_is_atomic_for_all_generated_actions() {
    let mut seen = [false; 4];
    let mut rng = Rng::new(110000100);
    for seed in 0..1000 {
        let mut state = GameState::new(2 + (seed % 3) as u8, seed).unwrap();
        for _ in 0..500 {
            let legal = actions(&state);
            if legal.is_empty() {
                break;
            }
            let index = match state.phase {
                Phase::Main => 0,
                Phase::Payment(_) => 1,
                Phase::Return => 2,
                Phase::Noble => 3,
                Phase::Terminal => unreachable!(),
            };
            if !seen[index] {
                // Exercise each phase's pre-mutation guard independently of seat order.
                let mut boundary = state.clone();
                boundary.turns = u32::MAX;
                for &action in &legal {
                    assert_eq!(boundary.apply_action(action), Err(RuleError::TurnLimit));
                    let mut buffer = ActionSet::new();
                    assert_eq!(
                        boundary.decision(&mut buffer).apply(action),
                        Err(RuleError::TurnLimit)
                    );
                    assert_eq!(boundary.turns, u32::MAX);
                    let mut restored = boundary.clone();
                    restored.turns = state.turns;
                    assert_eq!(restored, state);
                    assert_eq!(boundary.outcome(), None);
                }
                seen[index] = true;
            }
            state.apply_action(legal[rng.index(legal.len())]).unwrap();
            if seen.iter().all(|&s| s) {
                return;
            }
        }
    }
    assert_eq!(seen, [true; 4]);
}

#[test]
fn every_optional_gold_payment_preserves_full_state_invariants() {
    // Card 0 costs one of each non-black color. Start with a real dealt copy,
    // enough colored tokens for full payment, and enough gold for any subset.
    let initial = (0..1000)
        .map(|seed| GameState::new(2, seed).unwrap())
        .find(|s| s.market.contains(&0))
        .unwrap();
    for reserved in [false, true] {
        let mut state = initial.clone();
        let slot = state.market.iter().position(|&id| id == 0).unwrap() as u8;
        let buy = if reserved {
            state.apply_action(Action::ReserveVisible(slot)).unwrap();
            state.apply_action(Action::Take([1, 1, 1, 0, 0])).unwrap();
            Action::BuyReserved(0)
        } else {
            Action::BuyVisible(slot)
        };
        tokens(&mut state, 0, [1, 1, 1, 1, 0, 5]);
        state.check_invariants().unwrap();
        assert!(actions(&state).contains(&buy));
        let before = state.clone();
        state.apply_action(buy).unwrap();
        assert!(matches!(state.phase(), Phase::Payment(_)));
        assert_eq!(state.turns(), before.turns());
        state.check_invariants().unwrap();
        assert_eq!(actions(&state).len(), 16);
        for mask in 0u8..16 {
            let colored: [u8; 5] = std::array::from_fn(|c| if c < 4 { (mask >> c) & 1 } else { 0 });
            let payment = Action::Pay(colored);
            assert!(actions(&state).contains(&payment));
            let mut branch = state.clone();
            branch.apply_action(payment).unwrap();
            branch.check_invariants().unwrap();
            let gold = 4 - mask.count_ones() as u8;
            for (c, &paid) in colored.iter().enumerate() {
                assert_eq!(
                    branch.players[0].tokens[c],
                    before.players[0].tokens[c] - paid
                );
                assert_eq!(branch.bank[c], before.bank[c] + paid);
            }
            assert_eq!(branch.players[0].tokens[GOLD], 5 - gold);
            assert_eq!(branch.bank[GOLD], before.bank[GOLD] + gold);
            assert_eq!(branch.players[0].owned, 1);
            assert_eq!(branch.players[0].bonuses, [0, 0, 0, 0, 1]);
            assert_eq!(branch.players[0].reserve_count(), 0);
            assert_eq!(branch.turns(), before.turns() + 1);
            assert_eq!(branch.current_player(), 1);
            assert_eq!(branch.outcome(), None);
        }
    }
}

#[test]
fn eighth_bonus_of_a_color_is_a_legal_purchase() {
    // The external reference has a seven-card cap; the local rules do not.
    let target = 0u8;
    let mut state = (0..1000)
        .map(|seed| GameState::new(2, seed).unwrap())
        .find(|s| s.market.contains(&target))
        .unwrap();
    let color = CARDS[target as usize].bonus as usize;
    let mut candidates: Vec<_> = CARDS
        .iter()
        .enumerate()
        .filter(|&(id, card)| id != target as usize && card.bonus as usize == color)
        .collect();
    candidates.sort_by_key(|&(id, card)| (card.points, id));
    for &(id, _) in candidates.iter().take(7) {
        own(&mut state, 0, id as u8);
    }
    tokens(&mut state, 0, [0, 0, 0, 0, 0, 5]);
    state.check_invariants().unwrap();
    assert_eq!(state.players[0].bonuses[color], 7);
    let slot = state.market.iter().position(|&id| id == target).unwrap() as u8;
    let buy = Action::BuyVisible(slot);
    assert!(actions(&state).contains(&buy));
    state.apply_action(buy).unwrap();
    state.check_invariants().unwrap();
    state.apply_action(Action::Pay([0; 5])).unwrap();
    state.check_invariants().unwrap();
    assert_eq!(state.players[0].bonuses[color], 8);
    assert_eq!(state.players[0].owned.count_ones(), 8);
    assert_eq!(state.players[0].tokens[GOLD], 1);
}

#[test]
fn fast_enumeration_preserves_every_bank_pattern_and_order() {
    let mut state = GameState::new(2, 424262).unwrap();
    let mut expected = ActionSet::new();
    let mut actual = ActionSet::new();
    for pattern in 0..1024usize {
        let mut digits = pattern;
        for bank in &mut state.bank[..5] {
            *bank = [0, 1, 4, 7][digits % 4];
            digits /= 4;
        }
        state.legal_actions_reference(&mut expected);
        state.legal_actions(&mut actual);
        assert_eq!(actual, expected, "bank pattern {pattern}");
    }
}

#[test]
fn fast_enumeration_preserves_optional_payments_and_gold_returns() {
    let mut state = GameState::new(2, 424262).unwrap();
    let mut expected = ActionSet::new();
    let mut actual = ActionSet::new();
    let mut rng = Rng::new(424263);
    for card in 0..90u8 {
        state.market[0] = card;
        state.phase = Phase::Payment(Source::Market(0));
        for _ in 0..128 {
            let player = &mut state.players[0];
            for color in 0..5 {
                player.tokens[color] = rng.index(5) as u8;
                player.bonuses[color] = rng.index(5) as u8;
            }
            player.tokens[GOLD] = rng.index(6) as u8;
            state.legal_actions_reference(&mut expected);
            state.legal_actions(&mut actual);
            assert_eq!(actual, expected, "payment card {card}");
        }
    }
    state.phase = Phase::Return;
    for pattern in 0..6144usize {
        let mut digits = pattern / 6;
        state.players[0].tokens[GOLD] = (pattern % 6) as u8;
        for token in &mut state.players[0].tokens[..5] {
            *token = (digits % 4) as u8;
            digits /= 4;
        }
        if !(11..=13).contains(&state.players[0].token_count()) {
            continue;
        }
        state.legal_actions_reference(&mut expected);
        state.legal_actions(&mut actual);
        assert_eq!(actual, expected, "return pattern {pattern}");
    }
}

#[test]
fn fast_enumeration_preserves_complete_seeded_games_and_all_choices() {
    let mut phases = [0usize; 5];
    let mut action_types = [0usize; 8];
    for count in 2..=4 {
        for seed in 424262..424294 {
            let mut state = GameState::new(count, seed).unwrap();
            let mut reference = state.clone();
            let mut rng = Rng::new(seed);
            let mut expected = ActionSet::new();
            let mut actual = ActionSet::new();
            for _ in 0..2000 {
                phases[match state.phase {
                    Phase::Main => 0,
                    Phase::Payment(_) => 1,
                    Phase::Return => 2,
                    Phase::Noble => 3,
                    Phase::Terminal => 4,
                }] += 1;
                reference.legal_actions_reference(&mut expected);
                state.legal_actions(&mut actual);
                assert_eq!(actual, expected, "count {count} seed {seed}");
                for &action in &actual {
                    action_types[match action {
                        Action::Take(_) => 0,
                        Action::ReserveVisible(_) => 1,
                        Action::ReserveDeck(_) => 2,
                        Action::BuyVisible(_) => 3,
                        Action::BuyReserved(_) => 4,
                        Action::Pay(_) => 5,
                        Action::Return(_) => 6,
                        Action::Noble(_) => 7,
                    }] += 1;
                    let mut branch = state.clone();
                    branch.apply_action(action).unwrap();
                    branch.check_invariants().unwrap();
                    let mut guarded = state.clone();
                    let mut buffer = ActionSet::new();
                    let expected_observation = guarded.observe(guarded.current_player());
                    let decision = guarded.decision(&mut buffer);
                    assert_eq!(
                        decision.observe(expected_observation.viewer as usize),
                        expected_observation
                    );
                    decision.apply(action).unwrap();
                    assert_eq!(guarded, branch);
                    let mut indexed = state.clone();
                    let index = actual.iter().position(|a| *a == action).unwrap();
                    indexed.decision(&mut buffer).apply_index(index).unwrap();
                    assert_eq!(indexed, branch);
                }
                if actual.is_empty() {
                    break;
                }
                let action = if rng.index(3) != 0 {
                    actual
                        .iter()
                        .find(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                        .copied()
                } else {
                    None
                }
                .unwrap_or(actual[rng.index(actual.len())]);
                state.apply_action(action).unwrap();
                reference.apply_action(action).unwrap();
                assert_eq!(state, reference);
                assert_eq!(state.outcome(), reference.outcome());
                for seat in 0..usize::from(count) {
                    assert_eq!(state.observe(seat), reference.observe(seat));
                }
            }
        }
    }
    assert!(phases.iter().all(|&n| n > 0), "phases {phases:?}");
    assert!(
        action_types.iter().all(|&n| n > 0),
        "action types {action_types:?}"
    );
}

#[test]
fn validated_decisions_reject_invalid_choices_and_capacity_atomically() {
    let mut state = GameState::new(2, 424262).unwrap();
    let before = state.clone();
    let mut buffer = ActionSet::new();
    assert_eq!(
        state.decision(&mut buffer).apply(Action::Pay([0; 5])),
        Err(RuleError::IllegalAction)
    );
    assert_eq!(state, before);
    assert_eq!(
        state.decision(&mut buffer).apply_index(usize::MAX),
        Err(RuleError::IllegalAction)
    );
    assert_eq!(state, before);
    state.turns = u32::MAX;
    let before = state.clone();
    let action = actions(&state)[0];
    assert_eq!(
        state.decision(&mut buffer).apply(action),
        Err(RuleError::TurnLimit)
    );
    assert_eq!(state, before);
    assert_eq!(
        state.decision(&mut buffer).apply_index(0),
        Err(RuleError::TurnLimit)
    );
    assert_eq!(state, before);
    assert_eq!(
        state.decision(&mut buffer).apply(Action::Pay([0; 5])),
        Err(RuleError::IllegalAction)
    );
    assert_eq!(state, before);
}

#[test]
fn fast_noble_masks_match_requirements_at_all_bonus_boundaries() {
    let mut state = GameState::new(2, 109000999).unwrap();
    for pattern in 0..7776usize {
        let mut digits = pattern;
        for bonus in &mut state.players[0].bonuses {
            *bonus = [0, 1, 2, 3, 4, 255][digits % 6];
            digits /= 6;
        }
        for nobles in [0, 1, 3, 15, 0x155, 0x2aa, 0x3ff] {
            state.nobles = nobles;
            let expected = NOBLES.iter().enumerate().fold(0u16, |mask, (n, req)| {
                if nobles & (1 << n) != 0 && (0..5).all(|c| state.players[0].bonuses[c] >= req[c]) {
                    mask | (1 << n)
                } else {
                    mask
                }
            });
            assert_eq!(
                state.eligible(),
                expected,
                "pattern={pattern} nobles={nobles}"
            );
        }
    }
}

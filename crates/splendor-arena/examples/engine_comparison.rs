//! Matched raw-state microbench fixtures for Rust and the pinned AhinLendor C++ engine.
//!
//! Run with `cargo run --release -p splendor-arena --features benchmark-compat
//! --example engine_comparison -- research/ahinlendor/engine/fixtures.txt`.
//! The output contains sampled hidden worlds for raw-engine benchmarking only.
//! Never pass these fixtures to an agent or strength adapter.

use splendor_core::data::{CARDS, NOBLES};
use splendor_core::{Action, ActionSet, GameState, NONE, Observation, Phase, Rng};
use std::fmt::Write as _;
use std::fs::File;
use std::io::Write as _;
use std::time::Instant;

const OPS: usize = 80_000;
const REPEATS: usize = 3;

fn csv(values: impl IntoIterator<Item = impl std::fmt::Display>) -> String {
    values
        .into_iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn digest_feed(hash: &mut u64, value: u64) {
    *hash = (*hash ^ value).wrapping_mul(0x100000001b3);
}

fn material_digest(
    obs: &Observation,
    players: &[splendor_core::Player; 4],
    pools: &[[u8; 40]; 3],
) -> u64 {
    let mut hash = 0xcbf29ce484222325;
    let phase = match obs.phase {
        Phase::Main => 0,
        Phase::Return => 1,
        Phase::Noble => 2,
        Phase::Payment(_) => 3,
        Phase::Terminal => 4,
    };
    for value in [
        obs.count as u64,
        obs.viewer as u64,
        obs.current as u64,
        obs.turns as u64,
        obs.final_round as u64,
        phase,
    ] {
        digest_feed(&mut hash, value);
    }
    for &value in &obs.bank {
        digest_feed(&mut hash, value as u64);
    }
    for &value in &obs.market {
        digest_feed(&mut hash, if value == NONE { 0 } else { value as u64 + 1 });
    }
    for &value in &obs.remaining {
        digest_feed(&mut hash, value as u64);
    }
    let available = (0..10)
        .filter(|&id| obs.nobles & (1 << id) != 0)
        .map(|id| ahin_noble_id(&NOBLES[id]))
        .collect::<Vec<_>>();
    digest_feed(&mut hash, available.len() as u64);
    for id in available {
        digest_feed(&mut hash, id as u64);
    }
    for player in players.iter().take(obs.count as usize) {
        for &value in &player.tokens {
            digest_feed(&mut hash, value as u64);
        }
        for &value in &player.bonuses {
            digest_feed(&mut hash, value as u64);
        }
        digest_feed(&mut hash, player.score as u64);
        let owned = (0..90)
            .filter(|&id| player.owned & (1u128 << id) != 0)
            .map(|id| id + 1)
            .collect::<Vec<_>>();
        digest_feed(&mut hash, owned.len() as u64);
        for id in owned {
            digest_feed(&mut hash, id as u64);
        }
        let nobles = (0..10)
            .filter(|&id| player.nobles & (1 << id) != 0)
            .map(|id| ahin_noble_id(&NOBLES[id]))
            .collect::<Vec<_>>();
        digest_feed(&mut hash, nobles.len() as u64);
        for id in nobles {
            digest_feed(&mut hash, id as u64);
        }
        let reserved = &player.reserved[..player.reserve_count()];
        digest_feed(&mut hash, reserved.len() as u64);
        for card in reserved {
            digest_feed(&mut hash, card.card as u64 + 1);
            digest_feed(&mut hash, card.tier as u64);
            digest_feed(&mut hash, card.public as u64);
        }
    }
    for tier in 0..3 {
        digest_feed(&mut hash, obs.remaining[tier] as u64);
        for &id in &pools[tier][..obs.remaining[tier] as usize] {
            digest_feed(&mut hash, id as u64 + 1);
        }
    }
    hash
}

fn ahin_noble_id(req: &[u8; 5]) -> u8 {
    // Canonical zero-based noble ID to AhinLendor one-based card ID.
    let map = [9u8, 8, 10, 6, 7, 5, 4, 2, 3, 1];
    NOBLES
        .iter()
        .position(|signature| signature == req)
        .map(|canonical_id| map[canonical_id])
        .expect("noble signature exists in AhinLendor data")
}

fn sampled_world(obs: &Observation, seed: u64) -> ([[u8; 40]; 3], [splendor_core::Player; 4]) {
    let mut known = 0u128;
    for &card in &obs.market {
        if card != NONE {
            known |= 1u128 << card;
        }
    }
    for (seat, player) in obs.players.iter().enumerate() {
        let mut owned = player.owned;
        while owned != 0 {
            let id = owned.trailing_zeros() as u8;
            known |= 1u128 << id;
            owned &= owned - 1;
        }
        for (slot, reserved) in player.reserved.iter().enumerate() {
            if slot < obs.reserved_counts[seat] as usize && reserved.card != NONE {
                known |= 1u128 << reserved.card;
            }
        }
    }
    let mut pools = [[NONE; 40]; 3];
    let mut len = [0usize; 3];
    for (id, card) in CARDS.iter().enumerate() {
        if known & (1u128 << id) == 0 {
            let tier = card.tier as usize;
            pools[tier][len[tier]] = id as u8;
            len[tier] += 1;
        }
    }
    let mut rng = Rng::new(seed);
    for tier in 0..3 {
        rng.shuffle(&mut pools[tier][..len[tier]]);
    }
    let mut players = obs.players;
    for (seat, player) in players.iter_mut().enumerate() {
        for reserved in &mut player.reserved[..obs.reserved_counts[seat] as usize] {
            if reserved.card == NONE {
                let tier = reserved.tier as usize;
                len[tier] -= 1;
                reserved.card = pools[tier][len[tier]];
                pools[tier][len[tier]] = NONE;
            }
        }
    }
    (pools, players)
}

fn write_fixture(out: &mut File, tag: &str, obs: &Observation, rng_seed: u64) -> GameState {
    assert_eq!(obs.phase, Phase::Main);
    let (pools, sampled_players) = sampled_world(obs, rng_seed);
    let sampled = obs
        .determinize(&mut Rng::new(rng_seed))
        .expect("determinize");
    assert_eq!(sampled.observe(obs.viewer as usize), *obs);
    let raw = format!("{sampled:?}");
    assert!(
        raw.contains(&format!("decks: {pools:?}")),
        "independent pool reconstruction differs"
    );
    let sampled_observation = sampled.observe(obs.viewer as usize);
    for (seat, mut player) in sampled_players.iter().copied().enumerate() {
        if seat != obs.viewer as usize {
            for reserved in &mut player.reserved {
                if !reserved.public {
                    reserved.card = NONE;
                }
            }
        }
        assert_eq!(player, sampled_observation.players[seat]);
    }
    let nobles = (0..10)
        .filter(|&id| obs.nobles & (1 << id) != 0)
        .map(|id| ahin_noble_id(&NOBLES[id]));
    writeln!(
        out,
        "STATE|{tag}|{}|{}|{}|{}|{}|{}|{}|{}",
        obs.viewer,
        obs.current,
        obs.turns,
        obs.final_round as u8,
        csv(obs.bank),
        csv(obs
            .market
            .iter()
            .map(|&id| if id == NONE { 0 } else { id + 1 })),
        csv(obs.remaining),
        csv(nobles)
    )
    .unwrap();
    writeln!(
        out,
        "DIGEST|{:016x}",
        material_digest(obs, &sampled_players, &pools)
    )
    .unwrap();
    for (seat, player) in sampled_players.iter().enumerate().take(obs.count as usize) {
        let owned = (0..90)
            .filter(|&id| player.owned & (1u128 << id) != 0)
            .map(|id| id + 1);
        let owned = csv(owned);
        let nobles = (0..10)
            .filter(|&id| player.nobles & (1 << id) != 0)
            .map(|id| ahin_noble_id(&NOBLES[id]));
        let mut line = format!(
            "PLAYER|{seat}|{}|{}|{}|{}|{}|{}",
            csv(player.tokens),
            csv(player.bonuses),
            player.score,
            owned,
            csv(nobles),
            obs.reserved_counts[seat]
        );
        for reserved in &player.reserved[..obs.reserved_counts[seat] as usize] {
            write!(
                &mut line,
                "|{}|{}|{}",
                reserved.card + 1,
                reserved.tier,
                reserved.public as u8
            )
            .unwrap();
        }
        writeln!(out, "{line}").unwrap();
    }
    for (tier, pool) in pools.iter().enumerate() {
        let remaining = obs.remaining[tier] as usize;
        let ids = pool[..remaining].iter().map(|id| id + 1);
        writeln!(out, "DECK|{tier}|{}", csv(ids)).unwrap();
        if remaining > 0 {
            let expected_next = pool[remaining - 1];
            if tag == "start" {
                let mut probe = sampled.clone();
                probe
                    .apply_action(Action::ReserveDeck(tier as u8))
                    .expect("reserve probe is legal");
                assert_eq!(
                    probe.observe(obs.viewer as usize).players[obs.current as usize].reserved[0]
                        .card,
                    expected_next
                );
            }
            writeln!(out, "NEXT|{tier}|{}", expected_next + 1).unwrap();
        }
    }
    let mut legal = ActionSet::new();
    sampled.legal_actions(&mut legal);
    for action in &legal {
        let Action::BuyVisible(slot) = action else {
            continue;
        };
        let card_id = obs.market[*slot as usize];
        let card = CARDS[card_id as usize];
        let player = &obs.players[obs.current as usize];
        let mut pay = [0; 5];
        let mut gold = 0u8;
        for (color, amount) in pay.iter_mut().enumerate() {
            let due = card.cost[color].saturating_sub(player.bonuses[color]);
            *amount = due.min(player.tokens[color]);
            gold += due - *amount;
        }
        if gold > player.tokens[5] {
            continue;
        }
        let expected_refill = if obs.remaining[card.tier as usize] == 0 {
            NONE
        } else {
            pools[card.tier as usize][obs.remaining[card.tier as usize] as usize - 1]
        };
        let mut probe = sampled.clone();
        probe
            .apply_action(*action)
            .expect("selected buy action is legal");
        let mut payment_actions = ActionSet::new();
        probe.legal_actions(&mut payment_actions);
        if !payment_actions.contains(&Action::Pay(pay)) {
            continue;
        }
        probe
            .apply_action(Action::Pay(pay))
            .expect("colored-first payment is legal");
        assert_eq!(
            probe.observe(obs.viewer as usize).market[*slot as usize],
            expected_refill
        );
        writeln!(out, "REFILL|{}|{}", slot, expected_refill + 1).unwrap();
        break;
    }
    let take = find_take(&sampled);
    writeln!(out, "ACTION|{}", csv(take)).unwrap();
    let mut after = sampled.clone();
    after
        .apply_action(Action::Take(take))
        .expect("paired TAKE applies");
    let after_obs = after.observe(obs.viewer as usize);
    let mut after_players = after_obs.players;
    for (seat, player) in after_players.iter_mut().enumerate() {
        if seat == obs.viewer as usize {
            continue;
        }
        for (slot, reserved) in player.reserved.iter_mut().enumerate() {
            if slot < after_obs.reserved_counts[seat] as usize && !reserved.public {
                reserved.card = sampled_players[seat].reserved[slot].card;
            }
        }
    }
    writeln!(
        out,
        "AFTER_TAKE|{:016x}",
        material_digest(&after_obs, &after_players, &pools)
    )
    .unwrap();
    writeln!(out, "END").unwrap();
    sampled
}

fn find_take(state: &GameState) -> [u8; 5] {
    let mut legal = ActionSet::new();
    state.legal_actions(&mut legal);
    legal
        .into_iter()
        .find_map(|a| match a {
            Action::Take(t) => Some(t),
            _ => None,
        })
        .expect("fixture must have a legal TAKE action")
}

fn observation_checksum(obs: &Observation) -> u64 {
    let mut sum = obs.viewer as u64 + ((obs.current as u64) << 8) + ((obs.turns as u64) << 16);
    for &x in obs
        .bank
        .iter()
        .chain(obs.market.iter())
        .chain(obs.remaining.iter())
    {
        sum = sum.wrapping_mul(257).wrapping_add(x as u64);
    }
    sum = sum.wrapping_add(obs.nobles as u64);
    for p in &obs.players {
        for &x in p.tokens.iter().chain(p.bonuses.iter()) {
            sum = sum.wrapping_mul(257).wrapping_add(x as u64);
        }
        sum = sum
            .wrapping_add(p.owned as u64)
            .wrapping_add((p.owned >> 64) as u64);
        sum = sum
            .wrapping_add(p.nobles as u64)
            .wrapping_add(p.score as u64);
        for r in &p.reserved {
            sum = sum
                .wrapping_mul(257)
                .wrapping_add(r.card as u64 + 1)
                .wrapping_add((r.tier as u64) << 8)
                .wrapping_add((r.public as u64) << 16);
        }
    }
    sum
}

fn trajectory_action(state: &GameState, legal: &ActionSet, rng: &mut Rng) -> Action {
    match state.phase() {
        Phase::Main => {
            if let Some(&buy) = legal.iter().find(|a| matches!(a, Action::BuyVisible(_))) {
                return buy;
            }
            let takes = legal
                .iter()
                .filter(|a| matches!(a, Action::Take(_)))
                .copied()
                .collect::<Vec<_>>();
            if !takes.is_empty() {
                let viewer = state.current_player();
                let obs = state.observe(viewer);
                let player = &obs.players[viewer];
                let target = obs
                    .market
                    .iter()
                    .copied()
                    .filter(|&id| id != NONE)
                    .min_by_key(|&id| {
                        let card = CARDS[id as usize];
                        card.cost
                            .iter()
                            .enumerate()
                            .map(|(i, &c)| c.saturating_sub(player.bonuses[i]) as u16)
                            .sum::<u16>()
                    })
                    .expect("market has a target");
                let card = CARDS[target as usize];
                let scores = takes
                    .iter()
                    .map(|a| {
                        let Action::Take(tokens) = a else {
                            unreachable!()
                        };
                        let covered = (0..5)
                            .map(|i| {
                                (player.tokens[i] + tokens[i] + player.bonuses[i]).min(card.cost[i])
                                    as u16
                            })
                            .sum::<u16>();
                        (covered, *a)
                    })
                    .collect::<Vec<_>>();
                let best = scores.iter().map(|x| x.0).max().unwrap();
                let choices = scores
                    .iter()
                    .filter(|x| x.0 == best)
                    .map(|x| x.1)
                    .collect::<Vec<_>>();
                return choices[rng.index(choices.len())];
            }
            *legal.first().expect("main action exists")
        }
        Phase::Payment(_) => legal
            .iter()
            .copied()
            .max_by_key(|a| match a {
                Action::Pay(colors) => colors.iter().map(|&x| x as u16).sum::<u16>(),
                _ => 0,
            })
            .expect("payment exists"),
        Phase::Return => legal
            .iter()
            .copied()
            .min_by_key(|a| match a {
                Action::Return(tokens) => tokens[5],
                _ => u8::MAX,
            })
            .expect("return exists"),
        Phase::Noble => *legal.first().expect("noble choice exists"),
        Phase::Terminal => unreachable!("terminal state has no trajectory action"),
    }
}

fn bench<T>(state: &str, label: &str, ops: usize, mut f: impl FnMut() -> T) {
    for repeat in 0..REPEATS {
        let start = Instant::now();
        for _ in 0..ops {
            std::hint::black_box(f());
        }
        let seconds = start.elapsed().as_secs_f64();
        println!(
            "rust,{state},{label},{repeat},{ops},{seconds:.6},{:.0}",
            ops as f64 / seconds
        );
    }
}

fn main() {
    let path = std::env::args().nth(1).expect("fixture output path");
    let mut file = File::create(path).expect("create fixture file");
    writeln!(
        file,
        "# raw-engine-only synthetic determinized worlds; never agent input"
    )
    .unwrap();
    for (id, card) in CARDS.iter().enumerate() {
        writeln!(
            file,
            "CARD|{}|{}|{}|{}|{}",
            id + 1,
            card.tier + 1,
            card.bonus,
            card.points,
            csv(card.cost)
        )
        .unwrap();
    }
    for (id, req) in NOBLES.iter().enumerate() {
        writeln!(file, "NOBLE|{id}|{}|{}", ahin_noble_id(req), csv(req)).unwrap();
    }

    let mut state = GameState::new(2, 0x4148_494e_4c45_4e44).unwrap();
    let mut trajectory_rng = Rng::new(0x5354_4154_4553);
    let mut tags = [false; 3];
    let mut refill_captured = false;
    let mut samples = Vec::new();
    let milestones = [(0usize, "start"), (8, "mid"), (20, "late")];
    let mut operations = 0usize;
    loop {
        let turns = state.turns() as usize;
        for (i, (target, tag)) in milestones.iter().enumerate() {
            if !tags[i] && turns >= *target && state.phase() == Phase::Main {
                let obs = state.observe(state.current_player());
                let sampled = write_fixture(&mut file, tag, &obs, 0x4445_5445_524d_0000 + i as u64);
                samples.push((tag.to_string(), sampled));
                tags[i] = true;
            }
        }
        if (tags.iter().all(|&v| v) && refill_captured)
            || state.is_terminal()
            || operations >= 10_000
        {
            break;
        }
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        if legal.is_empty() {
            break;
        }
        if !refill_captured
            && state.phase() == Phase::Main
            && legal.iter().any(|a| matches!(a, Action::BuyVisible(_)))
        {
            let obs = state.observe(state.current_player());
            let sampled = write_fixture(&mut file, "refill", &obs, 0x4445_5445_524d_1000);
            samples.push(("refill".to_string(), sampled));
            refill_captured = true;
        }
        let action = trajectory_action(&state, &legal, &mut trajectory_rng);
        state
            .apply_action(action)
            .expect("generated action is legal");
        operations += 1;
    }
    assert!(
        tags[0] && tags[1],
        "trajectory did not reach start and mid snapshots"
    );
    if !tags[2] {
        panic!(
            "trajectory did not reach late snapshot before game end: turns={}",
            state.turns()
        );
    }
    assert!(
        refill_captured,
        "trajectory did not reach a visible buy for refill parity"
    );
    file.flush().unwrap();
    eprintln!("wrote four paired snapshots after {operations} source actions");

    println!("engine,state,case,repeat,operations,seconds,ops_per_second");
    for (tag, det) in samples {
        let take = find_take(&det);
        let mut legal = ActionSet::new();
        det.legal_actions(&mut legal);
        println!(
            "# rust state={tag} legal_actions={} take_actions={} paired_take={take:?}",
            legal.len(),
            legal
                .iter()
                .filter(|a| matches!(a, Action::Take(_)))
                .count()
        );
        bench(&tag, "clone", OPS, || (*std::hint::black_box(&det)).clone());
        bench(&tag, "legal_actions", OPS / 4, || {
            let mut actions = ActionSet::new();
            std::hint::black_box(&det).legal_actions(&mut actions);
            std::hint::black_box(actions)
        });
        bench(&tag, "terminal", OPS, || {
            std::hint::black_box(&det).is_terminal()
        });
        bench(&tag, "observation", OPS / 4, || {
            let obs = std::hint::black_box(&det).observe(0);
            std::hint::black_box(observation_checksum(&obs));
            obs
        });
        let batch = 512;
        let mut states = (0..batch).map(|_| det.clone()).collect::<Vec<_>>();
        for repeat in 0..REPEATS {
            let mut apply_seconds = 0.0;
            for _ in 0..batch {
                for s in &mut states {
                    *s = det.clone();
                }
                let start = Instant::now();
                for s in &mut states {
                    s.apply_action(Action::Take(take)).unwrap();
                    std::hint::black_box(s);
                }
                apply_seconds += start.elapsed().as_secs_f64();
            }
            println!(
                "rust,{tag},apply_take,{repeat},{},{apply_seconds:.6},{:.0}",
                batch * batch,
                (batch * batch) as f64 / apply_seconds
            );
        }
        bench(&tag, "clone_apply_take", OPS / 4, || {
            let mut s = (*std::hint::black_box(&det)).clone();
            s.apply_action(Action::Take(take)).unwrap();
            s
        });
        bench(&tag, "tree_expand_take", OPS / 8, || {
            let mut s = (*std::hint::black_box(&det)).clone();
            let mut actions = ActionSet::new();
            s.legal_actions(&mut actions);
            std::hint::black_box(actions);
            s.apply_action(Action::Take(take)).unwrap();
            s
        });
    }
}

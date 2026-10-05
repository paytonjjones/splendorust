//! Emit a deterministic, raw-engine full-turn trajectory for Rust/C++ replay.
//!
//! The file contains private sampled setup information for engine benchmarking
//! only. Never pass it to an agent or strength adapter.
use splendor_core::data::CARDS;
use splendor_core::{Action, ActionSet, GOLD, GameState, Observation, Phase, Rng};
use std::fmt::Write as _;
use std::fs::File;
use std::hint::black_box;
use std::io::{BufWriter, Write};
use std::time::Instant;

#[derive(Clone)]
struct CachedStep {
    before: GameState,
    action: Action,
    after: GameState,
    legal: ActionSet,
    observations_after: Vec<Observation>,
}

fn csv(values: impl IntoIterator<Item = impl std::fmt::Display>) -> String {
    values
        .into_iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn ahin_noble_id(canonical_id: usize) -> u8 {
    [9u8, 8, 10, 6, 7, 5, 4, 2, 3, 1][canonical_id]
}

fn phase_code(phase: Phase) -> u64 {
    match phase {
        Phase::Main => 0,
        Phase::Return => 1,
        Phase::Noble => 2,
        Phase::Payment(_) => 3,
        Phase::Terminal => 4,
    }
}

fn feed(hash: &mut u64, value: u64) {
    *hash = (*hash ^ value).wrapping_mul(0x100000001b3);
}

#[derive(Clone)]
struct Shadow {
    decks: [Vec<u8>; 3], // one-based IDs, stack top at back; exact Ahin order
    reserves: [Vec<(u8, u8, bool)>; 2], // ID, tier, public
}

impl Shadow {
    fn new(draw_order: &[Vec<u8>; 3]) -> Self {
        Self {
            decks: std::array::from_fn(|tier| {
                draw_order[tier][4..]
                    .iter()
                    .rev()
                    .map(|&id| id + 1)
                    .collect()
            }),
            reserves: [Vec::new(), Vec::new()],
        }
    }

    fn apply(&mut self, action: Action, actor: usize, obs: &Observation) {
        match action {
            Action::ReserveVisible(slot) => {
                let card = obs.market[slot as usize];
                let tier = CARDS[card as usize].tier as usize;
                self.decks[tier].pop(); // the next Observation carries the market.
                self.reserves[actor].push((card + 1, tier as u8, true));
            }
            Action::ReserveDeck(tier) => {
                let card = self.decks[tier as usize]
                    .pop()
                    .expect("legal reserve has a card");
                self.reserves[actor].push((card, tier, false));
            }
            Action::BuyVisible(slot) => {
                let card = obs.market[slot as usize];
                let tier = CARDS[card as usize].tier as usize;
                self.decks[tier].pop();
            }
            Action::BuyReserved(slot) => {
                self.reserves[actor].remove(slot as usize);
            }
            _ => {}
        }
    }

    fn digest(&self, obs: &Observation) -> u64 {
        let mut hash = 0xcbf29ce484222325;
        feed(&mut hash, obs.count as u64);
        feed(&mut hash, obs.current as u64);
        feed(&mut hash, obs.turns as u64);
        feed(
            &mut hash,
            obs.players[..obs.count as usize]
                .iter()
                .any(|p| p.score >= 15) as u64,
        );
        feed(&mut hash, phase_code(obs.phase));
        for &value in &obs.bank {
            feed(&mut hash, value as u64);
        }
        for &id in &obs.market {
            feed(&mut hash, if id == u8::MAX { 0 } else { id as u64 + 1 });
        }
        for tier in 0..3 {
            feed(&mut hash, self.decks[tier].len() as u64);
        }
        let mut available = (0..10)
            .filter(|&id| obs.nobles & (1 << id) != 0)
            .map(ahin_noble_id)
            .collect::<Vec<_>>();
        available.sort_unstable();
        feed(&mut hash, available.len() as u64);
        for id in available {
            feed(&mut hash, id as u64);
        }
        for seat in 0..obs.count as usize {
            let player = &obs.players[seat];
            for &value in &player.tokens {
                feed(&mut hash, value as u64);
            }
            for &value in &player.bonuses {
                feed(&mut hash, value as u64);
            }
            feed(&mut hash, player.score as u64);
            let owned = (0..90)
                .filter(|&id| player.owned & (1u128 << id) != 0)
                .map(|id| id + 1)
                .collect::<Vec<_>>();
            feed(&mut hash, owned.len() as u64);
            for id in owned {
                feed(&mut hash, id as u64);
            }
            let mut claimed = (0..10)
                .filter(|&id| player.nobles & (1 << id) != 0)
                .map(ahin_noble_id)
                .collect::<Vec<_>>();
            claimed.sort_unstable();
            feed(&mut hash, claimed.len() as u64);
            for id in claimed {
                feed(&mut hash, id as u64);
            }
            feed(&mut hash, self.reserves[seat].len() as u64);
            for &(id, tier, public) in &self.reserves[seat] {
                feed(&mut hash, id as u64);
                feed(&mut hash, tier as u64);
                feed(&mut hash, public as u64);
            }
        }
        for deck in &self.decks {
            feed(&mut hash, deck.len() as u64);
            for &id in deck {
                feed(&mut hash, id as u64);
            }
        }
        hash
    }

    fn snapshot(&self, obs: &Observation) -> String {
        let mut text = format!(
            "S;{};{};{};{};{};",
            obs.count,
            obs.current,
            obs.turns,
            obs.players[..obs.count as usize]
                .iter()
                .any(|p| p.score >= 15) as u8,
            phase_code(obs.phase),
        );
        write!(
            &mut text,
            "B:{};M:{};",
            csv(obs.bank),
            csv(obs
                .market
                .iter()
                .map(|&id| if id == u8::MAX { 0 } else { id + 1 }))
        )
        .unwrap();
        for tier in 0..3 {
            write!(&mut text, "D{tier}:{};", csv(&self.decks[tier])).unwrap();
        }
        let mut available = (0..10)
            .filter(|&id| obs.nobles & (1 << id) != 0)
            .map(ahin_noble_id)
            .collect::<Vec<_>>();
        available.sort_unstable();
        write!(&mut text, "N:{};", csv(available)).unwrap();
        for seat in 0..obs.count as usize {
            let player = &obs.players[seat];
            let owned = (0..90)
                .filter(|&id| player.owned & (1u128 << id) != 0)
                .map(|id| id + 1)
                .collect::<Vec<_>>();
            let mut claimed = (0..10)
                .filter(|&id| player.nobles & (1 << id) != 0)
                .map(ahin_noble_id)
                .collect::<Vec<_>>();
            claimed.sort_unstable();
            write!(
                &mut text,
                "P{seat};T:{};B:{};S:{};O:{};N:{};R:",
                csv(player.tokens),
                csv(player.bonuses),
                player.score,
                csv(owned),
                csv(claimed),
            )
            .unwrap();
            for (index, &(id, tier, public)) in self.reserves[seat].iter().enumerate() {
                if index > 0 {
                    text.push(',');
                }
                write!(&mut text, "{id}:{tier}:{}", public as u8).unwrap();
            }
            text.push(';');
        }
        text
    }
}

fn action_line(action: Action) -> String {
    match action {
        Action::Take(v) => format!("ACTION|take|{}", csv(v)),
        Action::ReserveVisible(i) => format!("ACTION|reserve_visible|{i}"),
        Action::ReserveDeck(i) => format!("ACTION|reserve_deck|{i}"),
        Action::BuyVisible(i) => format!("ACTION|buy_visible|{i}"),
        Action::BuyReserved(i) => format!("ACTION|buy_reserved|{i}"),
        Action::Pay(v) => format!("ACTION|pay|{}", csv(v)),
        Action::Return(v) => format!("ACTION|return|{}", csv(v)),
        Action::Noble(i) => format!("ACTION|noble|{i}"),
    }
}

fn select_action(state: &GameState, legal: &ActionSet) -> Option<Action> {
    match state.phase() {
        Phase::Main => {
            let turn = state.turns();
            let obs = state.observe(state.current_player());
            let player = &obs.players[obs.current as usize];
            if let Some(&action) = legal.iter().find(|a| matches!(a, Action::BuyVisible(_))) {
                return Some(action);
            }
            if let Some(&action) = legal.iter().find(|a| matches!(a, Action::BuyReserved(_))) {
                return Some(action);
            }
            if turn == 0
                && let Some(&action) = legal.iter().find(|a| matches!(a, Action::ReserveDeck(_)))
            {
                return Some(action);
            }
            if turn == 2
                && let Some(&action) = legal
                    .iter()
                    .find(|a| matches!(a, Action::ReserveVisible(_)))
            {
                return Some(action);
            }
            if player.token_count() >= 10
                && let Some(&action) = legal.iter().find(|a| matches!(a, Action::ReserveDeck(_)))
            {
                return Some(action);
            }
            let market_target = obs
                .market
                .iter()
                .copied()
                .filter(|&id| id != u8::MAX)
                .min_by_key(|&id| {
                    let card = CARDS[id as usize];
                    card.cost
                        .iter()
                        .enumerate()
                        .map(|(i, &cost)| cost.saturating_sub(player.bonuses[i]) as u16)
                        .sum::<u16>()
                });
            if let Some(target) = market_target {
                let card = CARDS[target as usize];
                let mut best = None;
                for &action in legal.iter().filter(|a| matches!(a, Action::Take(_))) {
                    let Action::Take(tokens) = action else {
                        unreachable!()
                    };
                    let coverage = (0..5)
                        .map(|i| {
                            (player.tokens[i] + tokens[i] + player.bonuses[i]).min(card.cost[i])
                                as u16
                        })
                        .sum::<u16>();
                    if best.is_none_or(|(_, value)| coverage > value) {
                        best = Some((action, coverage));
                    }
                }
                if let Some((action, _)) = best {
                    return Some(action);
                }
            }
            legal.first().copied()
        }
        Phase::Payment(_) => legal
            .iter()
            .max_by_key(|action| match action {
                Action::Pay(payment) => payment.iter().map(|&x| x as u16).sum::<u16>(),
                _ => 0,
            })
            .copied(),
        Phase::Return => legal
            .iter()
            .find(|action| matches!(action, Action::Return(v) if v[GOLD] == 0))
            .copied(),
        Phase::Noble => legal
            .iter()
            .find(|a| matches!(a, Action::Noble(_)))
            .copied(),
        Phase::Terminal => None,
    }
}

fn main() {
    let mut args = std::env::args().skip(1);
    let output = args
        .next()
        .expect("usage: engine_profile OUTPUT.txt SEED [REPLAYS] [REPEATS]");
    let seed = args
        .next()
        .expect("valid seed")
        .parse::<u64>()
        .expect("valid seed");
    let replay_games = args
        .next()
        .as_deref()
        .unwrap_or("10000")
        .parse::<usize>()
        .expect("valid replay count");
    let repeats = args
        .next()
        .as_deref()
        .unwrap_or("3")
        .parse::<usize>()
        .expect("valid repeat count");
    assert!(replay_games > 0 && repeats > 0);
    let mut setup_rng = Rng::new(seed);
    let mut orders = [Vec::new(), Vec::new(), Vec::new()];
    for (tier, order) in orders.iter_mut().enumerate() {
        *order = (0..90)
            .filter(|&id| CARDS[id].tier as usize == tier)
            .map(|id| id as u8)
            .collect();
        setup_rng.shuffle(order);
    }
    let mut noble_pool = (0..10).collect::<Vec<u8>>();
    setup_rng.shuffle(&mut noble_pool);
    let noble_ids = [noble_pool[0], noble_pool[1], noble_pool[2]];
    let state_orders = [&orders[0][..], &orders[1][..], &orders[2][..]];
    let mut state =
        GameState::new_benchmark_setup(2, state_orders, &noble_ids).expect("valid benchmark setup");
    let initial_state = state.clone();
    let mut shadow = Shadow::new(&orders);
    let path = std::path::Path::new(&output);
    let mut out = BufWriter::new(File::create(path).expect("create trajectory"));
    writeln!(out, "TRAJECTORY|sprint48-ahin-full-turn-v1|{seed}").unwrap();
    for (tier, order) in orders.iter().enumerate() {
        writeln!(
            out,
            "SETUP_DECK|{tier}|{}",
            csv(order.iter().map(|&id| id + 1))
        )
        .unwrap();
    }
    writeln!(
        out,
        "SETUP_NOBLES|{}",
        csv(noble_ids.map(|id| ahin_noble_id(id as usize)))
    )
    .unwrap();
    let initial = state.observe(0);
    writeln!(
        out,
        "START|{:016x}|{}",
        shadow.digest(&initial),
        shadow.snapshot(&initial)
    )
    .unwrap();
    let mut phase_seen = [false; 5];
    let mut actions_seen = [0u64; 8];
    let mut action_trace: Vec<Vec<Action>> = Vec::new();
    let mut cached_steps: Vec<CachedStep> = Vec::new();
    let mut turns = 0usize;
    let mut status = "complete";
    while !state.is_terminal() && turns < 400 {
        let starting_turn = state.turns();
        writeln!(out, "TURN|{turns}").unwrap();
        let mut action_steps = 0;
        let mut turn_actions = Vec::new();
        while !state.is_terminal() && state.turns() == starting_turn {
            let phase = state.phase();
            phase_seen[match phase {
                Phase::Main => 0,
                Phase::Payment(_) => 1,
                Phase::Return => 2,
                Phase::Noble => 3,
                Phase::Terminal => 4,
            }] = true;
            let mut legal = ActionSet::new();
            state.legal_actions_reference(&mut legal);
            if legal.is_empty() {
                status = "unsupported_no_action";
                break;
            }
            let Some(action) = select_action(&state, &legal) else {
                status = if phase == Phase::Return {
                    "unsupported_gold_return"
                } else {
                    "unsupported_action"
                };
                break;
            };
            let category = match action {
                Action::Take(_) => 0,
                Action::ReserveVisible(_) => 1,
                Action::ReserveDeck(_) => 2,
                Action::BuyVisible(_) => 3,
                Action::BuyReserved(_) => 4,
                Action::Pay(_) => 5,
                Action::Return(_) => 6,
                Action::Noble(_) => 7,
            };
            actions_seen[category] += 1;
            writeln!(out, "{}", action_line(action)).unwrap();
            turn_actions.push(action);
            let before = state.clone();
            shadow.apply(
                action,
                state.current_player(),
                &state.observe(state.current_player()),
            );
            state
                .apply_action(action)
                .expect("selected action is legal");
            let observations_after = (0..state.player_count())
                .map(|seat| state.observe(seat))
                .collect();
            cached_steps.push(CachedStep {
                before,
                action,
                after: state.clone(),
                legal,
                observations_after,
            });
            action_steps += 1;
            assert!(
                action_steps <= 8,
                "one turn exceeded expected compound-action bound"
            );
        }
        if status != "complete" {
            break;
        }
        assert!(
            state.turns() > starting_turn || state.is_terminal(),
            "selected turn did not finish"
        );
        let after = state.observe(0);
        let digest = shadow.digest(&after);
        writeln!(
            out,
            "ENDTURN|{turns}|{:016x}|{}",
            digest,
            shadow.snapshot(&after)
        )
        .unwrap();
        turns += 1;
        action_trace.push(turn_actions);
    }
    if turns == 400 && !state.is_terminal() {
        status = "turn_limit";
    }
    if state.is_terminal() {
        phase_seen[4] = true;
    }
    writeln!(
        out,
        "END|{status}|{turns}|{:016x}|{}",
        shadow.digest(&state.observe(0)),
        shadow.snapshot(&state.observe(0))
    )
    .unwrap();
    out.flush().expect("flush trajectory");
    eprintln!(
        "status={status} turns={turns} phase_seen={phase_seen:?} action_counts={actions_seen:?}"
    );
    if status != "complete" {
        std::process::exit(2);
    }
    let mut choices_by_phase = [0usize; 4];
    let mut max_choices_by_phase = [0usize; 4];
    for step in &cached_steps {
        let phase = match step.before.phase() {
            Phase::Main => 0,
            Phase::Payment(_) => 1,
            Phase::Return => 2,
            Phase::Noble => 3,
            Phase::Terminal => unreachable!(),
        };
        choices_by_phase[phase] += step.legal.len();
        max_choices_by_phase[phase] = max_choices_by_phase[phase].max(step.legal.len());
    }
    eprintln!(
        "choices_by_phase={choices_by_phase:?} max_choices_by_phase={max_choices_by_phase:?} state_bytes={} action_bytes={} action_set_bytes={}",
        std::mem::size_of::<GameState>(),
        std::mem::size_of::<Action>(),
        std::mem::size_of::<ActionSet>()
    );
    eprintln!(
        "outcome_winners_mask={}",
        state.outcome().expect("complete trace").winners
    );
    let expected_final = state;
    let mut correctness_replay = initial_state.clone();
    for (index, step) in cached_steps.iter().enumerate() {
        assert_eq!(
            correctness_replay, step.before,
            "recorded pre-action state at step {index}"
        );
        let mut legal = ActionSet::new();
        correctness_replay.legal_actions_reference(&mut legal);
        assert_eq!(legal, step.legal, "reference enumeration changed");
        let mut optimized = ActionSet::new();
        correctness_replay.legal_actions(&mut optimized);
        assert_eq!(
            optimized, legal,
            "optimized enumeration/order mismatch at {index}"
        );
        assert!(legal.contains(&step.action));
        let mut guarded = correctness_replay.clone();
        guarded.decision(&mut optimized).apply(step.action).unwrap();
        assert_eq!(
            guarded, step.after,
            "validated decision mismatch at {index}"
        );
        correctness_replay.apply_action(step.action).unwrap();
        assert_eq!(
            correctness_replay, step.after,
            "exact state mismatch after action {index}"
        );
        for (seat, expected) in step.observations_after.iter().enumerate() {
            assert_eq!(
                correctness_replay.observe(seat),
                *expected,
                "observation mismatch after action {index}, seat {seat}"
            );
        }
    }
    assert_eq!(
        correctness_replay, expected_final,
        "full Rust trace state mismatch"
    );
    println!(
        "engine,workload,repeat,replayed_games,complete_turns,canonical_actions,native_apply_calls,legal_enumerations,seconds,turns_per_second,games_per_second,operation_count"
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_new_buffer_checked",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_reused_buffer_checked",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_checked_apply_only",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_trace_traversal_clone",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_optimized_enum_checked",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_optimized_reused_checked",
    );
    profile_full(
        &action_trace,
        &initial_state,
        replay_games,
        repeats,
        "full_validated_decision",
    );
    profile_components(&cached_steps, replay_games, repeats);
}

fn emit(workload: &str, repeat: usize, games: usize, counts: [usize; 5], seconds: f64) {
    let [turns, actions, applies, enumerations, operations] = counts;
    let turns_per_second = if turns == 0 {
        0.0
    } else {
        turns as f64 / seconds
    };
    let games_per_second = if games == 0 || turns == 0 {
        0.0
    } else {
        games as f64 / seconds
    };
    println!(
        "rust,{workload},{repeat},{games},{turns},{actions},{applies},{enumerations},{seconds:.6},{turns_per_second:.2},{games_per_second:.4},{operations}"
    );
}

fn profile_full(
    action_trace: &[Vec<Action>],
    initial: &GameState,
    games: usize,
    repeats: usize,
    workload: &str,
) {
    let optimized = workload.starts_with("full_optimized");
    let turn_count = action_trace.len();
    let action_count: usize = action_trace.iter().map(Vec::len).sum();
    for repeat in 0..repeats {
        let start = Instant::now();
        for _ in 0..games {
            let mut replay = initial.clone();
            match workload {
                "full_new_buffer_checked" | "full_optimized_enum_checked" => {
                    for turn in action_trace {
                        for &action in turn {
                            let mut legal = ActionSet::new();
                            if optimized {
                                replay.legal_actions(&mut legal);
                            } else {
                                replay.legal_actions_reference(&mut legal);
                            }
                            let action = black_box(action);
                            assert!(black_box(legal.as_slice()).contains(&action));
                            replay.apply_action(action).expect("replay legal action");
                        }
                        black_box(&replay);
                    }
                }
                "full_reused_buffer_checked" | "full_optimized_reused_checked" => {
                    let mut legal = ActionSet::new();
                    for turn in action_trace {
                        for &action in turn {
                            if optimized {
                                replay.legal_actions(&mut legal);
                            } else {
                                replay.legal_actions_reference(&mut legal);
                            }
                            let action = black_box(action);
                            assert!(black_box(legal.as_slice()).contains(&action));
                            replay.apply_action(action).expect("replay legal action");
                        }
                        black_box(&replay);
                    }
                }
                "full_validated_decision" => {
                    let mut legal = ActionSet::new();
                    for turn in action_trace {
                        for &action in turn {
                            let decision = replay.decision(&mut legal);
                            black_box(decision.actions());
                            decision
                                .apply(black_box(action))
                                .expect("enumerated action");
                        }
                        black_box(&replay);
                    }
                }
                "full_checked_apply_only" => {
                    for turn in action_trace {
                        for &action in turn {
                            replay
                                .apply_action(black_box(action))
                                .expect("replay legal action");
                        }
                        black_box(&replay);
                    }
                }
                "full_trace_traversal_clone" => {
                    for turn in action_trace {
                        for action in turn {
                            black_box(action);
                        }
                        black_box(&replay);
                    }
                }
                _ => unreachable!(),
            }
        }
        let seconds = start.elapsed().as_secs_f64();
        let timed_applies = if workload == "full_new_buffer_checked"
            || workload == "full_reused_buffer_checked"
            || workload.starts_with("full_optimized")
            || workload == "full_validated_decision"
            || workload == "full_checked_apply_only"
        {
            action_count * games
        } else {
            0
        };
        let timed_enumerations = if workload == "full_new_buffer_checked"
            || workload == "full_reused_buffer_checked"
            || workload.starts_with("full_optimized")
            || workload == "full_validated_decision"
        {
            action_count * games
        } else {
            0
        };
        emit(
            workload,
            repeat,
            if timed_applies == 0 { 0 } else { games },
            [
                if timed_applies == 0 {
                    0
                } else {
                    turn_count * games
                },
                timed_applies,
                timed_applies,
                timed_enumerations,
                action_count * games,
            ],
            seconds,
        );
    }
}

fn profile_components(steps: &[CachedStep], games: usize, repeats: usize) {
    let phase_names = ["main", "payment", "return", "noble", "terminal"];
    let mut phase_steps: [Vec<usize>; 5] = std::array::from_fn(|_| Vec::new());
    for (index, step) in steps.iter().enumerate() {
        let phase = match step.before.phase() {
            Phase::Main => 0,
            Phase::Payment(_) => 1,
            Phase::Return => 2,
            Phase::Noble => 3,
            Phase::Terminal => 4,
        };
        phase_steps[phase].push(index);
    }
    for repeat in 0..repeats {
        let mut legal = ActionSet::new();
        for optimized in [false, true] {
            for (phase, indices) in phase_steps.iter().enumerate() {
                let start = Instant::now();
                let mut sink = 0usize;
                for _ in 0..games {
                    for &index in indices {
                        if optimized {
                            black_box(&steps[index].before).legal_actions(&mut legal);
                        } else {
                            black_box(&steps[index].before).legal_actions_reference(&mut legal);
                        }
                        sink = sink.wrapping_add(black_box(legal.as_slice()).len());
                    }
                }
                black_box(sink);
                let workload = format!(
                    "enumeration_{}_{}",
                    if optimized { "optimized" } else { "reference" },
                    phase_names[phase]
                );
                emit(
                    &workload,
                    repeat,
                    0,
                    [0, 0, 0, indices.len() * games, indices.len() * games],
                    start.elapsed().as_secs_f64(),
                );
            }
        }

        let start = Instant::now();
        let mut sink = 0usize;
        for _ in 0..games {
            for step in steps {
                sink = sink.wrapping_add(
                    black_box(step.legal.as_slice()).contains(&black_box(step.action)) as usize,
                );
            }
        }
        black_box(sink);
        emit(
            "cached_membership",
            repeat,
            0,
            [0, 0, 0, 0, steps.len() * games],
            start.elapsed().as_secs_f64(),
        );

        let start = Instant::now();
        let mut sink = 0usize;
        for _ in 0..games {
            for step in steps {
                let mut state = black_box(step.before.clone());
                state
                    .apply_action(black_box(step.action))
                    .expect("cached legal action");
                black_box(&state);
                sink = sink.wrapping_add(black_box(state.turns()) as usize);
            }
        }
        black_box(sink);
        emit(
            "cached_clone_checked_apply",
            repeat,
            0,
            [0, 0, steps.len() * games, 0, steps.len() * games],
            start.elapsed().as_secs_f64(),
        );

        let start = Instant::now();
        let mut sink = 0usize;
        for _ in 0..games {
            for step in steps {
                let state = black_box(step.before.clone());
                sink = sink.wrapping_add(black_box(state.turns()) as usize);
            }
        }
        black_box(sink);
        emit(
            "cached_clone_only",
            repeat,
            0,
            [0, 0, 0, 0, steps.len() * games],
            start.elapsed().as_secs_f64(),
        );
    }
}

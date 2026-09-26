//! Cooperative coverage search, not a competitive agent or strength experiment.
use splendor_agents::action_score;
use splendor_arena::{History, encode, replay};
use splendor_core::{
    Action, ActionSet, ENGINE_VERSION, GameState, NONE, Observation, Phase, Player, Rng,
    data::CARDS,
};

fn gap(o: &Observation, p: &Player, tier: u8) -> i32 {
    o.market
        .iter()
        .copied()
        .chain(p.reserved.iter().map(|r| r.card))
        .filter(|&id| id != NONE && CARDS[id as usize].tier == tier)
        .map(|id| {
            (0..5)
                .map(|c| {
                    i32::from(
                        CARDS[id as usize].cost[c]
                            .saturating_sub(p.bonuses[c])
                            .saturating_sub(p.tokens[c]),
                    )
                })
                .sum::<i32>()
                - i32::from(p.tokens[5])
        })
        .min()
        .unwrap_or(0)
        .max(0)
}
fn score(o: &Observation, a: Action, tier: u8) -> i32 {
    let p = o.players[o.current as usize];
    match a {
        Action::BuyVisible(i) | Action::BuyReserved(i) => {
            let id = if matches!(a, Action::BuyVisible(_)) {
                o.market[i as usize]
            } else {
                p.reserved[i as usize].card
            };
            let card = CARDS[id as usize];
            if p.score + card.points >= 15 {
                return -10000;
            }
            action_score(o, a, true)
                + if card.tier == tier {
                    3000
                } else if card.points == 0 {
                    500
                } else {
                    -1000
                }
        }
        Action::ReserveVisible(i) if CARDS[o.market[i as usize] as usize].tier == tier => {
            1800 - CARDS[o.market[i as usize] as usize]
                .cost
                .iter()
                .map(|&v| i32::from(v))
                .sum::<i32>()
                * 10
        }
        Action::Take(t) => {
            let mut q = p;
            for (c, v) in t.into_iter().enumerate() {
                q.tokens[c] += v;
            }
            action_score(o, a, true) + (gap(o, &p, tier) - gap(o, &q, tier)) * 200
        }
        Action::Return(t) => {
            let mut q = p;
            for (c, v) in t.into_iter().enumerate() {
                q.tokens[c] -= v;
            }
            action_score(o, a, true) - gap(o, &q, tier) * 200
        }
        _ => action_score(o, a, true),
    }
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let output = std::path::PathBuf::from(args.next().ok_or("new output directory")?);
    std::fs::create_dir(&output)?;
    for tier in [1u8, 2] {
        let mut best = 255;
        let mut found = false;
        for attempt in 0..100u64 {
            let seed = 107000000 + u64::from(tier) * 1000 + attempt;
            let mut state = GameState::new(4, seed)?;
            let mut rng = Rng::new(seed ^ 0xeaaef00d);
            let mut history = History {
                format: 1,
                engine: ENGINE_VERSION.into(),
                players: 4,
                seed,
                actions: Vec::new(),
                state_debug: String::new(),
            };
            let mut legal = ActionSet::new();
            let mut exhausted_actions = 0u8;
            for _ in 0..2000 {
                let o = state.observe(state.current_player());
                best = best.min(o.remaining[tier as usize]);
                if exhausted_actions == 3 && state.phase() == Phase::Main {
                    history.state_debug = format!("{state:?}");
                    assert_eq!(replay(&history)?, state);
                    std::fs::write(
                        output.join(format!("tier-{}-v2.json", tier + 1)),
                        serde_json::to_vec(&history)?,
                    )?;
                    println!(
                        "tier {} seed {seed} attempts {} turns {} decisions {} scores {:?}",
                        tier + 1,
                        attempt + 1,
                        state.turns(),
                        history.actions.len(),
                        o.players.map(|p| p.score)
                    );
                    found = true;
                    break;
                }
                if state.is_terminal() {
                    break;
                }
                state.legal_actions(&mut legal);
                if legal.is_empty() {
                    break;
                }
                let action = if rng.index(16) == 0 {
                    legal[rng.index(legal.len())]
                } else {
                    *legal.iter().max_by_key(|&&a| score(&o, a, tier)).unwrap()
                };
                if o.remaining[tier as usize] == 0
                    && matches!(action, Action::BuyVisible(i) | Action::ReserveVisible(i) if i / 4 == tier)
                {
                    exhausted_actions |= if matches!(action, Action::BuyVisible(_)) {
                        1
                    } else {
                        2
                    };
                }
                state.apply_action(action)?;
                state.check_invariants()?;
                history.actions.push(encode(action));
            }
            if found {
                break;
            }
            eprintln!(
                "tier {} seed {seed} failed: turns {} remaining {} phase {:?} removal_mask {exhausted_actions}",
                tier + 1,
                state.turns(),
                state.observe(state.current_player()).remaining[tier as usize],
                state.phase()
            );
        }
        if !found {
            return Err(format!("tier {} not depleted; minimum remaining {best}", tier + 1).into());
        }
    }
    Ok(())
}

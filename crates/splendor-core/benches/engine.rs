use criterion::{Criterion, black_box, criterion_group, criterion_main};
use splendor_core::{ActionSet, GameState, Phase, Rng};
fn bench(c: &mut Criterion) {
    let s = GameState::new(2, 42).unwrap();
    let mut a = ActionSet::new();
    s.legal_actions(&mut a);
    let action = a[0];
    c.bench_function("legal/opening", |b| {
        b.iter(|| black_box(&s).legal_actions(black_box(&mut a)))
    });
    let mut trajectory = s.clone();
    let mut rng = Rng::new(123);
    let mut fixtures: [Option<GameState>; 3] = [None, None, None];
    for _ in 0..2000 {
        let slot = match trajectory.phase() {
            Phase::Main if trajectory.turns() > 30 => Some(0),
            Phase::Payment(_) => Some(1),
            Phase::Return => Some(2),
            _ => None,
        };
        if let Some(slot) = slot
            && fixtures[slot].is_none()
        {
            fixtures[slot] = Some(trajectory.clone());
        }
        trajectory.legal_actions(&mut a);
        if a.is_empty() {
            break;
        }
        trajectory.apply_action(a[rng.index(a.len())]).unwrap();
    }
    for (name, fixture) in ["main-midgame", "payment", "return"]
        .into_iter()
        .zip(fixtures)
    {
        let fixture = fixture.expect("seeded benchmark fixture must reach every phase");
        c.bench_function(&format!("legal/{name}"), |b| {
            b.iter(|| black_box(&fixture).legal_actions(black_box(&mut a)))
        });
    }
    // Fixed opening and midgame observations, including hidden reservations.
    // No agent policy, I/O, or clock is included in these measured operations.
    for count in 2..=4 {
        let mut state = GameState::new(count, 42).unwrap();
        let mut choices = ActionSet::new();
        let mut fixture_rng = Rng::new(123);
        for label in ["opening", "midgame"] {
            if label == "midgame" {
                while state.turns() < 40 {
                    state.legal_actions(&mut choices);
                    assert!(!choices.is_empty(), "fixed fixture must reach turn 40");
                    state
                        .apply_action(choices[fixture_rng.index(choices.len())])
                        .unwrap();
                }
            }
            let observation = state.observe(state.current_player());
            c.bench_function(&format!("determinize/{label}-{count}p"), |b| {
                b.iter_batched(
                    || Rng::new(456),
                    |mut rng| {
                        black_box(&observation)
                            .determinize(black_box(&mut rng))
                            .unwrap()
                    },
                    criterion::BatchSize::SmallInput,
                )
            });
            c.bench_function(&format!("invariants/{label}-{count}p"), |b| {
                b.iter(|| black_box(&state).check_invariants().unwrap())
            });
        }
    }
    c.bench_function("clone", |b| b.iter(|| black_box(black_box(&s).clone())));
    c.bench_function("clone_apply", |b| {
        b.iter(|| {
            let mut t = black_box(&s).clone();
            t.apply_action(black_box(action)).unwrap();
            black_box(t)
        })
    });
    c.bench_function("apply", |b| {
        b.iter_batched(
            || s.clone(),
            |mut t| {
                t.apply_action(black_box(action)).unwrap();
                black_box(t)
            },
            criterion::BatchSize::SmallInput,
        )
    });
    c.bench_function("random_game", |b| {
        b.iter(|| {
            let mut s = GameState::new(2, 42).unwrap();
            let mut rng = Rng::new(123);
            let mut a = ActionSet::new();
            for _ in 0..10000 {
                s.legal_actions(&mut a);
                if a.is_empty() {
                    break;
                }
                s.apply_action(a[rng.index(a.len())]).unwrap();
            }
            black_box(s)
        })
    });
}
criterion_group!(benches, bench);
criterion_main!(benches);

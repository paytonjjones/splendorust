use criterion::{Criterion, black_box, criterion_group, criterion_main};
use splendor_agents::SearchConfig;
use splendor_arena::{RunConfig, tournament};
fn arena(c: &mut Criterion) {
    for threads in [1, 4] {
        let config = RunConfig {
            names: vec!["random".into(); 2],
            games: 256,
            seed: 12345,
            threads,
            max_decisions: 20000,
            check: false,
            search: SearchConfig::default(),
        };
        c.bench_function(&format!("arena/random/threads-{threads}/256-games"), |b| {
            b.iter(|| black_box(tournament(&config).unwrap()))
        });
    }
}
criterion_group!(benches, arena);
criterion_main!(benches);

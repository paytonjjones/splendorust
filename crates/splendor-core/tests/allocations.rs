//! Allocation checks live outside the unsafe-free production library.
use splendor_core::{Action, ActionSet, GameState, Phase, Rng};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

struct CountingAllocator;
thread_local! {
    static TRACKING: Cell<(bool, usize)> = const { Cell::new((false, 0)) };
}

fn record_allocation() {
    let _ = TRACKING.try_with(|tracking| {
        let (active, count) = tracking.get();
        if active {
            tracking.set((true, count + 1));
        }
    });
}

// SAFETY: Every operation forwards the unchanged pointer and layout to System.
// The thread-local counter owns no allocated memory and does not call the allocator.
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record_allocation();
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record_allocation();
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record_allocation();
        unsafe { System.realloc(ptr, layout, size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

struct TrackingGuard;
impl Drop for TrackingGuard {
    fn drop(&mut self) {
        TRACKING.with(|tracking| tracking.set((false, tracking.get().1)));
    }
}

fn measured<T>(run: impl FnOnce() -> T) -> (T, usize) {
    TRACKING.with(|tracking| tracking.set((true, 0)));
    let guard = TrackingGuard;
    let result = run();
    drop(guard);
    (result, TRACKING.with(|tracking| tracking.get().1))
}

#[test]
fn normal_core_paths_do_not_allocate() {
    // Confirm that this build observes allocation before testing the core.
    let (_, control) = measured(|| black_box(Box::new(black_box([0u8; 128]))));
    assert!(control > 0);
    let ((phases, actions), allocations) = measured(|| {
        let mut phases = [0usize; 5];
        let mut actions = [0usize; 8];
        for players in 2..=4 {
            for seed in 0..256 {
                let mut state = GameState::new(players, 131_000_000 + seed).unwrap();
                let mut rng = Rng::new(seed);
                for _ in 0..2000 {
                    phases[match state.phase() {
                        Phase::Main => 0,
                        Phase::Payment(_) => 1,
                        Phase::Return => 2,
                        Phase::Noble => 3,
                        Phase::Terminal => 4,
                    }] += 1;
                    state.check_invariants().unwrap();
                    let observation = state.observe(state.current_player());
                    black_box(observation.determinize(&mut rng).unwrap());
                    let mut legal = ActionSet::new();
                    state.legal_actions(&mut legal);
                    for &action in &legal {
                        actions[match action {
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
                        black_box(branch.observe(branch.current_player()));
                    }
                    if legal.is_empty() {
                        break;
                    }
                    let mut chosen = legal[rng.index(legal.len())];
                    // Reach purchase and noble phases without an agent dependency.
                    if rng.index(2) == 0
                        && let Some(&buy) = legal
                            .iter()
                            .find(|a| matches!(a, Action::BuyVisible(_) | Action::BuyReserved(_)))
                    {
                        chosen = buy;
                    }
                    state.apply_action(chosen).unwrap();
                }
            }
        }
        (phases, actions)
    });
    assert_eq!(allocations, 0);
    assert!(
        phases.iter().all(|&count| count > 0),
        "phase coverage: {phases:?}"
    );
    assert!(
        actions.iter().all(|&count| count > 0),
        "action coverage: {actions:?}"
    );
    println!("phases={phases:?} actions={actions:?} allocations={allocations}");
}

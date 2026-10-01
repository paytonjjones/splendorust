//! Four independent selected-action votes versus one executed teacher.
use rayon::prelude::*;
use splendor_agents::{SearchConfig, make_agent, neural::action_index};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::time::Instant;
fn main() {
    let start = Instant::now();
    let config = SearchConfig {
        iterations: 800,
        depth: 16,
        ..Default::default()
    };
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(14)
        .build()
        .unwrap();
    let mut stream = Rng::new(4_790_000_000);
    let setups: Vec<_> = (0..1000).map(|_| stream.next_u64()).collect();
    let rows = pool.install(|| setups.par_iter().enumerate().flat_map_iter(|(block,&setup)| {
        let config = &config;
        [0usize,1].into_iter().map(move |rotation| {
            let mut state = GameState::new(2,setup).unwrap();
            let policy_base = 4_791_000_000+block as u64*16;
            let mut ensemble:Vec<_> = (0..4).map(|r|make_agent("flywheel-root-gumbel-best",policy_base+r,config).unwrap()).collect();
            let mut single = make_agent("flywheel-root-gumbel-best",policy_base+8,config).unwrap();
            let mut legal = ActionSet::new();let mut blocked = false;let mut decisions = 0;let mut ties = 0;let mut first_agreement = 0;let mut max_vote_sum = 0;
            for _ in 0..20000 {
                if state.is_terminal() {break;}
                state.legal_actions(&mut legal);if legal.is_empty() {blocked=true;break;}
                let seat = state.current_player();let o = state.observe(seat);
                let action = if seat==rotation {
                    let first = ensemble[0].select_action(&o,&legal);
                    if o.phase!=Phase::Main {first} else {
                        let mut votes = [0u8;67];let mut credits = [0.0f64;67];
                        let id = action_index(first).unwrap();votes[id]+=1;credits[id]+=f64::from(ensemble[0].value_target().unwrap());
                        for teacher in &mut ensemble[1..] {
                            let chosen = teacher.select_action(&o,&legal);let id = action_index(chosen).unwrap();votes[id]+=1;credits[id]+=f64::from(teacher.value_target().unwrap());
                        }
                        let max_vote = *votes.iter().max().unwrap();
                        ties += u64::from(votes.iter().filter(|&&v|v==max_vote).count()>1);
                        let chosen = *legal.iter().filter(|a|votes[action_index(**a).unwrap()]>0).max_by(|a,b| {
                            let ai=action_index(**a).unwrap();let bi=action_index(**b).unwrap();
                            votes[ai].cmp(&votes[bi]).then_with(||(credits[ai]/f64::from(votes[ai])).total_cmp(&(credits[bi]/f64::from(votes[bi])))).then_with(||bi.cmp(&ai))
                        }).unwrap();
                        decisions+=1;first_agreement+=u64::from(chosen==first);max_vote_sum+=u64::from(max_vote);chosen
                    }
                } else {single.select_action(&o,&legal)};
                state.apply_action(action).unwrap();
            }
            let outcome=state.outcome();let credit=outcome.map(|o|if o.winners&(1<<rotation)!=0{1.0/f64::from(o.winners.count_ones())}else{0.0});
            serde_json::json!({"block":block,"rotation":rotation,"setup":setup,"status":if outcome.is_some(){"complete"}else if blocked{"blocked"}else{"capped"},"consensus_credit":credit,"turns":state.turns(),"ensemble_main_decisions":decisions,"vote_ties":ties,"first_replica_agreements":first_agreement,"max_vote_sum":max_vote_sum,"ensemble_simulations":ensemble.iter().map(|a|a.work_counts().0).sum::<u64>(),"single_simulations":single.work_counts().0,"ensemble_inferences":ensemble.iter().map(|a|a.work_counts().1).sum::<u64>(),"single_inferences":single.work_counts().1})
        })
    }).collect::<Vec<_>>());
    println!(
        "{}",
        serde_json::json!({"schema":"consensus-teacher-v1","games":2000,"blocks":1000,"master":4790000000u64,"replicas":4,"iterations_per_replica":800,"single_iterations":800,"depth":16,"threads":14,"seconds":start.elapsed().as_secs_f64(),"rule":"teacher diagnostic only; unequal compute; no model promotion"})
    );
    for row in rows {
        println!("{row}");
    }
}

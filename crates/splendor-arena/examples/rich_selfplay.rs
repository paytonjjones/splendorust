//! Opt-in canonical search labels. The agent receives Observation only.
use clap::Parser;
use rayon::prelude::*;
use splendor_agents::{
    Agent, SearchConfig, neural::action_index, neural_search::NeuralAgent, transfer,
};
use splendor_arena::{History, encode, replay};
use splendor_core::{ActionSet, ENGINE_VERSION, GameState, Phase, Rng};
use std::{
    io::{BufWriter, Write},
    path::PathBuf,
    time::Instant,
};

const ROW_BYTES: usize = 2600;

#[derive(Parser)]
struct Args {
    #[arg(long)]
    model: PathBuf,
    #[arg(long)]
    output: PathBuf,
    #[arg(long)]
    games: usize,
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    policy_seed: u64,
    #[arg(long, default_value_t = 256)]
    iterations: u32,
    #[arg(long, default_value_t = 16)]
    depth: u32,
    #[arg(long, default_value_t = 32)]
    threads: usize,
    #[arg(long, default_value_t = 20000)]
    max_decisions: usize,
    /// Fraction of turns with full search; only full captured states train.
    #[arg(long, default_value_t = 1.0)]
    full_probability: f64,
    #[arg(long, default_value_t = 64)]
    cheap_iterations: u32,
    /// Sample visits in the first N total player turns (zero preserves argmax play).
    #[arg(long, default_value_t = 0)]
    stochastic_turns: u32,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a = Args::parse();
    assert!(a.games > 0 && a.threads > 0 && a.iterations > 0 && a.cheap_iterations > 0);
    assert!((0.0..=1.0).contains(&a.full_probability));
    assert!(!a.output.exists(), "output must be new");
    std::fs::create_dir_all(&a.output)?;
    let model = Box::leak(Box::new(transfer::Model::from_bytes(&std::fs::read(
        &a.model,
    )?)));
    let native_ids = transfer::policy_logits(&std::array::from_fn(|i| i as f32));
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(a.threads)
        .build()?;
    let start = Instant::now();
    let mut data = BufWriter::new(std::fs::File::create(a.output.join("rows.bin.partial"))?);
    let mut history_out = BufWriter::new(std::fs::File::create(
        a.output.join("histories.jsonl.partial"),
    )?);
    let mut counts = [0usize; 3];
    let (mut rows, mut full_rows, mut simulations, mut inferences) = (0usize, 0usize, 0u64, 0u64);
    for batch in (0..a.games).step_by(64) {
        let results:Vec<_>=pool.install(||(batch..(batch+64).min(a.games)).into_par_iter().map(|g| {
            let setup=Rng::new(a.seed.wrapping_add(g as u64)).next_u64();
            let mut policy_rng=Rng::new(a.policy_seed.wrapping_add(g as u64));
            let mut encoder=Rng::new(policy_rng.next_u64());
            let mut curriculum=Rng::new(policy_rng.next_u64());
            let mut agents=std::array::from_fn::<_,2,_>(|_| {
                let mut agent=NeuralAgent::new(policy_rng.next_u64(),SearchConfig {
                    iterations:a.iterations,depth:a.depth,..Default::default()
                });
                agent.transferred=true;agent.external_model=Some(model);
                agent.world_pool=3;agent.cpuct=0.4;agent.fpu_reduction=0.02965;
                agent.uniform_prior=0.0;agent.capture_search_targets=true;agent
            });
            let mut state=GameState::new(2,setup).unwrap();
            let mut legal=ActionSet::new();
            let mut samples=Vec::new();
            let mut actions=Vec::new();
            let mut sampled_full=0usize;
            for decision in 0..a.max_decisions {
                state.legal_actions(&mut legal);
                if state.outcome().is_some() || legal.is_empty() {break;}
                let seat=state.current_player();
                let o=state.observe(seat);
                let full=curriculum.next_u64() as f64/(u64::MAX as f64)<a.full_probability;
                agents[seat].set_search_iterations(if full {a.iterations} else {a.cheap_iterations});
                let mut chosen=agents[seat].select_action(&o,&legal);
                if o.phase==Phase::Main && o.turns<124 {
                    let targets=agents[seat].search_targets.as_ref();
                    if o.turns<a.stochastic_turns && let Some(t)=targets {
                        let total:u32=t.visits.iter().sum();
                        let mut draw=curriculum.index(total as usize);
                        for &action in &legal {
                            let n=t.visits[action_index(action).unwrap()] as usize;
                            if draw<n {chosen=action;break;}
                            draw-=n;
                        }
                    }
                    let mut mask=[0f32;81];let mut visits=[0u32;81];let mut q=[f32::NAN;81];
                    for &action in &legal {
                        let i=action_index(action).unwrap();let j=native_ids[i] as usize;
                        mask[j]=1.0;
                        if let Some(t)=targets {visits[j]=t.visits[i];q[j]=t.q[i].unwrap_or(f32::NAN);}
                    }
                    let x=transfer::encode(&o,&mut encoder);
                    let context=transfer::public_context(&o);
                    let mut bytes=Vec::with_capacity(ROW_BYTES);
                    bytes.extend(setup.to_le_bytes());bytes.extend((decision as u32).to_le_bytes());
                    bytes.push(seat as u8);bytes.push(u8::from(full && targets.is_some()));bytes.extend([0;2]);
                    for v in x.into_iter().chain(context).chain(mask) {bytes.extend(v.to_le_bytes());}
                    for n in visits {bytes.extend(n.to_le_bytes());}
                    for v in q {bytes.extend(v.to_le_bytes());}
                    bytes.extend(targets.map_or(f32::NAN,|t|t.root_value).to_le_bytes());
                    bytes.extend(targets.map_or(f32::NAN,|t|t.network_value).to_le_bytes());
                    bytes.extend((native_ids[action_index(chosen).unwrap()] as u16).to_le_bytes());bytes.extend([0;2]);
                    bytes.extend(f32::NAN.to_le_bytes());assert_eq!(bytes.len(),ROW_BYTES);
                    sampled_full+=usize::from(full && targets.is_some());
                    samples.push((seat,bytes));
                }
                state.apply_action(chosen).unwrap();state.check_invariants().unwrap();
                actions.push(encode(chosen));
            }
            state.legal_actions(&mut legal);
            let outcome=state.outcome();
            let status=if outcome.is_some() {0} else if legal.is_empty() {1} else {2};
            let h=History {format:1,engine:ENGINE_VERSION.into(),players:2,seed:setup,actions,state_debug:format!("{state:?}")};
            assert_eq!(format!("{:?}",replay(&h).unwrap()),format!("{state:?}"));
            let mut bytes=Vec::with_capacity(samples.len()*ROW_BYTES);
            for (seat,mut row) in samples {
                let credit=outcome.map(|r|if r.winners&(1<<seat)!=0 {1.0/r.winners.count_ones() as f32} else {0.0}).unwrap_or(f32::NAN);
                row[ROW_BYTES-4..].copy_from_slice(&credit.to_le_bytes());bytes.extend(row);
            }
            let work=agents.iter().map(Agent::work_counts).fold((0,0),|(s,c),(x,y)|(s+x,c+y));
            let record=serde_json::json!({"game":g,"status":(["complete","no_legal_action","decision_limit"][status]),"winners":outcome.map_or(0,|r|r.winners),"history":h,"rows":bytes.len()/ROW_BYTES,"full_rows":sampled_full,"simulations":work.0,"inferences":work.1});
            (status,bytes,record,sampled_full,work)
        }).collect());
        for (status, bytes, record, n, work) in results {
            counts[status] += 1;
            rows += bytes.len() / ROW_BYTES;
            full_rows += n;
            simulations += work.0;
            inferences += work.1;
            data.write_all(&bytes)?;
            serde_json::to_writer(&mut history_out, &record)?;
            history_out.write_all(b"\n")?;
        }
        data.flush()?;
        history_out.flush()?;
        println!(
            "{}",
            serde_json::json!({"games":counts.iter().sum::<usize>(),"counts":counts,"rows":rows,"full_rows":full_rows,"seconds":start.elapsed().as_secs_f64()})
        );
    }
    data.flush()?;
    history_out.flush()?;
    std::fs::rename(a.output.join("rows.bin.partial"), a.output.join("rows.bin"))?;
    std::fs::rename(
        a.output.join("histories.jsonl.partial"),
        a.output.join("histories.jsonl"),
    )?;
    std::fs::write(
        a.output.join("complete.json"),
        serde_json::to_vec_pretty(
            &serde_json::json!({"games":a.games,"counts":counts,"rows":rows,"full_rows":full_rows,"row_bytes":ROW_BYTES,"seed":a.seed,"policy_seed":a.policy_seed,"iterations":a.iterations,"cheap_iterations":a.cheap_iterations,"full_probability":a.full_probability,"stochastic_turns":a.stochastic_turns,"threads":a.threads,"depth":a.depth,"world_pool":3,"seconds":start.elapsed().as_secs_f64(),"simulations":simulations,"inferences":inferences,"all_games_replayed":true,"engine":ENGINE_VERSION}),
        )?,
    )?;
    Ok(())
}

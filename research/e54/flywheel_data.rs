//! Sharded self-play supervision. Inputs come only from the acting Observation.
use clap::Parser;
use rayon::prelude::*;
use splendor_agents::{SearchConfig, make_agent, neural::action_index, transfer};
use splendor_core::{ActionSet, GameState, Phase, Rng};
use std::{
    io::{BufWriter, Write},
    path::PathBuf,
    time::Instant,
};
#[derive(Parser)]
struct Args {
    #[arg(long)]
    games: usize,
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    policy_seed: u64,
    #[arg(long, default_value_t = 128)]
    iterations: u32,
    #[arg(long, default_value_t = 16)]
    depth: u32,
    #[arg(long, default_value_t = 4)]
    threads: usize,
    #[arg(long, default_value_t = 1)]
    encoding_views: usize,
    #[arg(long)]
    output: PathBuf,
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a = Args::parse();
    assert!(a.games > 0 && a.threads > 0);
    assert!(matches!(a.encoding_views, 1 | 8));
    let native_ids = transfer::policy_logits(&std::array::from_fn(|i| i as f32));
    let start = Instant::now();
    let tmp = a.output.with_extension("bin.partial");
    let mut out = BufWriter::new(std::fs::File::create(&tmp)?);
    let views_tmp = a.output.with_extension("views.bin.partial");
    let mut views_out = if a.encoding_views == 8 {
        Some(BufWriter::new(std::fs::File::create(&views_tmp)?))
    } else {
        None
    };
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(a.threads)
        .build()?;
    let mut counts = [0usize; 3];
    let mut rows = 0usize;
    let mut simulations = 0u64;
    let mut inference_calls = 0u64;
    let mut records = Vec::new();
    for batch in (0..a.games).step_by(64) {
        let results: Vec<_>=pool.install(|| (batch..(batch+64).min(a.games)).into_par_iter().map(|g| {
            let setup=Rng::new(a.seed.wrapping_add(g as u64)).next_u64();
            let mut prng=Rng::new(a.policy_seed.wrapping_add(g as u64));
            let config=SearchConfig {iterations:a.iterations,depth:a.depth,..Default::default()};
            let mut agents=[make_agent("flywheel-best",prng.next_u64(),&config).unwrap(),make_agent("flywheel-best",prng.next_u64(),&config).unwrap()];
            let mut encoder=Rng::new(prng.next_u64());
            let mut exploration=Rng::new(prng.next_u64());
            let mut view_encoder=Rng::new(prng.next_u64());
            let mut view_groups=Vec::new();
            let mut blind_rows=0usize;
            let mut state=GameState::new(2,setup).unwrap();
            let mut legal=ActionSet::new();
            let mut samples=Vec::new();
            for _ in 0..2000 {
                state.legal_actions(&mut legal);
                if legal.is_empty() {break;}
                let seat=state.current_player();
                let o=state.observe(seat);
                let mut chosen=agents[seat].select_action(&o,&legal);
                if o.phase==Phase::Main && o.turns<124 {
                    let policy=agents[seat].policy_target().unwrap_or_else(|| {let mut p=[0.0;67];p[action_index(chosen).unwrap()]=1.0;p});
                    let value=agents[seat].value_target().unwrap_or(f32::NAN);
                    let mut mask=[0f32;81];
                    let mut target=[0f32;81];
                    for &action in &legal {
                        let i=action_index(action).unwrap();
                        assert!(native_ids[i]>=0.0);
                        let j=native_ids[i] as usize;
                        mask[j]=1.0;target[j]=policy[i];
                    }
                    if o.turns<6 {
                        let total: f64=legal.iter().map(|&action| f64::from(policy[action_index(action).unwrap()])).sum();
                        let mut draw=exploration.next_u64() as f64/u64::MAX as f64*total;
                        for &action in &legal {
                            draw-=f64::from(policy[action_index(action).unwrap()]);
                            if draw<=0.0 {chosen=action;break;}
                        }
                    }
                    let x=transfer::encode(&o,&mut encoder);
                    let opponent=1-seat;
                    let blind=o.players[opponent].reserved.iter().take(o.reserved_counts[opponent] as usize).any(|r| !r.public);
                    if blind {
                        blind_rows+=1;
                        if a.encoding_views==8 {
                            let alternatives:Vec<_>=(1..8).map(|_| transfer::encode(&o,&mut view_encoder)).collect();
                            view_groups.push((samples.len(),alternatives));
                        }
                    }
                    samples.push((seat,x,mask,target,value));
                }
                state.apply_action(chosen).unwrap();
            }
            state.legal_actions(&mut legal);
            let result=state.outcome();
            let status=if result.is_some() {0} else if legal.is_empty() {1} else {2};
            let mut bytes=Vec::with_capacity(samples.len()*2232);
            for (seat,x,mask,policy,value) in samples {
                let outcome=result.map(|r| if r.winners&(1<<seat)!=0 {1.0/r.winners.count_ones() as f32} else {0.0}).unwrap_or(f32::NAN);
                bytes.extend(setup.to_le_bytes());
                for v in x.into_iter().chain(mask).chain(policy).chain([value,outcome]) {bytes.extend(v.to_le_bytes());}
            }
            let (s0,c0)=agents[0].work_counts();let (s1,c1)=agents[1].work_counts();
            let record=serde_json::json!({"setup":setup,"status":(["complete","blocked","capped"][status]),"turns":state.turns(),"rows":bytes.len()/2232,"opponent_blind_rows":blind_rows});
            (status,bytes,s0+s1,c0+c1,record,view_groups)
        }).collect());
        for (status, bytes, s, c, record, view_groups) in results {
            if let Some(writer) = views_out.as_mut() {
                for (index, alternatives) in view_groups {
                    writer.write_all(&((rows + index) as u64).to_le_bytes())?;
                    for x in alternatives {
                        for v in x {
                            writer.write_all(&v.to_le_bytes())?;
                        }
                    }
                }
            }
            counts[status] += 1;
            rows += bytes.len() / 2232;
            simulations += s;
            inference_calls += c;
            records.push(record);
            out.write_all(&bytes)?;
        }
        out.flush()?;
        eprintln!(
            "{}",
            serde_json::json!({"games_finished":counts.iter().sum::<usize>(),"rows":rows,"seconds":start.elapsed().as_secs_f64()})
        );
    }
    out.flush()?;
    drop(out);
    std::fs::rename(tmp, &a.output)?;
    if let Some(mut writer) = views_out {
        writer.flush()?;
        drop(writer);
        std::fs::rename(views_tmp, a.output.with_extension("views.bin"))?;
    }
    let manifest = serde_json::json!({"schema":"flywheel-v1","encoding_views":a.encoding_views,"views_format":"u64 base-row index; f32[7][392]; only opponent-blind rows; base labels unchanged","row_bytes":2232,"format":"u64 setup; f32[392] actor observation encoding; f32[81] native legal mask; f32[81] root visits; f32 teacher credit; f32 terminal credit (NaN if incomplete)","games":a.games,"complete":counts[0],"blocked":counts[1],"capped":counts[2],"rows":rows,"seed":a.seed,"policy_seed":a.policy_seed,"iterations":a.iterations,"depth":a.depth,"threads":a.threads,"temperature_total_turns":6,"seconds":start.elapsed().as_secs_f64(),"simulations":simulations,"inference_calls":inference_calls,"source":env!("SPLENDOR_SOURCE_ID"),"records":records});
    std::fs::write(
        a.output.with_extension("json"),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    println!(
        "{}",
        serde_json::json!({"output":a.output,"rows":rows,"seconds":start.elapsed().as_secs_f64()})
    );
    Ok(())
}

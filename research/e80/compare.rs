use splendor_agents::{make_agent,SearchConfig,neural::action_index};
use splendor_core::{GameState,ActionSet,Phase,Rng};
use rayon::prelude::*;
use std::time::Instant;
fn main(){
 let start=Instant::now();let config=SearchConfig{iterations:800,depth:16,..Default::default()};
 let pool=rayon::ThreadPoolBuilder::new().num_threads(14).build().unwrap();
 let mut stream=Rng::new(4530000000);let setups:Vec<_>=(0..1000).map(|_|stream.next_u64()).collect();
 let rows=pool.install(||setups.par_iter().enumerate().flat_map_iter(|(block,&setup)|{
  let config=&config;
  [0usize,1].into_iter().map(move |rotation|{
   let mut s=GameState::new(2,setup).unwrap();let mut agents=[make_agent("flywheel-gumbel",4531000000+block as u64*2,&config).unwrap(),make_agent("flywheel-gumbel",4531000001+block as u64*2,&config).unwrap()];
   let mut legal=ActionSet::new();let mut count=0;let mut agreement=0;let mut mass=0.;let mut blocked=false;
   for _ in 0..20000 {
    if s.is_terminal(){break} s.legal_actions(&mut legal);if legal.is_empty(){blocked=true;break}
    let seat=s.current_player();let o=s.observe(seat);let agent=&mut agents[seat];let chosen=agent.select_action(&o,&legal);let mut action=chosen;
    if o.phase==Phase::Main {if let Some(p)=agent.policy_target(){
      let target=*legal.iter().filter(|a|action_index(**a).is_some()).max_by(|a,b|p[action_index(**a).unwrap()].total_cmp(&p[action_index(**b).unwrap()])).unwrap();
      count+=1;agreement+=u64::from(target==chosen);mass+=f64::from(p[action_index(chosen).unwrap()]);
      if seat==rotation {action=target;}
    }}
    s.apply_action(action).unwrap();
   }
   let outcome=s.outcome();let credit=outcome.map(|o|if o.winners & (1<<rotation)!=0{1./f64::from(o.winners.count_ones())}else{0.});
   serde_json::json!({"block":block,"rotation":rotation,"setup":setup,"status":if outcome.is_some(){"complete"}else if blocked{"blocked"}else{"capped"},"policy_argmax_credit":credit,"turns":s.turns(),"teacher_decisions":count,"selected_argmax_agreements":agreement,"selected_target_probability_sum":mass,"simulations":agents.iter().map(|a|a.work_counts().0).sum::<u64>(),"inferences":agents.iter().map(|a|a.work_counts().1).sum::<u64>()})
  })
 }).collect::<Vec<_>>());
 println!("{}",serde_json::json!({"schema":"gumbel-target-execution-v1","games":2000,"blocks":1000,"master":4530000000u64,"iterations":800,"depth":16,"threads":14,"source_id":"frozen library; see build.json","seconds":start.elapsed().as_secs_f64()}));
 for row in rows {println!("{row}");}
}

use splendor_agents::{make_agent,SearchConfig};
use splendor_core::{GameState,ActionSet};
fn main(){
 let config=SearchConfig{iterations:128,depth:16,..Default::default()};let mut decisions=0;
 for seed in 0..16 {
  let mut s=GameState::new(2,4501000000+seed).unwrap();
  let mut base=make_agent("flywheel-gumbel",4502000000+seed,&config).unwrap();
  let mut root=make_agent("flywheel-root-gumbel-candidate",4502000000+seed,&config).unwrap();
  let mut legal=ActionSet::new();
  for _ in 0..512 {if s.is_terminal(){break} s.legal_actions(&mut legal);assert!(!legal.is_empty());let o=s.observe(s.current_player());let a=base.select_action(&o,&legal);let b=root.select_action(&o,&legal);assert_eq!(a,b);assert_eq!(base.policy_target(),root.policy_target());assert_eq!(base.value_target(),root.value_target());assert_eq!(base.work_counts(),root.work_counts());s.apply_action(a).unwrap();decisions+=1;}
  assert!(s.is_terminal());
 }
 println!("{}",serde_json::json!({"games":16,"decisions":decisions,"actions_targets_work_exact":true,"all_complete":true}));
}

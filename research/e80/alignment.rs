use splendor_agents::{make_agent,SearchConfig,neural::action_index};
use splendor_core::{GameState,ActionSet,Action,Phase};
fn main(){
 let config=SearchConfig{iterations:800,depth:16,..Default::default()};let mut rows=Vec::new();
 for stress in [false,true] {for seed in 0..4 {
  let mut s=GameState::new(2,4532000000+seed).unwrap();let mut actor=make_agent("strong",0,&SearchConfig::default()).unwrap();let mut legal=ActionSet::new();let mut captured=0;
  for _ in 0..256 {if s.is_terminal(){break}s.legal_actions(&mut legal);if legal.is_empty(){break}let o=s.observe(s.current_player());
   if o.phase==Phase::Main && o.turns%8==0 && captured<8 {
    for name in ["flywheel-gumbel","flywheel-gumbel-noisy"] {for replicate in 0..4 {
     let mut teacher=make_agent(name,4533000000+seed*64+captured*8+replicate,&config).unwrap();let chosen=teacher.select_action(&o,&legal);
     if let Some(p)=teacher.policy_target(){let argmax=*legal.iter().filter(|a|action_index(**a).is_some()).max_by(|a,b|p[action_index(**a).unwrap()].total_cmp(&p[action_index(**b).unwrap()])).unwrap();rows.push(serde_json::json!({"stress":stress,"game":seed,"turn":o.turns,"observation":format!("{o:?}"),"replicate":replicate,"teacher":name,"selected_index":action_index(chosen),"argmax_index":action_index(argmax),"selected_probability":p[action_index(chosen).unwrap()],"policy":p.as_slice()}));}
    }}captured+=1;
   }
   let action=if stress && o.phase==Phase::Main && o.turns<6 {legal.iter().copied().find(|a|matches!(a,Action::ReserveDeck(_))).unwrap_or_else(||actor.select_action(&o,&legal))}else{actor.select_action(&o,&legal)};s.apply_action(action).unwrap();
  }
 }}
 for row in rows {println!("{row}");}
}

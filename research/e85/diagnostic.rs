use splendor_agents::{belief,transfer,make_agent,SearchConfig};
use splendor_core::{GameState,ActionSet,Phase,Rng,Action};
fn main(){
 let mut legal=ActionSet::new();
 for stress in [false,true] { for seed in 0..4 {
 let mut state=GameState::new(2,4640000000+seed).unwrap();
 let mut actor=make_agent("strong",0,&SearchConfig::default()).unwrap();
 for _ in 0..128 {
 if state.is_terminal(){break;} state.legal_actions(&mut legal);if legal.is_empty(){break;}
 let o=state.observe(state.current_player());
 if o.phase==Phase::Main && o.turns<124 {
 let context=transfer::public_context(&o);
 for sample in 0..8 {let x=transfer::encode(&o,&mut Rng::new(4650000000+sample));let (mean,features)=belief::moments(&x,&context);
 println!("{}",serde_json::json!({"stress":stress,"seed":seed,"turn":o.turns,"sample":sample,"x":x.as_slice(),"context":context,"mean":mean.as_slice(),"features":features.as_slice()}));}
 }
 let a=if stress && o.phase==Phase::Main && o.turns<6 {legal.iter().copied().find(|a|matches!(a,Action::ReserveDeck(t) if u32::from(*t)==o.turns/2)).unwrap_or_else(||actor.select_action(&o,&legal))}else{actor.select_action(&o,&legal)};
 state.apply_action(a).unwrap();
 }
 }}
}

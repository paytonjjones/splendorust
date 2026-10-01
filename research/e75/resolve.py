from pathlib import Path
import re
p=Path('crates/splendor-agents/src/neural_search.rs');s=p.read_text()
s=re.sub(r'<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> 9c354b6 \(Add shared search environments for native AlphaZero rules\)\n',lambda m:m[1],s,flags=re.S)
s=s.replace('    fn simulate(\n','    fn simulate_environment<E: crate::environment::Environment>(\n')
s=s.replace('impl Node {','const SEARCH_ACTION_CAPACITY: usize = 81;\nimpl<A> Node<A> {')
start=s.index('impl<A> Node<A> {');end=s.index('pub struct NeuralAgent {',start);s=s[:start]+s[start:end].replace('ACTIONS','SEARCH_ACTION_CAPACITY')+s[end:]
start=s.index('    fn gumbel_root(');end=s.index('    fn simulate_environment',start);part=s[start:end]
for a,b in [('fn gumbel_root(','fn gumbel_root<E: crate::environment::Environment>('),('o: &Observation','o: &E::Observation'),('Vec<Node>','Vec<Node<E::Action>>'),('HashMap<[u8; 192], usize>','HashMap<E::Key, usize>'),('worlds: &[GameState]','worlds: &[E::State]'),(') -> usize {',') -> usize\n    where Self: crate::environment::PolicyValue<E>,\n    {'),('[0.0; ACTIONS]','[0.0; SEARCH_ACTION_CAPACITY]'),('o.determinize(&mut self.rng).expect("valid observation")','E::determinize(o, &mut self.rng)'),('state.current_player()','E::current(&state)'),('state.turns()','E::turns(&state)'),('state.apply_action(nodes[root].edges[edge].action).unwrap();','E::apply(&mut state,nodes[root].edges[edge].action,&mut self.rng);'),('self.simulate(&mut state, depth, nodes, index)','self.simulate_environment::<E>(&mut state, depth, nodes, index)')]:part=part.replace(a,b)
s=s[:start]+part+s[end:]
s=s.replace('self.simulate(&mut state, self.config.depth.max(1), &mut nodes, &mut index)','self.simulate_environment::<crate::environment::Canonical>(&mut state, self.config.depth.max(1), &mut nodes, &mut index)').replace('self.gumbel_root(o, root, &mut nodes, &mut index, &worlds)','self.gumbel_root::<crate::environment::Canonical>(o, root, &mut nodes, &mut index, &worlds)')
start=s.index('    pub fn select_environment');end=s.index('pub(super) fn key',start);part=s[start:end];mark='        for simulation in 0..self.config.iterations {'
part=part.replace(mark,'''        if self.gumbel {
            let selected=self.gumbel_root::<E>(o,0,&mut nodes,&mut index,&worlds);
            return nodes[0].edges[selected].action;
        }
'''+mark,1);s=s[:start]+part+s[end:]
old='''        let (policy, values) = self
            .external_model
            .expect("native environment requires frozen model")
            .infer(&x);'''
new='''        let model=self.external_model.expect("native environment requires frozen model");
        let (policy,values)=if model.needs_public_context() {
            let opponent=1-usize::from(o.current);let mut context=[0.0;7];
            for slot in 0..usize::from(o.players[opponent].reserved_count) {
                let r=o.players[opponent].reserved[slot];
                context[slot]=f32::from(!r.public);context[slot+3]=f32::from(r.tier+1)/3.0;context[6]+=context[slot]/3.0;
            }
            model.infer_with_context(&x,&context)
        } else {model.infer(&x)};'''
assert old in s;s=s.replace(old,new);p.write_text(s)

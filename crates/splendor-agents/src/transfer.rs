//! Native inference for the upstream version-80 network.
//! Architecture copyright (c) 2018 Surag Nair (MIT).
//! See research/e30/UPSTREAM-LICENSE. No game-state input is accepted here.
mod attention;
mod entity;
mod large;
mod remote;
struct Reader {
    values: Vec<f32>,
    at: usize,
}
impl Reader {
    fn take(&mut self, n: usize) -> Vec<f32> {
        let result = self.values[self.at..self.at + n].to_vec();
        self.at += n;
        result
    }
    fn dense(&mut self, input: usize, output: usize) -> Dense {
        Dense {
            weights: self.take(input * output),
            bias: self.take(output),
            input,
        }
    }
    fn norm(&mut self, input: usize, output: usize, channels: usize, depthwise: bool) -> Norm {
        let weights = self.take(input * output);
        // Four output channels share each vector load. Each output retains
        // the original input-channel FMA order. Packing is done once per model.
        let packed = if depthwise {
            Vec::new()
        } else {
            assert!(output.is_multiple_of(4));
            (0..output / 4)
                .flat_map(|g| {
                    (0..input).map({
                        let weights = &weights;
                        move |i| std::array::from_fn(|lane| weights[(g * 4 + lane) * input + i])
                    })
                })
                .collect()
        };
        Norm {
            weights,
            packed,
            scale: self.take(channels),
            bias: self.take(channels),
            input,
            output,
            depthwise,
        }
    }
    fn block(&mut self) -> Block {
        Block {
            expand: self.norm(56, 168, 168, false),
            depthwise: self.norm(7, 7, 168, true),
            squeeze: self.dense(168, 40),
            excite: self.dense(40, 168),
            project: self.norm(168, 56, 56, false),
        }
    }
}
struct Dense {
    weights: Vec<f32>,
    bias: Vec<f32>,
    input: usize,
}
impl Dense {
    fn apply(&self, x: &[f32]) -> Vec<f32> {
        assert_eq!(x.len(), self.input);
        self.weights
            .chunks_exact(self.input)
            .zip(&self.bias)
            .map(|(w, &b)| {
                let mut sums = [0.0; 8];
                let (wc, wr) = w.as_chunks::<8>();
                let (xc, xr) = x.as_chunks::<8>();
                for (w, x) in wc.iter().zip(xc) {
                    for j in 0..8 {
                        sums[j] = w[j].mul_add(x[j], sums[j]);
                    }
                }
                for (j, (&w, &x)) in wr.iter().zip(xr).enumerate() {
                    sums[j] = w.mul_add(x, sums[j]);
                }
                b + sums.iter().sum::<f32>()
            })
            .collect()
    }
}
#[derive(Clone, Copy)]
enum Activation {
    None,
    Relu,
    HardSwish,
}
impl Activation {
    fn apply(self, x: f32) -> f32 {
        match self {
            Self::None => x,
            Self::Relu => x.max(0.0),
            Self::HardSwish => x * (x + 3.0).clamp(0.0, 6.0) / 6.0,
        }
    }
}
struct Norm {
    weights: Vec<f32>,
    packed: Vec<[f32; 4]>,
    scale: Vec<f32>,
    bias: Vec<f32>,
    input: usize,
    output: usize,
    depthwise: bool,
}
impl Norm {
    fn apply(&self, x: &[f32], activation: Activation) -> Vec<f32> {
        if self.depthwise {
            assert_eq!(x.len(), self.scale.len() * self.input);
            let mut y = vec![0.0; self.scale.len() * self.output];
            for (channel, row) in x.chunks_exact(self.input).enumerate() {
                for (feature, weights) in self.weights.chunks_exact(self.input).enumerate() {
                    let sum: f32 = weights
                        .iter()
                        .zip(row)
                        .fold(0.0, |s, (&w, &x)| w.mul_add(x, s));
                    y[channel * self.output + feature] =
                        activation.apply(sum.mul_add(self.scale[channel], self.bias[channel]));
                }
            }
            y
        } else {
            assert_eq!(x.len(), self.input * 7);
            let mut y = vec![0.0; self.output * 7];
            for (channel, weights) in self.weights.chunks_exact(self.input).enumerate() {
                let mut sums = [0.0; 7];
                for (&w, row) in weights.iter().zip(x.as_chunks::<7>().0) {
                    for (j, sum) in sums.iter_mut().enumerate() {
                        *sum = w.mul_add(row[j], *sum);
                    }
                }
                for j in 0..7 {
                    y[channel * 7 + j] =
                        activation.apply(sums[j].mul_add(self.scale[channel], self.bias[channel]));
                }
            }
            y
        }
    }
}
impl Norm {
    fn apply_interleaved(&self, x: &[f32], activation: Activation) -> Vec<f32> {
        if self.depthwise {
            return self.apply(x, activation);
        }
        assert_eq!(x.len(), self.input * 7);
        let mut y = vec![0.0; self.output * 7];
        for (group, weights) in self.packed.chunks_exact(self.input).enumerate() {
            // The four lanes are independent dot products, not a reduction.
            let mut sums = [[0.0; 4]; 7];
            for (w, row) in weights.iter().zip(x.as_chunks::<7>().0) {
                for spatial in 0..7 {
                    for lane in 0..4 {
                        sums[spatial][lane] = w[lane].mul_add(row[spatial], sums[spatial][lane]);
                    }
                }
            }
            for (lane, output) in y[group * 28..group * 28 + 28]
                .as_chunks_mut::<7>()
                .0
                .iter_mut()
                .enumerate()
            {
                let channel = group * 4 + lane;
                for (spatial, value) in output.iter_mut().enumerate() {
                    *value = activation.apply(
                        sums[spatial][lane].mul_add(self.scale[channel], self.bias[channel]),
                    );
                }
            }
        }
        y
    }
}

struct Block {
    expand: Norm,
    depthwise: Norm,
    squeeze: Dense,
    excite: Dense,
    project: Norm,
}
impl Block {
    fn apply_mode(&self, x: &[f32], head: bool, interleaved: bool) -> Vec<f32> {
        let activation = if head {
            Activation::HardSwish
        } else {
            Activation::Relu
        };
        let h = if interleaved {
            self.expand.apply_interleaved(x, activation)
        } else {
            self.expand.apply(x, activation)
        };
        let mut h = self.depthwise.apply(&h, activation);
        let pooled: Vec<f32> = h
            .as_chunks::<7>()
            .0
            .iter()
            .map(|row| {
                if head {
                    row.iter().copied().fold(f32::NEG_INFINITY, f32::max)
                } else {
                    row.iter().sum::<f32>() / 7.0
                }
            })
            .collect();
        let squeezed: Vec<_> = self
            .squeeze
            .apply(&pooled)
            .into_iter()
            .map(|x| x.max(0.0))
            .collect();
        let scales = self.excite.apply(&squeezed);
        for (row, scale) in h.as_chunks_mut::<7>().0.iter_mut().zip(scales) {
            let scale = (scale + 3.0).clamp(0.0, 6.0) / 6.0;
            for x in row {
                *x *= scale;
            }
        }
        let mut y = if interleaved {
            self.project.apply_interleaved(&h, Activation::None)
        } else {
            self.project.apply(&h, Activation::None)
        };
        for (y, x) in y.iter_mut().zip(x) {
            *y += x;
        }
        y
    }
}
struct BootstrapModel {
    first: Norm,
    trunk: Vec<Block>,
    policy_block: Block,
    policy_hidden: Dense,
    policy_output: Dense,
    value_block: Block,
    value_hidden: Dense,
    value_output: Dense,
}
impl BootstrapModel {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let (bytes, depth, inputs) = if bytes.starts_with(b"SPINFO57") {
            assert!(bytes.len() >= 16, "information model header");
            let depth = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
            assert!((1..=8).contains(&depth), "information trunk depth");
            assert_eq!(
                u32::from_le_bytes(bytes[12..16].try_into().unwrap()),
                7,
                "public context fields"
            );
            (&bytes[16..], depth, 57)
        } else if bytes.starts_with(b"SPPUB751") {
            assert!(bytes.len() >= 12, "public model header");
            let depth = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
            assert!((1..=8).contains(&depth), "public trunk depth");
            (&bytes[12..], depth, 75)
        } else if bytes.starts_with(b"SPMOBIL1") {
            assert!(bytes.len() >= 12, "mobile model header");
            let depth = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
            assert!((2..=8).contains(&depth), "mobile trunk depth");
            (&bytes[12..], depth, 56)
        } else {
            (bytes, 1, 56)
        };
        assert_eq!(
            bytes.len(),
            569_624 + 4 * 33297 * (depth - 1) + 4 * 56 * (inputs - 56),
            "version-80 model byte length"
        );
        assert!(
            bytes
                .as_chunks::<4>()
                .0
                .iter()
                .all(|b| f32::from_le_bytes(*b).is_finite()),
            "nonfinite model weights"
        );
        let values = bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| f32::from_le_bytes(*b))
            .collect();
        let mut r = Reader { values, at: 0 };
        let model = Self {
            first: r.norm(inputs, 56, 56, false),
            trunk: (0..depth).map(|_| r.block()).collect(),
            policy_block: r.block(),
            policy_hidden: r.dense(392, 81),
            policy_output: r.dense(81, 81),
            value_block: r.block(),
            value_hidden: r.dense(392, 2),
            value_output: r.dense(2, 2),
        };
        assert_eq!(r.at, r.values.len());
        model
    }
    pub fn infer(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        self.infer_mode(x, false)
    }
    fn infer_mode(&self, x: &[f32; 392], interleaved: bool) -> ([f32; 81], [f32; 2]) {
        let h = self.features(x, interleaved);
        (self.policy(&h, interleaved), self.value(&h, interleaved))
    }
    fn features(&self, x: &[f32], interleaved: bool) -> Vec<f32> {
        let mut h = if interleaved {
            self.first.apply_interleaved(x, Activation::None)
        } else {
            self.first.apply(x, Activation::None)
        };
        for block in &self.trunk {
            h = block.apply_mode(&h, false, interleaved);
        }

        h
    }
    fn policy(&self, h: &[f32], interleaved: bool) -> [f32; 81] {
        let policy = self.policy_block.apply_mode(h, true, interleaved);
        let policy: Vec<_> = self
            .policy_hidden
            .apply(&policy)
            .into_iter()
            .map(|x| x.max(0.0))
            .collect();
        let policy = self.policy_output.apply(&policy);
        policy.try_into().unwrap()
    }
    fn value(&self, h: &[f32], interleaved: bool) -> [f32; 2] {
        let value = self.value_block.apply_mode(h, true, interleaved);
        let value: Vec<_> = self
            .value_hidden
            .apply(&value)
            .into_iter()
            .map(|x| x.max(0.0))
            .collect();
        let value = self
            .value_output
            .apply(&value)
            .into_iter()
            .map(f32::tanh)
            .collect::<Vec<_>>();
        value.try_into().unwrap()
    }
    fn value_raw(&self, h: &[f32], interleaved: bool) -> [f32; 2] {
        let value = self.value_block.apply_mode(h, true, interleaved);
        let value: Vec<_> = self
            .value_hidden
            .apply(&value)
            .into_iter()
            .map(|x| x.max(0.0))
            .collect();
        let value = self
            .value_output
            .apply(&value)
            .into_iter()
            .collect::<Vec<_>>();
        value.try_into().unwrap()
    }
}

/// Tokenize an Entity public input without access to a real hidden world.
pub fn entity_tokens(input: &[f32; 525]) -> Vec<f32> {
    entity::EntityModel::tokens(input)
}

/// Native checkpoint dispatch. Both architectures use the same observation encoder.
pub struct Model {
    architecture: Architecture,
}
/// One public tensor row for an opt-in batched inference wave.
pub struct InferenceRow<'a> {
    pub features: &'a [f32; 392],
    pub context: &'a [f32; 7],
    pub native_rules: bool,
    pub history: &'a [[f32; 32]; 16],
    pub pool: &'a [f32; 90],
}
type EntityBackend = fn(&[f32], usize) -> Vec<([f32; 81], [f32; 2])>;

enum Architecture {
    Entity(entity::EntityModel),
    ExternalEntity(EntityBackend),
    Remote(remote::RemoteModel),
    Large(Box<large::LargeModel>),
    Attention(Box<attention::AttentionModel>),
    Bootstrap(Box<BootstrapModel>),
    Gated(GatedModel),
    Split(Box<SplitModel>),
    Residual(Box<ResidualModel>),
}
struct SplitModel {
    policy: BootstrapModel,
    critic: BootstrapModel,
}
impl SplitModel {
    fn from_bytes(bytes: &[u8]) -> Self {
        assert!(bytes.len() >= 16, "dual model header");
        let policy_len = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        let critic_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let end = 16usize.checked_add(policy_len).unwrap();
        assert_eq!(
            end.checked_add(critic_len).unwrap(),
            bytes.len(),
            "dual payload lengths"
        );
        Self {
            policy: BootstrapModel::from_bytes(&bytes[16..end]),
            critic: BootstrapModel::from_bytes(&bytes[end..]),
        }
    }
    fn infer(&self, x: &[f32; 392], interleaved: bool) -> ([f32; 81], [f32; 2]) {
        let policy_h = self.policy.features(x, interleaved);
        let critic_h = self.critic.features(x, interleaved);
        (
            self.policy.policy(&policy_h, interleaved),
            self.critic.value(&critic_h, interleaved),
        )
    }
}
struct ResidualModel {
    base: BootstrapModel,
    delta: GatedModel,
    public_belief: bool,
}
impl ResidualModel {
    fn from_bytes(bytes: &[u8]) -> Self {
        assert!(bytes.len() >= 16, "residual model header");
        let base_len = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        let delta_len = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let end = 16usize.checked_add(base_len).unwrap();
        assert_eq!(
            end.checked_add(delta_len).unwrap(),
            bytes.len(),
            "residual model lengths"
        );
        let delta = &bytes[end..];
        assert!(
            delta.starts_with(b"SPGATED1")
                || delta.starts_with(b"SPGATED2")
                || delta.starts_with(b"SPGATED3"),
            "residual correction format"
        );
        assert_eq!(
            bytes.starts_with(b"SPBELF01"),
            delta.starts_with(b"SPGATED3"),
            "public correction format"
        );
        Self {
            base: BootstrapModel::from_bytes(&bytes[16..end]),
            delta: GatedModel::from_bytes(delta),
            public_belief: bytes.starts_with(b"SPBELF01"),
        }
    }
    fn infer(&self, x: &[f32; 392], interleaved: bool) -> ([f32; 81], [f32; 2]) {
        assert!(!self.public_belief, "belief model requires public context");
        let h = self.base.features(x, interleaved);
        let mut pi = self.base.policy(&h, interleaved);
        let value = self.base.value_raw(&h, interleaved);
        let (dp, dv) = self.delta.infer_raw(x);
        for (p, d) in pi.iter_mut().zip(dp) {
            *p += d;
        }
        (pi, std::array::from_fn(|i| (value[i] + dv[i]).tanh()))
    }
}
impl Model {
    /// Run the frozen Entity trunk through a host backend. The callback receives
    /// only tokens made from the public observation encoder.
    pub fn with_entity_backend(infer: EntityBackend) -> Self {
        Self {
            architecture: Architecture::ExternalEntity(infer),
        }
    }

    pub fn uses_history_bridge(&self) -> bool {
        matches!(&self.architecture, Architecture::Remote(model) if model.history)
    }
    pub fn uses_full_public_history(&self) -> bool {
        matches!(&self.architecture, Architecture::Remote(model) if model.history_version == 2)
    }
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let architecture = if bytes.starts_with(b"SPREMOTE") {
            Architecture::Remote(remote::RemoteModel::from_bytes(bytes))
        } else if bytes.starts_with(b"SPENTY01") {
            Architecture::Entity(entity::EntityModel::from_bytes(bytes))
        } else if bytes.starts_with(b"SPLARGE1") {
            Architecture::Large(Box::new(large::LargeModel::from_bytes(bytes)))
        } else if bytes.starts_with(b"SPATTN01") {
            Architecture::Attention(Box::new(attention::AttentionModel::from_bytes(bytes)))
        } else if bytes.starts_with(b"SPRESID1") || bytes.starts_with(b"SPBELF01") {
            Architecture::Residual(Box::new(ResidualModel::from_bytes(bytes)))
        } else if bytes.starts_with(b"SPDUAL01") {
            Architecture::Split(Box::new(SplitModel::from_bytes(bytes)))
        } else if bytes.starts_with(b"SPGATED1") || bytes.starts_with(b"SPGATED2") {
            Architecture::Gated(GatedModel::from_bytes(bytes))
        } else {
            Architecture::Bootstrap(Box::new(BootstrapModel::from_bytes(bytes)))
        };
        Self { architecture }
    }
    /// Original deterministic implementation for validation and fallback.
    pub fn infer_original(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        match &self.architecture {
            Architecture::Bootstrap(model) => model.infer(x),
            Architecture::Gated(model) => model.infer(x),
            Architecture::Split(model) => model.infer(x, false),
            Architecture::Residual(model) => model.infer(x, false),
            Architecture::Entity(_)
            | Architecture::ExternalEntity(_)
            | Architecture::Attention(_)
            | Architecture::Remote(_)
            | Architecture::Large(_) => {
                panic!("model requires public context")
            }
        }
    }
    pub fn has_correction(&self) -> bool {
        matches!(
            self.architecture,
            Architecture::Residual(_) | Architecture::Attention(_)
        )
    }
    /// Fast frozen evaluator used below a large root correction.
    pub fn infer_base(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        match &self.architecture {
            Architecture::Residual(model) => model.base.infer_mode(x, true),
            Architecture::Attention(model) => model.base.infer_mode(x, true),
            _ => self.infer(x),
        }
    }
    /// Public models retain native noble slot order, which affects native rules.
    /// Legacy transferred models keep their frozen sorted-noble feature contract.
    pub fn uses_native_noble_order(&self) -> bool {
        matches!(
            &self.architecture,
            Architecture::Remote(_) | Architecture::Large(_)
        ) || matches!(&self.architecture, Architecture::Bootstrap(model) if model.first.input == 75)
    }
    pub fn needs_public_context(&self) -> bool {
        matches!(
            &self.architecture,
            Architecture::Entity(_)
                | Architecture::ExternalEntity(_)
                | Architecture::Attention(_)
                | Architecture::Remote(_)
                | Architecture::Large(_)
        ) || matches!(&self.architecture, Architecture::Bootstrap(model) if matches!(model.first.input, 57 | 75))
            || matches!(&self.architecture, Architecture::Residual(model) if model.public_belief)
    }
    pub fn infer_with_context(&self, x: &[f32; 392], context: &[f32; 7]) -> ([f32; 81], [f32; 2]) {
        self.infer_with_profile(x, context, false)
    }
    /// Public rules identity; no private game information enters this input.
    pub fn infer_with_profile(
        &self,
        x: &[f32; 392],
        context: &[f32; 7],
        native_rules: bool,
    ) -> ([f32; 81], [f32; 2]) {
        if matches!(
            &self.architecture,
            Architecture::Entity(_) | Architecture::ExternalEntity(_)
        ) {
            let (mean, public) = crate::belief::moments(x, context);
            let mut input = [0.0; 525];
            input[..392].copy_from_slice(&mean);
            input[392..519].copy_from_slice(&public[392..]);
            input[519] = f32::from(native_rules);
            return match &self.architecture {
                Architecture::Entity(model) => model.infer(&input),
                Architecture::ExternalEntity(infer) => infer(&entity_tokens(&input), 1).remove(0),
                _ => unreachable!(),
            };
        }
        if let Architecture::Remote(model) = &self.architecture {
            return model.infer(x, context, native_rules, &[[0.0; 32]; 16], &[1.0; 90]);
        }
        if let Architecture::Large(model) = &self.architecture {
            return model.infer(x, context, native_rules);
        }
        if let Architecture::Bootstrap(model) = &self.architecture
            && model.first.input == 75
        {
            let (mean, public) = crate::belief::moments(x, context);
            let mut input = [0.0; 525];
            input[..392].copy_from_slice(&mean);
            input[392..519].copy_from_slice(&public[392..]);
            input[519] = f32::from(native_rules);
            let h = model.features(&input, true);
            return (model.policy(&h, true), model.value(&h, true));
        }
        if let Architecture::Attention(model) = &self.architecture {
            return model.infer(x, context);
        }
        if let Architecture::Residual(model) = &self.architecture
            && model.public_belief
        {
            let (mean, features) = crate::belief::moments(x, context);
            let h = model.base.features(&mean, true);
            let mut pi = model.base.policy(&h, true);
            let value = model.base.value_raw(&h, true);
            let (dp, dv) = model.delta.infer_features(&features);
            for (p, d) in pi.iter_mut().zip(dp) {
                *p += d;
            }
            return (pi, std::array::from_fn(|i| (value[i] + dv[i]).tanh()));
        }
        if let Architecture::Bootstrap(model) = &self.architecture
            && model.first.input == 57
        {
            let mut input = [0.0; 399];
            input[..392].copy_from_slice(x);
            input[392..].copy_from_slice(context);
            let h = model.features(&input, true);
            return (model.policy(&h, true), model.value(&h, true));
        }
        self.infer(x)
    }
    pub fn infer(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        match &self.architecture {
            Architecture::Bootstrap(model) => model.infer_mode(x, true),
            Architecture::Gated(model) => model.infer(x),
            Architecture::Split(model) => model.infer(x, true),
            Architecture::Residual(model) => model.infer(x, true),
            Architecture::Entity(_)
            | Architecture::ExternalEntity(_)
            | Architecture::Attention(_)
            | Architecture::Remote(_)
            | Architecture::Large(_) => {
                panic!("model requires public context")
            }
        }
    }
    /// A bounded sequence of public events; hidden labels are never accepted.
    pub fn infer_with_history(
        &self,
        x: &[f32; 392],
        context: &[f32; 7],
        native_rules: bool,
        history: &[[f32; 32]; 16],
        pool: &[f32; 90],
    ) -> ([f32; 81], [f32; 2]) {
        if let Architecture::Remote(model) = &self.architecture {
            model.infer(x, context, native_rules, history, pool)
        } else {
            self.infer_with_profile(x, context, native_rules)
        }
    }

    /// Evaluate public observation rows together when the model uses the
    /// checkpoint-bound tensor service. Other model formats keep scalar parity.
    pub fn infer_with_history_batch(
        &self,
        inputs: &[InferenceRow<'_>],
    ) -> Vec<([f32; 81], [f32; 2])> {
        if let Architecture::ExternalEntity(infer) = &self.architecture {
            if inputs.is_empty() {
                return Vec::new();
            }
            let mut tokens = Vec::with_capacity(inputs.len() * 31 * 48);
            for row in inputs {
                let (mean, public) = crate::belief::moments(row.features, row.context);
                let mut input = [0.0; 525];
                input[..392].copy_from_slice(&mean);
                input[392..519].copy_from_slice(&public[392..]);
                input[519] = f32::from(row.native_rules);
                tokens.extend_from_slice(&entity_tokens(&input));
            }
            return infer(&tokens, inputs.len());
        }
        if let Architecture::Remote(model) = &self.architecture {
            let rows: Vec<_> = inputs
                .iter()
                .map(|row| remote::Input {
                    x: row.features,
                    context: row.context,
                    native: row.native_rules,
                    history: row.history,
                    pool: row.pool,
                })
                .collect();
            model.infer_batch(&rows)
        } else {
            inputs
                .iter()
                .map(|row| {
                    self.infer_with_history(
                        row.features,
                        row.context,
                        row.native_rules,
                        row.history,
                        row.pool,
                    )
                })
                .collect()
        }
    }
}

struct GatedBlock {
    gain: Vec<f32>,
    gate: Dense,
    up: Dense,
    down: Dense,
}
struct GatedModel {
    stem: Dense,
    bitplanes: bool,
    blocks: Vec<GatedBlock>,
    gain: Vec<f32>,
    head: Dense,
}
fn silu(x: f32) -> f32 {
    x / (1.0 + (-x).exp())
}
fn rms_norm(x: &[f32], gain: &[f32]) -> Vec<f32> {
    let factor = (x.iter().map(|v| v * v).sum::<f32>() / x.len() as f32 + 1e-5)
        .sqrt()
        .recip();
    x.iter().zip(gain).map(|(&v, &g)| v * factor * g).collect()
}
fn gated_features(x: &[f32; 392], bitplanes: bool) -> Vec<f32> {
    let mut features = vec![0.0; if bitplanes { 512 } else { 392 }];
    for (scaled, &value) in features[..392].iter_mut().zip(x) {
        *scaled = value * 0.1;
    }
    features[6] = x[6] / 124.0;
    if bitplanes {
        let mut at = 392;
        for row in [26, 28, 30] {
            for color in 0..5 {
                let index = row * 7 + color;
                let bits = x[index] as i8 as u8;
                features[index] = 0.0;
                for bit in 0..8 {
                    features[at] = f32::from((bits >> bit) & 1);
                    at += 1;
                }
            }
        }
    }
    features
}
impl GatedModel {
    fn from_bytes(bytes: &[u8]) -> Self {
        assert!(bytes.len() >= 16, "gated model header");
        let width = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        let count = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        assert!(
            (32..=512).contains(&width) && width.is_multiple_of(8) && (1..=8).contains(&count),
            "gated model dimensions"
        );
        let bitplanes = bytes.starts_with(b"SPGATED2");
        let inputs = if bytes.starts_with(b"SPGATED3") {
            519
        } else if bitplanes {
            512
        } else {
            392
        };
        let parameters = (inputs + 1) * width
            + count * (3 * width * width + 4 * width)
            + width
            + 83 * width
            + 83;
        assert_eq!(bytes.len(), 16 + 4 * parameters, "gated model byte length");
        let values: Vec<_> = bytes[16..]
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| f32::from_le_bytes(*b))
            .collect();
        assert!(
            values.iter().all(|x| x.is_finite()),
            "nonfinite gated model weights"
        );
        let mut r = Reader { values, at: 0 };
        let stem = r.dense(inputs, width);
        let blocks = (0..count)
            .map(|_| GatedBlock {
                gain: r.take(width),
                gate: r.dense(width, width),
                up: r.dense(width, width),
                down: r.dense(width, width),
            })
            .collect();
        let gain = r.take(width);
        let head = r.dense(width, 83);
        assert_eq!(r.at, r.values.len());
        Self {
            stem,
            bitplanes,
            blocks,
            gain,
            head,
        }
    }
    fn infer(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        let (pi, value) = self.infer_raw(x);
        (pi, value.map(f32::tanh))
    }
    fn infer_raw(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        let features = gated_features(x, self.bitplanes);
        self.infer_features(&features)
    }
    fn infer_features(&self, features: &[f32]) -> ([f32; 81], [f32; 2]) {
        assert_eq!(features.len(), self.stem.input);
        let mut h: Vec<_> = self.stem.apply(features).into_iter().map(silu).collect();
        for b in &self.blocks {
            let n = rms_norm(&h, &b.gain);
            let mut gate = b.gate.apply(&n);
            let up = b.up.apply(&n);
            for (g, u) in gate.iter_mut().zip(up) {
                *g = silu(*g) * u;
            }
            for (v, d) in h.iter_mut().zip(b.down.apply(&gate)) {
                *v += d;
            }
        }
        let y = self.head.apply(&rms_norm(&h, &self.gain));
        (y[..81].try_into().unwrap(), [y[81], y[82]])
    }
}

/// Public reservation metadata omitted by the legacy sampled-world encoding.
pub fn public_context(o: &splendor_core::Observation) -> [f32; 7] {
    assert_eq!(o.count, 2);
    let opponent = 1 - usize::from(o.current);
    let mut context = [0.0; 7];
    for slot in 0..usize::from(o.reserved_counts[opponent]) {
        let r = o.players[opponent].reserved[slot];
        context[slot] = f32::from(!r.public);
        context[slot + 3] = f32::from(r.tier + 1) / 3.0;
        context[6] += context[slot] / 3.0;
    }
    context
}

/// Encode a sampled information set, never a supplied hidden GameState.
/// Canonical player zero is the actual actor. The caller must respect the
/// upstream model's two-player input domain.
pub fn encode(o: &splendor_core::Observation, rng: &mut splendor_core::Rng) -> [f32; 392] {
    use splendor_core::{
        NONE,
        data::{CARDS, NOBLES},
    };
    assert_eq!(o.count, 2);
    assert!(o.turns < 124);
    let world = o.determinize(rng).expect("valid public observation");
    let players: Vec<_> = (0..2)
        .map(|relative| {
            let seat = (usize::from(o.current) + relative) % 2;
            world.observe(seat).players[seat]
        })
        .collect();
    let mut x = [0.0; 392];
    x[..6].copy_from_slice(&o.bank.map(f32::from));
    x[6] = o.turns as f32;
    let card = |x: &mut [f32; 392], row: usize, id: u8| {
        let c = CARDS[id as usize];
        for (color, cost) in c.cost.into_iter().enumerate() {
            x[row * 7 + color] = f32::from(cost);
        }
        x[(row + 1) * 7 + usize::from(c.bonus)] = 1.0;
        x[(row + 1) * 7 + 6] = f32::from(c.points);
    };
    let mut occupied = 0u128;
    for (slot, &id) in o.market.iter().enumerate() {
        if id != NONE {
            card(&mut x, 1 + 2 * slot, id);
            occupied |= 1u128 << id;
        }
    }
    let all_nobles = players.iter().fold(o.nobles, |mask, p| mask | p.nobles);
    let nobles: Vec<_> = (0..10).filter(|id| all_nobles & (1 << id) != 0).collect();
    assert_eq!(nobles.len(), 3);
    for (slot, &id) in nobles.iter().enumerate() {
        let mut write_noble = |row: usize| {
            for (color, cost) in NOBLES[id].into_iter().enumerate() {
                x[row * 7 + color] = f32::from(cost);
            }
            x[row * 7 + 6] = 3.0;
        };
        if o.nobles & (1 << id) != 0 {
            write_noble(31 + slot);
        }
        for (seat, p) in players.iter().enumerate() {
            if p.nobles & (1 << id) != 0 {
                write_noble(36 + 3 * seat + slot);
            }
        }
    }
    for (seat, p) in players.iter().enumerate() {
        occupied |= p.owned;
        for (color, token) in p.tokens.into_iter().enumerate() {
            x[(34 + seat) * 7 + color] = f32::from(token);
        }
        for (color, bonus) in p.bonuses.into_iter().enumerate() {
            x[(42 + seat) * 7 + color] = f32::from(bonus);
        }
        x[(42 + seat) * 7 + 6] = f32::from(p.score) - 3.0 * p.nobles.count_ones() as f32;
        for (slot, reservation) in p.reserved.iter().enumerate() {
            if reservation.card != NONE {
                card(&mut x, 44 + 6 * seat + 2 * slot, reservation.card);
                occupied |= 1u128 << reservation.card;
            }
        }
    }
    let mut bits = [[0u8; 5]; 3];
    for (id, c) in CARDS.iter().enumerate() {
        if occupied & (1u128 << id) == 0 {
            let (tier, color) = (
                usize::from(c.tier),
                usize::from(super::transfer_data::CARD_GROUP[id]),
            );
            x[(25 + 2 * tier) * 7 + color] += 1.0;
            bits[tier][color] |= 128 >> super::transfer_data::CARD_SLOT[id];
        }
    }
    for (tier, colors) in bits.iter().enumerate() {
        for (color, &mask) in colors.iter().enumerate() {
            x[(26 + 2 * tier) * 7 + color] = f32::from(mask as i8);
        }
        assert_eq!(
            (0..5).map(|c| x[(25 + 2 * tier) * 7 + c] as u8).sum::<u8>(),
            o.remaining[tier]
        );
    }
    x
}
/// Translate native logits to the existing 67-action policy indexing.
pub fn policy_logits(native: &[f32; 81]) -> [f32; 67] {
    let mut p = [-1e8; 67];
    for (i, &mask) in super::transfer_data::TAKE_MASKS.iter().enumerate() {
        p[usize::from(mask)] = native[30 + i];
    }
    p[32..37].copy_from_slice(&native[55..60]);
    p[37..49].copy_from_slice(&native[12..24]);
    p[49..52].copy_from_slice(&native[24..27]);
    p[52..64].copy_from_slice(&native[..12]);
    p[64..67].copy_from_slice(&native[27..30]);
    p
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Agent, SearchConfig, StrongHeuristicAgent, make_agent};
    use splendor_core::{ActionSet, GameState, Rng};
    fn small_gated_bytes() -> Vec<u8> {
        let width = 32usize;
        let parameters = 393 * width + 3 * width * width + 4 * width + width + 83 * width + 83;
        let mut bytes = b"SPGATED1".to_vec();
        bytes.extend_from_slice(&(width as u32).to_le_bytes());
        bytes.extend_from_slice(&1u32.to_le_bytes());
        bytes.resize(16 + parameters * 4, 0);
        // Zero matrices make all outputs equal to the last layer's bias.
        for (index, bias) in [2.0f32, -1.0, 0.5].into_iter().enumerate() {
            let at = bytes.len() - 12 + index * 4;
            bytes[at..at + 4].copy_from_slice(&bias.to_le_bytes());
        }
        bytes
    }
    #[test]
    fn gated_checkpoint_output_bias_and_validation() {
        let bytes = small_gated_bytes();
        let model = Model::from_bytes(&bytes);
        let (p, v) = model.infer(&[1.0; 392]);
        assert_eq!(p[80], 2.0);
        assert_eq!(v, [(-1.0f32).tanh(), 0.5f32.tanh()]);
        for length in [8, 15, 16, bytes.len() - 1, bytes.len() - 4] {
            assert!(std::panic::catch_unwind(|| Model::from_bytes(&bytes[..length])).is_err());
        }
        let mut nonfinite = bytes.clone();
        nonfinite[16..20].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&nonfinite)).is_err());
        let mut invalid = bytes.clone();
        invalid[8..12].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        invalid[8..12].copy_from_slice(&32u32.to_le_bytes());
        invalid[12..16].copy_from_slice(&0u32.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
    }
    #[test]
    fn gated_bitplanes_preserve_signed_byte_semantics() {
        let mut x = [0.0; 392];
        x[6] = 62.0;
        x[26 * 7] = -128.0;
        x[26 * 7 + 1] = 127.0;
        x[30 * 7 + 4] = -1.0;
        let f = gated_features(&x, true);
        assert_eq!(f.len(), 512);
        assert_eq!(f[6], 0.5);
        assert_eq!(&f[392..400], &[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]);
        assert_eq!(&f[400..408], &[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0]);
        assert_eq!(&f[504..512], &[1.0; 8]);
        assert_eq!(f[26 * 7], 0.0);
        let width = 32usize;
        let parameters = 513 * width + 3 * width * width + 4 * width + width + 83 * width + 83;
        let mut bytes = b"SPGATED2".to_vec();
        bytes.extend_from_slice(&(width as u32).to_le_bytes());
        bytes.extend_from_slice(&1u32.to_le_bytes());
        bytes.resize(16 + parameters * 4, 0);
        let (p, v) = Model::from_bytes(&bytes).infer(&x);
        assert_eq!(p, [0.0; 81]);
        assert_eq!(v, [0.0; 2]);
        bytes.pop();
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bytes)).is_err());
    }
    #[test]
    fn deeper_identity_trunk_preserves_bootstrap_and_checks_header() {
        let original = include_bytes!("models/e30.bin");
        let split = 4 * (56 * 56 + 2 * 56 + 33297);
        let mut bytes = b"SPMOBIL1".to_vec();
        bytes.extend_from_slice(&3u32.to_le_bytes());
        bytes.extend_from_slice(&original[..split]);
        bytes.resize(bytes.len() + 2 * 4 * 33297, 0);
        bytes.extend_from_slice(&original[split..]);
        let before = Model::from_bytes(original);
        let after = Model::from_bytes(&bytes);
        for seed in [0, 1, 1190000007] {
            let state = GameState::new(2, seed).unwrap();
            let x = encode(&state.observe(0), &mut Rng::new(17));
            assert_eq!(before.infer(&x), after.infer(&x));
        }
        for depth in [0u32, 1, 9, u32::MAX] {
            let mut invalid = bytes.clone();
            invalid[8..12].copy_from_slice(&depth.to_le_bytes());
            assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        }
        bytes.pop();
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bytes)).is_err());
    }
    #[test]
    fn interleaved_kernel_matches_reference_bits_on_real_observations() {
        let original = include_bytes!("models/e30.bin");
        let first = (56 * 56 + 56 * 2) * 4;
        let block = 33297 * 4;
        let mut deeper = b"SPMOBIL1".to_vec();
        deeper.extend_from_slice(&3u32.to_le_bytes());
        deeper.extend_from_slice(&original[..first + block]);
        deeper.extend_from_slice(&original[first..first + block]);
        deeper.extend_from_slice(&original[first..first + block]);
        deeper.extend_from_slice(&original[first + block..]);
        let models = [
            Model::from_bytes(original),
            Model::from_bytes(&deeper),
            Model::from_bytes(&small_gated_bytes()),
        ];
        let mut inputs = 0;
        for seed in 0..16 {
            let mut state = GameState::new(2, 2_200_000_000 + seed).unwrap();
            let mut rng = Rng::new(seed);
            let mut legal = ActionSet::new();
            for _ in 0..200 {
                if state.is_terminal() || state.turns() >= 124 {
                    break;
                }
                state.legal_actions(&mut legal);
                if legal.is_empty() {
                    break;
                }
                let observation = state.observe(state.current_player());
                let x = encode(&observation, &mut rng);
                for model in &models {
                    let before = model.infer_original(&x);
                    let after = model.infer(&x);
                    for (a, b) in before
                        .0
                        .iter()
                        .chain(&before.1)
                        .zip(after.0.iter().chain(&after.1))
                    {
                        assert_eq!(a.to_bits(), b.to_bits(), "seed {seed}, input {inputs}");
                    }
                }
                inputs += 1;
                state
                    .apply_action(StrongHeuristicAgent.select_action(&observation, &legal))
                    .unwrap();
            }
        }
        assert!(inputs > 1000);
    }
    #[test]
    fn split_model_keeps_critic_independent_and_checks_payloads() {
        let original = include_bytes!("models/e30.bin");
        let mut policy = original.to_vec();
        // Change policy features too: using them for the critic must fail this test.
        let feature_bias_at = 4 * (56 * 56 + 56);
        let feature_bias = f32::from_le_bytes(
            policy[feature_bias_at..feature_bias_at + 4]
                .try_into()
                .unwrap(),
        );
        policy[feature_bias_at..feature_bias_at + 4]
            .copy_from_slice(&(feature_bias + 2.0).to_le_bytes());
        let bias_at = policy.len() - 136356 - 4;
        let bias = f32::from_le_bytes(policy[bias_at..bias_at + 4].try_into().unwrap());
        policy[bias_at..bias_at + 4].copy_from_slice(&(bias + 0.5).to_le_bytes());
        let mut bytes = b"SPDUAL01".to_vec();
        bytes.extend_from_slice(&(policy.len() as u32).to_le_bytes());
        bytes.extend_from_slice(&(original.len() as u32).to_le_bytes());
        bytes.extend_from_slice(&policy);
        bytes.extend_from_slice(original);
        let dual = Model::from_bytes(&bytes);
        let expected_policy = Model::from_bytes(&policy);
        let expected_value = Model::from_bytes(original);
        let mut values_differ = false;
        for seed in 0..32 {
            let state = GameState::new(2, seed).unwrap();
            let x = encode(&state.observe(0), &mut Rng::new(seed + 9));
            let actual = dual.infer(&x);
            assert_eq!(actual.0, expected_policy.infer(&x).0);
            assert_eq!(actual.1, expected_value.infer(&x).1);
            assert_eq!(actual, dual.infer_original(&x));
            values_differ |= expected_policy.infer(&x).1 != expected_value.infer(&x).1;
        }
        assert!(
            values_differ,
            "policy features must differ from frozen critic features"
        );
        let mut invalid = bytes.clone();
        invalid[8..12].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        invalid = bytes.clone();
        invalid.pop();
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        invalid = bytes;
        invalid[16..20].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(b"SPDUAL01")).is_err());
    }
    #[test]
    fn residual_identity_corrections_and_payload_checks() {
        let base = include_bytes!("models/e30.bin");
        let mut delta = small_gated_bytes();
        let head = delta.len() - 4 * (83 * 32 + 83);
        delta[head..].fill(0);
        let wrap = |d: &[u8]| {
            let mut b = b"SPRESID1".to_vec();
            b.extend_from_slice(&(base.len() as u32).to_le_bytes());
            b.extend_from_slice(&(d.len() as u32).to_le_bytes());
            b.extend_from_slice(base);
            b.extend_from_slice(d);
            b
        };
        let identity = Model::from_bytes(&wrap(&delta));
        let original = Model::from_bytes(base);
        let raw_base = BootstrapModel::from_bytes(base);
        for seed in 0..32 {
            let state = GameState::new(2, seed).unwrap();
            let x = encode(&state.observe(0), &mut Rng::new(seed + 31));
            let before = original.infer(&x);
            let after = identity.infer(&x);
            for (a, b) in before
                .0
                .into_iter()
                .chain(before.1)
                .zip(after.0.into_iter().chain(after.1))
            {
                assert_eq!(a.to_bits(), b.to_bits());
            }
            assert_eq!(after, identity.infer_original(&x));
        }
        let bias = delta.len() - 4 * 83;
        delta[bias + 7 * 4..bias + 8 * 4].copy_from_slice(&(-0.5f32).to_le_bytes());
        delta[bias + 81 * 4..bias + 82 * 4].copy_from_slice(&0.25f32.to_le_bytes());
        delta[bias + 82 * 4..bias + 83 * 4].copy_from_slice(&(-0.15f32).to_le_bytes());
        let corrected_bytes = wrap(&delta);
        let corrected = Model::from_bytes(&corrected_bytes);
        let state = GameState::new(2, 3610000000).unwrap();
        let x = encode(&state.observe(0), &mut Rng::new(17));
        let mut expected = original.infer(&x);
        expected.0[7] -= 0.5;
        let value = raw_base.value_raw(&raw_base.features(&x, true), true);
        expected.1 = [(value[0] + 0.25).tanh(), (value[1] - 0.15).tanh()];
        assert_eq!(corrected.infer(&x), expected);
        for offset in [8, 12] {
            let mut invalid = corrected_bytes.clone();
            invalid[offset..offset + 4].copy_from_slice(&u32::MAX.to_le_bytes());
            assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        }
        let mut invalid = corrected_bytes.clone();
        invalid.pop();
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        for offset in [16, 16 + base.len() + 16] {
            let mut invalid = corrected_bytes.clone();
            invalid[offset..offset + 4].copy_from_slice(&f32::NAN.to_le_bytes());
            assert!(std::panic::catch_unwind(|| Model::from_bytes(&invalid)).is_err());
        }
        assert!(std::panic::catch_unwind(|| Model::from_bytes(b"SPRESID1")).is_err());
    }
    #[test]
    fn bootstrap_dispatch_preserves_exact_inference() {
        let bytes = include_bytes!("models/e30.bin");
        let baseline = BootstrapModel::from_bytes(bytes);
        let dispatched = Model::from_bytes(bytes);
        for seed in [0, 1, 1160000007] {
            let state = GameState::new(2, seed).unwrap();
            let x = encode(&state.observe(0), &mut Rng::new(17));
            assert_eq!(baseline.infer(&x), dispatched.infer(&x));
        }
    }
    #[test]
    fn translated_main_logits_cover_exactly_native_main_actions() {
        let native = std::array::from_fn(|i| i as f32);
        let mut mapped: Vec<_> = policy_logits(&native)
            .into_iter()
            .filter(|&x| x >= 0.0)
            .map(|x| x as u8)
            .collect();
        mapped.sort();
        assert_eq!(mapped, (0..60).collect::<Vec<u8>>());
    }
    #[test]
    fn transferred_search_has_no_hidden_world_access_and_handles_late_turns() {
        let mut state = GameState::new(2, 619000007).unwrap();
        state
            .apply_action(splendor_core::Action::ReserveDeck(0))
            .unwrap();
        let o = state.observe(state.current_player());
        let alternate = o.determinize(&mut Rng::new(17)).unwrap();
        let other = alternate.observe(o.viewer as usize);
        assert_eq!(o, other);
        assert_eq!(
            encode(&o, &mut Rng::new(81)),
            encode(&other, &mut Rng::new(81))
        );
        let mut legal = ActionSet::new();
        state.legal_actions(&mut legal);
        let config = SearchConfig {
            iterations: 8,
            depth: 8,
            ..Default::default()
        };
        for name in [
            "transfer",
            "transfer-native",
            "transfer-pool3",
            "transfer-dynamic",
        ] {
            let mut a = make_agent(name, 18, &config).unwrap();
            let mut b = make_agent(name, 18, &config).unwrap();
            assert_eq!(a.select_action(&o, &legal), b.select_action(&other, &legal));
            assert_eq!(a.policy_target(), b.policy_target());
            let mut late = o.clone();
            late.turns = 124;
            let before = a.work_counts();
            assert_eq!(
                a.select_action(&late, &legal),
                StrongHeuristicAgent.select_action(&late, &legal)
            );
            assert_eq!(before, a.work_counts());
        }
    }
    #[test]
    fn public_projection_identity_and_hidden_world_invariance() {
        use splendor_core::{Action, GameState, Rng};
        let original = include_bytes!("models/e30.bin");
        let mut bytes = b"SPPUB751".to_vec();
        bytes.extend(1u32.to_le_bytes());
        for row in original[..56 * 56 * 4].as_chunks::<{ 56 * 4 }>().0 {
            bytes.extend(row);
            bytes.extend([0; 19 * 4]);
        }
        bytes.extend(&original[56 * 56 * 4..]);
        let old = Model::from_bytes(original);
        let new = Model::from_bytes(&bytes);
        assert!(new.needs_public_context());
        assert!(!new.has_correction());
        let mut state = GameState::new(2, 81).unwrap();
        state.apply_action(Action::ReserveDeck(0)).unwrap();
        let o = state.observe(state.current_player());
        let context = public_context(&o);
        assert_eq!(context[0], 1.0);
        let mut expected = None;
        for seed in 0..16 {
            let x = encode(&o, &mut Rng::new(1000 + seed));
            let mean = crate::belief::moments(&x, &context).0;
            let prediction = new.infer_with_context(&x, &context);
            assert_eq!(prediction, old.infer(&mean));
            assert_eq!(prediction, new.infer_with_profile(&x, &context, true));
            if let Some(previous) = expected {
                assert_eq!(prediction, previous);
            }
            expected = Some(prediction);
        }
        let x = encode(&o, &mut Rng::new(1000));
        assert!(std::panic::catch_unwind(|| new.infer(&x)).is_err());
        // Spatial feature index519 is column74, lane1 of the first layer.
        let at = 12 + 74 * 4;
        bytes[at..at + 4].copy_from_slice(&1f32.to_le_bytes());
        let changed = Model::from_bytes(&bytes);
        assert_ne!(
            changed.infer_with_profile(&x, &context, false),
            changed.infer_with_profile(&x, &context, true)
        );
        let mut bad = bytes.clone();
        bad[8..12].copy_from_slice(&0u32.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bad)).is_err());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bytes[..bytes.len() - 4])).is_err());
    }
    #[test]
    fn information_projection_identity_and_payload_checks() {
        let original = include_bytes!("models/e30.bin");
        let mut bytes = b"SPINFO57".to_vec();
        bytes.extend(1u32.to_le_bytes());
        bytes.extend(7u32.to_le_bytes());
        for row in original[..56 * 56 * 4].as_chunks::<{ 56 * 4 }>().0 {
            bytes.extend(row);
            bytes.extend(0f32.to_le_bytes());
        }
        bytes.extend(&original[56 * 56 * 4..]);
        let old = Model::from_bytes(original);
        let new = Model::from_bytes(&bytes);
        assert!(!old.needs_public_context());
        assert!(new.needs_public_context());
        let context = [1.0, 0.0, 1.0, 1.0 / 3.0, 2.0 / 3.0, 1.0, 2.0 / 3.0];
        for seed in 0..32 {
            let state = splendor_core::GameState::new(2, seed).unwrap();
            let x = encode(&state.observe(0), &mut splendor_core::Rng::new(1000 + seed));
            assert_eq!(old.infer(&x), new.infer_with_context(&x, &context));
            assert_eq!(old.infer(&x), old.infer_with_context(&x, &context));
        }
        let x = encode(
            &splendor_core::GameState::new(2, 0).unwrap().observe(0),
            &mut splendor_core::Rng::new(1000),
        );
        assert!(std::panic::catch_unwind(|| new.infer(&x)).is_err());
        let weight_offset = 16 + 56 * 4;
        let mut changed = bytes.clone();
        changed[weight_offset..weight_offset + 4].copy_from_slice(&1f32.to_le_bytes());
        let changed = Model::from_bytes(&changed);
        assert_ne!(
            changed.infer_with_context(&x, &context),
            changed.infer_with_context(&x, &[0.0; 7])
        );
        for offset in [8, 12] {
            let mut bad = bytes.clone();
            bad[offset..offset + 4].copy_from_slice(&0u32.to_le_bytes());
            assert!(std::panic::catch_unwind(|| Model::from_bytes(&bad)).is_err());
        }
        let mut bad = bytes.clone();
        bad[weight_offset..weight_offset + 4].copy_from_slice(&f32::NAN.to_le_bytes());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bad)).is_err());
        assert!(std::panic::catch_unwind(|| Model::from_bytes(&bytes[..bytes.len() - 4])).is_err());
    }
}

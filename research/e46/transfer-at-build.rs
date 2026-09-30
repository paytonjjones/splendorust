//! Native inference for the upstream version-80 network.
//! Architecture copyright (c) 2018 Surag Nair (MIT).
//! See research/e30/UPSTREAM-LICENSE. No game-state input is accepted here.
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
        Norm {
            weights: self.take(input * output),
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
struct Block {
    expand: Norm,
    depthwise: Norm,
    squeeze: Dense,
    excite: Dense,
    project: Norm,
}
impl Block {
    fn apply(&self, x: &[f32], head: bool) -> Vec<f32> {
        let activation = if head {
            Activation::HardSwish
        } else {
            Activation::Relu
        };
        let h = self.expand.apply(x, activation);
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
        let mut y = self.project.apply(&h, Activation::None);
        for (y, x) in y.iter_mut().zip(x) {
            *y += x;
        }
        y
    }
}
struct BootstrapModel {
    first: Norm,
    trunk: Block,
    policy_block: Block,
    policy_hidden: Dense,
    policy_output: Dense,
    value_block: Block,
    value_hidden: Dense,
    value_output: Dense,
}
impl BootstrapModel {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        assert_eq!(
            bytes.len(),
            include_bytes!("models/e30.bin").len(),
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
            first: r.norm(56, 56, 56, false),
            trunk: r.block(),
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
        let h = self
            .trunk
            .apply(&self.first.apply(x, Activation::None), false);
        let policy = self.policy_block.apply(&h, true);
        let policy: Vec<_> = self
            .policy_hidden
            .apply(&policy)
            .into_iter()
            .map(|x| x.max(0.0))
            .collect();
        let policy = self.policy_output.apply(&policy);
        let value = self.value_block.apply(&h, true);
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
        (policy.try_into().unwrap(), value.try_into().unwrap())
    }
}

/// Native checkpoint dispatch. Both architectures use the same observation encoder.
pub struct Model {
    architecture: Architecture,
}
enum Architecture {
    Bootstrap(Box<BootstrapModel>),
    Gated(GatedModel),
}
impl Model {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let architecture = if bytes.starts_with(b"SPGATED1") || bytes.starts_with(b"SPGATED2") {
            Architecture::Gated(GatedModel::from_bytes(bytes))
        } else {
            Architecture::Bootstrap(Box::new(BootstrapModel::from_bytes(bytes)))
        };
        Self { architecture }
    }
    pub fn infer(&self, x: &[f32; 392]) -> ([f32; 81], [f32; 2]) {
        match &self.architecture {
            Architecture::Bootstrap(model) => model.infer(x),
            Architecture::Gated(model) => model.infer(x),
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
        let inputs = if bitplanes { 512 } else { 392 };
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
        let features = gated_features(x, self.bitplanes);
        let mut h: Vec<_> = self.stem.apply(&features).into_iter().map(silu).collect();
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
        (y[..81].try_into().unwrap(), [y[81].tanh(), y[82].tanh()])
    }
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
}

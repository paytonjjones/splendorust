//! Full deep residual inference. Public inputs only; no frozen leaf network.
use super::*;
struct Linear {
    input: usize,
    output: usize,
    weights: Vec<[f32; 4]>,
    bias: Vec<[f32; 4]>,
}
impl Linear {
    fn read(r: &mut Reader, input: usize, output: usize) -> Self {
        let weights = r.take(input * output);
        let bias = r.take(output);
        let groups = output.div_ceil(4);
        Self {
            input,
            output,
            weights: (0..groups)
                .flat_map(|group| {
                    let weights = &weights;
                    (0..input).map(move |i| {
                        std::array::from_fn(|lane| {
                            let row = group * 4 + lane;
                            if row < output {
                                weights[row * input + i]
                            } else {
                                0.0
                            }
                        })
                    })
                })
                .collect(),
            bias: (0..groups)
                .map(|group| {
                    std::array::from_fn(|lane| bias.get(group * 4 + lane).copied().unwrap_or(0.0))
                })
                .collect(),
        }
    }
    fn apply(&self, x: &[f32]) -> Vec<f32> {
        assert_eq!(x.len(), self.input);
        let mut output = Vec::with_capacity(self.output.div_ceil(4) * 4);
        for (weights, bias) in self.weights.chunks_exact(self.input).zip(&self.bias) {
            let mut sums = [0.0f32; 4];
            for (w, v) in weights.iter().zip(x) {
                for lane in 0..4 {
                    sums[lane] = v.mul_add(w[lane], sums[lane]);
                }
            }
            output.extend(sums.into_iter().zip(bias).map(|(v, b)| v + b));
        }
        output.truncate(self.output);
        output
    }
}
struct Norm {
    gain: Vec<f32>,
    bias: Vec<f32>,
}
impl Norm {
    fn read(r: &mut Reader, width: usize) -> Self {
        Self {
            gain: r.take(width),
            bias: r.take(width),
        }
    }
    fn apply(&self, x: &[f32]) -> Vec<f32> {
        let mean = x.iter().map(|v| f64::from(*v)).sum::<f64>() / x.len() as f64;
        let variance = x
            .iter()
            .map(|v| (f64::from(*v) - mean).powi(2))
            .sum::<f64>()
            / x.len() as f64;
        let scale = (variance + 1e-5).sqrt().recip();
        x.iter()
            .zip(&self.gain)
            .zip(&self.bias)
            .map(|((v, g), b)| ((f64::from(*v) - mean) * scale) as f32 * g + b)
            .collect()
    }
}
fn gelu(x: f32) -> f32 {
    // Numerical Recipes erf approximation; export parity bounds the error.
    let z = f64::from(x) * std::f64::consts::FRAC_1_SQRT_2;
    let t = 1.0 / (1.0 + 0.5 * z.abs());
    let tau = t
        * (-z * z - 1.26551223
            + t * (1.00002368
                + t * (0.37409196
                    + t * (0.09678418
                        + t * (-0.18628806
                            + t * (0.27886807
                                + t * (-1.13520398
                                    + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))))
            .exp();
    let erf = if z >= 0.0 { 1.0 - tau } else { tau - 1.0 };
    (0.5 * f64::from(x) * (1.0 + erf)) as f32
}
struct Block {
    norm: Norm,
    up: Linear,
    down: Linear,
}
pub(super) struct LargeModel {
    stem: Linear,
    blocks: Vec<Block>,
    norm: Norm,
    policy: Linear,
    value: Linear,
}
impl LargeModel {
    pub(super) fn from_bytes(bytes: &[u8]) -> Self {
        assert!(
            bytes.len() >= 16 && (bytes.len() - 16).is_multiple_of(4),
            "large residual payload"
        );
        let width = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        let depth = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        assert!(
            (128..=1024).contains(&width) && width.is_multiple_of(4) && depth == 8,
            "large residual dimensions"
        );
        let expected = (525 + 1) * width
            + depth * (2 * width * width + 4 * width)
            + 2 * width
            + (width + 1) * 83;
        assert_eq!(
            bytes.len(),
            16 + 4 * expected,
            "large residual payload length"
        );
        let values: Vec<_> = bytes[16..]
            .as_chunks::<4>()
            .0
            .iter()
            .map(|v| f32::from_le_bytes(*v))
            .collect();
        assert!(values.iter().all(|v| v.is_finite()));
        let mut r = Reader { values, at: 0 };
        let stem = Linear::read(&mut r, 525, width);
        let blocks = (0..depth)
            .map(|_| Block {
                norm: Norm::read(&mut r, width),
                up: Linear::read(&mut r, width, width),
                down: Linear::read(&mut r, width, width),
            })
            .collect();
        let result = Self {
            stem,
            blocks,
            norm: Norm::read(&mut r, width),
            policy: Linear::read(&mut r, width, 81),
            value: Linear::read(&mut r, width, 2),
        };
        assert_eq!(r.at, r.values.len(), "large residual payload length");
        result
    }
    pub(super) fn infer(
        &self,
        x: &[f32; 392],
        context: &[f32; 7],
        native: bool,
    ) -> ([f32; 81], [f32; 2]) {
        let (mean, public) = crate::belief::moments(x, context);
        let mut input = [0.0; 525];
        for (dest, value) in input[..392].iter_mut().zip(mean) {
            *dest = value * 0.1;
        }
        input[6] = x[6] / 124.0;
        input[392..519].copy_from_slice(&public[392..]);
        input[519] = f32::from(native);
        let mut h = self.stem.apply(&input);
        for block in &self.blocks {
            let mut up = block.up.apply(&block.norm.apply(&h));
            up.iter_mut().for_each(|v| *v = gelu(*v));
            let delta = block.down.apply(&up);
            for (v, d) in h.iter_mut().zip(delta) {
                *v += d / 8.0f32.sqrt();
            }
        }
        let h = self.norm.apply(&h);
        (
            self.policy.apply(&h).try_into().unwrap(),
            self.value
                .apply(&h)
                .into_iter()
                .map(f32::tanh)
                .collect::<Vec<_>>()
                .try_into()
                .unwrap(),
        )
    }
}

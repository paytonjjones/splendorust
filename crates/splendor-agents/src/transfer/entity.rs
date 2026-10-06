//! Portable Entity Transformer inference used by the strength champion.

use std::convert::TryInto;

const TOKENS: usize = 31;
const WIDTH: usize = 256;
const HEADS: usize = 8;
const HEAD: usize = WIDTH / HEADS;

#[derive(Clone)]
struct Linear {
    out: usize,
    input: usize,
    weight: Vec<f32>,
    bias: Vec<f32>,
}
impl Linear {
    fn read(r: &mut Reader, out: usize, input: usize) -> Self {
        Self {
            out,
            input,
            weight: r.take(out * input),
            bias: r.take(out),
        }
    }
    fn apply(&self, x: &[f32], y: &mut [f32]) {
        for (o, output) in y[..self.out].iter_mut().enumerate() {
            let row = &self.weight[o * self.input..(o + 1) * self.input];
            *output = self.bias[o] + row.iter().zip(x).map(|(a, b)| a * b).sum::<f32>();
        }
    }
}
struct Layer {
    qkv: Linear,
    proj: Linear,
    ff1: Linear,
    ff2: Linear,
    n1: (Vec<f32>, Vec<f32>),
    n2: (Vec<f32>, Vec<f32>),
}
impl Layer {
    fn read(r: &mut Reader) -> Self {
        Self {
            qkv: Linear::read(r, WIDTH * 3, WIDTH),
            proj: Linear::read(r, WIDTH, WIDTH),
            ff1: Linear::read(r, WIDTH * 4, WIDTH),
            ff2: Linear::read(r, WIDTH, WIDTH * 4),
            n1: r.norm(),
            n2: r.norm(),
        }
    }
}
struct Reader<'a> {
    b: &'a [u8],
    p: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Vec<f32> {
        let end = self.p + n * 4;
        assert!(end <= self.b.len());
        let v = (self.p..end)
            .step_by(4)
            .map(|i| f32::from_le_bytes(self.b[i..i + 4].try_into().unwrap()))
            .collect();
        self.p = end;
        v
    }
    fn norm(&mut self) -> (Vec<f32>, Vec<f32>) {
        (self.take(WIDTH), self.take(WIDTH))
    }
}
pub(crate) struct EntityModel {
    identity: Vec<f32>,
    project: Linear,
    layers: Vec<Layer>,
    norm: (Vec<f32>, Vec<f32>),
    policy: Linear,
    value: Linear,
}
impl EntityModel {
    pub(crate) fn from_bytes(bytes: &[u8]) -> Self {
        assert!(bytes.starts_with(b"SPENTY01"));
        let mut r = Reader {
            b: &bytes[8..],
            p: 0,
        };
        let identity = r.take(TOKENS * WIDTH);
        let project = Linear::read(&mut r, WIDTH, 48);
        let layers = (0..6).map(|_| Layer::read(&mut r)).collect();
        let norm = r.norm();
        let policy = Linear::read(&mut r, 81, WIDTH);
        let value = Linear::read(&mut r, 2, WIDTH);
        assert_eq!(r.p, r.b.len());
        Self {
            identity,
            project,
            layers,
            norm,
            policy,
            value,
        }
    }
    fn ln(x: &[f32], n: &(Vec<f32>, Vec<f32>), y: &mut [f32]) {
        let mean = x.iter().sum::<f32>() / x.len() as f32;
        let var = x.iter().map(|v| (v - mean) * (v - mean)).sum::<f32>() / x.len() as f32;
        let d = (var + 1e-5).sqrt();
        for i in 0..x.len() {
            y[i] = (x[i] - mean) / d * n.0[i] + n.1[i];
        }
    }
    // Preserve the frozen reference coefficients and reduction arithmetic.
    #[allow(clippy::excessive_precision, clippy::approx_constant)]
    fn gelu(x: f32) -> f32 {
        // PyTorch's default GELU uses the exact erf form, not the tanh shortcut.
        let sign = if x < 0.0 { -1.0 } else { 1.0 };
        let ax = x.abs() * 0.7071067811865476;
        let t = 1.0 / (1.0 + 0.3275911 * ax);
        let poly = t
            * (0.254829592
                + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
        let erf = sign * (1.0 - poly * (-ax * ax).exp());
        0.5 * x * (1.0 + erf)
    }
    pub(super) fn tokens(input: &[f32; 525]) -> Vec<f32> {
        let mut z = vec![0.0; TOKENS * 48];
        let mut r = [0.0f32; 392];
        for i in 0..392 {
            r[i] = input[i] * 0.1;
        }
        r[6] = input[6] / 124.0;
        let put = |z: &mut Vec<f32>, t: usize, s: usize, src: &[f32], n: usize| {
            z[t * 48 + s..t * 48 + s + n].copy_from_slice(&src[..n]);
        };
        put(&mut z, 0, 0, &r[0..7], 7);
        z[7] = input[519];
        for p in 0..2 {
            put(&mut z, 1 + p, 0, &r[(34 + p) * 7..(35 + p) * 7], 7);
            put(&mut z, 1 + p, 7, &r[(42 + p) * 7..(43 + p) * 7], 7);
            put(
                &mut z,
                1 + p,
                14,
                &r[(36 + 3 * p) * 7..(39 + 3 * p) * 7],
                21,
            );
        }
        for slot in 0..12 {
            put(
                &mut z,
                3 + slot,
                0,
                &r[(1 + 2 * slot) * 7..(3 + 2 * slot) * 7],
                14,
            );
            z[(3 + slot) * 48 + 14] = (slot / 4 + 1) as f32 / 3.0;
        }
        for slot in 0..3 {
            put(
                &mut z,
                15 + slot,
                0,
                &r[(31 + slot) * 7..(32 + slot) * 7],
                7,
            );
        }
        for p in 0..2 {
            for slot in 0..3 {
                let i = 18 + 3 * p + slot;
                put(
                    &mut z,
                    i,
                    0,
                    &r[(44 + 6 * p + 2 * slot) * 7..(46 + 6 * p + 2 * slot) * 7],
                    14,
                );
                z[i * 48 + 14] = p as f32;
                if p == 1 {
                    z[i * 48 + 15] = input[512 + slot];
                    z[i * 48 + 16] = input[515 + slot];
                }
            }
        }
        for tier in 0..3 {
            put(
                &mut z,
                24 + tier,
                0,
                &r[(25 + 2 * tier) * 7..(26 + 2 * tier) * 7],
                7,
            );
            put(
                &mut z,
                24 + tier,
                7,
                &input[392 + 40 * tier..432 + 40 * tier],
                40,
            );
            z[(24 + tier) * 48 + 47] = (tier + 1) as f32 / 3.0;
        }
        put(&mut z, 27, 0, &input[512..519], 7);
        put(&mut z, 28, 0, &r[26 * 7..27 * 7], 7);
        put(&mut z, 29, 0, &r[28 * 7..29 * 7], 7);
        put(&mut z, 30, 0, &r[30 * 7..31 * 7], 7);
        z
    }
    pub(crate) fn infer(&self, input: &[f32; 525]) -> ([f32; 81], [f32; 2]) {
        let tok = Self::tokens(input);
        let mut h = vec![0.0; TOKENS * WIDTH];
        for t in 0..TOKENS {
            let mut v = vec![0.0; WIDTH];
            self.project.apply(&tok[t * 48..t * 48 + 48], &mut v);
            for i in 0..WIDTH {
                h[t * WIDTH + i] = v[i] + self.identity[t * WIDTH + i];
            }
        }
        for l in &self.layers {
            let mut n = vec![0.0; TOKENS * WIDTH];
            for t in 0..TOKENS {
                Self::ln(
                    &h[t * WIDTH..t * WIDTH + WIDTH],
                    &l.n1,
                    &mut n[t * WIDTH..t * WIDTH + WIDTH],
                );
            }
            let mut qkv = vec![0.0; TOKENS * WIDTH * 3];
            for t in 0..TOKENS {
                l.qkv.apply(
                    &n[t * WIDTH..t * WIDTH + WIDTH],
                    &mut qkv[t * WIDTH * 3..t * WIDTH * 3 + WIDTH * 3],
                );
            }
            let mut a = vec![0.0; TOKENS * WIDTH];
            for t in 0..TOKENS {
                for head in 0..HEADS {
                    let mut scores = vec![0.0; TOKENS];
                    for s in 0..TOKENS {
                        let mut dot = 0.0;
                        for k in 0..HEAD {
                            dot += qkv[t * WIDTH * 3 + head * HEAD + k]
                                * qkv[s * WIDTH * 3 + WIDTH + head * HEAD + k];
                        }
                        scores[s] = dot / (HEAD as f32).sqrt();
                    }
                    let m = scores.iter().copied().fold(f32::NEG_INFINITY, f32::max);
                    let mut sum = 0.0;
                    for x in &mut scores {
                        *x = (*x - m).exp();
                        sum += *x;
                    }
                    for x in &mut scores {
                        *x /= sum;
                    }
                    for s in 0..TOKENS {
                        for k in 0..HEAD {
                            a[t * WIDTH + head * HEAD + k] +=
                                scores[s] * qkv[s * WIDTH * 3 + 2 * WIDTH + head * HEAD + k];
                        }
                    }
                }
            }
            let mut p = vec![0.0; WIDTH];
            for t in 0..TOKENS {
                l.proj.apply(&a[t * WIDTH..t * WIDTH + WIDTH], &mut p);
                for i in 0..WIDTH {
                    h[t * WIDTH + i] += p[i];
                }
            }
            let mut n2 = vec![0.0; TOKENS * WIDTH];
            for t in 0..TOKENS {
                Self::ln(
                    &h[t * WIDTH..t * WIDTH + WIDTH],
                    &l.n2,
                    &mut n2[t * WIDTH..t * WIDTH + WIDTH],
                );
                let mut u = vec![0.0; WIDTH * 4];
                l.ff1.apply(&n2[t * WIDTH..t * WIDTH + WIDTH], &mut u);
                for x in &mut u {
                    *x = Self::gelu(*x);
                }
                let mut d = vec![0.0; WIDTH];
                l.ff2.apply(&u, &mut d);
                for i in 0..WIDTH {
                    h[t * WIDTH + i] += d[i];
                }
            }
        }
        let mut cls = vec![0.0; WIDTH];
        Self::ln(&h[0..WIDTH], &self.norm, &mut cls);
        let mut p = [0.0; 81];
        let mut v = [0.0; 2];
        self.policy.apply(&cls, &mut p);
        self.value.apply(&cls, &mut v);
        for x in &mut v {
            *x = x.tanh();
        }
        (p, v)
    }
}

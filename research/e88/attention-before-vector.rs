//! Small public-root attention branch. The frozen base remains the leaf model.
use super::*;
const TOKENS: usize = 57;
const WIDTH: usize = 64;
struct Block {
    norm1: Vec<f32>,
    qkv: Dense,
    out: Dense,
    norm2: Vec<f32>,
    gate: Dense,
    up: Dense,
    down: Dense,
}
pub(super) struct AttentionModel {
    pub(super) base: BootstrapModel,
    row: Dense,
    global_input: Dense,
    position: Vec<f32>,
    blocks: Vec<Block>,
    norm: Vec<f32>,
    head: Dense,
}
impl AttentionModel {
    pub(super) fn from_bytes(bytes: &[u8]) -> Self {
        assert!(bytes.len() >= 12, "attention header");
        let base_len = u32::from_le_bytes(bytes[8..12].try_into().unwrap()) as usize;
        let end = 12usize.checked_add(base_len).unwrap();
        assert!(end <= bytes.len());
        let values: Vec<_> = bytes[end..]
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| f32::from_le_bytes(*b))
            .collect();
        assert_eq!((bytes.len() - end) % 4, 0);
        assert!(values.iter().all(|v| v.is_finite()));
        let mut r = Reader { values, at: 0 };
        let row = r.dense(7, WIDTH);
        let global_input = r.dense(127, WIDTH);
        let position = r.take(TOKENS * WIDTH);
        let blocks = (0..2)
            .map(|_| Block {
                norm1: r.take(WIDTH),
                qkv: r.dense(WIDTH, 3 * WIDTH),
                out: r.dense(WIDTH, WIDTH),
                norm2: r.take(WIDTH),
                gate: r.dense(WIDTH, 128),
                up: r.dense(WIDTH, 128),
                down: r.dense(128, WIDTH),
            })
            .collect();
        let norm = r.take(WIDTH);
        let head = r.dense(WIDTH, 83);
        assert_eq!(r.at, r.values.len(), "attention payload length");
        Self {
            base: BootstrapModel::from_bytes(&bytes[12..end]),
            row,
            global_input,
            position,
            blocks,
            norm,
            head,
        }
    }
    pub(super) fn infer(&self, x: &[f32; 392], context: &[f32; 7]) -> ([f32; 81], [f32; 2]) {
        let (mean, features) = crate::belief::moments(x, context);
        let base_h = self.base.features(&mean, true);
        let mut pi = self.base.policy(&base_h, true);
        let value = self.base.value_raw(&base_h, true);
        let mut h = Vec::with_capacity(TOKENS);
        h.push(self.global_input.apply(&features[392..]));
        h.extend(
            features[..392]
                .as_chunks::<7>()
                .0
                .iter()
                .map(|row| self.row.apply(row)),
        );
        for (token, position) in h
            .iter_mut()
            .zip(self.position.as_chunks::<WIDTH>().0.iter())
        {
            for (v, p) in token.iter_mut().zip(position) {
                *v += p;
            }
        }
        for block in &self.blocks {
            let qkv: Vec<_> = h
                .iter()
                .map(|v| block.qkv.apply(&rms_norm(v, &block.norm1)))
                .collect();
            for row in 0..TOKENS {
                let mut attended = [0.0f32; WIDTH];
                for head in 0..4 {
                    let offset = head * 16;
                    let mut scores = [0.0f32; TOKENS];
                    for (col, score) in scores.iter_mut().enumerate() {
                        *score = (0..16)
                            .map(|j| qkv[row][offset + j] * qkv[col][WIDTH + offset + j])
                            .sum::<f32>()
                            / 4.0;
                    }
                    let maximum = scores.iter().copied().fold(f32::NEG_INFINITY, f32::max);
                    for score in &mut scores {
                        *score = (*score - maximum).exp();
                    }
                    let sum = scores.iter().sum::<f32>();
                    for score in &mut scores {
                        *score /= sum;
                    }
                    for j in 0..16 {
                        attended[offset + j] = (0..TOKENS)
                            .map(|col| scores[col] * qkv[col][2 * WIDTH + offset + j])
                            .sum();
                    }
                }
                for (v, d) in h[row].iter_mut().zip(block.out.apply(&attended)) {
                    *v += d;
                }
            }
            for row in &mut h {
                let n = rms_norm(row, &block.norm2);
                let mut gate = block.gate.apply(&n);
                for (g, u) in gate.iter_mut().zip(block.up.apply(&n)) {
                    *g = silu(*g) * u;
                }
                for (v, d) in row.iter_mut().zip(block.down.apply(&gate)) {
                    *v += d;
                }
            }
        }
        let delta = self.head.apply(&rms_norm(&h[0], &self.norm));
        for (p, d) in pi.iter_mut().zip(&delta[..81]) {
            *p += d;
        }
        (
            pi,
            std::array::from_fn(|i| (value[i] + delta[81 + i]).tanh()),
        )
    }
}

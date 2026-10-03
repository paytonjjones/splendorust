//! Research-only tensor bridge. No state, RNG or labels cross this boundary.
use std::{
    cell::RefCell,
    collections::HashMap,
    io::{Read, Write},
    net::TcpStream,
};

pub(super) struct RemoteModel {
    pub(super) history: bool,
    pub(super) history_version: u8,
    endpoint: String,
    slot: u32,
    hash: [u8; 32],
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn history_versions_preserve_their_registered_public_fields() {
        for version in 0..=2 {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let address = listener.local_addr().unwrap();
            let worker = std::thread::spawn(move || {
                let (mut conn, _) = listener.accept().unwrap();
                let mut slot = [0u8; 4];
                conn.read_exact(&mut slot).unwrap();
                conn.write_all(&[0u8; 32]).unwrap();
                let mut wire = [0u8; 4508];
                conn.read_exact(&mut wire).unwrap();
                for row in 0..16 {
                    for field in 0..32 {
                        let offset = 4 * (525 + row * 32 + field);
                        let value =
                            f32::from_le_bytes(wire[offset..offset + 4].try_into().unwrap());
                        let omitted = version == 0 || (version == 1 && matches!(field, 15 | 16));
                        assert_eq!(value, if omitted { 0.0 } else { field as f32 / 32.0 });
                    }
                }
                conn.write_all(&[0u8; 332]).unwrap();
            });
            let descriptor = format!("SPREMOTE{address}\n0\n{}\n{version}\n", "00".repeat(32));
            let model = RemoteModel::from_bytes(descriptor.as_bytes());
            let history = [std::array::from_fn(|field| field as f32 / 32.0); 16];
            model.infer(&[0.0; 392], &[0.0; 7], false, &history, &[1.0; 90]);
            worker.join().unwrap();
        }
    }
    #[test]
    fn tensors_are_invariant_across_hidden_samples_and_disabled_history() {
        use splendor_core::{Action, GameState, Rng};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let worker = std::thread::spawn(move || {
            let (mut conn, _) = listener.accept().unwrap();
            let mut slot = [0u8; 4];
            conn.read_exact(&mut slot).unwrap();
            assert_eq!(u32::from_le_bytes(slot), 3);
            conn.write_all(&[0u8; 32]).unwrap();
            let mut previous = None;
            for _ in 0..8 {
                let mut wire = [0u8; 4508];
                conn.read_exact(&mut wire).unwrap();
                if let Some(old) = previous {
                    assert_eq!(wire, old);
                }
                previous = Some(wire);
                conn.write_all(&[0u8; 332]).unwrap();
            }
        });
        let descriptor = format!("SPREMOTE{address}\n3\n{}\n0\n", "00".repeat(32));
        let model = RemoteModel::from_bytes(descriptor.as_bytes());
        let mut state = GameState::new(2, 619000007).unwrap();
        state.apply_action(Action::ReserveDeck(0)).unwrap();
        let o = state.observe(state.current_player());
        let context = crate::transfer::public_context(&o);
        assert_eq!(context[0], 1.0);
        for seed in 0..8 {
            let x = crate::transfer::encode(&o, &mut Rng::new(seed));
            let output = model.infer(
                &x,
                &context,
                false,
                &[[seed as f32; 32]; 16],
                &crate::public_history::canonical_pool(&o),
            );
            assert_eq!(output, ([0.0; 81], [0.0; 2]));
        }
        worker.join().unwrap();
    }
    #[test]
    fn reject_checkpoint_mismatch_before_tensor_send() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let worker = std::thread::spawn(move || {
            let (mut conn, _) = listener.accept().unwrap();
            let mut slot = [0u8; 4];
            conn.read_exact(&mut slot).unwrap();
            conn.write_all(&[1u8; 32]).unwrap();
        });
        let descriptor = format!("SPREMOTE{address}\n0\n{}\n1\n", "00".repeat(32));
        let model = RemoteModel::from_bytes(descriptor.as_bytes());
        let result = std::panic::catch_unwind(|| {
            model.infer(&[0.0; 392], &[0.0; 7], false, &[[0.0; 32]; 16], &[1.0; 90])
        });
        worker.join().unwrap();
        assert!(result.is_err(), "wrong checkpoint accepted");
    }
    #[test]
    #[should_panic(expected = "local tensor service required")]
    fn reject_nonlocal_service() {
        RemoteModel::from_bytes(
            format!("SPREMOTE192.0.2.1:19531\n0\n{}\n0\n", "00".repeat(32)).as_bytes(),
        );
    }
}
thread_local! {
    static CONNECTIONS: RefCell<Connections> = RefCell::new(HashMap::new());
}
type Connections = HashMap<(String, u32, [u8; 32]), TcpStream>;
impl RemoteModel {
    pub(super) fn from_bytes(bytes: &[u8]) -> Self {
        let header = std::str::from_utf8(&bytes[8..]).expect("remote model header");
        let fields: Vec<_> = header.lines().collect();
        assert_eq!(fields.len(), 4, "remote descriptor fields");
        let endpoint = fields[0].to_owned();
        let address: std::net::SocketAddr = endpoint.parse().expect("remote address");
        assert!(address.ip().is_loopback(), "local tensor service required");
        let slot = fields[1].parse().expect("remote model slot");
        let history_version = match fields[3] {
            "0" => 0,
            "1" => 1,
            "2" => 2,
            _ => panic!("history mode"),
        };
        assert_eq!(fields[2].len(), 64, "checkpoint hash length");
        let hash = std::array::from_fn(|i| {
            u8::from_str_radix(&fields[2][2 * i..2 * i + 2], 16).expect("checkpoint hash")
        });
        Self {
            history: history_version > 0,
            history_version,
            endpoint,
            slot,
            hash,
        }
    }
    pub(super) fn infer(
        &self,
        x: &[f32; 392],
        context: &[f32; 7],
        native: bool,
        history: &[[f32; 32]; 16],
        pool: &[f32; 90],
    ) -> ([f32; 81], [f32; 2]) {
        let (mean, public) = crate::belief::moments(x, context);
        let mut input = [0.0f32; 1127];
        input[..392].copy_from_slice(&mean);
        input[392..519].copy_from_slice(&public[392..]);
        input[519] = f32::from(native);
        for (target, row) in input[525..1037]
            .as_chunks_mut::<32>()
            .0
            .iter_mut()
            .zip(history)
        {
            if self.history {
                target.copy_from_slice(row);
                if self.history_version == 1 {
                    target[15] = 0.0;
                    target[16] = 0.0;
                }
            }
        }
        input[1037..].copy_from_slice(pool);
        assert!(input.iter().all(|v| v.is_finite()));
        CONNECTIONS.with(|connections| {
            let mut connections = connections.borrow_mut();
            let stream = connections
                .entry((self.endpoint.clone(), self.slot, self.hash))
                .or_insert_with(|| {
                    let mut stream = TcpStream::connect(&self.endpoint)
                        .expect("connect research tensor service");
                    stream.set_nodelay(true).expect("tensor socket option");
                    stream
                        .write_all(&self.slot.to_le_bytes())
                        .expect("tensor model slot");
                    let mut actual = [0u8; 32];
                    stream
                        .read_exact(&mut actual)
                        .expect("tensor checkpoint identity");
                    assert_eq!(actual, self.hash, "tensor service checkpoint mismatch");
                    stream
                });
            let mut wire = [0u8; 4508];
            for (target, value) in wire.as_chunks_mut::<4>().0.iter_mut().zip(input) {
                target.copy_from_slice(&value.to_le_bytes());
            }
            stream.write_all(&wire).expect("send legal model tensor");
            let mut response = [0u8; 332];
            stream
                .read_exact(&mut response)
                .expect("read model prediction");
            let values: [f32; 83] = std::array::from_fn(|i| {
                f32::from_le_bytes(response[4 * i..4 * i + 4].try_into().unwrap())
            });
            assert!(values.iter().all(|v| v.is_finite()), "finite model outputs");
            assert!(
                values[81..].iter().all(|v| (-1.0..=1.0).contains(v)),
                "bounded values"
            );
            (
                values[..81].try_into().unwrap(),
                values[81..].try_into().unwrap(),
            )
        })
    }
}

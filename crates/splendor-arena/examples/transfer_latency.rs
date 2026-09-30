//! Fixed-input transfer inference timing and exact output comparison artifact.
use splendor_agents::transfer::Model;
use std::{hint::black_box, time::Instant};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let model = Model::from_bytes(&std::fs::read(&args[1])?);
    let data: serde_json::Value = serde_json::from_slice(&std::fs::read(&args[2])?)?;
    let xs: Vec<[f32; 392]> = data["x"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            row.as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_f64().unwrap() as f32)
                .collect::<Vec<_>>()
                .try_into()
                .unwrap()
        })
        .collect();
    let outputs: Vec<_> = xs
        .iter()
        .map(|x| {
            let (p, v) = model.infer(x);
            serde_json::json!({"policy":p.as_slice(),"value":v})
        })
        .collect();
    std::fs::write(&args[3], serde_json::to_vec(&outputs)?)?;
    for repeat in 0..3 {
        let start = Instant::now();
        for i in 0..10000 {
            black_box(model.infer(black_box(&xs[i % xs.len()])));
        }
        println!(
            "{}",
            serde_json::json!({"repeat":repeat,"calls":10000,"seconds":start.elapsed().as_secs_f64(),"source":env!("SPLENDOR_SOURCE_ID")})
        );
    }
    Ok(())
}

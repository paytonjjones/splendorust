use splendor_agents::neural_search::Model;
use std::{hint::black_box, time::Instant};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    let bytes = std::fs::read(&a[1])?;
    let model = Model::from_bytes(&bytes);
    let data: serde_json::Value = serde_json::from_slice(&std::fs::read(&a[2])?)?;
    let positions: Vec<Vec<f32>> = data["x"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| {
            r.as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap() as f32)
                .collect()
        })
        .collect();
    for repeat in 0..3 {
        let start = Instant::now();
        for i in 0..20000 {
            black_box(model.infer(black_box(&positions[i % positions.len()])));
        }
        println!(
            "{}",
            serde_json::json!({"repeat":repeat,"calls":20000,"seconds":start.elapsed().as_secs_f64(),"source":env!("SPLENDOR_SOURCE_ID")})
        );
    }
    Ok(())
}

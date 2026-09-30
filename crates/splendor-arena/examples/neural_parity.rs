//! Compare native inference with exported PyTorch outputs.
use splendor_agents::neural_search::Model;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = std::env::args().collect();
    let model = Model::from_bytes(&std::fs::read(&a[1])?);
    let expected: serde_json::Value = serde_json::from_slice(&std::fs::read(&a[2])?)?;
    let mut max_error = 0f64;
    for (i, row) in expected["x"].as_array().unwrap().iter().enumerate() {
        let x: Vec<f32> = row
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap() as f32)
            .collect();
        let (policy, value) = model.infer(&x);
        for (j, &p) in policy.iter().enumerate() {
            max_error =
                max_error.max((f64::from(p) - expected["logits"][i][j].as_f64().unwrap()).abs());
        }
        max_error =
            max_error.max((f64::from(value) - expected["value_logits"][i].as_f64().unwrap()).abs());
    }
    assert!(max_error < 0.0001, "inference mismatch {max_error}");
    println!(
        "{}",
        serde_json::json!({"positions":expected["x"].as_array().unwrap().len(),"max_absolute_error":max_error,"tolerance":0.0001})
    );
    Ok(())
}

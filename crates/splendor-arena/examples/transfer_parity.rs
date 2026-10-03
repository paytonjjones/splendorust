//! Validate transferred inference on real initial boards and extreme stress inputs.
use splendor_agents::transfer::Model;
fn probabilities(logits: &[f32], mask: &[bool]) -> Vec<f32> {
    let max = logits
        .iter()
        .zip(mask)
        .filter(|(_, valid)| **valid)
        .map(|(&x, _)| x)
        .fold(f32::NEG_INFINITY, f32::max);
    let mut p: Vec<_> = logits
        .iter()
        .zip(mask)
        .map(|(&x, &valid)| if valid { (x - max).exp() } else { 0.0 })
        .collect();
    let total: f32 = p.iter().sum();
    for value in &mut p {
        *value /= total;
    }
    p
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args().collect();
    let model = Model::from_bytes(&std::fs::read(&args[1])?);
    let data: serde_json::Value = serde_json::from_slice(&std::fs::read(&args[2])?)?;
    let xs = data["x"].as_array().unwrap();
    let (mut maximum, mut real_maximum, mut output_maximum) = (0.0f32, 0.0f32, 0.0f32);
    for (i, row) in xs.iter().enumerate() {
        let x: [f32; 392] = row
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap() as f32)
            .collect::<Vec<_>>()
            .try_into()
            .unwrap();
        let (policy, value) = if let Some(rows) = data["context"].as_array() {
            let context: [f32; 7] = rows[i]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap() as f32)
                .collect::<Vec<_>>()
                .try_into()
                .unwrap();
            let native = data["native_profiles"][i].as_bool().unwrap_or(false);
            if let Some(rows) = data["history"].as_array() {
                let history: [[f32; 32]; 16] = std::array::from_fn(|j| {
                    std::array::from_fn(|k| rows[i][j][k].as_f64().unwrap() as f32)
                });
                let pool: [f32; 90] =
                    std::array::from_fn(|j| data["pool"][i][j].as_f64().unwrap() as f32);
                model.infer_with_history(&x, &context, native, &history, &pool)
            } else {
                model.infer_with_profile(&x, &context, native)
            }
        } else {
            model.infer(&x)
        };
        let expected_policy: Vec<_> = data["logits"][i]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap() as f32)
            .collect();
        for (&actual, &expected) in policy.iter().zip(&expected_policy) {
            let error = (actual - expected).abs();
            maximum = maximum.max(error);
            if i < 8 || args.get(3).is_some_and(|s| s == "real") {
                real_maximum = real_maximum.max(error);
            }
            // Extreme synthetic inputs produce logits over 500 in magnitude.
            assert!(error <= 0.001 + 0.00001 * expected.abs());
        }
        for (actual, expected) in value.into_iter().zip(data["values"][i].as_array().unwrap()) {
            output_maximum = output_maximum.max((actual - expected.as_f64().unwrap() as f32).abs());
        }
        let mut rng = splendor_core::Rng::new(617000007 + i as u64);
        for trial in 0..50 {
            let mut mask: Vec<_> = (0..81).map(|_| trial == 0 || rng.index(10) == 0).collect();
            mask[trial % 81] = true;
            for (actual, expected) in probabilities(&policy, &mask)
                .into_iter()
                .zip(probabilities(&expected_policy, &mask))
            {
                output_maximum = output_maximum.max((actual - expected).abs());
            }
        }
    }
    println!(
        "{}",
        serde_json::json!({"positions":xs.len(),"real_initial_board_max_logit_error":real_maximum,"all_inputs_max_logit_error":maximum,"masked_policy_and_value_max_error":output_maximum,"real_logit_tolerance":0.0001,"output_tolerance":0.001,"stress_logit_tolerance":"0.001 + 0.00001 * abs(expected)"})
    );
    assert!(real_maximum < 0.0001);
    assert!(output_maximum < 0.001);
    Ok(())
}

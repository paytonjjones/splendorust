//! Serialization adapters keep research configuration out of the agent crate.
use serde::{Deserialize, Serialize};
use splendor_agents::{Evaluation, RolloutPolicy, SearchConfig};
use std::time::Duration;

#[derive(Serialize, Deserialize)]
#[serde(remote = "SearchConfig", deny_unknown_fields)]
pub(crate) struct SearchSettings {
    iterations: u32,
    depth: u32,
    width: usize,
    time_budget: Option<Duration>,
    #[serde(with = "RolloutSettings")]
    rollout: RolloutPolicy,
    #[serde(with = "EvaluationSettings")]
    evaluation: Evaluation,
}

#[derive(Serialize, Deserialize)]
#[serde(remote = "RolloutPolicy", rename_all = "snake_case")]
enum RolloutSettings {
    Random,
    Greedy,
    Strong,
}

#[derive(Serialize, Deserialize)]
#[serde(remote = "Evaluation", rename_all = "snake_case")]
enum EvaluationSettings {
    Score,
    Engine,
}

# E80: teacher targets lose some executed-action strength

The teacher that executes the argmax of its exported training policy scores **44.425%** against the same teacher that executes sequential halving. All **2,000 paired games complete**. The two-sided95% empirical Bernstein interval over1,000 setup blocks is **40.278–48.572%**. Both agents use frozen E68,800 simulations,depth16,three sampled worlds and noise0. This supports a target/execution mismatch under this opponent and budget. It does not prove that this mismatch caused all previous training failures.

Across110,716 searched Main decisions, chosen action and policy argmax agree87.192%; mean target probability of the chosen action is0.75918. This shows why agreement alone was insufficient: the differing actions cause a measurable strength loss.

A separate fixed cohort has60 ordinary/forced-blind Strong observations and four independent teachers each. Agreement is89.66% ordinary /85.48% stress with noise0, and70.69% /68.55% with noise1. This cohort does not estimate corpus prevalence. E74 used the noisy teacher; E76 verified the noise-free executed-action teacher. Neither noisy-teacher strength nor its target-policy strength had been established by E76.

The full target-action comparison takes541.62s under concurrent E79 load. It is a structural diagnostic outside the usual128-simulation screen. All raw records, seeds, labels, binary/library/model hashes and sources remain. The initial standalone compile failed on a moved configuration capture; the corrected strict-warning build passed. A Python test discovery found no tests in research; this is recorded, not a passing test claim.

E81 changes labels to the chosen actions of the verified noise-free800-simulation teacher, while keeping the exact E74 actor positions and fast student architecture. No new production search mode or model promotion comes from E80.

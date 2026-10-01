# E93: consensus at a fixed total teacher budget

Hypothesis: E91's consensus direction can improve teacher decisions without a fourfold increase in search cost. Compare four independent E88 root-Gumbel200 searches, using the same vote/value tie rule, against one E88 root-Gumbel800 search. Both spend exactly800 simulations per searched Main decision. Four root evaluations and twelve sampled worlds can still cost more wall time; record that limit. No architecture sweep, coefficient tuning, or production search change.

Run2,000 paired games at master4800000000, policy identity seeds4801000000 plus16 times the block, with ensemble offsets0–3 and single offset8. Use depth16, noise0 and14 threads. Use the helper fallback validated in E91. Preserve all statuses, exact simulation counts, raw paired outcomes, build/model/library hashes and wall time. No arena records are training data.

Require every scheduled game complete and a conservative paired95% lower bound above50% before using this direction for a large corpus. Otherwise preserve the failure and do not scale consensus data on this evidence. E81 champion and E88 provisional lineage remain unchanged. This teacher test is separate from E92's unchanged external target; an internal teacher gain cannot establish external dominance.

# E84: root capacity after target repair

The 3.04-million-parameter root model scores **50.175%** against E81 Gumbel128 in **2,000 complete paired games**. The 95% interval is **45.898–54.452%**. It does not pass the registered provisional rule. Retain E81.

This repeats E78's 384-wide/six-block RMSNorm/SwiGLU correction, frozen E68 leaf base,20 epochs and seed800000015 on the repaired E81 target corpus. Epoch2 is selected. Training takes702.92 seconds; full run842.26 seconds under concurrent E82/E83 load. Native parity and frozen-base checks pass. Later held-out scores worsen sharply, reaching CE3.12354 at epoch20. This does not support another size increase of this flat correction on these targets. It does not prove the reason for the poor generalization.

The fixed-observation shared-host timing ratio is0.91194 versus E81 and passes the declared cost limit. Strong contention and the older frozen leaf base prevent an isolated speed claim from this result. The raw workload text inherited an initial-model description; cost-summary.json records the actual trained model hashes and scope.

Native candidate:d1d1cb55ebeb2a9c6f9c90e2bdce44334643c9db5f68537e65c0eba5afe69f2b. Checkpoint:2a532fcfc561e1d616c1d772178c51ce429542fc3b757970af1d59068343b631. Sources, data hashes, models, parity, timings, gate records and negative decisions remain.

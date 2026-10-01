# E87: strong-policy full-game self-play

Decision: retain E81. The student scored49.075% against E81 Gumbel128 in2,000 complete paired games, with conservative95% interval44.8005–53.3495%. Neither the strict gate nor the provisional point rule selects it. Champion and lineage remain E81.

All5,000 training and1,000 development games completed. The teacher controlled whole games at800 simulations, using frozen E81/Gumbel/noise0. Labels were corrected selected-action targets. Collected278,646 fresh training positions; with fixed E82 replay, trained334,040 positions and evaluated55,646 development positions. Public-context sidecars and immutable collector/model/source hashes are preserved.

Ten training epochs took108.36 seconds; development selection chose epoch9. Native inference matches PyTorch on64 real inputs: maximum logit error0.00001717 and policy/value error0.00000239. Full collection→training→screen cycle took1,099.46 seconds (18.32 minutes). Strict Clippy and118 release tests passed through the arena gate.

On the first data file, teacher-value terminal-outcome Brier error was0.19124 versus0.19742 on the prior weak-actor file. This compares different trajectories and is descriptive only. Better development metrics did not establish better playing strength.

This rejects the tested strong-trajectory/bootstrap training recipe. Together with E84/E86, it calls for a structural representation/capacity test rather than more small variants of the same flat network. The next planned model uses attention across public board rows at the root with the fast E81 leaf evaluator frozen.

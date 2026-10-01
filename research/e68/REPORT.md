# E68: teacher labels on student states

The fast candidate scores 50.725% against E59 in 2,000 complete games at 128
simulations (95% interval 46.42–55.03%). It passes the registered provisional
point rule. This is not statistical promotion. E56 remains the confirmed champion.

E59 actors use 128 simulations and independent E59 teachers use 800. Five
1,000-game train shards contain 278,820 positions; E64 replay adds 55,990 for
334,810 training rows. Development has 55,860 positions. Training selects epoch
10 and takes 124.91 seconds. Screening takes 75.06 seconds. Full train collection
takes 1,403.33 seconds, and development takes 285.79 seconds under shared load.
Baseline policy KL is 0.618 on the first 3,000 student-state games versus 0.574
on E64 teacher-state development. Different cohorts limit causal interpretation.

A diagnostic example first failed strict Clippy before any screen games ran.
That failed gate is preserved. After the fix, resume_gate.py checks that no
screen exists and uses the still-unused registered seed 4230000000. All sources,
models, labels, corpus hashes, raw arena records, and negative checks are saved.

# E69: public-information encoding collision

Seventeen valid observation pairs encode exactly the same 392 floats and have
identical native model outputs and actor legal sets. In one member, opponent
reservations are unknown. In the other, they are public and equal the first
member's independently sampled belief cards. Real private card identities are
never used. Core determinization validates both observations.

The encoder omits the public/unknown reservation flag and retained tier metadata.
It cannot distinguish these information conditions, even with a larger network
that receives only the same inputs. This proves an input-information omission;
it does not prove that it caused the prior strength plateau.

Eight 800-simulation E59 teachers per condition produce mean policy TV 0.134945;
two of 17 mean argmax choices differ. Mean value difference is 0.02323. These
are finite contrasts on a fixed blind stress cohort, not prevalence, optimal
policy, or playing-strength estimates. Raw vectors, labels, failed build/Clippy
logs, successful checks, and source are preserved. E70 tests an explicit mask
on the same saved teacher labels, with minimal extra inference work.

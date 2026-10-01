# E90: action-label stability

Independent 800-simulation E88 teachers agree on 57.1107% of chosen actions. Two independent four-search consensus choices agree on 69.3694%. The 128-simulation search agrees on 71.4125% of actions. These are conditional measurements on 222 fresh E88 trajectory observations, not population prevalence or playing strength.

The public root prior chooses an action that receives 43.5811% of empirical 800-search votes. Mean largest vote fraction is 70.7770%; mean selected-action entropy is 0.64675 nats. Mean selected-action value standard deviation is 0.026414. Blind observations have larger value variation, but similar action disagreement to known observations.

All 222 native root outputs are exactly invariant across eight independently sampled encodings. Thus E85/E88 removed the measured root-input variation, while searched action labels still vary. This does not prove that target noise causes the learning plateau. It does show why a single selected-action target can differ substantially from the public teacher's repeated behavior.

The diagnostic took 7.76 seconds with 14 threads. All observations, legal indices, complete policy vectors, values, seeds, native priors, model/library/binary hashes, and compiler commands are saved. Initial standalone linking failed because Apple LLVM could not read the pinned Rust bitcode; thin LTO fixed the link. The failed log is preserved.

The preregistered next step is a playing-strength check of a consensus teacher before training on more labels. No model, search endpoint, or champion is promoted by this diagnostic.

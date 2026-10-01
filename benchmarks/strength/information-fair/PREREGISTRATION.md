# Information fairness, fixed native benchmark

Hypothesis before implementation: private reservation identities and exact
unordered remaining-card membership contribute to the measured AlphaZero
advantage. Removing that information from AlphaZero, or supplying the same
information to SplendoRust, can change win credit at fixed rules and budgets.
These are two independent interventions, not agent training or promotion.

Use three arms on identical fresh setup blocks and both seat rotations:
control (public SplendoRust / unchanged AlphaZero), blind AlphaZero (public
SplendoRust / public-only sampled AlphaZero input), and privileged SplendoRust
(exact unordered partition / unchanged AlphaZero). No future order is supplied.
The actual referee remains the clean pinned upstream engine in every arm.

Endpoint: E81 Gumbel128/depth16/worlds3, no noise, checkpoint as in E92;
AlphaZero800 uses its unchanged checkpoint, MCTS, three chance universes,
coefficients, memory cleanup and total-turn temperature schedule. If the user
selects the original E56 PUCT endpoint before execution, record that choice
without changing budgets. Never select settings using outcomes.

First validate information invariance, exact partition support, actor legal
sets, default-policy parity and fixed work. Run a 2,000-game screen per arm
at master 4900000000. Then run a disjoint 20,000-game confirmation per arm
at master 4910000000. Same policy/chance seeds within each stage. Use eight
processes and retain commands, source/binary/model hashes and all raw histories.
Do not use confirmation outcomes to select any implementation or setting.

Primary contrasts: variant minus control SplendoRust win credit. Resample
whole independent setup blocks, retaining all arms and both rotations in each
block. Report 95% paired bootstrap intervals and simultaneous conservative
Hoeffding intervals for both differences. Report variant win credit, seat
effects, incomplete outcomes, caps and runtime. Define the control advantage
over equal credit as 0.5 minus control SR credit; report the fraction reduced
by each intervention with uncertainty and explicit scope. Do not add the two
fractions: the interventions estimate different counterfactuals and can interact.
Retain incomplete credit bounds; no incomplete game becomes a win.

Blind input is reconstructed solely from public history and the actor's own
private cards. Unknown reservations and tier decks form one sampled partition
without replacement. Sampling RNG is independent of referee/policy RNG. This
preserves native board shape and search mechanics; a sampled identity is a
hypothesis, never the real hidden identity. Preserve all known public cards,
reservation tiers/counts, own private cards, deck counts and public state.
Exact hidden values must affect neither sampled inputs nor decisions when
public observations and seeds are equal.

Privileged input explicitly includes full reservation IDs and sorted deck
sets. It uses the same native transition, search kernel and frozen model.
Root worlds and every simulated leaf use that exact unordered partition,
with uniform chance draws; never re-redact and re-sample it in neural input.
Default public/canonical agents and archived benchmarks remain unchanged.

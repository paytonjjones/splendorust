# E91: consensus teacher

Four independent E88 root-Gumbel800 searches, combined by chosen-action vote, score 56.875% against a single E88 root-Gumbel800 search. All 2,000 paired games complete. The conservative paired 95% interval is 52.6431–61.1069%. This passes the preregistered teacher-quality check. It does not promote a model or show an equal-compute improvement.

The ensemble uses 3,200 simulations per searched Main decision, versus 800 for the single teacher. It differs from its first replica on 26.4184% of decisions. Vote ties occur on 15.2205%; they use mean chosen-action value, then the smaller native action index. Mean largest vote fraction is 73.6401%. All 55,537 ensemble Main decisions pass exact simulation-count accounting.

The full schedule took 873.19 seconds with 14 threads under shared-host load. Ensemble and single-teacher simulation totals were 177,718,400 and 44,413,600. Raw outcomes, paired setups, counters, all seeds, model/library/binary hashes and compiler commands are saved. No arena records become training data.

The initial wrapper failed when a helper decision had no search value. That run was stopped and excluded. Its logs and source remain. The corrected wrapper completed a four-game execution check, then restarted the full schedule from the original seeds. Forced single-action, non-Main and turn-cap helper decisions keep the first replica's unchanged helper action and do not count as consensus searches.

E90 established substantial selected-action variation; E91 shows that consensus with extra compute can produce a stronger teacher. These facts do not isolate variance reduction from extra search compute. Before an expensive consensus corpus, the next check must compare four 200-simulation searches with one 800-simulation search at the same total simulation budget. The canonical champion stays E81 and the provisional lineage stays E88. A separate current-champion external check is running because dominance against credible opponents remains a critical goal.

# Browser time levels and fallback

Hypothesis: Fixed 5, 10, and 30 second turn limits let users trade wait time for search. E81 gives users without WebGPU a playable opponent. Downloading only the active inference format reduces startup cost without changing weights.

Budget: Four active hours. Run one GPU job at a time. Keep the frozen Entity and E81 weights. Compare FP32 native and browser inference with batch size one and include output transfers. Check numerical parity before accepting any GPU graph change. Do not claim measured playing strength for timeout search.

The default is 10 seconds. Changes apply to new games. Retry keeps the original limit. Each game records its actual model, backend, and limit. A running game does not change models after a GPU error.

Additional user requests: Show a turn timer, use “engine” on the page, and show actual download progress. Measure batch-one, batch-four, and batch-eight WebGPU inference with 500 calls each. This batch probe does not change game search. A batched search candidate needs separate fresh strength evidence before deployment.

// Load the state once. A request can arrive between load and waitAsync;
// the expected old state then makes waitAsync return without sleeping.
export async function waitForGpuRequest(control: Int32Array): Promise<void> {
  while (true) {
    const state = Atomics.load(control, 0);
    if (state === 1) return;
    if (state === -1) throw new Error("WebGPU inference stopped.");
    const wait = Atomics.waitAsync(control, 0, state);
    if (wait.async) await wait.value;
  }
}

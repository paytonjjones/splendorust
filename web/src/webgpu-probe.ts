import { loadGpuModel } from "./webgpu-model";
import fixturesUrl from "../../research/webgpu-20261006/fixtures.json?url";

declare global { interface Window { gpuProbe?: unknown; gpuProbeError?: string } }
try {
  const champion = await (await fetch("/champion.json")).json();
  const batch = Number(new URLSearchParams(location.search).get("batch") || 1);
  const capture = location.search.includes("capture");
  const model = await loadGpuModel(champion.model.sha256, location.origin + "/", capture, undefined, batch);
  const fixtures = await (await fetch(fixturesUrl)).json() as Array<{ tokens: number[]; logits: number[]; values: number[] }>;
  const pack = (start: number) => new Float32Array(Array.from({ length: batch }, (_, i) => fixtures[(start+i) % fixtures.length].tokens).flat());
  let maxLogitError = 0, maxValueError = 0;
  const check = (actual: Float32Array, start: number) => {
    if (![...actual].every(Number.isFinite)) throw new Error("GPU output is not finite.");
    for (let row = 0; row < batch; row++) {
      const fixture = fixtures[(start+row) % fixtures.length];
      maxLogitError = Math.max(maxLogitError, ...fixture.logits.map((v,i) => Math.abs(v-actual[row*81+i])));
      maxValueError = Math.max(maxValueError, ...fixture.values.map((v,i) => Math.abs(v-actual[batch*81+row*2+i])));
    }
    if (maxLogitError > .001 || maxValueError > .0001) throw new Error(`GPU parity failed: ${maxLogitError}, ${maxValueError}`);
  };
  for (let i = 0; i < 3; i++) await model.evaluate(pack(0));
  for (let i = 0; i < fixtures.length; i++) check(await model.evaluate(pack(i)), i);
  const times: number[] = [];
  for (let i = 0; i < 510; i++) {
    const start = performance.now();
    const actual = await model.evaluate(pack(i));
    const elapsed = performance.now() - start;
    check(actual, i);
    if (i >= 10) times.push(elapsed);
  }
  times.sort((a,b) => a-b);
  window.gpuProbe = { batch, capture, fixtures: fixtures.length, measuredCalls: times.length, maxLogitError, maxValueError, inferenceMs: { median: times[Math.floor(times.length / 2)], p95: times[Math.floor(times.length * .95)], mean: times.reduce((a,b) => a+b,0)/times.length, max: times.at(-1) }, model: model.metadata };
  document.querySelector("#result")!.textContent = JSON.stringify(window.gpuProbe, null, 2);
  await model.release();
} catch (error) {
  window.gpuProbeError = String(error);
  document.querySelector("#result")!.textContent = String(error);
}

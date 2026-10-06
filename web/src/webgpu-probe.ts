import { loadGpuModel } from "./webgpu-model";
import fixturesUrl from "../../research/webgpu-20261006/fixtures.json?url";

declare global { interface Window { gpuProbe?: unknown; gpuProbeError?: string } }
try {
  const champion = await (await fetch("/champion.json")).json();
  const model = await loadGpuModel(champion.model.sha256, location.origin + "/");
  const fixtures = await (await fetch(fixturesUrl)).json() as Array<{ tokens: number[]; logits: number[]; values: number[] }>;
  for (let i = 0; i < 3; i++) await model.evaluate(new Float32Array(fixtures[0].tokens));
  let maxLogitError = 0, maxValueError = 0;
  const times: number[] = [];
  for (const fixture of fixtures) {
    const actual = await model.evaluate(new Float32Array(fixture.tokens));
    maxLogitError = Math.max(maxLogitError, ...fixture.logits.map((v, i) => Math.abs(v - actual[i])));
    maxValueError = Math.max(maxValueError, ...fixture.values.map((v, i) => Math.abs(v - actual[i + 81])));
  }
  if (maxLogitError > 0.001 || maxValueError > 0.0001) throw new Error(`GPU parity failed: ${maxLogitError}, ${maxValueError}`);
  for (let i = 0; i < 110; i++) {
    const start = performance.now();
    await model.evaluate(new Float32Array(fixtures[i % fixtures.length].tokens));
    if (i >= 10) times.push(performance.now() - start);
  }
  times.sort((a,b) => a-b);
  window.gpuProbe = { fixtures: fixtures.length, maxLogitError, maxValueError, inferenceMs: { median: times[50], p95: times[95], mean: times.reduce((a,b) => a+b,0)/times.length, max: times.at(-1) }, model: model.metadata };
  document.querySelector("#result")!.textContent = JSON.stringify(window.gpuProbe, null, 2);
  await model.release();
} catch (error) {
  window.gpuProbeError = String(error);
  document.querySelector("#result")!.textContent = String(error);
}

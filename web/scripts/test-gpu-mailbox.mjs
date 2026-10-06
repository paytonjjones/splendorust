import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';
import { waitForGpuRequest } from '../src/gpu-mailbox.ts';

// Force a request to arrive after the read and before the wait. Waiting on
// state 1 would lose its notification and leave the caller blocked.
const originalWait = Atomics.waitAsync;
const originalLoad = Atomics.load;
const control = new Int32Array(new SharedArrayBuffer(16));
let waits = 0;
try {
  let reads = 0;
  Atomics.load = (array, index) => {
    const value = originalLoad(array, index);
    if (reads++ === 0) Atomics.store(array, index, 1);
    return value;
  };
  Atomics.waitAsync = (array, index, expected) => {
    waits++;
    assert.equal(originalLoad(array, index), 1);
    assert.equal(expected, 0);
    return { async: false, value: 'not-equal' };
  };
  await waitForGpuRequest(control);
  assert.equal(waits, 1);
} finally { Atomics.waitAsync = originalWait; Atomics.load = originalLoad; }

// Exercise the complete shared-memory protocol without model arithmetic.
const url = new URL('../src/gpu-mailbox.ts', import.meta.url).href;
const worker = new Worker(`
  const { parentPort } = require('node:worker_threads');
  parentPort.once('message', async buffer => {
    const { waitForGpuRequest } = await import(${JSON.stringify(url)});
    const view = new Int32Array(buffer);
    // Keep the process alive while waitAsync owns no event-loop handle.
    const keepAlive = setInterval(() => {}, 1000);
    parentPort.postMessage('ready');
    for (let index = 0; index < 100000; index++) {
      await waitForGpuRequest(view);
      view[2] = view[1] * 2;
      Atomics.store(view, 0, 2);
      Atomics.notify(view, 0);
    }
    clearInterval(keepAlive);
  });
`, { eval: true });
try {
  const ready = new Promise((resolve, reject) => {
    worker.once('message', resolve);
    worker.once('error', reject);
  });
  Atomics.store(control, 0, 0);
  worker.postMessage(control.buffer);
  await ready;
  for (let index = 0; index < 100000; index++) {
    control[1] = index;
    Atomics.store(control, 0, 1);
    Atomics.notify(control, 0);
    while (Atomics.load(control, 0) === 1) {
      assert.notEqual(Atomics.wait(control, 0, 1, 2000), 'timed-out');
    }
    assert.equal(Atomics.load(control, 0), 2);
    assert.equal(control[2], index * 2);
    Atomics.store(control, 0, 0);
    Atomics.notify(control, 0);
  }
  console.log('Forced handoff race and 100,000 inference handoffs passed.');
} finally { await worker.terminate(); }

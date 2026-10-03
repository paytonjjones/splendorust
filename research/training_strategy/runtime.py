"""Owned, checkpoint-bound inference service; never reuse another study's port."""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from data import ROOT, sha


class Runtime:
    def __init__(self, models, output, port=19620, device='mps'):
        self.models = models
        self.output = Path(output)
        self.port, self.device = port, device
        self.service = None
        self.log = None
        self.descriptors = {}

    def __enter__(self):
        self.output.mkdir(parents=True, exist_ok=False)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', self.port))
        service_command = [sys.executable, ROOT / 'research/architecture_pivots/service.py',
            '--port', self.port, '--device', self.device, '--batch', 32,
            '--delay-ms', 1, '--fast-entities']
        receipt = {}
        for slot, source in self.models:
            directory = self.output / str(slot)
            directory.mkdir()
            copy = directory / 'model.pt'
            shutil.copyfile(source, copy)
            assert sha(copy) == sha(source)
            command = [sys.executable, ROOT / 'research/architecture_pivots/export.py',
                       copy, '--port', self.port, '--slot', slot]
            with (directory / 'export.log').open('w') as log:
                subprocess.run(list(map(str, command)), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            self.descriptors[slot] = copy.with_suffix('.bin')
            service_command += ['--model', f'{slot}:{copy}']
            receipt[slot] = dict(source=str(source), checkpoint_sha256=sha(copy), descriptor_sha256=sha(copy.with_suffix('.bin')))
        self.log = (self.output / 'service.log').open('w')
        try:
            self.service = subprocess.Popen(list(map(str, service_command)), cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT)
            (self.output / 'run.json').write_text(json.dumps(dict(pid=self.service.pid,
                command=list(map(str,service_command)), models=receipt, batch=32,
                started_at=time.time()), indent=2)+'\n')
            deadline = time.monotonic()+60
            while True:
                if self.service.poll() is not None:
                    raise RuntimeError(f'Service failed: {self.output / "service.log"}')
                try:
                    with socket.create_connection(('127.0.0.1', self.port), timeout=1):
                        return self
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Service start timeout')
                    time.sleep(.1)
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *unused):
        if self.service is not None:
            self.service.terminate()
            try:
                self.service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.service.kill()
                self.service.wait()
        if self.log is not None:
            self.log.close()


def command_run(command, directory, environment=None, accepted=(0,)):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    command = list(map(str, command))
    (directory / 'command.json').write_text(json.dumps(dict(command=command,
        environment=environment or {}, started_at=time.time()), indent=2)+'\n')
    started = time.monotonic()
    env = os.environ.copy()
    env.update(environment or {})
    with (directory / 'output.log').open('w') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        (directory / 'process.json').write_text(json.dumps(dict(pid=process.pid, command=command))+'\n')
        code = process.wait()
    result = dict(returncode=code, seconds=time.monotonic()-started)
    (directory / 'exit.json').write_text(json.dumps(result, indent=2)+'\n')
    if code not in accepted:
        raise RuntimeError(f'Command failed ({code}): {directory / "output.log"}')
    return result

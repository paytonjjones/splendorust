"""Run a bounded command in its own process group; retain timeout as exit 124."""
import os
import signal
import subprocess
import sys
import time


def main():
    deadline = float(sys.argv[1])
    child = subprocess.Popen(sys.argv[2:], start_new_session=True)
    try:
        return child.wait(timeout=max(.01, deadline - time.time()))
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        return 124


if __name__ == '__main__':
    sys.exit(main())

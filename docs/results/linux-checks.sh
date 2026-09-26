#!/bin/bash
set -eu
rustc -Vv > /logs/rustc.txt
uname -a > /logs/uname.txt
rustup component add rustfmt clippy > /logs/components.txt 2>&1
git -C /tmp config --global --add safe.directory /reference
for check in fmt clippy tests build python; do
  case "$check" in
    fmt) cmd='cargo fmt --all -- --check';;
    clippy) cmd='cargo clippy --release --locked --workspace --all-targets -- -D warnings';;
    tests) cmd='cargo test --release --locked --workspace';;
    build) cmd='cargo build --release --locked';;
    python) cmd="SPLENDOR_REFERENCE=/reference python3 -m unittest discover -s scripts -p 'test_*.py'";;
  esac
  set +e
  bash -c "$cmd" > "/logs/$check.txt" 2>&1
  code=$?
  set -e
  printf '%s\t%s\t%s\n' "$check" "$code" "$cmd" >> /logs/status.tsv
  echo "$check $code"
done

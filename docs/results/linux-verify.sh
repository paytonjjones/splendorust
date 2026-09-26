#!/bin/bash
set -u
for name in e15-7-after e15-3p-after e15-4p-after; do
 /build/release/splendor verify-report "/logs/$name.json" > "/logs/$name-verify.txt" 2>&1
 code=$?
 printf '%s\t%s\n' "$name" "$code" >> /logs/verify-status.tsv
 cat "/logs/$name-verify.txt"
done

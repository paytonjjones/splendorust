#!/usr/bin/env python3
"""Compatibility entry point for the audited paired summary."""
import argparse,json
from pathlib import Path
from summarize import summarize
if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(summarize(a.input),indent=2)+'\n')

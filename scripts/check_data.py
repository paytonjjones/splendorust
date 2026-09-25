#!/usr/bin/env python3
"""Offline check and optional cross-check against independently supplied source files."""
import argparse
import csv
import pathlib
import re

root=pathlib.Path(__file__).resolve().parents[1]
colors=['white','blue','green','red','black']
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--bouk-csv',type=pathlib.Path)
p.add_argument('--seal-csv',type=pathlib.Path)
p.add_argument('--seal-cpp',type=pathlib.Path)
a=p.parse_args()
rows=list(csv.DictReader((root/'data/cards.csv').open()))
cards=[(int(r['tier']),r['bonus'],int(r['points']),*(int(r[c]) for c in colors)) for r in rows]
assert len(cards)==90 and len(set(cards))==90
assert [sum(c[0]==tier for c in cards) for tier in [1,2,3]]==[40,30,20]
if a.bouk_csv:
    other=list(csv.DictReader(a.bouk_csv.open()))
    assert cards==[(int(r['Level']),r['Color'].lower(),int(r['PV']),*(int(r[c.title()]) for c in colors)) for r in other]
if a.seal_csv:
    other=list(csv.DictReader(a.seal_csv.open()))
    names=dict(zip('wbgrk',colors))
    assert cards==[(int(r['level']),names[r['gem']],int(r['points']),*(int(r[c] or 0) for c in 'wbgrk')) for r in other]
if a.seal_cpp:
    row=re.search(r'NOBLES_STR = \{(.*?)\}',a.seal_cpp.read_text()).group(1)
    other=[]
    for text in re.findall(r'"\[3\|(.*?)\]"',row):
        d={c:int(v) for c,v in re.findall(r'([rgbwk])(\d)',text)}
        other.append(tuple(d.get(c,0) for c in 'wbgrk'))
    ours=[tuple(int(r[c]) for c in colors) for r in csv.DictReader((root/'data/nobles.csv').open())]
    assert sorted(ours)==sorted(other)
print('Static data checks passed.')

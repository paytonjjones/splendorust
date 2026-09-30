"""Check augmentation support, labels, reproducibility and immutable base rows."""
import sys,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from encoding_views import open_views,sample_views
from flywheel_model import open_rows
files=['local/research/e54/collector-check/views.bin'];rows,_,_=open_rows(files);groups,_=open_views(files,rows)
indices=np.arange(len(rows[0]));base=np.array(rows[0],copy=True)
x=sample_views(base['x'],indices,groups[0],np.random.default_rng(42))
y=sample_views(base['x'],indices,groups[0],np.random.default_rng(42))
assert np.array_equal(x,y)
assert np.array_equal(base,rows[0])
blind=np.isin(indices,groups[0]['row']);assert np.array_equal(x[~blind],base['x'][~blind])
for index in indices[blind]:
 group=groups[0][np.searchsorted(groups[0]['row'],index)]
 assert np.array_equal(x[index],base['x'][index]) or any(np.array_equal(x[index],v) for v in group['x'])
for field in ['policy','mask','teacher','outcome']:
 assert np.array_equal(base[field],rows[0][field],equal_nan=True)
print('Same-seed views, unchanged no-blind rows, exact support, immutable base labels pass')

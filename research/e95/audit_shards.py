"""Recheck completed corpus hashes, replay receipts and legal training rows."""
import argparse,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'research'))
from flywheel_model import DTYPE,sha,check_rows
ap=argparse.ArgumentParser();ap.add_argument('--split',choices=['train','dev'],required=True);ap.add_argument('--before-offset',type=int,default=10000);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
receipts=[];total=blind=0;teacher=outcome=0.;setups=set()
for path in sorted((ROOT/'local/research/e95'/args.split).glob('*/checks.json')):
 if int(path.parent.name)>=args.before_offset:continue
 report=json.loads(path.read_text());rows=np.fromfile(path.parent/'data.bin',dtype=DTYPE);context=np.fromfile(path.parent/'data.context.bin',dtype='<f4').reshape(-1,7);check_rows(rows)
 assert len(rows)==len(context)==report['rows']==report['replay_transitions'];assert report['games']==report['completed'];assert np.isfinite(rows['teacher']).all() and np.isfinite(rows['outcome']).all()
 assert sha(path.parent/'data.bin')==report['data_sha256'] and sha(path.parent/'data.context.bin')==report['context_sha256'] and sha(path.parent/'histories.json.gz')==report['histories_sha256']
 assert (rows['mask'][rows['policy']>0]==1).all() and (rows['policy'].sum(-1)==1).all() and np.isin(rows['policy'],[0,1]).all()
 ids=set(map(int,np.unique(rows['setup'])));assert len(ids)==report['completed'] and not ids&setups;setups.update(ids)
 total+=len(rows);blind+=int((context[:,:3].sum(-1)>0).sum());teacher+=float(rows['teacher'].astype(float).sum());outcome+=float(rows['outcome'].astype(float).sum());receipts.append(dict(shard=path.parent.name,**report))
assert total>0
result=dict(split=args.split,before_offset=args.before_offset,games=len(setups),rows=total,blind_rows=blind,mean_selected_teacher_credit=teacher/total,mean_outcome_credit=outcome/total,all_complete_and_replayed=True,data_hashes_verified=True,legal_onehot_targets=True,scope='Descriptive teacher-corpus validation only',receipts=receipts)
args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='receipts'}))

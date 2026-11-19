#!/usr/bin/env python3
"""Report speedrun-style splits from existing native receipts; never launch Red."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from pokemon_red_completion.red_milestone_splits import recorded_case_splits,compare_splits

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--compare',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_bytes());required=plan.get('required_species')
    if not isinstance(required,list) or len(required)!=124:p.error('plan must declare the exact route124 species')
    doc=recorded_case_splits(args.run_dir,required_species=required)
    if args.compare:doc['comparison']=compare_splits(doc,json.loads(args.compare.read_bytes()))
    args.output.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n')
    print('Milestone | Status | Confirmed frames | Recorded phase seconds | Versus baseline frames')
    comparisons={r['id']:r for r in doc.get('comparison',{}).get('rows',[])}
    for row in doc['rows']:
        elapsed=row.get('elapsed')or{};delta=comparisons.get(row['id'],{}).get('delta')or{}
        print(f"{row['label']} | {row['status']} | {elapsed.get('frames','—')} | {round(elapsed['wall_seconds'],3)if elapsed else '—'} | {delta.get('frames','—')}")
    return 0
if __name__=='__main__':raise SystemExit(main())

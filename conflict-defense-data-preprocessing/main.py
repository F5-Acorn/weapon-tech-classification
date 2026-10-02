"""전처리 실행 진입점: 1단계(사전 매칭) ~ 4단계(result), validate, status.

입력은 수집·저장 저장소(conflict-defense-data-collection)가 만든 work/pipeline.sqlite다.
"""
import argparse,json
from contextlib import closing
from preprocessing.config import load
from preprocessing.common import run_lock,connect,require
def main():
    p=argparse.ArgumentParser(description='F5 preprocessing: 0 used / 1 not used / 2 uncertain')
    p.add_argument('stage',choices=['1','2','3','4','validate','status'])
    p.add_argument('--config',default='config.json')
    p.add_argument('--allow-pending',action='store_true')
    a=p.parse_args();cfg=load(a.config)
    with run_lock(cfg):
        with closing(connect(cfg)) as c:
            if a.stage=='1':
                from preprocessing.match import run
                report=run(c,cfg,a.allow_pending)
            elif a.stage in ('2','3','4'):
                import importlib
                module=importlib.import_module('preprocessing.'+{'2':'articles','3':'classify','4':'export'}[a.stage]);report=module.run(c,cfg)
            elif a.stage=='validate':
                require(c,4)
                from preprocessing.validate import validate
                report=validate(c,cfg)
            else:report=dict(statuses=dict(c.execute('SELECT status,COUNT(*) FROM pages GROUP BY status')),
                             finished=[k for k in ('collect1','collect2','prep1','prep2','prep3','prep4') if c.execute('SELECT 1 FROM meta WHERE key=?',(k,)).fetchone()])
        print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

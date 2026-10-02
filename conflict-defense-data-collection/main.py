"""수집·저장 실행 진입점: 1단계(후보 기사 준비), 2단계(본문 수집), status.

이 파일을 만드는 것만으로는 수집이 시작되지 않는다. 그다음은 전처리 저장소에서 실행한다.
"""
import argparse,json
from contextlib import closing
from collection.config import load
from collection.common import run_lock,connect
def main():
    p=argparse.ArgumentParser(description='F5 data collection: stage 1 candidates, stage 2 article bodies')
    p.add_argument('stage',choices=['1','2','status'])
    p.add_argument('--config',default='config.json')
    p.add_argument('--workers',type=int,default=48);p.add_argument('--limit',type=int,default=0)
    p.add_argument('--cached-db');p.add_argument('--fetch-network',action='store_true')
    a=p.parse_args();cfg=load(a.config)
    if a.stage=='2' and not a.cached_db and not a.fetch_network:p.error('Stage 2 requires --cached-db or explicit --fetch-network')
    with run_lock(cfg):
        if a.stage=='1':
            from collection.prepare import run
            report=run(cfg)
        else:
            with closing(connect(cfg)) as c:
                if a.stage=='2':
                    from collection.collect import run
                    report=run(c,cfg,a.workers,a.limit,a.cached_db,a.fetch_network)
                else:report=dict(statuses=dict(c.execute('SELECT status,COUNT(*) FROM pages GROUP BY status')))
        print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

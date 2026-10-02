"""[수집·저장 2단계] 고유 URL마다 본문을 한 번 수집해 제목·본문만 저장한다 (보고서 1.1 입력 조건).

Stage 2 only stores fetched text. It never matches names or decides usage.
"""
import collections,concurrent.futures,datetime,hashlib,json,sqlite3,zlib
from pathlib import Path
from .common import require,done,mark,atomic_json,meta,preprocessing_started
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(c,r):
    body=r.get('body') or ''
    c.execute('UPDATE pages SET status=?,title=?,body=?,error=?,fetched_at=?,final_url=?,body_sha256=? WHERE url=?',
      (r['status'],r.get('title',''),zlib.compress(body.encode('utf-8')) if body else None,r.get('error',''),now(),r.get('final_url',r['url']),hashlib.sha256(body.encode()).hexdigest(),r['url']))
def import_cache(c,cfg,path):
    path=Path(path).resolve()
    if not path.is_file():raise FileNotFoundError('Cached DB not found (relative paths are resolved from the current folder): '+str(path))
    if path==cfg.db:raise ValueError('Cache must differ from target DB')
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=60)
    source.execute('PRAGMA query_only=ON');source.execute('BEGIN')
    try:
        # The cache must belong to this exact ordered source CSV; IDs stay text.
        old=source.execute('SELECT article_id,conflict_id,published_date,url,title FROM input_rows ORDER BY row_no')
        n=0
        for expected in c.execute('SELECT article_id,conflict_id,published_date,url,title FROM input_rows ORDER BY row_no'):
            got=old.fetchone()
            if got is None or tuple('' if x is None else str(x) for x in got)!=tuple(expected):raise ValueError('Cache/input mismatch at row '+str(n+1))
            n+=1
        if old.fetchone() is not None:raise ValueError('Cache has extra input rows')
        pending=set(r[0] for r in c.execute("SELECT url FROM pages WHERE status='pending'"));copied=0
        for url,status,title,body,error,fetched in source.execute('SELECT url,status,title,body,error,fetched_at FROM pages'):
            if url not in pending or status=='pending':continue
            if status=='extracted' and not body:raise ValueError('Extracted page without stored body: '+url)
            raw=zlib.decompress(body).decode('utf-8') if body else ''
            c.execute('UPDATE pages SET status=?,title=?,body=?,error=?,fetched_at=?,final_url=?,body_sha256=? WHERE url=?',
              (status,title,body,error,fetched,url,hashlib.sha256(raw.encode()).hexdigest(),url));copied+=1
        c.commit();return copied
    finally:source.close()
def run(c,cfg,workers=48,limit=0,cached_db=None,fetch_network=False):
    require(c,1)
    # 전처리 저장소가 1단계(사전 매칭)를 시작하면 수집 결과가 고정되므로 더 수집하지 않는다.
    if preprocessing_started(c):raise RuntimeError('Matching snapshot already fixed; use a new work_dir to collect more')
    copied=import_cache(c,cfg,cached_db) if cached_db else 0
    completed=0
    if fetch_network:
        from .fetcher import fetch
        if workers<1 or limit<0:raise ValueError('Invalid workers/limit')
        domains=collections.deque(r[0] for r in c.execute("SELECT domain FROM pages WHERE status='pending' GROUP BY domain ORDER BY MIN(rowid)"))
        in_flight={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            while domains or in_flight:
                stop=(cfg.work_dir/'STOP').exists() or (limit and completed+len(in_flight)>=limit)
                while domains and len(in_flight)<workers and not stop:
                    domain=domains.popleft()
                    row=c.execute("SELECT url FROM pages WHERE status='pending' AND domain=? LIMIT 1",(domain,)).fetchone()
                    if row:
                        date=c.execute('SELECT published_date FROM input_rows WHERE url=? ORDER BY row_no LIMIT 1',(row[0],)).fetchone()[0]
                        in_flight[pool.submit(fetch,row[0],domain,date)]=domain
                    stop=(cfg.work_dir/'STOP').exists() or (limit and completed+len(in_flight)>=limit)
                if not in_flight:break
                finished,_=concurrent.futures.wait(in_flight,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in finished:
                    domain=in_flight.pop(future);save(c,future.result());completed+=1;domains.append(domain)
                if finished:
                    c.commit();atomic_json(cfg.work_dir/'progress.json',dict(collection_stage=2,session_completed=completed,statuses=dict(c.execute('SELECT status,COUNT(*) FROM pages GROUP BY status'))))
    statuses=dict(c.execute('SELECT status,COUNT(*) FROM pages GROUP BY status'))
    report=dict(cached_pages_imported=copied,network_pages_attempted=completed,statuses=statuses,collection_complete=statuses.get('pending',0)==0)
    mark(c,2,report);atomic_json(cfg.work_dir/'collect2_manifest.json',report);return report

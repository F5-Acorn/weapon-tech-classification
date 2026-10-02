"""공통 함수: 작업 DB 연결·단계 기록(meta)·잠금·SHA-256.

작업 DB(work/pipeline.sqlite)는 전처리 저장소(conflict-defense-data-preprocessing)로 넘기는 인계 파일이다.
형식은 README.md의 "작업 DB 형식"에 정리했다. 형식을 바꾸면 DB_FORMAT을 올리고 전처리 저장소도 같이 고친다.
"""
import hashlib, json, os, sqlite3, contextlib
from pathlib import Path
DB_FORMAT='f5-collection-db-v2'
ARTICLE_COLUMNS=['article_id','conflict_id','published_date','article_url','title']
def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)
def put_meta(c,key,value):
    c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
def meta(c,key):
    row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else None
# 단계 기록 키: 수집 collect1·collect2, 전처리 prep1~prep4 (같은 작업 DB의 meta 테이블을 함께 쓰므로 이름을 나눈다)
def done(c,number):return meta(c,'collect'+str(number)) is not None
def require(c,number):
    if not done(c,number):raise RuntimeError('Run collection stage '+str(number)+' first')
def mark(c,number,report):
    put_meta(c,'collect'+str(number),report);c.commit();return report
def preprocessing_started(c):return meta(c,'prep1') is not None
def connect(cfg):
    if not cfg.db.exists():raise RuntimeError('Run collection stage 1 first')
    c=sqlite3.connect(cfg.db,timeout=60)
    try:
        if meta(c,'db_format')!=DB_FORMAT:raise RuntimeError('Incompatible DB; never reuse the historical collection DB as work_dir')
    except Exception:c.close();raise
    c.execute('PRAGMA foreign_keys=ON');return c
@contextlib.contextmanager
def run_lock(cfg):
    cfg.work_dir.mkdir(parents=True,exist_ok=True)
    with (cfg.work_dir/'run.lock').open('a+b') as f:
        f.seek(0);f.write(b'1');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another stage holds the work-directory lock')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('Another stage holds the work-directory lock')
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

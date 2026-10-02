"""공통 함수: 작업 DB 연결·단계 기록(meta)·잠금·CSV 원자적 저장·SHA-256.

입력은 수집·저장 저장소(conflict-defense-data-collection)가 만든 작업 DB(work/pipeline.sqlite)다.
인계 형식은 README.md의 "작업 DB 형식"에 있다. DB_FORMAT이 다르면 읽지 않는다.
"""
import csv, hashlib, json, os, sqlite3, contextlib
from pathlib import Path
from .codes import SCHEMA
DB_FORMAT='f5-collection-db-v2'
ARTICLE_COLUMNS=['article_id','conflict_id','published_date','article_url','title']
RESULT_COLUMNS=['article_id','category_id','usage_code','evidence_sentence']
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
# 단계 기록 키: 전처리 prep1~prep4, 수집 저장소 collect1·collect2 (같은 작업 DB의 meta 테이블을 함께 쓴다)
def done(c,number):return meta(c,'prep'+str(number)) is not None
def require(c,number):
    if not done(c,number):raise RuntimeError('Run preprocessing stage '+str(number)+' first')
def mark(c,number,report):
    put_meta(c,'prep'+str(number),report);c.commit();return report
def require_collection(c):
    if meta(c,'collect2') is None:raise RuntimeError('Collection is not finished: run stages 1-2 in the collection repository first')
def connect(cfg):
    if not cfg.db.exists():raise RuntimeError('Work DB not found: run the collection repository first ('+str(cfg.db)+')')
    c=sqlite3.connect(cfg.db,timeout=60)
    try:
        if meta(c,'db_format')!=DB_FORMAT:raise RuntimeError('Incompatible DB; never reuse the historical collection DB as work_dir')
        if meta(c,'code_schema') not in (None,SCHEMA):raise RuntimeError('Incompatible DB code schema: '+str(meta(c,'code_schema')))
    except Exception:c.close();raise
    c.execute('PRAGMA foreign_keys=ON');return c
def check_sources(c,cfg,names):
    known=meta(c,'source_hashes')
    for name in names:
        if sha256(cfg.sources_dir/name)!=known[name]:raise RuntimeError('Dictionary changed after preprocessing stage 1: '+name)
DICTIONARIES=[('sipri_dictionary.csv',{'wp_name','category_id'}),('nato_dictionary.csv',{'tech_name','category_id'}),('usage_patterns.csv',{'pattern_id','base_form','trans_form'})]
def register_sources(c,cfg):
    """사전 3종의 컬럼·빈 ID를 검사하고 SHA-256을 기록한다. 이미 기록돼 있으면 바뀌지 않았는지만 확인한다."""
    if meta(c,'source_hashes') is not None:
        check_sources(c,cfg,[name for name,_ in DICTIONARIES]);return meta(c,'source_hashes')
    hashes={}
    for name,required in DICTIONARIES:
        with (cfg.sources_dir/name).open(encoding='utf-8-sig',newline='') as f:
            rd=csv.DictReader(f)
            if not required.issubset(rd.fieldnames or []):raise ValueError('Missing columns: '+name)
            count=0
            for row in rd:
                count+=1
                identifier=row.get('category_id',row.get('pattern_id',''))
                if not identifier.strip():raise ValueError('Blank dictionary ID: '+name)
            if not count:raise ValueError('Empty dictionary: '+name)
        hashes[name]=sha256(cfg.sources_dir/name)
    put_meta(c,'source_hashes',hashes);return hashes
def ensure_schema(c):
    """전처리 테이블을 만든다. 수집 저장소가 만든 meta·input_rows·pages는 건드리지 않는다."""
    c.executescript("""
    CREATE TABLE IF NOT EXISTS matched_pages(url TEXT PRIMARY KEY REFERENCES pages(url));
    CREATE TABLE IF NOT EXISTS matches(match_id INTEGER PRIMARY KEY,url TEXT REFERENCES pages(url),sentence_no INTEGER,section TEXT,category_id TEXT,matched_name TEXT,sentence TEXT,start_pos INTEGER,end_pos INTEGER,UNIQUE(url,sentence_no,section,category_id,matched_name,start_pos,end_pos));
    CREATE INDEX IF NOT EXISTS matches_url ON matches(url);
    CREATE TABLE IF NOT EXISTS selected_articles(row_no INTEGER PRIMARY KEY,article_id TEXT UNIQUE NOT NULL,conflict_id TEXT,published_date TEXT,url TEXT,title TEXT);
    CREATE INDEX IF NOT EXISTS selected_url ON selected_articles(url);
    CREATE TABLE IF NOT EXISTS article_exclusions(row_no INTEGER PRIMARY KEY,article_id TEXT,reason TEXT,retained_article_id TEXT);
    CREATE TABLE IF NOT EXISTS decisions(match_id INTEGER PRIMARY KEY REFERENCES matches(match_id),usage_code INTEGER CHECK(usage_code IN (0,1,2)),reason TEXT,pattern_ids TEXT);
    CREATE TABLE IF NOT EXISTS result_rows(article_id TEXT,category_id TEXT,usage_code INTEGER NOT NULL CHECK(usage_code IN (0,1,2)),evidence_sentence TEXT,PRIMARY KEY(article_id,category_id));
    """)
    put_meta(c,'code_schema',SCHEMA);c.commit()
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
def csv_write(path,headers,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');n=0
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(headers)
        for row in rows:w.writerow(row);n+=1
    os.replace(tmp,path);return n
def file_info(path,rows):return dict(path=str(path),rows_excluding_header=rows,bytes=path.stat().st_size,sha256=sha256(path))

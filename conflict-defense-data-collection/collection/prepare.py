"""[수집·저장 1단계] 후보 기사 CSV(BigQuery 결과)를 검사하고 새 작업 DB(pipeline.sqlite)를 만든다.

Stage 1: check the candidate CSV and create a separate, new work DB.
"""
import csv, sqlite3
from urllib.parse import urlsplit
from .common import ARTICLE_COLUMNS, DB_FORMAT, sha256, put_meta, mark, atomic_json
def run(cfg):
    cfg.work_dir.mkdir(parents=True,exist_ok=True)
    with cfg.db.open('xb'):pass
    c=sqlite3.connect(cfg.db)
    try:
        c.executescript("""
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE input_rows(row_no INTEGER PRIMARY KEY,article_id TEXT UNIQUE NOT NULL,conflict_id TEXT,published_date TEXT,url TEXT,title TEXT);
        CREATE TABLE pages(url TEXT PRIMARY KEY,domain TEXT,status TEXT NOT NULL DEFAULT 'pending',title TEXT,body BLOB,error TEXT,fetched_at TEXT,final_url TEXT,body_sha256 TEXT);
        CREATE INDEX pages_domain_status ON pages(domain,status);
        CREATE INDEX input_url ON input_rows(url);
        """)
        put_meta(c,'db_format',DB_FORMAT)
        with cfg.input_csv.open(encoding='utf-8-sig',newline='') as f:
            rd=csv.reader(f)
            if next(rd)!=ARTICLE_COLUMNS:raise ValueError('Expected exact five article columns, in documented order')
            n=0
            for n,row in enumerate(rd,1):
                if len(row)!=5 or not row[0].strip():raise ValueError('Invalid candidate row '+str(n))
                aid,conflict,date,url,title=row
                c.execute('INSERT INTO input_rows VALUES(?,?,?,?,?,?)',(n,aid,conflict,date,url,title))
                parts=urlsplit(url)
                status='pending' if parts.scheme in ('http','https') and parts.hostname else 'invalid_url'
                c.execute('INSERT OR IGNORE INTO pages(url,domain,status) VALUES(?,?,?)',(url,parts.netloc.lower(),status))
        if not n:raise ValueError('Empty input CSV')
        report=dict(input_rows=n,unique_urls=c.execute('SELECT COUNT(*) FROM pages').fetchone()[0],input_sha256=sha256(cfg.input_csv),db_format=DB_FORMAT)
        mark(c,1,report);atomic_json(cfg.work_dir/'collect1_manifest.json',report);return report
    except Exception:
        c.rollback()
        # Keep failed preparation diagnosable; choose a new work_dir after fixing input.
        raise
    finally:c.close()

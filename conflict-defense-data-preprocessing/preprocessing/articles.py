"""[전처리 2단계 · 보고서 1.1] 사전 이름이 한 번 이상 나온 기사만 articles로 확정한다 (제목 보완, 5컬럼 결측 제외, 중복 제외).

Stage 4 finalizes articles solely from name matches, missingness and duplication.
"""
import hashlib,json,re
from urllib.parse import urlsplit,urlunsplit
from .common import require,done,mark,meta,csv_write,ARTICLE_COLUMNS,file_info,atomic_json
def normalize_url(url):
    # Preserve query/scheme and encoded path bytes; do not strip tracking or decode %2F.
    backslash=bool(re.search(r'%5c|\\',url,flags=re.I))
    u=urlsplit(re.sub(r'%5c','/',url,flags=re.I).replace('\\','/'))
    path=re.sub('/+','/',u.path) if backslash and (u.hostname or '').lower().endswith('strategypage.com') else u.path
    return urlunsplit((u.scheme.lower(),u.netloc.lower(),path,u.query,''))
def complete(row):return all(x is not None and str(x).strip() for x in row)
def run(c,cfg):
    require(c,1)
    if done(c,2):return meta(c,'prep2')
    c.execute('DELETE FROM selected_articles');c.execute('DELETE FROM article_exclusions')
    signatures={}
    for url in c.execute('SELECT DISTINCT url FROM matches'):
        rows=c.execute('SELECT category_id,matched_name,sentence FROM matches WHERE url=? ORDER BY category_id,matched_name,sentence',(url[0],))
        signatures[url[0]]=hashlib.sha256(json.dumps(sorted(set(rows)),ensure_ascii=False).encode()).hexdigest()
    seen={};missing=duplicates=0
    query="""SELECT i.row_no,i.article_id,i.conflict_id,i.published_date,i.url,
       CASE WHEN trim(coalesce(p.title,''))<>'' THEN p.title ELSE i.title END
       FROM input_rows i JOIN pages p ON i.url=p.url
       WHERE p.status='extracted' AND EXISTS(SELECT 1 FROM matches m WHERE m.url=i.url)
       ORDER BY i.row_no"""
    for row in c.execute(query):
        rn,aid,conflict,date,url,title=row
        if not complete(row[1:]):
            c.execute('INSERT INTO article_exclusions VALUES(?,?,?,NULL)',(rn,aid,'missing_required_article_field'));missing+=1;continue
        # Different conflict or matching content stays separate. Observation date alone
        # does not create a second article with otherwise identical URL/title/content.
        key=(conflict,normalize_url(url),title,signatures[url])
        if key in seen:
            c.execute('INSERT INTO article_exclusions VALUES(?,?,?,?)',(rn,aid,'same_normalized_url_conflict_title_matching_content',seen[key]));duplicates+=1;continue
        seen[key]=aid;c.execute('INSERT INTO selected_articles VALUES(?,?,?,?,?,?)',row)
    path=cfg.deliverables/'articles.csv'
    count=csv_write(path,ARTICLE_COLUMNS,c.execute('SELECT article_id,conflict_id,published_date,url,title FROM selected_articles ORDER BY row_no'))
    csv_write(cfg.work_dir/'article_exclusions.csv',['source_row_no','article_id','reason','retained_article_id'],c.execute('SELECT * FROM article_exclusions ORDER BY row_no'))
    report=dict(file=file_info(path,count),excluded_missing_rows=missing,excluded_duplicate_rows=duplicates,usage_filter_applied=False,dedup_policy='same normalized URL + conflict + final title + complete category/name/matched-sentence signature; first original row retained')
    mark(c,2,report);atomic_json(cfg.work_dir/'prep2_manifest.json',report);return report

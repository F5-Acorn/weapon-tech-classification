"""[전처리 4단계 · 보고서 7장] 기사×카테고리마다 사용→비사용→불확실 우선순위로 판정 하나와 근거 문장을 남겨 result.csv를 쓴다.

Stage 6: aggregate by article/category and write validated result.csv.
"""
import json
from .common import require,done,mark,meta,csv_write,RESULT_COLUMNS,file_info,atomic_json
from .codes import PRIORITY
def grouped(c,url):
    selected={}
    query="""SELECT m.category_id,d.usage_code,m.sentence FROM matches m
      JOIN decisions d ON d.match_id=m.match_id WHERE m.url=? AND d.usage_code IS NOT NULL
      ORDER BY m.sentence_no,m.match_id"""
    for cat,code,sentence in c.execute(query,(url,)):
        if cat not in selected or PRIORITY[code]<PRIORITY[selected[cat][0]]:selected[cat]=(code,[])
        if code==selected[cat][0] and sentence not in selected[cat][1]:selected[cat][1].append(sentence)
    return [(cat,code,'\n'.join(sentences)) for cat,(code,sentences) in sorted(selected.items())]
def run(c,cfg):
    require(c,3)
    if done(c,4):
        from .validate import validate
        validate(c,cfg);return meta(c,'prep4')
    c.execute('DELETE FROM result_rows')
    for aid,url in c.execute('SELECT article_id,url FROM selected_articles ORDER BY row_no'):
        c.executemany('INSERT INTO result_rows VALUES(?,?,?,?)',((aid,*row) for row in grouped(c,url)))
    path=cfg.deliverables/'result.csv'
    count=csv_write(path,RESULT_COLUMNS,c.execute('SELECT r.* FROM selected_articles a JOIN result_rows r ON a.article_id=r.article_id ORDER BY a.row_no,r.category_id'))
    c.commit()
    from .validate import validate
    report=validate(c,cfg)
    report['result_file']=file_info(path,count)
    mark(c,4,report);atomic_json(cfg.deliverables/'manifest.json',report);return report

# -*- coding: utf-8 -*-
"""1차 — 무기/기술 사전으로 해당 단어가 포함된 문장만 추출"""
import sys, re, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import dicts as D

SRC = config.ARTICLE_TEXTS          # 0단계 산출물 (fetch_bodies.py export)
OUT = config.out_dir(sys.argv)      # 첫 인자로 출력 폴더 지정 가능

CONFLICT = {"v1_russia_ukraine": "러시아·우크라이나",
            "v2_middle_east": "중동(이란·이스라엘·미국)"}

def conflict_of(ds):
    if pd.isna(ds): return "미상"
    p = [CONFLICT.get(x, x) for x in str(ds).split("|")]
    return "복수 분쟁" if len(p) > 1 else p[0]

def main():
    config.require(SRC)
    items, idx, maxlen = D.load_item_dict()
    print(f"1차 사전: 항목 {len(items)}개 (무기 210 / 기술 114), n-gram 키 {len(idx)}개")

    meta = pd.read_csv(SRC, usecols=["article_id","domain","datasets","sqldate",
                                     "published_at","title","url"])
    pa = pd.to_datetime(meta.published_at, format="mixed", utc=True, errors="coerce")
    sq = pd.to_datetime(meta.sqldate.astype(str), format="%Y%m%d", errors="coerce")
    meta["보도일"] = pa.dt.tz_convert(None).fillna(sq).dt.date
    meta["날짜출처"] = pa.notna().map({True: "published_at", False: "GDELT 기록일"})
    meta["분쟁"] = meta.datasets.map(conflict_of)
    M = meta.set_index("article_id")[["보도일","날짜출처","분쟁","domain","title","url"]].to_dict("index")

    rows, blocked = [], []
    t0 = time.time(); n = 0
    reader = pd.read_csv(SRC, usecols=["article_id","body"], chunksize=1000)
    for chunk in reader:
        for aid, bd in zip(chunk.article_id, chunk.body.fillna("")):
            n += 1
            if not bd: continue
            m = M.get(aid)
            if not m: continue
            pos = 0
            for si, sent in enumerate(SPLIT(bd)):
                if not sent.strip(): continue
                toks, hits = D.match_terms(sent, idx, maxlen)
                if not hits: continue
                low = [t[0].lower() for t in toks]
                seen = set()
                for mt, raw, i, j in hits:
                    # ① 케이스 규칙
                    if not D.case_ok(raw, mt["case_rule"]):
                        blocked.append((aid, si, mt["std_en"], raw, f"케이스 규칙({mt['case_rule']})")); continue
                    # ② 선행어 차단
                    key = mt["surface"].lower()
                    pb = D.PREV_BLOCK.get(key)
                    if pb and i > 0 and re.sub(r"[-–]$","",low[i-1]) in pb:
                        blocked.append((aid, si, mt["std_en"], f"{toks[i-1][0]} {raw}", f"선행어 차단({low[i-1]})")); continue
                    # ③ 스팬 차단 (anti-tank 등)
                    sb = D.SPAN_BLOCK.get(key)
                    if sb:
                        around = sent[max(0,toks[i][1]-12):toks[j-1][2]]
                        if any(p.search(around) for p in sb):
                            blocked.append((aid, si, mt["std_en"], around.strip(), "결합형 차단")); continue
                    # ③-2 후행어 차단 (Quds Force 등)
                    nb = D.NEXT_BLOCK.get(mt["surface"].lower())
                    if nb and j < len(low) and low[j] in nb:
                        blocked.append((aid, si, mt["std_en"], f"{raw} {toks[j][0]}", f"후행어 차단({low[j]})")); continue
                    # ④ 순알파벳 모델명 — 종류 단어 또는 군사 단서 필요
                    if mt.get("need_cue"):
                        ctx = set(low[:i] + low[j:])
                        if not (ctx & mt["type_words"]) and not (ctx & D.MILITARY_CUES):
                            blocked.append((aid, si, mt["std_en"], raw, "모델명 단서 없음")); continue
                    k = (mt["item_id"], i, j)
                    if k in seen: continue
                    seen.add(k)
                    rows.append((m["보도일"], m["날짜출처"], m["분쟁"], aid, m["domain"],
                                 si, mt["kind"], mt["item_id"], mt["std_en"], mt["std_ko"],
                                 mt["match_type"], mt["surface"], raw,
                                 re.sub(r"\s+"," ",sent).strip(), m["title"], m["url"]))
        if n % 4000 < 1000:
            print(f"  기사 {n}건 처리  문장 {len(rows)}건  {time.time()-t0:.0f}s")

    df = pd.DataFrame(rows, columns=["보도일","날짜출처","분쟁","article_id","매체","문장번호",
                                     "구분","항목ID","표준명_en","표준명_ko","매칭유형",
                                     "사전표현","원문표현","문장","기사제목","url"])
    df = df.sort_values(["보도일","분쟁","매체","항목ID","article_id","문장번호"]).reset_index(drop=True)
    df.to_csv(OUT/"1차_무기기술_문장추출.csv", index=False, encoding="utf-8-sig")

    bl = pd.DataFrame(blocked, columns=["article_id","문장번호","표준명_en","원문표현","차단사유"])
    bl.to_csv(OUT/"1차_차단내역.csv", index=False, encoding="utf-8-sig")

    print(f"\n추출 {len(df)}건 / 문장 {df.groupby(['article_id','문장번호']).ngroups}개 / "
          f"기사 {df.article_id.nunique()}건")
    print(f"차단 {len(bl)}건")
    print(df.구분.value_counts().to_string())

_SPLIT = D.SENT_SPLIT
def SPLIT(t): return _SPLIT.split(t)

if __name__ == "__main__":
    main()

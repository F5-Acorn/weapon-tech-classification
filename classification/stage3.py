# -*- coding: utf-8 -*-
"""3차 — 대분류 매핑(대/중/소 3층) 및 종류별 집계"""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import dicts as D

OUT = config.out_dir(sys.argv)      # 1·2차와 같은 폴더를 써야 한다

DAE = {"W02": "감시·정찰", "W03": "기동", "W04": "함정", "W05": "항공",
       "W06": "화력", "W07": "방공", "W09": "우주",
       "T00": "기타", "T01": "센서", "T02": "정보통신", "T03": "제어·전자",
       "T04": "화생방", "T05": "소재", "T06": "플랫폼·구조"}


def main():
    cm = D.load_category_map()
    cm["소분류_key"] = cm["소분류_en"].str.lower().str.strip()
    cm = cm.drop_duplicates(subset=["kind", "소분류_key"])
    print(f"3차 사전: 매핑 {len(cm)}개 / 대분류 {cm.대분류코드.nunique()}개 / "
          f"중분류 {cm.중분류코드.nunique()}개")

    config.require(OUT / "2차_사용여부_판정.csv")
    o = pd.read_csv(OUT / "2차_사용여부_판정.csv")
    o["소분류_key"] = o["표준명_en"].str.lower().str.strip()
    m = o.merge(cm.rename(columns={"kind": "구분"}),
                on=["구분", "소분류_key"], how="left")
    miss = m[m.중분류코드.isna()]
    if len(miss):
        print(f"  [주의] 매핑 실패 {len(miss)}건: {sorted(miss.표준명_en.unique())}")
    m["대분류명"] = m.대분류코드.map(DAE).fillna("미매핑")
    m["소분류"] = m["표준명_en"]

    cols = ["보도일","날짜출처","분쟁","article_id","매체","문장번호","구분",
            "대분류코드","대분류명","중분류코드","중분류명","소분류","표준명_ko",
            "항목ID","매칭유형","원문표현","판정","판정근거","사용표현","표현_유형",
            "사용가능성","거리_토큰","인용동반","부정동반","문장","기사제목","url"]
    m = m[cols].sort_values(["보도일","분쟁","대분류코드","중분류코드","소분류",
                             "article_id","문장번호"])
    m.to_csv(OUT / "3차_분류매핑_문장.csv", index=False, encoding="utf-8-sig")

    use = m[m.판정 == "사용 보도"]

    def agg(df, keys, label):
        g = df.groupby(keys, dropna=False).agg(
            보도건수=("article_id", "size"),
            기사수=("article_id", "nunique"),
            소분류_종수=("소분류", "nunique"),
            최초보도일=("보도일", "min"),
            최근보도일=("보도일", "max")).reset_index()
        g = g.sort_values(["보도건수"], ascending=False)
        g.to_csv(OUT / f"3차_집계_{label}.csv", index=False, encoding="utf-8-sig")
        return g

    a1 = agg(use, ["구분","대분류코드","대분류명"], "대분류")
    a2 = agg(use, ["구분","대분류코드","대분류명","중분류코드","중분류명"], "중분류")
    a3 = use.groupby(["구분","대분류코드","대분류명","중분류코드","중분류명","소분류","표준명_ko"],
                     dropna=False).agg(
        보도건수=("article_id","size"), 기사수=("article_id","nunique"),
        최초보도일=("보도일","min"), 최근보도일=("보도일","max")).reset_index()
    a3 = a3.sort_values(["구분","대분류코드","중분류코드","보도건수"], ascending=[True,True,True,False])
    a3.to_csv(OUT / "3차_집계_소분류.csv", index=False, encoding="utf-8-sig")

    mo = use.copy()
    mo["월"] = pd.to_datetime(mo.보도일).dt.to_period("M").astype(str)
    mm = mo.groupby(["분쟁","월","구분","대분류코드","대분류명"]).agg(
        보도건수=("article_id","size"), 기사수=("article_id","nunique"),
        소분류_종수=("소분류","nunique")).reset_index().sort_values(["분쟁","월","구분","대분류코드"])
    mm.to_csv(OUT / "3차_집계_월별.csv", index=False, encoding="utf-8-sig")

    print(f"\n분류 매핑 {len(m)}건 (사용 보도 {len(use)}건)")
    print(f"\n대분류 집계 (사용 보도 기준)")
    print(a1.to_string(index=False))
    print(f"\n중분류 상위 12")
    print(a2.head(12).to_string(index=False))
    print(f"\n소분류 상위 12")
    print(a3.sort_values("보도건수", ascending=False).head(12)[
        ["구분","중분류명","소분류","표준명_ko","보도건수","기사수"]].to_string(index=False))

if __name__ == "__main__":
    main()

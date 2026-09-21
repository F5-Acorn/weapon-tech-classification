# -*- coding: utf-8 -*-
"""3차 결과를 분쟁별 폴더 / 분류 층위별 파일로 분해 — 보도일 기준 전량 나열"""
import sys, re
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

OUT  = config.out_dir(sys.argv)     # 1~3차와 같은 폴더
ROOT = OUT / "3차_분류별"

FOLDER = {"러시아·우크라이나": "러시아_우크라이나",
          "중동(이란·이스라엘·미국)": "중동",
          "복수 분쟁": "복수_분쟁"}

BASE = ["보도일","날짜출처","분쟁","구분","판정","판정근거",
        "매체","기사제목","항목ID","매칭유형","원문표현",
        "사용표현","표현_유형","사용가능성","문장","url","article_id","문장번호"]

LEVELS = {
    "대분류": (["대분류코드","대분류명"], ["중분류코드","소분류"]),
    "중분류": (["대분류코드","대분류명","중분류코드","중분류명"], ["소분류"]),
    "소분류": (["대분류코드","대분류명","중분류코드","중분류명","소분류","표준명_ko"], []),
}

def main():
    config.require(OUT / "3차_분류매핑_문장.csv")
    m = pd.read_csv(OUT / "3차_분류매핑_문장.csv")
    m["보도일"] = pd.to_datetime(m["보도일"]).dt.date
    ROOT.mkdir(parents=True, exist_ok=True)
    summary = []

    for conflict, sub in m.groupby("분쟁"):
        d = ROOT / FOLDER.get(conflict, re.sub(r"[^\w가-힣]+", "_", conflict))
        d.mkdir(parents=True, exist_ok=True)

        for label, (keys, childs) in LEVELS.items():
            # ① 보도 목록 — 분류별로 묶고 그 안에서 보도일 오름차순, 전량 나열
            cols = keys + BASE
            lst = sub[cols].sort_values(keys + ["보도일", "article_id", "문장번호"])
            lst.to_csv(d / f"{label}_보도목록.csv", index=False, encoding="utf-8-sig")

            # ② 일자별 집계 — (보도일 × 분류) 조합을 빠짐없이
            aggs = {"보도건수": ("article_id", "size"), "기사수": ("article_id", "nunique"),
                    "사용보도": ("판정", lambda s: int((s == "사용 보도").sum())),
                    "사용외언급": ("판정", lambda s: int((s == "사용 외 언급").sum())),
                    "확인필요": ("판정", lambda s: int((s == "확인 필요").sum()))}
            for c in childs:
                aggs[f"{'중분류' if c=='중분류코드' else '소분류'}_종수"] = (c, "nunique")
            day = (sub.groupby(["보도일"] + keys, dropna=False)
                      .agg(**aggs).reset_index()
                      .sort_values(["보도일"] + keys))
            day.to_csv(d / f"{label}_일자별집계.csv", index=False, encoding="utf-8-sig")

            summary.append(dict(분쟁=conflict, 폴더=d.name, 층위=label,
                                보도목록_행=len(lst),
                                분류_종수=sub[keys[0] if label=="대분류" else keys[-2]].nunique()
                                          if label != "소분류" else sub["소분류"].nunique(),
                                일자별집계_행=len(day),
                                최초보도일=str(sub["보도일"].min()),
                                최근보도일=str(sub["보도일"].max())))
        print(f"[{conflict}] -> {d.name}/  ({len(sub)}건)")

    s = pd.DataFrame(summary)
    s.to_csv(ROOT / "폴더_구성표.csv", index=False, encoding="utf-8-sig")
    print()
    print(s.to_string(index=False))

if __name__ == "__main__":
    main()

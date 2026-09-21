# -*- coding: utf-8 -*-
"""분쟁별 최종 집계 — 보도일 × 중분류, 사용 보도 + 확인 필요"""
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
INCLUDE = ["사용 보도", "확인 필요"]      # 확인 필요는 넉넉히 포함

config.require(OUT / "3차_분류매핑_문장.csv")
m = pd.read_csv(OUT / "3차_분류매핑_문장.csv")
m["보도일"] = pd.to_datetime(m["보도일"]).dt.date
sel = m[m["판정"].isin(INCLUDE)]
print(f"전체 {len(m)}건 → 대상 {len(sel)}건 "
      f"(사용 보도 {int((m.판정=='사용 보도').sum())} + 확인 필요 {int((m.판정=='확인 필요').sum())}, "
      f"사용 외 언급 {int((m.판정=='사용 외 언급').sum())}건 제외)\n")

for conflict, sub in sel.groupby("분쟁"):
    d = ROOT / FOLDER.get(conflict, re.sub(r"[^\w가-힣]+", "_", conflict))
    d.mkdir(parents=True, exist_ok=True)
    g = (sub.groupby(["구분", "보도일", "중분류코드", "중분류명"], dropna=False)
            .agg(보도건수=("article_id", "size"), 기사수=("article_id", "nunique"))
            .reset_index())
    g["_o"] = g["구분"].map({"무기": 0, "기술": 1}).fillna(9)
    g = (g.sort_values(["_o", "보도일", "중분류코드"])
          [["구분", "보도일", "중분류코드", "중분류명", "보도건수", "기사수"]])
    # 무기 / 기술 각각 별도 파일
    for k in ("무기", "기술"):
        sg = g[g["구분"] == k][["보도일", "중분류코드", "중분류명", "보도건수", "기사수"]]
        if len(sg):
            sg.to_csv(d / f"{k}_일자별집계.csv", index=False, encoding="utf-8-sig")
    g.to_csv(d / "분류_일자별집계.csv", index=False, encoding="utf-8-sig")
    print(f"[{conflict}] {d.name}/분류_일자별집계.csv  {len(g)}행")
    for k, sg in g.groupby("구분", sort=False):
        print(f"    {k}  {len(sg):5d}행  보도건수 {int(sg.보도건수.sum()):5d}  "
              f"기사수 {int(sg.기사수.sum()):5d}  중분류 {sg.중분류코드.nunique():2d}종  "
              f"{sg.보도일.min()} ~ {sg.보도일.max()}")

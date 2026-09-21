# -*- coding: utf-8 -*-
"""2차 — 사용여부 사전으로 유관 문장 추출 및 사용 보도 판정"""
import sys, re
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import dicts as D

OUT = config.out_dir(sys.argv)      # 1차와 같은 폴더를 써야 한다
MAX_DIST = 25          # 항목 언급과 사용 표현 사이 최대 토큰 거리

NEG_TYPES  = {"사용·교전 부정", "공급 부정·부인", "공급 부정·불확실성"}
ATTR_TYPES = {"발표·인용·출처"}
# 단독으로는 부정 판정 근거가 될 수 없는 기능어
WEAK_NEG = {"no", "neither", "without", "cannot", "cannot be"}

LEVEL2JUDGE = {"상": "사용 보도", "중": "확인 필요", "하": "사용 외 언급"}


def main():
    config.require(OUT / "1차_무기기술_문장추출.csv")
    df = pd.read_csv(OUT / "1차_무기기술_문장추출.csv")
    urows, uidx, umax = D.load_usage_dict()
    print(f"2차 사전: 표현 {len(urows)}개 → 활용형 전개 {int(urows.전개수.sum())}개, "
          f"n-gram 키 {len(uidx)}개")

    # 문장 단위로 사용 표현을 한 번만 찾는다
    cache = {}
    out, unmatched = [], []
    for r in df.itertuples(index=False):
        sent = str(r.문장)
        if sent not in cache:
            toks, hits = D.match_terms(sent, uidx, umax)
            cache[sent] = (toks, hits)
        toks, hits = cache[sent]

        # 이 행의 항목 표현 위치
        low = [t[0].lower() for t in toks]
        tgt = [t.lower() for t in D.TOKEN_RE.findall(str(r.원문표현))]
        pos = next((i for i in range(len(low) - len(tgt) + 1)
                    if low[i:i + len(tgt)] == tgt), 0)

        found = []
        for mt, raw, i, j in hits:
            if mt["scope"] != r.구분:
                continue
            dist = 0 if pos <= i <= pos + len(tgt) else min(abs(i - pos), abs(i - (pos + len(tgt))))
            if dist > MAX_DIST:
                continue
            found.append((mt, raw, dist))

        base = dict(보도일=r.보도일, 날짜출처=r.날짜출처, 분쟁=r.분쟁, article_id=r.article_id,
                    매체=r.매체, 문장번호=r.문장번호, 구분=r.구분, 항목ID=r.항목ID,
                    표준명_en=r.표준명_en, 표준명_ko=r.표준명_ko, 매칭유형=r.매칭유형,
                    원문표현=r.원문표현, 문장=sent, 기사제목=r.기사제목, url=r.url)
        if not found:
            unmatched.append(base)
            continue

        strong_neg = [f for f in found if f[0]["usage_type"] in NEG_TYPES
                      and f[0]["usage_term"].lower() not in WEAK_NEG]
        weak_neg   = [f for f in found if f[0]["usage_type"] in NEG_TYPES
                      and f[0]["usage_term"].lower() in WEAK_NEG]
        attr       = [f for f in found if f[0]["usage_type"] in ATTR_TYPES]
        core       = [f for f in found if f[0]["usage_type"] not in NEG_TYPES | ATTR_TYPES]

        if strong_neg:
            judge, reason, pick = "사용 외 언급", "부정 표현", strong_neg
        elif core:
            lv = min((f[0]["level"] for f in core), key=lambda x: "상중하".index(x))
            judge = LEVEL2JUDGE[lv]
            pick = [f for f in core if f[0]["level"] == lv]
            reason = f"사용가능성 {lv}"
            if judge == "사용 보도" and weak_neg and min(f[2] for f in weak_neg) <= 6:
                judge, reason = "확인 필요", "인접 부정어(±6토큰) — 검수 필요"
        elif attr:
            # 인용 표현(said/claims)만 있는 문장은 사용 여부의 근거가 되지 못한다 → 미발견 처리
            base["비고"] = "인용 표현 단독(" + ", ".join(sorted({f[1] for f in attr})) + ") — 판정 근거 없음"
            unmatched.append(base)
            continue
        else:
            judge, reason, pick = "사용 외 언급", "기능어 부정만", weak_neg or found

        pick.sort(key=lambda f: f[2])
        best = pick[0]
        out.append({**base,
                    "판정": judge, "판정근거": reason,
                    "usage_id": best[0]["usage_id"], "사용표현": best[1],
                    "사전표현_사용": best[0]["usage_term"], "표현_유형": best[0]["usage_type"],
                    "사용가능성": best[0]["level"], "거리_토큰": best[2],
                    "인용동반": bool(attr), "부정동반": bool(strong_neg or weak_neg),
                    "전체사용표현": " | ".join(sorted({f"{f[1]}({f[0]['usage_type']})" for f in found}))})

    SORT = ["보도일","분쟁","매체","항목ID","article_id","문장번호"]

    def save(rows, name):
        df = pd.DataFrame(rows)
        if len(df):
            df = df.sort_values(SORT)
        df.to_csv(OUT / name, index=False, encoding="utf-8-sig")
        return df

    o = save(out, "2차_사용여부_판정.csv")
    u = save(unmatched, "2차_사용표현_미발견.csv")

    if not len(o):
        print("\n[주의] 사용여부 판정 건이 0건입니다. "
              "1차 결과 또는 사용여부 사전을 확인하세요.")
        return

    print(f"\n유관 문장 {len(o)}건 / 미발견 {len(u)}건 "
          f"(미발견률 {len(u)/(len(o)+len(u))*100:.1f}%)")
    print(o.판정.value_counts().to_string())
    print()
    print(o.groupby(['구분','판정']).size().to_string())
    print()
    print("실제로 쓰인 사용 표현 상위 20")
    print(o.groupby(['사전표현_사용','표현_유형']).size().sort_values(ascending=False).head(20).to_string())

if __name__ == "__main__":
    main()

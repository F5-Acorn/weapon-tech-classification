# -*- coding: utf-8 -*-
"""공용 모듈 — 사전 로드 / 토큰화 / n-gram 색인 / 케이스 규칙"""
import re, sys, unicodedata
from pathlib import Path
import pandas as pd
from wordfreq import zipf_frequency

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

F_SIPRI = config.F_SIPRI          # 1차 무기 사전 (SIPRI 210)
F_NATO  = config.F_NATO           # 1차 기술 사전 (NATO 114)
F_UW    = config.F_USAGE_WEAPON   # 2차 무기 사용여부 54
F_UT    = config.F_USAGE_TECH     # 2차 기술 사용여부 34
F_MW    = config.F_MAP_WEAPON     # 3차 무기 대분류 매핑
F_MT    = config.F_MAP_TECH       # 3차 기술 대분류 매핑

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# ── 케이스 규칙 임계값 (wordfreq zipf) ──────────────────────────────
ZIPF_UPPER_ONLY = 4.0   # 이상: 원문이 전부 대문자일 때만 인정 (hard/page/smart/tank/Milan/Arthur)
ZIPF_NOT_LOWER  = 3.0   # 이상: 원문이 전부 소문자면 기각 (Taurus/Patriot/Abrams/Spear)
                        # 미만: 대소문자 무관 (Himars/Javelin/Shahed)

# ── 명백한 오탐: 바로 앞 단어 기준 차단 ─────────────────────────────
PREV_BLOCK = {
    "tank":       {"think", "fuel", "gas", "water", "storage", "oxygen", "septic",
                   "petrol", "propane", "oil", "anti", "think-tank"},
    "tanker":     {"oil", "fuel", "gas", "crude", "chemical", "lng", "lpg", "product"},
    "bomber":     {"suicide", "car"},
    "cargo ship": {"civilian", "dry", "commercial", "merchant"},
}
# 하이픈 결합형 차단 (매칭 원문 자체에 포함되면 기각)
SPAN_BLOCK = {
    "tank": (re.compile(r"anti-?\s*tank", re.I),),
}
# 약어 오탐 (시각 표기 등)
ACRONYM_BLOCK = {"AM", "PM"}

# ── 모델명 제외 목록 (팀이 직접 수정하는 파일) ─────────────────────────
def _load_model_exclude():
    f = config.F_MODEL_EXCLUDE
    if not f.exists():
        return set()
    return {str(x).strip().lower() for x in pd.read_csv(f)["모델명"].dropna()}

MODEL_EXCLUDE = _load_model_exclude()
NEXT_BLOCK = {"quds": {"force", "forces"}}

# ── 순알파벳 모델명이 통과하려면 같은 문장에 있어야 하는 일반 군사 단서 ──────
MILITARY_CUES = set("""
military army navy naval airforce troops soldier soldiers forces brigade battalion
regiment division garrison ministry defence defense commander general colonel
war warfare combat battlefield frontline offensive counteroffensive invasion
strike strikes struck attack attacked attacking bombardment shelling shelled bombing
missile missiles rocket rockets drone drones artillery mortar shell shells ammunition
munition munitions warhead launcher launchers battery batteries salvo barrage
tank tanks armour armor armoured armored infantry convoy
aircraft jet jets fighter bomber helicopter helicopters sortie sorties airstrike
warship warships frigate destroyer submarine submarines fleet corvette
radar sensor jamming interception intercept intercepted interceptor
fired firing launch launched deployed deployment destroyed downed targeted
supplied delivered shipment weapons weapon arms armaments ordnance
""".split())

CAT_STOP = {"anti", "light", "heavy", "armed", "multi", "self", "propelled", "mini",
            "system", "systems", "with", "and", "for", "type", "class", "very",
            "short", "long", "medium", "range", "unmanned", "manned", "nuclear",
            "conventional", "surface", "air", "to", "ground"}


def type_words(desc):
    """분류명에서 '무기 종류 단어'를 뽑는다 (patrol boat -> boat/boats/patrol)."""
    out = set()
    for t in TOKEN_RE.findall(desc.lower()):
        for p in re.split(r"[-/]", t):
            if len(p) > 2 and p not in CAT_STOP:
                out |= plural_forms(p)
    return out


def norm(s):
    return unicodedata.normalize("NFKC", str(s)).strip()


def tokenize(text):
    """[(원문토큰, start, end)]"""
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def plural_forms(w):
    out = {w}
    if w.isalpha():
        if w.endswith(("s", "x", "z", "ch", "sh")):
            out.add(w + "es")
        elif w.endswith("y") and len(w) > 1 and w[-2] not in "aeiou":
            out.add(w[:-1] + "ies")
        else:
            out.add(w + "s")
    elif re.search(r"[0-9]$", w):
        out.add(w + "s")
    return out


def _case_rule(surface, kind):
    """반환: 'any' | 'not_lower' | 'upper_only'.
    표준명·복합 유의어는 일반 용어이므로 규칙 면제 — 모델명·약어에만 적용한다."""
    if kind == "acronym":
        return "upper_only"
    if kind != "model":
        return "any"
    toks = TOKEN_RE.findall(surface)
    if any(re.search(r"[0-9]", t) for t in toks):
        return "any"                      # 제식번호(MiG-29, Tu-95)는 안전
    if len(toks) != 1:
        return "not_lower"                # Storm Shadow, Abu Dhabi
    z = zipf_frequency(toks[0].lower(), "en")
    if z >= ZIPF_UPPER_ONLY:
        return "upper_only"
    if z >= ZIPF_NOT_LOWER:
        return "not_lower"
    return "any"


def needs_cue(surface, kind):
    """순알파벳 모델명은 같은 문장에 종류 단어나 군사 단서가 있어야 인정."""
    if kind != "model":
        return False
    return not any(re.search(r"[0-9]", t) for t in TOKEN_RE.findall(surface))


def _add(idx, surface, meta, maxlen):
    toks = [t.lower() for t in TOKEN_RE.findall(surface)]
    if not toks:
        return maxlen
    keys = {" ".join(toks)}
    for pl in plural_forms(toks[-1]):
        keys.add(" ".join(toks[:-1] + [pl]))
    for k in keys:
        idx.setdefault(k, []).append(meta)
    return max(maxlen, len(toks))


def load_item_dict():
    """1차 사전 — 무기(SIPRI 210) + 기술(NATO 114)"""
    config.require(F_SIPRI, F_NATO)
    rows, idx, maxlen = [], {}, 1

    sip = pd.read_csv(F_SIPRI)
    sip.columns = ["desc", "desig", "syn", "ko"]
    for i, r in enumerate(sip.itertuples(index=False), 1):
        std = norm(r.desc)                                # weapon description
        ko  = "" if pd.isna(r.ko) else norm(r.ko)
        iid = f"W{i:03d}"
        rows.append(dict(item_id=iid, kind="무기", std_en=std, std_ko=ko))
        variants = [(std, "표준명", "phrase")]
        if not pd.isna(r.desig):
            for d in str(r.desig).split(","):
                d = norm(d).rstrip("-").strip()
                if d:
                    variants.append((d, "모델명", "model"))
        if not pd.isna(r.syn):
            for s in str(r.syn).split(","):
                s = norm(s)
                if s:
                    kd = "acronym" if (s.isupper() and len(s) <= 5) else "phrase"
                    variants.append((s, "유의어", kd))
        tw = type_words(std)
        for surf, mtype, kd in variants:
            if surf.upper() in ACRONYM_BLOCK:
                continue
            if kd == "model" and surf.lower() in MODEL_EXCLUDE:
                continue
            maxlen = _add(idx, surf, dict(item_id=iid, kind="무기", std_en=std, std_ko=ko,
                                          surface=surf, match_type=mtype,
                                          case_rule=_case_rule(surf, kd),
                                          need_cue=needs_cue(surf, kd), type_words=tw), maxlen)

    nato = pd.read_csv(F_NATO)
    nato.columns = ["desc", "desig", "syn", "ko"]
    nato = nato.dropna(subset=["desc"])
    for i, r in enumerate(nato.itertuples(index=False), 1):
        std = norm(r.desc)
        ko  = "" if pd.isna(r.ko) else norm(r.ko)
        iid = f"T{i:03d}"
        rows.append(dict(item_id=iid, kind="기술", std_en=std, std_ko=ko))
        variants = [(std, "표준명", "phrase")]
        if not pd.isna(r.syn):
            for s in str(r.syn).split(","):
                s = norm(s)
                if s:
                    kd = "acronym" if (s.isupper() and len(s) <= 5) else "phrase"
                    variants.append((s, "유의어", kd))
        tw = type_words(std)
        for surf, mtype, kd in variants:
            if surf.upper() in ACRONYM_BLOCK:
                continue
            maxlen = _add(idx, surf, dict(item_id=iid, kind="기술", std_en=std, std_ko=ko,
                                          surface=surf, match_type=mtype,
                                          case_rule=_case_rule(surf, kd),
                                          need_cue=needs_cue(surf, kd), type_words=tw), maxlen)

    return pd.DataFrame(rows), idx, maxlen


def load_usage_dict():
    """2차 사전 — 무기 54 + 기술 34, 활용형 전개"""
    config.require(F_UW, F_UT)
    idx, maxlen, rows = {}, 1, []
    for f, scope in ((F_UW, "무기"), (F_UT, "기술")):
        d = pd.read_excel(f)
        for r in d.itertuples(index=False):
            base = norm(r.키워드)
            forms = [base]
            if not pd.isna(r.활용형):
                forms += [norm(x) for x in str(r.활용형).split(";") if norm(x)]
            clean = []
            for f0 in forms:
                # "launches (attack/strike)" -> "launches",  "(military) exercise / drill" -> "exercise","drill"
                inner = re.findall(r"\(([^)]*)\)", f0)
                out = norm(re.sub(r"\([^)]*\)", " ", f0))
                for part in re.split(r"\s*/\s*", out):
                    part = norm(part)
                    if part and TOKEN_RE.findall(part):
                        clean.append(part)
                for iv in inner:                     # 괄호 안이 독립 표현인 경우만
                    for part in re.split(r"[/,]", iv):
                        part = norm(part)
                        if len(TOKEN_RE.findall(part)) >= 2:
                            clean.append(part)
            rows.append(dict(usage_id=r.표현_ID, scope=scope, 키워드=base,
                             표현_유형=r.표현_유형, 사용가능성=r.무기_기술_사용가능성,
                             전개수=len(set(clean))))
            for s in set(clean):
                maxlen = _add(idx, s, dict(usage_id=r.표현_ID, scope=scope, usage_term=s,
                                           usage_type=norm(r.표현_유형),
                                           level=norm(r.무기_기술_사용가능성)), maxlen)
    return pd.DataFrame(rows), idx, maxlen


def load_category_map():
    """3차 사전 — 대분류(prefix) / 중분류(코드·명) / 소분류(항목명)"""
    config.require(F_MW, F_MT)
    out = []
    for f, kind in ((F_MW, "무기"), (F_MT, "기술")):
        d = pd.read_excel(f)
        d.columns = ["code", "name"]
        d["code"] = d["code"].ffill()
        for r in d.dropna(subset=["name"]).itertuples(index=False):
            parts = str(r.code).split("\n")
            mid_code = norm(parts[0])
            mid_name = norm(parts[1]) if len(parts) > 1 else ""
            out.append(dict(kind=kind, 대분류코드=mid_code[:3],
                            중분류코드=mid_code, 중분류명=mid_name,
                            소분류_en=norm(r.name)))
    return pd.DataFrame(out)


def match_terms(sent, idx, maxlen):
    """문장에서 사전 표현을 찾는다. [(meta, matched_text, tok_i, tok_j)]"""
    toks = tokenize(sent)
    low = [t[0].lower() for t in toks]
    n, i, hits = len(toks), 0, []
    while i < n:
        best = None
        for L in range(min(maxlen, n - i), 0, -1):
            key = " ".join(low[i:i + L])
            metas = idx.get(key)
            if metas:
                best = (L, metas)
                break
        if best:
            L, metas = best
            raw = sent[toks[i][1]:toks[i + L - 1][2]]
            for meta in metas:
                hits.append((meta, raw, i, i + L))
            i += L
        else:
            i += 1
    return toks, hits


def case_ok(raw, rule):
    if rule == "any":
        return True
    letters = [c for c in raw if c.isalpha()]
    if not letters:
        return True
    if rule == "upper_only":
        return all(c.isupper() for c in letters)
    return not all(c.islower() for c in letters)      # not_lower

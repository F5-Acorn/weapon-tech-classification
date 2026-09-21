# -*- coding: utf-8 -*-
"""경로 설정 — 모든 스크립트가 여기서 경로를 가져온다.

기본값은 이 파일이 있는 폴더(리포 루트) 기준 상대경로이므로,
clone 만 하면 별도 수정 없이 동작한다.

경로를 바꾸고 싶으면 환경변수로 덮어쓴다 (코드 수정 불필요).

    Windows PowerShell:  $env:WT_OUT_DIR = "D:\\out"
    Windows CMD:         set WT_OUT_DIR=D:\out
    macOS / Linux:       export WT_OUT_DIR=~/out
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _p(env_key: str, default: Path) -> Path:
    return Path(os.environ.get(env_key, str(default))).expanduser()


# 사전 (리포에 포함, 팀이 직접 수정하는 파일)
DICT_DIR = _p("WT_DICT_DIR", ROOT / "data" / "dict")

F_SIPRI = DICT_DIR / "SIPRI_keywords_EN_simple.csv"   # 1차 무기 사전 210
F_NATO = DICT_DIR / "NATO_keywords_EN_simple.csv"     # 1차 기술 사전 114
F_USAGE_WEAPON = DICT_DIR / "usage_weapon.xlsx"       # 2차 무기 사용여부 54
F_USAGE_TECH = DICT_DIR / "usage_tech.xlsx"           # 2차 기술 사용여부 34
F_MAP_WEAPON = DICT_DIR / "map_weapon.xlsx"           # 3차 무기 대분류 매핑
F_MAP_TECH = DICT_DIR / "map_tech.xlsx"               # 3차 기술 대분류 매핑
F_MODEL_EXCLUDE = DICT_DIR / "model_exclude.csv"      # 모델명 제외 목록

# 입력 — 용량이 커서 리포에 포함하지 않는다 (.gitignore)
INPUT_DIR = _p("WT_INPUT_DIR", ROOT / "data" / "input")
ARTICLE_TEXTS = _p("WT_ARTICLE_TEXTS", INPUT_DIR / "article_texts.csv")

# 출력 — 리포에 포함하지 않는다 (.gitignore)
# 1~3차 산출물이 모두 여기 쌓이고, 분쟁별 분해 결과는 그 아래 '3차_분류별/' 에 들어간다.
OUT_DIR = _p("WT_OUT_DIR", ROOT / "out")


def out_dir(argv, idx: int = 1) -> Path:
    """스크립트 첫 인자로 출력 폴더를 받고, 없으면 기본값을 쓴다."""
    d = Path(argv[idx]).expanduser() if len(argv) > idx else OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def require(*paths: Path) -> None:
    """필요한 파일이 없으면 무엇이 없는지 알려주고 멈춘다."""
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        lines = "\n".join(f"  - {p}" for p in missing)
        raise SystemExit(
            f"[경로 오류] 다음 파일을 찾지 못했습니다:\n{lines}\n"
            f"config.py 의 경로를 확인하거나 환경변수로 지정하세요."
        )

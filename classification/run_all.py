# -*- coding: utf-8 -*-
"""1~3차 분류를 순서대로 한 번에 실행한다 (전체 2분 내외).

    python run_all.py              # config.py 의 기본 출력 폴더(out/) 사용
    python run_all.py D:\\out3      # 출력 폴더 직접 지정

0단계(본문 수집)는 별도다. fetch_bodies.py 를 먼저 끝내고 이 스크립트를 돌린다.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

HERE = Path(__file__).resolve().parent
OUT = config.out_dir(sys.argv)
STEPS = ["stage1.py", "stage2.py", "stage3.py", "stage3_split.py", "make_final.py"]


def main():
    print(f"출력 폴더: {OUT}\n")
    t0 = time.time()
    for s in STEPS:
        print(f"\n{'=' * 60}\n[{s}]\n{'=' * 60}")
        r = subprocess.run([sys.executable, str(HERE / s), str(OUT)])
        if r.returncode != 0:
            raise SystemExit(f"\n[중단] {s} 가 실패했습니다 (exit {r.returncode}).")
    print(f"\n전체 완료 — {time.time() - t0:.0f}초")


if __name__ == "__main__":
    main()

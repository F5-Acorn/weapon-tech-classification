"""판정 코드 정의 (보고서 6장): 0=사용, 1=비사용, 2=불확실. 우선순위는 사용 → 비사용 → 불확실.

This package alone uses 0=used, 1=not used, 2=uncertain from classification onward.
"""
USED=0
NOT_USED=1
UNCERTAIN=2
SCHEMA='staged-used0-notused1-uncertain2-v1'
PRIORITY={USED:0, NOT_USED:1, UNCERTAIN:2}
def preferred(codes):
    return min(codes,key=PRIORITY.__getitem__)

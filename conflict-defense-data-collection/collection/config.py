"""공통 설정: config.json의 input_csv, work_dir 경로를 읽는다 (상대 경로는 config.json 위치 기준).

전처리 저장소와 같은 config.json을 써도 된다. 이 저장소는 sources_dir를 쓰지 않는다.
"""
from dataclasses import dataclass
from pathlib import Path
import json
@dataclass(frozen=True)
class Config:
    input_csv: Path
    work_dir: Path
    @property
    def db(self): return self.work_dir/'pipeline.sqlite'
def load(path):
    path=Path(path).resolve()
    raw=json.loads(path.read_text(encoding='utf-8-sig'))
    def resolve(key):
        p=Path(raw[key]);return (path.parent/p).resolve() if not p.is_absolute() else p.resolve()
    return Config(*(resolve(k) for k in ('input_csv','work_dir')))

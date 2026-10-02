"""공통 설정: config.json의 input_csv, sources_dir, work_dir 경로를 읽는다 (상대 경로는 config.json 위치 기준).

work_dir는 수집·저장 저장소에서 쓴 것과 같은 폴더여야 한다.
"""
from dataclasses import dataclass
from pathlib import Path
import json
@dataclass(frozen=True)
class Config:
    input_csv: Path
    sources_dir: Path
    work_dir: Path
    @property
    def db(self): return self.work_dir/'pipeline.sqlite'
    @property
    def deliverables(self): return self.work_dir/'deliverables'
def load(path):
    path=Path(path).resolve()
    raw=json.loads(path.read_text(encoding='utf-8-sig'))
    def resolve(key):
        p=Path(raw[key]);return (path.parent/p).resolve() if not p.is_absolute() else p.resolve()
    return Config(*(resolve(k) for k in ('input_csv','sources_dir','work_dir')))

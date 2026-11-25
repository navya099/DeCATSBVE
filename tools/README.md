# 개발 도구 (헤드리스 실행 · 기하 검증 · 회귀 비교)

GUI 없이 자동 배치 파이프라인을 돌리고, 출력이 의도대로만 바뀌었는지 확인하는 도구입니다.
모든 명령은 저장소 루트에서 실행합니다.

## 1. 헤드리스 실행 — `tools/headless.py`

```bash
python -m tools.headless --info-dir D:/route/info --structure D:/route/info/구조물.xlsx --speed 250 --out out/run1
```

```bash
python -m tools.headless --info-dir D:/route/info --structure D:/route/info/구조물.xlsx --speed 150 --mode double --track-distance 4.4 --sub-rail 1 --out out/double
```

- `--info-dir`: BVEParser 출력 폴더 (`bve_coordinates.txt`, `curve_info.txt`, `pitch_info.txt`, `rail_info.txt`)
- `--idxlib`: 인덱스 라이브러리. Google 시트 `freeobj` 를 내보낸 CSV(`인덱스,파일명,경로`) 또는
  노선의 `.freeobj(N) 경로` 목록 txt. 없으면 출력 주석의 오브젝트 이름이 `None` 으로 나옵니다.
- `--config case.json` 으로 설정 파일을 쓸 수도 있습니다 (키 설명은 `tools/headless.py` 상단).
- 데이터셋은 GUI 와 같이 `config/` 의 표준 데이터셋을 씁니다 (`--custom-json/--custom-spandata` 로 커스텀).

출력 폴더: `main_pole.txt`, `main_wire.txt`, (`sub_pole.txt`, `sub_wire.txt`), `wires.json`(검증용),
`summary.json`(전주·경간 수, 처리 오류), `run.log`(처리 로그)

## 2. 전선 기하 검증 — `tools/verify.py`

출력된 전선을 BVE 배치 방식(시작점 + yaw + 경간)으로 다시 놓았을 때 다음 지지점에 닿는지 횡방향 오차를 계산합니다.
상선은 `rail_info.txt` 의 실제 레일 좌표(BVE 계산값)를 기준으로 비교합니다.

```bash
python -m tools.verify out/double --coord D:/route/info/bve_coordinates.txt --rail-info D:/route/info/rail_info.txt --sub-rail 1
```

## 3. 회귀 비교 — `tools/regression.py`

케이스 폴더 = `case.json`(헤드리스 설정) + `expected/`(기준 출력).

```bash
python -m tools.regression check tests/regression_cases/synthetic_single_250
```

```bash
python -m tools.regression record D:/regression/충남선_250
```

- `check`: 현재 코드 출력과 `expected/` 비교. 문자열은 정확히, 숫자는 허용오차(`--tol`, 기본 1e-6) 이내면 일치.
  `case.json` 에 `"verify": {"main_max_cm": 0.1, "sub_max_cm": 0.1}` 가 있으면 기하 오차 한도도 검사합니다.
- `record`: 현재 출력으로 `expected/` 갱신. **출력이 바뀌는 게 의도한 변경일 때만** 실행하세요.

### pytest

```bash
python -m pytest tests
```

- `tests/regression_cases/` 의 합성 노선 케이스(단선 250, 복선 오프셋 150, 복선 rail_info 150)는 항상 실행됩니다.
  합성 노선은 `tests/regression_cases/make_synthetic_route.py` 로 다시 만들 수 있습니다.
- 실제 노선 케이스는 저장소에 커밋하지 않고, 폴더를 환경변수로 지정하면 같은 테스트에 포함됩니다.

```bat
set DECATSBVE_REGRESSION_CASES=D:\regression\충남선_250;D:\regression\도시철도_복선
python -m pytest tests
```

### 실제 노선 케이스 만들기

1. 폴더를 만들고 `case.json` 작성 (경로는 절대경로 또는 `case.json` 기준 상대경로)

```json
{
  "coord": "info/bve_coordinates.txt", "curve": "info/curve_info.txt", "pitch": "info/pitch_info.txt",
  "structure": "info/구조물.xlsx", "idxlib": "프리오브젝트.txt",
  "speed": 250, "mode": "single", "main_direction": "L", "tunnel_direction": "L",
  "start": 0, "end": 90850,
  "verify": {"main_max_cm": 0.1}
}
```

2. 신뢰할 수 있는 코드(예: 현재 `main`)에서 `python -m tools.regression record <폴더>` 로 기준 출력 기록
3. 이후 변경마다 `python -m tools.regression check <폴더>` 또는 pytest 로 확인

## 4. GUI 스모크 테스트 — `tools/gui_smoke.py`

실제 Tk 앱을 띄워 편집 동작(전주 이동·삭제, 에어조인트 추가·제거, 흐름방지 추가·삭제, 상선 편집)을 실행하고,
단계마다 테이블·배치도·전선·흐름방지가 서로 일치하는지 검사합니다. 창이 잠깐 열렸다 닫힙니다.

```bash
python -m tools.gui_smoke tests/regression_cases/synthetic_double_rail_150/case.json
```

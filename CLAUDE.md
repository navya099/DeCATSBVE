# DeCATSBVE — 작업 안내 (Claude Code 용)

BVE(openBVE) 전용 전차선로(전주·브래킷·전선) 자동 배치·편집 프로그램. 입력은 BVEParser 가 노선에서 추출한
선형 파일, 출력은 BVE CSV(`.freeobj` 구문)·도면(DXF)·물량표. 사용자·주석·문서는 한국어.
자세한 문서는 `docs/` (구조·데이터 모델·입출력·확장 방법·테스트·설계 결정).

## 명령 (저장소 루트에서)

```bash
python main.py                                            # GUI (Tk)
python -m pytest tests                                    # 테스트 (합성 노선 회귀 포함)
python -m tools.headless --config tests/regression_cases/synthetic_single_250/case.json --out out/run
python -m tools.regression check tests/regression_cases/synthetic_single_250
xvfb-run -a python -m tools.gui_smoke tests/regression_cases/synthetic_double_rail_150/case.json   # GUI 스모크
ruff check --select F,E9 .                                # 미사용 import·문법 (경고 0 유지)
```

- 실제 노선 회귀 케이스는 저장소 밖: `DECATSBVE_REGRESSION_CASES=<폴더>;<폴더>` (Windows `;`, Linux `:`)
- 도면(DXF)·미리보기 테스트는 `ezdxf`/`pyqtgraph` 가 있을 때만 실행 (없으면 skip)
- Linux 에서 GUI: `MPLBACKEND=TkAgg` (PyQt 가 있으면 matplotlib 이 Qt 백엔드를 고름), 미리보기는 `QT_QPA_PLATFORM=offscreen`

## 반드시 지킬 것

1. **편집은 코어 함수 → `rebuild(runner)` → `MODEL_CHANGED`**. GUI 는 코어 함수만 부른다.
   전주 `core/pole/pole_edit.py`, 구간 `core/section_edit.py`, 전선 `core/wire/wire_overrides.py`,
   데이터셋 `core/dataset_edit.py`. 코어 함수는 GUI 없이 동작해야 한다 (tkinter import 금지).
2. **파생 값은 직접 쓰지 않는다.** `PoleDATA.next_*`·`span` 은 이은 다음 전주에서 계산되는 속성
   (`PoleUpdator.update_all` 만 잇는다, 항상 트랙 전체 목록). 좌표·계획고·곡선·구배는 `core/pole/pole_geometry.place_on_alignment` 하나로.
3. **출력이 바뀌면 의도한 것인지 확인.** 리팩터링은 BVE CSV 바이트 동일이 원칙. 의도한 변경일 때만
   `python -m tools.regression record <케이스>` 로 기준 출력 갱신하고 PR 에 이유를 적는다.
4. **오브젝트 인덱스·치수는 데이터셋(`config/railway_*.JSON`)에.** 코드에 숫자 인덱스를 새로 고정하지 않는다.
   새 데이터셋 키는 `DatasetGetter` 에 기본값과 함께 추가 (구버전 커스텀 데이터셋 호환), `core/dataset_edit.validate` 에 검사 추가.
5. **PC 별 경로는 사용자 설정**(`file_io/user_settings.py`, `~/.decatsbve/settings.json`). `c:/temp`, `D:\...` 같은 절대 경로 금지.
6. **구성품을 만들면 `role`·`spec` 을 기록** (`enums/component_role.py`). 도면 약어·물량표가 역할을 쓴다.
7. **구버전 `.dat` 호환.** 새 필드는 기본값 있는 dataclass 필드로 추가하고, 필요하면 `core/model_rebuilder.normalize` 에서 보정.
8. **오류를 출력만 하고 넘기지 않는다.** 빠진 전주·전선은 `runner.pole_errors`/`wire_errors`, CSV 누락은 `BVECSV.errors` 로 모아 GUI 가 알린다.
9. 25m 는 BVE 블록 단위 (곡선·구배·구조물이 블록마다 정의됨) — 하드코딩된 25 는 의도된 것.

## 자주 쓰는 위치

| 무엇 | 어디 |
|---|---|
| 자동 배치 실행 | `core/runner.py` (`AutoRunner.run`), 전주 생성 `core/pole/pole_processor.py` |
| 재계산 단일 진입점 | `core/model_rebuilder.py` (`rebuild`, `normalize`) |
| 경간 길이 규칙 | `utils/comom_util.py` (`get_max_span_at`, `get_span_from`) |
| 구간 종류 등록표 | `core/section_edit.py` (`SECTION_KINDS`, `register_kind`) |
| 에어조인트·에어섹션 브래킷 / 전선 | `core/bracket/section_bracket_builder.py`, `core/wire/section_wire_base.py` |
| BVE CSV | `bve/bvecsv.py` |
| 도면 / 물량표 / 미리보기 | `core/drawing/`, `core/quantities.py`, `xref_module/preview/` |
| GUI | `gui/maingui.py`(메인), `maineditor.py`(테이블), `pole_plotter.py`(배치도), `*editor*.py`, `pole_assembler.py` |

## 작업 방식

- 브랜치에서 작업 → PR → 머지. 커밋 메시지는 한국어로 무엇·왜.
- 변경마다 pytest + (편집·화면을 건드렸으면) GUI 스모크. 새 기능에는 테스트를 같이 추가.
- 보류 중인 결정은 `docs/decisions.md` 의 "보류" 절 확인 (예: 무효전차선 경간표 인덱스 — 사용자 확인 전 바꾸지 말 것).

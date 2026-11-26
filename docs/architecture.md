# 구조

## 전체 흐름

```
입력 (BVEParser 출력·구조물 xlsx·인덱스 라이브러리·데이터셋)
  │
  ▼ AutoRunner.run()                                   core/runner.py
  ├ base_info_load / create_dictionary_by_track        선형(Alignment)·구조물·곡선·구배, 트랙별(main/sub)
  ├ distribute_pole_spacing_flexible                   전주 측점 (경간 상한 규칙, utils/comom_util.py)
  ├ define_airjoint_section                            1600m 마다 에어조인트 (단주 / 복주)
  ├ PoleProcessor.process_pole_multitrack              전주·구성품 생성 → runner.poledata
  ├ WireProcessor.process_to_wire                      경간별 전선 → runner.wire_data
  └ AnticreepingDeviceProcessor                        흐름방지장치(에어조인트 사이 가운데)
  │
  ▼ 편집 (GUI 또는 코어 함수)                            core/pole/pole_edit.py, core/section_edit.py,
  │   runner.poledata 만 고침                           core/wire/wire_overrides.py, core/dataset_edit.py
  ▼ rebuild(runner)                                    core/model_rebuilder.py
  ├ normalize            구버전 데이터 보정(uid·구간 enum·구성품 역할·선형), 다음 전주 연결
  ├ place_track          좌표·계획고·곡선·구배 다시 계산 (pole_geometry.place_on_alignment)
  ├ PoleUpdator          다음 전주 잇기 (레일 단절 구간은 잇지 않음)
  ├ WireProcessor        전선 다시 생성 (+ wire_errors)
  ├ wire_overrides.apply 전선 상세 편집(경간 uid 단위) 다시 적용
  └ 흐름방지              사용자 추가/삭제 요청 유지하고 다시 계산
  │
  ▼ MODEL_CHANGED 이벤트 → 테이블·배치도·상세 편집기 갱신
  │
  ▼ 출력: BVE CSV (bve/bvecsv.py) · 도면 (core/drawing) · 물량표 (core/quantities.py)
          · 전주 미리보기/DXF (xref_module/preview) · 저장(.dat, pickle)
```

핵심 원칙: **편집은 전주 데이터만 고치고, 파생 데이터(연결·전선·흐름방지)는 `rebuild` 하나로 처음부터 다시 만든다.**
그래서 편집 기능이 늘어도 "이 편집 뒤에 무엇을 다시 계산해야 하나"를 기능마다 챙길 필요가 없다.

## 모듈 지도

| 경로 | 역할 |
|---|---|
| `main.py` | GUI 진입점 |
| `core/runner.py`, `core/base_runner.py`, `core/manual_pole_runner.py` | 실행 상태(runner): 입력·설정·결과(poledata·wire_data)·오류 |
| `core/alignment/` | `Alignment`(측점 → 좌표·계획고·방위, 곡선·구배 조회), 상선 레일 좌표(`rail_alignment`) |
| `core/pole/` | 전주 데이터(`poledata`), 생성(`pole_processor`, 일반·곡선·터널 처리기), 편집(`pole_edit`), 선형 값(`pole_geometry`), 연결(`pole_updator`), 화면용 전주 단위(`pole_units`) |
| `core/airjoint/`, `core/airsection/`, `core/bracket/` | 에어조인트(단주·복주)·에어섹션 브래킷·설비 (공통 `section_bracket_builder`) |
| `core/mast/` | 기둥·기초·밴드 |
| `core/wire/` | 전선 생성(`wire_processor`, 구간별 `section_handler` → 에어조인트·에어섹션 공통 `section_wire_base`), 전선 상세 편집(`wire_overrides`) |
| `core/equipment/anticreepingdevice/` | 흐름방지장치·흐름방지선 |
| `core/section_edit.py` | 구간(에어조인트·에어섹션·흐름방지) 종류 등록표·조회·추가·삭제 |
| `core/dataset_edit.py`, `dataset/` | 데이터셋 읽기(`DatasetGetter`), 편집·검사 |
| `core/drawing/`, `core/quantities.py` | 평면도·종단면도(DXF), 물량표 |
| `bve/bvecsv.py` | BVE CSV 출력 (`errors` 에 누락 기록) |
| `enums/` | `SectionType`(구간), `FlowStop`, `ComponentRole`(구성품 역할) |
| `xref_module/` | 미리보기(BVE CSV 오브젝트 파서·배치·Qt 뷰어), DXF, 인덱스 라이브러리, 오브젝트 경로 |
| `file_io/` | 파일 읽기·저장, 사용자 설정(`user_settings`) |
| `gui/` | Tk 화면 (아래) |
| `vms/` | 화면용 래퍼(`EditablePole` 등, 선택 전달용) |
| `event/` | 이벤트 이름·발행기 |
| `tools/` | 헤드리스 실행·기하 검증·회귀 비교·GUI 스모크·미리보기 오브젝트 생성 |
| `assets/preview/` | 미리보기·도면용 BVE 오브젝트(배경·전철전력 라이브러리) |
| `config/` | 표준 데이터셋(설계속도 150/250/350 JSON + 경간표 xlsx) |

## GUI

| 파일 | 화면 |
|---|---|
| `gui/maingui.py` | 메인 창: 설정(설계속도·생성 모드·에어조인트 방식·도면 축척·트랙), 실행, CSV·도면 저장, 데이터 저장/로드, 유틸리티(라이브러리·데이터셋·Object 폴더·물량표) |
| `gui/maineditor.py` | 전주 테이블(복주는 -F/-B 두 행), 셀 편집·전주 추가/삭제/파일 불러오기, 편집 후 `commit_change` → `rebuild` |
| `gui/pole_plotter.py` | 배치도(클릭 선택), 전주 이동(±1m), 미리보기·DXF |
| `gui/pole_assembler.py` | 전주 상세 편집기(구성품·역할·게이지·자동 구성) |
| `gui/section_editor.py` | 구간 편집기(에어조인트·에어섹션·흐름방지) |
| `gui/wireeditor.py` | 전선 상세 편집기(지지점·전선 추가/삭제, 오브젝트 검색) |
| `gui/dataset_gui.py` | 데이터셋 편집기(설정값·경간표·검사·커스텀 저장) |

이벤트(`event/events.py`):
- `POLE_SELECTED` / `POLES_SELECTED` / `WIRE_SELECTED`: 테이블 선택 → 배치도·상세 편집기가 따라감
  (`EditablePole.which` = 복주 앞 0 / 뒤 1)
- `MODEL_CHANGED`: 데이터가 바뀐 뒤 한 번. 모든 화면은 이 이벤트로 다시 그린다 (화면끼리 직접 부르지 않음)

미리보기 창(pyqtgraph, Qt)은 Tk 앱 안에서 Qt 이벤트 루프가 돌지 않아, 배치도가 창이 열려 있는 동안 Tk 타이머로 Qt 이벤트를 처리한다.

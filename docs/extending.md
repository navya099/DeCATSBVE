# 기능 확장 방법

공통 순서: **데이터(데이터셋·enum) → 코어(GUI 없이) → rebuild/출력이 따라오는지 → GUI → 테스트**.
코어 함수는 runner 의 전주 데이터만 고치고, 화면 갱신은 호출 측이 `rebuild` 후 `MODEL_CHANGED` 로 한다.

## 1. 새 구간 종류 (예: 3경간 에어조인트, 새 에어섹션)

1. `enums/section_type.py`: 전주별 구간 값 추가 (예: `AJ3_START … AJ3_END`), 순서 튜플(`AIRJOINT_3SPAN_SEQUENCE`) 정의.
   기존 종류와 같은 처리라면 `role` 매핑으로 기존 값에 대응시킬 수 있다 (복주 `AJD_*` 참고).
   `is_airjoint`/`is_airsection` 이 새 값을 포함하는지 확인.
2. 브래킷·설비: `core/bracket/section_bracket_builder.SectionBracketBuilder` 를 상속해 전주별 규칙만 작성
   (`core/airjoint/aj_bracket_adder.py`, `core/airsection/as_bracket_adder.py` 참고 —
   `offset`/`side_offset`(데이터셋 오프셋·좌우), `add_f_bracket`, `add_paired_bracket`, `add_middle_brackets`, `add_anchor`).
   구성품에는 `role`·`spec` 이 자동으로 붙는다.
3. 전선: `core/wire/section_wire_base.SectionWireProcessor` 상속 (`aj_wire_processor.py`, `as_wire_processor.py` 참고 —
   `wires_start`, `wires_parallel_in`, `wires_crossing`, `wires_end`, 장력장치 무효선 `_rising_from_tension`/`_falling_to_tension`).
   `core/wire/section_handler.py` 에 분기 추가.
4. 데이터셋: 필요한 오프셋·인덱스를 `config/railway_*.JSON` 에 추가하고 `DatasetGetter` 에 기본값과 함께 getter,
   `core/dataset_edit.validate` 에 검사.
5. 등록: `core/section_edit.register_kind(SectionKind(id, 화면 이름, category, 용도, sequence, processor))`.
   구간 편집기(GUI)·조회·삭제·흐름방지 계산이 등록표를 따라온다.
6. 출력 위치: BVE CSV 의 브래킷 측점 규칙이 다르면 `bve/bvecsv.py` 와 `core/pole/pole_units.bracket_stations` 를 함께 고친다
   (`tests/test_drawing.py::test_bracket_stations_match_bve_csv` 가 둘이 같은지 확인).
7. 자동 배치에 쓰려면 `core/runner.py` 의 `define_airjoint_section(tags=...)` 와 실행 설정 옵션.
8. 테스트: 구간 추가·삭제 후 출력 복원(`tests/test_section_edit.py` 패턴), 브래킷·전선 위치, GUI 스모크 단계.

## 2. 새 부품·설비

1. 역할이 새로 필요하면 `enums/component_role.ComponentRole` 에 추가하고 `infer_role`(구버전·사용자 추가 추정)·
   `core/quantities.CATEGORY`(물량표 분류)에 반영.
2. 인덱스는 데이터셋 (`equipment` 등) + `DatasetGetter` getter(기본값).
3. 만드는 곳에서 `EquipmentDATA(..., type=..., role=ComponentRole.X, spec=...)`.
4. 물량표·도면·전주 편집기(역할 열)는 자동으로 따라온다.

## 3. 데이터셋 키 추가

- `config/railway_150/250/350.JSON` 세 곳에 같은 구조로 추가
- `DatasetGetter.get_*`: 키가 없을 때의 기본값 (구버전 커스텀 데이터셋 호환)
- `core/dataset_edit.validate`: 검사 (오류/경고)
- 실행 설정(UI)에서 덮어쓰는 값이면 runner 속성 + `BaseRunner.apply_dataset_options` (복주 간격 참고)

## 4. 새 출력 (도면 종류, 보고서 등)

- `runner.poledata`·`wire_data`·`alignment_for` 만 읽는 모듈로 (`core/drawing/`, `core/quantities.py` 참고). BVE CSV 와 값을 따로 계산하지 않는다.
- 위치: 실제 전주 단위는 `pole_units.units`(복주 앞·뒤), 브래킷 측점은 `bracket_stations`, 선형 점은 `Alignment.offset_point`.
- 부품 구분은 오브젝트 이름이 아니라 `role`/`spec`.
- 무거운 라이브러리(ezdxf 등)는 함수 안에서 import (없는 환경에서도 나머지가 동작하도록), 테스트는 `pytest.importorskip`.
- GUI 저장 버튼 + 헤드리스 옵션(`tools/headless.py`), 실패해도 다른 저장을 막지 않게.

## 5. 새 편집 기능

1. 코어 함수 (`core/pole/pole_edit.py` 등): 입력 검증 → 거부는 `ValueError(사용자에게 보일 문장)` → 전주 데이터 변경 → 안내 문구 목록 반환.
   - 선형 값은 `place_on_alignment`, 다음 전주 연결은 `PoleUpdator.update_all(트랙 전체)`.
   - 구간 전주를 건드리면 구간이 반쪽 남지 않는지 (`section_edit`).
2. GUI 는 코어 함수 호출 → `commit_change`(rebuild + MODEL_CHANGED) → 안내/오류 메시지.
3. 테스트: 코어 함수 단위 테스트(`tests/test_pole_edit.py` 패턴) + GUI 스모크 단계(`tools/gui_smoke.py`).

## 6. 체크리스트

- [ ] `python -m pytest tests` (실제 노선 케이스 포함 권장)
- [ ] 출력이 바뀌었다면 의도한 변경인지 확인하고 `tools.regression record`
- [ ] 편집·화면을 건드렸으면 GUI 스모크
- [ ] `ruff check --select F,E9 .` 경고 0
- [ ] 구버전 `.dat` 불러오기 (새 필드 기본값·`normalize`)
- [ ] 문서(`docs/`) 갱신

# 데이터 모델

## runner (실행 상태)

`core/base_runner.py`. GUI·헤드리스·저장(.dat)이 모두 이 객체 하나를 다룬다.

| 속성 | 내용 |
|---|---|
| `poledata` | `{'main': [PoleDATA...], 'sub': [...]}` 측점 순 |
| `wire_data` | `{'main': [WireData...], ...}` 경간(시작 전주 측점)별 전선 |
| `alignment_by_track`, `polyline_with_sta`, `offset_line_with_25` | 트랙별 선형 (`Alignment`), 상선은 rail_info 실제 레일 또는 일정 간격 오프셋 |
| `curvelist`, `pitchlist`, `structure_list` (+ `*_by_track`) | 곡선·구배·구조물 (25m 블록 단위) |
| `dataprocessor` | `DatasetGetter` (설계 데이터셋) |
| `idxlib` | 인덱스 라이브러리 (인덱스 ↔ 오브젝트 이름·경로) |
| `wire_overrides` | 전선 상세 편집 내용 (경간 uid 단위, 아래) |
| `anticreeping_pr` | 흐름방지 처리기 (사용자 추가/삭제 요청 보관) |
| `airjoint_type`, `double_pole_spacing`, `double_pole_feeder` | 에어조인트 방식(단주/복주)·복주 설정 (데이터셋보다 우선) |
| `pole_errors`, `wire_errors`, `processing_errors()` | 처리 중 빠진 전주·전선 |

`alignment_for(runner, track)` (`core/model_rebuilder.py`) 로 트랙 선형을 얻는다.

## PoleDATA (전주 = 지지점)

`core/pole/poledata.py`. 필드는 성격별로 네 가지다.

| 성격 | 필드 | 규칙 |
|---|---|---|
| 입력 | `post_number`, `pos`, `gauge`(건식게이지, 좌 −/우 +), `structure`, `section`, `base_type`(I/O/F), `side`, `track`, `flowstop`, `uid` | 편집 함수(`pole_edit`, `section_edit`)로만 바꾼다 |
| 선형 값 | `coord`, `z`, `radius`, `cant`, `pitch` | `pole_geometry.place_on_alignment` 하나로 계산. rebuild 마다 다시 계산 |
| 이웃 값 | `next_pos`, `span`, `next_gauge`, `next_structure`, `next_z`, `next_base_type`, `next_side` | **속성** — `PoleUpdator` 가 이은 다음 전주(`next_pole`)에서 바로 계산. 잇지 않은 전주(레일 단절 직전·마지막)는 생성 때 값 |
| 구성품 | `mast`(기둥·기초·밴드), `brackets`(브래킷·피팅), `equipments`, `twin`(복주 두 번째 전주) | 자동 배치가 만들고, 전주 상세 편집기로 고친다 |

- `uid`: 전주가 이동·재계산돼도 유지되는 고유 ID. 전선 편집은 `(트랙, 앞 전주 uid, 뒤 전주 uid)` 경간 키로 저장되어 전주를 옮겨도 따라간다.
- 다음 전주 연결은 `.dat` 에 저장하지 않는다 (긴 사슬은 pickle 재귀 한도를 넘음). 불러온 뒤 `normalize` 가 다시 잇는다.

### 복주(TwinPole)

복주 에어조인트 2·3·4호주는 지지점 하나(PoleDATA)에 전주 2개:
- `pole.twin = TwinPole(spacing, mast, equipments)` — 두 번째(뒤) 전주
- 브래킷은 `pole.brackets` 에 함께, `BracketDATA.on_twin` 으로 앞/뒤 구분
- 위치: 앞 전주 `pos − spacing/2`, 뒤 전주 `pos + spacing/2` (`pole.station_offsets`)
- 화면·도면용 "실제 전주 단위"는 `core/pole/pole_units.py` (`PoleUnit`, 번호 `-F`/`-B`, `bracket_stations`)

## 구성품과 역할

| 클래스 | 파일 |
|---|---|
| `Mast`(기둥, `base`, `accessories`) / `MastBase` / `MastAccessory` | `core/mast/` |
| `BracketDATA`(`bracket_type`, `stagger`, `fittings`, `on_twin`) / `FittingDATA` | `core/bracket/` |
| `EquipmentDATA`(`type`) | `core/equipment/equipment_data.py` |

공통: `index`(BVE 오브젝트 인덱스), 이름(`name`/`bracket_name`/`label`), `offset`(x, 높이), `rotation`,
**`role`·`spec`** (`enums/component_role.py`).

- `role` = 무엇인지 (`ComponentRole`: 기둥·하수강·기초·밴드·가동브래킷·F형/AJ형 브래킷·전차선/조가선 지지금구·곡선당김금구·급전선설비·평행틀·장력장치·인류장치·지선·흐름방지장치·봉강지선·기타)
- `spec` = 세부 (브래킷 I/O, 곡선당김금구 L/R, 기둥 P10/P12/H…, 밴드 상부/하부, 조가선 지지금구 무효인상용/에어조인트용)
- BVE 오브젝트 이름과 별개다. 예: 250 데이터셋의 일반 개소 브래킷은 `…-AJ-I` 오브젝트지만 역할은 "가동브래킷 I".
- 자동 배치가 만들 때 기록한다. 구버전 데이터·사용자 추가 구성품은 `infer_role`(데이터셋 인덱스 → 이름 순)로 채운다.
- 흐름방지장치·봉강지선은 흐름방지 처리기가 재계산마다 만들므로 읽기 전용.

## 구간 (SectionType)

`enums/section_type.py`. `pole.section` 값이 연속한 전주의 순서로 구간 종류를 이룬다 (`core/section_edit.SECTION_KINDS`).

| 종류 | 전주 | 값 |
|---|---|---|
| 에어조인트 2경간 (단주) | 5 | `AJ_START`, `AJ_2`, `AJ_MIDDLE`, `AJ_4`, `AJ_END` |
| 복주 에어조인트 2경간 | 5 (전주 8) | `AJD_*` — `role` 로 단주 값에 대응, 브래킷·전선 규칙 공유 |
| 에어섹션 단일 / 이중 | 5 / 8 | `AS1_1…AS1_5` / `AS1_1…AS1_4_D, AS2_1…AS2_4` |
| 흐름방지 | 3 | `pole.flowstop` (구간과 별개, `FlowStop.START/MIDDLE/END`) |

`section_role(section)` 은 복주 값을 단주 값으로 바꿔 준다 (처리기는 역할로 분기).

## 전선

- `WireData(pos, span, wires, track_name, insulators)` — 경간 하나 (`core/wire/wire_data.py`), 장간애자는 `insulators`
- `SingleWire`: `label`(전차선·본선전차선·무효전차선·무효조가선·조가선·AF·FPW·흐름방지선…), `index`, `offset`(시작 x, 높이),
  `end_point`(끝 x, 높이), `adjusted_angle`(yaw), `topdown_angle`, `station`(장력장치 구간처럼 시작 측점이 전주와 다를 때)
- 전선 상세 편집 `runner.wire_overrides`: `{(트랙, 앞 uid, 뒤 uid): {전선 키: {...}}}` — 재계산 뒤 `wire_overrides.apply` 가 다시 적용.
  전선 키는 `라벨#순번` (같은 라벨 여러 개를 구분). 흐름방지선은 읽기 전용.

## 저장(.dat)과 호환

- `file_io/filemanager.save_runner/load_runner` = runner pickle.
- 불러오면 `normalize(runner)` 가 보정: 전주 uid, 구간 문자열 → enum, section 에 있던 흐름방지 → `flowstop`,
  구성품 역할 추정, 기둥 offset 버그 복구, 선형 리스트 → `Alignment`, 다음 전주 연결.
- 새 필드는 **기본값 있는 dataclass 필드**로 추가 (구버전 객체는 클래스 기본값을 읽음). 필요하면 `normalize` 에 보정 추가.

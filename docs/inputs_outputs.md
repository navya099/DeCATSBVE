# 입력·출력

## 입력

### BVEParser 출력 (info 폴더)

[BVEParser](https://github.com/navya099/BVEParser) 가 노선(route.csv)에서 추출한다. GUI 는 info 폴더를 고르면 아래를 찾는다.

| 파일 | 내용 |
|---|---|
| `bve_alignment.txt` | **권장.** 25m 블록마다 `측점,X,Y,Z,Bearing,Radius,Cant,Pitch,height` — 좌표·곡선·구배를 한 파일로 |
| `bve_coordinates.txt`, `curve_info.txt`, `pitch_info.txt` | 예전 형식 (bve_alignment.txt 가 없을 때) |
| `rail_info.txt` | 복선 상선: 레일별 실제 좌표와 `visible`(레일이 그려지는지). 상선 레일번호를 지정하면 이 좌표를 상선 선형으로 쓰고, 레일이 끊긴 경간은 잇지 않는다. 없으면 선로중심간격만큼 일정 오프셋 |

- 25m 는 BVE 블록 단위다. 곡선·구배·구조물이 블록마다 정의되고, 측점→블록은 `get_block_index`.
- `Alignment`(`core/alignment/alignment.py`): 측점 → 좌표(`point`)·계획고(`elevation`)·오프셋 점(`offset_point`)·방위, 곡선·구배 조회.

### 구조물 (xlsx)

`교량`, `터널` 시트에 구간(이름, 시작 측점, 끝 측점). 그 밖은 토공. `isbridge_tunnel(pos, structure_list)`.

### 인덱스 라이브러리

BVE `.freeobj(N)` 인덱스 ↔ 오브젝트 이름·경로 (`xref_module/index_libmgr.IndexLibrary`, 열 `인덱스, 파일명, 경로`).

- GUI: Google 스프레드시트 `freeobj` 시트 ("라이브러리 갱신")
- 헤드리스: 위 시트를 내보낸 CSV, 또는 노선의 `.freeobj(N) 경로` 목록 txt (`tools/headless.load_index_library`)
- 경로는 BVE Object 폴더 기준 → 미리보기가 같은 이름 오브젝트를 폴더로 구분해 찾는 데 쓴다.
- 새 오브젝트를 데이터셋에 쓰면 라이브러리(시트·txt)에도 같은 인덱스를 추가해야 이름이 나온다.

### 데이터셋 (설계 기준)

표준: `config/railway_{150,250,350}.JSON` + `config/spandata_{150,250,350}.xlsx` (설계속도별, 항상 소스 폴더 `config/` 에서 읽음).
커스텀: 데이터셋 편집기에서 저장한 JSON + xlsx 를 "커스텀 모드"로 지정. 읽기는 `dataset/dataset_getter.DatasetGetter`.

| 키 | 내용 |
|---|---|
| `design` | `speed`, `prefix` |
| `mast.index` | `일반개소`/`평행개소` × 구조물 → 기둥 인덱스 (터널은 하수강) |
| `mast.gauge` | 구조물별 건식게이지 (m) |
| `mast.foundation` | 구조물별 기초 |
| `mast.band.index` / `yoffset` | `가동브래킷용`(상부·하부)·`완철용`·`기타` × 규격(P10/P12/H…) → 밴드 인덱스·높이 |
| `bracket.index` | `일반개소`/`에어조인트`/`에어섹션`/`F브래킷` × 구조물 × I/O |
| `bracket.fitting` | 전차선지지금구·조가선지지금구(일반용·에어조인트용·무효인상용)·곡선당김금구(I/O/F × L/R) |
| `feeder`, `spreader` | 구조물별 급전선설비, 평행틀(1m·1.6m) |
| `equipment` | 장력장치·지선·인류장치·장간애자·흐름방지장치·봉강지선 인덱스 (없으면 이전 고정값) |
| `wire.offset` / `system_height` | 전차선 높이(CW), AF·FPW 위치(x, y), 구조물별 가고 |
| `airjoint` / `airsection` | `offset`(F형·AJ형/AS형 시점·중간·끝 x, y), `bracket_height` |
| `airjoint.double_pole` | 복주 `spacing`(m), `feeder`(both/front). 실행 설정 입력이 우선 |
| spandata xlsx | 시트 `토공전차선`·`터널전차선`·`무효용조가선`·`무효용전차선`·`급전선`·`보호선`, 열 `이름·전선종류·길이·인덱스·가고` — 경간 길이 → 전선 오브젝트 |

데이터셋 편집기(`core/dataset_edit.py`)의 검사가 필수 키·타입·경간표를 확인한다.

### 사용자 설정 (PC 별)

`~/.decatsbve/settings.json` (`file_io/user_settings.py`, 환경변수 `DECATSBVE_SETTINGS` 로 위치 변경).
- `bve_object_root`: BVE Object 폴더 (미리보기·도면이 오브젝트를 찾는 곳, 기본 `D:\BVE\루트\Railway\Object`)

## 출력

| 출력 | 파일 | 코드 |
|---|---|---|
| BVE CSV | `전주.txt`, `전차선.txt` (복선: `상선전주.txt`, `상선전차선.txt`) — `측점,.freeobj 트랙;인덱스;x;y;yaw…` | `bve/bvecsv.py` |
| 도면 | `평면도.dxf`, `종단면도_본선.dxf` (복선 `종단면도_상선.dxf`) — 'CSV 저장' + '도면 작성 (DXF)' | `core/drawing/` |
| 물량표 | `물량표.csv` (엑셀용 UTF-8 BOM) — 유틸리티 '물량표 저장' | `core/quantities.py` |
| 전주 미리보기·DXF | 선택 전주 단면(정면) — 배치도 '전주 미리보기'·'도면 저장' | `xref_module/preview/`, `xref_module/dxf_controller/` |
| 데이터 저장 | `.dat` (runner pickle) | `file_io/filemanager.py` |
| 헤드리스 | 위 CSV(`main_pole.txt` 등) + `wires.json`(검증용) + `summary.json` + `run.log` (+ `--dxf`, `--bom`) | `tools/headless.py` |

미리보기 오브젝트 찾는 순서: 인덱스 라이브러리 경로 → BVE Object 폴더 → 저장소 `assets/preview/` (대소문자 무시) → 이름 검색.
배경(레일·건축한계·선로중심선·노반)은 Object 폴더 → `assets/preview/`. `assets/preview/README.md` 참고.

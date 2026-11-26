# 전주 미리보기·도면(DXF) 배경 오브젝트

전주 미리보기와 도면 저장에서 전주 뒤에 그리는 레일·건축한계·선로중심선·노반 단면 BVE CSV 오브젝트와 그 텍스처.
`xref_module/preview/preview_sevice.py` 의 `TRACK_OBJECT`, `CLEARANCE_OBJECT`, `CENTERLINE_OBJECT`, `STRUCTURE_OBJECTS` 가 쓴다.

찾는 순서 (`xref_module/path_resolver.py` `PathResolver.preview_object`):
1. 사용자가 지정한 BVE Object 폴더(유틸리티 > BVE Object 폴더 지정) / 원래 상대 경로
2. 이 폴더의 같은 파일명

| 파일 | 용도 | 원래 경로 (Object 폴더 기준) |
|---|---|---|
| 5M레일_신선_전차선X.csv | 레일 | 철도표준라이브러리/궤도/표준단면/자갈도상/일반철도/ |
| 건축한계.csv | 건축한계 (사용자 제공 DXF 를 tools/preview_objects.py outline 으로 변환, m 단위·선로 중심/레일면 원점) | temp/ |
| 선로중심선.csv | 선로중심선 (선로 중심 x=0, 레일면 −0.5~7m 세로 직사각형) | temp/ |
| psc거더교_단선.csv | 교량 단선 | 철도표준라이브러리/노반/교량/ |
| psc빔 복선.csv | 교량 복선 | 전라선/노반/교량/ |
| natm.csv | 터널 단선 | 동해선/노반/터널/ |
| 4.3m터널.csv | 터널 복선 | 호남선/노반/구조물/터널/ |
| 표준횡단면도.csv | 토공 단선 | 동해선/노반/토공/ |
| 6공구복선노반l.csv | 토공 복선 | 중앙선/노반/토공/ |

이미지 파일은 위 CSV 가 참조하는 텍스처 (미리보기는 형상만 사용, BVE 에서 열 때 필요).

## 전철전력/ — 전주·브래킷·금구·설비 오브젝트

BVE Object 폴더의 `철도표준라이브러리/전철전력` 과 같은 구조 (공통·일반철도·고속철도·cako250).
미리보기·도면에서 전주 구성품을 찾는 순서 (`PreviewService.find`):
1. 인덱스 라이브러리 경로(프리오브젝트 목록·구글 시트의 '경로')로 — BVE Object 폴더, 이 폴더 (대소문자 무시)
   → 같은 이름 파일이 여러 폴더(예: CAKO250/교량용, CAKO250/토공)에 있어도 정확한 파일
2. 이름 검색 — Object 폴더의 전철전력 라이브러리, 이 폴더

## 직접 만들기 (tools/preview_objects.py)

    python -m tools.preview_objects centerline assets/preview/선로중심선.csv
    python -m tools.preview_objects outline 건축한계.dxf assets/preview/건축한계.csv --scale 0.001 --origin X,Y [--layer 레이어]

outline: DXF 의 선(폴리선·선·호·원·스플라인)을 선로 방향으로 얇게(기본 0.05m) 밀어낸 띠.
mm 도면이면 --scale 0.001, --origin 은 도면에서 선로 중심·레일면 위치(도면 단위). ezdxf 필요.

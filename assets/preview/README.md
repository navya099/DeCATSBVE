# 전주 미리보기·도면(DXF) 배경 오브젝트

전주 미리보기와 도면 저장에서 전주 뒤에 그리는 레일·건축한계·선로중심선·노반 단면 BVE CSV 오브젝트와 그 텍스처.
`xref_module/preview/preview_sevice.py` 의 `TRACK_OBJECT`, `CLEARANCE_OBJECT`, `CENTERLINE_OBJECT`, `STRUCTURE_OBJECTS` 가 쓴다.

찾는 순서 (`xref_module/path_resolver.py` `PathResolver.preview_object`):
1. 사용자가 지정한 BVE Object 폴더(유틸리티 > BVE Object 폴더 지정) / 원래 상대 경로
2. 이 폴더의 같은 파일명

| 파일 | 용도 | 원래 경로 (Object 폴더 기준) |
|---|---|---|
| 5M레일_신선_전차선X.csv | 레일 | 철도표준라이브러리/궤도/표준단면/자갈도상/일반철도/ |
| 건축한계.csv | 건축한계 (현재 빈 메시) | temp/ |
| 선로중심선.csv | 선로중심선 (현재 빈 메시) | temp/ |
| psc거더교_단선.csv | 교량 단선 | 철도표준라이브러리/노반/교량/ |
| psc빔 복선.csv | 교량 복선 | 전라선/노반/교량/ |
| natm.csv | 터널 단선 | 동해선/노반/터널/ |
| 4.3m터널.csv | 터널 복선 | 호남선/노반/구조물/터널/ |
| 표준횡단면도.csv | 토공 단선 | 동해선/노반/토공/ |
| 6공구복선노반l.csv | 토공 복선 | 중앙선/노반/토공/ |

이미지 파일은 위 CSV 가 참조하는 텍스처 (미리보기는 형상만 사용, BVE 에서 열 때 필요).

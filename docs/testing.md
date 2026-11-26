# 테스트와 검증

명령과 도구 옵션은 [`tools/README.md`](../tools/README.md).

## 구성

| 종류 | 위치 | 무엇을 지키나 |
|---|---|---|
| 단위·기능 테스트 | `tests/test_*.py` | 편집 함수(전주·구간·전선·데이터셋), 경간 규칙, 선형, 역할, 연결, 파서, 미리보기 경로, 도면, 물량표, 오류 수집 |
| 출력 회귀 | `tests/test_regression.py` + `tests/regression_cases/` | 합성 노선 4개의 BVE CSV 가 기준 출력과 같은지 (숫자 허용오차), 전선 기하 오차 한도 |
| 실제 노선 회귀 | 저장소 밖 케이스 폴더 (`DECATSBVE_REGRESSION_CASES`) | 충남선·도시철도 복선 등 실제 노선 출력 |
| 재계산 불변 | `tests/test_rebuild.py` | 자동 배치 직후 rebuild 해도 출력 동일, 여러 번 해도 동일 |
| GUI 스모크 | `tools/gui_smoke.py <case.json>` | 실제 Tk 앱에서 편집 동작 후 테이블·배치도·전선·흐름방지가 서로 일치, 도면·물량표 저장 |

합성 노선(`tests/regression_cases/synthetic_route`, 생성 `tests/regression_cases/make_synthetic_route.py`): 직선·R600·R250 급곡선·구배·교량·터널, 단선/복선(오프셋·rail_info).

## 선택 의존성

- `ezdxf`: 도면·DXF 변환 테스트 (없으면 skip)
- `pyqtgraph`(+PyQt5): 미리보기 창 — 자동 테스트는 오브젝트 구성·경로까지, 창은 수동 확인
- Linux GUI: `xvfb-run -a`, `MPLBACKEND=TkAgg`, 미리보기 `QT_QPA_PLATFORM=offscreen`

## 출력이 바뀌는 변경

1. 바뀐 곳이 의도한 것인지 `tools.regression check` 출력과 `diff` 로 확인
2. 의도한 변경이면 `python -m tools.regression record <케이스>` (합성 케이스는 커밋, 실제 노선 케이스는 각자 PC 에서)
3. PR 에 어떤 출력이 왜 바뀌었는지 적기 (예: 경간 상한 규칙 변경 → 충남선 전주 1697 → 1699)

리팩터링은 **BVE CSV 바이트 동일**이 기준이다. 넓게 확인하려면 합성·실제 노선 × 단주/복주 × 에어섹션 단일·이중·에어조인트·흐름방지를
추가한 출력을 변경 전후로 저장해 `diff -r` 한다 (PR #19~#25 에서 사용한 방식).

## Windows·BVE 에서 확인할 것 (자동 테스트 밖)

- BVE 에서 노선 열기: 전주·브래킷·전선 위치, 복주 쌍 전주, 350km/h 에어섹션 오브젝트(994~999)
- 미리보기 창: 확대·이동, 닫았다 다시 열기
- CAD: 도면 레이어·글자(맑은 고딕)·종단 과장
- 엑셀: 물량표
- 구버전 `.dat` 불러오기 후 편집·저장

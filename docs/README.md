# DeCATSBVE 개발 문서

BVE 전용 전차선로 자동 배치·편집 프로그램의 개발 문서입니다. 사용법이 아니라 **코드를 고치고 기능을 넓히는 사람**을 위한 문서입니다.

| 문서 | 내용 |
|---|---|
| [architecture.md](architecture.md) | 전체 흐름(입력 → 자동 배치 → 편집 → 재계산 → 출력), 모듈 지도, GUI 이벤트 |
| [data_model.md](data_model.md) | runner·전주(PoleDATA)·구성품·역할·구간·전선·전선 편집·복주, 저장(.dat) 호환 |
| [inputs_outputs.md](inputs_outputs.md) | 입력 파일(BVEParser·구조물·인덱스 라이브러리), 데이터셋 키, 사용자 설정, 출력 파일 |
| [extending.md](extending.md) | 기능 확장 방법 (새 구간 종류, 새 부품·설비, 데이터셋 키, 새 출력, 새 편집 기능) |
| [testing.md](testing.md) | 테스트 구성, 회귀 비교, GUI 스모크, 실제 노선 케이스, Windows 확인 목록 |
| [decisions.md](decisions.md) | 설계 결정과 근거, 보류 중인 항목 |

도구 사용법(헤드리스 실행·기하 검증·회귀 비교)은 [`tools/README.md`](../tools/README.md),
AI 작업 규칙 요약은 저장소 루트의 [`CLAUDE.md`](../CLAUDE.md).

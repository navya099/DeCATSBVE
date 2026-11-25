"""EventController 이벤트 이름 (문자열 오타 방지용 상수)"""

# 선택 (편집기 → 플로터/상세 편집기)
POLE_SELECTED = "pole_selected"      # (EditablePole)
POLES_SELECTED = "poles_selected"    # (list[EditablePole]) 같은 측점의 본선+상선
WIRE_SELECTED = "wire_selected"      # (EditableWire) 선택한 경간 (전선 상세 편집기가 따라감)

# 데이터 변경: runner.poledata / wire_data 가 바뀐 뒤 한 번 발행.
# 테이블·플롯 등 모든 화면은 이 이벤트 하나로 갱신한다.
MODEL_CHANGED = "model_changed"      # ()

class EditableWire:
    """편집기에서 선택한 경간의 전선 묶음(WireData)을 가리키는 래퍼.

    전선 편집은 core.wire.wire_overrides (경간 단위 편집 내용) → rebuild() 로 한다.
    이 래퍼는 선택 상태와 앞뒤 경간 탐색만 맡는다.
    """

    def __init__(self, wire, structure_list=None, curve_list=None, pitch_list=None, polyline_with_sta=None,
                 prev_wire=None, next_wire=None):
        self.wire = wire
        self.polyline_with_sta = polyline_with_sta
        self.prev_wire = prev_wire
        self.next_wire = next_wire

    @property
    def track(self):
        return self.wire.track_name

    @property
    def pos(self):
        return self.wire.pos

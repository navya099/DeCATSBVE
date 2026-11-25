class EditablePole:
    """편집기에서 선택한 전주(PoleDATA)를 가리키는 래퍼 (앞뒤 전주 탐색용).

    전주 편집은 core.pole.pole_edit (이동·게이지·기본 타입·구성품) → rebuild() 로 한다.
    """

    def __init__(self, pole, structure_list=None, curve_list=None, pitch_list=None, polyline_with_sta=None,
                 prev_pole=None, next_pole=None):
        self.pole = pole
        self.polyline_with_sta = polyline_with_sta
        self.prev_pole = prev_pole
        self.next_pole = next_pole

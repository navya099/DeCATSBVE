from core.alignment.rail_alignment import is_span_visible


class PoleUpdator:
    @staticmethod
    def update_all(poles, alignment=None):
        """인접 전주 기준으로 next_* 속성 갱신.

        alignment 에 레일 표시 정보(RailAlignment.visible_blocks)가 있으면, 다음 전주까지의 경간에
        레일이 그려지지 않는 경우(레일 단절) 두 전주를 잇지 않고 기존 next_* 를 유지한다.
        그래야 단절 구간을 건너는 전선이 생기지 않는다 (WireProcessor 는 next_pos 가 다음 전주와 같을 때만 전선 생성).
        """
        for i, current_pole in enumerate(poles):
            next_pole = poles[i + 1] if i < len(poles) - 1 else None
            if not next_pole:
                continue
            if alignment is not None and not is_span_visible(alignment, current_pole.pos, next_pole.pos):
                continue
            current_pole.next_pos = next_pole.pos
            current_pole.span = next_pole.pos - current_pole.pos
            current_pole.next_gauge = next_pole.gauge
            current_pole.next_structure = next_pole.structure
            current_pole.next_z = next_pole.z
            current_pole.next_base_type = next_pole.base_type
            current_pole.next_side = next_pole.side

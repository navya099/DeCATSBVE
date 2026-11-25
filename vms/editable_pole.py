from core.alignment.define_funtion import iscurve, isslope
from core.structure.define_structure import isbridge_tunnel
from core.alignment.alignment import as_alignment


class EditablePole:
    def __init__(self, pole, structure_list, curve_list ,pitch_list, polyline_with_sta, prev_pole=None, next_pole=None):
        self.pole = pole
        self.structure_list = structure_list
        self.curve_list = curve_list
        self.pitch_list = pitch_list
        self.polyline_with_sta = polyline_with_sta
        self.prev_pole = prev_pole
        self.next_pole = next_pole

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.pole, key):
                setattr(self.pole, key, value)

        try:
            # 현재 전주 재계산
            self.recalculate()

            # 인접 전주 pos/next_pos 동기화
            if self.prev_pole:
                self.prev_pole.pole.next_pos = self.pole.pos
                self.prev_pole.pole.next_base_type = self.pole.base_type
                self.prev_pole.recalculate()
            if self.next_pole:
                self.next_pole.pole.pos = self.pole.next_pos
                self.next_pole.recalculate()
        except Exception as e:
            raise Exception(e)

    def recalculate(self):
        # span 갱신
        self.pole.span = self.pole.next_pos - self.pole.pos
        #좌표갱신
        alignment = as_alignment(self.polyline_with_sta)
        self.pole.coord = alignment.offset_point(self.pole.pos, self.pole.gauge)

        # z, next_z 갱신
        self.pole.z = alignment.elevation(self.pole.pos)
        self.pole.next_z = alignment.elevation(self.pole.next_pos)

        # 구조물, 곡선, 구배 등 갱신
        self.pole.structure = isbridge_tunnel(self.pole.pos, self.structure_list)
        curve, R, c = iscurve(self.pole.pos, self.curve_list)
        self.pole.radius, self.pole.cant = R, c
        slope, pitch = isslope(self.pole.pos, self.pitch_list)
        self.pole.pitch = pitch
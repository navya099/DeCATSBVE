"""에어섹션 구간 전선 (본선·무효선·장간애자)

에어섹션 = 1구간(AS1_1 ~ AS1_5, 단일 에어섹션은 여기까지) + 이중 에어섹션의 2구간(AS2_1 ~ AS2_4).
2구간은 1구간과 좌우가 반대라 오프셋 부호만 뒤집힌다 (_signed_offsets 의 second).

전주별 처리:
    AS1_1        본선 → AS 시점, 장력장치에서 오르는 무효선
    AS1_2 AS2_1  본선 (AS 시점 → 중간2), 무효선 (F 시점 → 중간1), 장간애자
    AS1_3 AS2_2  본선 → 무효선 상승 (중간2 → F 끝), 무효선 → 본선 (중간1 → AS 끝)
    AS1_4_D      본선 (AS 끝 유지), 1구간 무효선 → 장력장치, 2구간 장력장치에서 오르는 무효선
    AS1_4_S      본선 (AS 끝 → 다음 전주), 무효선 → 장력장치, 장간애자
    AS2_3        AS1_4_S 와 같고 장력장치 길이·높이만 다름
    AS1_5 AS2_4  본선 (일반 개소처럼 브래킷 편위)
"""
from core.insulator.insulator_data import InsulatorData
from core.wire.common_processor import CommonWireProcessor
from enums.section_type import SectionType
from utils.comom_util import initialrize_tenstion_device

# 무효선이 장력장치로 내려가는 구간의 장력장치 길이·높이 (AS1_4_D 1구간, AS2_3)
SHORT_TENSION = dict(tension_device_length=4, cw_height=5.638094, mw_height=6.237956)


class AirSectionWireProcessor:
    def __init__(self, compros: CommonWireProcessor, datap, al):
        self.common = compros
        self.datap = datap
        self.al = al

    # ── 공통 ────────────────────────────────────────
    def _offset(self, name):
        """데이터셋 오프셋 (x, y)"""
        value = self.datap.get_airsection_offset(name)
        return value.get('x'), value.get('y')

    def _signed_offsets(self, pole, second=False):
        """방향(side)에 맞춘 x 오프셋과 F형 높이.
        시점 쪽(AS 시점·F 시점·중간1)과 끝 쪽(중간2·AS 끝·F 끝)은 서로 반대편.
        1구간: 시점 쪽 부호 = −side, 2구간(second): +side"""
        start_sign = pole.side if second else -pole.side
        end_sign = -start_sign
        f_start_x, f_start_y = self._offset('F형_시점')
        return dict(
            as_start=self._offset('AS형_시점')[0] * start_sign,
            f_start=f_start_x * start_sign,
            middle1=self._offset('AS형_중간1')[0] * start_sign,
            middle2=self._offset('AS형_중간2')[0] * end_sign,
            as_end=self._offset('AS형_끝')[0] * end_sign,
            f_end=self._offset('F형_끝')[0] * end_sign,
            f_y=f_start_y,
        )

    def _heights(self, pole, next_pole):
        """(시작 전차선, 끝 전차선, 시작 가고, 끝 가고)"""
        d = self.datap
        return (d.get_contact_wire_height(pole.structure), d.get_contact_wire_height(next_pole.structure),
                d.get_system_height(pole.structure), d.get_system_height(next_pole.structure))

    def _wire(self, wire, index, pole, start, end, pitch_angle, label, station=None):
        w = self.common.run(self.al, index, station if station is not None else pole.pos, pole.next_pos,
                            pole.z, pole.next_z, start, end, pitch_angle, label=label)
        if station is not None:
            w.station = station
        wire.add_wire(w)

    def _insulators(self, wire, pole, dpos, x, mw_height, cw_height):
        """장간애자 (조가선·전차선 높이에 하나씩)"""
        index = self.datap.get_equipment_index('장간애자')
        for height in (mw_height, cw_height):
            wire.add_insulator(InsulatorData(pos=pole.pos + dpos, index=index, type='장간애자N-a',
                                             offset=(x, height), yaw=0, pitch=0, roll=0))

    def _rising_from_tension(self, wire, pole, pitch_angle, imw_index, icw_index, end_x, h):
        """장력장치에서 출발해 다음 전주 end_x 로 오르는 무효 조가선·전차선 (기점 측점이 앞당겨짐)"""
        scw, ecw, ssys, esys = h['heights']
        _, _, th1, th2, parallel_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, scw, ssys, h['f_y'])
        self._wire(wire, imw_index, pole, (parallel_d, th2), (end_x, ecw + esys), pitch_angle, '무효조가선',
                   station=sta2)
        self._wire(wire, icw_index, pole, (parallel_d, th1), (end_x, ecw + h['f_y']), pitch_angle, '무효전차선',
                   station=sta2)

    def _falling_to_tension(self, wire, pole, pitch_angle, cut, start_x, h, **tension):
        """start_x 에서 다음 전주 장력장치(다음 전주 게이지)로 내려가는 무효 조가선·전차선"""
        scw, _, ssys, _ = h['heights']
        imw_index = self.datap.get_inactive_mw_span(pole.span - cut)
        icw_index = self.datap.get_inactive_cw_span(pole.span - cut)
        _, _, th1, th2, _, _ = initialrize_tenstion_device(pole.pos, pole.gauge, pole.span, scw, ssys, h['f_y'],
                                                          **tension)
        self._wire(wire, imw_index, pole, (start_x, scw + ssys), (pole.next_gauge, th2), pitch_angle, '무효조가선')
        self._wire(wire, icw_index, pole, (start_x, scw + h['f_y']), (pole.next_gauge, th1), pitch_angle,
                   '무효전차선')

    # ── 전주별 처리 ──────────────────────────────────
    def run(self, pole, next_pole, wire, pitch_angle, offset, cw_index):
        section = pole.section
        if section == SectionType.AS1_1:
            self.process_start(pole, next_pole, wire, cw_index, pitch_angle)
        elif section in (SectionType.AS1_2, SectionType.AS2_1):
            self.process_parallel_in(pole, next_pole, wire, cw_index, pitch_angle,
                                     second=section == SectionType.AS2_1)
        elif section in (SectionType.AS1_3, SectionType.AS2_2):
            self.process_crossing(pole, next_pole, wire, cw_index, pitch_angle,
                                  second=section == SectionType.AS2_2)
        elif section == SectionType.AS1_4_D:
            self.process_double_middle(pole, next_pole, wire, cw_index, pitch_angle)
        elif section == SectionType.AS1_4_S:
            self.process_parallel_out(pole, next_pole, wire, cw_index, pitch_angle, second=False, cut=7)
        elif section == SectionType.AS2_3:
            self.process_parallel_out(pole, next_pole, wire, cw_index, pitch_angle, second=True, cut=4,
                                      **SHORT_TENSION)
        elif section in (SectionType.AS1_5, SectionType.AS2_4):
            self.process_end(pole, next_pole, wire, cw_index, pitch_angle)

    def process_start(self, pole, next_pole, wire, cw_index, pitch_angle):
        """AS1_1: 본선 → AS 시점, 장력장치에서 F 시점으로 오르는 무효선"""
        o = self._signed_offsets(pole)
        h = dict(heights=self._heights(pole, next_pole), f_y=o['f_y'])
        scw, ecw, _, _ = h['heights']
        self._wire(wire, cw_index, pole, (pole.brackets[0].stagger, scw), (o['as_start'], ecw), pitch_angle,
                   '본선전차선')
        self._rising_from_tension(wire, pole, pitch_angle, self.datap.get_inactive_mw_span(pole.span - 7),
                                  self.datap.get_inactive_cw_span(pole.span - 7), o['f_start'], h)

    def process_parallel_in(self, pole, next_pole, wire, cw_index, pitch_angle, second):
        """AS1_2 / AS2_1: 본선 AS 시점 → 중간2, 무효선 F 시점 → 중간1, 장간애자"""
        o = self._signed_offsets(pole, second)
        scw, ecw, ssys, esys = self._heights(pole, next_pole)
        self._wire(wire, cw_index, pole, (o['as_start'], scw), (o['middle2'], ecw), pitch_angle, '본선전차선')
        inactive = self.datap.get_inactive_mw_span(pole.span)  # 이전 코드 그대로 전차선도 조가선 인덱스
        self._wire(wire, inactive, pole, (o['f_start'], scw + ssys), (o['middle1'], ecw + esys), pitch_angle,
                   '무효조가선')
        self._wire(wire, inactive, pole, (o['f_start'], scw + o['f_y']), (o['middle1'], ecw), pitch_angle,
                   '무효전차선')
        self._insulators(wire, pole, +2, o['f_start'], scw + ssys, scw + o['f_y'])

    def process_crossing(self, pole, next_pole, wire, cw_index, pitch_angle, second):
        """AS1_3 / AS2_2: 본선 → 무효선 상승 (중간2 → F 끝), 무효선 → 본선 (중간1 → AS 끝)"""
        o = self._signed_offsets(pole, second)
        scw, ecw, ssys, esys = self._heights(pole, next_pole)
        inactive = self.datap.get_inactive_mw_span(pole.span)  # 이전 코드 그대로 전차선도 조가선 인덱스
        self._wire(wire, inactive, pole, (o['middle2'], scw), (o['f_end'], ecw + o['f_y']), pitch_angle,
                   '무효전차선')
        self._wire(wire, inactive, pole, (o['middle2'], scw + ssys), (o['f_end'], ecw + esys), pitch_angle,
                   '무효조가선')
        self._wire(wire, cw_index, pole, (o['middle1'], scw), (o['as_end'], ecw), pitch_angle, '무효->본선전차선')

    def process_double_middle(self, pole, next_pole, wire, cw_index, pitch_angle):
        """AS1_4_D (이중 에어섹션 가운데): 본선 AS 끝 유지, 1구간 무효선 → 장력장치,
        2구간 무효선이 장력장치에서 오름 (2구간 F 시점은 1구간 기준 좌표에서 좌측일 때만 반전)"""
        o = self._signed_offsets(pole)
        h = dict(heights=self._heights(pole, next_pole), f_y=o['f_y'])
        scw, ecw, _, _ = h['heights']
        self._wire(wire, cw_index, pole, (o['as_end'], scw), (o['as_end'], ecw), pitch_angle, '본선전차선')
        self._falling_to_tension(wire, pole, pitch_angle, 4, o['f_end'], h, **SHORT_TENSION)
        second_f_start = o['f_start'] * (-1 if pole.side == -1 else 1)
        self._rising_from_tension(wire, pole, pitch_angle, self.datap.get_inactive_mw_span(pole.span - 6),
                                  self.datap.get_inactive_cw_span(pole.span - 6), second_f_start, h)

    def process_parallel_out(self, pole, next_pole, wire, cw_index, pitch_angle, second, cut, **tension):
        """AS1_4_S / AS2_3: 본선 AS 끝 → 다음 전주 편위, 무효선 F 끝 → 장력장치, 장간애자"""
        o = self._signed_offsets(pole, second)
        h = dict(heights=self._heights(pole, next_pole), f_y=o['f_y'])
        scw, ecw, ssys, _ = h['heights']
        self._wire(wire, cw_index, pole, (o['as_end'], scw), (next_pole.brackets[0].stagger, ecw), pitch_angle,
                   '본선전차선')
        self._falling_to_tension(wire, pole, pitch_angle, cut, o['f_end'], h, **tension)
        self._insulators(wire, pole, -2, o['f_end'], scw + ssys, scw + o['f_y'])

    def process_end(self, pole, next_pole, wire, cw_index, pitch_angle):
        """AS1_5 / AS2_4: 본선 (브래킷 편위 → 다음 전주 편위)"""
        scw, ecw, _, _ = self._heights(pole, next_pole)
        self._wire(wire, cw_index, pole, (pole.brackets[0].stagger, scw), (next_pole.brackets[0].stagger, ecw),
                   pitch_angle, '본선전차선')

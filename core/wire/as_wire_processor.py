from core.insulator.insulator_data import InsulatorData
from core.wire.common_processor import CommonWireProcessor
from utils.comom_util import initialrize_tenstion_device
from enums.section_type import SectionType


class AirSectionWireProcessor:
    def __init__(self, compros: CommonWireProcessor, datap, al):
        self.common = compros
        self.datap = datap
        self.al = al

    def _offset(self, name):
        """데이터셋 오프셋 (x, y)"""
        value = self.datap.get_airsection_offset(name)
        return value.get('x'), value.get('y')

    def run(self, pole, next_pole, wire, pitch_angle ,offset, cw_index):
        # 에어섹션 구간 처리
        # 무효전차선 정보 가져오기
        imw_index = self.datap.get_inactive_mw_span(pole.span - 7)
        icw_index = self.datap.get_inactive_cw_span(pole.span - 7)

        if pole.section == SectionType.AS1_1:
            self.process_section_start(pole, next_pole, wire, cw_index,icw_index, imw_index, pitch_angle)

        elif pole.section == SectionType.AS1_2:
            self.process_section_two(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS1_3:
            self.process_section_three(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS1_4_D:
            self.process_section_forth(pole, next_pole, wire, cw_index, pitch_angle)
        elif pole.section == SectionType.AS1_4_S:
            self.process_section_forth_single(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS1_5:
            self.process_end(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS2_1:
            self.process_section_five(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS2_2:
            self.process_section_six(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS2_3:
            self.process_section_seven(pole, next_pole, wire, cw_index, pitch_angle)

        elif pole.section == SectionType.AS2_4:
            self.process_end(pole, next_pole, wire, cw_index, pitch_angle)

    def process_section_start(self, pole, next_pole, wire, cw_index,icw_index, imw_index, pitch_angle):

        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')
        # 일반 구간
        if pole.side == -1:
            aj_start_x *= 1
            f_start_x *= 1
        else:
            aj_start_x *= -1
            f_start_x *= -1

        # 본선
        start_offset = pole.brackets[0].stagger
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (start_offset, start_cw_height), (aj_start_x, end_cw_height), pitch_angle, label='본선전차선')
        )
        # 무효선
        # slope_degree1=전차선 각도, slope_degree2=조가선 각도, H1=전차선높이, H2=조가선 높이
        slope_degree1, slope_degree2, h1, h2, pererall_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, start_cw_height, start_system_height, f_start_y)

        mw = self.common.run(
            self.al, imw_index, sta2, pole.next_pos, pole.z, pole.next_z,
            (pererall_d, h2), (f_start_x, end_cw_height + end_system_height), pitch_angle, label='무효조가선')

        mw.station = sta2
        wire.add_wire(mw)

        cw = self.common.run(
            self.al, icw_index, sta2, pole.next_pos, pole.z, pole.next_z,
            (pererall_d, h1), (f_start_x, end_cw_height + f_start_y), pitch_angle, label='무효전차선')
        cw.station = sta2
        wire.add_wire(cw)

    def process_section_two(self, pole, next_pole, wire, cw_index, pitch_angle):

        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')

        # 일반 구간
        if pole.side == -1:
            aj_start_x *= 1
            f_start_x *= 1
            aj_middle1_x *= 1
            aj_middle2_x *= -1
        else:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
            aj_middle2_x *= 1

        # 본선
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_start_x, start_cw_height), (aj_middle2_x, end_cw_height), pitch_angle, label='본선전차선')
        )
        # 무효선
        imw_index = self.datap.get_inactive_mw_span(pole.span)
        icw_index = self.datap.get_inactive_mw_span(pole.span)
        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_start_x, start_cw_height + start_system_height), (aj_middle1_x, end_cw_height + end_system_height),
            pitch_angle, label='무효조가선')
        )
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_start_x, start_cw_height + f_start_y), (aj_middle1_x, end_cw_height), pitch_angle, label='무효전차선')
        )
        #절연애자 설치
        insulator = InsulatorData(pos=pole.pos + 2, index=678, type='장간애자N-a', offset=(f_start_x, start_cw_height + start_system_height),yaw=0,pitch=0,roll=0)
        wire.add_insulator(insulator)
        insulator = InsulatorData(pos=pole.pos + 2, index=678, type='장간애자N-a',
                                  offset=(f_start_x, start_cw_height + f_start_y), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)

    def process_section_three(self, pole, next_pole, wire, cw_index, pitch_angle):
        f_end_x, _ = self._offset('F형_끝')
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')
        aj_end_x, _ = self._offset('AS형_끝')

        # 일반 구간
        if pole.side == -1:
            aj_start_x *= 1
            f_start_x *= 1
            aj_middle1_x *= 1
            aj_middle2_x *= -1
            aj_end_x *= -1
            f_end_x *= -1

        else:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
            aj_middle2_x *= 1
            aj_end_x *= 1
            f_end_x *= 1

        # 본선 >무효선 상승
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        # 본선 -> 무효전차선
        imw_index = self.datap.get_inactive_mw_span(pole.span)
        icw_index = self.datap.get_inactive_mw_span(pole.span)
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle2_x, start_cw_height), (f_end_x, end_cw_height + f_start_y), pitch_angle, label='무효전차선')
        )
        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle2_x, start_cw_height + start_system_height), (f_end_x, end_cw_height + end_system_height),
            pitch_angle, label='무효조가선')
        )

        # 무효선 > 본선
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle1_x, start_cw_height), (aj_end_x, end_cw_height), pitch_angle, label='무효->본선전차선')
        )
    def process_section_forth(self, pole, next_pole, wire, cw_index, pitch_angle):
        f_end_x, _ = self._offset('F형_끝')
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')
        aj_end_x, _ = self._offset('AS형_끝')
        # 일반 구간
        if pole.side == -1:
            aj_start_x *= 1
            f_start_x *= 1
            aj_middle1_x *= 1
            aj_middle2_x *= -1
            aj_end_x *= -1
            f_end_x *= -1

        else:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
            aj_middle2_x *= 1
            aj_end_x *= 1
            f_end_x *= 1
        # 본선
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_end_x, start_cw_height), (aj_end_x, end_cw_height), pitch_angle, label='본선전차선')
        )
        ###섹션 1구간 무효인상선
        # 무효선
        tension_device_length = 4
        imw_index = self.datap.get_inactive_mw_span(pole.span - tension_device_length)
        icw_index = self.datap.get_inactive_cw_span(pole.span - tension_device_length)

        # slope_degree1=전차선 각도, slope_degree2=조가선 각도, H1=전차선높이, H2=조가선 높이
        slope_degree1, slope_degree2, h1, h2, pererall_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, start_cw_height, start_system_height, f_start_y, tension_device_length=tension_device_length, cw_height=5.638094, mw_height=6.237956)

        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + start_system_height), (pole.next_gauge, h2), pitch_angle, label='무효조가선')
        )
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + f_start_y), (pole.next_gauge, h1), pitch_angle, label='무효전차선')
        )
        ###섹션 2구간 무효선
        imw_index = self.datap.get_inactive_mw_span(pole.span - 6)
        icw_index = self.datap.get_inactive_cw_span(pole.span - 6)

        #2구간 다시 처리필요
        if pole.side == -1:
            f_start_x *= -1
        # 무효선
        # slope_degree1=전차선 각도, slope_degree2=조가선 각도, H1=전차선높이, H2=조가선 높이
        slope_degree1, slope_degree2, h1, h2, pererall_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, start_cw_height, start_system_height, f_start_y)

        mw = self.common.run(
            self.al, imw_index, sta2, pole.next_pos, pole.z, pole.next_z,
            (pererall_d, h2), (f_start_x, end_cw_height + end_system_height), pitch_angle, label='무효조가선')

        mw.station = sta2
        wire.add_wire(mw)

        cw = self.common.run(
            self.al, icw_index, sta2, pole.next_pos, pole.z, pole.next_z,
            (pererall_d, h1), (f_start_x, end_cw_height + f_start_y), pitch_angle, label='무효전차선')
        cw.station = sta2
        wire.add_wire(cw)

    def process_section_forth_single(self, pole, next_pole, wire, cw_index, pitch_angle):
        f_end_x, _ = self._offset('F형_끝')
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')
        aj_end_x, _ = self._offset('AS형_끝')
        # 일반 구간
        if pole.side == -1:
            aj_start_x *= 1
            f_start_x *= 1
            aj_middle1_x *= 1
            aj_middle2_x *= -1
            aj_end_x *= -1
            f_end_x *= -1

        else:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
            aj_middle2_x *= 1
            aj_end_x *= 1
            f_end_x *= 1
        # 본선
        end_offset = next_pole.brackets[0].stagger
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_end_x, start_cw_height), (end_offset, end_cw_height), pitch_angle, label='본선전차선')
        )
        # 무효선
        tension_device_length = 7
        imw_index = self.datap.get_inactive_mw_span(pole.span - tension_device_length)
        icw_index = self.datap.get_inactive_cw_span(pole.span - tension_device_length)

        # slope_degree1=전차선 각도, slope_degree2=조가선 각도, H1=전차선높이, H2=조가선 높이
        slope_degree1, slope_degree2, h1, h2, pererall_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, start_cw_height, start_system_height, f_start_y)

        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + start_system_height), (pole.next_gauge, h2), pitch_angle, label='무효조가선')
        )
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + f_start_y), (pole.next_gauge, h1), pitch_angle, label='무효전차선')
        )
        # 절연애자 설치
        insulator = InsulatorData(pos=pole.pos - 2, index=678, type='장간애자N-a',
                                  offset=(f_end_x, start_cw_height + start_system_height), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)
        insulator = InsulatorData(pos=pole.pos - 2, index=678, type='장간애자N-a',
                                  offset=(f_end_x, start_cw_height + f_start_y), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)
    def process_section_five(self, pole, next_pole, wire, cw_index, pitch_angle):
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')

        # 일반 구간
        if pole.side == -1:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
            aj_middle2_x *= 1
        else:
            aj_start_x *= 1
            f_start_x *= 1
            aj_middle1_x *= 1
            aj_middle2_x *= -1

        # 본선
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_start_x, start_cw_height), (aj_middle2_x, end_cw_height), pitch_angle, label='본선전차선')
        )
        # 무효선
        imw_index = self.datap.get_inactive_mw_span(pole.span)
        icw_index = self.datap.get_inactive_mw_span(pole.span)
        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_start_x, start_cw_height + start_system_height), (aj_middle1_x, end_cw_height + end_system_height),
            pitch_angle, label='무효조가선')
        )
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_start_x, start_cw_height + f_start_y), (aj_middle1_x, end_cw_height), pitch_angle, label='무효전차선')
        )
        # 절연애자 설치
        insulator = InsulatorData(pos=pole.pos + 2, index=678, type='장간애자N-a',
                                  offset=(f_start_x, start_cw_height + start_system_height), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)
        insulator = InsulatorData(pos=pole.pos + 2, index=678, type='장간애자N-a',
                                  offset=(f_start_x, start_cw_height + f_start_y), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)

    def process_section_six(self, pole, next_pole, wire, cw_index, pitch_angle):
        f_end_x, _ = self._offset('F형_끝')
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        _, f_start_y = self._offset('F형_시점')
        aj_end_x, _ = self._offset('AS형_끝')

        # 일반 구간
        if pole.side == -1:
            aj_middle1_x *= -1
            aj_middle2_x *= 1
            aj_end_x *= 1
            f_end_x *= 1
        else:

            aj_middle1_x *= 1
            aj_middle2_x *= -1
            aj_end_x *= -1
            f_end_x *= -1

        # 본선 >무효선 상승
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        end_system_height = self.datap.get_system_height(next_pole.structure)
        # 본선 -> 무효전차선
        imw_index = self.datap.get_inactive_mw_span(pole.span)
        icw_index = self.datap.get_inactive_mw_span(pole.span)
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle2_x, start_cw_height), (f_end_x, end_cw_height + f_start_y), pitch_angle, label='무효전차선')
        )
        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle2_x, start_cw_height + start_system_height), (f_end_x, end_cw_height + end_system_height),
            pitch_angle, label='무효조가선')
        )

        # 무효선 > 본선
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_middle1_x, start_cw_height), (aj_end_x, end_cw_height), pitch_angle, label='무효->본선전차선')
        )
    def process_section_seven(self, pole, next_pole, wire, cw_index, pitch_angle):
        # 평행구간 전차선 오프셋
        f_end_x, _ = self._offset('F형_끝')
        aj_middle1_x, _ = self._offset('AS형_중간1')
        aj_middle2_x, _ = self._offset('AS형_중간2')
        aj_start_x, _ = self._offset('AS형_시점')
        f_start_x, f_start_y = self._offset('F형_시점')
        aj_end_x, _ = self._offset('AS형_끝')

        # 방향(side) + 터널 여부에 따라 X 좌표 반전

        # 일반 구간
        if pole.side == -1:
            aj_start_x *= -1
            f_start_x *= -1
            aj_middle1_x *= -1
        else:
            aj_middle2_x *= -1
            aj_end_x *= -1
            f_end_x *= -1

        # 본선
        end_offset = next_pole.brackets[0].stagger
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)
        start_system_height = self.datap.get_system_height(pole.structure)
        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (aj_end_x, start_cw_height), (end_offset, end_cw_height), pitch_angle, label='본선전차선')
        )
        # 무효선
        tension_device_length = 4
        imw_index = self.datap.get_inactive_mw_span(pole.span - tension_device_length)
        icw_index = self.datap.get_inactive_cw_span(pole.span - tension_device_length)

        # slope_degree1=전차선 각도, slope_degree2=조가선 각도, H1=전차선높이, H2=조가선 높이
        slope_degree1, slope_degree2, h1, h2, pererall_d, sta2 = initialrize_tenstion_device(
            pole.pos, pole.gauge, pole.span, start_cw_height, start_system_height, f_start_y, tension_device_length=tension_device_length,cw_height=5.638094, mw_height=6.237956)

        wire.add_wire(self.common.run(
            self.al, imw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + start_system_height), (pole.next_gauge, h2), pitch_angle, label='무효조가선')
        )
        wire.add_wire(self.common.run(
            self.al, icw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (f_end_x, start_cw_height + f_start_y), (pole.next_gauge, h1), pitch_angle, label='무효전차선')
        )
        # 절연애자 설치
        insulator = InsulatorData(pos=pole.pos - 2, index=678, type='장간애자N-a',
                                  offset=(f_end_x, start_cw_height + start_system_height), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)
        insulator = InsulatorData(pos=pole.pos - 2, index=678, type='장간애자N-a',
                                  offset=(f_end_x, start_cw_height + f_start_y), yaw=0, pitch=0, roll=0)
        wire.add_insulator(insulator)
    def process_end(self, pole, next_pole, wire, cw_index, pitch_angle):
        # 본선
        start_offset = pole.brackets[0].stagger
        end_offset = next_pole.brackets[0].stagger
        start_cw_height = self.datap.get_contact_wire_height(pole.structure)
        end_cw_height = self.datap.get_contact_wire_height(next_pole.structure)

        wire.add_wire(self.common.run(
            self.al, cw_index, pole.pos, pole.next_pos, pole.z, pole.next_z,
            (start_offset, start_cw_height), (end_offset, end_cw_height), pitch_angle, label='본선전차선')
        )


"""전주 데이터 변경 후 파생 데이터(전주 연결, 전선, 흐름방지장치) 재계산 — 단일 진입점

편집 동작(전주 이동/추가/삭제/값 수정, 에어조인트·에어섹션 추가/삭제, 엑셀 로드 등)은
runner.poledata 만 고친 뒤 rebuild(runner) 를 한 번 부른다. 화면 갱신은 호출 측에서
MODEL_CHANGED 이벤트로 알린다 (event/events.py).
"""
from core.equipment.anticreepingdevice.anticreeping_device_processor import AnticreepingDeviceProcessor
from core.pole.pole_updator import PoleUpdator
from core.wire.wire_processor import WireProcessor


def alignment_for(runner, track):
    """트랙 선형 (main: 본선, sub: 상선)"""
    if runner.alignment_by_track and runner.alignment_by_track.get(track) is not None:
        return runner.alignment_by_track[track]
    return runner.polyline_with_sta if track == 'main' else runner.offset_line_with_25


def rebuild(runner):
    """runner.poledata 기준으로 전주 연결 → 전선 → 흐름방지장치를 처음부터 다시 계산"""
    if not runner.poledata:
        return
    # 1) 인접 전주 연결 (next_pos, span 등). 레일 단절 구간은 잇지 않음
    for track, poles in runner.poledata.items():
        PoleUpdator.update_all(poles, alignment_for(runner, track))

    # 2) 전선 재생성
    runner.wire_processor = WireProcessor(runner.dataprocessor, runner.alignment_by_track,
                                          runner.poledata, runner.curvelist)
    runner.wire_data = runner.wire_processor.process_to_wire()

    # 3) 흐름방지장치: 사용자 추가/삭제 요청은 유지하고, 현재 배치에서 다시 계산
    anticreeping = getattr(runner, 'anticreeping_pr', None)
    if anticreeping is None:
        anticreeping = AnticreepingDeviceProcessor(runner.poledata, runner.wire_data,
                                                   runner.airjoint_list, runner.wire_processor)
        runner.anticreeping_pr = anticreeping
    anticreeping.set_data(runner.poledata, runner.wire_data, runner.wire_processor)
    anticreeping.process()

"""편집 후 재계산(core.model_rebuilder.rebuild) 테스트: python -m pytest tests"""
import contextlib
import glob
import io
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.airjoint.airjoint_processor import AirJointProcessor  # noqa: E402
from core.alignment.rail_alignment import RailAlignment  # noqa: E402
from core.model_rebuilder import alignment_for, rebuild  # noqa: E402
from core.pole.normal_section_processor import NormalSectionProcessor  # noqa: E402
from core.pole.pole_updator import PoleUpdator  # noqa: E402
from core.pole.tunnel_section_processor import TunnelSectionProcessor  # noqa: E402
from enums.airjoint_section import AirJoint  # noqa: E402
from enums.section_type import FlowStop, SectionType  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')
BUILTIN = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(CASES, '*', 'case.json')))


def run_case(name):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def outputs(runner, tmp_path, tag):
    out = tmp_path / tag
    headless.write_outputs(runner, str(out), '')
    return {f.name: f.read_text(encoding='utf-8') for f in out.iterdir() if f.suffix == '.txt'}


def quiet_rebuild(runner):
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)


def flowstop_mids(runner, track='main'):
    return [p.pos for p in runner.poledata[track] if p.flowstop == FlowStop.MIDDLE]


def set_airjoint(runner, track, mid_index):
    """편집기 add_airjoint 와 같은 변경: 연속 5개 전주에 에어조인트 구간 지정 후 처리"""
    poles = runner.poledata[track]
    tags = [AirJoint.START, AirJoint.POINT_2, AirJoint.MIDDLE, AirJoint.POINT_4, AirJoint.END]
    group = poles[mid_index - 2: mid_index + 3]
    for pole, tag in zip(group, tags):
        pole.section = tag.value
    for pole in group:
        AirJointProcessor.process(pole, alignment_for(runner, track), runner.dataprocessor, runner.idxlib)
    return group


def clear_airjoint(runner, group):
    """편집기 remove_airjoint 와 같은 변경"""
    for pole in group:
        pole.section = None
        pole.brackets, pole.mast, pole.equipments = [], None, []
        processor = TunnelSectionProcessor if pole.structure == '터널' else NormalSectionProcessor
        processor.process(pole, runner.dataprocessor, runner.idxlib)


def normal_run(poles, start=0):
    """앞뒤 2개까지 모두 일반개소인 가운데 전주 인덱스"""
    return next(i for i in range(max(2, start), len(poles) - 2)
                if all(poles[j].section is None for j in range(i - 2, i + 3)))


@pytest.mark.parametrize('case_dir', BUILTIN, ids=os.path.basename)
def test_rebuild_after_run_reproduces_output(case_dir, tmp_path):
    """자동 배치 직후 rebuild 해도 출력이 같아야 한다 (재계산 경로 = 생성 경로)"""
    runner = run_case(os.path.basename(case_dir))
    first = outputs(runner, tmp_path, 'first')
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'rebuilt') == first
    quiet_rebuild(runner)  # 여러 번 해도 동일 (상태 누적 없음)
    assert outputs(runner, tmp_path, 'rebuilt2') == first


def test_flowstop_follows_airjoint_edits():
    """에어조인트 추가 → 새 장력구간에 흐름방지 생성, 제거 → 원래대로 (이전: 처음 계산값에 고정)"""
    runner = run_case('synthetic_single_250')
    assert flowstop_mids(runner) == []  # 에어조인트 1개뿐 → 흐름방지 구간 없음

    poles = runner.poledata['main']
    existing_aj = next(i for i, p in enumerate(poles) if p.section == AirJoint.END.value)
    group = set_airjoint(runner, 'main', normal_run(poles, existing_aj + 10))
    quiet_rebuild(runner)
    mids = flowstop_mids(runner)
    assert len(mids) == 1
    assert poles[existing_aj].pos < mids[0] < group[0].pos  # 두 에어조인트 사이
    devices = [p for p in poles if any(e.type == '흐름방지장치' for e in p.equipments)]
    assert len(devices) == 2  # 시작점·끝점 전주
    wires = [w for wd in runner.wire_data['main'] for w in wd.wires if w.label == '흐름방지선']
    assert len(wires) == 2

    clear_airjoint(runner, group)
    quiet_rebuild(runner)
    assert flowstop_mids(runner) == []
    assert not any(e.type in ('흐름방지장치', '봉강지선') for p in poles for e in p.equipments)
    assert not any(w.label == '흐름방지선' for wd in runner.wire_data['main'] for w in wd.wires)


def test_manual_flowstop_requests_survive_rebuild():
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    i = normal_run(poles, 3)
    start, mid, end = poles[i - 1].pos, poles[i].pos, poles[i + 1].pos
    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.add_manual_section('main', start, end, mid)
    assert flowstop_mids(runner) == [mid]

    quiet_rebuild(runner)  # 다른 편집으로 재계산돼도 유지
    assert flowstop_mids(runner) == [mid]

    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.remove_manual_section('main', start, end, mid)
    quiet_rebuild(runner)
    assert flowstop_mids(runner) == []


def test_flowstop_does_not_overwrite_airjoint_section():
    """흐름방지 구간이 짧아 에어조인트 끝/시작 전주와 겹쳐도 에어조인트 태그는 유지"""
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    end = next(i for i, p in enumerate(poles) if p.section == AirJoint.END.value)
    # 에어조인트 바로 뒤에 다른 에어조인트를 붙여 사이 전주를 최소화
    set_airjoint(runner, 'main', end + 3)
    quiet_rebuild(runner)
    assert poles[end].section == AirJoint.END.value
    assert poles[end + 1].section == AirJoint.START.value


def test_flowstop_is_separate_from_section():
    """흐름방지 위치는 PoleDATA.flowstop 에만 기록되고 구간(section)은 그대로, CSV 주석 라벨은 동일"""
    from enums.section_type import section_label
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    i = normal_run(poles, 3)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.add_manual_section('main', poles[i - 1].pos, poles[i + 1].pos, poles[i].pos)
    assert [p.flowstop for p in poles[i - 1:i + 2]] == [FlowStop.START, FlowStop.MIDDLE, FlowStop.END]
    assert all(p.section is None for p in poles[i - 1:i + 2])
    assert section_label(poles[i]) == '흐름방지 중간점'
    assert section_label(poles[0]) == '일반개소'
    aj = next(p for p in poles if p.section is not None)
    assert section_label(aj) == aj.section and isinstance(aj.section, SectionType)


def test_pole_updator_does_not_link_across_rail_gap():
    alignment = RailAlignment([(i * 25, i * 25.0, 0.0, 0.0) for i in range(13)],
                              visible_blocks={0.0, 25.0, 50.0, 75.0, 200.0, 225.0, 250.0})

    def pole(pos):
        return types.SimpleNamespace(pos=pos, next_pos=None, span=None, gauge=3, structure='토공', z=0,
                                     base_type='I', side=-1)

    poles = [pole(0), pole(50), pole(200), pole(250)]
    poles[1].next_pos, poles[1].span = 100, 50  # 생성 시점의 경간 (단절 직전)
    PoleUpdator.update_all(poles, alignment)
    assert (poles[0].next_pos, poles[0].span) == (50, 50)
    assert (poles[1].next_pos, poles[1].span) == (100, 50)  # 단절을 건너 200 과 잇지 않음
    assert (poles[2].next_pos, poles[2].span) == (250, 50)
    PoleUpdator.update_all(poles)  # 표시 정보 없으면 기존처럼 연결
    assert poles[1].next_pos == 200


def test_normalize_legacy_poles():
    """구버전 .dat: uid/flowstop 없음, 구간·흐름방지 위치가 section 문자열"""
    from core.model_rebuilder import normalize
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    aj = next(p for p in poles if p.section is not None)
    legacy = poles[5]
    aj.section = str(aj.section.value)         # 문자열 구간
    legacy.section = '흐름방지 중간점'           # 흐름방지 위치가 section 에
    for p in (aj, legacy):
        del p.__dict__['uid'], p.__dict__['flowstop']
    del runner.__dict__['wire_overrides']
    normalize(runner)
    assert isinstance(aj.section, SectionType) and aj.flowstop is None and aj.uid
    assert legacy.section is None and legacy.flowstop == FlowStop.MIDDLE and legacy.uid
    assert runner.wire_overrides == {}
    uid = legacy.uid
    normalize(runner)  # 두 번 해도 그대로
    assert legacy.uid == uid


# ── 전선 상세 편집 보존 (경간 단위) ─────────────────────────────
from core.wire import wire_overrides  # noqa: E402
from tools.verify import load_main_line, wire_errors  # noqa: E402
from vms.editable_pole import EditablePole  # noqa: E402
from vms.editable_wires import EditableWire  # noqa: E402


def editable_wires(runner, track='main'):
    """편집기 create_ewires 와 같은 래퍼 목록"""
    out, prev = [], None
    for wire in runner.wire_data[track]:
        ew = EditableWire(wire, runner.structure_list, runner.curvelist, runner.pitchlist,
                          alignment_for(runner, track), prev_wire=prev)
        if prev:
            prev.next_wire = ew
        out.append(ew)
        prev = ew
    return out


def edit_wire_end(runner, wire_pos, label, end_point, track='main'):
    """전선 편집기 commit 과 같은 순서: snapshot → update(끝점) → 다음 경간 시작점 맞춤 → 기록 → rebuild"""
    ews = editable_wires(runner, track)
    ew = next(e for e in ews if e.wire.pos == wire_pos)
    i = next(k for k, w in enumerate(ew.wire.wires) if w.label == label)
    positions = [ew.wire.pos] + [e.wire.pos for e in (ew.prev_wire, ew.next_wire) if e]
    before = wire_overrides.snapshot(runner, track, positions)
    ew.update(index=i, offset=ew.wire.wires[i].offset, end_point=end_point)
    if ew.next_wire and i < len(ew.next_wire.wire.wires):
        ew.next_wire.wire.wires[i].offset = end_point
    n = wire_overrides.record_changes(runner, track, before)
    quiet_rebuild(runner)
    return n


def wire_of(runner, pos, label, track='main'):
    return next(w for wd in runner.wire_data[track] if wd.pos == pos for w in wd.wires if w.label == label)


def geometry_max_error_cm(runner, track='main'):
    line = load_main_line(os.path.join(CASES, 'synthetic_route', 'bve_coordinates.txt'))
    by_pos = {p.pos: p for p in runner.poledata[track]}
    rows = [dict(pos=wd.pos, next_pos=by_pos[wd.pos].next_pos, start=list(w.offset), end=list(w.end_point),
                 yaw=w.adjusted_angle, station=w.station, label=w.label, radius=by_pos[wd.pos].radius)
            for wd in runner.wire_data[track] for w in wd.wires]
    return wire_errors(rows, line)[0][0] * 100


def test_wire_edit_survives_rebuild_and_pole_move(tmp_path):
    runner = run_case('synthetic_single_250')
    auto = outputs(runner, tmp_path, 'auto')
    poles = runner.poledata['main']
    i = normal_run(poles, 4)
    span_pole, end_pole = poles[i], poles[i + 1]
    new_end = (0.35, 5.3)

    assert edit_wire_end(runner, span_pole.pos, '전차선', new_end) >= 2  # 이 경간 끝점 + 다음 경간 시작점
    assert wire_of(runner, span_pole.pos, '전차선').end_point == new_end
    assert wire_of(runner, end_pole.pos, '전차선').offset == new_end
    assert geometry_max_error_cm(runner) < 0.001  # 앞뒤 경간 각도까지 새 지지점에 맞게 재계산

    # 다른 편집으로 재계산돼도 유지
    quiet_rebuild(runner)
    assert wire_of(runner, span_pole.pos, '전차선').end_point == new_end

    # 경간 앞 전주를 옮겨도(uid 동일) 유지, 각도는 새 위치 기준
    ep = EditablePole(span_pole, runner.structure_list, runner.curvelist, runner.pitchlist,
                      alignment_for(runner, 'main'))
    ep.prev_pole = EditablePole(poles[i - 1], runner.structure_list, runner.curvelist, runner.pitchlist,
                                alignment_for(runner, 'main'))
    ep.next_pole = EditablePole(end_pole, runner.structure_list, runner.curvelist, runner.pitchlist,
                                alignment_for(runner, 'main'))
    ep.update(pos=span_pole.pos + 1)
    quiet_rebuild(runner)
    assert wire_of(runner, span_pole.pos, '전차선').end_point == new_end
    assert geometry_max_error_cm(runner) < 0.001

    # 자동값으로 되돌리기 → 원래 위치로 옮기면 처음 출력과 같아야 함
    wire_overrides.clear(runner, 'main', [poles[i - 1].pos, span_pole.pos, end_pole.pos])
    ep.update(pos=span_pole.pos - 1)
    quiet_rebuild(runner)
    assert runner.wire_overrides == {}
    assert outputs(runner, tmp_path, 'reset') == auto


def test_wire_edit_follows_span_existence():
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    i = normal_run(poles, 4)
    a, b = poles[i], poles[i + 1]
    edit_wire_end(runner, a.pos, '전차선', (0.4, 5.25))
    key = ('main', a.uid, b.uid)
    assert key in runner.wire_overrides

    # 전주 a 삭제 → 그 경간 편집 정리
    poles.remove(a)
    quiet_rebuild(runner)
    assert key not in runner.wire_overrides
    assert all(a.uid not in k for k in runner.wire_overrides)


def test_save_load_keeps_sections_uids_and_wire_edits(tmp_path):
    """데이터 저장/로드(.dat) 후에도 구간 enum, 전주 uid, 전선 편집 내용 유지"""
    from core.model_rebuilder import normalize
    from file_io.filemanager import load_runner, save_runner
    runner = run_case('synthetic_single_250')
    poles = runner.poledata['main']
    i = normal_run(poles, 4)
    edit_wire_end(runner, poles[i].pos, '전차선', (0.31, 5.27))
    expected = outputs(runner, tmp_path, 'before')

    path = tmp_path / 'runner.dat'
    save_runner(runner, str(path))
    loaded = load_runner(str(path))
    normalize(loaded)
    assert [p.uid for p in loaded.poledata['main']] == [p.uid for p in poles]
    assert any(isinstance(p.section, SectionType) for p in loaded.poledata['main'])
    assert loaded.wire_overrides == runner.wire_overrides
    quiet_rebuild(loaded)
    assert outputs(loaded, tmp_path, 'after') == expected

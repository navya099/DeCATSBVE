"""전선 상세 편집 (core.wire.wire_overrides) 테스트: python -m pytest tests

전선 상세 편집기(gui/wireeditor.py)가 부르는 것과 같은 API 로 편집한 뒤 rebuild 하여 검증한다.
"""
import contextlib
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.model_rebuilder import alignment_for, rebuild  # noqa: E402
from core.wire import wire_overrides as wo  # noqa: E402
from enums.section_type import SectionType  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import load_main_line, wire_errors  # noqa: E402
from core.pole import pole_edit  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_single_250'):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def quiet_rebuild(runner):
    with contextlib.redirect_stdout(io.StringIO()):
        rebuild(runner)


def outputs(runner, tmp_path, tag):
    out = tmp_path / tag
    headless.write_outputs(runner, str(out), '')
    return {f.name: f.read_text(encoding='utf-8') for f in out.iterdir() if f.suffix == '.txt'}


def normal_index(poles, start=4):
    return next(i for i in range(max(2, start), len(poles) - 2)
                if all(poles[j].section is None for j in range(i - 2, i + 3)))


def row(runner, pos, key, track='main'):
    return next((r for r in wo.span_info(runner, track, pos).wires if r.key == key), None)


def geometry_max_error_cm(runner, track='main'):
    """BVE 배치 기준 전선 끝점 ↔ 다음 지지점 오차 (각도가 지지점에 맞게 재계산됐는지)"""
    line = load_main_line(os.path.join(CASES, 'synthetic_route', 'bve_coordinates.txt'))
    by_pos = {p.pos: p for p in runner.poledata[track]}
    rows = [dict(pos=wd.pos, next_pos=by_pos[wd.pos].next_pos, start=list(w.offset), end=list(w.end_point),
                 yaw=w.adjusted_angle, station=w.station, label=w.label, radius=by_pos[wd.pos].radius)
            for wd in runner.wire_data[track] for w in wd.wires]
    return wire_errors(rows, line)[0][0] * 100


@pytest.fixture
def span():
    runner = run_case()
    poles = runner.poledata['main']
    i = normal_index(poles)
    return runner, poles, i


def test_span_info_lists_wires(span):
    runner, poles, i = span
    info = wo.span_info(runner, 'main', poles[i].pos)
    assert info.pole is poles[i] and info.next_pole is poles[i + 1]
    keys = [r.key for r in info.wires]
    assert '전차선#0' in keys and len(keys) == len(set(keys))
    assert all(r.status == 'auto' for r in info.wires)
    assert wo.span_info(runner, 'main', poles[i].pos + 1) is None  # 경간 시작이 아닌 측점


def test_set_wire_links_neighbors_and_recomputes_angles(span):
    runner, poles, i = span
    a, b, prev = poles[i], poles[i + 1], poles[i - 1]
    changed = wo.set_wire(runner, 'main', a.pos, '전차선#0', start=(0.15, 5.25), end=(0.35, 5.3))
    assert set(changed) == {a.pos, b.pos, prev.pos}  # 이 경간 + 뒤 경간 시작점 + 앞 경간 끝점
    quiet_rebuild(runner)
    assert row(runner, a.pos, '전차선#0').offset == (0.15, 5.25)
    assert row(runner, a.pos, '전차선#0').end_point == (0.35, 5.3)
    assert row(runner, b.pos, '전차선#0').offset == (0.35, 5.3)
    assert row(runner, prev.pos, '전차선#0').end_point == (0.15, 5.25)
    assert row(runner, a.pos, '전차선#0').status == 'edited'
    assert geometry_max_error_cm(runner) < 0.001


def test_set_wire_without_linking_touches_only_this_span(span):
    runner, poles, i = span
    a, b = poles[i], poles[i + 1]
    before_next = row(runner, b.pos, '전차선#0').offset
    assert wo.set_wire(runner, 'main', a.pos, '전차선#0', start=row(runner, a.pos, '전차선#0').offset,
                       end=(0.4, 5.2), link_neighbors=False) == [a.pos]
    quiet_rebuild(runner)
    assert row(runner, b.pos, '전차선#0').offset == before_next


def test_edit_survives_pole_move_and_reset_restores_output(span, tmp_path):
    runner, poles, i = span
    auto = outputs(runner, tmp_path, 'auto')
    a = poles[i]
    wo.set_wire(runner, 'main', a.pos, '전차선#0', start=row(runner, a.pos, '전차선#0').offset, end=(0.3, 5.3))
    quiet_rebuild(runner)

    al = alignment_for(runner, 'main')
    pole_edit.move_pole(runner, a, a.pos + 1, al)
    quiet_rebuild(runner)
    assert row(runner, a.pos, '전차선#0').end_point == (0.3, 5.3)  # uid 로 경간을 찾아 유지
    assert geometry_max_error_cm(runner) < 0.001                  # 각도는 새 위치 기준

    pole_edit.move_pole(runner, a, a.pos - 1, al)
    for pos in (poles[i - 1].pos, a.pos, poles[i + 1].pos):
        wo.reset_span(runner, 'main', pos)
    quiet_rebuild(runner)
    assert runner.wire_overrides == {}
    assert outputs(runner, tmp_path, 'reset') == auto


def test_add_and_remove_wire(span):
    runner, poles, i = span
    a = poles[i]
    key = wo.add_wire(runner, 'main', a.pos, '부급전선', 1239, (-2.5, 7.0), (-2.5, 7.0))
    quiet_rebuild(runner)
    added = row(runner, a.pos, key)
    assert added.status == 'added' and added.label == '부급전선' and added.index == 1239
    assert added.adjusted_angle is not None
    assert geometry_max_error_cm(runner) < 0.001
    wd = next(w for w in runner.wire_data['main'] if w.pos == a.pos)
    assert any(w.label == '부급전선' for w in wd.wires)

    # 추가 전선 지지점 수정 → 유지
    wo.set_wire(runner, 'main', a.pos, key, (-2.4, 7.1), (-2.4, 7.1))
    quiet_rebuild(runner)
    assert row(runner, a.pos, key).offset == (-2.4, 7.1)

    # 자동 전선 삭제 → 출력에서 빠지고 '삭제됨' 으로 표시, 자동값 복원 → 되살아남
    victim = next(r for r in wo.span_info(runner, 'main', a.pos).wires if r.label == 'AF')
    wo.remove_wire(runner, 'main', a.pos, victim.key)
    quiet_rebuild(runner)
    assert not any(w.label == 'AF' for w in next(w for w in runner.wire_data['main'] if w.pos == a.pos).wires)
    assert row(runner, a.pos, victim.key).status == 'removed'
    wo.reset_wire(runner, 'main', a.pos, victim.key)
    quiet_rebuild(runner)
    assert row(runner, a.pos, victim.key).status == 'auto'

    # 추가 전선 삭제
    wo.remove_wire(runner, 'main', a.pos, key)
    quiet_rebuild(runner)
    assert row(runner, a.pos, key) is None
    assert runner.wire_overrides == {}


def test_keys_stay_stable_after_removing_earlier_same_label_wire(span):
    """같은 라벨 전선이 여럿일 때 앞 전선을 지워도 뒤 전선 키(편집 대상)가 밀리지 않음"""
    runner, poles, i = span
    a = poles[i]
    k1 = wo.add_wire(runner, 'main', a.pos, '전차선', 1713, (0.1, 5.2), (0.1, 5.2))  # 전차선이 2개가 됨
    quiet_rebuild(runner)
    wo.remove_wire(runner, 'main', a.pos, '전차선#0')
    quiet_rebuild(runner)
    keys = [r.key for r in wo.span_info(runner, 'main', a.pos).wires]
    assert '전차선#0' in keys and k1 in keys  # 삭제 표시된 #0 과 추가 전선이 구분됨
    assert row(runner, a.pos, '전차선#0').status == 'removed'


def test_flowstop_wire_is_read_only():
    runner = run_case()
    poles = runner.poledata['main']
    i = normal_index(poles, 3)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.add_manual_section('main', poles[i - 1].pos, poles[i + 1].pos, poles[i].pos)
    start = next(p for p in poles if p.flowstop is not None)
    fs = next(r for r in wo.span_info(runner, 'main', start.pos).wires if r.label == '흐름방지선')
    assert not fs.editable
    with pytest.raises(ValueError):
        wo.set_wire(runner, 'main', start.pos, fs.key, (0, 0), (0, 0))
    with pytest.raises(ValueError):
        wo.remove_wire(runner, 'main', start.pos, fs.key)


def test_deleted_pole_prunes_its_span_edits(span):
    runner, poles, i = span
    a, b = poles[i], poles[i + 1]
    wo.set_wire(runner, 'main', a.pos, '전차선#0', row(runner, a.pos, '전차선#0').offset, (0.4, 5.25),
                link_neighbors=False)
    key = ('main', a.uid, b.uid)
    assert key in runner.wire_overrides
    poles.remove(a)
    quiet_rebuild(runner)
    assert all(a.uid not in k for k in runner.wire_overrides)


def test_save_load_keeps_sections_uids_and_wire_edits(span, tmp_path):
    from core.model_rebuilder import normalize
    from file_io.filemanager import load_runner, save_runner
    runner, poles, i = span
    a = poles[i]
    wo.set_wire(runner, 'main', a.pos, '전차선#0', row(runner, a.pos, '전차선#0').offset, (0.31, 5.27))
    key = wo.add_wire(runner, 'main', a.pos, '부급전선', 1239, (-2.5, 7.0), (-2.5, 7.0))
    quiet_rebuild(runner)
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
    assert row(loaded, a.pos, key).status == 'added'

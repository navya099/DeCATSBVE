"""전주 상세 편집 (core.pole.pole_edit) 테스트: python -m pytest tests

전주 상세 편집기(gui/pole_assembler.py)가 부르는 것과 같은 API 로 편집한 뒤 rebuild 하여 검증한다.
"""
import contextlib
import io
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.model_rebuilder import alignment_for, normalize, rebuild  # noqa: E402
from core.pole import pole_edit as pe  # noqa: E402
from enums.section_type import SectionType  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import load_main_line, wire_errors  # noqa: E402
from xref_module.index_libmgr import IndexLibrary  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')
LIB = [(1370, '강관주-P10-9m'), (1371, '강관주-P10-9m-교량'), (1375, '강관주-P12-9m'), (623, '기초-토공'),
       (685, '가동브래킷용밴드3호_P10'), (1296, 'Cako250_I'), (1297, 'Cako250_O'), (1234, '급전선현수조립체'),
       (531, '평행틀1m'), (9001, '테스트장비'), (9002, '테스트피팅'), (679, '흐름방지장치_강관주용')]


def run_case(name='synthetic_single_250'):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    runner.idxlib = IndexLibrary(pd.DataFrame([{'인덱스': i, '파일명': n, '경로': n + '.csv'} for i, n in LIB]))
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


def pole_block(runner, pole, track='main'):
    """CSV 에서 이 전주 블록의 freeobj 줄"""
    from bve.bvecsv import BVECSV
    with contextlib.redirect_stdout(io.StringIO()):
        lines = BVECSV([pole], [], track_index=0).create_pole_csv()
    return [l for l in lines if '.freeobj' in l]


@pytest.fixture
def setup():
    runner = run_case()
    poles = runner.poledata['main']
    i = next(k for k in range(3, len(poles) - 3) if all(poles[j].section is None for j in range(k - 2, k + 3)))
    return runner, poles, poles[i]


def row(pole, key):
    return next(r for r in pe.components(pole) if r.key == key)


def test_components_listing(setup):
    _, _, pole = setup
    rows = pe.components(pole)
    kinds = [r.kind for r in rows]
    assert kinds[0] == 'mast' and 'br' in kinds and 'eq' in kinds
    assert len({r.key for r in rows}) == len(rows)
    feeder = next(r for r in rows if r.kind == 'eq')
    assert feeder.detail == '급전선설비' and feeder.editable


def test_set_mast_by_name_or_index_keeps_pole_in_csv(setup):
    runner, _, pole = setup
    pe.set_component(runner, pole, 'mast', name='강관주-P12-9m')
    assert (pole.mast.name, pole.mast.index) == ('강관주-P12-9m', 1375)
    pe.set_component(runner, pole, 'mast', index=1371)
    assert pole.mast.name == '강관주-P10-9m-교량'
    assert isinstance(pole.mast.offset, tuple)  # 이전 버그: offset=게이지(숫자) → CSV 에서 기둥 이후 줄 누락
    quiet_rebuild(runner)
    assert any(';1371;' in l for l in pole_block(runner, pole))


def test_unknown_object_rejected_without_changes(setup):
    runner, _, pole = setup
    before = (pole.mast.name, pole.mast.index)
    with pytest.raises(ValueError):
        pe.set_component(runner, pole, 'mast', name='없는기둥')
    with pytest.raises(ValueError):
        pe.set_component(runner, pole, 'mast', index=123456)
    assert (pole.mast.name, pole.mast.index) == before


def test_offset_rotation_edit_and_persist_across_rebuild(setup):
    runner, poles, pole = setup
    pe.set_component(runner, pole, 'br:0', offset=(0.1, 0.2), rotation=3.0)
    quiet_rebuild(runner)
    other = poles[poles.index(pole) + 4]
    other.pos += 0  # 다른 편집으로 재계산
    quiet_rebuild(runner)
    assert row(pole, 'br:0').offset == (0.1, 0.2) and row(pole, 'br:0').rotation == 3.0


def test_add_and_remove_components(setup):
    runner, _, pole = setup
    n_br, n_eq = len(pole.brackets), len(pole.equipments)
    k_br = pe.add_component(runner, pole, 'br', name='Cako250_O', offset=(0, 0))
    k_fit = pe.add_component(runner, pole, 'fit', index=9002, parent=k_br)
    k_eq = pe.add_component(runner, pole, 'eq', name='테스트장비', offset=(pole.gauge, 1.0))
    k_acc = pe.add_component(runner, pole, 'acc', name='가동브래킷용밴드3호_P10', offset=(pole.gauge, 7.0))
    assert row(pole, k_fit).parent == k_br and row(pole, k_fit).name == '테스트피팅'
    assert row(pole, k_eq).detail == '기타장비'
    quiet_rebuild(runner)
    csv = pole_block(runner, pole)
    assert any(';9001;' in l for l in csv) and any(';9002;' in l for l in csv)

    pe.remove_component(pole, k_fit)
    pe.remove_component(pole, k_br)
    pe.remove_component(pole, k_eq)
    pe.remove_component(pole, k_acc)
    assert (len(pole.brackets), len(pole.equipments)) == (n_br, n_eq)  # 이전 버그: '-' 버튼이 데이터를 안 지움
    with pytest.raises(ValueError):
        pe.add_component(runner, pole, 'fit', index=9002, parent=None)
    with pytest.raises(ValueError):
        pe.remove_component(pole, 'mast')


def test_flowstop_equipment_read_only_and_not_duplicated(setup):
    runner, poles, pole = setup
    i = poles.index(pole)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.anticreeping_pr.add_manual_section('main', poles[i - 1].pos, poles[i + 1].pos, pole.pos)
    start = poles[i - 1]
    fs = next(r for r in pe.components(start) if r.detail == '흐름방지장치')
    assert not fs.editable
    with pytest.raises(ValueError):
        pe.set_component(runner, start, fs.key, rotation=0)
    with pytest.raises(ValueError):
        pe.remove_component(start, fs.key)
    # 다른 구성품을 편집하고 재계산해도 흐름방지장치가 중복되지 않음 (이전: '기타장비'로 저장돼 계속 쌓임)
    pe.set_component(runner, start, 'mast', offset=row(start, 'mast').offset)
    quiet_rebuild(runner)
    quiet_rebuild(runner)
    assert sum(e.type == '흐름방지장치' for e in start.equipments) == 1


def test_set_gauge_moves_gauge_components_and_keeps_edits(setup):
    runner, _, pole = setup
    old_coord, old = pole.coord, pole.gauge
    new = round(old * 1.2, 3)
    # 직접 편집: 브래킷 위치 변경, 게이지 위치 장비 추가, 게이지와 무관한 위치의 장비 추가
    pe.set_component(runner, pole, 'br:0', offset=(0.1, 0.2), rotation=2.0)
    k_on = pe.add_component(runner, pole, 'eq', index=9001, offset=(old, 1.5))
    k_off = pe.add_component(runner, pole, 'eq', index=9001, offset=(old + 0.7, 1.5))
    gauge_keys = [r.key for r in pe.components(pole) if abs(r.offset[0] - old) < 1e-9]

    moved, notices = pe.set_gauge(runner, pole, new, alignment_for(runner, 'main'))
    quiet_rebuild(runner)
    assert moved == len(gauge_keys) and notices == []
    assert pole.gauge == new and pole.coord != old_coord
    for key in gauge_keys:  # 기둥·기초·밴드·급전선설비·추가 장비가 게이지를 따라감
        assert row(pole, key).offset[0] == pytest.approx(new)
    assert row(pole, 'br:0').offset == (0.1, 0.2) and row(pole, 'br:0').rotation == 2.0  # 편집 유지
    assert row(pole, k_on).offset == (new, 1.5)
    assert row(pole, k_off).offset == (old + 0.7, 1.5)  # 게이지 위치가 아닌 것은 그대로
    line = load_main_line(os.path.join(CASES, 'synthetic_route', 'bve_coordinates.txt'))
    by_pos = {p.pos: p for p in runner.poledata['main']}
    rows = [dict(pos=wd.pos, next_pos=by_pos[wd.pos].next_pos, start=list(w.offset), end=list(w.end_point),
                 yaw=w.adjusted_angle, station=w.station, label=w.label, radius=0)
            for wd in runner.wire_data['main'] for w in wd.wires]
    assert wire_errors(rows, line)[0][0] < 1e-5
    with pytest.raises(ValueError):
        pe.set_gauge(runner, pole, -new, alignment_for(runner, 'main'))  # 좌우 변경 불가


def test_set_gauge_moves_opposite_side_and_warns_tension_angle(setup):
    runner, poles, _ = setup
    tunnel = next(p for p in poles if p.structure == '터널' and p.section is None)
    opposite = [r.key for r in pe.components(tunnel) if abs(r.offset[0] + tunnel.gauge) < 1e-9]
    assert opposite  # 터널 급전선설비는 반대편(−게이지)
    new = round(tunnel.gauge * 1.1, 3)
    pe.set_gauge(runner, tunnel, new, alignment_for(runner, 'main'))
    assert all(row(tunnel, k).offset[0] == pytest.approx(-new) for k in opposite)

    aj_start = next(p for p in poles if p.section == SectionType.AJ_START)
    assert any(e.type == '장력장치' for e in aj_start.equipments)
    _, notices = pe.set_gauge(runner, aj_start, aj_start.gauge * 1.1, alignment_for(runner, 'main'))
    assert notices and '장력장치' in notices[0]


def test_regenerate_restores_auto_output(setup, tmp_path):
    runner, _, pole = setup
    auto = outputs(runner, tmp_path, 'auto')
    pe.set_component(runner, pole, 'mast', name='강관주-P12-9m')
    pe.add_component(runner, pole, 'eq', name='테스트장비')
    pe.remove_component(pole, 'br:0')
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'edited') != auto
    pe.regenerate(runner, pole, alignment_for(runner, 'main'))
    quiet_rebuild(runner)
    assert outputs(runner, tmp_path, 'regenerated') == auto


def test_normalize_repairs_legacy_mast_offset(setup):
    runner, _, pole = setup
    complete = pole_block(runner, pole)
    pole.mast.offset = pole.gauge  # 이전 조립기 버그로 저장된 형태
    broken = pole_block(runner, pole)
    assert len(broken) < len(complete)  # 기둥 이후(기둥·밴드·기초·브래킷) 줄이 CSV 에서 빠짐
    normalize(runner)
    assert isinstance(pole.mast.offset, tuple) and pole.mast.offset[0] == pole.gauge
    assert pole_block(runner, pole) == complete


# ── 전주 기본 속성 (표 셀 편집·배치도 이동) ───────────────────
def test_rename(setup):
    runner, poles, pole = setup
    pe.rename(runner, pole, 'X-1')
    assert pole.post_number == 'X-1'
    with pytest.raises(ValueError):
        pe.rename(runner, pole, poles[0].post_number)   # 중복
    with pytest.raises(ValueError):
        pe.rename(runner, pole, ' ')


def test_move_keeps_component_edits_and_updates_geometry(setup):
    runner, poles, pole = setup
    al = alignment_for(runner, 'main')
    pe.set_component(runner, pole, 'br:0', offset=(0.11, 0.22))   # 직접 편집
    uid, coord, old = pole.uid, pole.coord, pole.pos
    assert pe.move_pole(runner, pole, old + 2, al) == []
    quiet_rebuild(runner)
    assert pole.pos == old + 2 and pole.uid == uid and pole.coord != coord
    assert pole.z == al.elevation(old + 2)
    assert row(pole, 'br:0').offset == (0.11, 0.22)                  # 이전: 표 편집이 전주를 새로 만들어 사라짐
    i = poles.index(pole)
    assert poles[i - 1].span == pole.pos - poles[i - 1].pos and pole.span == poles[i + 1].pos - pole.pos


def test_move_validation(setup):
    runner, poles, pole = setup
    al = alignment_for(runner, 'main')
    i = poles.index(pole)
    for bad in (poles[i - 1].pos, poles[i + 1].pos, poles[i - 1].pos - 5):
        with pytest.raises(ValueError):
            pe.move_pole(runner, pole, bad, al)
    with pytest.raises(ValueError):                                   # 경간표에 없는 경간 (앞 경간 1m)
        pe.move_pole(runner, pole, poles[i - 1].pos + 0.5, al)
    aj = next(p for p in poles if p.section is not None)
    with pytest.raises(ValueError):
        pe.move_pole(runner, aj, aj.pos + 1, al)                      # 구간 전주
    assert pole.pos == poles[i].pos                                    # 실패 시 그대로


def test_move_across_structure_regenerates_for_new_structure():
    """구조물 경계를 넘어 이동하면 새 구조물의 건식게이지로 구성품 재생성"""
    from core.structure.define_structure import isbridge_tunnel
    runner = run_case()
    poles = runner.poledata['main']
    al = alignment_for(runner, 'main')

    def span_ok(span, structure):
        try:
            runner.dataprocessor.get_contact_wire_span(span, structure)
            return True
        except ValueError:
            return False

    found = None
    for i in range(1, len(poles) - 1):
        prev, pole, nxt = poles[i - 1], poles[i], poles[i + 1]
        if pole.section is not None:
            continue
        for t in range(int(prev.pos) + 1, int(nxt.pos)):
            s = isbridge_tunnel(t, runner.structure_list)
            if s != pole.structure and span_ok(t - prev.pos, prev.structure) and span_ok(nxt.pos - t, s):
                found = (pole, t, s)
                break
        if found:
            break
    assert found, '구조물 경계를 넘는 이동 위치가 있어야 함'
    pole, target, structure = found
    notices = pe.move_pole(runner, pole, target, al)
    assert pole.structure == structure and notices
    assert abs(pole.gauge) == runner.dataprocessor.get_pole_gauge(structure)
    assert row(pole, 'mast').offset[0] == pytest.approx(pole.gauge)


def test_set_base_type(setup):
    runner, _, pole = setup
    al = alignment_for(runner, 'main')
    new = 'O' if pole.base_type == 'I' else 'I'
    old_bracket = pole.brackets[0].index
    assert pe.set_base_type(runner, pole, new.lower(), al)
    assert pole.base_type == new and pole.brackets[0].index != old_bracket
    assert pe.set_base_type(runner, pole, new, al) == []               # 그대로면 변경 없음
    with pytest.raises(ValueError):
        pe.set_base_type(runner, pole, 'Z', al)

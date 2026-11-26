"""구간 편집 (core.section_edit) 테스트: python -m pytest tests"""
import contextlib
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import section_edit as se  # noqa: E402
from core.model_rebuilder import alignment_for, rebuild  # noqa: E402
from enums.section_type import SectionType  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_single_250'):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    return runner


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def outputs(runner, tmp_path, tag):
    out = tmp_path / tag
    headless.write_outputs(runner, str(out), '')
    return {f.name: f.read_text(encoding='utf-8') for f in out.iterdir() if f.suffix == '.txt'}


def kinds(runner, track='main'):
    return [i.kind.id if i.kind else None for i in se.find_sections(runner, track)]


def free_start(poles, n, start=3):
    """연속 n 개가 모두 일반개소인 구간의 시작 전주"""
    return next(poles[i] for i in range(start, len(poles) - n)
                if all(poles[j].section is None and poles[j].flowstop is None for j in range(i, i + n)))


def test_registry_has_supported_kinds():
    assert {'airjoint_2span', 'airsection_single', 'airsection_double', 'flowstop'} <= set(se.SECTION_KINDS)
    assert se.SECTION_KINDS['airjoint_2span'].n_poles == 5
    assert se.SECTION_KINDS['airsection_single'].n_poles == 5
    assert se.SECTION_KINDS['airsection_double'].n_poles == 8


def test_find_existing_sections():
    runner = run_case()
    assert kinds(runner) == ['airjoint_2span']
    aj = se.find_sections(runner, 'main')[0]
    assert [p.section for p in aj.poles] == list(se.SECTION_KINDS['airjoint_2span'].sequence)
    runner2 = run_case('synthetic_double_rail_150')
    assert kinds(runner2, 'main') == kinds(runner2, 'sub') == ['airjoint_2span']


def test_add_airjoint_creates_flowstop_and_remove_restores_output(tmp_path):
    runner = run_case()
    auto = outputs(runner, tmp_path, 'auto')
    poles = runner.poledata['main']
    start = free_start(poles, 5, start=poles.index(se.find_sections(runner, 'main')[0].poles[-1]) + 8)
    plan = se.plan_add(runner, 'main', start.pos, 'airjoint_2span')
    assert plan.ok and [p for p, _, _ in plan.assignments][0] is start
    se.apply_add(runner, plan, alignment_for)
    quiet(rebuild, runner)
    assert kinds(runner) == ['airjoint_2span', 'flowstop', 'airjoint_2span']  # 두 에어조인트 사이에 흐름방지 자동
    new = next(i for i in se.find_sections(runner, 'main') if i.start_pos == start.pos)
    se.remove(runner, new, alignment_for)
    quiet(rebuild, runner)
    assert kinds(runner) == ['airjoint_2span']
    assert outputs(runner, tmp_path, 'removed') == auto


@pytest.mark.parametrize('kind_id', ['airsection_single', 'airsection_double'])
def test_add_and_remove_airsection(kind_id, tmp_path):
    runner = run_case()
    auto = outputs(runner, tmp_path, 'auto')
    poles = runner.poledata['main']
    kind = se.SECTION_KINDS[kind_id]
    start = free_start(poles, kind.n_poles, start=20)
    se.apply_add(runner, se.plan_add(runner, 'main', start.pos, kind_id), alignment_for)
    quiet(rebuild, runner)
    found = next(i for i in se.find_sections(runner, 'main') if i.start_pos == start.pos)
    assert found.kind.id == kind_id  # 단일/이중을 구간 값 순서로 구분
    assert se.kind_of_pole(runner, found.poles[0]).id == kind_id
    se.remove(runner, found, alignment_for)
    quiet(rebuild, runner)
    assert outputs(runner, tmp_path, 'removed') == auto


def test_plan_validation():
    runner = run_case()
    poles = runner.poledata['main']
    aj = se.find_sections(runner, 'main')[0]
    # 끝 부근: 전주 부족
    assert not se.plan_add(runner, 'main', poles[-2].pos, 'airjoint_2span').ok
    # 기존 에어조인트와 겹침
    p = se.plan_add(runner, 'main', poles[poles.index(aj.poles[0]) - 2].pos, 'airsection_single')
    assert not p.ok and '이미 다른 구간' in p.problems[0]
    # 흐름방지는 일반개소만
    assert not se.plan_add(runner, 'main', aj.poles[0].pos, 'flowstop').ok
    # 끊긴 경간 포함
    start = free_start(poles, 5, start=20)
    start.next_pos = start.next_pos + 1  # 다음 전주와 이어지지 않은 상태
    assert any('끊긴' in m for m in se.plan_add(runner, 'main', start.pos, 'airjoint_2span').problems)
    # 없는 전주·트랙
    assert not se.plan_add(runner, 'main', 12345.6, 'airjoint_2span').ok
    assert not se.plan_add(runner, 'sub', poles[5].pos, 'airjoint_2span').ok
    with pytest.raises(ValueError):
        se.apply_add(runner, se.plan_add(runner, 'main', poles[-2].pos, 'airjoint_2span'), alignment_for)


def test_add_and_remove_flowstop_on_both_tracks():
    runner = run_case('synthetic_double_rail_150')
    start = free_start(runner.poledata['main'], 3, start=3)
    plans = se.plan_add_tracks(runner, ['main', 'sub'], start.pos, 'flowstop')
    assert all(p.ok for p in plans)
    for plan in plans:
        quiet(se.apply_add, runner, plan, alignment_for)
    quiet(rebuild, runner)
    for track in ('main', 'sub'):
        fs = [i for i in se.find_sections(runner, track) if i.kind.id == 'flowstop']
        assert len(fs) == 1 and fs[0].start_pos == start.pos
        quiet(se.remove, runner, fs[0], alignment_for)
    quiet(rebuild, runner)
    assert not any(i.kind.id == 'flowstop' for i in se.find_sections(runner) if i.kind)


def test_incomplete_section_is_reported_and_removable():
    runner = run_case()
    pole = free_start(runner.poledata['main'], 1, start=20)
    pole.section = SectionType.AJ_MIDDLE  # 전주 하나에만 구간 값 (이전 표 셀 편집으로 생길 수 있던 형태)
    broken = [i for i in se.find_sections(runner, 'main') if i.kind is None]
    assert len(broken) == 1 and broken[0].poles == [pole]
    se.remove(runner, broken[0], alignment_for)
    assert pole.section is None


def test_registering_new_airjoint_type():
    """새 에어조인트 타입: 등록표에 추가하면 찾기·추가·삭제가 그대로 동작"""
    calls = []

    def processor(runner, pole, alignment):
        calls.append(pole.pos)
        se.SECTION_KINDS['airjoint_2span'].processor(runner, pole, alignment)

    seq = (SectionType.AJ_START, SectionType.AJ_2, SectionType.AJ_4, SectionType.AJ_END)  # 예시 순서
    kind = se.register_kind(se.SectionKind('airjoint_test', '시험용 에어조인트 (전주 4개)', 'airjoint',
                                           '시험', seq, processor))
    try:
        with pytest.raises(ValueError):
            se.register_kind(se.SectionKind('dup', '중복', 'airjoint', '', seq, processor))
        runner = run_case()
        start = free_start(runner.poledata['main'], 4, start=20)
        se.apply_add(runner, se.plan_add(runner, 'main', start.pos, 'airjoint_test'), alignment_for)
        quiet(rebuild, runner)
        assert len(calls) == 4
        found = next(i for i in se.find_sections(runner, 'main') if i.start_pos == start.pos)
        assert found.kind is kind
        se.remove(runner, found, alignment_for)
        assert all(p.section is None for p in found.poles)
    finally:
        se.SECTION_KINDS.pop('airjoint_test', None)


@pytest.mark.parametrize('kind_id', ['airsection_single', 'airsection_double'])
def test_airsection_at_350_uses_standard_bracket_index(kind_id):
    """350km/h 표준 데이터셋 에어섹션 브래킷: 토공 994/995, 교량 996/997, 터널 998/999"""
    cfg = headless.load_config(os.path.join(CASES, 'synthetic_single_250', 'case.json'))
    cfg['speed'] = 350
    runner = headless.build_runner(cfg)
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
    expected = {'토공': {994, 995}, '교량': {996, 997}, '터널': {998, 999}}
    poles = runner.poledata['main']
    n = se.SECTION_KINDS[kind_id].n_poles
    seen = set()
    for structure in expected:
        start = next((poles[i] for i in range(3, len(poles) - n)
                      if all(poles[j].section is None and poles[j].flowstop is None
                             and poles[j].structure == structure for j in range(i, i + n))), None)
        if start is None:
            continue
        plan = se.plan_add(runner, 'main', start.pos, kind_id)
        assert plan.ok, plan.problems
        se.apply_add(runner, plan, alignment_for)
        quiet(rebuild, runner)
        group = next(i for i in se.find_sections(runner, 'main') if i.start_pos == start.pos).poles
        indices = {b.index for p in group for b in p.brackets}
        assert indices & expected[structure], (structure, indices)
        assert not indices & (set().union(*expected.values()) - expected[structure])
        seen.add(structure)
    assert '토공' in seen

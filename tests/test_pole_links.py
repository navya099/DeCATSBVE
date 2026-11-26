"""구조 개선 2단계: 이웃 전주 값은 이은 전주에서 바로, 선형 값은 한 함수로 — python -m pytest tests"""
import contextlib
import io
import os
import pickle
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.model_rebuilder import alignment_for, normalize, rebuild  # noqa: E402
from core.pole import pole_edit as pe  # noqa: E402
from core.pole.pole_geometry import place_on_alignment, track_lists  # noqa: E402
from core.pole.poledata import NEIGHBOR_FIELDS, PoleDATA  # noqa: E402
from tools import headless  # noqa: E402

CASES = os.path.join(ROOT, 'tests', 'regression_cases')


def run_case(name='synthetic_double_rail_150'):
    runner = headless.build_runner(headless.load_config(os.path.join(CASES, name, 'case.json')))
    with contextlib.redirect_stdout(io.StringIO()):
        runner.run()
        rebuild(runner)
    return runner


def neighbor_values(poles):
    return [tuple(getattr(p, name) for name in NEIGHBOR_FIELDS) for p in poles]


def test_neighbor_values_follow_next_pole_immediately():
    runner = run_case()
    poles = runner.poledata['main']
    a, b = next((p, q) for p, q in zip(poles, poles[1:]) if p.section is None and q.section is None
                and p.next_pole is q)
    assert (a.next_pos, a.span, a.next_gauge, a.next_z) == (b.pos, b.pos - a.pos, b.gauge, b.z)
    pe.set_gauge(runner, b, round(b.gauge * 1.1, 3), alignment_for(runner, 'main'))
    assert a.next_gauge == b.gauge                       # 재계산 전에도 바로 (예전: 복사본이라 rebuild 까지 이전 값)
    b.base_type = 'F'
    assert a.next_base_type == 'F'
    assert poles[-1].next_pole is None                   # 마지막 전주는 잇지 않음


def test_save_load_relinks_without_storing_links(tmp_path):
    from file_io.filemanager import load_runner, save_runner
    runner = run_case()
    before = {t: neighbor_values(ps) for t, ps in runner.poledata.items()}
    assert all('_next' not in p.__getstate__() for ps in runner.poledata.values() for p in ps)
    path = tmp_path / 'r.dat'
    save_runner(runner, str(path))
    loaded = load_runner(str(path))
    normalize(loaded)
    assert {t: neighbor_values(ps) for t, ps in loaded.poledata.items()} == before
    assert all(p.next_pole is q for p, q in zip(loaded.poledata['main'], loaded.poledata['main'][1:]))


def test_long_track_pickles_without_recursion_error():
    """다음 전주 연결을 저장하면 3000주 사슬이 pickle 재귀 한도를 넘음 → 연결은 저장하지 않음"""
    poles = [PoleDATA(post_number=str(i), pos=i * 50, next_pos=None, span=None, gauge=-3, next_gauge=None,
                      structure='토공', next_structure=None, radius=0, cant=0, pitch=0, section=None, z=0,
                      next_z=None, mast=None) for i in range(5000)]
    for p, q in zip(poles, poles[1:]):
        p.link_next(q)
    restored = pickle.loads(pickle.dumps(poles))
    assert restored[0].next_pole is None and restored[0].next_pos is None


def test_legacy_pickled_neighbor_values_still_readable():
    runner = run_case('synthetic_single_250')
    pole = runner.poledata['main'][3]
    state = pole.__getstate__()
    state.pop('_unlinked', None)
    legacy = PoleDATA.__new__(PoleDATA)
    legacy.__dict__.update(state)
    legacy.__dict__.update(next_pos=999, span=42, next_gauge=-3.5)   # 구버전: 인스턴스에 값이 그대로
    assert (legacy.next_pos, legacy.span, legacy.next_gauge) == (999, 42, -3.5)


def test_alignment_values_have_single_source():
    runner = run_case()
    for track, poles in runner.poledata.items():
        al = alignment_for(runner, track)
        curves, pitches = track_lists(runner, track)
        for p in poles[::7]:
            stored = (p.z, p.radius, p.cant, p.pitch, tuple(p.coord))
            place_on_alignment(p, al, curves, pitches)
            assert (p.z, p.radius, p.cant, p.pitch, tuple(p.coord)) == stored
    # 상선 전주 이동도 상선 선형·트랙 표로 (예전: 이동은 본선 곡선표를 썼음)
    sub = runner.poledata['sub']
    pole = None
    for i in range(1, len(sub) - 1):
        q = sub[i]
        if q.section is None and sub[i - 1].next_pole is q and q.next_pole is sub[i + 1]:
            try:
                pe.move_pole(runner, q, q.pos + 1, alignment_for(runner, 'sub'))
            except ValueError:
                continue
            pole = q
            break
    assert pole is not None
    al = alignment_for(runner, 'sub')
    assert pole.z == pytest.approx(al.elevation(pole.pos)) and tuple(pole.coord) == tuple(al.offset_point(pole.pos, pole.gauge))

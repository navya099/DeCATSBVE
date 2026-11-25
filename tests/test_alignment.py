"""선형(core.alignment.alignment.Alignment) 테스트: python -m pytest tests"""
import contextlib
import io
import os
import shutil
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.alignment.alignment import Alignment  # noqa: E402
from core.alignment.define_funtion import iscurve, isslope  # noqa: E402
from tools import headless  # noqa: E402
from tools.verify import verify  # noqa: E402

ROUTE = os.path.join(ROOT, 'tests', 'regression_cases', 'synthetic_route')


@pytest.fixture(scope='module')
def pair():
    a = Alignment.from_bve_alignment(os.path.join(ROUTE, 'bve_alignment.txt'))
    b = Alignment.from_legacy_files(*(os.path.join(ROUTE, f) for f in
                                      ('bve_coordinates.txt', 'curve_info.txt', 'pitch_info.txt')))
    return a, b


def test_alignment_file_equals_legacy_files(pair):
    a, b = pair
    assert list(a) == list(b) and a.curves == b.curves and a.pitches == b.pitches
    assert (a.start, a.end, a.block) == (0.0, 3000.0, 25.0)


def test_queries(pair):
    a, _ = pair
    assert a.curve(512) == (600.0, 0.08) and a.curve(1650) == (-250.0, 0.12) and a.curve(100) == (0.0, 0.0)
    assert a.pitch(1500) == 0.01 and a.pitch(100) == 0.0
    assert a.point(0)[:2] == (1000.0, 2000.0)
    assert a.elevation(1000) == pytest.approx(10.0) and a.elevation(1500) > 10.0
    right = a.offset_point(0, 4.0)      # +x 진행방향 30° → 우측
    assert right[1] < 2000.0
    assert a.bearing(0) == pytest.approx(30.0)


def test_station_tables_match_list_scan(pair):
    """iscurve/isslope: 블록 조회 결과 = 예전 리스트 훑기 결과"""
    a, _ = pair
    plain_curves, plain_pitches = list(a.curvelist), list(a.pitchlist)
    for s in range(0, 3000, 7):
        assert iscurve(s, a.curvelist) == iscurve(s, plain_curves)
        assert isslope(s, a.pitchlist) == isslope(s, plain_pitches)


def test_header_and_bad_files(tmp_path):
    bad = tmp_path / 'bve_alignment.txt'
    bad.write_text('측점,X,Y\n0,1,2\n', encoding='utf-8')
    with pytest.raises(ValueError):
        Alignment.from_bve_alignment(str(bad))


def test_info_dir_prefers_alignment_file(tmp_path):
    for f in ('bve_coordinates.txt', 'curve_info.txt', 'pitch_info.txt'):
        shutil.copy(os.path.join(ROUTE, f), tmp_path / f)
    assert Alignment.from_info_dir(str(tmp_path)).source.endswith('bve_coordinates.txt')
    shutil.copy(os.path.join(ROUTE, 'bve_alignment.txt'), tmp_path / 'bve_alignment.txt')
    assert Alignment.from_info_dir(str(tmp_path)).source.endswith('bve_alignment.txt')


def _shift_route(src, dst, shift):
    """측점을 shift 만큼 옮긴 bve_alignment.txt·구조물 (노선이 0m 에서 시작하지 않는 경우)"""
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(src, 'bve_alignment.txt'), encoding='utf-8') as f, \
            open(os.path.join(dst, 'bve_alignment.txt'), 'w', encoding='utf-8') as g:
        for n, line in enumerate(f):
            if n == 0:
                g.write(line)
                continue
            c = line.split(',')
            c[0] = str(float(c[0]) + shift)
            g.write(','.join(c))
    with pd.ExcelWriter(os.path.join(dst, 'structure.xlsx')) as w:
        pd.DataFrame([['교량1', 700 + shift, 900 + shift, 200]]).to_excel(w, sheet_name='교량', header=False, index=False)
        pd.DataFrame([['터널1', 1800 + shift, 2300 + shift, 500]]).to_excel(w, sheet_name='터널', header=False, index=False)


def test_route_not_starting_at_zero(tmp_path):
    """bve_alignment.txt 는 측점이 들어 있어 10km 에서 시작하는 노선도 곡선·좌표가 맞음
    (기존 3개 파일 방식은 좌표 첫 줄을 0m 로 가정해 어긋났음)"""
    base = {'structure': os.path.join(ROUTE, 'structure.xlsx'), 'alignment': os.path.join(ROUTE, 'bve_alignment.txt'),
            'speed': 250, 'mode': 'single', 'start': 0, 'end': 3000}
    shifted_dir = tmp_path / 'shifted'
    _shift_route(ROUTE, str(shifted_dir), 10000)
    shifted = dict(base, alignment=str(shifted_dir / 'bve_alignment.txt'),
                   structure=str(shifted_dir / 'structure.xlsx'), start=10000, end=13000)
    results = {}
    for name, cfg in (('base', base), ('shifted', shifted)):
        out = tmp_path / name
        with contextlib.redirect_stdout(io.StringIO()):
            summary = headless.run(cfg, str(out))
        assert summary['errors'] == []
        geo = verify(str(out), cfg['alignment'])
        assert geo['main']['max_cm'] < 0.001
        r = headless.build_runner(cfg)
        with contextlib.redirect_stdout(io.StringIO()):
            r.run()
        results[name] = [(p.pos - cfg['start'], p.radius, p.cant, p.pitch, p.structure) for p in r.poledata['main']]
        # 에어조인트는 절대 측점 1,600m 배수 부근에 자동 배치 (시작 측점이 다르면 상대 위치는 달라지는 게 정상)
        for pos, _ in r.airjoint_list:
            assert min(pos % 1600, 1600 - pos % 1600) <= 100 + 5 * 60
    assert results['base'] == results['shifted']  # 같은 상대 위치·곡선·캔트·구배·구조물

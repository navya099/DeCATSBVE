"""계산 유틸 회귀 테스트: python -m pytest tests"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import math_util  # noqa: E402
from utils.comom_util import get_max_span_straight, get_max_span_tunnel  # noqa: E402
from utils.math_util import (  # noqa: E402
    clear_geometry_caches,
    get_elevation_pos,
    interpolate_cached,
    interpolate_coordinates,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_geometry_caches()
    yield
    clear_geometry_caches()


def make_line(y=0.0, z0=0.0, dz=0.0, n=5):
    """x축 방향 25m 간격 선형: [(sta, x, y, z), ...]"""
    return [(i * 25, i * 25.0, y, z0 + i * dz) for i in range(n)]


def test_interpolate_z_uses_ratio_not_distance():
    line = make_line(dz=1.0)  # 25m 당 1m 상승
    (x, y, z), _, bearing = interpolate_coordinates(line, 12.5)
    assert x == pytest.approx(12.5)
    assert z == pytest.approx(0.5)  # 이전 버그: 12.5
    assert bearing == pytest.approx(0.0)


def test_interpolate_last_point_is_inclusive():
    line = make_line()
    (x, _, _), _, _ = interpolate_coordinates(line, 100)
    assert x == pytest.approx(100.0)
    with pytest.raises(ValueError):
        interpolate_coordinates(line, 101)


def test_cache_is_separated_per_polyline():
    main = make_line(y=0.0)
    sub = make_line(y=4.3)  # 상선 (선로중심간격 4.3m)
    (_, y_main, _), _, _ = interpolate_cached(main, 50)
    (_, y_sub, _), _, _ = interpolate_cached(sub, 50)
    assert y_main == pytest.approx(0.0)
    assert y_sub == pytest.approx(4.3)  # 이전 버그: 본선 값(0.0)이 반환됨


def test_elevation_cache_is_separated_per_polyline():
    a = make_line(z0=10.0)
    b = make_line(z0=20.0)
    assert get_elevation_pos(25, a) == pytest.approx(10.0)
    assert get_elevation_pos(25, b) == pytest.approx(20.0)


def test_clear_geometry_caches():
    interpolate_cached(make_line(), 25)
    assert math_util.interpolation_cache
    clear_geometry_caches()
    assert not math_util.interpolation_cache


@pytest.mark.parametrize("speed,straight,tunnel", [(150, 50, 40), (250, 60, 45), (350, 63, 50)])
def test_max_span(speed, straight, tunnel):
    assert get_max_span_straight(speed) == straight
    assert get_max_span_tunnel(speed) == tunnel


def test_max_span_unsupported_speed_raises():
    with pytest.raises(ValueError):
        get_max_span_straight(200)
    with pytest.raises(ValueError):
        get_max_span_tunnel(200)


def test_offset_polyline_keeps_station_and_z():
    from utils.math_util import offset_polyline
    line = make_line(z0=100.0, dz=1.0)  # +x 방향
    right = offset_polyline(line, 4.3)
    assert [p[0] for p in right] == [p[0] for p in line]  # 측점 1:1 유지
    assert [p[3] for p in right] == [p[3] for p in line]  # 고도 유지
    assert all(p[2] == pytest.approx(-4.3) for p in right)  # +x 진행 시 우측 = -y
    left = offset_polyline(line, -4.3)
    assert all(p[2] == pytest.approx(4.3) for p in left)
    # 상선 선형으로 보간/고도 계산이 동작해야 함 (이전: z 가 빠져 unpack 에러)
    interpolate_cached(right, 30)
    assert get_elevation_pos(30, right) == pytest.approx(101.2)


def test_bracket_lookup_error_names_missing_key_and_source():
    from dataset.dataset_getter import DatasetGetter
    ds = {'bracket': {'index': {'일반개소': {'토공': {'O': 630}}}}, '_source': {'json': 'c:/temp/x.json'}}
    g = DatasetGetter(ds)
    assert g.get_bracket_codes('일반개소', '토공', 'O') == 630
    assert g.get_bracket_codes('일반개소', '토공') == {'O': 630}
    with pytest.raises(ValueError) as e:
        g.get_bracket_codes('일반개소', '토공', 'I')
    msg = str(e.value)
    assert "'I'" in msg and 'bracket.index.일반개소.토공' in msg and "['O']" in msg and 'x.json' in msg

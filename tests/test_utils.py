"""계산 유틸 회귀 테스트: python -m pytest tests"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.comom_util import (distribute_pole_spacing_flexible, get_max_span_at, get_max_span_straight,  # noqa: E402
                              get_max_span_tunnel, get_span_from)
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


def test_geometry_cache_is_per_alignment_and_not_pickled():
    """보간·고도 캐시는 선형 객체마다 따로 있고(.dat 에는 저장 안 함), 리스트도 같은 결과"""
    import pickle
    from core.alignment.alignment import Alignment
    pts = make_line(dz=1.0)
    a, b = Alignment(pts), Alignment(make_line(y=4.3))
    assert a.point(30)[1] == pytest.approx(0.0) and b.point(30)[1] == pytest.approx(4.3)
    assert a.elevation(30) == pytest.approx(1.2)
    assert a._cache('locate') and a._cache('elevation')
    restored = pickle.loads(pickle.dumps(a))
    assert restored._geometry_cache == {} and list(restored) == list(a)
    assert restored.point(30) == a.point(30)
    a.clear_cache()
    assert a._geometry_cache == {}
    # 리스트를 넘기는 호환 함수도 같은 값
    assert interpolate_cached(pts, 30) == Alignment(pts).locate(30)
    assert get_elevation_pos(30, pts) == Alignment(pts).elevation(30)
    clear_geometry_caches()


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


# 경간 상한: 측점 최대 경간 = min(설계속도 한도(직선/터널), 곡선 반경 한도)
CURVES = [(sta, 1500, 0.05) for sta in range(1000, 1500, 25)] + [(sta, 300, 0.1) for sta in range(2000, 2500, 25)]
STRUCT = {'bridge': [], 'tunnel': [('T1', 2200, 2600)]}


@pytest.mark.parametrize("speed,pos,expected", [
    (150, 500, 50), (250, 500, 60), (350, 500, 63),     # 직선: 설계속도 한도
    (150, 1100, 50), (250, 1100, 60), (350, 1100, 60),  # R1500(60m): 저속은 설계속도 한도가 더 작음
    (250, 2050, 35),                                    # R300 토공
    (250, 2300, 35), (250, 2550, 45),                   # 터널 안 곡선은 반경 한도, 터널 직선은 터널 한도
])
def test_max_span_at(speed, pos, expected):
    assert get_max_span_at(pos, speed, CURVES, STRUCT) == expected


def test_span_from_respects_end_point_limit():
    # 직선에서 출발해 60m 끝이 R300 곡선 안 → 35m (끝점도 한도 안)
    assert get_span_from(1960, 250, CURVES, STRUCT) == 35
    assert get_span_from(500, 250, CURVES, STRUCT) == 60
    positions = distribute_pole_spacing_flexible(0, 3000, CURVES, STRUCT, 150)
    for a, b in zip(positions, positions[1:]):
        assert b - a <= min(get_max_span_at(p, 150, CURVES, STRUCT) for p in (a, b))


def test_span_avoids_short_sharp_curve_inside_span():
    """경간 가운데에만 걸치는 짧은 급곡선(1블록)도 한도 적용"""
    from utils.comom_util import get_max_span_between, span_check_points
    curves = [(1525, 300, 0.1)]                       # 1525~1550 한 블록만 R300
    assert span_check_points(1500, 1560) == [1500, 1525, 1550, 1560]
    assert get_max_span_between(1500, 1560, 250, curves, STRUCT) == 35
    assert get_span_from(1500, 250, curves, STRUCT) == 35
    positions = distribute_pole_spacing_flexible(0, 3000, curves, STRUCT, 250)
    for a, b in zip(positions, positions[1:]):
        assert b - a <= get_max_span_between(a, b, 250, curves, STRUCT)

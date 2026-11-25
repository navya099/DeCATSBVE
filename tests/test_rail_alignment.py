"""rail_info 기반 상선 선형 테스트: python -m pytest tests"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.alignment.rail_alignment import (  # noqa: E402
    build_rail_alignment, is_span_visible, parse_rail_info, visible_ranges,
)
from utils.math_util import offset_polyline  # noqa: E402

MAIN = [(i * 25, i * 25.0, 0.0, 10.0) for i in range(9)]  # 0~200m, +x 방향


def write_rail_info(tmp_path, rows):
    p = tmp_path / "rail_info.txt"
    p.write_text("\n".join(",".join(str(c) for c in r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def rail_rows(visible_until=None, with_flag=True, key=1, offset=-4.4, dz=0.0):
    rows = []
    for sta, x, y, z in MAIN:
        r = [float(sta), key, x, y + offset, z + dz]
        if with_flag:
            r.append(1 if visible_until is None or sta < visible_until else 0)
        rows.append(r)
    rows.append([0.0, 2, 0.0, 99.0, 0.0, 1])  # 다른 레일은 무시돼야 함
    return rows


def test_parse_reads_only_requested_rail(tmp_path):
    pts, has_vis = parse_rail_info(write_rail_info(tmp_path, rail_rows()), 1)
    assert has_vis
    assert len(pts) == len(MAIN)
    assert pts[0.0][1] == pytest.approx(-4.4)


def test_parse_missing_rail_raises(tmp_path):
    with pytest.raises(ValueError):
        parse_rail_info(write_rail_info(tmp_path, rail_rows()), 7)


def test_rail_coordinates_and_height_used(tmp_path):
    pts, has_vis = parse_rail_info(write_rail_info(tmp_path, rail_rows(dz=-13.5)), 1)
    al = build_rail_alignment(MAIN, pts, offset_polyline(MAIN, 4.4), 1, has_vis)
    assert [p[0] for p in al] == [p[0] for p in MAIN]
    assert al[3][2] == pytest.approx(-4.4)
    assert al[3][3] == pytest.approx(-3.5)  # 레일 높이(2층 구조 등) 반영


def test_rail_end_hides_stale_coordinates(tmp_path):
    # 레일 블록 0~100 까지 그려지고(100→125 구간 표시 X), 이후 좌표는 마지막 오프셋이 복사된 값
    rows = rail_rows(visible_until=100)
    for r in rows:
        if r[1] == 1 and r[0] >= 125:
            r[3] = -20.0  # 파서가 남긴 의미 없는 좌표
    pts, has_vis = parse_rail_info(write_rail_info(tmp_path, rows), 1)
    al = build_rail_alignment(MAIN, pts, offset_polyline(MAIN, 4.4), 1, has_vis)
    assert visible_ranges(al) == [(0.0, 100.0)]
    assert al[4][2] == pytest.approx(-4.4)   # 100m: 마지막 그려진 구간의 끝점 → 레일 좌표
    assert al[6][2] == pytest.approx(-4.4)   # 150m: 표시 X → fallback 오프셋(-4.4), stale(-20) 아님
    assert is_span_visible(al, 50, 100)
    assert not is_span_visible(al, 50, 110)
    assert not is_span_visible(al, 125, 175)


def test_old_format_treated_as_all_visible(tmp_path):
    pts, has_vis = parse_rail_info(write_rail_info(tmp_path, rail_rows(with_flag=False)), 1)
    assert not has_vis
    al = build_rail_alignment(MAIN, pts, offset_polyline(MAIN, 4.4), 1, has_vis)
    assert al.visible_blocks is None
    assert is_span_visible(al, 0, 200)


def test_plain_list_alignment_is_always_visible():
    assert is_span_visible(MAIN, 0, 200)

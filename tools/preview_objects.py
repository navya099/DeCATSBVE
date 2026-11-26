"""미리보기 배경 오브젝트(BVE CSV) 만들기

    선로중심선: 선로 중심(x=0)을 세로로 표시하는 얇은 직사각형
        python -m tools.preview_objects centerline assets/preview/선로중심선.csv
    단면 외곽선(건축한계 등): DXF 의 선(폴리선·선·호·원·스플라인)을 선로 방향으로 얇게 밀어낸 띠
        python -m tools.preview_objects outline 건축한계.dxf assets/preview/건축한계.csv --scale 0.001

좌표는 BVE 기준 x(우측)·y(위)·z(진행 방향), 단위 m. DXF 도면 단위가 mm 이면 --scale 0.001,
도면 원점이 선로 중심·레일면이 아니면 --origin X,Y (도면 단위) 로 그 점을 (0, 0) 으로 옮긴다.
면은 앞뒤 모두 보이도록 두 방향으로 넣는다 (미리보기 파서는 AddFace 만 읽음).
"""
import argparse
import sys

HEADER = ';DeCATSBVE tools.preview_objects 로 생성\n'


def _fmt(v):
    return f'{round(v, 6):g}'


def _quad(lines, base, a, b, c, d):
    """사각형 a-b-c-d (정점 번호 base 기준)를 앞뒤 두 방향 삼각형으로"""
    a, b, c, d = (base + i for i in (a, b, c, d))
    lines.append(f'AddFace, {a}, {b}, {c}\n')
    lines.append(f'AddFace, {a}, {c}, {d}\n')
    lines.append(f'AddFace, {a}, {c}, {b}\n')
    lines.append(f'AddFace, {a}, {d}, {c}\n')


def centerline_csv(bottom=-0.5, top=7.0, width=0.01):
    """선로 중심 표시: x = ±width/2, y = bottom~top, z = 0 평면"""
    h = width / 2
    lines = [HEADER, 'CreateMeshBuilder,\n']
    for x, y in ((-h, bottom), (h, bottom), (h, top), (-h, top)):
        lines.append(f'AddVertex, {_fmt(x)}, {_fmt(y)}, 0,\n')
    _quad(lines, 0, 0, 1, 2, 3)
    return ''.join(lines)


def polylines_csv(polylines, depth=0.05):
    """단면 선 목록 [[(x, y), ...], ...] → 선로 방향(z 0~depth)으로 밀어낸 띠 (선마다 메시 하나)"""
    lines = [HEADER]
    for points in polylines:
        if len(points) < 2:
            continue
        lines.append('CreateMeshBuilder,\n')
        for x, y in points:
            lines.append(f'AddVertex, {_fmt(x)}, {_fmt(y)}, 0,\n')
            lines.append(f'AddVertex, {_fmt(x)}, {_fmt(y)}, {_fmt(depth)},\n')
        for i in range(len(points) - 1):
            _quad(lines, 0, 2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2)
    return ''.join(lines)


def read_dxf_polylines(path, layer=None, scale=1.0, origin=(0.0, 0.0), flatten=0.01):
    """DXF 모델 공간의 선 → [[(x, y), ...]] (도면 단위 × scale, origin 을 0 으로). 호·원·스플라인은 꺾은선으로"""
    import ezdxf
    from ezdxf import path as ezpath
    doc = ezdxf.readfile(path)
    ox, oy = origin
    result = []
    for e in doc.modelspace():
        if layer and e.dxf.get('layer') != layer:
            continue
        kind = e.dxftype()
        if kind == 'LINE':
            pts = [e.dxf.start, e.dxf.end]
        elif kind in ('LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'SPLINE', 'ELLIPSE'):
            pts = list(ezpath.make_path(e).flattening(flatten / scale if scale else flatten))
        else:
            continue
        result.append([((p[0] - ox) * scale, (p[1] - oy) * scale) for p in pts])
    if not result:
        raise ValueError(f'{path}: 선이 없습니다' + (f" (레이어 '{layer}')" if layer else ''))
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='미리보기 배경 오브젝트(BVE CSV) 만들기')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('centerline', help='선로중심선')
    c.add_argument('out')
    c.add_argument('--bottom', type=float, default=-0.5)
    c.add_argument('--top', type=float, default=7.0)
    c.add_argument('--width', type=float, default=0.01)
    o = sub.add_parser('outline', help='DXF 단면 외곽선 → 밀어낸 띠')
    o.add_argument('dxf')
    o.add_argument('out')
    o.add_argument('--layer', help='이 레이어의 선만')
    o.add_argument('--scale', type=float, default=1.0, help='도면 단위 → m (mm 도면이면 0.001)')
    o.add_argument('--origin', default='0,0', help='선로 중심·레일면 위치 X,Y (도면 단위)')
    o.add_argument('--depth', type=float, default=0.05, help='선로 방향 두께 (m)')
    a = ap.parse_args(argv)
    if a.cmd == 'centerline':
        text = centerline_csv(a.bottom, a.top, a.width)
    else:
        ox, oy = (float(v) for v in a.origin.split(','))
        polylines = read_dxf_polylines(a.dxf, a.layer, a.scale, (ox, oy))
        text = polylines_csv(polylines, a.depth)
        xs = [x for pl in polylines for x, _ in pl]
        ys = [y for pl in polylines for _, y in pl]
        print(f'선 {len(polylines)}개, x {min(xs):.3f}~{max(xs):.3f} m, y {min(ys):.3f}~{max(ys):.3f} m')
    with open(a.out, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(text)
    print(f'저장: {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

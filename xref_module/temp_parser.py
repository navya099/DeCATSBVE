"""BVE CSV 오브젝트 파서 (미리보기·도면용 형상: 정점·면)

BVE(openBVE) CSV 오브젝트 형식:
    - 명령은 대소문자 구분 없음, 인수는 쉼표로 구분, ';' 뒤는 주석, 빈 인수는 0
    - CreateMeshBuilder              새 메시
    - AddVertex, x, y, z[, 법선]     정점 (법선은 무시)
    - AddFace / AddFace2, v1, v2, …  면 (꼭짓점 3개 이상, AddFace2 = 양면)
    - Cube, 반폭, 반높이, 반깊이       상자 (정점 8, 면 6)
    - Cylinder, n, 위 반지름, 아래 반지름, 높이   원기둥/원뿔 (반지름이 음수면 그 면 뚜껑 없음)
    - Translate / Scale / Rotate / Mirror, …       현재 메시 정점 변환
      TranslateAll / ScaleAll / RotateAll / MirrorAll  지금까지의 모든 메시 정점 변환
    - 재질·텍스처 명령(SetColor, LoadTexture, SetTextureCoordinates 등)은 형상과 무관해 무시
좌표는 OpenBVE 좌표계(x 우측, y 위, z 진행)로 읽고 CoordinateSystem.OPENBVE 로 표시한다.
"""
import math

from xref_module.objmodel.csvobject import CSVObject
from xref_module.objmodel.face.face import Face
from xref_module.objmodel.mesh.mesh import Mesh
from xref_module.vector3.vector3 import Vector3
from xref_module.world.coordinatesystem import CoordinateSystem

# 형상과 무관해 무시하는 명령 (소문자)
IGNORED = {'setcolor', 'setemissivecolor', 'setblendmode', 'setwrapmode', 'loadtexture',
           'setdecaltransparentcolor', 'settexturecoordinates', 'generatenormals', 'enablecrossfading',
           'settext', 'settextcolor', 'setbackgroundcolor', 'settextpadding', 'setfont', 'setcolorall',
           'setemissivecolorall'}


def _args(parts, count, default=0.0):
    """인수 count 개 (없거나 빈 값은 default, 숫자가 아니면 ValueError)"""
    values = []
    for i in range(count):
        raw = parts[i].strip() if i < len(parts) else ''
        values.append(float(raw) if raw else default)
    return values


def _rotate(points, axis, angle_deg):
    """축(axis) 둘레로 angle 도 회전 (로드리게스, openBVE 와 같은 식)"""
    ax, ay, az = axis
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    if norm == 0:
        ax, ay, az = 1.0, 0.0, 0.0
    else:
        ax, ay, az = ax / norm, ay / norm, az / norm
    t = math.radians(angle_deg)
    c, s = math.cos(t), math.sin(t)
    k = 1 - c
    for p in points:
        x, y, z = p
        p[0] = (c + k * ax * ax) * x + (k * ax * ay - s * az) * y + (k * ax * az + s * ay) * z
        p[1] = (k * ax * ay + s * az) * x + (c + k * ay * ay) * y + (k * ay * az - s * ax) * z
        p[2] = (k * ax * az - s * ay) * x + (k * ay * az + s * ax) * y + (c + k * az * az) * z


class CSVObjectParser:
    def __init__(self, lines):
        self.lines = lines
        self.unsupported = set()      # 알 수 없는 명령 (형상에 영향이 있을 수 있음)

    def parse(self) -> CSVObject:
        meshes = []                    # [[정점 [x,y,z] 목록, 면 목록], ...]
        current = None

        def builder():
            nonlocal current
            if current is None:        # CreateMeshBuilder 없이 시작한 파일
                current = [[], []]
                meshes.append(current)
            return current

        def all_points():
            return [p for m in meshes for p in m[0]]

        for raw in self.lines:
            line = raw.split(';', 1)[0].strip().lstrip('﻿')
            if not line:
                continue
            parts = line.split(',')
            cmd = parts[0].strip().lower()
            args = parts[1:]

            if cmd == 'createmeshbuilder':
                current = [[], []]
                meshes.append(current)
            elif cmd == 'addvertex':
                builder()[0].append(_args(args, 3))
            elif cmd in ('addface', 'addface2'):
                verts, faces = builder()
                idx = [int(float(a)) for a in args if a.strip()]
                if len(idx) >= 3 and all(0 <= i < len(verts) for i in idx):
                    faces.append(Face(idx[0], idx[1], idx[2], tuple(idx[3:])))
            elif cmd == 'cube':
                self._cube(builder(), *_args(args, 3))
            elif cmd == 'cylinder':
                self._cylinder(builder(), *_args(args, 4))
            elif cmd in ('translate', 'translateall'):
                dx, dy, dz = _args(args, 3)
                for p in (all_points() if cmd.endswith('all') else builder()[0]):
                    p[0] += dx
                    p[1] += dy
                    p[2] += dz
            elif cmd in ('scale', 'scaleall'):
                sx, sy, sz = (v if v != 0 else 1.0 for v in _args(args, 3, 1.0))
                for p in (all_points() if cmd.endswith('all') else builder()[0]):
                    p[0] *= sx
                    p[1] *= sy
                    p[2] *= sz
            elif cmd in ('rotate', 'rotateall'):
                x, y, z, angle = _args(args, 4)
                _rotate(all_points() if cmd.endswith('all') else builder()[0], (x, y, z), angle)
            elif cmd in ('mirror', 'mirrorall'):
                flags = _args(args, 3)
                for p in (all_points() if cmd.endswith('all') else builder()[0]):
                    for axis in range(3):
                        if flags[axis] != 0:
                            p[axis] = -p[axis]
            elif cmd not in IGNORED:
                self.unsupported.add(cmd)

        obj = CSVObject([Mesh(vertices=[Vector3(*p) for p in verts], faces=faces)
                         for verts, faces in meshes if verts])
        obj.coordsystem = CoordinateSystem.OPENBVE
        return obj

    @staticmethod
    def _cube(mesh, hx, hy, hz):
        verts, faces = mesh
        v = len(verts)
        verts.extend([[hx, hy, -hz], [hx, -hy, -hz], [-hx, -hy, -hz], [-hx, hy, -hz],
                      [hx, hy, hz], [hx, -hy, hz], [-hx, -hy, hz], [-hx, hy, hz]])
        for quad in ((0, 1, 2, 3), (0, 4, 5, 1), (0, 3, 7, 4), (6, 5, 4, 7), (6, 7, 3, 2), (6, 2, 1, 5)):
            a, b, c, d = (v + i for i in quad)
            faces.append(Face(a, b, c, (d,)))

    @staticmethod
    def _cylinder(mesh, n, upper_r, lower_r, height):
        verts, faces = mesh
        n = int(n)
        if n < 2:
            return
        v = len(verts)
        for i in range(n):
            t = 2 * math.pi * i / n
            dx, dz = math.cos(t), math.sin(t)
            verts.append([dx * abs(upper_r), 0.5 * height, dz * abs(upper_r)])
            verts.append([dx * abs(lower_r), -0.5 * height, dz * abs(lower_r)])
        for i in range(n):
            j = (i + 1) % n
            faces.append(Face(v + 2 * i, v + 2 * i + 1, v + 2 * j + 1, (v + 2 * j,)))
        if upper_r > 0:
            faces.append(Face(v, v + 2, v + 4, tuple(v + 2 * i for i in range(3, n))) if n >= 3 else None)
        if lower_r > 0:
            faces.append(Face(v + 1, v + 3, v + 5, tuple(v + 2 * i + 1 for i in range(3, n))) if n >= 3 else None)
        faces[:] = [f for f in faces if f is not None]

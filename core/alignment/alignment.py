"""선형(Alignment) — BVEParser 의 bve_alignment.txt 를 그대로 쓰는 선형 객체

bve_alignment.txt (BVEParser ApplyRouteData 출력, 블록마다 한 줄):
    측점,X,Y,Z,Bearing,Radius,Cant,Pitch,height
    - X, Y: 평면 좌표, Z: 레일 높이 (bve_coordinates.txt 와 같은 축)
    - Bearing: 진행 방위(라디안), Radius·Cant: 곡선 반경·캔트 (curve_info.txt 와 같음)
    - Pitch: 구배(비율, pitch_info.txt 와 같음), height: 블록 지반고 (참고용)
측점이 파일에 직접 들어 있으므로 노선이 0m 에서 시작하지 않아도 좌표·곡선·구배가 어긋나지 않는다.

Alignment 는 [(측점, x, y, z), ...] 리스트를 상속한다. 그래서 기존 선형 함수
(utils.math_util 의 interpolate_cached / get_elevation_pos / calculate_curve_angle 등)에 그대로 넘길 수 있고,
측점별 곡선·구배는 블록 측점 키로 바로 찾는다 (curve / pitch).
bve_alignment.txt 가 없으면 기존 3개 파일(bve_coordinates / curve_info / pitch_info)로도 만들 수 있다.
"""
import math
import os

from utils.math_util import calculate_offset_point, get_elevation_pos, interpolate_cached

BLOCK = 25
ALIGNMENT_FILE = 'bve_alignment.txt'
LEGACY_FILES = ('bve_coordinates.txt', 'curve_info.txt', 'pitch_info.txt')


class StationTable(list):
    """[(측점, 값...), ...] + 블록 측점 → 행 조회 (iscurve / isslope 가 리스트를 훑지 않도록)"""

    def __init__(self, rows=()):
        super().__init__(rows)
        self.by_station = {float(r[0]): r for r in self}

    def lookup(self, station):
        return self.by_station.get(float(station))


class Alignment(list):
    """[(측점, x, y, z), ...] + 측점별 곡선(반경, 캔트)·구배"""

    def __init__(self, points, curves=None, pitches=None, block=BLOCK, source=None):
        super().__init__(points)
        self.block = block
        self.source = source
        # 블록 측점 → (반경, 캔트) / 구배(비율)
        self.curves = dict(curves or {})
        self.pitches = dict(pitches or {})

    # ── 만들기 ─────────────────────────────────────
    @classmethod
    def from_bve_alignment(cls, path):
        """BVEParser bve_alignment.txt 로 선형 생성"""
        points, curves, pitches = [], {}, {}
        with open(path, encoding='utf-8-sig') as f:
            for n, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                cols = line.split(',')
                if n == 0 and not _is_number(cols[0]):
                    continue  # 머리글
                if len(cols) < 8:
                    raise ValueError(f'{path}:{n + 1} 열이 부족합니다 (측점,X,Y,Z,Bearing,Radius,Cant,Pitch 필요)')
                sta, x, y, z = (float(c) for c in cols[:4])
                points.append((sta, x, y, z))
                curves[sta] = (float(cols[5]), float(cols[6]))
                pitches[sta] = float(cols[7])
        if len(points) < 2:
            raise ValueError(f'{path}: 선형 점이 2개 이상 필요합니다.')
        block = points[1][0] - points[0][0]
        return cls(points, curves, pitches, block=block, source=path)

    @classmethod
    def from_legacy_files(cls, coord_path, curve_path, pitch_path, block=BLOCK):
        """기존 3개 파일로 선형 생성 (좌표 파일에는 측점이 없어 0m 부터 block 간격으로 가정)"""
        from file_io.basedata_processor import parse_curve, parse_pitch, parse_polyline
        coords = parse_polyline(coord_path)
        points = [(i * block, x, y, z) for i, (x, y, z) in enumerate(coords)]
        curves = {float(s): (r, c) for s, r, c in parse_curve(curve_path)}
        pitches = {float(s): p for s, p in parse_pitch(pitch_path)}
        return cls(points, curves, pitches, block=block, source=coord_path)

    @classmethod
    def from_info_dir(cls, folder):
        """폴더에서 bve_alignment.txt 우선, 없으면 기존 3개 파일"""
        path = os.path.join(folder, ALIGNMENT_FILE)
        if os.path.isfile(path):
            return cls.from_bve_alignment(path)
        return cls.from_legacy_files(*(os.path.join(folder, f) for f in LEGACY_FILES))

    def derived(self, points):
        """같은 측점·곡선·구배를 쓰는 다른 선형 (상선 등)"""
        return Alignment(points, self.curves, self.pitches, block=self.block, source=self.source)

    # ── 범위 ──────────────────────────────────────
    @property
    def start(self):
        return self[0][0]

    @property
    def end(self):
        return self[-1][0]

    def block_of(self, station):
        """측점이 속한 블록 시작 측점"""
        return math.floor((station - self.start) / self.block + 0.001) * self.block + self.start

    # ── 측점별 조회 ─────────────────────────────────
    def point(self, station):
        """측점의 선형 좌표 (x, y, z)"""
        return interpolate_cached(self, station)[0]

    def bearing(self, station):
        """측점이 속한 블록의 진행 방위 (도, x 축 기준 반시계)"""
        return interpolate_cached(self, station)[2]

    def elevation(self, station):
        return get_elevation_pos(station, self)

    def offset_point(self, station, offset):
        """측점에서 진행방향 수직으로 offset 만큼 떨어진 평면 좌표 (우측 +, calculate_offset_point 와 같은 규칙)"""
        (x, y, _), _, bearing = interpolate_cached(self, station)
        return calculate_offset_point(bearing, (x, y), offset)

    def curve(self, station):
        """(반경, 캔트). 직선이면 (0, 0)"""
        return self.curves.get(float(self.block_of(station)), (0.0, 0.0))

    def pitch(self, station):
        """구배 (비율)"""
        return self.pitches.get(float(self.block_of(station)), 0.0)

    # ── 기존 코드용 목록 ────────────────────────────
    @property
    def curvelist(self):
        """[(측점, 반경, 캔트)] — iscurve 용 (블록 측점 조회 가능)"""
        return StationTable((s, r, c) for s, (r, c) in sorted(self.curves.items()))

    @property
    def pitchlist(self):
        """[(측점, 구배)] — isslope 용 (블록 측점 조회 가능)"""
        return StationTable((s, p) for s, p in sorted(self.pitches.items()))

    @property
    def coordinates(self):
        """[(x, y, z)] — 기존 runner.polyline 형식"""
        return [(x, y, z) for _, x, y, z in self]


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False

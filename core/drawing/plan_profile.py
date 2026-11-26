"""전차선로 평면도·종단면도 그리기 (ezdxf)

평면도: 선형, 전주(○, 복주는 앞·뒤 2개), 브래킷(선로 중심 → 전주), 전주 정보(번호·측점·브래킷·전주),
        전선(시작 지지점 → 다음 지지점, 전선 종류별 레이어)
종단면도(트랙별): 가로 = 측점, 세로 = (레일면 계획고 + 높이) × 수직 과장
        종단선형, 전주(사각형, 이름의 규격·길이), 브래킷 지지점(○), 전주 정보,
        전선(전차선·조가선·무효선·급전선·보호선…). 전선은 지지점 사이 직선 (이도 표현 없음)
"""
import ezdxf

from core.alignment.alignment import as_alignment
from core.drawing.settings import LAYERS, mast_dimensions, wire_layer
from core.model_rebuilder import alignment_for
from core.pole import pole_units

TEXT_STYLE = 'KOREAN'
# 전선 객체에 조가선이 함께 들어 있는 전차선 (따로 '조가선' 전선이 없으면 조가선을 가고만큼 위에 그림)
CATENARY_LABELS = ('전차선', '본선전차선', '무효->본선전차선')


def new_document():
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.M
    doc.styles.add(TEXT_STYLE, font='malgun.ttf')       # 한글 (윈도 맑은 고딕)
    for name, color in LAYERS.values():
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    return doc


def _layer(key):
    return {'layer': LAYERS[key][0]}


def _label_text(pole):
    brackets = ', '.join(b.bracket_name or str(b.bracket_type or '') for b in pole.brackets or [])
    mast = pole.mast.name if pole.mast is not None else ''
    return f'{pole.post_number}\\P{pole.pos}\\P{brackets}\\P{mast}'


def _mtext(msp, text, insert, height, layer, attachment=1, rotation=0.0):
    msp.add_mtext(text, dxfattribs={'insert': insert, 'char_height': height, 'style': TEXT_STYLE,
                                    'attachment_point': attachment, 'rotation': rotation, **_layer(layer)})


def _outside_label(al, pole, distance):
    """평면도 전주 정보 위치: 전주에서 선로 바깥쪽으로 distance, 글자는 바깥쪽으로 뻗게 (본선·상선 글자가 겹치지 않음)"""
    import math
    cx, cy = al.offset_point(pole.pos, 0)
    px, py = pole.coord
    dx, dy = px - cx, py - cy
    norm = math.hypot(dx, dy) or 1.0
    dx, dy = dx / norm, dy / norm
    insert = (px + dx * distance, py + dy * distance)
    if abs(dx) >= abs(dy):
        attachment = 4 if dx > 0 else 6          # 가운데 왼쪽 / 가운데 오른쪽
    else:
        attachment = 8 if dy > 0 else 2          # 아래 가운데 / 위 가운데
    return insert, attachment


def _poles_by_pos(poles):
    return {p.pos: p for p in poles}


def _wires(runner, track):
    """[(전주, 전선)] — 전선마다 그 경간의 시작 전주 (다음 지지점 = 전주.next_pos)"""
    by_pos = _poles_by_pos(runner.poledata.get(track, []))
    for wd in (runner.wire_data or {}).get(track, []):
        pole = by_pos.get(wd.pos)
        if pole is None or pole.next_pos is None:
            continue
        for w in wd.wires:
            yield pole, wd, w


# ── 평면도 ──────────────────────────────────────────
def draw_plan(runner, settings, doc=None):
    doc = doc or new_document()
    msp = doc.modelspace()
    s = settings.symbol
    for track, poles in (runner.poledata or {}).items():
        al = as_alignment(alignment_for(runner, track))
        msp.add_lwpolyline([(p[1], p[2]) for p in al], dxfattribs=_layer('alignment'))
        for pole in poles:
            for unit in pole_units.units(pole):
                msp.add_circle(unit.coord(al), radius=1.5 * s, dxfattribs=_layer('pole'))
            for _, dpos in pole_units.bracket_stations(pole):
                station = pole.pos + dpos
                msp.add_line(al.offset_point(station, 0), al.offset_point(station, pole.gauge),
                             dxfattribs=_layer('bracket'))
            insert, attachment = _outside_label(al, pole, 3 * s)
            _mtext(msp, _label_text(pole), insert, 3 * s, 'label', attachment)
        for pole, _, w in _wires(runner, track):
            start = w.station if w.station is not None else pole.pos
            msp.add_line(al.offset_point(start, w.offset[0]), al.offset_point(pole.next_pos, w.end_point[0]),
                         dxfattribs=_layer(wire_layer(w.label)))
    return doc


# ── 종단면도 ─────────────────────────────────────────
def draw_profile(runner, track, settings, doc=None):
    doc = doc or new_document()
    msp = doc.modelspace()
    ex = settings.exaggeration
    s = settings.symbol
    al = as_alignment(alignment_for(runner, track))
    data = runner.dataprocessor

    def y(station, height=0.0):
        return (al.elevation(station) + height) * ex

    msp.add_lwpolyline([(p[0], p[3] * ex) for p in al], dxfattribs=_layer('profile_alignment'))
    for pole in runner.poledata.get(track, []):
        for unit in pole_units.units(pole):
            mast = pole.twin.mast if unit.which == pole_units.REAR else pole.mast
            if mast is None:
                continue
            height, width, base = mast_dimensions(mast.name)
            x = unit.station
            msp.add_lwpolyline([(x - width / 2, y(x, base)), (x + width / 2, y(x, base)),
                                (x + width / 2, y(x, base + height)), (x - width / 2, y(x, base + height))],
                               close=True, dxfattribs=_layer('pole'))
        for bracket, dpos in pole_units.bracket_stations(pole):
            x = pole.pos + dpos
            for fit in bracket.fittings or []:
                msp.add_circle((x, y(x, fit.offset[1])), radius=0.03 * ex, dxfattribs=_layer('bracket'))
        # 전주 정보: 레일면 아래에 세로(90°)로, 아래쪽으로 뻗게 (경간이 짧아도 옆 전주 글자와 겹치지 않음)
        _mtext(msp, _label_text(pole), (pole.pos, y(pole.pos) - 2 * s), 3 * s, 'label', attachment=6, rotation=90)

    for pole, wd, w in _wires(runner, track):
        start = w.station if w.station is not None else pole.pos
        end = pole.next_pos
        msp.add_line((start, y(start, w.offset[1])), (end, y(end, w.end_point[1])),
                     dxfattribs=_layer(wire_layer(w.label)))
        explicit_messenger = any(x.label == '조가선' for x in wd.wires)
        if w.label in CATENARY_LABELS and not explicit_messenger and data is not None:
            h1 = data.get_system_height(pole.structure)
            h2 = data.get_system_height(pole.next_structure or pole.structure)
            msp.add_line((start, y(start, w.offset[1] + h1)), (end, y(end, w.end_point[1] + h2)),
                         dxfattribs=_layer('messenger'))
    return doc

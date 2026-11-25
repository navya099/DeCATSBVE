"""전주 상세 편집 — 전주 구성품(기둥·기초·밴드·브래킷·피팅·장비) 조회·수정·추가·삭제 (GUI 없이 동작)

구성품 키:
    'mast'                 기둥            'base'          기초
    'acc:{i}'              기둥 부속(밴드)   'eq:{i}'        장비 (급전선설비, 평행틀 등)
    'br:{i}'               브래킷           'br:{i}/fit:{j}' 브래킷의 피팅
흐름방지장치·봉강지선은 흐름방지 처리기가 재계산마다 다시 만들므로 읽기 전용이다.

오브젝트 이름 ↔ 인덱스는 인덱스 라이브러리(runner.idxlib)로 맞춘다. 이름만 주면 인덱스를 찾고,
인덱스만 주면 이름을 찾는다. 라이브러리에 없으면 ValueError (인덱스 None 으로 저장되지 않도록).

편집 함수는 전주 데이터만 바꾼다. 호출 측에서 rebuild(runner) 후 MODEL_CHANGED 로 화면을 갱신한다.
건식게이지 변경은 게이지 위치(x = ±게이지)에 있던 구성품만 새 게이지로 옮기고 나머지 편집은 유지한다.
'자동 구성으로 되돌리기'는 그 전주의 구성품을 자동 배치 규칙으로 다시 만든다.
"""
from dataclasses import dataclass

from core.airjoint.airjoint_processor import AirJointProcessor
from core.airsection.airsection_processor import AirSectionProcessor
from core.bracket.bracket_data import BracketDATA
from core.bracket.fitting_data import FittingDATA
from core.equipment.equipment_data import EquipmentDATA
from core.mast.base.mast_base import MastBase
from core.mast.mast_accessory.mast_accessory import MastAccessory
from core.pole.normal_section_processor import NormalSectionProcessor
from core.pole.tunnel_section_processor import TunnelSectionProcessor
from enums.section_type import AIRSECTION_SINGLE, SectionType
from core.alignment.alignment import as_alignment

READ_ONLY_EQUIPMENT_TYPES = ('흐름방지장치', '봉강지선')
KIND_TEXT = {'mast': '기둥', 'base': '기초', 'acc': '밴드/부속', 'br': '브래킷', 'fit': '피팅', 'eq': '장비'}
ADDABLE_KINDS = ('br', 'fit', 'eq', 'acc')


@dataclass
class ComponentRow:
    key: str
    kind: str            # 'mast' | 'base' | 'acc' | 'br' | 'fit' | 'eq'
    name: str
    index: int | None
    offset: tuple
    rotation: float
    detail: str          # 장비 종류 등
    editable: bool
    parent: str | None = None   # 피팅의 브래킷 키


# ── 조회 ────────────────────────────────────────────
def _name_of(obj):
    return getattr(obj, 'bracket_name', None) or getattr(obj, 'name', None) or getattr(obj, 'label', '') or ''


def components(pole):
    """전주 구성품 목록 (표시 순서: 기둥, 기초, 부속, 브래킷(+피팅), 장비)"""
    rows = []
    mast = pole.mast
    if mast is not None:
        rows.append(ComponentRow('mast', 'mast', mast.name, mast.index, tuple(_xy(mast.offset)), mast.rotation, '', True))
        if mast.base is not None:
            b = mast.base
            rows.append(ComponentRow('base', 'base', b.name, b.index, tuple(_xy(b.offset)), b.rotation, '', True))
        for i, acc in enumerate(mast.accessories or []):
            rows.append(ComponentRow(f'acc:{i}', 'acc', acc.name, acc.index, tuple(_xy(acc.offset)), acc.rotation,
                                     '', True))
    for i, br in enumerate(pole.brackets):
        key = f'br:{i}'
        rows.append(ComponentRow(key, 'br', br.bracket_name, br.index, tuple(_xy(br.offset)), br.rotation,
                                 str(br.bracket_type or ''), True))
        for j, fit in enumerate(br.fittings):
            rows.append(ComponentRow(f'{key}/fit:{j}', 'fit', fit.label, fit.index, tuple(_xy(fit.offset)),
                                     fit.rotation, '', True, parent=key))
    for i, eq in enumerate(pole.equipments):
        rows.append(ComponentRow(f'eq:{i}', 'eq', eq.name, eq.index, tuple(_xy(eq.offset)), eq.rotation, eq.type,
                                 eq.type not in READ_ONLY_EQUIPMENT_TYPES))
    return rows


def _xy(offset):
    """구버전 데이터에서 offset 이 숫자 하나로 저장된 경우 보정 (기둥 offset=gauge 버그)"""
    if isinstance(offset, (int, float)):
        return (float(offset), 0.0)
    return tuple(offset)


def _get(pole, key):
    """키 → 구성품 객체"""
    if key == 'mast':
        return pole.mast
    if key == 'base':
        return pole.mast.base if pole.mast else None
    kind, _, rest = key.partition(':')
    if kind == 'acc':
        return (pole.mast.accessories or [])[int(rest)]
    if kind == 'eq':
        return pole.equipments[int(rest)]
    if kind == 'br':
        if '/fit:' in rest:
            b, f = rest.split('/fit:')
            return pole.brackets[int(b)].fittings[int(f)]
        return pole.brackets[int(rest)]
    raise KeyError(key)


# ── 이름 ↔ 인덱스 ──────────────────────────────────────
def resolve(idxlib, name=None, index=None):
    """(이름, 인덱스). 하나만 주면 라이브러리에서 나머지를 찾는다. 찾지 못하면 ValueError"""
    name = (str(name).strip() if name is not None else '').removesuffix('.csv').removesuffix('.CSV')
    if index is not None and str(index).strip() != '':
        index = int(index)
        if not name:
            found = idxlib.get_name(index)
            if found is None:
                raise ValueError(f'인덱스 {index} 가 인덱스 라이브러리에 없습니다.')
            name = found
        return name, index
    if not name:
        raise ValueError('오브젝트 이름이나 인덱스를 입력하세요.')
    found = idxlib.get_index(name)
    if found is None:
        raise ValueError(f"'{name}' 이(가) 인덱스 라이브러리에 없습니다. 인덱스를 직접 입력하세요.")
    return name, int(found)


def search(idxlib, keyword, limit=200):
    """인덱스 라이브러리에서 이름 검색 → [(이름, 인덱스)]"""
    keyword = (keyword or '').strip()
    if not keyword or idxlib is None:
        return []
    df = idxlib.search(keyword)
    return [(str(r['파일명']), int(r['인덱스'])) for _, r in df.head(limit).iterrows()]


# ── 수정 ────────────────────────────────────────────
def set_component(runner, pole, key, name=None, index=None, offset=None, rotation=None):
    """구성품 이름/인덱스·위치·회전 수정. 값 검증 후에만 바꾼다"""
    obj = _get(pole, key)
    if obj is None:
        raise ValueError(f'{key} 구성품이 없습니다.')
    if isinstance(obj, EquipmentDATA) and obj.type in READ_ONLY_EQUIPMENT_TYPES:
        raise ValueError(f'{obj.type} 는 흐름방지 처리에서 자동으로 만들어져 직접 수정할 수 없습니다.')
    new_name, new_index = None, None
    if name is not None or index is not None:
        new_name, new_index = resolve(runner.idxlib, name, index)
    new_offset = None if offset is None else (float(offset[0]), float(offset[1]))
    new_rotation = None if rotation is None else float(rotation)

    if new_name is not None:
        obj.index = new_index
        if isinstance(obj, BracketDATA):
            obj.bracket_name = new_name
        elif isinstance(obj, FittingDATA):
            obj.label = new_name
        else:
            obj.name = new_name
    if new_offset is not None:
        obj.offset = new_offset
    if new_rotation is not None:
        obj.rotation = new_rotation


def add_component(runner, pole, kind, name=None, index=None, offset=(0.0, 0.0), rotation=0.0,
                  parent=None, equipment_type='기타장비'):
    """구성품 추가. 반환: 새 구성품 키"""
    if kind not in ADDABLE_KINDS:
        raise ValueError(f'추가할 수 없는 종류입니다: {kind}')
    name, index = resolve(runner.idxlib, name, index)
    offset = (float(offset[0]), float(offset[1]))
    rotation = float(rotation)
    if kind == 'br':
        pole.brackets.append(BracketDATA(bracket_type=pole.base_type, index=index, offset=offset,
                                         rotation=rotation, bracket_name=name))
        return f'br:{len(pole.brackets) - 1}'
    if kind == 'fit':
        if not parent or not parent.startswith('br:') or '/fit:' in parent:
            raise ValueError('피팅을 추가할 브래킷을 선택하세요.')
        br = _get(pole, parent)
        br.fittings.append(FittingDATA(index=index, offset=offset, rotation=rotation, label=name))
        return f'{parent}/fit:{len(br.fittings) - 1}'
    if kind == 'eq':
        if equipment_type in READ_ONLY_EQUIPMENT_TYPES:
            raise ValueError(f'{equipment_type} 는 흐름방지장치 추가 기능으로 설치하세요.')
        pole.equipments.append(EquipmentDATA(name=name, index=index, offset=offset, rotation=rotation,
                                             type=equipment_type or '기타장비'))
        return f'eq:{len(pole.equipments) - 1}'
    # acc
    if pole.mast is None:
        raise ValueError('기둥이 없는 전주에는 부속을 추가할 수 없습니다.')
    if pole.mast.accessories is None:
        pole.mast.accessories = []
    pole.mast.accessories.append(MastAccessory(name=name, index=index, offset=offset, rotation=rotation))
    return f'acc:{len(pole.mast.accessories) - 1}'


def remove_component(pole, key):
    """구성품 삭제 (기둥은 삭제 불가, 기초는 없음으로)"""
    if key == 'mast':
        raise ValueError('기둥은 삭제할 수 없습니다. 다른 기둥으로 바꾸세요.')
    if key == 'base':
        if pole.mast is not None:
            pole.mast.base = None
        return
    obj = _get(pole, key)
    if isinstance(obj, EquipmentDATA) and obj.type in READ_ONLY_EQUIPMENT_TYPES:
        raise ValueError(f'{obj.type} 는 흐름방지장치 삭제 기능으로 제거하세요.')
    kind, _, rest = key.partition(':')
    if kind == 'acc':
        pole.mast.accessories.pop(int(rest))
    elif kind == 'eq':
        pole.equipments.pop(int(rest))
    elif '/fit:' in rest:
        b, f = rest.split('/fit:')
        pole.brackets[int(b)].fittings.pop(int(f))
    else:
        pole.brackets.pop(int(rest))


def set_base(runner, pole, name=None, index=None):
    """기초 지정 (없던 기초도 추가)"""
    if pole.mast is None:
        raise ValueError('기둥이 없는 전주입니다.')
    name, index = resolve(runner.idxlib, name, index)
    if pole.mast.base is None:
        pole.mast.base = MastBase(name=name, index=index, offset=(_xy(pole.mast.offset)[0], 0.0),
                                  rotation=pole.mast.rotation)
    else:
        pole.mast.base.name, pole.mast.base.index = name, index


# ── 자동 구성 재생성 (건식게이지 변경, 되돌리기) ─────────────────
def regenerate(runner, pole, alignment):
    """전주 구성품을 현재 구간·구조물·건식게이지로 자동 배치 규칙에 따라 다시 만든다 (수동 편집 내용은 사라짐)"""
    section = SectionType.parse(pole.section)
    # 구간 종류 등록표에서 이 전주가 속한 구간의 처리 방식 사용 (새 에어조인트 타입 등)
    from core.section_edit import kind_of_pole
    kind = kind_of_pole(runner, pole) if section is not None else None
    pole.brackets, pole.mast, pole.equipments = [], None, []
    if section is None:
        processor = TunnelSectionProcessor if pole.structure == '터널' else NormalSectionProcessor
        processor.process(pole, runner.dataprocessor, runner.idxlib)
    elif kind is not None and kind.processor is not None:
        kind.processor(runner, pole, alignment)
    elif section.is_airjoint:
        AirJointProcessor.process(pole, alignment, runner.dataprocessor, runner.idxlib)
    else:
        mode = 'single' if section in AIRSECTION_SINGLE else 'double'
        AirSectionProcessor.process(pole, alignment, runner.dataprocessor, runner.idxlib, mode=mode)


GAUGE_ANGLE_EQUIPMENT_TYPES = ('장력장치',)  # 회전각이 게이지로 계산되는 장비


def set_gauge(runner, pole, gauge, alignment):
    """건식게이지 변경: 전주 좌표 갱신 + 게이지를 따르는 구성품의 x 이동 (편집 내용 유지).

    자동 배치에서 기둥·기초·밴드·급전선설비·장력장치·지선·평행틀 등은 x = 게이지(반대편 설비는 −게이지)에 놓인다.
    x 가 ±이전 게이지인 구성품만 ±새 게이지로 옮기고 이름·인덱스·높이·회전·추가한 구성품은 그대로 둔다.
    반환: (옮긴 구성품 수, 안내 문구 목록)
    """
    gauge = float(gauge)
    if gauge == 0:
        raise ValueError('건식게이지는 0 이 될 수 없습니다.')
    if (gauge < 0) != (pole.gauge < 0):
        raise ValueError('건식게이지 부호(전주 좌/우)는 바꿀 수 없습니다. 값의 크기만 바꾸세요.')
    old = float(pole.gauge)
    moved = 0
    for r in components(pole):
        x, y = r.offset
        if abs(x - old) < 1e-9:
            new_x = gauge
        elif abs(x + old) < 1e-9:
            new_x = -gauge
        else:
            continue
        obj = _get(pole, r.key)
        obj.offset = (new_x, y)
        moved += 1
    pole.gauge = gauge
    pole.coord = as_alignment(alignment).offset_point(pole.pos, gauge)

    notices = []
    if any(e.type in GAUGE_ANGLE_EQUIPMENT_TYPES for e in pole.equipments):
        notices.append('장력장치 회전각은 게이지로 계산된 값이라 이전 값 그대로입니다. '
                       '정확히 맞추려면 "자동 구성으로 되돌리기"를 쓰세요.')
    return moved, notices


# ── 전주 기본 속성 (표 셀 편집·배치도 이동) ───────────────────
BASE_TYPES = ('I', 'O', 'F')


def _track_poles(runner, pole):
    poles = runner.poledata.get(pole.track, [])
    idx = next((i for i, p in enumerate(poles) if p is pole), None)
    if idx is None:
        raise ValueError(f'{pole.post_number}: 전주 목록에 없는 전주입니다.')
    return poles, idx


def rename(runner, pole, post_number):
    """전주번호 변경 (같은 트랙에서 중복 불가)"""
    post_number = str(post_number).strip()
    if not post_number:
        raise ValueError('전주번호를 입력하세요.')
    poles, _ = _track_poles(runner, pole)
    if any(p is not pole and p.post_number == post_number for p in poles):
        raise ValueError(f'같은 트랙에 전주번호 {post_number} 가 이미 있습니다.')
    pole.post_number = post_number


def _check_span(runner, span, structure, label):
    try:
        runner.dataprocessor.get_contact_wire_span(span, structure)
    except ValueError:
        raise ValueError(f'{label} 경간 {span:g}m 가 {structure} 경간표에 없습니다.') from None


def move_pole(runner, pole, new_pos, alignment):
    """전주 측점 이동. 앞뒤 전주 사이, 앞뒤 경간이 경간표에 있어야 함, 일반개소만.
    좌표·고도·곡선·구배·구조물을 새 위치로 갱신하고 구성품 편집은 유지한다.
    구조물(토공/교량/터널)이 바뀌면 그 구조물의 건식게이지로 구성품을 자동 재생성한다.
    반환: 안내 문구 목록"""
    from core.alignment.alignment import as_alignment
    from core.alignment.define_funtion import iscurve, isslope
    from core.structure.define_structure import isbridge_tunnel

    new_pos = float(new_pos)
    new_pos = int(new_pos) if new_pos.is_integer() else new_pos
    if pole.section is not None:
        raise ValueError(f'{pole.post_number}: {pole.section} 전주는 이동할 수 없습니다 (일반개소만 이동 가능).')
    poles, idx = _track_poles(runner, pole)
    prev_pole = poles[idx - 1] if idx > 0 else None
    next_pole = poles[idx + 1] if idx + 1 < len(poles) else None
    if prev_pole is not None and new_pos <= prev_pole.pos:
        raise ValueError(f'앞 전주({prev_pole.post_number}, {prev_pole.pos}m)보다 뒤여야 합니다.')
    if next_pole is not None and new_pos >= next_pole.pos:
        raise ValueError(f'뒤 전주({next_pole.post_number}, {next_pole.pos}m)보다 앞이어야 합니다.')
    al = as_alignment(alignment)
    if not (al.start <= new_pos <= al.end):
        raise ValueError(f'선형 범위({al.start:g}~{al.end:g}m) 밖입니다.')
    new_structure = isbridge_tunnel(new_pos, runner.structure_list)
    if prev_pole is not None and prev_pole.next_pos == pole.pos:
        _check_span(runner, new_pos - prev_pole.pos, prev_pole.structure, '앞')
    if next_pole is not None and pole.next_pos == next_pole.pos:
        _check_span(runner, next_pole.pos - new_pos, new_structure, '뒤')

    # 검증 통과 → 반영
    notices = []
    old_structure = pole.structure
    pole.pos = new_pos
    pole.structure = new_structure
    _, pole.radius, pole.cant = iscurve(new_pos, runner.curvelist)
    _, pole.pitch = isslope(new_pos, runner.pitchlist)
    pole.z = al.elevation(new_pos)
    if new_structure != old_structure:
        sign = -1 if pole.gauge < 0 else 1
        pole.gauge = runner.dataprocessor.get_pole_gauge(new_structure) * sign
        regenerate(runner, pole, al)
        notices.append(f'구조물이 {old_structure} → {new_structure} 로 바뀌어 건식게이지({pole.gauge})와 '
                       '구성품을 자동으로 다시 만들었습니다.')
    pole.coord = al.offset_point(new_pos, pole.gauge)
    # 앞뒤 전주와의 연결(next_pos·span 등)을 바로 맞춤 (전체 재계산 전에도 데이터가 일관되도록)
    from core.pole.pole_updator import PoleUpdator
    PoleUpdator.update_all(poles[max(0, idx - 1):idx + 2], al)
    if prev_pole is not None and prev_pole.next_pos == pole.pos:
        notices += filter(None, [span_limit_notice(runner, prev_pole.pos, pole.pos, '앞')])
    if next_pole is not None and pole.next_pos == next_pole.pos:
        notices += filter(None, [span_limit_notice(runner, pole.pos, next_pole.pos, '뒤')])
    return notices


def span_limit_notice(runner, start_pos, end_pos, label=''):
    """경간이 설계 최대 경간(설계속도·곡선 반경·터널, 시작·끝 측점 중 엄격한 값)을 넘으면 안내 문구, 아니면 None.
    경간표에 있는 경간이면 전선은 만들어지므로 거부하지 않고 알리기만 한다."""
    from utils.comom_util import get_max_span_at
    speed = getattr(runner, 'designspeed', None)
    try:
        limit = min(get_max_span_at(p, speed, runner.curvelist, runner.structure_list) for p in (start_pos, end_pos))
    except ValueError:
        return None  # 최대 경간 기준이 없는 설계속도
    span = end_pos - start_pos
    if span <= limit:
        return None
    return (f'{label + " " if label else ""}경간 {span:g}m 가 설계 최대 경간 {limit}m 를 넘습니다 '
            f'(설계속도 {speed}km/h, 곡선 반경·터널 기준).')


def delete_pole(runner, pole):
    """전주 삭제. 앞뒤 전주가 이어지는 새 경간이 경간표에 있어야 함. 반환: 안내 문구 목록"""
    poles, idx = _track_poles(runner, pole)
    notices = []
    if 0 < idx < len(poles) - 1:
        prev_pole, next_pole = poles[idx - 1], poles[idx + 1]
        new_span = next_pole.pos - prev_pole.pos
        try:
            runner.dataprocessor.get_contact_wire_span(new_span, prev_pole.structure)
        except ValueError:
            raise ValueError(f'{pole.post_number}: 삭제하면 {prev_pole.post_number}~{next_pole.post_number} '
                             f'경간이 {new_span:g}m 가 되어 경간표에 없습니다.') from None
        notices += filter(None, [span_limit_notice(runner, prev_pole.pos, next_pole.pos,
                                                   f'{prev_pole.post_number}~{next_pole.post_number}')])
    del poles[idx]
    return notices


def set_base_type(runner, pole, base_type, alignment):
    """기본 타입(I/O/F) 변경 — 브래킷이 기본 타입으로 정해지므로 구성품을 자동 재생성"""
    base_type = str(base_type).strip().upper()
    if base_type not in BASE_TYPES:
        raise ValueError(f'기본 타입은 {", ".join(BASE_TYPES)} 중 하나입니다.')
    if pole.section is not None:
        raise ValueError(f'{pole.post_number}: {pole.section} 전주의 기본 타입은 바꿀 수 없습니다.')
    if base_type == pole.base_type:
        return []
    pole.base_type = base_type
    regenerate(runner, pole, alignment)
    return ['기본 타입이 바뀌어 구성품을 자동으로 다시 만들었습니다 (직접 편집한 구성품은 사라짐).']

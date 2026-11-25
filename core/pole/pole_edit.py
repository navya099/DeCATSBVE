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

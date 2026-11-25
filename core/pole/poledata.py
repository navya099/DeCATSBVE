import uuid
from dataclasses import dataclass, field

from core.bracket.bracket_data import BracketDATA
from core.equipment.equipment_data import EquipmentDATA
from core.mast.mastdata import Mast
from enums.section_type import FlowStop, SectionType


def new_pole_uid() -> str:
    return uuid.uuid4().hex


@dataclass
class PoleDATA:
    post_number: str
    pos: int
    next_pos: int
    span: int
    gauge: float
    next_gauge: float
    structure: str
    next_structure: str
    radius: float
    cant: float
    pitch: float
    section: SectionType | None   # None = 일반개소
    z: float
    next_z: float
    mast: Mast | None
    brackets: list[BracketDATA] = field(default_factory=list)
    equipments: list[EquipmentDATA] = field(default_factory=list)
    base_type: str = ''
    next_base_type: str = ''
    coord: tuple[float, float] = (0, 0)
    track: str = None  # 추가: 트랙 구분 (main / sub)
    side: int = None  # 추가: 좌/우 구분 -1,1
    next_side: int = None
    # 흐름방지장치 위치 (구간과 별개). 흐름방지가 붙어도 section(일반개소/에어조인트 등)은 그대로 유지된다
    flowstop: FlowStop | None = None
    # 전주 고유 ID: 전주가 이동/재계산돼도 유지. 경간(Span) = (앞 전주 uid, 뒤 전주 uid)
    uid: str = field(default_factory=new_pole_uid)

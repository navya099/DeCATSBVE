import uuid
from dataclasses import dataclass, field

from core.bracket.bracket_data import BracketDATA
from core.equipment.equipment_data import EquipmentDATA
from core.mast.mastdata import Mast
from enums.section_type import FlowStop, SectionType


def new_pole_uid() -> str:
    return uuid.uuid4().hex


@dataclass
class TwinPole:
    """복주(複柱): 한 지지점에 선 두 번째 전주. 주 전주는 측점 − spacing/2, 이 전주는 측점 + spacing/2 에 선다.
    브래킷은 PoleDATA.brackets 에 함께 두고 BracketDATA.on_twin 으로 어느 전주에 달렸는지 구분한다."""
    spacing: float
    mast: Mast | None = None
    equipments: list[EquipmentDATA] = field(default_factory=list)


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
    # 복주 에어조인트의 두 번째 전주 (없으면 None)
    twin: TwinPole | None = None

    @property
    def station_offsets(self):
        """(주 전주, 두 번째 전주) 측점 보정값. 복주가 아니면 (0, None)"""
        if self.twin is None:
            return 0, None
        half = self.twin.spacing / 2
        return -half, half

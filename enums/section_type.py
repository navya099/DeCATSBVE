"""전주 구간 종류 / 흐름방지 위치

값은 기존 문자열과 같고 str 을 상속하므로 문자열과 그대로 비교된다
(SectionType.AJ_START == "에어조인트 시작점 (1호주)"). 예전 .dat 에 문자열로 저장된 구간도 동작하고,
출력(BVE CSV 주석)도 바뀌지 않는다. 새 코드는 문자열 대신 이 enum 을 쓴다.
"""
from enum import Enum

NORMAL_LABEL = '일반개소'


class _StrEnum(str, Enum):
    # f-string/str() 에서 'SectionType.AJ_START' 가 아니라 값이 나오도록 (Python 3.10~3.13 공통)
    __str__ = str.__str__
    __format__ = str.__format__

    @classmethod
    def parse(cls, value):
        """문자열/enum → 멤버. 해당 없음(일반개소, 'None', 빈 값 등)이면 None"""
        if value is None or isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip())
        except ValueError:
            return None


class SectionType(_StrEnum):
    """전주 구간 (None = 일반개소)"""
    AJ_START = "에어조인트 시작점 (1호주)"
    AJ_2 = "에어조인트 (2호주)"
    AJ_MIDDLE = "에어조인트 중간주 (3호주)"
    AJ_4 = "에어조인트 (4호주)"
    AJ_END = "에어조인트 끝점 (5호주)"

    AS1_1 = "에어섹션1구간_1호주"
    AS1_2 = "에어섹션1구간_2호주"
    AS1_3 = "에어섹션1구간_3호주"
    AS1_4_S = "에어섹션1구간_4호주_S"   # 단일 에어섹션
    AS1_4_D = "에어섹션1구간_4호주_D"   # 이중 에어섹션
    AS1_5 = "에어섹션1구간_5호주"
    AS2_1 = "에어섹션2구간_1호주"
    AS2_2 = "에어섹션2구간_2호주"
    AS2_3 = "에어섹션2구간_3호주"
    AS2_4 = "에어섹션2구간_4호주"

    @property
    def is_airjoint(self):
        return self in AIRJOINT_SEQUENCE

    @property
    def is_airsection(self):
        return self.value.startswith("에어섹션")


AIRJOINT_SEQUENCE = (SectionType.AJ_START, SectionType.AJ_2, SectionType.AJ_MIDDLE,
                     SectionType.AJ_4, SectionType.AJ_END)
AIRSECTION_SINGLE = (SectionType.AS1_1, SectionType.AS1_2, SectionType.AS1_3, SectionType.AS1_4_S,
                     SectionType.AS1_5)
AIRSECTION_DOUBLE = (SectionType.AS1_1, SectionType.AS1_2, SectionType.AS1_3, SectionType.AS1_4_D,
                     SectionType.AS2_1, SectionType.AS2_2, SectionType.AS2_3, SectionType.AS2_4)


class FlowStop(_StrEnum):
    """흐름방지장치 위치 (전주 구간과 별개, PoleDATA.flowstop)"""
    START = "흐름방지 시작점"
    MIDDLE = "흐름방지 중간점"
    END = "흐름방지 끝점"


def section_label(pole):
    """화면/CSV 주석용 구간 이름: 에어조인트·에어섹션 구간 > 흐름방지 위치 > '일반개소'"""
    if pole.section:
        return str(pole.section)
    flowstop = getattr(pole, 'flowstop', None)
    return str(flowstop) if flowstop else NORMAL_LABEL

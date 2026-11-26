"""도면 설정·레이어·전주 치수"""
import re
from dataclasses import dataclass


@dataclass
class DrawingSettings:
    """plan_scale: 평면도 축척 1:N (문자·기호 크기 = 기준 × N/1000)
    profile_v_scale: 종단면도 수직 축척 1:N. 수평은 평면 축척 → 수직 과장 = plan_scale / profile_v_scale"""
    plan_scale: float = 1000
    profile_v_scale: float = 100

    def __post_init__(self):
        if self.plan_scale <= 0 or self.profile_v_scale <= 0:
            raise ValueError('도면 축척은 0보다 커야 합니다.')

    @property
    def symbol(self):
        """평면 기호·문자 배율 (1:1000 → 1)"""
        return self.plan_scale / 1000

    @property
    def exaggeration(self):
        """종단면도 높이 과장 배율 (예: 1:1000 / 1:100 → 10)"""
        return self.plan_scale / self.profile_v_scale


# 레이어: (이름, 색) — 레거시 도면과 같은 이름·색 (새로 추가: 조가선·무효선·급전선·보호선·흐름방지선)
LAYERS = {
    'alignment': ('선형', 1),
    'profile_alignment': ('종단선형', 1),
    'pole': ('전주', 4),
    'bracket': ('브래킷', 6),
    'label': ('전주번호', 7),
    'contact': ('전차선', 3),
    'messenger': ('조가선', 3),
    'inactive': ('무효선', 1),
    'feeder': ('급전선', 2),
    'protect': ('보호선', 11),
    'flowstop': ('흐름방지선', 30),
    'other_wire': ('기타전선', 8),
}


def wire_layer(label):
    """전선 이름 → 레이어 키"""
    label = str(label or '')
    if label.startswith('무효') and not label.startswith('무효->'):
        return 'inactive'
    if '조가선' in label:
        return 'messenger'
    if '전차선' in label:
        return 'contact'
    if label in ('AF', '급전선', '부급전선') or label.startswith('급전'):
        return 'feeder'
    if label in ('FPW', '보호선'):
        return 'protect'
    if '흐름방지' in label:
        return 'flowstop'
    return 'other_wire'


# 종단면도 전주 치수 (높이 m, 폭 m, 레일면 위 시작 높이 m) — 레거시 도면 값
MAST_WIDTH = {'P10': 0.2674, 'P12': 0.312, 'H250': 0.25, 'H300': 0.3, 'H208': 0.25}
TUNNEL_HANGER = (1.735, 0.25, 4.54)          # 터널하수강
DEFAULT_MAST = (9.0, 0.3, 0.0)


def mast_dimensions(name):
    """전주 오브젝트 이름 → (높이, 폭, 시작 높이). 이름의 규격(P10·P12·H250…)과 길이(9m·8.5m) 사용, 모르면 기본값"""
    name = str(name or '')
    if '하수강' in name:
        return TUNNEL_HANGER
    length = re.search(r'(\d+(?:\.\d+)?)\s*m', name)
    height = float(length.group(1)) if length else DEFAULT_MAST[0]
    kind = re.search(r'(P\s*1[02]|H\s*\d{3})', name.upper())
    width = MAST_WIDTH.get(kind.group(1).replace(' ', ''), DEFAULT_MAST[1]) if kind else DEFAULT_MAST[1]
    return height, width, 0.0

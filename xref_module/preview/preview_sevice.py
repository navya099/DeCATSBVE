
from xref_module.filefinder import FileLocator
from xref_module.path_resolver import PathResolver
from xref_module.preview.category import PreviewCategory
from xref_module.preview.previe_assembler import PreviewAssembler
from xref_module.preview.preview_item import PreviewItem
from xref_module.objmodel.transform import Transform
from xref_module.preview.preview_result import PreviewBuildResult
from xref_module.vector3.vector3 import Vector3
import math

# 미리보기 배경 오브젝트: BVE Object 폴더(사용자 설정) 기준 상대 경로.
# Object 폴더에 없으면 저장소 assets/preview 의 같은 이름 파일, 그것도 없으면 건너뛰고 누락 목록에 표시
TRACK_OBJECT = '철도표준라이브러리/궤도/표준단면/자갈도상/일반철도/5M레일_신선_전차선X.csv'
CLEARANCE_OBJECT = 'temp/건축한계.csv'
CENTERLINE_OBJECT = 'temp/선로중심선.csv'
# (구조물, 단선/복선) → 노반 오브젝트. 복선은 본선(트랙 0)에만 복선 단면을 그림
STRUCTURE_OBJECTS = {
    ('교량', 'single'): '철도표준라이브러리/노반/교량/psc거더교_단선.csv',
    ('교량', 'double'): '전라선/노반/교량/psc빔 복선.csv',
    ('터널', 'single'): '동해선/노반/터널/natm.csv',
    ('터널', 'double'): '호남선/노반/구조물/터널/4.3m터널.csv',
    ('토공', 'single'): '동해선/노반/토공/표준횡단면도.csv',
    ('토공', 'double'): '중앙선/노반/토공/6공구복선노반l.csv',
}


class PreviewService:
    def __init__(self, idxlib=None):
        self.idxlib = idxlib          # 인덱스 → 경로 (정확한 오브젝트 파일, 같은 이름 파일이 여러 폴더에 있을 때)
        self._locators = {}

    def locator(self, root):
        """이름 검색기 (폴더별로 캐시)"""
        if root not in self._locators:
            self._locators[root] = FileLocator(root)
        return self._locators[root]

    @staticmethod
    def _missing(missing, name):
        """찾지 못한 구성품 기록 ('null' = BVE 빈 오브젝트 자리는 제외)"""
        if str(name).strip().lower() != 'null':
            missing.append(name)

    def find(self, name, index=None):
        """구성품 오브젝트 파일:
        1) 인덱스 라이브러리 경로 — BVE Object 폴더, 저장소 assets/preview/전철전력 (대소문자 무시)
        2) 이름 검색 — Object 폴더의 전철전력 라이브러리, 저장소 assets/preview/전철전력"""
        if index is not None and self.idxlib is not None and hasattr(self.idxlib, 'get_path_by_index'):
            path = PathResolver.library_object(self.idxlib.get_path_by_index(index))
            if path:
                return path
        if not name:
            return None
        for root in (PathResolver.library_root(), PathResolver.BUNDLED_LIBRARY):
            path = self.locator(root).find(name)
            if path:
                return path
        return None

    @staticmethod
    def _background(items, missing, relative, transform, category):
        """배경 오브젝트: Object 폴더에 있으면 그 파일(사용자 수정본), 없으면 저장소 assets/preview 파일"""
        path = PathResolver.preview_object(relative)
        if path is not None:
            items.append(PreviewItem(path=path, transform=transform, category=category))
        else:
            missing.append(PathResolver.object_path(relative))

    def _component(self, items, missing, obj, name, category, pivot, dy=0.0):
        """구성품 하나: 오브젝트 파일을 찾아 (x, 진행 방향 dy, 높이) 에 배치. 없으면 누락 목록"""
        if obj is None or not name:
            return
        path = self.find(name, getattr(obj, 'index', None))
        if path is None:
            self._missing(missing, name)
            return
        x, z = obj.offset[0], obj.offset[1]
        items.append(PreviewItem(path=path, category=category,
                                 transform=Transform(x=x, y=dy, z=z, rotation=obj.rotation, pivot=pivot)))

    def _mast(self, items, missing, mast, pivot, dy):
        """기둥 + 기초 + 부속(밴드)"""
        if mast is None:
            return
        self._component(items, missing, mast, mast.name, PreviewCategory.POLE, pivot, dy)
        if mast.base is not None:
            self._component(items, missing, mast.base, mast.base.name, PreviewCategory.POLE, pivot, dy)
        for acc in mast.accessories or []:
            if acc:
                self._component(items, missing, acc, acc.name, PreviewCategory.POLE, pivot, dy)

    def build(self, pole, trackidx, distnace=4.3, direction=1, mode='single', idxlib=None):
        """전주 하나의 미리보기 오브젝트 (기둥·기초·밴드, 브래킷·피팅, 레일·건축한계·중심선, 설비, 노반).
        복주 에어조인트는 앞 전주(측점 − 간격/2)와 뒤 전주(측점 + 간격/2)를 진행 방향으로 떼어 놓는다."""
        if idxlib is not None:
            self.idxlib = idxlib
        items = []
        missing = []
        if not pole:
            return PreviewBuildResult(objects=[], missing=["pole이 None입니다"])
        pivot = Vector3(0, 0, 0) if trackidx == 0 else Vector3(distnace * direction, 0, 0)
        twin = getattr(pole, 'twin', None)
        front_dy, rear_dy = pole.station_offsets if twin is not None else (0.0, None)

        # 1. 기둥·기초·부속 (복주면 뒤 전주 것도)
        try:
            self._mast(items, missing, pole.mast, pivot, front_dy)
            if twin is not None:
                self._mast(items, missing, twin.mast, pivot, rear_dy)
        except Exception as e:  # noqa: BLE001 - 구성품 하나 때문에 미리보기 전체가 멈추지 않도록
            print(f"[Mast 처리 오류] {e}")
            missing.append("기둥 처리 실패")

        # 2. 브래킷과 피팅 (복주면 달린 전주 위치)
        for br in pole.brackets or []:
            if not br:
                continue
            dy = rear_dy if twin is not None and getattr(br, 'on_twin', False) else front_dy
            try:
                self._component(items, missing, br, br.bracket_name, PreviewCategory.BRACKET, pivot, dy)
                for fit in br.fittings or []:
                    if fit:
                        self._component(items, missing, fit, fit.label, PreviewCategory.BRACKET, pivot, dy)
            except Exception as e:  # noqa: BLE001
                print(f"[Bracket 처리 오류] {e}")
                missing.append("브래킷 처리 실패")

        # 3. 레일 · 건축한계 · 궤도중심선 (캔트만큼 기울임)
        roll = math.degrees(math.atan(pole.cant / 1.5))
        for relative, category in ((TRACK_OBJECT, PreviewCategory.TRACK), (CLEARANCE_OBJECT, PreviewCategory.TRACK),
                                   (CENTERLINE_OBJECT, PreviewCategory.CENTERLINE)):
            self._background(items, missing, relative, Transform(x=0, z=0, rotation=0, pivot=pivot, roll=roll),
                             category)

        # 4. 설비 (복주면 뒤 전주 설비도)
        equipment_groups = [(pole.equipments, front_dy)] + ([(twin.equipments, rear_dy)] if twin is not None else [])
        for equipments, dy in equipment_groups:
            for equip in equipments or []:
                try:
                    if equip:
                        self._component(items, missing, equip, equip.name, PreviewCategory.FEEDER, pivot, dy)
                except Exception as e:  # noqa: BLE001
                    print(f"[Equipment 처리 오류] {e}")
                    missing.append("설비 처리 실패")

        # 5. 구조물 (복선은 본선에만 복선 단면)
        structure = pole.structure if pole.structure in ('교량', '터널') else '토공'
        layout = 'single' if mode == 'single' else 'double'
        if layout == 'single' or trackidx == 0:
            self._background(items, missing, STRUCTURE_OBJECTS[(structure, layout)],
                             Transform(x=0, z=0, rotation=0, pivot=pivot), PreviewCategory.STRUCTURE)

        # 최종 조립
        objects = PreviewAssembler.load_items(items, failed=missing)
        return PreviewBuildResult(objects=objects, missing=missing)


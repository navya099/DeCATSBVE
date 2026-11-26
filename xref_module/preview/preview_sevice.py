
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
    def __init__(self):
        self._locator = None
        self._locator_root = None

    @property
    def locator(self):
        """전철전력 라이브러리 검색기 (Object 폴더 설정이 바뀌면 다시 만듦)"""
        root = PathResolver.library_root()
        if self._locator is None or self._locator_root != root:
            self._locator, self._locator_root = FileLocator(root), root
        return self._locator

    @staticmethod
    def _background(items, missing, relative, transform, category):
        """배경 오브젝트: Object 폴더에 있으면 그 파일(사용자 수정본), 없으면 저장소 assets/preview 파일"""
        path = PathResolver.preview_object(relative)
        if path is not None:
            items.append(PreviewItem(path=path, transform=transform, category=category))
        else:
            missing.append(PathResolver.object_path(relative))

    def build(self, pole, trackidx, distnace=4.3, direction=1, mode='single'):
        items = []
        missing = []
        distnace *= direction
        if trackidx == 0:
            pivot = Vector3(0,0,0)
        else:
            pivot = Vector3(distnace, 0, 0)

        if not pole:
            return PreviewBuildResult(objects=[], missing=["pole이 None입니다"])

        # 2. 기둥
        try:
            mast = pole.mast
            if mast:
                if mast.name:
                    path = self.locator.find(mast.name)
                    if path:
                        items.append(
                            PreviewItem(
                                path=path,
                                transform=Transform(x=mast.offset[0],z=mast.offset[1], rotation=mast.rotation,pivot=pivot),
                                category=PreviewCategory.POLE
                            )
                        )
                    else:
                        missing.append(mast.name)
        except Exception as e:
            print(f"[Mast 처리 오류] {e}")
            missing.append("mast 처리 실패")

        # 2-1. 전주기초
        try:
            mast = pole.mast
            if mast:
                if mast.base:
                    base = mast.base
                    if base.name:
                        path = self.locator.find(mast.base.name)
                        if path:
                            items.append(
                                PreviewItem(
                                    path=path,
                                    transform=Transform(x=base.offset[0], z=base.offset[1], rotation=base.rotation, pivot=pivot),
                                    category=PreviewCategory.POLE
                                )
                            )
                        else:
                            missing.append(base.name)
        except Exception as e:
            print(f"[기초 처리 오류] {e}")
            missing.append("기초 처리 실패")

        # 2-2. 전주악세서리
        try:
            mast = pole.mast
            if mast:
                if mast.accessories:
                    for ac in mast.accessories:
                        if ac:
                            if ac.name:
                                path = self.locator.find(ac.name)
                                if path:
                                    items.append(
                                        PreviewItem(
                                            path=path,
                                            transform=Transform(x=ac.offset[0], z=ac.offset[1], rotation=ac.rotation,
                                                                pivot=pivot),
                                            category=PreviewCategory.POLE
                                        )
                                    )
                                else:
                                    missing.append(ac.name)
        except Exception as e:
            print(f"[전주 악세서리 처리 오류] {e}")
            missing.append("악세서리 처리 실패")

        # 3. 브래킷
        for br in getattr(pole, "brackets", []):
            try:
                if br:
                    if br.bracket_name:
                        path = self.locator.find(br.bracket_name)
                        if path:
                            items.append(
                                PreviewItem(
                                    path=path,
                                    transform=Transform(x=br.offset[0], z=br.offset[1], rotation=br.rotation,pivot=pivot),
                                    category=PreviewCategory.BRACKET
                                )
                            )
                        else:
                            missing.append(br.bracket_name)

                    # 브래킷 피팅류
                    for f in getattr(br, "fittings", []):
                        try:
                            if f:
                                if f.label:
                                    path = self.locator.find(f.label)
                                    if path:
                                        items.append(
                                            PreviewItem(
                                                path=path,
                                                transform=Transform(x=f.offset[0], z=f.offset[1],rotation=f.rotation,pivot=pivot),
                                                category=PreviewCategory.BRACKET
                                            )
                                        )
                                    else:
                                        missing.append(f.label)
                        except Exception as e:
                            print(f"[Fitting 처리 오류] {e}")
                            missing.append("fitting 처리 실패")
            except Exception as e:
                print(f"[Bracket 처리 오류] {e}")
                missing.append("bracket 처리 실패")

        # 4. 레일 · 4-1. 건축한계 · 4-2. 궤도중심선 (캔트만큼 기울임)
        roll = math.degrees(math.atan(pole.cant / 1.5))
        for relative, category in ((TRACK_OBJECT, PreviewCategory.TRACK), (CLEARANCE_OBJECT, PreviewCategory.TRACK),
                                   (CENTERLINE_OBJECT, PreviewCategory.CENTERLINE)):
            self._background(items, missing, relative, Transform(x=0, z=0, rotation=0, pivot=pivot, roll=roll),
                             category)

        # 5. 장비들
        for equip in getattr(pole, "equipments", []):
            try:
                if equip:
                    if equip.name:
                        path = self.locator.find(equip.name)
                        if path:
                            items.append(
                                PreviewItem(
                                    path=path,
                                    transform=Transform(x=equip.offset[0], z=equip.offset[1], rotation=equip.rotation,pivot=pivot),
                                    category=PreviewCategory.FEEDER
                                )
                            )
                        else:
                            missing.append(equip.name)
            except Exception as e:
                print(f"[Equipment 처리 오류] {e}")
                missing.append("equipment 처리 실패")

        # 6. 구조물 (복선은 본선에만 복선 단면)
        structure = pole.structure if pole.structure in ('교량', '터널') else '토공'
        layout = 'single' if mode == 'single' else 'double'
        if layout == 'single' or trackidx == 0:
            self._background(items, missing, STRUCTURE_OBJECTS[(structure, layout)],
                             Transform(x=0, z=0, rotation=0, pivot=pivot), PreviewCategory.STRUCTURE)

        # 최종 조립
        objects = PreviewAssembler.load_items(items, failed=missing)
        return PreviewBuildResult(objects=objects, missing=missing)


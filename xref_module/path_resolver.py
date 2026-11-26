"""BVE Object 폴더 기준 경로 (PC마다 다른 위치는 사용자 설정 bve_object_root, file_io/user_settings.py)"""
import os

from file_io import user_settings

# Object 폴더 안의 전철전력 표준 라이브러리 (전주·브래킷·설비 오브젝트 검색 위치)
CATENARY_LIBRARY = os.path.join('철도표준라이브러리', '전철전력')
# 저장소에 포함된 미리보기 배경 오브젝트(레일·건축한계·노반 단면, 텍스처 포함). 파일명만으로 찾음
BUNDLED_PREVIEW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'preview')


class PathResolver:
    @staticmethod
    def object_root():
        """BVE Object 폴더 (사용자 설정)"""
        return user_settings.get('bve_object_root')

    @classmethod
    def library_root(cls):
        return os.path.join(cls.object_root(), CATENARY_LIBRARY)

    @classmethod
    def object_path(cls, relative):
        """Object 폴더 기준 상대 경로 → 절대 경로 ('/', '\\' 모두 허용)"""
        parts = relative.replace('\\', '/').split('/')
        return os.path.join(cls.object_root(), *parts)

    @classmethod
    def preview_object(cls, relative):
        """미리보기 배경 오브젝트 경로: 1) BVE Object 폴더/상대경로 2) 저장소 assets/preview/파일명.
        없으면 None (찾아본 경로는 preview_candidates)"""
        return next((p for p in cls.preview_candidates(relative) if os.path.isfile(p)), None)

    @classmethod
    def preview_candidates(cls, relative):
        name = relative.replace('\\', '/').split('/')[-1]
        return [cls.object_path(relative), os.path.join(BUNDLED_PREVIEW, name)]

    @classmethod
    def resolve(cls, names: list[str]) -> list[str]:
        return [os.path.join(cls.library_root(), f"{name}.csv") for name in names]

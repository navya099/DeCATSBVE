"""BVE Object 폴더 기준 경로 (PC마다 다른 위치는 사용자 설정 bve_object_root, file_io/user_settings.py)"""
import os

from file_io import user_settings

# Object 폴더 안의 전철전력 표준 라이브러리 (전주·브래킷·설비 오브젝트 검색 위치)
CATENARY_LIBRARY = os.path.join('철도표준라이브러리', '전철전력')


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
    def resolve(cls, names: list[str]) -> list[str]:
        return [os.path.join(cls.library_root(), f"{name}.csv") for name in names]

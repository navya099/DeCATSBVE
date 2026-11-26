"""BVE Object 폴더 기준 경로 (PC마다 다른 위치는 사용자 설정 bve_object_root, file_io/user_settings.py)"""
import os

from file_io import user_settings

# Object 폴더 안의 전철전력 표준 라이브러리 (전주·브래킷·설비 오브젝트 검색 위치)
CATENARY_LIBRARY = os.path.join('철도표준라이브러리', '전철전력')
# 저장소에 포함된 미리보기 배경 오브젝트(레일·건축한계·노반 단면, 텍스처 포함). 파일명만으로 찾음
BUNDLED_PREVIEW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'preview')
# 저장소에 포함된 전철전력 라이브러리 (Object 폴더의 철도표준라이브러리/전철전력 과 같은 구조)
BUNDLED_LIBRARY = os.path.join(BUNDLED_PREVIEW, '전철전력')


def _split(relative):
    return [p for p in str(relative).replace('\\', '/').split('/') if p]


def find_case_insensitive(base, parts):
    """base 아래 parts 경로를 대소문자 구분 없이 찾기 (Windows 경로를 Linux 에서도). 없으면 None"""
    current = base
    for part in parts:
        candidate = os.path.join(current, part)
        if os.path.exists(candidate):
            current = candidate
            continue
        try:
            entries = os.listdir(current)
        except OSError:
            return None
        match = next((e for e in entries if e.lower() == part.lower()), None)
        if match is None:
            return None
        current = os.path.join(current, match)
    return current


class PathResolver:
    BUNDLED_LIBRARY = BUNDLED_LIBRARY

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
    def library_object(cls, index_path):
        """인덱스 라이브러리 경로(Object 폴더 기준, 예: 철도표준라이브러리\\전철전력\\CAKO250\\토공\\x.csv) → 파일.
        1) BVE Object 폴더 2) 저장소 assets/preview/전철전력 (철도표준라이브러리/전철전력 아래만). 없으면 None"""
        if not index_path or not isinstance(index_path, str):
            return None
        parts = _split(index_path)
        found = find_case_insensitive(cls.object_root(), parts)
        if found and os.path.isfile(found):
            return found
        lib = _split(CATENARY_LIBRARY)
        if [p.lower() for p in parts[:len(lib)]] == [p.lower() for p in lib]:
            found = find_case_insensitive(BUNDLED_LIBRARY, parts[len(lib):])
            if found and os.path.isfile(found):
                return found
        return None

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

# core/geometry/face.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Face:
    """면: 꼭짓점 a, b, c (+ 4번째 이후는 rest). BVE AddFace 는 꼭짓점 3개 이상"""
    a: int
    b: int
    c: int
    rest: tuple = ()

    def indices(self) -> tuple:
        return (self.a, self.b, self.c) + tuple(self.rest)

    def edges(self):
        """둘레 모서리 (i, j) 목록"""
        idx = self.indices()
        return [(idx[k], idx[(k + 1) % len(idx)]) for k in range(len(idx))]

    def triangles(self):
        """삼각형 분할 (부채꼴)"""
        idx = self.indices()
        return [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]

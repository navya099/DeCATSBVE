from xref_module.world.bve_transform import OpenBVETransform
from xref_module.world.coordinatesystem import CoordinateSystem
from xref_module.world.world_transform import WorldTransform


class CoordinateConverter:
    def __init__(self):

        self._map = {
            CoordinateSystem.OPENBVE: OpenBVETransform(),
            CoordinateSystem.WORLD: WorldTransform(),
        }

    def convert(self, csvobj, target: CoordinateSystem):
        if csvobj.coordsystem == target:
            return

        src_tf = self._map[csvobj.coordsystem]
        dst_tf = self._map[target]

        for mesh in csvobj.meshes:
            mesh.vertices = [
                dst_tf.from_world(
                    src_tf.to_world(v)
                )
                for v in mesh.vertices
            ]

        csvobj.coordsystem = target

    # -----------------------------
    # 단일 점 변환
    # -----------------------------
    def convert_point(self, point, target: CoordinateSystem, source: CoordinateSystem = CoordinateSystem.OPENBVE):
        """
        단일 점 변환: source 좌표계 → (WORLD) → target 좌표계
        point: Vector3 (source 좌표계, 기본 OPENBVE — 미리보기 pivot 이 OpenBVE 기준)
        target: 변환할 목표 좌표계
        return: Vector3 (target 좌표계)
        """
        src_tf = self._map[source]
        dst_tf = self._map[target]
        return dst_tf.from_world(src_tf.to_world(point))

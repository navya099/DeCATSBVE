from file_io.file_controler import FileController
from xref_module.objmodel.object_modifyer import ObjectModifier
from xref_module.preview.layer_object import PreviewLayerObject
from xref_module.preview.preview_item import PreviewItem
from xref_module.temp_parser import CSVObjectParser
from xref_module.world.convert import CoordinateConverter


class PreviewAssembler:
    @staticmethod
    def load_items(items: list[PreviewItem], failed: list | None = None):
        """오브젝트 파일을 읽어 배치. 읽지 못한 파일은 failed 에 ('경로: 오류') 를 넣고 건너뜀 (하나 때문에 전체 실패 X)"""
        objects = []
        filecontroller = FileController()
        coordsystemconvertor = CoordinateConverter()
        for item in items:
            try:
                objects.append(PreviewAssembler._load_item(item, filecontroller, coordsystemconvertor))
            except Exception as e:  # noqa: BLE001 - 파일 없음·형식 오류 등
                if failed is None:
                    raise
                failed.append(f'{item.path}: {e}')
        return objects

    @staticmethod
    def _load_item(item, filecontroller, coordsystemconvertor):
        filecontroller.set_path(item.path)
        filecontroller.load()

        csvobj = CSVObjectParser(
            filecontroller.get_lines()
        ).parse()
        ## 좌표계는 항상 WORLD 기준으로 ObjectModifier 적용
        from xref_module.world.coordinatesystem import CoordinateSystem
        coordsystemconvertor.convert(csvobj, CoordinateSystem.WORLD)
        #피봇 좌표계 변경
        pivot = coordsystemconvertor.convert_point(item.transform.pivot, CoordinateSystem.WORLD)
        modifier = ObjectModifier(csvobj)
        modifier.set_pivot(pivot)
        #필수: 월드좌표로 배치;
        modifier.translate_world(
            pivot.x,
            pivot.y,
            pivot.z
        )
        modifier.rotate_z(item.transform.rotation)
        modifier.rotate_y(item.transform.roll)

        modifier.translate_local(
            item.transform.x,
            item.transform.y,
            item.transform.z
        )
        modifier.apply()

        # PreviewObject 생성
        preview_obj = PreviewLayerObject(
            mesh=csvobj,
            pivot=(pivot.x, pivot.y, pivot.z),
            category=item.category.name,
            color=None  # 나중에 _track_color()로 채움
        )

        return preview_obj


"""BVE CSV 오브젝트 파서(미리보기·도면): python -m pytest tests"""
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from file_io.file_controler import FileController  # noqa: E402
from xref_module.temp_parser import CSVObjectParser  # noqa: E402


def parse(text):
    p = CSVObjectParser(text.splitlines())
    return p.parse(), p


def verts(mesh):
    return [(round(v.x, 9), round(v.y, 9), round(v.z, 9)) for v in mesh.vertices]


def test_case_comments_addface2_and_polygons():
    obj, parser = parse('''
createmeshbuilder ; 주석
ADDVERTEX, 0, 0, 0 ;끝 주석
AddVertex, 1, 0, 0,
AddVertex, 1, 1, 0
AddVertex, 0, 1, 0
AddFace2, 0, 1, 2, 3
addface, 0, 1, 9
SetColor, 255, 0, 0
''')
    mesh, = obj.meshes
    assert verts(mesh) == [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    face, = mesh.faces                                    # 범위 밖 정점(9) 면은 건너뜀
    assert face.indices() == (0, 1, 2, 3) and face.edges() == [(0, 1), (1, 2), (2, 3), (3, 0)]
    assert face.triangles() == [(0, 1, 2), (0, 2, 3)]
    assert parser.unsupported == set()


def test_translate_scope_scale_mirror_rotate():
    obj, _ = parse('''
CreateMeshBuilder
AddVertex, 1, 0, 0
CreateMeshBuilder
AddVertex, 1, 0, 0
Translate, 0, 1, 0
TranslateAll, 0, 0, 2
Scale, 2, , 0
MirrorAll, 1, 0, 0
''')
    first, second = obj.meshes
    assert verts(first) == [(-1, 0, 2)]                   # Translate 는 현재 메시만, *All 은 전부
    assert verts(second) == [(-2, 1, 2)]                  # Scale 빈 값·0 은 1
    rot, _ = parse('CreateMeshBuilder\nAddVertex, 1, 0, 0\nRotate, 0, 1, 0, 90\n')
    assert verts(rot.meshes[0]) == [(0, 0, -1)]
    rot_all, _ = parse('CreateMeshBuilder\nAddVertex, 1, 0, 0\nCreateMeshBuilder\nAddVertex, 0, 1, 0\n'
                       'RotateAll, 0, 0, 1, 90\n')
    assert [verts(m) for m in rot_all.meshes] == [[(0, 1, 0)], [(-1, 0, 0)]]


def test_cube_and_cylinder():
    obj, _ = parse('CreateMeshBuilder\nCube, 1, 2, 3\n')
    mesh, = obj.meshes
    assert len(mesh.vertices) == 8 and len(mesh.faces) == 6
    assert {abs(c) for v in verts(mesh) for c in v} == {1, 2, 3}
    assert sum(len(f.edges()) for f in mesh.faces) == 24
    obj, _ = parse('CreateMeshBuilder\nCylinder, 8, 1, 2, 4\n')
    mesh, = obj.meshes
    assert len(mesh.vertices) == 16 and len(mesh.faces) == 8 + 2
    ys = sorted({v[1] for v in verts(mesh)})
    assert ys == [-2, 2]
    obj, _ = parse('CreateMeshBuilder\nCylinder, 6, -1, 1, 2\n')          # 음수 반지름: 그 뚜껑 없음
    assert len(obj.meshes[0].faces) == 6 + 1


def test_without_create_mesh_builder_and_unknown_command():
    obj, parser = parse('AddVertex, 0, 0, 0\nAddVertex, 1, 0, 0\nAddVertex, 0, 1, 0\nAddFace, 0, 1, 2\nShear, 1, 0, 0\n')
    assert len(obj.meshes) == 1 and len(obj.meshes[0].faces) == 1
    assert parser.unsupported == {'shear'}


def test_bundled_library_parses_completely():
    """저장소 라이브러리(전철전력·배경) 전부: 읽기 성공, 알 수 없는 명령 없음, 면 인덱스 유효"""
    count = 0
    for root, _, files in os.walk(os.path.join(ROOT, 'assets', 'preview')):
        for f in files:
            if not f.lower().endswith('.csv'):
                continue
            fc = FileController(os.path.join(root, f))
            fc.load()
            parser = CSVObjectParser(fc.get_lines())
            obj = parser.parse()
            assert parser.unsupported == set(), (f, parser.unsupported)
            for mesh in obj.meshes:
                assert all(0 <= i < len(mesh.vertices) for face in mesh.faces for i in face.indices())
            count += 1
    assert count > 800


def test_translate_all_applied_to_wire_objects():
    """이전 파서는 TranslateALL 을 무시해 전차선 오브젝트가 5.2m 높게 그려졌음"""
    path = os.path.join(ROOT, 'assets', 'preview', '전철전력', '공통', '전선', '전차선_가고1.2m_50m.csv')
    fc = FileController(path)
    fc.load()
    obj = CSVObjectParser(fc.get_lines()).parse()
    ys = [v.y for m in obj.meshes for v in m.vertices]
    assert min(ys) < 0.5 and max(ys) < 2.0           # 레일면 기준이 아니라 전선 기준(0 근처)으로 이동됨


def test_cp949_file(tmp_path):
    path = tmp_path / 'cp949.csv'
    path.write_bytes('; 한글 주석\nCreateMeshBuilder\nAddVertex, 1, 2, 3\n'.encode('cp949'))
    fc = FileController(str(path))
    fc.load()
    assert fc.encoding == 'cp949'
    obj = CSVObjectParser(fc.get_lines()).parse()
    assert verts(obj.meshes[0]) == [(1, 2, 3)]

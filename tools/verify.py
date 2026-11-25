"""전선 기하 검증: 출력된 전선을 BVE 배치 방식으로 다시 놓았을 때 다음 지지점에 닿는지

BVE freeobj 배치 모델:
    - 트랙 위치 s 의 기준점 = 블록 시작점 + (s - 블록시작) × 블록 진행방향
      (블록 진행방향 = 이 블록 점 → 다음 블록 점, 레일 1 이상도 같은 방식)
    - x 오프셋은 진행방향의 우측(+)
    - yaw(+) 는 우회전
전선 시작점에서 yaw 방향으로 (시작점~끝 지지점 거리) 만큼 뻗은 끝점과, 다음 전주의 실제 지지점 사이의
횡방향 오차를 계산한다. 상선은 rail_info.txt 의 실제 레일 좌표(BVE 계산값)를 기준으로 삼는다.

사용 예:
    python -m tools.verify out/double --coord D:/route/info/bve_coordinates.txt \
        --rail-info D:/route/info/rail_info.txt --sub-rail 1
"""
import argparse
import json
import math
import os
import sys

BLOCK = 25


def load_main_line(coord_path):
    with open(coord_path, encoding='utf-8') as f:
        return [tuple(map(float, l.split(',')[:2])) for l in f if l.strip()]


def load_rail_line(rail_info_path, rail_key, n_blocks):
    pts = {}
    with open(rail_info_path, encoding='utf-8') as f:
        for line in f:
            c = line.strip().split(',')
            if len(c) >= 5 and int(float(c[1])) == rail_key:
                pts[float(c[0])] = (float(c[2]), float(c[3]))
    return [pts.get(i * float(BLOCK)) for i in range(n_blocks)]


def _frame(line, s):
    i = min(int(s // BLOCK), len(line) - 2)
    (x1, y1), (x2, y2) = line[i], line[i + 1]
    th = math.atan2(y2 - y1, x2 - x1)
    t = s - i * BLOCK
    return (x1 + t * math.cos(th), y1 + t * math.sin(th)), th


def _world(line, s, x):
    (px, py), th = _frame(line, s)
    return (px + x * math.sin(th), py - x * math.cos(th)), th


def wire_errors(rows, line):
    """[(오차 m, row), ...] 오차 큰 순"""
    res = []
    for w in rows:
        if w['next_pos'] is None or w['station'] is not None:
            continue  # 별도 측점에 놓이는 장력장치 등은 제외
        a, th = _world(line, w['pos'], w['start'][0])
        b, _ = _world(line, w['next_pos'], w['end'][0])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        d = th - math.radians(w['yaw'])
        e = math.hypot(a[0] + length * math.cos(d) - b[0], a[1] + length * math.sin(d) - b[1])
        res.append((e, w))
    res.sort(key=lambda r: -r[0])
    return res


def verify(out_dir, coord_path, rail_info_path=None, sub_rail=None):
    """트랙별 {'wires', 'mean_cm', 'max_cm', 'worst': [...]} (상선은 rail_info 있을 때만)"""
    with open(os.path.join(out_dir, 'wires.json'), encoding='utf-8') as f:
        data = json.load(f)
    main_line = load_main_line(coord_path)
    result = {}
    for track, rows in data.items():
        if track == 'main':
            line = main_line
        elif rail_info_path and sub_rail is not None:
            line = load_rail_line(rail_info_path, sub_rail, len(main_line))
        else:
            continue  # 상선 기준 좌표 없음
        errs = wire_errors(rows, line)
        if not errs:
            result[track] = {'wires': 0, 'mean_cm': 0.0, 'max_cm': 0.0, 'worst': []}
            continue
        values = [e for e, _ in errs]
        result[track] = {
            'wires': len(values),
            'mean_cm': sum(values) / len(values) * 100,
            'max_cm': values[0] * 100,
            'worst': [{'error_cm': e * 100, 'pos': w['pos'], 'label': w['label'], 'radius': w['radius']}
                      for e, w in errs[:5]],
        }
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description='DeCATSBVE 전선 기하 검증')
    ap.add_argument('out_dir', help='tools.headless 출력 폴더 (wires.json)')
    ap.add_argument('--coord', required=True, help='bve_coordinates.txt')
    ap.add_argument('--rail-info', help='rail_info.txt (상선 검증용)')
    ap.add_argument('--sub-rail', type=int, help='상선 레일번호')
    a = ap.parse_args(argv)
    for track, r in verify(a.out_dir, a.coord, a.rail_info, a.sub_rail).items():
        print(f"[{track}] 전선 {r['wires']}개  평균 {r['mean_cm']:.2f}cm  최대 {r['max_cm']:.2f}cm")
        for w in r['worst']:
            print(f"    {w['error_cm']:8.2f}cm  pos={w['pos']} R={w['radius']} {w['label']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""GUI 없이 자동 배치 파이프라인 실행

입력 파일 → AutoRunner.run() → BVE CSV(전주/전선) + 검증용 wires.json + summary.json

사용 예:
    python -m tools.headless --config tests/regression_cases/synthetic_single/case.json --out out/single
    python -m tools.headless --info-dir c:/temp/info --structure c:/temp/info/구조물.xlsx \
        --speed 250 --end 90850 --out out/run1   (info-dir 에 bve_alignment.txt 가 있으면 그것을 사용)
    python -m tools.headless --info-dir D:/route/info --structure D:/route/구조물.xlsx \
        --speed 150 --mode double --track-distance 4.4 --sub-rail 1 --out out/double

설정 파일(case.json) 키 (경로는 case.json 이 있는 폴더 기준 상대경로 가능):
    alignment                        : BVEParser bve_alignment.txt (권장, 좌표·곡선·구배 한 파일)
    coord, curve, pitch              : alignment 가 없을 때 기존 3개 파일
    structure                        : 구조물 xlsx (필수)
    rail_info, sub_rail              : 상선을 rail_info.txt 실제 레일로 만들 때 (선택)
    idxlib                           : 인덱스 라이브러리 CSV(인덱스,파일명,경로) 또는
                                       .freeobj(N) 경로 목록 txt (선택, 없으면 이름 None)
    speed, start, end, brokenchain   : 설계속도, 시점/종점 측점, 파정
    mode                             : "single" | "double"
    main_direction                   : 본선 전주 위치 "L" | "R" (복선이면 상선은 반대)
    tunnel_direction                 : 단선 터널 전주 위치 "L" | "R" (복선은 GUI 와 같이 반전 규칙)
    track_distance                   : 복선 선로중심간격 (rail_info 미사용 시 상선 오프셋)
    custom_json, custom_spandata     : 커스텀 데이터셋 (지정 시 커스텀 모드)
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd  # noqa: E402

from bve.bvecsv import BVECSV  # noqa: E402
from core.runner import AutoRunner  # noqa: E402
from dataset.dataset_getter import DatasetGetter  # noqa: E402
from dataset.dataset_manager import load_dataset  # noqa: E402
from xref_module.index_libmgr import IndexLibrary  # noqa: E402

AIRJOINT_TYPES = ('single', 'double_pole')
DEFAULTS = {
    'speed': 150, 'start': 0.0, 'end': None, 'brokenchain': 0.0,
    'mode': 'single', 'main_direction': 'L', 'tunnel_direction': 'L',
    'track_distance': 4.3, 'sub_rail': None, 'rail_info': None, 'idxlib': None, 'alignment': None,
    'coord': None, 'curve': None, 'pitch': None,
    'custom_json': None, 'custom_spandata': None,
    'airjoint_type': 'single',   # 'single' 단주 | 'double_pole' 복주
    'double_pole_spacing': None,  # 복주 쌍 전주 간격(m), None = 데이터셋 값
}
PATH_KEYS = ('alignment', 'coord', 'curve', 'pitch', 'structure', 'rail_info', 'idxlib', 'custom_json',
             'custom_spandata')
ERROR_PATTERN = re.compile(r'에러|오류|Error|error')


def load_config(path):
    """case.json 로드, 상대경로를 case.json 폴더 기준으로 변환"""
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    for key in PATH_KEYS:
        if cfg.get(key):
            cfg[key] = os.path.normpath(os.path.join(base, cfg[key]))
    return cfg


def load_index_library(path):
    """인덱스 라이브러리: CSV(인덱스,파일명,경로) 또는 BVE '.freeobj(N) 경로' 목록"""
    if not path:
        return IndexLibrary(pd.DataFrame(columns=['인덱스', '파일명', '경로']))
    if path.lower().endswith('.csv'):
        return IndexLibrary(pd.read_csv(path))
    rows = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = re.match(r'\s*\.freeobj\((\d+)\)\s*(.+?)\s*$', line, re.I)
            if m:
                obj_path = m.group(2)
                name = os.path.splitext(os.path.basename(obj_path.replace('\\', '/')))[0]
                rows.append({'인덱스': int(m.group(1)), '파일명': name, '경로': obj_path})
    return IndexLibrary(pd.DataFrame(rows, columns=['인덱스', '파일명', '경로']))


def last_station(path):
    """선형 파일(bve_alignment.txt 또는 curve_info.txt)의 마지막 측점 (종점 미지정 시 사용)"""
    last = None
    with open(path, encoding='utf-8-sig') as f:
        for line in f:
            head = line.split(',')[0].strip()
            try:
                last = float(head)
            except ValueError:
                continue  # 머리글
    return last


def build_runner(cfg):
    """설정으로 AutoRunner 구성 (GUI maingui.update_inputs / _apply_track_settings 와 같은 규칙)"""
    cfg = {**DEFAULTS, **cfg}
    r = AutoRunner()
    r.alignment_file_path = cfg['alignment']
    r.coord_file_path = cfg['coord']
    r.curve_file_path = cfg['curve']
    r.pitch_file_path = cfg['pitch']
    r.structure_file_path = cfg['structure']
    r.designspeed = int(cfg['speed'])
    r.track_mode = cfg['mode']
    r.start_station = float(cfg['start'])
    r.end_station = float(cfg['end'] if cfg['end'] is not None else last_station(cfg['alignment'] or cfg['curve']))
    r.brokenchain = float(cfg['brokenchain'])
    r.idxlib = load_index_library(cfg['idxlib'])
    if cfg['airjoint_type'] not in AIRJOINT_TYPES:
        raise ValueError(f"airjoint_type 은 {'/'.join(AIRJOINT_TYPES)} 중 하나: {cfg['airjoint_type']}")
    r.airjoint_type = cfg['airjoint_type']
    if cfg['double_pole_spacing'] is not None:
        r.double_pole_spacing = float(cfg['double_pole_spacing'])

    custom = bool(cfg['custom_json'])
    r.iscustommode = int(custom)
    r.dataprocessor = DatasetGetter(load_dataset(r.designspeed, custom, cfg['custom_json'], cfg['custom_spandata']))

    main_side = -1 if cfg['main_direction'] == 'L' else 1
    if r.track_mode == 'single':
        r.track_direction['main'] = main_side
        r.track_distance = 0.0
        r.tunnel_direction['main'] = -1 if cfg['tunnel_direction'] == 'L' else 1
    elif r.track_mode == 'double':
        r.track_direction.update(main=main_side, sub=-main_side)
        r.track_distance = float(cfg['track_distance'])
        r.tunnel_direction.update(main=-main_side, sub=main_side)  # 복선 터널은 방향 반전
        if cfg['sub_rail'] is not None:
            r.sub_rail_key = int(cfg['sub_rail'])
            info_dir = os.path.dirname(cfg['alignment'] or cfg['coord'])
            r.rail_info_file_path = cfg['rail_info'] or os.path.join(info_dir, 'rail_info.txt')
    else:
        raise ValueError(f"mode 는 single 또는 double: {r.track_mode}")
    return r


def write_outputs(runner, out_dir, log_text):
    """BVE CSV, wires.json, summary.json 저장"""
    os.makedirs(out_dir, exist_ok=True)
    summary = {'tracks': {}, 'errors': [l for l in log_text.splitlines() if ERROR_PATTERN.search(l)]}
    wires_dump = {}
    for track, idx in (('main', 0), ('sub', 1)):
        if track not in runner.poledata:
            continue
        poles, wires = runner.poledata[track], runner.wire_data[track]
        csv = BVECSV(poles, wires, track_index=idx)
        with contextlib.redirect_stdout(io.StringIO()):
            pole_lines, wire_lines = csv.create_pole_csv(), csv.create_wire_csv()
        with open(os.path.join(out_dir, f'{track}_pole.txt'), 'w', encoding='utf-8') as f:
            f.writelines(pole_lines)
        with open(os.path.join(out_dir, f'{track}_wire.txt'), 'w', encoding='utf-8') as f:
            f.writelines(wire_lines)

        by_pos = {p.pos: p for p in poles}
        rows = []
        for wire in wires:
            pole = by_pos[wire.pos]
            for w in wire.wires:
                rows.append(dict(pos=pole.pos, next_pos=pole.next_pos, span=pole.span, label=w.label,
                                 start=list(w.offset), end=list(w.end_point), yaw=w.adjusted_angle,
                                 pitch=w.topdown_angle, radius=pole.radius, station=w.station))
        wires_dump[track] = rows
        summary['tracks'][track] = {'poles': len(poles), 'spans': len(wires),
                                    'first_pole': poles[0].pos if poles else None,
                                    'last_pole': poles[-1].pos if poles else None}
    with open(os.path.join(out_dir, 'wires.json'), 'w', encoding='utf-8') as f:
        json.dump(wires_dump, f, ensure_ascii=False)
    with open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def run(cfg, out_dir, quiet=True):
    """설정으로 실행하고 out_dir 에 결과 저장. summary dict 반환"""
    runner = build_runner(cfg)
    buf = io.StringIO()
    t = time.time()
    with contextlib.redirect_stdout(buf) if quiet else contextlib.nullcontext():
        runner.run()
    summary = write_outputs(runner, out_dir, buf.getvalue())
    summary['elapsed_sec'] = round(time.time() - t, 2)
    with open(os.path.join(out_dir, 'run.log'), 'w', encoding='utf-8') as f:
        f.write(buf.getvalue())
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description='DeCATSBVE 헤드리스 실행')
    ap.add_argument('--config', help='case.json (다른 인자보다 먼저 적용, 인자로 덮어쓰기 가능)')
    ap.add_argument('--info-dir', help='BVEParser 출력 폴더 (bve_alignment.txt 우선, 없으면 '
                                       'bve_coordinates/curve_info/pitch_info.txt, 복선은 rail_info.txt)')
    ap.add_argument('--alignment', help='bve_alignment.txt 경로')
    ap.add_argument('--structure', help='구조물 xlsx (교량/터널 시트)')
    ap.add_argument('--idxlib', help='인덱스 라이브러리 CSV 또는 .freeobj 목록 txt')
    ap.add_argument('--speed', type=int)
    ap.add_argument('--start', type=float)
    ap.add_argument('--end', type=float)
    ap.add_argument('--brokenchain', type=float)
    ap.add_argument('--mode', choices=['single', 'double'])
    ap.add_argument('--main-direction', choices=['L', 'R'])
    ap.add_argument('--tunnel-direction', choices=['L', 'R'])
    ap.add_argument('--track-distance', type=float)
    ap.add_argument('--sub-rail', type=int, help='상선 레일번호 (rail_info.txt 사용)')
    ap.add_argument('--rail-info', help='rail_info.txt 경로 (기본: info-dir/rail_info.txt)')
    ap.add_argument('--custom-json')
    ap.add_argument('--custom-spandata')
    ap.add_argument('--out', required=True, help='출력 폴더')
    ap.add_argument('--verbose', action='store_true', help='처리 로그를 화면에도 출력')
    a = ap.parse_args(argv)

    cfg = load_config(a.config) if a.config else {}
    if a.info_dir:
        alignment = os.path.join(a.info_dir, 'bve_alignment.txt')
        if os.path.isfile(alignment):
            cfg['alignment'] = alignment
        else:
            cfg.update(coord=os.path.join(a.info_dir, 'bve_coordinates.txt'),
                       curve=os.path.join(a.info_dir, 'curve_info.txt'),
                       pitch=os.path.join(a.info_dir, 'pitch_info.txt'))
    for key in ('alignment', 'structure', 'idxlib', 'speed', 'start', 'end', 'brokenchain', 'mode', 'main_direction',
                'tunnel_direction', 'track_distance', 'sub_rail', 'rail_info', 'custom_json', 'custom_spandata'):
        value = getattr(a, key)
        if value is not None:
            cfg[key] = value
    needed = ('structure',) if cfg.get('alignment') else ('coord', 'curve', 'pitch', 'structure')
    missing = [k for k in needed if not cfg.get(k)]
    if missing:
        ap.error(f"입력 파일 지정 필요: {missing} (--config 또는 --info-dir/--alignment/--structure)")

    summary = run(cfg, a.out, quiet=not a.verbose)
    for track, s in summary['tracks'].items():
        print(f"[{track}] 전주 {s['poles']}개, 경간 {s['spans']}개 ({s['first_pole']} ~ {s['last_pole']})")
    print(f"처리 오류 {len(summary['errors'])}건, {summary['elapsed_sec']}초 → {a.out}")
    for line in summary['errors'][:10]:
        print('  ', line)
    return 0


if __name__ == '__main__':
    sys.exit(main())

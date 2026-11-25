"""전선 상세 편집 내용을 경간(Span) 단위로 보관하고 재계산 후 다시 적용

경간 = 연속한 두 전주. 키는 (트랙, 앞 전주 uid, 뒤 전주 uid) 로, 전주가 이동해도 유지된다
(PoleDATA.uid). 전선 상세 편집기는 전선 지지점(시작점·끝점의 x 이격거리, 높이)을 고치므로,
지지점만 보관하고 각도(평면·종단)는 적용할 때 현재 선형·전주 위치로 다시 계산한다.
그래서 전주를 옮겨도 편집한 지지점은 유지되고 각도는 새 위치에 맞게 바뀐다.

runner.wire_overrides = {
    ("main", 앞 uid, 뒤 uid): {"전차선#0": {"offset": [x, y], "end_point": [x, y]}, ...},
}
전선 키 = "라벨#같은 라벨 안에서의 순번" (한 경간에 같은 라벨 전선이 여러 개일 수 있음)

경간이 없어지면(앞뒤 전주 사이에 전주 추가, 전주 삭제 등) 그 편집은 적용되지 않는다.
전주 자체가 삭제된 경간의 편집은 정리(prune)된다.
"""
from core.wire.common_processor import CommonWireProcessor
from utils.math_util import change_permile_to_degree


def wire_keys(wires):
    """[(전선키, SingleWire), ...]"""
    seen = {}
    out = []
    for w in wires:
        k = seen.get(w.label, 0)
        seen[w.label] = k + 1
        out.append((f"{w.label}#{k}", w))
    return out


def span_key(track, pole, next_pole):
    return (track, pole.uid, next_pole.uid)


def spans_by_pos(poles):
    """{앞 전주 pos: (앞 전주, 뒤 전주)} — 실제로 이어진(next_pos 가 다음 전주) 경간만"""
    out = {}
    for pole, nxt in zip(poles, poles[1:]):
        if pole.next_pos == nxt.pos:
            out[pole.pos] = (pole, nxt)
    return out


def snapshot(runner, track, positions):
    """지정 경간들(앞 전주 pos)의 현재 전선 지지점 {span_key: {전선키: (offset, end_point)}}"""
    spans = spans_by_pos(runner.poledata[track])
    wires_by_pos = {w.pos: w for w in runner.wire_data[track]}
    out = {}
    for pos in positions:
        if pos not in spans or pos not in wires_by_pos:
            continue
        key = span_key(track, *spans[pos])
        out[key] = {wk: (tuple(w.offset), tuple(w.end_point)) for wk, w in wire_keys(wires_by_pos[pos].wires)}
    return out


def record_changes(runner, track, before):
    """편집 전 snapshot 과 비교해 바뀐 전선 지지점을 overrides 에 기록. 기록한 전선 수 반환"""
    overrides = _overrides(runner)
    positions = {}
    spans = spans_by_pos(runner.poledata[track])
    for pos, (pole, nxt) in spans.items():
        positions[span_key(track, pole, nxt)] = pos
    after = snapshot(runner, track, [positions[k] for k in before if k in positions])
    n = 0
    for key, wires in after.items():
        old = before.get(key, {})
        for wk, (offset, end_point) in wires.items():
            if old.get(wk) != (offset, end_point):
                overrides.setdefault(key, {})[wk] = {'offset': list(offset), 'end_point': list(end_point)}
                n += 1
    return n


def apply(runner, alignment_for):
    """재생성된 wire_data 에 편집 내용 적용 + 각도 재계산. (적용 전선 수, 정리한 경간 수)"""
    overrides = _overrides(runner)
    if not overrides:
        return 0, 0
    processor = CommonWireProcessor()
    applied = 0
    live_uids = {t: {p.uid for p in poles} for t, poles in runner.poledata.items()}
    for track, wires in runner.wire_data.items():
        spans = spans_by_pos(runner.poledata[track])
        alignment = alignment_for(runner, track)
        for wire in wires:
            if wire.pos not in spans:
                continue
            pole, nxt = spans[wire.pos]
            edits = overrides.get(span_key(track, pole, nxt))
            if not edits:
                continue
            pitch_angle = change_permile_to_degree(pole.pitch)
            for wk, w in wire_keys(wire.wires):
                edit = edits.get(wk)
                if edit is None:
                    continue
                w.offset = tuple(edit['offset'])
                w.end_point = tuple(edit['end_point'])
                new = processor.run(alignment, w.index, pole.pos, nxt.pos, pole.z, nxt.z,
                                    start=w.offset, end=w.end_point, pitch_angle=pitch_angle, label=w.label)
                w.adjusted_angle, w.topdown_angle = new.adjusted_angle, new.topdown_angle
                applied += 1
    # 삭제된 전주가 낀 경간의 편집 정리
    stale = [k for k in overrides if k[0] not in live_uids or k[1] not in live_uids[k[0]] or k[2] not in live_uids[k[0]]]
    for k in stale:
        del overrides[k]
    return applied, len(stale)


def clear(runner, track, positions):
    """지정 경간들(앞 전주 pos)의 편집 내용 삭제 (자동 계산값으로 되돌림). 삭제한 경간 수"""
    overrides = _overrides(runner)
    spans = spans_by_pos(runner.poledata[track])
    n = 0
    for pos in positions:
        if pos in spans and overrides.pop(span_key(track, *spans[pos]), None) is not None:
            n += 1
    return n


def _overrides(runner):
    if getattr(runner, 'wire_overrides', None) is None:
        runner.wire_overrides = {}
    return runner.wire_overrides

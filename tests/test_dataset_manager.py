"""데이터셋 로더 테스트: python -m pytest tests"""
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dataset.dataset_getter import DatasetGetter  # noqa: E402
from dataset.dataset_manager import get_config_dir, load_dataset  # noqa: E402


def test_config_dir_is_source_config():
    assert os.path.normcase(get_config_dir()) == os.path.normcase(os.path.join(ROOT, 'config'))


@pytest.mark.parametrize("speed", [150, 250, 350])
def test_standard_dataset_loads_from_config(speed):
    ds = load_dataset(speed, False)
    assert ds['design']['speed'] == speed
    assert os.path.dirname(ds['_source']['json']) == get_config_dir()
    g = DatasetGetter(ds)
    # 현재 코드가 요구하는 형식인지 (이전 형식 config 회귀 방지)
    for structure in ('토공', '교량', '터널'):
        g.get_bracket_codes('일반개소', structure, 'I')
        g.get_bracket_codes('일반개소', structure, 'O')
        g.get_pole_gauge(structure)
    assert ds['span_data']['토공전차선']


def test_unsupported_speed():
    with pytest.raises(ValueError):
        load_dataset(200, False)


def test_custom_mode_requires_paths():
    with pytest.raises(ValueError):
        load_dataset(150, True)


def test_custom_mode_uses_given_paths(tmp_path):
    j = tmp_path / 'my.json'
    x = tmp_path / 'my_span.xlsx'
    shutil.copy(os.path.join(ROOT, 'config', 'railway_250.JSON'), j)
    shutil.copy(os.path.join(ROOT, 'config', 'spandata_250.xlsx'), x)
    ds = load_dataset(150, True, str(j), str(x))  # 커스텀이면 설계속도 무시
    assert ds['design']['speed'] == 250
    assert ds['_source']['json'] == str(j)


def test_custom_mode_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dataset(150, True, str(tmp_path / 'none.json'), str(tmp_path / 'none.xlsx'))

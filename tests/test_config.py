from __future__ import annotations

from pathlib import Path

from localbooru.cli import build_parser
from localbooru.config import (
    LocalBooruConfig,
    load_config_file,
    render_default_config_template,
)


def _make_args(arg_list: list[str] | None = None):
    parser = build_parser()
    return parser.parse_args(arg_list or [])


def test_config_defaults_without_file(monkeypatch, tmp_path):
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    args = _make_args()
    config = LocalBooruConfig.from_sources(args)

    assert config.root == Path(".").resolve()
    assert config.roots == [config.root]
    assert config.db_path == Path("gallery.db").resolve()
    expected_cache = (cache_root / "localbooru" / "thumbs").resolve()
    assert config.thumb_cache == expected_cache
    assert config.extra_roots == []
    assert config.watch is False
    assert config.config_file is None


def test_config_file_relative_roots(monkeypatch, tmp_path):
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config_path = config_dir / "localbooru.toml"
    config_path.write_text(
        'roots = ["images", "more"]\nwatch = true\n', encoding="utf-8"
    )

    args = _make_args()
    data = load_config_file(config_path)
    config = LocalBooruConfig.from_sources(
        args, file_options=data, config_path=config_path
    )

    assert config.config_file == config_path.resolve()
    assert config.root == (config_dir / "images").resolve()
    assert (config_dir / "more").resolve() in config.extra_roots
    assert config.watch is True
    expected_db = (state_root / "localbooru" / "gallery.db").resolve()
    assert config.db_path == expected_db


def test_cli_overrides_config(monkeypatch, tmp_path):
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    cfg_root_one = config_dir / "rootA"
    cfg_root_two = config_dir / "rootB"
    cfg_extra = config_dir / "rootC"
    config_data = {
        "roots": [str(cfg_root_one), str(cfg_root_two)],
        "extra_roots": [str(cfg_extra)],
        "watch": True,
    }

    cli_root = tmp_path / "cli-root"
    cli_extra = tmp_path / "cli-extra"
    cli_db = tmp_path / "cli.db"
    args = _make_args(
        [
            "--root",
            str(cli_root),
            "--db",
            str(cli_db),
            "--extra-root",
            str(cli_extra),
        ]
    )

    config = LocalBooruConfig.from_sources(
        args, file_options=config_data, config_path=config_dir / "config.toml"
    )

    assert config.root == cli_root.resolve()
    expected_extras = {
        cfg_root_one.resolve(),
        cfg_root_two.resolve(),
        cfg_extra.resolve(),
        cli_extra.resolve(),
    }
    assert set(config.extra_roots) == expected_extras
    assert config.db_path == cli_db.resolve()
    # watch comes from config even without CLI flag
    assert config.watch is True


def test_default_config_path_pickup(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    default_config = home / ".localbooru.toml"
    default_config.write_text('root = "library"\nwatch = true\n', encoding="utf-8")

    args = _make_args()
    data = load_config_file(default_config)
    config = LocalBooruConfig.from_sources(
        args, file_options=data, config_path=default_config
    )

    assert config.config_file == default_config.resolve()
    assert config.root == (default_config.parent / "library").resolve()
    assert config.watch is True


def test_cwd_flag_restores_legacy_defaults(monkeypatch, tmp_path):
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    args = _make_args(["--cwd"])
    config = LocalBooruConfig.from_sources(args)

    assert config.db_path == Path("gallery.db").resolve()
    assert config.config_file is None


def test_render_default_config_template(monkeypatch, tmp_path):
    cache_root = tmp_path / "cache"
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_root))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    template = render_default_config_template()

    expected_db = (state_root / "localbooru" / "gallery.db").resolve()
    expected_cache = (cache_root / "localbooru" / "thumbs").resolve()

    assert f'db_path = "{expected_db}"' in template
    assert f'thumb_cache = "{expected_cache}"' in template
    assert 'clip_device = "cpu"' in template
    assert "auto_tag_mode = \"augment\"" in template

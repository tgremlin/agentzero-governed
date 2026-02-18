from pathlib import Path

from tools.doctor import parse_compose_ps_json, parse_env_file, resolve_data_dir


def test_parse_env_file_reads_pairs(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "A0_DATA_DIR=./client-data\n# comment\nALLOWED_ORIGINS=http://localhost:50001\n",
        encoding="utf-8",
    )
    parsed = parse_env_file(env)
    assert parsed["A0_DATA_DIR"] == "./client-data"
    assert parsed["ALLOWED_ORIGINS"] == "http://localhost:50001"


def test_resolve_data_dir_uses_repo_relative():
    root = Path("/tmp/repo")
    out = resolve_data_dir(root, {"A0_DATA_DIR": "./client-data"})
    assert str(out).endswith("/tmp/repo/client-data")


def test_parse_compose_ps_json_supports_array_and_lines():
    arr = '[{"Service":"app","State":"running"},{"Service":"postgres","State":"running"}]'
    parsed_arr = parse_compose_ps_json(arr)
    assert parsed_arr["app"] == "running"
    assert parsed_arr["postgres"] == "running"

    lines = '{"Service":"app","State":"running"}\n{"Service":"temporal","State":"running"}\n'
    parsed_lines = parse_compose_ps_json(lines)
    assert parsed_lines["app"] == "running"
    assert parsed_lines["temporal"] == "running"

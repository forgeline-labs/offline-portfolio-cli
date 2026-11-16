"""Black-box CLI tests for offline-portfolio-cli, traceable to the spec ACs.

Every test drives the program through its documented entrypoint with
``subprocess`` and ``sys.executable``; no private module is imported.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
APP_CMD = ROOT / "app.cmd"
MAX_FILE_BYTES = 1024 * 1024

EXAMPLE = {
    "profile": {"name": "Demo", "bio": "Local"},
    "projects": [
        {"slug": "demo", "title": "Demo", "description": "Exemplo"},
    ],
    "skills": ["Python"],
}


def run(*args, cwd=None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(APP), *args],
        capture_output=True,
        timeout=60,
        cwd=cwd,
        env=env,
    )


def write(tmp_path, data, name="portfolio.json"):
    path = tmp_path / name
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        text = data if isinstance(data, str) else json.dumps(data)
        path.write_bytes(text.encode("utf-8"))
    return path


def assert_error(result, code):
    assert result.returncode == code, result
    assert result.stdout == b""
    assert result.stderr.startswith(b"error:")
    text = result.stderr.decode("utf-8")
    assert text.endswith("\n")
    assert text.count("\n") == 1
    assert "Traceback" not in text


def parse_stdout(result):
    assert result.returncode == 0, result
    assert result.stderr == b""
    assert result.stdout.endswith(b"\n")
    assert b"\r" not in result.stdout
    assert result.stdout.count(b"\n") == 1
    return json.loads(result.stdout.decode("utf-8"))


def sample_with(projects=None, skills=None):
    return {
        "profile": {"name": "Demo", "bio": "Local"},
        "projects": projects if projects is not None else list(EXAMPLE["projects"]),
        "skills": skills if skills is not None else list(EXAMPLE["skills"]),
    }


# AC-1: show returns the example object with sorted arrays.
def test_ac1_show_full_object_sorted(tmp_path):
    data = {
        "profile": {"name": "Demo", "bio": "Local"},
        "projects": [
            {"slug": "zulu", "title": "Zulu", "description": "Third"},
            {"slug": "alpha", "title": "Alpha", "description": "First"},
        ],
        "skills": ["Rust", "Python", "Ada"],
    }
    result = run("show", str(write(tmp_path, data)))
    output = parse_stdout(result)
    assert output["profile"] == {"name": "Demo", "bio": "Local"}
    assert [p["slug"] for p in output["projects"]] == ["alpha", "zulu"]
    assert output["skills"] == ["Ada", "Python", "Rust"]
    assert set(output) == {"profile", "projects", "skills"}


def test_ac1_show_example_object(tmp_path):
    result = run("show", str(write(tmp_path, EXAMPLE)))
    assert parse_stdout(result) == {
        "profile": {"name": "Demo", "bio": "Local"},
        "projects": [
            {"slug": "demo", "title": "Demo", "description": "Exemplo"},
        ],
        "skills": ["Python"],
    }


# AC-2: every --section returns only its object/array, with no wrapper.
@pytest.mark.parametrize(
    "section, expected",
    [
        ("profile", EXAMPLE["profile"]),
        ("projects", EXAMPLE["projects"]),
        ("skills", EXAMPLE["skills"]),
    ],
)
def test_ac2_sections(tmp_path, section, expected):
    result = run("show", str(write(tmp_path, EXAMPLE)), "--section", section)
    assert parse_stdout(result) == expected


# AC-3: find matches title and description, ignoring case; absent gives [].
def test_ac3_find_title_case_insensitive(tmp_path):
    data = sample_with(
        projects=[
            {"slug": "one", "title": "Rust Weaver", "description": "nothing"},
            {"slug": "two", "title": "other", "description": "nothing"},
        ]
    )
    result = run("find", str(write(tmp_path, data)), "RUST")
    assert parse_stdout(result) == [
        {"slug": "one", "title": "Rust Weaver", "description": "nothing"}
    ]


def test_ac3_find_description_case_insensitive(tmp_path):
    data = sample_with(
        projects=[
            {"slug": "demo", "title": "Demo", "description": "Exemplo"},
        ]
    )
    assert parse_stdout(run("find", str(write(tmp_path, data)), "exemplo")) == [
        {"slug": "demo", "title": "Demo", "description": "Exemplo"}
    ]


def test_ac3_find_absent_returns_empty_array(tmp_path):
    data = sample_with()
    result = run("find", str(write(tmp_path, data)), "missing-query")
    assert result.returncode == 0
    assert result.stdout == b"[]\n"
    assert result.stderr == b""


# AC-4: casefold maps STRASSE to the Straße title.
def test_ac4_casefold_strasse(tmp_path):
    project = {"slug": "strasse", "title": "Straße", "description": ""}
    data = sample_with(projects=[project])
    assert parse_stdout(run("find", str(write(tmp_path, data)), "STRASSE")) == [project]


# AC-5: the slug is not searched.
def test_ac5_slug_not_searched(tmp_path):
    project = {"slug": "needle", "title": "Title", "description": "Text"}
    data = sample_with(projects=[project])
    result = run("find", str(write(tmp_path, data)), "needle")
    assert result.returncode == 0
    assert result.stdout == b"[]\n"


# AC-6: duplicate slug, extra key or wrong type is rejected.
def test_ac6_duplicate_slug(tmp_path):
    projects = [
        {"slug": "dup", "title": "A", "description": ""},
        {"slug": "dup", "title": "B", "description": ""},
    ]
    assert_error(run("show", str(write(tmp_path, sample_with(projects=projects)))), 2)


def test_ac6_extra_key(tmp_path):
    data = sample_with()
    data["extra"] = 1
    assert_error(run("show", str(write(tmp_path, data))), 2)


def test_ac6_extra_key_in_project(tmp_path):
    projects = [
        {"slug": "ok", "title": "A", "description": "", "url": "https://x.test"}
    ]
    assert_error(run("show", str(write(tmp_path, sample_with(projects=projects)))), 2)


def test_ac6_wrong_type(tmp_path):
    data = sample_with()
    data["profile"]["name"] = 42
    assert_error(run("show", str(write(tmp_path, data))), 2)


def test_ac6_boolean_is_not_a_string(tmp_path):
    data = sample_with()
    data["profile"]["name"] = True
    assert_error(run("show", str(write(tmp_path, data))), 2)


# AC-7: control characters (ESC included) are rejected without being echoed.
def test_ac7_escape_in_field(tmp_path):
    data = sample_with()
    data["profile"]["bio"] = "before\x1bafter"
    result = run("show", str(write(tmp_path, data)))
    assert_error(result, 2)
    assert b"before" not in result.stderr
    assert b"after" not in result.stderr


# AC-8: Unicode paths with spaces work and the input file is untouched.
def test_ac8_unicode_path_with_spaces(tmp_path):
    directory = tmp_path / "dados ção 日本"
    directory.mkdir()
    path = write(directory, EXAMPLE, name="meu portfólio.json")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = run("show", str(path))
    assert parse_stdout(result)["profile"]["name"] == "Demo"
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after


def test_ac8_unicode_content_round_trips(tmp_path):
    data = {
        "profile": {"name": "Zoë 日本", "bio": "Linha 1 — é permitido"},
        "projects": [],
        "skills": ["Café"],
    }
    output = parse_stdout(run("show", str(write(tmp_path, data))))
    assert output["profile"] == data["profile"]
    assert output["skills"] == ["Café"]


# AC-9: empty arrays are valid; an empty query is invalid.
def test_ac9_empty_arrays_valid(tmp_path):
    data = sample_with(projects=[], skills=[])
    result = run("show", str(write(tmp_path, data)))
    assert parse_stdout(result) == {
        "profile": {"name": "Demo", "bio": "Local"},
        "projects": [],
        "skills": [],
    }


def test_ac9_empty_query_invalid(tmp_path):
    assert_error(run("find", str(write(tmp_path, EXAMPLE)), ""), 2)


# AC-10: whole-file validation precedes --section filtering.
def test_ac10_invalid_project_fails_for_profile_section(tmp_path):
    projects = [{"slug": "Bad Slug", "title": "A", "description": ""}]
    data = sample_with(projects=projects)
    assert_error(run("show", str(write(tmp_path, data)), "--section", "profile"), 2)


# AC-11: missing file is an I/O error; oversized file is a validation error.
def test_ac11_missing_file(tmp_path):
    assert_error(run("show", str(tmp_path / "absent.json")), 3)


def test_ac11_file_one_byte_over_limit(tmp_path):
    base = json.dumps(sample_with()).encode("utf-8")
    assert len(base) < MAX_FILE_BYTES
    raw = base + b" " * (MAX_FILE_BYTES + 1 - len(base))
    assert len(raw) == MAX_FILE_BYTES + 1
    assert_error(run("show", str(write(tmp_path, raw))), 2)


def test_ac11_exactly_one_mib_accepted(tmp_path):
    base = json.dumps(sample_with()).encode("utf-8")
    raw = base + b" " * (MAX_FILE_BYTES - len(base))
    assert len(raw) == MAX_FILE_BYTES
    result = run("show", str(write(tmp_path, raw)))
    assert parse_stdout(result)["profile"]["name"] == "Demo"


# AC-12: --version and --help are independent of FILE and storage.
def test_ac12_version(tmp_path):
    result = run("--version", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == b"offline-portfolio-cli 0.1.0\n"
    assert result.stderr == b""


def test_ac12_help(tmp_path):
    result = run("--help", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stderr == b""
    text = result.stdout.decode("utf-8")
    for token in ("usage:", "app", "show", "find", "--section", "--help", "--version"):
        assert token in text
    assert list(tmp_path.iterdir()) == []


# Ambiguity resolutions: parser and encoding edge cases.
def test_ambiguous_bom_rejected(tmp_path):
    raw = b"\xef\xbb\xbf" + json.dumps(sample_with()).encode("utf-8")
    assert_error(run("show", str(write(tmp_path, raw))), 2)


def test_ambiguous_invalid_utf8_rejected(tmp_path):
    raw = json.dumps(sample_with()).encode("utf-8") + b"\xff"
    assert_error(run("show", str(write(tmp_path, raw))), 2)


def test_ambiguous_nan_rejected(tmp_path):
    raw = b'{"profile":{"name":"Demo","bio":"Local"},"projects":[],"skills":[NaN]}'
    assert_error(run("show", str(write(tmp_path, raw))), 2)


def test_ambiguous_duplicate_json_keys_rejected(tmp_path):
    raw = b'{"profile":{"name":"A","name":"B","bio":""},"projects":[],"skills":[]}'
    assert_error(run("show", str(write(tmp_path, raw))), 2)


def test_ambiguous_extra_positional_rejected(tmp_path):
    assert_error(run("show", str(write(tmp_path, EXAMPLE)), "extra"), 2)


def test_ambiguous_section_without_value_rejected(tmp_path):
    assert_error(run("show", str(write(tmp_path, EXAMPLE)), "--section"), 2)


def test_ambiguous_unknown_argument_rejected():
    assert_error(run("--bogus"), 2)


def test_ambiguous_missing_file_argument():
    assert_error(run("show"), 2)


def test_ambiguous_missing_query_argument(tmp_path):
    assert_error(run("find", str(write(tmp_path, EXAMPLE))), 2)


def test_ambiguous_control_in_query_rejected(tmp_path):
    assert_error(run("find", str(write(tmp_path, EXAMPLE)), "a\x1bb"), 2)


def test_ambiguous_nbsp_and_unicode_spaces_accepted(tmp_path):
    data = sample_with()
    data["profile"]["bio"] = "a b c"
    output = parse_stdout(run("show", str(write(tmp_path, data))))
    assert output["profile"]["bio"] == "a b c"


def test_ambiguous_nfc_nfd_skill_uniqueness(tmp_path):
    composed = "café"
    decomposed = "café"
    data = sample_with(skills=[composed, decomposed])
    output = parse_stdout(run("show", str(write(tmp_path, data))))
    assert len(output["skills"]) == 2


def test_ambiguous_duplicate_skill_rejected(tmp_path):
    data = sample_with(skills=["Python", "Python"])
    assert_error(run("show", str(write(tmp_path, data))), 2)


# POSIX delivery contract: ./app is equivalent to python app.
@pytest.mark.skipif(os.name == "nt", reason="executable bit is POSIX only")
def test_posix_executable_entrypoint(tmp_path):
    result = subprocess.run(
        [str(APP), "show", str(write(tmp_path, EXAMPLE))],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert json.loads(result.stdout.decode("utf-8"))["profile"]["name"] == "Demo"


# Windows delivery contract: app.cmd propagates arguments and the exit code.
@pytest.mark.skipif(os.name != "nt", reason="app.cmd is a Windows launcher")
def test_windows_launcher_propagates_exit_code(tmp_path):
    path = write(
        tmp_path, {"profile": {"name": "Demo", "bio": ""}, "projects": [], "skills": []}
    )
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    ok = subprocess.run(
        [comspec, "/c", str(APP_CMD), "show", str(path)],
        capture_output=True,
        timeout=60,
    )
    assert ok.returncode == 0
    assert json.loads(ok.stdout.decode("utf-8"))["profile"]["name"] == "Demo"
    bad = subprocess.run(
        [comspec, "/c", str(APP_CMD), "show", str(tmp_path / "absent.json")],
        capture_output=True,
        timeout=60,
    )
    assert bad.returncode == 3

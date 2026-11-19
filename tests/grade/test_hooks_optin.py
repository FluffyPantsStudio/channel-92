"""A film folder's grade hooks are programs; they run only when the person asks with --hooks, and say what runs."""

from __future__ import annotations

from atomic_flix.cli import grade_steps
from atomic_flix.grade.hooks import run_hooks


def _hooks(tmp_path):
    folder = tmp_path / "hooks" / "tone.d"
    folder.mkdir(parents=True)
    marker = tmp_path / "ran.txt"
    (folder / "10-note.py").write_text(f"import pathlib\npathlib.Path(r'{marker}').write_text('ran')\n",
                                       encoding="utf-8")
    return folder, marker


def test_hooks_are_off_unless_asked(tmp_path):
    folder, marker = _hooks(tmp_path)
    said: list[str] = []
    problems = grade_steps.film_hooks(folder, tmp_path / "toned.mp4", tmp_path / "toned.tone.json", enabled=False,
                                      say=said.append)
    assert problems == []
    assert not marker.exists()
    assert any("--hooks" in line and "10-note.py" in line for line in said), said


def test_with_hooks_each_one_is_named_before_it_runs(tmp_path):
    folder, marker = _hooks(tmp_path)
    said: list[str] = []
    problems = grade_steps.film_hooks(folder, tmp_path / "toned.mp4", tmp_path / "toned.tone.json", enabled=True,
                                      say=said.append)
    assert problems == []
    assert marker.exists()
    assert any("10-note.py" in line for line in said)


def test_run_hooks_announces_each_command(tmp_path):
    folder, marker = _hooks(tmp_path)
    said: list[str] = []
    run_hooks(folder, tmp_path / "toned.mp4", tmp_path / "toned.tone.json", announce=said.append)
    assert len(said) == 1 and "10-note.py" in said[0]


def test_the_grade_step_has_a_hooks_flag_that_defaults_off():
    args = grade_steps.grade_parser().parse_args(["some-film"])
    assert args.hooks is False
    assert grade_steps.grade_parser().parse_args(["some-film", "--hooks"]).hooks is True
    assert "--hooks" in grade_steps.grade_parser().format_help()

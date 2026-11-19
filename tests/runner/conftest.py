"""Fixtures for the runner's tests: fake ComfyUI hosts and a tiny film project."""

from __future__ import annotations

from pathlib import Path

import pytest

from fake_comfyui import FakeComfy
from runner_samples import SILENT_GRAPH, SUNG_GRAPH, write_graph


@pytest.fixture
def fake_hosts():
    started: list[FakeComfy] = []

    def make(count: int = 1, **kwargs) -> list[FakeComfy]:
        fakes = [FakeComfy(gpu_name=f"Fake GPU {i}", **kwargs).start() for i in range(count)]
        started.extend(fakes)
        return fakes

    yield make
    for fake in started:
        fake.close()
    for fake in started:
        assert fake.forbidden == [], f"the runner called a forbidden route: {fake.forbidden}"


@pytest.fixture
def film_dir(tmp_path: Path) -> Path:
    root = tmp_path / "girl-in-the-tub"
    (root / "stills").mkdir(parents=True)
    (root / "plan").mkdir()
    for key in ("S01", "S02", "S03", "S04", "S05"):
        (root / "stills" / f"{key}.png").write_bytes(b"\x89PNG fake " + key.encode())
        (root / "plan" / f"{key}.voice-soft.wav").write_bytes(b"RIFF fake " + key.encode())
    return root


@pytest.fixture
def sung_graph(film_dir: Path) -> Path:
    return write_graph(film_dir / "graphs", "sung-pinned.json", SUNG_GRAPH,
                       {"needs": ["wording", "opening_still", "audio"], "frame_multiple": 8, "commit_gb": 40})


@pytest.fixture
def silent_graph(film_dir: Path) -> Path:
    return write_graph(film_dir / "graphs", "plate.json", SILENT_GRAPH, {"frame_multiple": 8, "commit_gb": 40})


@pytest.fixture
def cleared(monkeypatch):
    """The runner's `shoot` on a bare project folder: the film checks (gate 5, its batch, lint) are passed, since
    these tests are about the runner's own work; tests/cli/test_cli_shoot_gates.py covers the checks themselves."""
    monkeypatch.setattr("atomic_flix.runner.__main__.clear_to_shoot", lambda film, keys=None: None)
    monkeypatch.setattr("atomic_flix.runner.__main__.Film.open", classmethod(lambda cls, root: root))

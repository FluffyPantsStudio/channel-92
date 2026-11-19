"""Graph templates: placeholders, filling, sidecars and the refusals made before anything is queued."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomic_flix.runner.template import (
    GraphMeta,
    TemplateError,
    check_request,
    check_size,
    fill,
    frames_for,
    load_graph,
    load_meta,
    placeholders,
)
import atomic_flix
from atomic_flix.runner.names import KIT_MAPS, GraphNames, NameMapError, load_names, parse_map
from first_film_env import UNSET, under_root
from runner_samples import SILENT_GRAPH, SUNG_GRAPH

OUR_WORKFLOWS = under_root("workflows")


def test_fill_keeps_the_type_of_a_whole_placeholder_and_pastes_inside_text():
    graph = {"a": "$seed", "b": "x-$save_as"}
    filled = fill(graph, {"seed": 1934820044, "save_as": "tub-S02-ab12cd"})
    assert filled == {"a": 1934820044, "b": "x-tub-S02-ab12cd"}
    assert isinstance(filled["a"], int)
    assert graph == {"a": "$seed", "b": "x-$save_as"}, "the template itself is never changed"


def test_fill_walks_nested_nodes_and_lists():
    graph = {"1": {"inputs": {"punch": "$punch", "pair": ["$width", "$height"], "link": ["10", 0]}}}
    filled = fill(graph, {"punch": 0.7, "width": 1280, "height": 704})
    assert filled["1"]["inputs"] == {"punch": 0.7, "pair": [1280, 704], "link": ["10", 0]}


def test_placeholders_lists_every_name_once():
    assert placeholders(SUNG_GRAPH) == {"wording", "opening_still", "width", "height", "audio", "seconds", "frames",
                                        "seed", "save_as"}
    assert placeholders({"a": "$image1", "b": "$image2 and $image1"}) == {"image1", "image2"}


def test_editor_format_is_refused(tmp_path):
    path = tmp_path / "editor.json"
    path.write_text(json.dumps({"nodes": [], "links": [], "version": 0.4}), encoding="utf-8")
    with pytest.raises(TemplateError, match="Export \\(API\\)"):
        load_graph(path)


def test_meta_sidecar_is_read_and_defaults_apply_without_one(sung_graph, tmp_path):
    meta = load_meta(sung_graph)
    assert meta == GraphMeta(needs=("wording", "opening_still", "audio"), frame_multiple=8, commit_gb=40.0)
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(SUNG_GRAPH), encoding="utf-8")
    assert load_meta(bare) == GraphMeta()


def test_frames_round_up_to_the_model_step_plus_one():
    assert frames_for(9, 24, 8) == 217
    assert frames_for(12, 24, 8) == 289
    assert frames_for(5, 24, 4) == 121
    assert frames_for(5.1, 24, 17) == 137


def test_sizes_follow_the_step():
    check_size(1280, 704, 32)
    # a control-video graph: both halves of the size must be multiples of 64 (size_step 128 in its sidecar)
    check_size(1152, 640, 128)
    check_size(1280, 768, 128)
    with pytest.raises(TemplateError, match="multiple of 32"):
        check_size(1280, 700, 32)
    with pytest.raises(TemplateError, match="multiple of 128"):
        check_size(1280, 704, 128)


def _values(**extra):
    base = {"wording": "she sings", "opening_still": "stills/S02.png", "audio": "plan/S02.voice-soft.wav",
            "width": 1280, "height": 704, "seconds": 9, "frames": 217, "seed": 7, "save_as": "tub-S02-aa"}
    return {**base, **extra}


def test_a_complete_vocal_request_passes():
    check_request(SUNG_GRAPH, GraphMeta(), _values(), vocal=True)


def test_vocal_on_a_graph_without_audio_is_refused_unless_allowed():
    values = {k: v for k, v in _values().items() if k != "audio"}
    with pytest.raises(TemplateError, match="audio"):
        check_request(SILENT_GRAPH, GraphMeta(), values, vocal=True)
    check_request(SILENT_GRAPH, GraphMeta(), values, vocal=True, silent_ok=True)
    check_request(SILENT_GRAPH, GraphMeta(), values, vocal=False)


def test_render_graph_without_wording_or_opening_still_is_refused():
    graph = {k: v for k, v in SUNG_GRAPH.items() if k != "10"}
    with pytest.raises(TemplateError, match="opening_still"):
        check_request(graph, GraphMeta(), _values(), vocal=True)
    graph = {k: v for k, v in SUNG_GRAPH.items() if k != "6"}
    with pytest.raises(TemplateError, match="wording"):
        check_request(graph, GraphMeta(), _values(), vocal=True)


def test_a_still_graph_needs_only_wording():
    graph = {"6": {"inputs": {"text": "$wording"}}, "9": {"inputs": {"seed": "$seed", "p": "$save_as"}}}
    check_request(graph, GraphMeta(kind="still"), {"wording": "p", "seed": 1, "save_as": "x"}, vocal=False)


def test_a_placeholder_without_a_value_is_refused_never_sent_empty():
    graph = {**SUNG_GRAPH, "60": {"inputs": {"image": "$closing_still"}}}
    with pytest.raises(TemplateError, match="closing_still"):
        check_request(graph, GraphMeta(), _values(), vocal=True)
    with pytest.raises(TemplateError, match="closing_still"):
        check_request(graph, GraphMeta(), _values(closing_still=""), vocal=True)


def test_a_sidecar_need_without_a_value_is_refused():
    with pytest.raises(TemplateError, match="likeness"):
        check_request(SUNG_GRAPH, GraphMeta(needs=("wording", "likeness")), _values(), vocal=True)


def test_more_images_than_slots_is_refused():
    graph = {**SUNG_GRAPH, "70": {"inputs": {"image": "$image1"}}}
    with pytest.raises(TemplateError, match="image"):
        check_request(graph, GraphMeta(), _values(image1="a.png", image2="b.png"), vocal=True)
    check_request(graph, GraphMeta(), _values(image1="a.png"), vocal=True)


def test_a_graph_without_seed_or_prefix_is_refused():
    graph = {k: v for k, v in SUNG_GRAPH.items() if k != "37"}
    with pytest.raises(TemplateError, match="seed"):
        check_request(graph, GraphMeta(), _values(), vocal=True)
    graph = {k: v for k, v in SUNG_GRAPH.items() if k != "52"}
    with pytest.raises(TemplateError, match="save_as"):
        check_request(graph, GraphMeta(), _values(), vocal=True)


@pytest.mark.first_film
@pytest.mark.skipif(OUR_WORKFLOWS is None, reason=UNSET)
def test_our_sung_workflow_is_filled_through_its_name_map():
    path = OUR_WORKFLOWS / "sung-ltx23-pinned.json"
    if not path.is_file():
        pytest.skip(f"{path} is not on this machine")
    graph = load_graph(path)
    names = load_names(path)
    assert names.found_at is not None, "the kit's workflows/ folder holds this graph's name map"
    assert names.kit_names(placeholders(graph)) == {"wording", "opening_still", "width", "height", "audio",
                                                    "seconds", "frames", "seed", "save_as"}
    filled = fill(graph, _values(), names)
    assert filled["52"]["inputs"]["filename_prefix"] == "flix/tub-S02-aa"
    assert filled["37"]["inputs"]["noise_seed"] == 7
    assert placeholders(filled) == set()


# A graph saved earlier, with its own names for the kit's inputs.
OTHER_NAMES = {"6": {"inputs": {"text": "$caption"}}, "10": {"inputs": {"image": "$start_image"}},
               "37": {"inputs": {"noise_seed": "$seed"}}, "52": {"inputs": {"filename_prefix": "flix/$stem"}}}
OTHER_MAP = {"format": "atomic-flix/graph-map@1",
             "names": {"wording": "caption", "opening_still": "start_image", "save_as": "stem"}}


def _write_map(folder: Path, graph_name: str, content) -> Path:
    path = folder / graph_name.replace(".json", ".map.json")
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_a_map_beside_the_graph_lets_the_kit_names_fill_it(tmp_path):
    graph_path = tmp_path / "older.json"
    graph_path.write_text(json.dumps(OTHER_NAMES), encoding="utf-8")
    _write_map(tmp_path, "older.json", OTHER_MAP)
    names = load_names(graph_path)
    values = {"wording": "she sings", "opening_still": "S02.png", "seed": 9, "save_as": "tub-S02-aa"}
    check_request(OTHER_NAMES, GraphMeta(kind="still"), values, vocal=False, names=names)
    filled = fill(OTHER_NAMES, values, names)
    assert filled["6"]["inputs"]["text"] == "she sings"
    assert filled["10"]["inputs"]["image"] == "S02.png"
    assert filled["52"]["inputs"]["filename_prefix"] == "flix/tub-S02-aa"


def test_without_a_map_the_kit_names_are_the_graph_names(tmp_path):
    graph_path = tmp_path / "made-for-the-kit.json"
    graph_path.write_text(json.dumps(SUNG_GRAPH), encoding="utf-8")
    names = load_names(graph_path)
    assert names.found_at is None and names.to_graph == {}
    assert fill(SUNG_GRAPH, _values(), names) == fill(SUNG_GRAPH, _values())


def test_a_graph_with_other_names_and_no_map_is_refused():
    with pytest.raises(TemplateError, match="wording"):
        check_request(OTHER_NAMES, GraphMeta(kind="still"), {"wording": "p", "seed": 1, "save_as": "x"},
                      vocal=False, names=GraphNames())


def test_the_maps_folder_from_the_environment_is_searched(tmp_path, monkeypatch):
    maps = tmp_path / "maps"
    maps.mkdir()
    _write_map(maps, "older.json", OTHER_MAP)
    monkeypatch.setenv("ATOMIC_FLIX_MAPS", str(maps))
    assert load_names(tmp_path / "older.json").graph_name("wording") == "caption"


@pytest.mark.parametrize("bad, words", [
    ({"names": {"wording": "caption"}}, "format"),
    ({"format": "atomic-flix/graph-map@1", "names": {}}, "names"),
    ({"format": "atomic-flix/graph-map@1", "names": {"wording": "Caption!"}}, "not placeholder names"),
    ({"format": "atomic-flix/graph-map@1", "names": {"wording": "x", "save_as": "x"}}, "two kit names"),
])
def test_a_malformed_map_is_refused(bad, words):
    with pytest.raises(NameMapError, match=words):
        parse_map(bad, "test.map.json")


def test_the_kit_ships_a_valid_map_for_each_of_our_graphs():
    maps = sorted(KIT_MAPS.glob("*.map.json"))
    assert KIT_MAPS == Path(atomic_flix.__file__).resolve().parent / "workflows", "the maps ship inside the package"
    assert maps, "atomic_flix/workflows/ holds the name maps for our existing graphs"
    for path in maps:
        names = parse_map(json.loads(path.read_text(encoding="utf-8")), str(path))
        assert set(names.to_graph) <= {"wording", "opening_still", "closing_still", "likeness", "save_as"}


def test_a_sidecar_with_an_unknown_key_is_refused(tmp_path):
    graph_path = tmp_path / "g.json"
    graph_path.write_text(json.dumps(SUNG_GRAPH), encoding="utf-8")
    graph_path.with_suffix(".meta.json").write_text(json.dumps({"vram": 20}), encoding="utf-8")
    with pytest.raises(TemplateError, match="unknown key"):
        load_meta(graph_path)

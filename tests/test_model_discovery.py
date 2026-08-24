from fermion.cognitive.discovery import discover_models


def test_model_discovery_is_recursive_and_local(tmp_path) -> None:
    nested = tmp_path / "nested"; nested.mkdir()
    model = nested / "tiny.gguf"; model.write_bytes(b"GGUF")
    assert discover_models([tmp_path]) == [model.resolve()]

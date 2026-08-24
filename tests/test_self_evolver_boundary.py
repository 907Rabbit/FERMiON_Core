from pathlib import Path

from fermion.adapters.self_evolver import SelfEvolverAdapter, SelfEvolverConfig
from fermion.safe_self_evolver import ENGINE_ID


def test_supported_entry_points_and_adapter_share_the_canonical_self_evolver(tmp_path):
    adapter = SelfEvolverAdapter(SelfEvolverConfig(tmp_path / "evolver"))
    assert adapter.observe().state["engine_id"] == ENGINE_ID
    root_entry = (Path(__file__).parents[1] / "safe_self_evolver.py").read_text(encoding="utf-8")
    cli = (Path(__file__).parents[1] / "fermion" / "__main__.py").read_text(encoding="utf-8")
    assert "from fermion.safe_self_evolver import main" in root_entry
    assert "from .safe_self_evolver import main as self_evolver_main" in cli

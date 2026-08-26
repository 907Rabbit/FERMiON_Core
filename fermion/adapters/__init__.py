"""External candidate generators and application adapters."""

from .llama_cpp import LlamaCppAdapter, LlamaCppConfig, LlamaServerRuntime
from .unreal import UnrealAdapter, UnrealConfig, UnrealEditorAdapter
from .notepad import NotepadConfig, NotepadSandboxAdapter
from .notepad_curriculum import NotepadSafeLearningCatalog
from .notepad_ui import ClosedLoopNotepadAdapter, NotepadUIAdapter, PywinautoNotepadController
from .local_program import LocalProgramAdapter, ProgramEntry
from .imhex import ImHexReadOnlyAdapter
from .internet import InternetAdapter
from .coding import CodingSandboxAdapter, CodingSandboxConfig
from .self_evolver import SelfEvolverAdapter, SelfEvolverConfig
from .nmap_reports import NmapReportAdapter, NmapReportConfig
from .llama_runtime import LlamaRuntimeAdapter
from .science import FermionScienceAdapter
from .vendor_inventory import VendorInventoryAdapter
from .ciphey import CipheyAdapter
from .vendored_surfaces import (VendoredSurfaceAdapter, bettercap_adapter, codex_adapter,
                                ghosttrack_adapter, hackingtool_adapter, spiderfoot_adapter)

__all__ = ["LlamaCppAdapter", "LlamaCppConfig", "LlamaServerRuntime",
           "UnrealAdapter", "UnrealConfig", "UnrealEditorAdapter", "NotepadConfig",
           "NotepadSandboxAdapter", "NotepadSafeLearningCatalog", "NotepadUIAdapter",
           "ClosedLoopNotepadAdapter", "PywinautoNotepadController", "LocalProgramAdapter", "ProgramEntry",
           "ImHexReadOnlyAdapter", "InternetAdapter", "CodingSandboxAdapter", "CodingSandboxConfig",
           "SelfEvolverAdapter", "SelfEvolverConfig", "NmapReportAdapter", "NmapReportConfig",
           "LlamaRuntimeAdapter", "FermionScienceAdapter", "VendorInventoryAdapter",
           "CipheyAdapter", "VendoredSurfaceAdapter"]

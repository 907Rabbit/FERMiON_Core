"""Declared safe experiment catalog for the Notepad sandbox benchmark."""

from __future__ import annotations

from dataclasses import dataclass

from fermion.software.application import Action


@dataclass(frozen=True)
class SafeExperimentTemplate:
    name: str
    action: Action
    preconditions: tuple[str, ...]
    expected_effect: str
    rollback_strategy: str
    maximum_action_count: int
    risk_cost: float


class NotepadSafeLearningCatalog:
    """Small, reversible experiments confined by NotepadSandboxAdapter's root."""

    def __init__(self, document_name: str = "fermion_sample.txt"):
        self.templates = (
            SafeExperimentTemplate("create_test_document", Action("create_document", {"name": document_name, "content": "FERMiON\n"}),
                                   ("sandbox configured",), "document exists with expected content", "checkpoint restore", 1, 0.1),
            SafeExperimentTemplate("append_test_text", Action("append_text", {"name": document_name, "text": "sample\n"}),
                                   ("document exists",), "document content gains suffix", "checkpoint restore", 1, 0.1),
            SafeExperimentTemplate("rename_test_document", Action("rename_document", {"name": document_name, "new_name": "fermion_renamed.txt"}),
                                   ("document exists",), "new document name exists", "checkpoint restore", 1, 0.1),
            SafeExperimentTemplate("delete_test_document", Action("delete_document", {"name": document_name}),
                                   ("document exists",), "document is absent", "checkpoint restore", 1, 0.1),
        )

    def learning_templates(self) -> dict[str, Action]:
        return {item.action.operation: item.action for item in self.templates}

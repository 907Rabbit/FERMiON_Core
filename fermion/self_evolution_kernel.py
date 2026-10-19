#!/usr/bin/env python3
"""
CW-71 Falsifiable Self-Evolution Kernel - Neural Network Simulation

This simulation implements the full CW-71 architecture:
1. CandidateManifest: machine-readable manifest for every mutation
2. Self-prediction: predict mutation consequences before testing
3. Shadow evaluation: compare active vs candidate on identical tasks
4. Multi-gate promotion: hard, evidence, regression, robustness, improvement
5. Hash-chained provenance: cryptographic audit trail
6. Evolutionary memory: rejected candidates become training data

The simulation learns XOR and a regression task simultaneously,
using a small feedforward neural network as the evolvable component.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Cryptographic utilities
# ---------------------------------------------------------------------------

def canonical_json(obj: dict) -> str:
    """Return canonical JSON string for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_obj(obj: dict) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def hash_chain(previous_hash: str, event_obj: dict) -> str:
    """Extend a hash chain with a new event."""
    payload = canonical_json({"previous_hash": previous_hash, "event": event_obj})
    return sha256_bytes(payload.encode("utf-8"))


# ---------------------------------------------------------------------------
# Neural Network (evolvable component)
# ---------------------------------------------------------------------------

@dataclass
class NeuralNetwork:
    """A small feedforward network with fixed topology, evolvable weights."""
    input_size: int = 2
    hidden_size: int = 8
    output_size: int = 2

    weights1: list[float] = field(default_factory=list)
    bias1: list[float] = field(default_factory=list)
    weights2: list[float] = field(default_factory=list)
    bias2: list[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.weights1:
            rng = random.Random(42)
            self._randomize(rng)

    def _randomize(self, rng: random.Random, scale: float = 1.0):
        self.weights1 = [rng.uniform(-scale, scale) for _ in range(self.input_size * self.hidden_size)]
        self.bias1 = [rng.uniform(-scale, scale) for _ in range(self.hidden_size)]
        self.weights2 = [rng.uniform(-scale, scale) for _ in range(self.hidden_size * self.output_size)]
        self.bias2 = [rng.uniform(-scale, scale) for _ in range(self.output_size)]

    def forward(self, x: list[float]) -> list[float]:
        # Hidden layer with tanh activation
        hidden = []
        for h in range(self.hidden_size):
            s = self.bias1[h]
            for i in range(self.input_size):
                s += self.weights1[i * self.hidden_size + h] * x[i]
            hidden.append(math.tanh(s))
        # Output layer (linear for regression, sigmoid for classification)
        outputs = []
        for o in range(self.output_size):
            s = self.bias2[o]
            for h in range(self.hidden_size):
                s += self.weights2[h * self.output_size + o] * hidden[h]
            outputs.append(s)
        # Output 0: regression value; Output 1: classification logit
        outputs[1] = 1.0 / (1.0 + math.exp(-outputs[1]))
        return outputs

    def clone(self) -> "NeuralNetwork":
        n = NeuralNetwork(
            self.input_size, self.hidden_size, self.output_size,
            list(self.weights1), list(self.bias1),
            list(self.weights2), list(self.bias2),
        )
        return n

    def to_flat_weights(self) -> list[float]:
        return self.weights1 + self.bias1 + self.weights2 + self.bias2

    def from_flat_weights(self, flat: list[float]) -> "NeuralNetwork":
        n1 = self.input_size * self.hidden_size
        n2 = self.hidden_size
        n3 = self.hidden_size * self.output_size
        n4 = self.output_size
        assert len(flat) == n1 + n2 + n3 + n4
        return NeuralNetwork(
            self.input_size, self.hidden_size, self.output_size,
            flat[:n1], flat[n1:n1+n2], flat[n1+n2:n1+n2+n3], flat[n1+n2+n3:]
        )

    def total_params(self) -> int:
        return len(self.to_flat_weights())


# ---------------------------------------------------------------------------
# Dataset definitions
# ---------------------------------------------------------------------------

def make_xor_dataset(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    data = []
    for _ in range(n):
        a = rng.choice([0, 1])
        b = rng.choice([0, 1])
        xor_val = float(a ^ b)
        regression_val = 0.5 * a + 0.3 * b + 0.1 * a * b
        data.append({
            "input": [float(a), float(b)],
            "target": [regression_val, xor_val],
        })
    return data


def make_adversarial_dataset(data: list[dict], noise_scale: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    perturbed = []
    for sample in data:
        noisy_input = [x + rng.uniform(-noise_scale, noise_scale) for x in sample["input"]]
        perturbed.append({
            "input": noisy_input,
            "target": sample["target"],
        })
    return perturbed


# ---------------------------------------------------------------------------
# Objective vector computation
# ---------------------------------------------------------------------------

def compute_objective_vector(
    net: NeuralNetwork,
    data: list[dict],
    adversarial_data: Optional[list[dict]] = None,
) -> dict[str, float]:
    """Compute the CW-71 objective vector for a network."""
    regression_errors = []
    classification_errors = []
    total_samples = len(data)
    
    for sample in data:
        out = net.forward(sample["input"])
        regression_errors.append((out[0] - sample["target"][0]) ** 2)
        classification_errors.append((out[1] - sample["target"][1]) ** 2)
    
    task_loss = sum(regression_errors) / total_samples
    classification_loss = sum(classification_errors) / total_samples
    
    # Robustness: evaluate on adversarial data if provided
    robustness_loss = 0.0
    if adversarial_data:
        adv_errors = []
        for sample in adversarial_data:
            out = net.forward(sample["input"])
            adv_errors.append((out[0] - sample["target"][0]) ** 2)
        robustness_loss = sum(adv_errors) / len(adversarial_data)
    
    # Complexity: number of parameters (normalized)
    complexity_cost = net.total_params() / 100.0
    
    # Compute cost: approximate FLOPS (input*hidden + hidden*output)
    compute_cost = net.input_size * net.hidden_size + net.hidden_size * net.output_size
    compute_cost = compute_cost / 100.0
    
    # Grounding loss: penalize extreme weights
    flat = net.to_flat_weights()
    grounding_loss = sum(w * w for w in flat) / len(flat)
    
    # Safety risk: 0 if all weights bounded, else 1
    safety_risk = 1.0 if any(abs(w) > 10.0 for w in flat) else 0.0
    
    return {
        "task_loss": task_loss,
        "classification_loss": classification_loss,
        "robustness_loss": robustness_loss,
        "complexity_cost": complexity_cost,
        "compute_cost": compute_cost,
        "grounding_loss": grounding_loss,
        "safety_risk": safety_risk,
    }


# ---------------------------------------------------------------------------
# Mutation operators
# ---------------------------------------------------------------------------

def mutate_network(
    net: NeuralNetwork,
    rng: random.Random,
    mutation_rate: float = 0.15,
    mutation_scale: float = 0.3,
) -> tuple[NeuralNetwork, dict]:
    """Mutate a network's weights. Returns (mutated_network, mutation_info)."""
    flat = net.to_flat_weights()
    mutated = list(flat)
    num_mutations = 0
    
    for i in range(len(mutated)):
        if rng.random() < mutation_rate:
            delta = rng.gauss(0.0, mutation_scale)
            mutated[i] = max(-10.0, min(10.0, mutated[i] + delta))
            num_mutations += 1
    
    new_net = net.from_flat_weights(mutated)
    mutation_info = {
        "type": "weight_gaussian",
        "rate": mutation_rate,
        "scale": mutation_scale,
        "num_weights_changed": num_mutations,
        "total_weights": len(flat),
    }
    return new_net, mutation_info


def mutate_network_structured(
    net: NeuralNetwork,
    rng: random.Random,
    layer: str,
    mutation_scale: float,
) -> tuple[NeuralNetwork, dict]:
    """Structured mutation targeting a specific layer."""
    flat = net.to_flat_weights()
    mutated = list(flat)
    
    n1 = net.input_size * net.hidden_size
    n2 = net.hidden_size
    n3 = net.hidden_size * net.output_size
    
    if layer == "input_hidden":
        indices = list(range(n1 + n2))
    elif layer == "hidden_output":
        indices = list(range(n1 + n2, n1 + n2 + n3 + net.output_size))
    else:
        indices = list(range(len(flat)))
    
    for i in indices:
        if rng.random() < 0.3:
            mutated[i] = max(-10.0, min(10.0, mutated[i] + rng.gauss(0.0, mutation_scale)))
    
    new_net = net.from_flat_weights(mutated)
    mutation_info = {
        "type": "structured_weight_gaussian",
        "layer": layer,
        "scale": mutation_scale,
        "indices_affected": len(indices),
    }
    return new_net, mutation_info


# ---------------------------------------------------------------------------
# Self-Prediction Model
# ---------------------------------------------------------------------------

@dataclass
class SelfPredictionModel:
    """
    A simple linear model that predicts the task loss change of a mutation
    based on mutation features. This is the self-model that FERMiON uses
    to predict consequences before testing.
    """
    weights: dict[str, float] = field(default_factory=dict)
    learning_rate: float = 0.01

    def feature_vector(self, mutation_info: dict, parent_obj: dict, num_weights: int) -> dict[str, float]:
        features = {
            "num_weights_changed": float(mutation_info.get("num_weights_changed", 0)),
            "total_weights": float(num_weights),
            "mutation_scale": float(mutation_info.get("scale", 0)),
        }
        # One-hot encode mutation type
        mtype = mutation_info.get("type", "unknown")
        for t in ["weight_gaussian", "structured_weight_gaussian"]:
            features[f"type_{t}"] = 1.0 if mtype == t else 0.0
        # Include parent objective as features
        for key in ["task_loss", "grounding_loss"]:
            features[f"parent_{key}"] = float(parent_obj.get(key, 0.0))
        return features

    def predict_delta(self, features: dict[str, float]) -> float:
        prediction = 0.0
        for key, value in features.items():
            if key in self.weights:
                prediction += self.weights[key] * value
        return prediction

    def update(self, features: dict[str, float], actual_delta: float):
        prediction = self.predict_delta(features)
        error = actual_delta - prediction
        for key, value in features.items():
            if key not in self.weights:
                self.weights[key] = 0.0
            self.weights[key] += self.learning_rate * error * value

    def calibration_error(self, predictions: list[float], actuals: list[float]) -> float:
        if not predictions:
            return 0.0
        return sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)

    def directional_accuracy(self, predictions: list[float], actuals: list[float]) -> float:
        if not predictions:
            return 0.0
        correct = 0
        for p, a in zip(predictions, actuals):
            if (p > 0 and a > 0) or (p < 0 and a < 0) or (abs(p) < 1e-6 and abs(a) < 1e-6):
                correct += 1
        return correct / len(predictions)


# ---------------------------------------------------------------------------
# CandidateManifest
# ---------------------------------------------------------------------------

@dataclass
class CandidateManifest:
    candidate_id: int
    parent_version: int
    parent_sha256: str
    mutation_type: str
    mutation_parameters: dict
    modified_components: list[str]
    immutable_components: list[str]
    hypothesis: str
    predicted_metrics: dict[str, float]
    observed_metrics: dict[str, float] = field(default_factory=dict)
    hard_gate_results: dict[str, bool] = field(default_factory=dict)
    regression_results: dict[str, float] = field(default_factory=dict)
    robustness_results: dict[str, float] = field(default_factory=dict)
    prediction_error: float = 0.0
    promotion_decision: str = "PENDING"
    rejection_reason: str = ""
    candidate_sha256: str = ""
    manifest_sha256: str = ""
    timestamp_ns: int = 0

    def compute_manifest_hash(self) -> str:
        """Compute the manifest's own hash."""
        obj = self.to_dict()
        obj["manifest_sha256"] = ""
        return sha256_obj(obj)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "parent_version": self.parent_version,
            "parent_sha256": self.parent_sha256,
            "mutation_type": self.mutation_type,
            "mutation_parameters": self.mutation_parameters,
            "modified_components": self.modified_components,
            "immutable_components": self.immutable_components,
            "hypothesis": self.hypothesis,
            "predicted_metrics": self.predicted_metrics,
            "observed_metrics": self.observed_metrics,
            "hard_gate_results": self.hard_gate_results,
            "regression_results": self.regression_results,
            "robustness_results": self.robustness_results,
            "prediction_error": self.prediction_error,
            "promotion_decision": self.promotion_decision,
            "rejection_reason": self.rejection_reason,
            "candidate_sha256": self.candidate_sha256,
            "manifest_sha256": self.manifest_sha256,
            "timestamp_ns": self.timestamp_ns,
        }


# ---------------------------------------------------------------------------
# FERMiON Self-Evolution Kernel
# ---------------------------------------------------------------------------

class FERMiONKernel:
    """
    The CW-71 Falsifiable Self-Evolution Kernel.
    Implements the full evolutionary cycle with self-prediction and multi-gate promotion.
    """

    def __init__(
        self,
        seed: int = 42,
        workspace: Optional[Path] = None,
    ):
        self.seed = seed
        self.rng = random.Random(seed)
        self.workspace = workspace or Path("fermion_runtime")
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Active state
        self.active_network = NeuralNetwork()
        self.active_network._randomize(random.Random(seed))
        self.active_version = 0
        self.active_sha256 = sha256_obj({"network": self.active_network.to_flat_weights(), "version": 0})

        # Self-prediction model
        self.self_model = SelfPredictionModel()

        # Evolutionary memory
        self.evolutionary_memory: list[dict] = []
        self.rejected_candidates: list[CandidateManifest] = []
        self.promoted_candidates: list[CandidateManifest] = []

        # Audit log (hash-chained)
        self.audit_chain: list[dict] = []
        self.audit_previous_hash = "GENESIS"

        # Performance tracking
        self.performance_history: list[float] = []
        self.calibration_history: list[float] = []
        self.directional_accuracy_history: list[float] = []
        self.success_rate_history: list[float] = []
        self.candidate_counter = 0

        # Datasets
        self.train_data = make_xor_dataset(200, seed=1001)
        self.val_data = make_xor_dataset(80, seed=2002)
        self.test_data = make_xor_dataset(80, seed=3003)
        self.adversarial_val = make_adversarial_dataset(self.val_data, noise_scale=0.1, seed=4004)

        # Hash datasets
        self.train_hash = sha256_obj({"data": self.train_data})
        self.val_hash = sha256_obj({"data": self.val_data})
        self.test_hash = sha256_obj({"data": self.test_data})

        # Validator hash (immutable falsifier root)
        self.validator_code = open(__file__, "r", encoding="utf-8").read()
        self.validator_hash = sha256_bytes(self.validator_code.encode("utf-8"))

        # Hard gate thresholds
        self.thresholds = {
            "safety_risk": 0.0,          # Must be zero
            "grounding_max": 5.0,        # Must be below
            "task_loss_improvement": 0.005,  # Must improve by at least 0.5%
            "robustness_regression": 0.02,   # Max 2% robustness regression
            "complexity_regression": 0.50,   # Max 50% complexity increase
        }

        # Promotion count for efficiency metric
        self.evaluated_count = 0
        self.promoted_count = 0

    # -----------------------------------------------------------------------
    # Audit log operations
    # -----------------------------------------------------------------------

    def append_audit(self, event_obj: dict):
        """Append an event to the hash-chained audit log."""
        new_hash = hash_chain(self.audit_previous_hash, event_obj)
        record = {
            "hash": new_hash,
            "previous_hash": self.audit_previous_hash,
            "event": event_obj,
            "timestamp_ns": time.time_ns(),
        }
        self.audit_chain.append(record)
        self.audit_previous_hash = new_hash

    def verify_audit_chain(self) -> bool:
        """Verify the integrity of the audit chain."""
        prev = "GENESIS"
        for record in self.audit_chain:
            recomputed = hash_chain(prev, record["event"])
            if recomputed != record["hash"]:
                return False
            prev = record["hash"]
        return True

    # -----------------------------------------------------------------------
    # Objective computation
    # -----------------------------------------------------------------------

    def compute_active_objective(self) -> dict[str, float]:
        return compute_objective_vector(
            self.active_network, self.val_data, self.adversarial_val
        )

    def compute_candidate_objective(self, net: NeuralNetwork) -> dict[str, float]:
        return compute_objective_vector(net, self.val_data, self.adversarial_val)

    # -----------------------------------------------------------------------
    # Mutation proposal
    # -----------------------------------------------------------------------

    def propose_mutation(self) -> tuple[NeuralNetwork, dict, str]:
        """Propose a mutation. Eventually this will use evolutionary memory."""
        # For now, mix random mutation types
        mtype = self.rng.choice(["weight_gaussian", "structured_weight_gaussian"])
        if mtype == "weight_gaussian":
            scale = 0.3 * (1.0 - min(0.8, len(self.promoted_candidates) * 0.05))
            scale = max(0.05, scale)
            candidate, info = mutate_network(
                self.active_network, self.rng,
                mutation_rate=0.15, mutation_scale=scale,
            )
            hypothesis = f"Gaussian weight mutation with scale {scale:.3f} improves task loss"
        else:
            layer = self.rng.choice(["input_hidden", "hidden_output"])
            scale = 0.4
            candidate, info = mutate_network_structured(
                self.active_network, self.rng, layer=layer, mutation_scale=scale
            )
            hypothesis = f"Structured mutation of {layer} layer improves task loss"
        return candidate, info, hypothesis

    # -----------------------------------------------------------------------
    # Self-prediction
    # -----------------------------------------------------------------------

    def predict_mutation_delta(
        self, mutation_info: dict, parent_objective: dict
    ) -> float:
        """Predict the change in task loss for a mutation."""
        features = self.self_model.feature_vector(
            mutation_info, parent_objective, self.active_network.total_params()
        )
        return self.self_model.predict_delta(features)

    # -----------------------------------------------------------------------
    # Multi-gate promotion decision
    # -----------------------------------------------------------------------

    def evaluate_promotion(
        self,
        parent_obj: dict[str, float],
        candidate_obj: dict[str, float],
        manifest: CandidateManifest,
    ) -> tuple[bool, dict, str]:
        """Apply multi-gate promotion criteria."""
        gates = {}

        # Gate 1: Hard safety
        gates["safety_risk_zero"] = candidate_obj["safety_risk"] <= self.thresholds["safety_risk"]
        
        # Gate 2: Grounding bound
        gates["grounding_bounded"] = candidate_obj["grounding_loss"] <= self.thresholds["grounding_max"]
        
        # Gate 3: Evidence (always true if we got here)
        gates["evidence_recorded"] = manifest.candidate_sha256 != ""
        
        # Gate 4: Regression - robustness
        robustness_delta = candidate_obj["robustness_loss"] - parent_obj["robustness_loss"]
        gates["robustness_no_regression"] = robustness_delta <= self.thresholds["robustness_regression"]
        
        # Gate 5: Regression - complexity
        complexity_delta = candidate_obj["complexity_cost"] - parent_obj["complexity_cost"]
        gates["complexity_no_regression"] = complexity_delta <= self.thresholds["complexity_regression"]
        
        # Gate 6: Improvement - task loss
        task_delta = candidate_obj["task_loss"] - parent_obj["task_loss"]
        improvement_ratio = abs(task_delta) / (parent_obj["task_loss"] + 1e-8)
        gates["task_loss_improvement"] = task_delta < -self.thresholds["task_loss_improvement"] * parent_obj["task_loss"]

        # All gates must pass
        all_passed = all(gates.values())

        if not all_passed:
            # Determine rejection reason
            failed_gates = [g for g, passed in gates.items() if not passed]
            reason = f"Failed gates: {', '.join(failed_gates)}"
            return False, gates, reason
        
        return True, gates, ""

    # -----------------------------------------------------------------------
    # Main evolution cycle
    # -----------------------------------------------------------------------

    def run_evolution_cycle(self) -> CandidateManifest:
        """Run a single CW-71 evolution cycle."""
        self.candidate_counter += 1
        self.evaluated_count += 1

        # Step 1: Observe - compute current objective
        parent_obj = self.compute_active_objective()

        # Step 2: Propose mutation
        candidate_net, mutation_info, hypothesis = self.propose_mutation()

        # Step 3: Predict consequences (self-prediction)
        predicted_delta = self.predict_mutation_delta(mutation_info, parent_obj)
        predicted_obj = dict(parent_obj)
        predicted_obj["task_loss"] = parent_obj["task_loss"] + predicted_delta

        # Step 4: Build CandidateManifest
        manifest = CandidateManifest(
            candidate_id=self.candidate_counter,
            parent_version=self.active_version,
            parent_sha256=self.active_sha256,
            mutation_type=mutation_info["type"],
            mutation_parameters=mutation_info,
            modified_components=["neural_network_weights"],
            immutable_components=["validator", "falsification_root", "promotion_policy"],
            hypothesis=hypothesis,
            predicted_metrics=predicted_obj,
            timestamp_ns=time.time_ns(),
        )

        # Step 5: Shadow evaluation - compute actual objective
        candidate_obj = self.compute_candidate_objective(candidate_net)
        manifest.observed_metrics = candidate_obj
        manifest.candidate_sha256 = sha256_obj({
            "network": candidate_net.to_flat_weights(),
            "version": self.candidate_counter,
        })

        # Compute actual delta
        actual_delta = candidate_obj["task_loss"] - parent_obj["task_loss"]

        # Step 6: Update self-model with prediction error
        features = self.self_model.feature_vector(
            mutation_info, parent_obj, self.active_network.total_params()
        )
        self.self_model.update(features, actual_delta)
        manifest.prediction_error = abs(predicted_delta - actual_delta)

        # Step 7: Multi-gate promotion
        promote, gates, reason = self.evaluate_promotion(
            parent_obj, candidate_obj, manifest
        )
        manifest.hard_gate_results = gates

        # Robustness results
        manifest.robustness_results = {
            "parent_robustness": parent_obj["robustness_loss"],
            "candidate_robustness": candidate_obj["robustness_loss"],
            "delta": candidate_obj["robustness_loss"] - parent_obj["robustness_loss"],
        }

        # Regression results
        manifest.regression_results = {
            "task_loss_delta": actual_delta,
            "classification_loss_delta": candidate_obj["classification_loss"] - parent_obj["classification_loss"],
            "complexity_delta": candidate_obj["complexity_cost"] - parent_obj["complexity_cost"],
        }

        # Step 8: Promotion or rejection
        if promote:
            manifest.promotion_decision = "PROMOTE"
            self.promoted_candidates.append(manifest)
            self.active_network = candidate_net
            self.active_version += 1
            self.active_sha256 = manifest.candidate_sha256
            self.promoted_count += 1
        else:
            manifest.promotion_decision = "REJECT"
            manifest.rejection_reason = reason
            self.rejected_candidates.append(manifest)

        manifest.manifest_sha256 = manifest.compute_manifest_hash()

        # Step 9: Record in evolutionary memory
        memory_entry = {
            "candidate_id": manifest.candidate_id,
            "mutation_type": manifest.mutation_type,
            "mutation_parameters": manifest.mutation_parameters,
            "parent_objective": parent_obj,
            "candidate_objective": candidate_obj,
            "predicted_delta": predicted_delta,
            "actual_delta": actual_delta,
            "promotion_decision": manifest.promotion_decision,
            "rejection_reason": manifest.rejection_reason,
        }
        self.evolutionary_memory.append(memory_entry)

        # Step 10: Audit log (hash-chained)
        self.append_audit({
            "event": "candidate_evaluated",
            "candidate_id": manifest.candidate_id,
            "promotion_decision": manifest.promotion_decision,
            "candidate_sha256": manifest.candidate_sha256,
            "predicted_delta": predicted_delta,
            "actual_delta": actual_delta,
            "gates": gates,
            "validator_hash": self.validator_hash,
            "dataset_hashes": {
                "train": self.train_hash,
                "val": self.val_hash,
                "test": self.test_hash,
            },
        })

        # Track metrics
        self.performance_history.append(parent_obj["task_loss"])
        self.calibration_history.append(manifest.prediction_error)
        
        # Directional accuracy over last 10 predictions
        if len(self.evolutionary_memory) >= 2:
            recent = self.evolutionary_memory[-10:]
            preds = [m["predicted_delta"] for m in recent]
            actuals = [m["actual_delta"] for m in recent]
            da = self.self_model.directional_accuracy(preds, actuals)
            self.directional_accuracy_history.append(da)
        else:
            self.directional_accuracy_history.append(0.0)
        
        # Success rate
        success_rate = self.promoted_count / self.evaluated_count if self.evaluated_count > 0 else 0.0
        self.success_rate_history.append(success_rate)

        return manifest

    def run_evolution(self, num_cycles: int, verbose: bool = True) -> dict:
        """Run multiple evolution cycles."""
        for cycle in range(num_cycles):
            manifest = self.run_evolution_cycle()
            if verbose and (cycle < 5 or cycle % 20 == 0 or cycle == num_cycles - 1):
                print(f"Cycle {cycle + 1}/{num_cycles}: "
                      f"Decision={manifest.promotion_decision} "
                      f"TaskLoss={self.performance_history[-1]:.4f} "
                      f"PredErr={manifest.prediction_error:.4f} "
                      f"SuccessRate={self.success_rate_history[-1]:.3f}")

        # Compute final metrics
        final_obj = self.compute_active_objective()
        
        # Compute calibration over all predictions
        all_preds = [m["predicted_delta"] for m in self.evolutionary_memory]
        all_actuals = [m["actual_delta"] for m in self.evolutionary_memory]
        final_calibration = self.self_model.calibration_error(all_preds, all_actuals)
        final_directional = self.self_model.directional_accuracy(all_preds, all_actuals)

        # Verify audit chain
        audit_verified = self.verify_audit_chain()

        return {
            "total_cycles": num_cycles,
            "promoted": self.promoted_count,
            "rejected": len(self.rejected_candidates),
            "success_rate": self.promoted_count / num_cycles if num_cycles > 0 else 0,
            "final_task_loss": final_obj["task_loss"],
            "final_classification_loss": final_obj["classification_loss"],
            "final_grounding_loss": final_obj["grounding_loss"],
            "self_model_calibration_error": final_calibration,
            "self_model_directional_accuracy": final_directional,
            "audit_chain_verified": audit_verified,
            "performance_history": self.performance_history,
            "calibration_history": self.calibration_history,
            "directional_accuracy_history": self.directional_accuracy_history,
            "success_rate_history": self.success_rate_history,
            "validator_hash": self.validator_hash,
            "dataset_hashes": {
                "train": self.train_hash,
                "val": self.val_hash,
                "test": self.test_hash,
            },
            "self_model_weights": dict(self.self_model.weights),
        }


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("CW-71 Falsifiable Self-Evolution Kernel - Neural Network Simulation")
    print("=" * 70)
    print()
    print("Hypothesis H71b: Can FERMiON learn to predict which mutations")
    print("will improve its own performance?")
    print()
    
    seed = 42
    num_cycles = 80
    
    print(f"Seed: {seed}")
    print(f"Evolution cycles: {num_cycles}")
    print(f"Network topology: 2-8-2 (input-hidden-output)")
    print()
    
    kernel = FERMiONKernel(seed=seed)
    
    print(f"Validator hash: {kernel.validator_hash[:16]}...")
    print(f"Training data hash: {kernel.train_hash[:16]}...")
    print(f"Validation data hash: {kernel.val_hash[:16]}...")
    print()
    
    print("Running evolution...")
    print("-" * 70)
    
    results = kernel.run_evolution(num_cycles, verbose=True)
    
    print()
    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print()
    print(f"Total cycles: {results['total_cycles']}")
    print(f"Promoted: {results['promoted']}")
    print(f"Rejected: {results['rejected']}")
    print(f"Success rate: {results['success_rate']:.3f}")
    print()
    print(f"Final task loss: {results['final_task_loss']:.6f}")
    print(f"Final classification loss: {results['final_classification_loss']:.6f}")
    print(f"Final grounding loss: {results['final_grounding_loss']:.6f}")
    print()
    print(f"Self-model calibration error: {results['self_model_calibration_error']:.6f}")
    print(f"Self-model directional accuracy: {results['self_model_directional_accuracy']:.3f}")
    print()
    print(f"Audit chain verified: {results['audit_chain_verified']}")
    print()
    
    # Analyze the self-model weights
    print("Self-model learned weights (feature importance):")
    for key, value in sorted(results['self_model_weights'].items()):
        print(f"  {key}: {value:.6f}")
    print()
    
    # Test hypothesis H71b
    print("Hypothesis H71b Evaluation:")
    if len(results['success_rate_history']) >= 20:
        first_half = sum(results['success_rate_history'][:len(results['success_rate_history'])//2]) / (len(results['success_rate_history'])//2)
        second_half = sum(results['success_rate_history'][len(results['success_rate_history'])//2:]) / (len(results['success_rate_history']) - len(results['success_rate_history'])//2)
        print(f"  Success rate first half: {first_half:.3f}")
        print(f"  Success rate second half: {second_half:.3f}")
        if second_half > first_half:
            print("  → Success rate is increasing (H71b positive signal)")
        else:
            print("  → Success rate not yet increasing")
    
    if len(results['calibration_history']) >= 20:
        first_half_cal = sum(results['calibration_history'][:len(results['calibration_history'])//2]) / (len(results['calibration_history'])//2)
        second_half_cal = sum(results['calibration_history'][len(results['calibration_history'])//2:]) / (len(results['calibration_history']) - len(results['calibration_history'])//2)
        print(f"  Calibration error first half: {first_half_cal:.6f}")
        print(f"  Calibration error second half: {second_half_cal:.6f}")
        if second_half_cal < first_half_cal:
            print("  → Calibration error is decreasing (H71b positive signal)")
        else:
            print("  → Calibration error not yet decreasing")
    print()
    
    # Save results to file
    output_path = Path("fermion_project/simulation_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_path}")
    print()
    
    return results


if __name__ == "__main__":
    main()

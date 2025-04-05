"""Core data models for the diagnostic system."""

from enum import Enum
from typing import List, Optional, Union, Dict, Any, Literal
from pydantic import BaseModel, Field


class EvidenceStrength(str, Enum):
    """Represents the strength of evidence for or against a failure mode."""
    CONFIRMS = "confirms"
    RULES_OUT = "rules_out"
    SUGGESTS = "suggests"
    SUGGESTS_AGAINST = "suggests_against"
    INCONCLUSIVE = "inconclusive"


class ComparisonOperator(str, Enum):
    """Operators used for comparing sensor readings against thresholds."""
    EQUALS = "="
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_THAN_EQUAL = "<="
    GREATER_THAN_EQUAL = ">="
    IN = "in"

    @classmethod
    def _missing_(cls, value):
        if value == "==":
            return cls.EQUALS
        return super()._missing_(value)


# Base Classes
class Node(BaseModel):
    """Base class for all graph nodes."""
    id: Optional[str] = None  # Neo4j elementId
    name: str
    type: str  # e.g., "component", "state", "failure_mode"
    description: Optional[str] = None


class Relationship(BaseModel):
    """Base class for all relationships."""
    id: Optional[str] = None  # Neo4j elementId
    type: str
    source: Node  # Source node object
    target: Node  # Target node object

    def get_source_id(self) -> Optional[str]:
        """Get the source node's ID if it exists."""
        return self.source.id if self.source else None

    def get_dest_id(self) -> Optional[str]:
        """Get the destination node's ID if it exists."""
        return self.target.id if self.target else None

    def has_valid_ids(self) -> bool:
        """Check if both source and dest nodes have valid IDs."""
        return bool(self.get_source_id() and self.get_dest_id())


# Node Types
class FailureMode(Node):
    """Represents a distinct way in which the system can fail."""
    type: Literal["FailureMode"] = "FailureMode"


class Observation(Node):
    """Represents something a human user can notice or describe."""
    type: Literal["Observation"] = "Observation"


class SensorReading(Node):
    """Represents quantifiable measurements from system sensors."""
    type: Literal["SensorReading"] = "SensorReading"
    unit: Optional[str] = None  # e.g., "V", "C", "enum"
    value: Optional[Union[float, int]] = None
    value_descriptions: Optional[str] = None  # Store as JSON string


# --- Relationship Properties ---
class EvidenceProperties(BaseModel):
    """Properties specific to EvidenceLink relationships."""
    when_true_strength: Optional[EvidenceStrength] = None
    when_false_strength: Optional[EvidenceStrength] = None
    operator: Optional[ComparisonOperator] = None
    threshold: Optional[Union[float, List[Union[str, float]]]] = None
    when_true_rationale: Optional[str] = None
    when_false_rationale: Optional[str] = None
    # Removed 'name' and 'rationale' as they are now specific to true/false cases


# Relationship Types
class CausesLink(Relationship):
    """Represents a causal relationship between a failure mode and an observation."""
    type: Literal["CAUSES"] = "CAUSES" # Match expected output casing


class EvidenceLink(Relationship):
    """Represents diagnostic evidence between an observation/sensor and a failure mode."""
    type: Literal["EVIDENCE_FOR"] = "EVIDENCE_FOR" # Match expected output casing
    properties: Optional[EvidenceProperties] = None # Nested properties


# Diagnostic Results (for API responses)
class DiagnosticResult(BaseModel):
    """Result of a diagnostic query."""
    failure_mode: str
    confidence: EvidenceStrength
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    explanation: Optional[str] = None


class TestRecommendation(BaseModel):
    """Recommendation for the next test to perform."""
    name: str
    type: str = "observation"  # Can be "observation" or "sensor_reading"
    strength_if_true: EvidenceStrength
    would_help_with: List[str] = Field(default_factory=list)
    operator: Optional[ComparisonOperator] = None
    threshold: Optional[Union[float, int, List[Union[float, int]]]] = None


class ExplanationEvidence(BaseModel):
    """Represents evidence used in explaining a diagnostic result."""
    name: str
    type: str  # "observation" or "sensor_reading"
    operator: Optional[ComparisonOperator] = None
    threshold: Optional[Union[float, int, List[Union[float, int]]]] = None
    actual_value: Optional[Union[float, int, str]] = None
    strength: EvidenceStrength
    for_or_against: str = "for"  # "for" or "against"
    explanation: Optional[str] = None 
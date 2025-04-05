"""Core diagnostic engine implementation."""

import json
import logging
from typing import List, Dict, Any, Optional

from telltale.core.models import (
    DiagnosticResult,
    EvidenceStrength,
    TestRecommendation,
    ExplanationEvidence
)
from telltale.core.database import Neo4jConnection
from telltale.core.example_data import ExampleScenarios

logger = logging.getLogger(__name__)

class DiagnosticEngine:
    """Main diagnostic engine that processes observations and sensor readings."""

    def __init__(self):
        """Initialize the diagnostic engine with a database connection."""
        self.db = Neo4jConnection()

    def diagnose(self, observations: List[str], sensor_readings: Optional[Dict[str, float]] = None, 
                 include_explanations: bool = False) -> List[DiagnosticResult]:
        """
        Process observations and sensor readings to determine likely failure modes.
        
        Args:
            observations: List of observation names that are true
            sensor_readings: Optional dict of sensor readings {sensor_name: value}
            include_explanations: Whether to include explanation text for each diagnosis
            
        Returns:
            List of DiagnosticResult objects sorted by confidence
        """
        # Build the query
        query = """
            // Match all failure modes that could be relevant
            MATCH (fm:FailureMode)
            WHERE EXISTS {
                MATCH (fm)-[:CAUSES]->(o:Observation)
                WHERE o.name IN $observations
            }
            
            // Collect evidence from observations
            OPTIONAL MATCH (o:Observation)-[e:EVIDENCE_FOR]->(fm)
            WHERE o.name IN $observations
            WITH fm, collect({
                name: o.name,
                strength: e.when_true_strength,
                evidence_type: 'observation'
            }) as observation_evidence
            
            // Collect evidence from sensor readings
            OPTIONAL MATCH (s:SensorReading)-[e:EVIDENCE_FOR]->(fm)
            WHERE s.name IN $sensor_names
            WITH fm, observation_evidence, collect({
                name: s.name,
                strength: e.when_true_strength,
                when_false_strength: e.when_false_strength,
                evidence_type: 'sensor',
                operator: e.operator,
                threshold: e.threshold
            }) as sensor_evidence
            
            // Combine evidence
            WITH fm, observation_evidence + sensor_evidence as all_evidence
            
            // For each piece of evidence, determine if it supports or contradicts
            UNWIND all_evidence as evidence
            WITH fm, evidence
            WHERE evidence.name IS NOT NULL
            
            WITH fm, 
                 evidence.name as evidence_name,
                 evidence.strength as strength,
                 evidence.when_false_strength as when_false_strength,
                 evidence.evidence_type as evidence_type,
                 evidence.operator as operator,
                 evidence.threshold as threshold
            
            // Determine the effective strength based on sensor comparisons
            WITH fm, evidence_name,
                 CASE 
                     WHEN evidence_type = 'sensor' THEN
                         CASE
                             WHEN operator = '<' AND $sensor_readings[evidence_name] < threshold THEN strength
                             WHEN operator = '>' AND $sensor_readings[evidence_name] > threshold THEN strength
                             WHEN operator = '=' AND $sensor_readings[evidence_name] = threshold THEN strength
                             ELSE null
                         END
                     ELSE strength
                 END as effective_strength,
                 CASE 
                     WHEN evidence_type = 'sensor' THEN
                         CASE
                             WHEN operator = '<' AND $sensor_readings[evidence_name] >= threshold THEN 'contradicting'
                             WHEN operator = '>' AND $sensor_readings[evidence_name] <= threshold THEN 'contradicting'
                             WHEN operator = '=' AND $sensor_readings[evidence_name] <> threshold THEN 'contradicting'
                             ELSE null
                         END
                     ELSE null
                 END as contradicting_flag,
                 CASE
                     WHEN evidence_type = 'sensor' THEN
                         CASE
                             WHEN operator = '<' AND $sensor_readings[evidence_name] >= threshold THEN when_false_strength
                             WHEN operator = '>' AND $sensor_readings[evidence_name] <= threshold THEN when_false_strength
                             WHEN operator = '=' AND $sensor_readings[evidence_name] <> threshold THEN when_false_strength
                             ELSE null
                         END
                     ELSE null
                 END as when_false_strength_value
            
            // Group evidence by failure mode
            WITH fm, 
                 collect({name: evidence_name, contradicting: contradicting_flag}) as evidence_items,
                 collect(evidence_name) as supporting_evidence,
                 collect(effective_strength) as strengths,
                 collect(when_false_strength_value) as false_strengths
            
            // Extract contradicting evidence
            WITH fm,
                 supporting_evidence,
                 strengths,
                 [item IN evidence_items WHERE item.contradicting = 'contradicting' | item.name] as contradicting_evidence,
                 false_strengths
                 
            // Check if any evidence rules out this failure mode
            WITH fm,
                 supporting_evidence,
                 contradicting_evidence,
                 strengths,
                 'rules_out' IN false_strengths as is_ruled_out
            
            // Calculate overall confidence (using max strength for now)
            WITH fm,
                 supporting_evidence,
                 contradicting_evidence,
                 is_ruled_out,
                 CASE
                     // If the failure mode is ruled out, use that
                     WHEN is_ruled_out = true THEN 'rules_out'
                     // If we have contradicting evidence, the overall confidence should be INCONCLUSIVE
                     WHEN size(contradicting_evidence) > 0 THEN 'inconclusive'
                     // Otherwise use the highest strength level from supporting evidence
                     WHEN size([x IN strengths WHERE x = 'confirms']) > 0 THEN 'confirms'
                     WHEN size([x IN strengths WHERE x = 'suggests']) > 0 THEN 'suggests'
                     WHEN size([x IN strengths WHERE x = 'suggests_against']) > 0 THEN 'suggests_against'
                     WHEN size([x IN strengths WHERE x = 'rules_out']) > 0 THEN 'rules_out'
                     ELSE 'inconclusive'
                 END as confidence
            
            // Only return results that aren't ruled out
            WHERE confidence <> 'rules_out'
            
            RETURN fm.name as failure_mode,
                   confidence,
                   supporting_evidence,
                   contradicting_evidence
            ORDER BY 
                CASE confidence
                    WHEN 'confirms' THEN 0
                    WHEN 'suggests' THEN 1
                    WHEN 'suggests_against' THEN 2
                    WHEN 'inconclusive' THEN 3
                END
        """
        
        # Execute query
        params = {
            "observations": observations,
            "sensor_readings": sensor_readings or {},
            "sensor_names": list(sensor_readings.keys()) if sensor_readings else []
        }
        
        results = self.db.run_query(query, params)
        
        # Convert to DiagnosticResult objects
        diagnostic_results = [
            DiagnosticResult(
                failure_mode=r["failure_mode"],
                confidence=EvidenceStrength(r["confidence"]),
                supporting_evidence=r["supporting_evidence"],
                contradicting_evidence=r.get("contradicting_evidence", [])
            )
            for r in results
        ]
        
        # Add explanations if requested
        if include_explanations:
            for result in diagnostic_results:
                result.explanation = self.explain_diagnosis_text(
                    result.failure_mode, observations, sensor_readings
                )
        
        return diagnostic_results

    def get_test_recommendations(self, current_observations: List[str]) -> List[TestRecommendation]:
        """
        Get recommendations for additional tests that would help narrow down the failure mode.
        
        Args:
            current_observations: List of observation names that are currently known to be true
            
        Returns:
            List of TestRecommendation objects sorted by usefulness
        """
        query = """
            // Find all failure modes that could explain the current observations
            MATCH (fm:FailureMode)
            WHERE EXISTS {
                MATCH (fm)-[:CAUSES]->(o:Observation)
                WHERE o.name IN $observations
            }
            
            // Find all evidence that could help diagnose these failure modes
            MATCH (ev)-[e:EVIDENCE_FOR]->(fm)
            WHERE NOT ev.name IN $observations
                  AND (ev:Observation OR ev:SensorReading)
            
            // Group by evidence to see which tests would help with multiple failure modes
            WITH ev,
                 CASE WHEN ev:Observation THEN 'observation' ELSE 'sensor_reading' END as type,
                 e.operator as operator,
                 e.threshold as threshold,
                 e.when_true_strength as strength_if_true,
                 collect(DISTINCT fm.name) as would_help_with
            
            RETURN ev.name as name,
                   type,
                   operator,
                   threshold,
                   strength_if_true,
                   would_help_with
            ORDER BY size(would_help_with) DESC
        """
        
        results = self.db.run_query(query, {"observations": current_observations})
        
        return [
            TestRecommendation(
                name=r["name"],
                type=r["type"],
                strength_if_true=EvidenceStrength(r["strength_if_true"]),
                would_help_with=r["would_help_with"],
                operator=r["operator"],
                threshold=r["threshold"]
            )
            for r in results
        ]
        
    def explain_diagnosis(self, failure_mode: str, observations: List[str], 
                          sensor_readings: Optional[Dict[str, float]] = None) -> List[ExplanationEvidence]:
        """
        Explain why a specific failure mode was diagnosed based on observations and sensor readings.
        
        Args:
            failure_mode: The name of the failure mode to explain
            observations: List of observation names that are true
            sensor_readings: Optional dict of sensor readings {sensor_name: value}
            
        Returns:
            List of ExplanationEvidence objects explaining the evidence paths
        """
        # Build the query to trace evidence paths
        query = """
            // Match the specific failure mode
            MATCH (fm:FailureMode {name: $failure_mode})
            
            // First, find all observations that are evidence
            OPTIONAL MATCH (o:Observation)-[e:EVIDENCE_FOR]->(fm)
            WHERE o.name IN $observations
            WITH fm, collect({
                name: o.name,
                type: 'observation',
                operator: null,
                threshold: null,
                actual_value: true,
                strength: e.when_true_strength,
                for_or_against: 'for',
                explanation: CASE 
                    WHEN e.name IS NOT NULL THEN e.name 
                    ELSE 'Observation "' + o.name + '" is evidence for "' + fm.name + '"'
                END,
                rationale: e.rationale
            }) as observation_evidence
            
            // Next, find all sensor readings that are evidence
            OPTIONAL MATCH (s:SensorReading)-[e:EVIDENCE_FOR]->(fm)
            WHERE s.name IN $sensor_names
            
            WITH fm, observation_evidence, collect({
                name: s.name,
                type: 'sensor_reading',
                operator: e.operator,
                threshold: e.threshold,
                actual_value: $sensor_readings[s.name],
                strength: CASE 
                    WHEN e.operator = '<' AND $sensor_readings[s.name] < e.threshold THEN e.when_true_strength
                    WHEN e.operator = '>' AND $sensor_readings[s.name] > e.threshold THEN e.when_true_strength
                    WHEN e.operator = '=' AND $sensor_readings[s.name] = e.threshold THEN e.when_true_strength
                    WHEN e.operator = '<' AND $sensor_readings[s.name] >= e.threshold THEN e.when_false_strength
                    WHEN e.operator = '>' AND $sensor_readings[s.name] <= e.threshold THEN e.when_false_strength
                    WHEN e.operator = '=' AND $sensor_readings[s.name] <> e.threshold THEN e.when_false_strength
                    ELSE null
                END,
                for_or_against: CASE 
                    WHEN e.operator = '<' AND $sensor_readings[s.name] < e.threshold THEN 'for'
                    WHEN e.operator = '>' AND $sensor_readings[s.name] > e.threshold THEN 'for'
                    WHEN e.operator = '=' AND $sensor_readings[s.name] = e.threshold THEN 'for'
                    WHEN e.operator = '<' AND $sensor_readings[s.name] >= e.threshold THEN 'against'
                    WHEN e.operator = '>' AND $sensor_readings[s.name] <= e.threshold THEN 'against'
                    WHEN e.operator = '=' AND $sensor_readings[s.name] <> e.threshold THEN 'against'
                    ELSE null
                END,
                explanation: CASE 
                    WHEN e.name IS NOT NULL THEN e.name 
                    ELSE CASE 
                        WHEN e.operator = '<' AND $sensor_readings[s.name] < e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' is less than threshold ' + toString(e.threshold)
                        WHEN e.operator = '>' AND $sensor_readings[s.name] > e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' is greater than threshold ' + toString(e.threshold)
                        WHEN e.operator = '=' AND $sensor_readings[s.name] = e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' equals threshold ' + toString(e.threshold)
                        WHEN e.operator = '<' AND $sensor_readings[s.name] >= e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' is NOT less than threshold ' + toString(e.threshold)
                        WHEN e.operator = '>' AND $sensor_readings[s.name] <= e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' is NOT greater than threshold ' + toString(e.threshold)
                        WHEN e.operator = '=' AND $sensor_readings[s.name] <> e.threshold 
                            THEN 'Sensor "' + s.name + '" reading ' + toString($sensor_readings[s.name]) + ' does NOT equal threshold ' + toString(e.threshold)
                        ELSE null
                    END
                END,
                rationale: e.rationale
            }) as sensor_evidence
            
            // Combine all evidence
            WITH observation_evidence + sensor_evidence as all_evidence
            
            // Filter out null entries
            UNWIND all_evidence as evidence
            WITH evidence
            WHERE evidence.strength IS NOT NULL
            
            RETURN evidence.name as name,
                  evidence.type as type,
                  evidence.operator as operator,
                  evidence.threshold as threshold,
                  evidence.actual_value as actual_value,
                  evidence.strength as strength,
                  evidence.for_or_against as for_or_against,
                  evidence.explanation as explanation,
                  evidence.rationale as rationale
        """
        
        # Execute query
        params = {
            "failure_mode": failure_mode,
            "observations": observations,
            "sensor_readings": sensor_readings or {},
            "sensor_names": list(sensor_readings.keys()) if sensor_readings else []
        }
        
        results = self.db.run_query(query, params)
        
        # Convert to ExplanationEvidence objects
        return [
            ExplanationEvidence(
                name=r["name"],
                type=r["type"],
                operator=r["operator"],
                threshold=r["threshold"],
                actual_value=r["actual_value"],
                strength=EvidenceStrength(r["strength"]),
                for_or_against=r["for_or_against"],
                explanation=r["explanation"] + (f" - {r['rationale']}" if r.get("rationale") else "")
            )
            for r in results
        ]
        
    def explain_diagnosis_text(self, failure_mode: str, observations: List[str], 
                              sensor_readings: Optional[Dict[str, float]] = None) -> str:
        """
        Generate a human-readable text explanation for why a specific failure mode was diagnosed.
        
        Args:
            failure_mode: The name of the failure mode to explain
            observations: List of observation names that are true
            sensor_readings: Optional dict of sensor readings {sensor_name: value}
            
        Returns:
            A string with a human-readable explanation of the diagnosis
        """
        evidence_list = self.explain_diagnosis(failure_mode, observations, sensor_readings)
        
        if not evidence_list:
            return f"No evidence was found to explain the diagnosis of '{failure_mode}'."
        
        # Group evidence by whether it supports or contradicts the diagnosis
        supporting_evidence = [e for e in evidence_list if e.for_or_against == 'for']
        contradicting_evidence = [e for e in evidence_list if e.for_or_against == 'against']
        
        # Start with a header explaining what we're doing
        explanation = f"Explanation for diagnosis: '{failure_mode}'\n\n"
        
        # Add section for supporting evidence
        if supporting_evidence:
            explanation += "Evidence supporting this diagnosis:\n"
            
            # Group by strength
            confirms = [e for e in supporting_evidence if e.strength == EvidenceStrength.CONFIRMS]
            suggests = [e for e in supporting_evidence if e.strength == EvidenceStrength.SUGGESTS]
            
            if confirms:
                explanation += "\nStrong confirmations:\n"
                for e in confirms:
                    explanation += f"- {e.explanation}\n"
            
            if suggests:
                explanation += "\nSuggestive evidence:\n"
                for e in suggests:
                    explanation += f"- {e.explanation}\n"
        else:
            explanation += "No evidence was found supporting this diagnosis.\n"
        
        # Add section for contradicting evidence
        if contradicting_evidence:
            explanation += "\nEvidence contradicting this diagnosis:\n"
            
            # Group by strength
            rules_out = [e for e in contradicting_evidence if e.strength == EvidenceStrength.RULES_OUT]
            suggests_against = [e for e in contradicting_evidence if e.strength == EvidenceStrength.SUGGESTS_AGAINST]
            
            if rules_out:
                explanation += "\nStrong contradictions:\n"
                for e in rules_out:
                    explanation += f"- {e.explanation}\n"
            
            if suggests_against:
                explanation += "\nMild contradictions:\n"
                for e in suggests_against:
                    explanation += f"- {e.explanation}\n"
        else:
            explanation += "\nNo evidence was found contradicting this diagnosis.\n"
            
        # Add causal paths
        causal_paths = self.get_causal_paths(failure_mode, observations)
        if causal_paths:
            explanation += "\nCausal links from this failure mode to the observed symptoms:\n\n"
            for i, path in enumerate(causal_paths):
                explanation += f"Path {i+1}:\n"
                explanation += f"- {path['failure_mode']} CAUSES {path['observation']}\n"
                if path.get('intermediate_nodes'):
                    for node in path['intermediate_nodes']:
                        explanation += f"  └─> {node}\n"
        
        return explanation
        
    def get_causal_paths(self, failure_mode: str, observations: List[str]) -> List[Dict[str, Any]]:
        """
        Get causal paths from a failure mode to the observed symptoms.
        
        Args:
            failure_mode: The name of the failure mode
            observations: List of observation names
            
        Returns:
            List of dicts representing paths from the failure mode to observations
        """
        query = """
            // Match paths from the failure mode to observations
            MATCH path = (fm:FailureMode {name: $failure_mode})-[:CAUSES*]->(o:Observation)
            WHERE o.name IN $observations
            
            // Extract nodes along the path
            WITH fm, o, [node IN nodes(path) | node.name] AS path_nodes
            
            // Remove first and last nodes to get only intermediate nodes
            WITH fm, o, 
                 CASE 
                     WHEN size(path_nodes) > 2 
                     THEN [node IN path_nodes[1..-1] WHERE node <> fm.name AND node <> o.name]
                     ELSE []
                 END AS intermediate_nodes
            
            RETURN fm.name as failure_mode,
                   o.name as observation,
                   intermediate_nodes
        """
        
        results = self.db.run_query(query, {
            "failure_mode": failure_mode,
            "observations": observations
        })
        
        return results 

    def explain_all_diagnoses(self, diagnoses: List[DiagnosticResult], 
                             observations: List[str], 
                             sensor_readings: Optional[Dict[str, float]] = None) -> List[DiagnosticResult]:
        """
        Add explanations to a list of diagnostic results.
        
        Args:
            diagnoses: List of DiagnosticResult objects to explain
            observations: List of observation names that are true
            sensor_readings: Optional dict of sensor readings {sensor_name: value}
            
        Returns:
            The same list of DiagnosticResult objects with explanations added
        """
        for result in diagnoses:
            result.explanation = self.explain_diagnosis_text(
                result.failure_mode, observations, sensor_readings
            )
        
        return diagnoses 
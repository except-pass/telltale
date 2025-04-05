"""Truth Table Generation Module for Diagnostic Engine.

This module provides functionality to generate and evaluate truth tables
for diagnostic graphs, allowing users to systematically explore how different
combinations of observations and sensor values affect diagnostic outcomes.
"""

import itertools
from typing import Dict, List, Set, Any, Tuple, Optional, Union
import csv
import io
import json
from pydantic import BaseModel

from telltale.core.models import (
    EvidenceStrength, Node, FailureMode, Observation, 
    SensorReading, CausesLink, EvidenceLink
)
from telltale.core.diagnostic import DiagnosticEngine


class ExpectedOutcome(BaseModel):
    """Represents an expected diagnostic outcome for a test case."""
    failure_mode: str
    confidence: EvidenceStrength


class TestCase(BaseModel):
    """Represents a single test case with inputs and expected outcomes."""
    inputs: Dict[str, Any]  # Contains 'observations' and 'sensor_values'
    expected: List[ExpectedOutcome]


class TruthTableResult(BaseModel):
    """Represents the result of a single test in the truth table."""
    inputs: Dict[str, Any]  # The input combination tested
    diagnosed_failure_modes: List[Dict[str, Any]]  # The actual diagnoses
    expected_failure_modes: List[Dict[str, Any]]  # The expected diagnoses
    unexpected_results: List[Dict[str, Any]]  # Results not in expected list
    missing_results: List[Dict[str, Any]]  # Expected results not found
    has_surprise: bool  # True if there are unexpected or missing results


class TruthTable:
    """Class for generating and evaluating truth tables for diagnostic graphs."""

    def __init__(self, diagnostic_engine: DiagnosticEngine):
        """Initialize the truth table generator.
        
        Args:
            diagnostic_engine: The diagnostic engine to use for evaluations
        """
        self.diagnostic_engine = diagnostic_engine
        
        # Initialize storage for inputs and expected outputs
        self.observations: Set[str] = set()
        self.sensor_readings: Dict[str, Dict[str, Any]] = {}
        self.expected_outcomes: List[TestCase] = []
        
    def scan_graph(self) -> None:
        """Scan the Neo4j graph to identify all observations and sensor readings."""
        # Query for all observation nodes
        obs_query = """
        MATCH (o:Observation)
        RETURN o.name as name
        """
        obs_results = self.diagnostic_engine.db.run_query(obs_query)
        for result in obs_results:
            self.observations.add(result["name"])
            
        # Query for all sensor reading nodes and their evidence relationships
        sensor_query = """
        MATCH (s:SensorReading)-[e:EVIDENCE_FOR]->(fm:FailureMode)
        RETURN 
            s.name as sensor_name,
            s.unit as unit,
            e.operator as operator,
            e.threshold as threshold
        """
        sensor_results = self.diagnostic_engine.db.run_query(sensor_query)
        
        # Group sensors and their thresholds
        for result in sensor_results:
            sensor_name = result["sensor_name"]
            if sensor_name not in self.sensor_readings:
                self.sensor_readings[sensor_name] = {
                    "unit": result["unit"],
                    "thresholds": [],
                    "operators": []
                }
            
            threshold = result["threshold"]
            operator = result["operator"]
            
            if threshold not in self.sensor_readings[sensor_name]["thresholds"]:
                self.sensor_readings[sensor_name]["thresholds"].append(threshold)
            
            if operator not in self.sensor_readings[sensor_name]["operators"]:
                self.sensor_readings[sensor_name]["operators"].append(operator)
    
    def register_expected_outcome(self, test_case: Dict[str, Any]) -> None:
        """Register an expected outcome for a specific test case.
        
        Args:
            test_case: Dictionary containing 'inputs' and 'expected' keys.
                inputs: Dict with 'observations' and 'sensor_values'.
                expected: List of Dict with 'failure_mode' and 'confidence'.
        """
        # Convert the raw dict to a TestCase model
        expected_outcomes = [
            ExpectedOutcome(failure_mode=outcome["failure_mode"], 
                            confidence=outcome["confidence"])
            for outcome in test_case["expected"]
        ]
        
        test_case_model = TestCase(
            inputs=test_case["inputs"],
            expected=expected_outcomes
        )
        
        self.expected_outcomes.append(test_case_model)
    
    def generate_test_cases(self, 
                           vary_observations: Optional[List[str]] = None,
                           fixed_observations: Optional[Dict[str, bool]] = None,
                           vary_sensors: Optional[List[str]] = None,
                           fixed_sensor_values: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """Generate test case combinations based on specified inputs to vary and fix.
        
        Args:
            vary_observations: List of observation names to vary (True/False/Unknown)
            fixed_observations: Dict of observation names with fixed True values
            vary_sensors: List of sensor names to vary values for
            fixed_sensor_values: Dict of sensor names with fixed values
            
        Returns:
            List of input combinations, each a dict with 'observations' and 'sensor_values'.
        """
        test_cases = []
        
        # Initialize with default empty values if not provided
        if vary_observations is None:
            vary_observations = []
        if fixed_observations is None:
            fixed_observations = {}
        if vary_sensors is None:
            vary_sensors = []
        if fixed_sensor_values is None:
            fixed_sensor_values = {}
        
        # Use all observations if none specified to vary
        if not vary_observations and not fixed_observations:
            vary_observations = list(self.observations)
        
        # Generate all combinations of varying observations (present or absent)
        observation_combinations = [[]]  # Start with empty list for no observations
        for r in range(1, len(vary_observations) + 1):
            for combo in itertools.combinations(vary_observations, r):
                observation_combinations.append(list(combo))
        
        # For each sensor to vary, generate test values around each threshold
        sensor_value_combinations = [{}]  # Start with empty dict for no sensor readings
        
        for sensor_name in vary_sensors:
            if sensor_name in self.sensor_readings:
                sensor_info = self.sensor_readings[sensor_name]
                sensor_test_values = []
                
                for threshold in sensor_info["thresholds"]:
                    # Generate values around each threshold regardless of operators
                    sensor_test_values.append(threshold - 0.1)  # Just below
                    sensor_test_values.append(threshold + 0.1)  # Just above
                    sensor_test_values.append(threshold)  # Exactly at threshold
                
                # Add a null value to simulate no sensor data
                sensor_test_values.append(None)
                
                # Create new combinations by adding each test value to existing combinations
                new_combinations = []
                for existing in sensor_value_combinations:
                    for value in sensor_test_values:
                        new_combo = existing.copy()
                        if value is not None:  # Skip None values
                            new_combo[sensor_name] = value
                        new_combinations.append(new_combo)
                
                sensor_value_combinations = new_combinations
        
        # Generate all combinations of observations and sensor values
        for obs_combo in observation_combinations:
            # Add fixed observations to each combo
            full_obs = obs_combo.copy()
            for obs, present in fixed_observations.items():
                if present and obs not in full_obs:
                    full_obs.append(obs)
            
            for sensor_combo in sensor_value_combinations:
                # Add fixed sensor values to each combo
                full_sensors = sensor_combo.copy()
                for sensor, value in fixed_sensor_values.items():
                    full_sensors[sensor] = value
                
                test_cases.append({
                    "observations": full_obs,
                    "sensor_values": full_sensors
                })
        
        return test_cases

    def run_test_case(self, test_case: Dict[str, Any]) -> TruthTableResult:
        """Run the diagnostic engine on a single test case.
        
        Args:
            test_case: Dict with 'observations' and 'sensor_values' keys.
            
        Returns:
            TruthTableResult with the test case results.
        """
        # Run the diagnostic engine
        diagnoses = self.diagnostic_engine.diagnose(
            observations=test_case["observations"],
            sensor_readings=test_case["sensor_values"]
        )
        
        # Convert diagnoses to a standard format for comparison
        actual_results = [
            {
                "failure_mode": d.failure_mode,
                "confidence": d.confidence.value
            }
            for d in diagnoses
        ]
        
        # Find the expected outcomes for this exact input, if any
        expected_results = []
        has_registered_expectations = False
        for expected in self.expected_outcomes:
            # Check if this expected outcome matches our test case
            if (set(expected.inputs.get("observations", [])) == set(test_case["observations"]) and
                expected.inputs.get("sensor_values", {}) == test_case["sensor_values"]):
                has_registered_expectations = True
                expected_results = [
                    {
                        "failure_mode": e.failure_mode,
                        "confidence": e.confidence.value
                    }
                    for e in expected.expected
                ]
        
        # Identify unexpected and missing results
        unexpected = []
        missing = []
        
        # Only look for unexpected/missing results if we have registered expectations
        if has_registered_expectations:
            for actual in actual_results:
                if actual not in expected_results:
                    unexpected.append(actual)
            
            for expected in expected_results:
                if expected not in actual_results:
                    missing.append(expected)
        
        return TruthTableResult(
            inputs=test_case,
            diagnosed_failure_modes=actual_results,
            expected_failure_modes=expected_results,
            unexpected_results=unexpected,
            missing_results=missing,
            has_surprise=(has_registered_expectations and (len(unexpected) > 0 or len(missing) > 0))
        )
    
    def run_truth_table(self, 
                        vary_observations: Optional[List[str]] = None,
                        fixed_observations: Optional[Dict[str, bool]] = None,
                        vary_sensors: Optional[List[str]] = None,
                        fixed_sensor_values: Optional[Dict[str, float]] = None,
                        test_cases: Optional[List[Dict[str, Any]]] = None) -> List[TruthTableResult]:
        """Run test cases through the diagnostic engine.
        
        Args:
            vary_observations: List of observation names to vary
            fixed_observations: Dict of observation names with fixed values
            vary_sensors: List of sensor names to vary values for
            fixed_sensor_values: Dict of sensor names with fixed values
            test_cases: Optional list of pre-defined test cases. If provided, other parameters are ignored.
            
        Returns:
            List of TruthTableResult objects.
        """
        if test_cases is None:
            test_cases = self.generate_test_cases(
                vary_observations=vary_observations,
                fixed_observations=fixed_observations,
                vary_sensors=vary_sensors,
                fixed_sensor_values=fixed_sensor_values
            )
        
        results = []
        for test_case in test_cases:
            result = self.run_test_case(test_case)
            results.append(result)
        
        return results
    
    def format_results(self, 
                      results: List[TruthTableResult], 
                      only_surprises: bool = False, 
                      format: str = 'text') -> str:
        """Format test results in a readable format.
        
        Args:
            results: List of TruthTableResult objects.
            only_surprises: If True, only include unexpected results.
            format: Output format ('text', 'csv', 'html', or 'table').
            
        Returns:
            String representation of the results.
        """
        if only_surprises:
            results = [r for r in results if r.has_surprise]
            
        if not results:
            return "No results to display."
            
        if format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Get all unique observation names and sensor names
            all_obs = set()
            all_sensors = set()
            for result in results:
                all_obs.update(result.inputs['observations'])
                all_sensors.update(result.inputs['sensor_values'].keys())
            
            # Write header
            header = []
            for obs in sorted(all_obs):
                header.append(f"Obs: {obs}")
            for sensor in sorted(all_sensors):
                header.append(f"Sensor: {sensor}")
            header.extend(['Diagnosed Failure Modes', 'Expected Failure Modes', 
                          'Unexpected Results', 'Missing Results'])
            writer.writerow(header)
            
            # Write data
            for result in results:
                row = []
                # Add observation values (True/False)
                for obs in sorted(all_obs):
                    row.append("Yes" if obs in result.inputs['observations'] else "No")
                
                # Add sensor values
                for sensor in sorted(all_sensors):
                    row.append(str(result.inputs['sensor_values'].get(sensor, "Unknown")))
                
                # Add diagnosis results
                row.append(json.dumps(result.diagnosed_failure_modes))
                row.append(json.dumps(result.expected_failure_modes))
                row.append(json.dumps(result.unexpected_results))
                row.append(json.dumps(result.missing_results))
                
                writer.writerow(row)
                
            return output.getvalue()
            
        elif format == 'html':
            # Get all unique observation names and sensor names
            all_obs = set()
            all_sensors = set()
            for result in results:
                all_obs.update(result.inputs['observations'])
                all_sensors.update(result.inputs['sensor_values'].keys())
            
            html = ['<table border="1">']
            
            # Header
            html.append('<tr>')
            for obs in sorted(all_obs):
                html.append(f'<th>Obs: {obs}</th>')
            for sensor in sorted(all_sensors):
                html.append(f'<th>Sensor: {sensor}</th>')
            html.append('<th>Diagnosed Failure Modes</th>')
            html.append('<th>Expected Failure Modes</th>')
            html.append('<th>Unexpected Results</th>')
            html.append('<th>Missing Results</th>')
            html.append('</tr>')
            
            # Data
            for result in results:
                html.append('<tr>')
                
                # Add observation values
                for obs in sorted(all_obs):
                    value = "Yes" if obs in result.inputs['observations'] else "No"
                    html.append(f'<td>{value}</td>')
                
                # Add sensor values
                for sensor in sorted(all_sensors):
                    value = result.inputs['sensor_values'].get(sensor, "Unknown")
                    html.append(f'<td>{value}</td>')
                
                # Add diagnosis results
                html.append(f'<td>{json.dumps(result.diagnosed_failure_modes)}</td>')
                html.append(f'<td>{json.dumps(result.expected_failure_modes)}</td>')
                
                # Color unexpected and missing results in red
                if result.unexpected_results:
                    html.append(f'<td style="color:red">{json.dumps(result.unexpected_results)}</td>')
                else:
                    html.append('<td></td>')
                    
                if result.missing_results:
                    html.append(f'<td style="color:red">{json.dumps(result.missing_results)}</td>')
                else:
                    html.append('<td></td>')
                    
                html.append('</tr>')
                
            html.append('</table>')
            return '\n'.join(html)
        
        elif format == 'table':
            # Get all unique observation names and sensor names
            all_obs = set()
            all_sensors = set()
            for result in results:
                all_obs.update(result.inputs['observations'])
                all_sensors.update(result.inputs['sensor_values'].keys())
            
            # Calculate column widths
            col_widths = {}
            for obs in sorted(all_obs):
                col_widths[f"Obs: {obs}"] = max(len(f"Obs: {obs}"), 5)  # Yes/No values
            
            for sensor in sorted(all_sensors):
                col_widths[f"Sensor: {sensor}"] = max(len(f"Sensor: {sensor}"), 10)  # Values may be longer
            
            col_widths["Diagnosed"] = 40  # For diagnosed failure modes
            col_widths["Expected"] = 40  # For expected failure modes
            col_widths["Unexpected"] = 40  # For unexpected results
            col_widths["Missing"] = 40  # For missing results
            
            # Build the table
            lines = []
            
            # Header
            header = []
            for obs in sorted(all_obs):
                header.append(f"Obs: {obs}".ljust(col_widths[f"Obs: {obs}"]))
            for sensor in sorted(all_sensors):
                header.append(f"Sensor: {sensor}".ljust(col_widths[f"Sensor: {sensor}"]))
            header.extend([
                "Diagnosed".ljust(col_widths["Diagnosed"]),
                "Expected".ljust(col_widths["Expected"]),
                "Unexpected".ljust(col_widths["Unexpected"]),
                "Missing".ljust(col_widths["Missing"])
            ])
            lines.append(" | ".join(header))
            
            # Separator
            separator = []
            for key, width in col_widths.items():
                separator.append("-" * width)
            lines.append("-|-".join(separator))
            
            # Data rows
            for result in results:
                row = []
                
                # Add observation values
                for obs in sorted(all_obs):
                    value = "Yes" if obs in result.inputs['observations'] else "No"
                    row.append(value.ljust(col_widths[f"Obs: {obs}"]))
                
                # Add sensor values
                for sensor in sorted(all_sensors):
                    value = str(result.inputs['sensor_values'].get(sensor, "Unknown"))
                    row.append(value.ljust(col_widths[f"Sensor: {sensor}"]))
                
                # Add diagnosis results
                diag_str = str(result.diagnosed_failure_modes)
                if len(diag_str) > col_widths["Diagnosed"]:
                    diag_str = diag_str[:col_widths["Diagnosed"]-3] + "..."
                row.append(diag_str.ljust(col_widths["Diagnosed"]))
                
                # Add expected results
                exp_str = str(result.expected_failure_modes)
                if len(exp_str) > col_widths["Expected"]:
                    exp_str = exp_str[:col_widths["Expected"]-3] + "..."
                row.append(exp_str.ljust(col_widths["Expected"]))
                
                # Add unexpected results
                unexp_str = str(result.unexpected_results)
                if len(unexp_str) > col_widths["Unexpected"]:
                    unexp_str = unexp_str[:col_widths["Unexpected"]-3] + "..."
                row.append(unexp_str.ljust(col_widths["Unexpected"]))
                
                # Add missing results
                miss_str = str(result.missing_results)
                if len(miss_str) > col_widths["Missing"]:
                    miss_str = miss_str[:col_widths["Missing"]-3] + "..."
                row.append(miss_str.ljust(col_widths["Missing"]))
                
                lines.append(" | ".join(row))
                
            return "\n".join(lines)
            
        else:  # default text format
            output = []
            for i, result in enumerate(results):
                output.append(f"Test Case {i+1}:")
                output.append(f"  Observations: {', '.join(result.inputs['observations'])}")
                output.append(f"  Sensor Values: {result.inputs['sensor_values']}")
                output.append(f"  Diagnosed Failure Modes: {result.diagnosed_failure_modes}")
                
                if result.expected_failure_modes:
                    output.append(f"  Expected Failure Modes: {result.expected_failure_modes}")
                
                if result.unexpected_results:
                    output.append(f"  UNEXPECTED RESULTS: {result.unexpected_results}")
                
                if result.missing_results:
                    output.append(f"  MISSING RESULTS: {result.missing_results}")
                    
                output.append("")
                
            return '\n'.join(output)
    
    def check_for_surprises(self, results: List[TruthTableResult]) -> bool:
        """Check if there are any unexpected or missing results.
        
        Args:
            results: List of TruthTableResult objects.
            
        Returns:
            True if there are surprises, False otherwise.
        """
        return any(r.has_surprise for r in results) 
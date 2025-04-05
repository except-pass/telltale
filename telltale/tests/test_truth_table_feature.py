"""Unit tests for the Truth Table feature."""

import unittest
import sys
import os
import tempfile
from telltale.tests.test_utils import Neo4jTestCase, is_neo4j_running
from telltale.core.diagnostic import DiagnosticEngine
from telltale.core.truth_table import TruthTable
from telltale.core.models import FailureMode, Observation, SensorReading, CausesLink, EvidenceLink


class TruthTableFeatureTest(Neo4jTestCase):
    """Test cases for the Truth Table feature."""
    
    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        self.diagnostic_engine = DiagnosticEngine()
        self.diagnostic_engine.db = self.connection
        self.truth_table = TruthTable(self.diagnostic_engine)
    
    def tearDown(self):
        """Clean up after each test."""
        super().tearDown()
    
    def test_truth_table_generation(self):
        """Test generating a truth table with varying inputs."""
        # Setup a test graph
        test_graph = {
            "failure_modes": [
                {
                    "name": "Dead Battery",
                    "description": "The battery is discharged or failed"
                },
                {
                    "name": "Speaker Broken",
                    "description": "The speaker is damaged or disconnected"
                }
            ],
            "observations": [
                {
                    "name": "No Sound",
                    "description": "Device produces no sound"
                },
                {
                    "name": "Buzz or Hiss",
                    "description": "Device produces a buzzing or hissing sound"
                }
            ],
            "sensor_readings": [
                {
                    "name": "battery_voltage",
                    "description": "Battery voltage in volts",
                    "unit": "V"
                }
            ],
            "causes_relationships": [
                {
                    "failure_mode": "Dead Battery",
                    "observation": "No Sound"
                },
                {
                    "failure_mode": "Speaker Broken",
                    "observation": "No Sound"
                },
                {
                    "failure_mode": "Speaker Broken",
                    "observation": "Buzz or Hiss"
                }
            ],
            "evidence_relationships": [
                {
                    "observation": "No Sound",
                    "failure_mode": "Dead Battery",
                    "when_true_strength": "suggests",
                    "when_false_strength": "rules_out"
                },
                {
                    "observation": "No Sound",
                    "failure_mode": "Speaker Broken",
                    "when_true_strength": "suggests",
                    "when_false_strength": "rules_out"
                },
                {
                    "observation": "Buzz or Hiss",
                    "failure_mode": "Speaker Broken",
                    "when_true_strength": "confirms",
                    "when_false_strength": "inconclusive"
                },
                {
                    "sensor": "battery_voltage",
                    "failure_mode": "Dead Battery",
                    "when_true_strength": "confirms",
                    "when_false_strength": "rules_out",
                    "operator": "<",
                    "threshold": 3.5
                }
            ]
        }
        
        # Load the test graph
        self._load_test_graph(test_graph)
        
        # Scan the graph to identify inputs
        self.truth_table.scan_graph()
        
        # Test varying all observations
        test_cases = self.truth_table.generate_test_cases(
            vary_observations=["No Sound", "Buzz or Hiss"]
        )
        self.assertEqual(len(test_cases), 4)  # Should have 4 combinations: [], [No Sound], [Buzz or Hiss], [No Sound, Buzz or Hiss]
        
        # Test varying all sensors
        test_cases = self.truth_table.generate_test_cases(
            vary_sensors=["battery_voltage"]
        )
        # Should have at least 2 values: one below threshold and one above threshold
        self.assertGreaterEqual(len(test_cases), 2)
        
        # Test with fixed observations
        test_cases = self.truth_table.generate_test_cases(
            vary_sensors=["battery_voltage"],
            fixed_observations={"No Sound": True}
        )
        for case in test_cases:
            self.assertIn("No Sound", case["observations"])
        
        # Test with fixed sensor values
        test_cases = self.truth_table.generate_test_cases(
            vary_observations=["No Sound", "Buzz or Hiss"],
            fixed_sensor_values={"battery_voltage": 3.0}
        )
        for case in test_cases:
            self.assertEqual(case["sensor_values"]["battery_voltage"], 3.0)
        
        # Register expected outcomes
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": ["No Sound"],
                "sensor_values": {"battery_voltage": 3.0}
            },
            "expected": [
                {
                    "failure_mode": "Dead Battery",
                    "confidence": "confirms"
                },
                {
                    "failure_mode": "Speaker Broken",
                    "confidence": "suggests"
                }
            ]
        })
        
        # Run a specific test case
        results = self.truth_table.run_truth_table(
            test_cases=[{
                "observations": ["No Sound"],
                "sensor_values": {"battery_voltage": 3.0}
            }]
        )
        
        # Verify results
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].diagnosed_failure_modes), 2)
        self.assertEqual(results[0].unexpected_results, [])
        self.assertEqual(results[0].missing_results, [])
        
        # Test output format
        text_output = self.truth_table.format_results(results)
        self.assertIn("No Sound", text_output)
        self.assertIn("battery_voltage", text_output)
        
        # Test HTML output
        html_output = self.truth_table.format_results(results, format='html')
        self.assertIn("<table", html_output)
        self.assertIn("</table>", html_output)
        
        # Test CSV output
        csv_output = self.truth_table.format_results(results, format='csv')
        self.assertIn("Obs: No Sound", csv_output)
        
        # Test table output
        table_output = self.truth_table.format_results(results, format='table')
        self.assertIn("Obs: No Sound", table_output)
        self.assertIn("Diagnosed", table_output)
    
    def test_comprehensive_truth_table(self):
        """Test a more comprehensive truth table with multiple observations and sensors."""
        # Setup a test graph with more elements
        test_graph = {
            "failure_modes": [
                {"name": "Dead Battery", "description": "Battery is discharged"},
                {"name": "Speaker Broken", "description": "Speaker is damaged"},
                {"name": "Software Crash", "description": "Software has crashed"}
            ],
            "observations": [
                {"name": "No Sound", "description": "No sound output"},
                {"name": "Buzz or Hiss", "description": "Distorted sound"},
                {"name": "No Display", "description": "Display is blank"}
            ],
            "sensor_readings": [
                {"name": "battery_voltage", "description": "Battery voltage", "unit": "V"},
                {"name": "cpu_temp", "description": "CPU temperature", "unit": "°C"}
            ],
            "causes_relationships": [
                {"failure_mode": "Dead Battery", "observation": "No Sound"},
                {"failure_mode": "Dead Battery", "observation": "No Display"},
                {"failure_mode": "Speaker Broken", "observation": "No Sound"},
                {"failure_mode": "Speaker Broken", "observation": "Buzz or Hiss"},
                {"failure_mode": "Software Crash", "observation": "No Display"}
            ],
            "evidence_relationships": [
                {"observation": "No Sound", "failure_mode": "Dead Battery", 
                 "when_true_strength": "suggests", "when_false_strength": "rules_out"},
                {"observation": "No Display", "failure_mode": "Dead Battery", 
                 "when_true_strength": "suggests", "when_false_strength": "inconclusive"},
                {"observation": "No Sound", "failure_mode": "Speaker Broken", 
                 "when_true_strength": "suggests", "when_false_strength": "rules_out"},
                {"observation": "Buzz or Hiss", "failure_mode": "Speaker Broken", 
                 "when_true_strength": "confirms", "when_false_strength": "inconclusive"},
                {"observation": "No Display", "failure_mode": "Software Crash", 
                 "when_true_strength": "suggests", "when_false_strength": "rules_out"},
                {"sensor": "battery_voltage", "failure_mode": "Dead Battery", 
                 "when_true_strength": "confirms", "when_false_strength": "rules_out",
                 "operator": "<", "threshold": 3.5},
                {"sensor": "cpu_temp", "failure_mode": "Software Crash", 
                 "when_true_strength": "suggests", "when_false_strength": "inconclusive",
                 "operator": ">", "threshold": 80}
            ]
        }
        
        # Load the test graph
        self._load_test_graph(test_graph)
        
        # Scan the graph to identify inputs
        self.truth_table.scan_graph()
        
        # Generate a focused truth table varying only specific inputs
        results = self.truth_table.run_truth_table(
            vary_observations=["No Sound"],
            fixed_observations={"No Display": True},
            vary_sensors=["battery_voltage"],
            fixed_sensor_values={"cpu_temp": 85}
        )
        
        # Verify results format
        table_output = self.truth_table.format_results(results, format='table')
        
        # Check that fixed values are present in all rows
        self.assertIn("No Display", table_output)
        self.assertIn("cpu_temp", table_output)
        
        # Should have results with "Dead Battery" when voltage is low
        has_dead_battery = False
        for result in results:
            for diagnosis in result.diagnosed_failure_modes:
                if diagnosis["failure_mode"] == "Dead Battery" and diagnosis["confidence"] == "confirms":
                    voltage = result.inputs["sensor_values"].get("battery_voltage")
                    if voltage is not None and voltage < 3.5:
                        has_dead_battery = True
        
        self.assertTrue(has_dead_battery, "Should diagnose Dead Battery when voltage is low")
        
        # Check surprises
        has_surprises = self.truth_table.check_for_surprises(results)
        
        # Debug: print the surprise results
        for i, result in enumerate(results):
            if result.has_surprise:
                print(f"\nSurprise in result {i}:")
                print(f"  Observations: {result.inputs['observations']}")
                print(f"  Sensor values: {result.inputs['sensor_values']}")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
        
        self.assertFalse(has_surprises, "Should not have surprises for unregistered expectations")
    
    def _load_test_graph(self, setup_data):
        """Helper method to load a test graph from setup data."""
        # Clear existing data
        self.connection.clean()
        
        # Create failure modes using proper models
        failure_modes = {}
        for fm_data in setup_data.get("failure_modes", []):
            fm = FailureMode(
                name=fm_data["name"],
                description=fm_data.get("description", "")
            )
            # Create node and store with name as key
            result = self.connection.run_query(
                """
                CREATE (n:FailureMode {name: $name, description: $description})
                RETURN elementId(n) as node_id
                """,
                {
                    "name": fm.name,
                    "description": fm.description
                }
            )
            fm.id = result[0]["node_id"]
            failure_modes[fm.name] = fm
        
        # Create observations using proper models
        observations = {}
        for obs_data in setup_data.get("observations", []):
            obs = Observation(
                name=obs_data["name"],
                description=obs_data.get("description", "")
            )
            # Create node and store with name as key
            result = self.connection.run_query(
                """
                CREATE (n:Observation {name: $name, description: $description})
                RETURN elementId(n) as node_id
                """,
                {
                    "name": obs.name,
                    "description": obs.description
                }
            )
            obs.id = result[0]["node_id"]
            observations[obs.name] = obs
            
        # Create sensor readings using proper models
        sensors = {}
        for sensor_data in setup_data.get("sensor_readings", []):
            sensor = SensorReading(
                name=sensor_data["name"],
                description=sensor_data.get("description", ""),
                unit=sensor_data.get("unit", "")
            )
            # Create node and store with name as key
            result = self.connection.run_query(
                """
                CREATE (n:SensorReading {
                    name: $name, 
                    description: $description,
                    unit: $unit
                })
                RETURN elementId(n) as node_id
                """,
                {
                    "name": sensor.name,
                    "description": sensor.description,
                    "unit": sensor.unit
                }
            )
            sensor.id = result[0]["node_id"]
            sensors[sensor.name] = sensor
            
        # Create CAUSES relationships
        for rel_data in setup_data.get("causes_relationships", []):
            causes_link = CausesLink(
                source=failure_modes[rel_data["failure_mode"]],
                dest=observations[rel_data["observation"]]
            )
            self.connection.run_query("""
                MATCH (source), (dest)
                WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
                MERGE (source)-[:CAUSES]->(dest)
            """, {
                "source_id": causes_link.source.id,
                "dest_id": causes_link.dest.id
            })
            
        # Create EVIDENCE_FOR relationships
        for rel_data in setup_data.get("evidence_relationships", []):
            # Handle observation evidence
            if "observation" in rel_data:
                evidence_link = EvidenceLink(
                    source=observations[rel_data["observation"]],
                    dest=failure_modes[rel_data["failure_mode"]],
                    when_true_strength=rel_data["when_true_strength"],
                    when_false_strength=rel_data["when_false_strength"]
                )
                self.connection.run_query("""
                    MATCH (source), (dest)
                    WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
                    MERGE (source)-[:EVIDENCE_FOR {
                        when_true_strength: $when_true_strength,
                        when_false_strength: $when_false_strength
                    }]->(dest)
                """, {
                    "source_id": evidence_link.source.id,
                    "dest_id": evidence_link.dest.id,
                    "when_true_strength": evidence_link.when_true_strength,
                    "when_false_strength": evidence_link.when_false_strength
                })
            
            # Handle sensor evidence
            if "sensor" in rel_data:
                evidence_link = EvidenceLink(
                    source=sensors[rel_data["sensor"]],
                    dest=failure_modes[rel_data["failure_mode"]],
                    when_true_strength=rel_data["when_true_strength"],
                    when_false_strength=rel_data["when_false_strength"],
                    operator=rel_data["operator"],
                    threshold=rel_data["threshold"]
                )
                self.connection.run_query("""
                    MATCH (source), (dest)
                    WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
                    MERGE (source)-[:EVIDENCE_FOR {
                        when_true_strength: $when_true_strength,
                        when_false_strength: $when_false_strength,
                        operator: $operator,
                        threshold: $threshold
                    }]->(dest)
                """, {
                    "source_id": evidence_link.source.id,
                    "dest_id": evidence_link.dest.id,
                    "when_true_strength": evidence_link.when_true_strength,
                    "when_false_strength": evidence_link.when_false_strength,
                    "operator": evidence_link.operator,
                    "threshold": evidence_link.threshold
                })


if __name__ == '__main__':
    if not is_neo4j_running():
        print("Neo4j is not running. Please start Neo4j before running this test.")
        sys.exit(1)
    unittest.main() 
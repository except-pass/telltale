"""Example test using the new Truth Table feature."""

import unittest
import sys
import os
from telltale.tests.test_utils import Neo4jTestCase, is_neo4j_running
from telltale.core.diagnostic import DiagnosticEngine
from telltale.core.truth_table import TruthTable
from telltale.core.models import FailureMode, Observation, SensorReading, CausesLink, EvidenceLink


class ExampleTruthTableTest(Neo4jTestCase):
    """Example test case using the new truth table feature."""
    
    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        self.diagnostic_engine = DiagnosticEngine()
        self.diagnostic_engine.db = self.connection
        self.truth_table = TruthTable(self.diagnostic_engine)
    
    def tearDown(self):
        """Clean up after each test."""
        super().tearDown()
    
    def test_battery_and_speaker_graph(self):
        """Test a simple graph with battery voltage and speaker diagnostics."""
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
        
        # Register expected outcomes for specific test cases
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
        
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": ["Buzz or Hiss"],
                "sensor_values": {}
            },
            "expected": [
                {
                    "failure_mode": "Speaker Broken",
                    "confidence": "confirms"
                }
            ]
        })
        
        # Add an expectation for the third case that will create a "surprise"
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": ["No Sound", "Buzz or Hiss"],
                "sensor_values": {"battery_voltage": 4.0}
            },
            "expected": [
                {
                    "failure_mode": "Speaker Broken",
                    "confidence": "suggests"  # This is different from actual 'confirms'
                }
            ]
        })
        
        # Run a specific subset of test cases
        test_cases = [
            {
                "observations": ["No Sound"],
                "sensor_values": {"battery_voltage": 3.0}
            },
            {
                "observations": ["Buzz or Hiss"],
                "sensor_values": {}
            },
            {
                "observations": ["No Sound", "Buzz or Hiss"],
                "sensor_values": {"battery_voltage": 4.0}
            }
        ]
        
        results = self.truth_table.run_truth_table(test_cases=test_cases)
        
        # Print the results
        print(self.truth_table.format_results(results))
        
        # Assert that there are no surprises for the first two test cases
        self.assertFalse(any(r.has_surprise for r in results[:2]))
        
        # For the third test case, we expect an unexpected result
        # Specifically, we expect the speaker broken to be "suggests" instead of "confirms"
        third_case_result = results[2]
        self.assertTrue(third_case_result.has_surprise, "Third test case should have unexpected results")
        
        # Verify the specific unexpected result we want
        speaker_broken_result = next(
            (r for r in third_case_result.diagnosed_failure_modes if r["failure_mode"] == "Speaker Broken"),
            None
        )
        self.assertIsNotNone(speaker_broken_result, "Should have a result for Speaker Broken")
        self.assertEqual(
            speaker_broken_result["confidence"],
            "confirms",  # We expect this to be "confirms" in the actual result
            "Speaker Broken should have 'confirms' confidence in the third test case"
        )
        
        # Generate and run the full truth table
        full_results = self.truth_table.run_truth_table(
            vary_observations=["No Sound", "Buzz or Hiss"],
            vary_sensors=["battery_voltage"]
        )
        
        # Print all test cases that were generated
        print("\nAll generated test cases:")
        for i, result in enumerate(full_results):
            obs_str = ", ".join(result.inputs["observations"]) if result.inputs["observations"] else "None"
            sensor_str = str(result.inputs["sensor_values"])
            print(f"Case {i}: Observations: {obs_str}, Sensors: {sensor_str}")
        
        # Register some expected outcomes for the full truth table - some deliberately incorrect
        # Case 1: No observations, battery below threshold
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": [],
                "sensor_values": {"battery_voltage": 3.4}
            },
            "expected": [
                {
                    "failure_mode": "Speaker Broken", 
                    "confidence": "suggests"  # Incorrect - should be empty list
                }
            ]
        })
        
        # Case 2: Both observations present, battery below threshold
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": ["No Sound", "Buzz or Hiss"],
                "sensor_values": {"battery_voltage": 3.4}
            },
            "expected": [
                {
                    "failure_mode": "Dead Battery", 
                    "confidence": "suggests"  # Incorrect - should be confirms
                },
                {
                    "failure_mode": "Speaker Broken", 
                    "confidence": "suggests"  # Incorrect - should be confirms
                }
            ]
        })
        
        # Case 3: Just No Sound, battery below threshold
        self.truth_table.register_expected_outcome({
            "inputs": {
                "observations": ["No Sound"],
                "sensor_values": {"battery_voltage": 3.4}
            },
            "expected": [
                {
                    "failure_mode": "Speaker Broken", 
                    "confidence": "confirms"  # Incorrect - should be suggests
                }
            ]
        })
        
        # Re-run full truth table after registering expected outcomes
        full_results = self.truth_table.run_truth_table(
            vary_observations=["No Sound", "Buzz or Hiss"],
            vary_sensors=["battery_voltage"]
        )
        
        # Print diagnostic information for full truth table
        print("\nDiagnostic Information for Full Truth Table:")
        for i, result in enumerate(full_results):
            # Generate values around thresholds: threshold - 0.1 => 3.4, threshold + 0.1 => 3.6
            battery_value = result.inputs["sensor_values"].get("battery_voltage")
            
            # Check if empty observations with battery value below threshold
            if (not result.inputs["observations"] and battery_value == 3.4):
                print(f"Case {i} - Empty observations with battery 3.4V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
            
            # Check if empty observations with battery value above threshold
            elif (not result.inputs["observations"] and battery_value == 3.6):
                print(f"Case {i} - Empty observations with battery 3.6V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
            
            # Check case with both observations and battery below threshold
            elif ("No Sound" in result.inputs["observations"] and 
                  "Buzz or Hiss" in result.inputs["observations"] and
                  battery_value == 3.4):
                print(f"Case {i} - Both observations with battery 3.4V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
            
            # Check case with both observations and battery above threshold
            elif ("No Sound" in result.inputs["observations"] and 
                  "Buzz or Hiss" in result.inputs["observations"] and
                  battery_value == 3.6):
                print(f"Case {i} - Both observations with battery 3.6V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
            
            # Check case with just No Sound and battery below threshold
            elif ("No Sound" in result.inputs["observations"] and 
                  "Buzz or Hiss" not in result.inputs["observations"] and
                  battery_value == 3.4):
                print(f"Case {i} - No Sound only with battery 3.4V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
            
            # Check case with just No Sound and battery above threshold
            elif ("No Sound" in result.inputs["observations"] and 
                  "Buzz or Hiss" not in result.inputs["observations"] and
                  battery_value == 3.6):
                print(f"Case {i} - No Sound only with battery 3.6V:")
                print(f"  Diagnosed: {result.diagnosed_failure_modes}")
                print(f"  Expected: {result.expected_failure_modes}")
                print(f"  Unexpected: {result.unexpected_results}")
                print(f"  Missing: {result.missing_results}")
                print(f"  Has surprise: {result.has_surprise}")
        
        # Export to HTML for visual inspection
        html_output = self.truth_table.format_results(full_results, format='html')
        with open('truth_table_results.html', 'w') as f:
            f.write(html_output)
    
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
    #if not is_neo4j_running():
    #    print("Neo4j is not running. Please start Neo4j before running this test.")
    #    sys.exit(1)
    unittest.main() 
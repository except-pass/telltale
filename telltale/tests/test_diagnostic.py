"""Tests for the diagnostic engine."""

from telltale.core.diagnostic import DiagnosticEngine
from telltale.core.models import (
    EvidenceStrength, 
    ComparisonOperator,
    FailureMode,
    Observation,
    SensorReading,
    EvidenceLink,
    CausesLink
)
from telltale.core.database import TestDatabase
from telltale.tests.test_utils import Neo4jTestCase


class TestDiagnosticEngine(Neo4jTestCase):
    """Test cases for the DiagnosticEngine class."""

    def setUp(self):
        """Set up test environment."""
        # Use the Neo4jTestCase setUp first
        super().setUp()
        
        # Create diagnostic engine with our connection
        self.engine = DiagnosticEngine()
        self.engine.db = self.connection
        
        # Create test data
        self.create_test_data()

    def create_test_data(self):
        """Create test data for diagnosing a dead battery and device off scenarios."""
        # Create failure mode nodes
        dead_battery = FailureMode(name="Dead Battery")
        self.connection.save_node(dead_battery)
        
        device_off = FailureMode(name="Device Off")
        self.connection.save_node(device_off)
        
        # Create observation node
        observation = Observation(name="No Music")
        self.connection.save_node(observation)
        
        # Create sensor reading nodes
        battery_sensor = SensorReading(name="battery_voltage")
        self.connection.save_node(battery_sensor)
        
        switch_sensor = SensorReading(name="switch_status")
        self.connection.save_node(switch_sensor)
        
        # Create CAUSES relationships - both failure modes cause "No Music"
        causes_rel1 = CausesLink(source=dead_battery, dest=observation)
        self.connection.save_relationship(causes_rel1)
        
        causes_rel2 = CausesLink(source=device_off, dest=observation)
        self.connection.save_relationship(causes_rel2)
        
        # Create EVIDENCE_FOR relationship from observation to failure modes
        obs_evidence1 = EvidenceLink(
            source=observation,
            dest=dead_battery,
            when_true_strength=EvidenceStrength.CONFIRMS,
            when_false_strength=EvidenceStrength.INCONCLUSIVE
        )
        self.connection.save_relationship(obs_evidence1)
        
        obs_evidence2 = EvidenceLink(
            source=observation,
            dest=device_off,
            when_true_strength=EvidenceStrength.CONFIRMS,
            when_false_strength=EvidenceStrength.INCONCLUSIVE
        )
        self.connection.save_relationship(obs_evidence2)
        
        # Create EVIDENCE_FOR relationship from battery_voltage to Dead Battery
        battery_evidence = EvidenceLink(
            source=battery_sensor,
            dest=dead_battery,
            when_true_strength=EvidenceStrength.CONFIRMS,
            when_false_strength=EvidenceStrength.RULES_OUT,
            operator=ComparisonOperator.LESS_THAN,
            threshold=4.0
        )
        self.connection.save_relationship(battery_evidence)
        
        # Create EVIDENCE_FOR relationship from switch_status to Device Off
        # 0 = Off, 1 = On
        switch_evidence = EvidenceLink(
            source=switch_sensor,
            dest=device_off,
            when_true_strength=EvidenceStrength.CONFIRMS,
            when_false_strength=EvidenceStrength.RULES_OUT,
            operator=ComparisonOperator.EQUALS,
            threshold=0
        )
        self.connection.save_relationship(switch_evidence)

    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, 'engine'):
            # Remove engine's reference to the connection
            if hasattr(self.engine, 'db'):
                del self.engine.db
        
        # Use the Neo4jTestCase tearDown to clean up the connection
        super().tearDown()

    def test_diagnose_dead_battery(self):
        """Test diagnosing a dead battery scenario."""
        observations = ["No Music"]
        sensor_readings = {"battery_voltage": 3.5}  # Below threshold of 4.0
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Verify results
        self.assertGreater(len(results), 0)
        dead_battery_result = next(r for r in results if r.failure_mode == "Dead Battery")
        self.assertEqual(dead_battery_result.confidence, EvidenceStrength.CONFIRMS)
        self.assertIn("battery_voltage", dead_battery_result.supporting_evidence)

    def test_diagnose_battery_not_dead(self):
        """Test diagnosing when battery is not dead."""
        observations = ["No Music"]
        sensor_readings = {"battery_voltage": 12.0}  # Above threshold of 4.0
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Verify results
        self.assertGreater(len(results), 0)
        
        # Dead Battery should not be in the results since it's ruled out by good battery voltage
        dead_battery_failure_modes = [r for r in results if r.failure_mode == "Dead Battery"]
        self.assertEqual(len(dead_battery_failure_modes), 0, 
                        "Dead Battery should not be in results when battery voltage is good")

    def test_diagnose_inconclusive_evidence(self):
        """Test diagnosing when evidence is inconclusive."""
        # Create new nodes for this specific test
        inconclusive_failure = FailureMode(name="Inconclusive Failure")
        self.connection.save_node(inconclusive_failure)
        
        test_observation = Observation(name="Test Observation")
        self.connection.save_node(test_observation)
        
        # Create CAUSES relationship
        causes_rel = CausesLink(source=inconclusive_failure, dest=test_observation)
        self.connection.save_relationship(causes_rel)
        
        # Create EVIDENCE_FOR relationship with INCONCLUSIVE strength
        evidence_link = EvidenceLink(
            source=test_observation,
            dest=inconclusive_failure,
            when_true_strength=EvidenceStrength.INCONCLUSIVE,
            when_false_strength=EvidenceStrength.INCONCLUSIVE
        )
        self.connection.save_relationship(evidence_link)
        
        # Run the test with the observation
        observations = ["Test Observation"]
        results = self.engine.diagnose(observations, {})
        
        # Verify results
        self.assertGreater(len(results), 0)
        inconclusive_result = next(r for r in results if r.failure_mode == "Inconclusive Failure")
        
        # Confidence should be INCONCLUSIVE because that's what we set in the evidence link
        self.assertEqual(inconclusive_result.confidence, EvidenceStrength.INCONCLUSIVE)
        
        # The observation should be in supporting evidence
        self.assertIn("Test Observation", inconclusive_result.supporting_evidence)
        
        # No contradicting evidence
        self.assertEqual(len(inconclusive_result.contradicting_evidence), 0)

    def test_diagnose_device_off(self):
        """Test diagnosing when the device is off."""
        observations = ["No Music"]
        sensor_readings = {
            "battery_voltage": 12.0,  # Good battery
            "switch_status": 0        # Switch is off (0 = Off)
        }
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Verify results
        self.assertGreater(len(results), 0)
        
        # Find the Device Off result
        device_off_result = next(r for r in results if r.failure_mode == "Device Off")
        
        # Check that the engine correctly identified Device Off as CONFIRMS
        self.assertEqual(device_off_result.confidence, EvidenceStrength.CONFIRMS)
        self.assertIn("switch_status", device_off_result.supporting_evidence)
        
        # Dead Battery should not be in the results since good battery voltage rules it out
        dead_battery_results = [r for r in results if r.failure_mode == "Dead Battery"]
        self.assertEqual(len(dead_battery_results), 0,
                         "Dead Battery should not be in results when battery voltage is good")

    def test_diagnose_multiple_failure_modes(self):
        """Test diagnosing when both failure modes are possible."""
        observations = ["No Music"]
        sensor_readings = {
            "battery_voltage": 3.0,  # Low battery
            "switch_status": 0       # Switch is off
        }
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Verify results
        self.assertGreater(len(results), 0)
        
        # Both failure modes should be confirmed
        dead_battery_result = next(r for r in results if r.failure_mode == "Dead Battery")
        self.assertEqual(dead_battery_result.confidence, EvidenceStrength.CONFIRMS)
        
        device_off_result = next(r for r in results if r.failure_mode == "Device Off")
        self.assertEqual(device_off_result.confidence, EvidenceStrength.CONFIRMS)
        
        # Check that both have their respective sensor readings as supporting evidence
        self.assertIn("battery_voltage", dead_battery_result.supporting_evidence)
        self.assertIn("switch_status", device_off_result.supporting_evidence)

    def test_device_on_rules_out_device_off(self):
        """Test that when switch is on, Device Off is ruled out."""
        observations = ["No Music"]
        sensor_readings = {
            "battery_voltage": 12.0,  # Good battery
            "switch_status": 1        # Switch is on (1 = On)
        }
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Both failure modes should be ruled out now:
        # - Device Off is ruled out by switch being on
        # - Dead Battery is ruled out by good battery voltage
        # So results should be empty
        self.assertEqual(len(results), 0, "No results should be returned when all failure modes are ruled out")

    def test_rules_out_specific_failure_modes(self):
        """Test that only relevant failure modes are ruled out."""
        # Create a third failure mode that isn't ruled out by our sensor readings
        speaker_broken = FailureMode(name="Speaker Broken")
        self.connection.save_node(speaker_broken)
        
        # Create a new observation for this test
        observation = Observation(name="No Music")
        self.connection.save_node(observation)
        
        # Create CAUSES relationship to No Music
        causes_rel = CausesLink(source=speaker_broken, dest=observation)
        self.connection.save_relationship(causes_rel)
        
        # Create EVIDENCE_FOR relationship from observation to speaker_broken
        evidence_link = EvidenceLink(
            source=observation,
            dest=speaker_broken,
            when_true_strength=EvidenceStrength.SUGGESTS,
            when_false_strength=EvidenceStrength.INCONCLUSIVE
        )
        self.connection.save_relationship(evidence_link)
        
        # Test with observation and sensors that rule out Dead Battery and Device Off
        observations = ["No Music"]
        sensor_readings = {
            "battery_voltage": 12.0,  # Good battery - rules out Dead Battery
            "switch_status": 1        # Switch is on - rules out Device Off
        }
        
        results = self.engine.diagnose(observations, sensor_readings)
        
        # Verify only Speaker Broken remains in results
        self.assertEqual(len(results), 1, "Only one failure mode should remain")
        self.assertEqual(results[0].failure_mode, "Speaker Broken")
        self.assertEqual(results[0].confidence, EvidenceStrength.SUGGESTS)


if __name__ == "__main__":
    import unittest
    unittest.main() 
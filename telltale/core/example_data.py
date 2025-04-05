"""Module containing example diagnostic scenarios for demonstration and testing."""

import json
import logging
from typing import Dict, Any, List

from telltale.core.models import (
    FailureMode, Observation, SensorReading,
    CausesLink, EvidenceLink, EvidenceStrength, ComparisonOperator, Node
)

logger = logging.getLogger(__name__)

class ExampleScenarios:
    """Class containing methods to create example diagnostic scenarios."""
    
    def __init__(self, db):
        """Initialize with a database connection."""
        self.db = db

    def create_node(self, node: Node) -> Node:
        """Create a node in the database and update its ID.
        
        Args:
            node: The node to create
            
        Returns:
            The node with its ID updated
        """
        # Build query dynamically based on non-null properties
        props = {
            "name": node.name,
            "description": node.description
        }
        
        # Add additional properties for SensorReading
        if isinstance(node, SensorReading):
            if node.unit:
                props["unit"] = node.unit
            if node.value_descriptions:
                props["value_descriptions"] = node.value_descriptions
        
        # Create property string for query
        prop_str = ", ".join(f"{k}: ${k}" for k in props.keys())
        
        # Get node type from the class name
        node_type = node.__class__.__name__
        
        result = self.db.run_query(
            f"""
            MERGE (n:{node_type} {{{prop_str}}})
            RETURN elementId(n) as node_id
            """,
            props
        )
        node.id = result[0]["node_id"]
        return node

    def create_relationship(self, rel: CausesLink | EvidenceLink) -> None:
        """Create a relationship in the database.
        
        Args:
            rel: The relationship to create
        """
        # Ensure both nodes have IDs
        if not rel.has_valid_ids():
            raise ValueError("Both source and dest nodes must have IDs")
        
        if isinstance(rel, CausesLink):
            self.db.run_query(
                """
                MATCH (source), (dest)
                WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
                MERGE (source)-[:CAUSES]->(dest)
                """,
                {"source_id": rel.get_source_id(), "dest_id": rel.get_dest_id()}
            )
        elif isinstance(rel, EvidenceLink):
            # Build relationship properties
            rel_props = {
                "when_true_strength": rel.when_true_strength.value,
                "when_false_strength": rel.when_false_strength.value,
                "name": rel.name
            }
            
            if rel.operator:
                rel_props["operator"] = rel.operator.value
            
            if rel.threshold is not None:
                rel_props["threshold"] = rel.threshold
            
            # Create property string for query
            prop_str = ", ".join(f"{k}: ${k}" for k in rel_props.keys())
            
            self.db.run_query(
                f"""
                MATCH (source), (dest)
                WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
                MERGE (source)-[r:EVIDENCE_FOR {{{prop_str}}}]->(dest)
                """,
                {
                    "source_id": rel.get_source_id(),
                    "dest_id": rel.get_dest_id(),
                    **rel_props
                }
            )

    def add_basic_scenarios(self) -> None:
        """Add the basic diagnostic scenarios (dead battery, mute mode, etc)."""
        # Create FailureMode nodes and get their IDs
        failure_modes = [
            FailureMode(name="Dead Battery", description="Battery voltage is too low to power the device"),
            FailureMode(name="Mute Mode", description="Device is in mute mode"),
            FailureMode(name="Speaker Broken", description="Speaker hardware is damaged or disconnected"),
            FailureMode(name="Device Off", description="Device is powered off")
        ]
        
        # Create nodes in DB and update with IDs
        failure_modes = [self.create_node(fm) for fm in failure_modes]
        
        # Create Observation nodes and get their IDs
        observations = [
            Observation(name="No Music", description="No sound is playing from the device"),
            Observation(name="Buzz or Hiss", description="Unwanted noise coming from the speaker")
        ]
        
        observations = [self.create_node(obs) for obs in observations]
        
        # Create SensorReading nodes and get their IDs
        sensor_readings = [
            SensorReading(name="battery_voltage", unit="V", description="Current battery voltage"),
            SensorReading(name="switch_status", unit="enum", description="Position of the mode switch",
                         value_descriptions='{"0": "OFF", "1": "ON", "2": "MUTE"}')
        ]
        
        sensor_readings = [self.create_node(sr) for sr in sensor_readings]
        
        # Create CAUSES relationships
        causes_links = [
            CausesLink(
                source=failure_modes[0],  # Dead Battery
                dest=observations[0]  # No Music
            ),
            CausesLink(
                source=failure_modes[1],  # Mute Mode
                dest=observations[0]  # No Music
            ),
            CausesLink(
                source=failure_modes[2],  # Speaker Broken
                dest=observations[0]  # No Music
            ),
            CausesLink(
                source=failure_modes[2],  # Speaker Broken
                dest=observations[1]  # Buzz or Hiss
            ),
            CausesLink(
                source=failure_modes[3],  # Device Off
                dest=observations[0]  # No Music
            )
        ]
        
        for link in causes_links:
            self.create_relationship(link)
        
        # Create EVIDENCE_FOR relationships
        evidence_links = [
            EvidenceLink(
                source=sensor_readings[0],  # battery_voltage
                dest=failure_modes[0],  # Dead Battery
                when_true_strength=EvidenceStrength.CONFIRMS,
                when_false_strength=EvidenceStrength.RULES_OUT,
                operator=ComparisonOperator.LESS_THAN,
                threshold=4.0,
                name="Low battery voltage"
            ),
            EvidenceLink(
                source=sensor_readings[1],  # switch_status
                dest=failure_modes[3],  # Device Off
                when_true_strength=EvidenceStrength.CONFIRMS,
                when_false_strength=EvidenceStrength.SUGGESTS_AGAINST,
                operator=ComparisonOperator.EQUALS,
                threshold=0,  # OFF state
                name="Switch position indicates device state"
            ),
            EvidenceLink(
                source=sensor_readings[1],  # switch_status
                dest=failure_modes[1],  # Mute Mode
                when_true_strength=EvidenceStrength.CONFIRMS,
                when_false_strength=EvidenceStrength.SUGGESTS_AGAINST,
                operator=ComparisonOperator.EQUALS,
                threshold=2,  # MUTE state
                name="Switch position indicates mute state"
            ),
            EvidenceLink(
                source=observations[1],  # Buzz or Hiss
                dest=failure_modes[2],  # Speaker Broken
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.INCONCLUSIVE,
                name="Buzzing or hissing sound"
            ),
            EvidenceLink(
                source=observations[0],  # No Music
                dest=failure_modes[0],  # Dead Battery
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.RULES_OUT,
                name="No music playing"
            ),
            EvidenceLink(
                source=observations[0],  # No Music
                dest=failure_modes[1],  # Mute Mode
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.INCONCLUSIVE,
                name="No music playing"
            ),
            EvidenceLink(
                source=observations[0],  # No Music
                dest=failure_modes[3],  # Device Off
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.RULES_OUT,
                name="No music playing"
            )
        ]
        
        for link in evidence_links:
            self.create_relationship(link)

        logger.info("Basic scenarios have been added successfully")

    def add_broken_speaker_wire_scenario(self) -> None:
        """Add the broken speaker wire diagnostic scenario."""
        # Create nodes
        failure_mode = self.create_node(
            FailureMode(name="Broken Speaker Wire", 
                       description="The wire connecting the speaker to the circuit board is broken")
        )
        
        observations = [
            self.create_node(Observation(name="Intermittent Sound", 
                                       description="Sound cuts in and out when the toy is moved")),
            self.create_node(Observation(name="Sound Only on One Side", 
                                       description="Sound only comes from one speaker")),
            self.create_node(Observation(name="No Music", 
                                       description="No sound is playing from the device"))
        ]
        
        sensor_readings = [
            self.create_node(SensorReading(name="speaker_impedance", 
                                         unit="ohm",
                                         description="Measured impedance of the speaker circuit")),
            self.create_node(SensorReading(name="speaker_continuity", 
                                         unit="bool",
                                         description="Continuity test result for speaker wiring",
                                         value_descriptions='{"0": "No Continuity", "1": "Continuity OK"}'))
        ]
        
        # Create CAUSES relationships
        causes_links = [
            CausesLink(source=failure_mode, dest=observations[0]),  # Intermittent Sound
            CausesLink(source=failure_mode, dest=observations[1]),  # Sound Only on One Side
            CausesLink(source=failure_mode, dest=observations[2])   # No Music
        ]
        
        for link in causes_links:
            self.create_relationship(link)
        
        # Create EVIDENCE_FOR relationships
        evidence_links = [
            EvidenceLink(
                source=sensor_readings[0],  # speaker_impedance
                dest=failure_mode,
                when_true_strength=EvidenceStrength.CONFIRMS,
                when_false_strength=EvidenceStrength.SUGGESTS_AGAINST,
                operator=ComparisonOperator.GREATER_THAN,
                threshold=1000,  # Very high impedance indicates broken wire
                name="High speaker impedance"
            ),
            EvidenceLink(
                source=sensor_readings[1],  # speaker_continuity
                dest=failure_mode,
                when_true_strength=EvidenceStrength.RULES_OUT,
                when_false_strength=EvidenceStrength.CONFIRMS,
                operator=ComparisonOperator.EQUALS,
                threshold=1,  # 1 means continuity is OK
                name="Speaker wire continuity test"
            ),
            EvidenceLink(
                source=observations[0],  # Intermittent Sound
                dest=failure_mode,
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.INCONCLUSIVE,
                name="Sound cuts in and out"
            ),
            EvidenceLink(
                source=observations[1],  # Sound Only on One Side
                dest=failure_mode,
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.INCONCLUSIVE,
                name="Sound only from one speaker"
            ),
            EvidenceLink(
                source=observations[2],  # No Music
                dest=failure_mode,
                when_true_strength=EvidenceStrength.SUGGESTS,
                when_false_strength=EvidenceStrength.RULES_OUT,
                name="No music playing"
            )
        ]
        
        for link in evidence_links:
            self.create_relationship(link)
        
        logger.info("Broken speaker wire scenario has been added successfully")


if __name__ == "__main__":
    from telltale.core.database import Neo4jConnection
    db = Neo4jConnection()
    example_scenarios = ExampleScenarios(db)
    example_scenarios.add_basic_scenarios()
    example_scenarios.add_broken_speaker_wire_scenario()
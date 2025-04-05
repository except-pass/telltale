import streamlit as st
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
import pandas as pd
import numpy as np

from telltale.core.database import Neo4jConnection
from telltale.core.diagnostic import DiagnosticEngine
from telltale.core.models import (
    FailureMode, 
    Observation, 
    SensorReading, 
    EvidenceStrength, 
    ComparisonOperator,
    DiagnosticResult,
    TestRecommendation,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TelltaleUI:
    """Streamlit UI for the Telltale diagnostic assistant."""

    def __init__(self):
        """Initialize the UI and connect to Neo4j."""
        self.db = Neo4jConnection()
        self.engine = DiagnosticEngine()
        
        # Initialize session state variables if they don't exist
        if "observations" not in st.session_state:
            st.session_state.observations = {}
        if "sensor_readings" not in st.session_state:
            st.session_state.sensor_readings = {}
        if "diagnosis_results" not in st.session_state:
            st.session_state.diagnosis_results = []
        if "test_recommendations" not in st.session_state:
            st.session_state.test_recommendations = []
        
        # Connect to database and load graph data
        self.db.connect()
        self.load_graph_data()

    def load_graph_data(self):
        """Load all graph data into memory."""
        # Fetch all observations
        observations_query = "MATCH (o:Observation) RETURN o.name as name"
        observations_result = self.db.run_query(observations_query)
        self.all_observations = [row["name"] for row in observations_result]
        
        # Fetch all sensor readings with value descriptions
        sensors_query = """
        MATCH (s:SensorReading) 
        RETURN s.name as name, s.value_descriptions as value_descriptions
        """
        sensors_result = self.db.run_query(sensors_query)
        self.all_sensors = []
        self.sensor_descriptions = {}
        for row in sensors_result:
            self.all_sensors.append(row["name"])
            if row["value_descriptions"]:
                # Parse the JSON string into a dictionary
                try:
                    import json
                    if isinstance(row["value_descriptions"], str):
                        desc_dict = json.loads(row["value_descriptions"])
                        # Convert string keys to integers for numeric values
                        self.sensor_descriptions[row["name"]] = {
                            int(k): v for k, v in desc_dict.items()
                        }
                    else:
                        self.sensor_descriptions[row["name"]] = row["value_descriptions"]
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Failed to parse value_descriptions for sensor {row['name']}")
                    self.sensor_descriptions[row["name"]] = {}
        
        # Fetch all failure modes
        failure_modes_query = "MATCH (f:FailureMode) RETURN f.name as name"
        failure_modes_result = self.db.run_query(failure_modes_query)
        self.all_failure_modes = [row["name"] for row in failure_modes_result]
        
        # Fetch sensor thresholds and operators for UI
        sensor_thresholds_query = """
        MATCH (s:SensorReading)-[r:EVIDENCE_FOR]->(f:FailureMode)
        WHERE r.threshold IS NOT NULL
        RETURN s.name as sensor, r.operator as operator, r.threshold as threshold
        """
        sensor_thresholds_result = self.db.run_query(sensor_thresholds_query)
        
        # Create a mapping of sensor names to their thresholds and operators
        self.sensor_metadata = {}
        for row in sensor_thresholds_result:
            sensor = row["sensor"]
            if sensor not in self.sensor_metadata:
                self.sensor_metadata[sensor] = []
            self.sensor_metadata[sensor].append({
                "operator": row["operator"],
                "threshold": row["threshold"]
            })
    
    def render_observation_controls(self):
        """Render UI controls for observations."""
        st.subheader("📝 Observations")
        st.markdown("Mark each observation as present, absent, or unknown:")
        
        for observation in self.all_observations:
            col1, col2 = st.columns([3, 5])
            with col1:
                st.markdown(f"**{observation}**")
            
            with col2:
                observation_key = f"obs_{observation}"
                options = ["Unknown", "Present", "Absent"]
                selected = st.radio(
                    f"Status of '{observation}'",
                    options,
                    key=observation_key,
                    label_visibility="collapsed",
                    horizontal=True,
                    index=0
                )
                
                # Update session state
                if selected == "Present":
                    st.session_state.observations[observation] = True
                elif selected == "Absent":
                    st.session_state.observations[observation] = False
                else:  # Unknown
                    if observation in st.session_state.observations:
                        del st.session_state.observations[observation]
            
            st.divider()
    
    def render_sensor_controls(self):
        """Render UI controls for sensor readings."""
        st.subheader("📊 Sensor Readings")
        st.markdown("Enter values for the available sensors:")
        
        for sensor in self.all_sensors:
            col1, col2 = st.columns([3, 5])
            with col1:
                st.markdown(f"**{sensor}**")
                
                # Show value descriptions if available
                if sensor in self.sensor_descriptions:
                    desc_text = ", ".join([f"{v}: {k}" for k, v in self.sensor_descriptions[sensor].items()])
                    st.caption(f"Values: {desc_text}")
                # Show threshold hints if available
                elif sensor in self.sensor_metadata:
                    hints = ", ".join([
                        f"{meta['operator']} {meta['threshold']}" 
                        for meta in self.sensor_metadata[sensor]
                    ])
                    st.caption(f"Examples: {hints}")
            
            with col2:
                sensor_key = f"sensor_{sensor}"
                # For sensors with value descriptions, use a selectbox
                if sensor in self.sensor_descriptions:
                    # Add "Unknown" option to the choices
                    choices = ["Unknown"] + [str(k) for k in self.sensor_descriptions[sensor].keys()]
                    value = st.selectbox(
                        f"Value for '{sensor}'",
                        choices,
                        key=sensor_key,
                        format_func=lambda x: f"{x} ({self.sensor_descriptions[sensor].get(int(x), 'Unknown')})" if x != "Unknown" else x
                    )
                    
                    # Update session state
                    if value == "Unknown":
                        if sensor in st.session_state.sensor_readings:
                            del st.session_state.sensor_readings[sensor]
                    else:
                        st.session_state.sensor_readings[sensor] = float(value)
                else:
                    # For numerical values, add an "Unknown" checkbox
                    unknown_key = f"unknown_{sensor_key}"
                    is_unknown = st.checkbox("Unknown", key=unknown_key, value=True)
                    
                    if is_unknown:
                        # If marked as unknown, remove from sensor readings and disable input
                        if sensor in st.session_state.sensor_readings:
                            del st.session_state.sensor_readings[sensor]
                        
                        # Show a disabled number input
                        st.number_input(
                            f"Value for '{sensor}'",
                            key=sensor_key,
                            step=0.1,
                            disabled=True
                        )
                    else:
                        # If not unknown, show an active number input
                        value = st.number_input(
                            f"Value for '{sensor}'",
                            key=sensor_key,
                            step=0.1
                        )
                        
                        # Update session state with the entered value
                        st.session_state.sensor_readings[sensor] = float(value)
            
            st.divider()
    
    def run_diagnosis(self):
        """Run diagnostic with current observations and sensor values."""
        # Collect present observations for diagnosis
        present_observations = []
        for obs, value in st.session_state.observations.items():
            if value is True:  # Only include observations marked as present
                present_observations.append(obs)
        
        # Run diagnosis with both observations and sensor values
        diagnosis_results = self.engine.diagnose(
            present_observations,
            sensor_readings=st.session_state.sensor_readings
        )
        test_recommendations = self.engine.get_test_recommendations(
            present_observations
        )
        
        # Update session state
        st.session_state.diagnosis_results = diagnosis_results
        st.session_state.test_recommendations = test_recommendations
    
    def render_diagnosis_results(self):
        """Render the diagnostic results."""
        st.subheader("🔬 Diagnostic Results")
        
        if not st.session_state.diagnosis_results:
            st.info("No diagnostic results yet. Press 'Run Diagnosis' to analyze.")
            return
        
        # Create a container for the results
        results_container = st.container()
        
        with results_container:
            # Display results in a table
            data = []
            for result in st.session_state.diagnosis_results:
                confidence_emoji = {
                    EvidenceStrength.CONFIRMS: "✅",
                    EvidenceStrength.SUGGESTS: "🔍",
                    EvidenceStrength.INCONCLUSIVE: "❓",
                }.get(result.confidence, "")
                
                data.append({
                    "Failure Mode": result.failure_mode,
                    "Confidence": f"{confidence_emoji} {result.confidence.value}",
                    "Supporting Evidence": ", ".join(result.supporting_evidence)
                })
            
            # Convert to DataFrame and display
            if data:
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No potential failure modes identified based on current observations.")
    
    def render_test_recommendations(self):
        """Render the test recommendations."""
        st.subheader("🧪 Suggested Next Tests")
        
        if not st.session_state.test_recommendations:
            st.info("No test recommendations available. Press 'Run Diagnosis' for suggestions.")
            return
        
        # Create a container for the recommendations
        recommendations_container = st.container()
        
        with recommendations_container:
            # Display recommendations in a table
            data = []
            for rec in st.session_state.test_recommendations:
                impact_emoji = {
                    EvidenceStrength.CONFIRMS: "✅",
                    EvidenceStrength.RULES_OUT: "❌",
                    EvidenceStrength.SUGGESTS: "🔍",
                }.get(rec.strength_if_true, "")
                
                details = ""
                if rec.operator and rec.threshold is not None:
                    details = f"{rec.operator} {rec.threshold}"
                
                data.append({
                    "Test": rec.name,
                    "Type": rec.type.capitalize(),
                    "Impact": f"{impact_emoji} {rec.strength_if_true.value}",
                    "Details": details,
                    "Would Help With": ", ".join(rec.would_help_with)
                })
            
            # Convert to DataFrame and display
            if data:
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No further tests recommended.")
    
    def render_debug_panel(self):
        """Render the debug panel for explainability."""
        with st.expander("🔍 Debug & Explainability"):
            st.subheader("Active Observations & Sensor Readings")
            
            # Show present observations
            st.markdown("**Present Observations:**")
            present_obs = [obs for obs, value in st.session_state.observations.items() if value is True]
            if present_obs:
                st.write(", ".join(present_obs))
            else:
                st.write("None")
            
            # Show absent observations
            st.markdown("**Absent Observations:**")
            absent_obs = [obs for obs, value in st.session_state.observations.items() if value is False]
            if absent_obs:
                st.write(", ".join(absent_obs))
            else:
                st.write("None")
            
            # Show sensor readings
            st.markdown("**Sensor Readings:**")
            if st.session_state.sensor_readings:
                sensor_data = []
                for sensor, value in st.session_state.sensor_readings.items():
                    # Get human-readable value if available
                    readable_value = value
                    if sensor in self.sensor_descriptions:
                        readable_value = f"{value} ({self.sensor_descriptions[sensor].get(value, 'Unknown')})"
                    
                    threshold_info = ""
                    # Add threshold evaluation info if available
                    if sensor in self.sensor_metadata:
                        threshold_matches = []
                        for meta in self.sensor_metadata[sensor]:
                            operator = meta.get("operator")
                            threshold = meta.get("threshold")
                            if operator and threshold is not None:
                                # Check if this value matches the threshold
                                match_found = False
                                if operator == "=":
                                    match_found = value == threshold
                                elif operator == "<":
                                    match_found = value < threshold
                                elif operator == ">":
                                    match_found = value > threshold
                                elif operator == "<=":
                                    match_found = value <= threshold
                                elif operator == ">=":
                                    match_found = value >= threshold
                                elif operator == "in" and isinstance(threshold, list):
                                    match_found = value in threshold
                                
                                status = "✅" if match_found else "❌"
                                # Add human-readable threshold value if available
                                if sensor in self.sensor_descriptions and threshold in self.sensor_descriptions[sensor]:
                                    threshold_str = f"{threshold} ({self.sensor_descriptions[sensor][threshold]})"
                                else:
                                    threshold_str = str(threshold)
                                threshold_matches.append(f"{status} {operator} {threshold_str}")
                        
                        if threshold_matches:
                            threshold_info = f" ({', '.join(threshold_matches)})"
                    
                    sensor_data.append({
                        "Sensor": sensor,
                        "Value": readable_value,
                        "Threshold Evaluation": threshold_info
                    })
                
                # Display sensor data as a table
                st.dataframe(pd.DataFrame(sensor_data), use_container_width=True)
            else:
                st.write("None")
            
            # Show active evidence relationships
            st.subheader("Active Evidence Relationships")
            
            # Fetch evidence relationships for present observations
            if present_obs:
                evidence_query = """
                MATCH (o)-[r:EVIDENCE_FOR]->(f:FailureMode)
                WHERE o.name IN $observations
                RETURN o.name as evidence, f.name as failure_mode, 
                       r.when_true_strength as when_true, r.when_false_strength as when_false,
                       r.operator as operator, r.threshold as threshold
                """
                evidence_results = self.db.run_query(evidence_query, {"observations": present_obs})
                
                if evidence_results:
                    evidence_data = []
                    for row in evidence_results:
                        evidence_data.append({
                            "Evidence": row["evidence"],
                            "Failure Mode": row["failure_mode"],
                            "When Present": row["when_true"],
                            "When Absent": row["when_false"],
                            "Operator": row.get("operator", ""),
                            "Threshold": row.get("threshold", "")
                        })
                    
                    st.dataframe(pd.DataFrame(evidence_data), use_container_width=True)
                else:
                    st.write("No active evidence relationships.")
            else:
                st.write("No active evidence relationships.")

    def render_ui(self):
        """Render the main UI components."""
        st.title("🔍 Telltale Diagnostic Assistant")
        st.markdown(
            """
            This tool helps diagnose problems by analyzing observations and sensor readings
            against a knowledge graph of failure modes.
            
            1. Mark your observations as present or absent
            2. Enter any available sensor readings
            3. Click 'Run Diagnosis' to analyze
            4. Review results and follow suggested next steps
            """
        )
        
        # Render user input controls
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            self.render_observation_controls()
        
        with col2:
            self.render_sensor_controls()
        
        # Run diagnosis button
        st.divider()
        if st.button("🧪 Run Diagnosis", type="primary", use_container_width=True):
            with st.spinner("Running diagnostic analysis..."):
                self.run_diagnosis()
        
        # Render results
        st.divider()
        results_tab, recommendations_tab, debug_tab = st.tabs([
            "🔬 Results", "🧪 Recommendations", "🔍 Debug"
        ])
        
        with results_tab:
            self.render_diagnosis_results()
        
        with recommendations_tab:
            self.render_test_recommendations()
        
        with debug_tab:
            self.render_debug_panel()

def main():
    """Main entry point for the Streamlit app."""
    st.set_page_config(
        page_title="Telltale Diagnostic Assistant",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Initialize and render the UI
    app = TelltaleUI()
    app.render_ui()

if __name__ == "__main__":
    main() 
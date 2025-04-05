
# 📋 TellTale Streamlit Demo UI Specification

## 🎯 Purpose

Build an interactive diagnostic assistant using **Streamlit** as a lightweight web interface. The assistant will connect to a **Neo4j knowledge graph**, enabling users to simulate device diagnostics by:

- Providing observations
- Simulating sensor readings
- Iteratively narrowing down possible failure modes
- Receiving diagnosis suggestions and test recommendations

This tool is intended as a functional demo.  Use the code in **Telltale**  to create the demo.  Don't re-code everything from scratch.

---

## 🔗 Backend Assumptions

- The Neo4j graph contains:
  - `FailureMode`, `Observation`, and `SensorReading` nodes
  - `EVIDENCE_FOR` relationships with `when_true_strength`, `when_false_strength`, `operator`, and `threshold`
  - `CAUSES` relationships (used for display or educational purposes)

- The graph is small enough to be **fully loaded into memory** for session-level caching.

---

## 🧱 UI Components

### 1. **Observation Controls**
- Dynamically list all `Observation` nodes from the database.
- For each, allow user to:
  - Mark as `"present"` ✅
  - Mark as `"absent"` ❌
  - Leave as `"unknown"` ❓
- UI Element: Dropdown or radio buttons for each observation.

---

### 2. **Sensor Input Controls**
- Dynamically list all `SensorReading` nodes.
- For each sensor:
  - Show its name (e.g., `battery_voltage`, `switch_status`)
  - Provide an appropriate input widget:
    - Number input (e.g., for voltage)
    - Dropdown/selectbox for enums (e.g., switch state: Off, On, Mute)
- These simulate sensor data for the diagnostic engine.

---

### 3. **Diagnosis Button**
- Clicking “Run Diagnosis” will:
  - Evaluate user-entered observations and sensor values
  - Filter out any failure modes that are `rules_out`
  - Rank remaining candidates based on strongest remaining evidence (`confirms`, `suggests`, etc.)
- Show output as a ranked list of failure modes with brief reasoning (e.g., “Confirmed by battery_voltage < 4.0”, “Suggested by Buzz or Hiss”)

---

### 4. **Suggested Next Tests**
- Display a section titled “Suggested Next Tests”.
- List all additional observations or sensor readings (not yet provided) that could help **confirm or rule out** the remaining failure modes.
- Show:
  - Observation/Sensor name
  - What failure modes it would help distinguish
  - What strength (e.g., “Would confirm: Dead Battery”, “Would rule out: Mute Mode”)

---

### 5. **Debug & Explainability Panel (optional)**
- Show internal reasoning:
  - All `EVIDENCE_FOR` relationships relevant to current inputs
  - Reasoning trail: which observations supported or ruled out which failures
- Useful for demos or education.

---

## 🔄 System Behavior

### On Page Load:
- Pull entire Neo4j graph into memory.
- Extract:
  - All nodes of type `Observation`, `SensorReading`, and `FailureMode`
  - All `EVIDENCE_FOR` relationships and their metadata

### On Input Change:
- Update internal state, but do not trigger diagnosis until user presses the button.

### On “Run Diagnosis”:
- Evaluate all user inputs against `EVIDENCE_FOR` relationships:
  - For each matched observation/sensor:
    - Use `when_true_strength` or `when_false_strength` based on the value
- Eliminate any failure mode with any `rules_out` edge triggered
- Rank the rest by max remaining evidence strength
- Display result and suggested next tests

---

## 📌 Notes

- Observations and sensor inputs should be **displayed by label**, not internal names.
- UI must tolerate partial input (some sensors/observations unknown).  Thats just like in real life where we need to learn more about the system over time.
- No need to write to the database — all inputs live in session memory.
- All content is driven from the graph itself — no hardcoded sensors or observations.
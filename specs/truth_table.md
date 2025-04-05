Specification: Truth Table Test Framework for Diagnostic Engine
Purpose
Build a tool to automatically generate and evaluate truth tables for small test graphs in Neo4j. This allows for rigorous verification that the diagnostic engine returns correct failure modes and evidence strengths under all combinations of observation and sensor input.

Scope & Assumptions
The graph is small enough to be fully loaded into memory for testing.

We're testing against manually curated test graphs with known expected outputs.

Not all observations or sensor readings will be active in a test case — some will remain null or absent.

Functionality
1. Graph Scan & Input Identification
Query the Neo4j database to extract:

All Observation nodes

All SensorReading nodes

All EVIDENCE_FOR relationships

Identify the subset of Observations and SensorReadings relevant to a given test case.

The test graph will specify which inputs are “in play”.

2. Test Case Generation
For each relevant input:

Observation:

Two states: True (present) or False (absent)

SensorReading:

For each EVIDENCE_FOR edge from that sensor, generate values:

Just below threshold (should fail condition)

Exactly at threshold (depends on operator)

Just above threshold (should pass condition)

Optional: a "null" value to simulate no sensor data

Generate all combinations of:

Boolean observations

Sampled sensor values

3. Diagnosis Execution
For each test case:

Call the DiagnosticEngine.diagnose(...) method with:

The chosen observation states

The selected sensor values

Capture the result:

Diagnosed failure modes

Confidence level (e.g., confirms, suggests)

Supporting evidence used

4. Assertion & Expectation Framework
Each test graph will define a small set of expected outcomes, e.g.:

json
Copy
Edit
{
  "inputs": {
    "observations": ["Buzz or Hiss"],
    "sensor_values": {"battery_voltage": 3.7}
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
}
The framework should assert that these expected results appear in the engine output.

Also validate that no unexpected failure modes are diagnosed.

5. Test Output
Render a truth table to the console or to a CSV/HTML file:

Columns: observations, sensor values, diagnosed failure modes, confidence levels, surprise flags

Include a mode that only displays unexpected results, to help catch contradictions

Technical Requirements
Use python unittest.  Use the test_utils in this library as needed

Include utilities to:

Load a test graph

Register expected outcomes

Run the full truth table

Print and assert results


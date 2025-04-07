# Telltale

A Knowledge Graph-Based Diagnostic Assistant that enables natural language to graph to diagnosis and explanation. Built with Neo4j and Python, this tool provides a framework for diagnostic reasoning based on observations and sensor data.

## Overview

Telltale implements a diagnostic system that follows a three-stage process:

1. **Natural Language to Graph**: Convert user observations and sensor data into a structured knowledge graph
2. **Graph-Based Reasoning**: Use the knowledge graph to identify and rank potential failure modes
3. **Diagnosis and Explanation**: Provide clear diagnoses with supporting evidence and recommended next steps

## Core Concepts

### Node Types

1. **FailureMode**
   - Represents a distinct way in which a system can fail
   - Properties:
     - `name`: String identifier (e.g., "Dead Battery", "Speaker Broken")
     - `description`: Detailed explanation of the failure mode

2. **Observation**
   - Represents human-noticeable effects or symptoms
   - Properties:
     - `name`: String identifier (e.g., "No Music", "Buzz or Hiss")
     - `description`: Detailed description of what can be observed

3. **SensorReading**
   - Represents quantifiable measurements from system sensors
   - Properties:
     - `name`: String identifier (e.g., "battery_voltage", "switch_status")
     - `unit`: Measurement unit (e.g., "V", "C", "enum")
     - `value`: Current reading (provided at runtime)
     - `value_descriptions`: JSON string mapping values to human-readable descriptions

### Relationships

1. **CAUSES** (from FailureMode to Observation)
   - Represents a ground-truth, physical, or logical relationship.
   - Indicates that a specific `FailureMode` *directly causes* an `Observation`. This describes the expected symptom if a failure occurs.
   - Example: `(Dead Battery) --[:CAUSES]--> (No Music)`

2. **EVIDENCE_FOR** (from Observation/SensorReading to FailureMode)
   - Represents a *diagnostic* relationship used for reasoning.
   - Encodes how the presence or absence of an `Observation`, or the value of a `SensorReading` relative to a threshold, impacts the likelihood of a specific `FailureMode`.
   - Properties:
     - `when_true_strength`: Evidence strength if the condition (observation present, sensor reading meets criteria) is met.
     - `when_false_strength`: Evidence strength if the condition is not met.
     - `operator`: Comparison operator (`=`, `<`, `>`, `<=`, `>=`, `in`) used for `SensorReading`.
     - `threshold`: Value(s) for comparison used for `SensorReading`.
   - Strength values:
     - `"confirms"`: Strongly confirms the failure mode.
     - `"rules_out"`: Definitely eliminates the failure mode.
     - `"suggests"`: Makes the failure mode more likely
     - `"suggests_against"`: Makes the failure mode less likely
     - `"inconclusive"`: No meaningful impact on likelihood

## Features

- Natural language interface for adding nodes and relationships
- Semantic similarity search to prevent duplicate concepts
- Interactive web UI for diagnostic sessions
- Automated test framework with truth table generation
- Docker-based deployment with Neo4j integration

## How it Works: Graph-Based Reasoning

Telltale leverages the structure of the Neo4j knowledge graph and the power of Cypher queries to perform diagnostics. While users interact via Python tools (like `node_manager.py`), the CLI, or the Web UI, these tools construct and execute Cypher queries internally.

### Knowledge Graph Structure for Diagnosis

- **Nodes**: `FailureMode`, `Observation`, `SensorReading` represent the core entities.
- **Relationships**:
    - `CAUSES`: Links failures to their direct symptoms. Used for *explaining* why an observation might occur if a failure is suspected.
    - `EVIDENCE_FOR`: Links observations and sensor readings *back* to the failure modes they provide evidence for. This encodes the diagnostic rules, including comparison operators and thresholds for sensor readings, and the strength of evidence (`confirms`, `rules_out`, etc.) under different conditions (present/absent, above/below threshold).

### Access Patterns & Diagnostic Logic with Cypher

1.  **Providing Runtime Data**: A diagnostic session starts by providing the current state:
    - Which `Observation`s are present or absent.
    - The current values for relevant `SensorReading`s.
    This runtime data is passed as *parameters* to internal Cypher queries.

2.  **Identifying and Ranking Candidates**: Cypher queries traverse the graph, primarily using the `EVIDENCE_FOR` relationships.
    - They match `FailureMode`s linked to the provided `Observation`s and `SensorReading`s.
    - Using the runtime data and the logic stored in `EVIDENCE_FOR` properties (`operator`, `threshold`, `when_true_strength`, `when_false_strength`), the queries evaluate the evidence for each potential `FailureMode`.
    - `FailureMode`s are ranked based on the strength of supporting evidence and whether any evidence rules them out.

3.  **Explaining Observations**: Once potential `FailureMode`s are identified and ranked, the system can explain *why* a user might be seeing a specific `Observation`. It does this by tracing the `CAUSES` relationships *from* the high-probability `FailureMode`s *to* the `Observation` in question.

4.  **Recommending Tests**: To narrow down the possibilities, the system identifies the most informative next steps. Internal Cypher queries search for *unobserved* `Observation`s or `SensorReading`s linked via `EVIDENCE_FOR` to the remaining candidate `FailureMode`s. It prioritizes tests associated with `confirms` or `rules_out` strengths, as these provide the most diagnostic value.

This approach centralizes the diagnostic logic within the graph structure itself, allowing the Python application layer to focus on user interaction and orchestration while leveraging Neo4j and Cypher for the core reasoning engine.

## Installation

### Using pip

```bash
# Install from the local directory
pip install -e .
```

### Development Setup

1. Create and activate a virtual environment:
```bash
uv venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
uv pip install -r requirements.txt
```

## Docker Setup

To run the entire application with Neo4j included:

```bash
docker-compose up -d
```

This starts:
- A Neo4j database container
- A Telltale business logic container
- A Streamlit UI container (accessible at http://localhost:8501)


## Web UI

The Streamlit web UI provides an interactive diagnostic experience with:

- Observation controls to mark symptoms as present/absent
- Sensor reading inputs with appropriate widgets
- Diagnosis results with confidence levels
- Recommended next tests
- Debug panel for understanding the reasoning

To access the UI:
- When running with Docker: http://localhost:8501
- When running locally: `python telltale/ui/run.py`

## Example

A user reports "No Music" when a device is turned on. Telltale will:

1. Identify possible causes through the knowledge graph:
   - Dead Battery (suggested by observation)
   - Mute Mode (suggested by observation)
   - Speaker Broken (not linked)
   - Device Off (not linked)

2. Recommend tests to narrow down the diagnosis:
   - Check battery_voltage < 4.0 (confirms/rules out Dead Battery)
   - Check switch_status = 0 (confirms/rules out Device Off)
   - Ask about "Buzz or Hiss" (suggests Speaker Broken)

3. Update recommendations as new observations are provided
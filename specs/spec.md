**Title: Knowledge Graph-Based Diagnostic Assistant Specification**

**Overview:**
This document outlines the structure, data model, and logic required to implement a graph-based diagnostic assistant using **Neo4j** and **Python**. The assistant is inspired by medical diagnostic knowledge graphs and is designed for diagnosing mechanical or electrical failures in devices based on observations and sensor data.

The system will:
1. Accept user-provided observations (e.g., "no music", "buzzing noise").
2. Cross-reference these observations with known failure modes.
3. Eliminate failure modes that are ruled out by observations.
4. Rank remaining candidates by strength of evidence.
5. Recommend the next best observation or sensor check to narrow the diagnosis.

---

**Data Model:**

**Nodes:**
- `FailureMode`
  - Represents a distinct way in which the system can fail (e.g., "Dead Battery", "Speaker Broken").
  - `name`: string

- `Observation`
  - Represents something a human user can notice or describe (e.g., "No Music", "Buzz or Hiss").
  - These are typically subjective or externally noticeable effects.
  - `name`: string

- `SensorReading`
  - Represents quantifiable measurements from system sensors (e.g., "battery_voltage < 4.0", "switch_status = 0").
  - These are objective signals captured by hardware.
  - `name`: string
  - `value`: number (provided at runtime, not stored on the node)

**Relationships:**

- `[:CAUSES]` from `FailureMode` to `Observation`
  - Represents a ground-truth relationship: "If this failure occurs, this observation is expected."
  - Example: `(FailureMode: Dead Battery) --[:CAUSES]--> (Observation: No Music)`

- `[:EVIDENCE_FOR]` from `Observation`, `SensorReading`, or `FailureMode` to `FailureMode`
  - Represents a diagnostic link: "Seeing (or not seeing) this observation tells us something about this failure mode."
  - Directional and asymmetric — may suggest, confirm, rule out, or be inconclusive.
  - Properties:
    - `when_true_strength`: enum — the evidentiary strength if the condition is met
    - `when_false_strength`: enum — the strength if the condition is not met
    - `operator`: string — one of `=`, `<`, `>`, `<=`, `>=`, `in` (only for sensor readings)
    - `threshold`: number or list — value(s) used for the comparison (only for sensor readings)

Valid `strength` values:
- `"confirms"`: This evidence strongly confirms the presence of a failure mode.
- `"rules_out"`: This evidence definitively eliminates a failure mode as a possibility.
- `"suggests"`: This evidence makes a failure mode more likely, but does not confirm it.
- `"suggests_against"`: This evidence makes a failure mode less likely, but does not rule it out.
- `"inconclusive"`: This evidence does not meaningfully impact the likelihood of the failure.

This enables bidirectional reasoning where the same sensor or observation can support or weaken a diagnosis based on its current value. **`CAUSES` is descriptive, `EVIDENCE_FOR` is diagnostic.**

---

**Cypher Schema & Example Data (Toy Problem):**

```cypher
CREATE (:FailureMode {name: "Dead Battery"});
CREATE (:FailureMode {name: "Power Switch Off"});
CREATE (:FailureMode {name: "Mute Mode"});
CREATE (:FailureMode {name: "Speaker Broken"});

CREATE (:Observation {name: "No Music"});
CREATE (:Observation {name: "Buzz or Hiss"});
CREATE (:SensorReading {name: "battery_voltage"});
CREATE (:SensorReading {name: "switch_status"});

// Causal relationships
MATCH (fm:FailureMode {name: "Dead Battery"}), (o:Observation {name: "No Music"})
CREATE (fm)-[:CAUSES]->(o);

MATCH (fm:FailureMode {name: "Power Switch Off"}), (o:Observation {name: "No Music"})
CREATE (fm)-[:CAUSES]->(o);

MATCH (fm:FailureMode {name: "Mute Mode"}), (o:Observation {name: "No Music"})
CREATE (fm)-[:CAUSES]->(o);

MATCH (fm:FailureMode {name: "Speaker Broken"}), (o:Observation {name: "No Music"})
CREATE (fm)-[:CAUSES]->(o);

MATCH (fm:FailureMode {name: "Speaker Broken"}), (o:Observation {name: "Buzz or Hiss"})
CREATE (fm)-[:CAUSES]->(o);

// Diagnostic relationships
MATCH (fm:FailureMode {name: "Dead Battery"}), (sr:SensorReading {name: "battery_voltage"})
CREATE (sr)-[:EVIDENCE_FOR {
  operator: "<",
  threshold: 4.0,
  when_true_strength: "confirms",
  when_false_strength: "rules_out"
}]->(fm);

MATCH (fm:FailureMode {name: "Power Switch Off"}), (sr:SensorReading {name: "switch_status"})
CREATE (sr)-[:EVIDENCE_FOR {
  operator: "=",
  threshold: 0,
  when_true_strength: "confirms",
  when_false_strength: "rules_out"
}]->(fm);

MATCH (fm:FailureMode {name: "Mute Mode"}), (sr:SensorReading {name: "switch_status"})
CREATE (sr)-[:EVIDENCE_FOR {
  operator: "=",
  threshold: 2,
  when_true_strength: "confirms",
  when_false_strength: "suggests_against"
}]->(fm);

MATCH (fm:FailureMode {name: "Speaker Broken"}), (o:Observation {name: "Buzz or Hiss"})
CREATE (o)-[:EVIDENCE_FOR {
  when_true_strength: "suggests",
  when_false_strength: "inconclusive"
}]->(fm);

MATCH (fm:FailureMode {name: "Dead Battery"}), (o:Observation {name: "No Music"})
CREATE (o)-[:EVIDENCE_FOR {
  when_true_strength: "suggests",
  when_false_strength: "rules_out"
}]->(fm);

MATCH (fm:FailureMode {name: "Mute Mode"}), (o:Observation {name: "No Music"})
CREATE (o)-[:EVIDENCE_FOR {
  when_true_strength: "suggests",
  when_false_strength: "inconclusive"
}]->(fm);

// Failure Mode to Failure Mode relationships
MATCH (fm1:FailureMode {name: "Dead Battery"}), (fm2:FailureMode {name: "Speaker Broken"})
CREATE (fm1)-[:EVIDENCE_FOR {
  when_true_strength: "suggests",
  when_false_strength: "inconclusive"
}]->(fm2);

MATCH (fm1:FailureMode {name: "Power Supply Issue"}), (fm2:FailureMode {name: "Dead Battery"})
CREATE (fm1)-[:EVIDENCE_FOR {
  when_true_strength: "confirms",
  when_false_strength: "rules_out"
}]->(fm2);
```

---

**Diagnostic Query Logic:**

### 1. Identify Candidate Failure Modes

```cypher
MATCH (o:Observation)-[r:EVIDENCE_FOR]->(fm:FailureMode)
WHERE o.name IN $user_observations
WITH fm, COLLECT(r.when_true_strength) AS strengths
WHERE NONE(s IN strengths WHERE s = 'rules_out')

// Also consider evidence from other failure modes
MATCH (fm)<-[r2:EVIDENCE_FOR]-(other_fm:FailureMode)
WHERE other_fm.name IN $confirmed_failure_modes
WITH fm, strengths + COLLECT(r2.when_true_strength) AS all_strengths
WHERE NONE(s IN all_strengths WHERE s = 'rules_out')

WITH fm.name AS failure_mode,
     REDUCE(maxStrength = 'inconclusive', s IN all_strengths |
       CASE
         WHEN s = 'confirms' THEN 'confirms'
         WHEN s = 'suggests' AND maxStrength <> 'confirms' THEN 'suggests'
         ELSE maxStrength
       END
     ) AS strongest_signal
RETURN failure_mode, strongest_signal
```

### 2. Recommend Next Best Tests

```cypher
MATCH (o:Observation)-[r:EVIDENCE_FOR]->(fm:FailureMode)
WHERE o.name IN $user_observations
WITH fm, COLLECT(r.when_true_strength) AS strengths
WHERE NONE(s IN strengths WHERE s = 'rules_out')

// Also consider evidence from other failure modes
MATCH (fm)<-[r2:EVIDENCE_FOR]-(other_fm:FailureMode)
WHERE other_fm.name IN $confirmed_failure_modes
WITH fm, strengths + COLLECT(r2.when_true_strength) AS all_strengths
WHERE NONE(s IN all_strengths WHERE s = 'rules_out')

MATCH (fm)<-[new_r:EVIDENCE_FOR]-(next_o:Observation)
WHERE NOT next_o.name IN $user_observations
  AND new_r.when_true_strength IN ['confirms', 'rules_out']

RETURN DISTINCT
  next_o.name AS next_question,
  new_r.when_true_strength AS strength_if_seen,
  COLLECT(DISTINCT fm.name) AS would_help_with
ORDER BY strength_if_seen DESC
```

---

**Example Use Case (Toy Diagnosis Walkthrough):**

> A customer reports: "No Music when the button is pressed."

```python
user_observations = ["No Music"]
```
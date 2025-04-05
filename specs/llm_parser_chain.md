# LLM Parser Chain Specification

## Overview
This document specifies the implementation of a chain of LLM prompts using LangChain to break up the natural language parsing process into distinct, focused steps. The goal is to improve reliability and maintainability by separating concerns and making each step's purpose explicit.

## Node and Relationship Definitions

### Node Types

1. **FailureMode**
   - A distinct way in which the system can fail
   - Must be a root cause or underlying issue
   - Can cause multiple symptoms
   - Often requires diagnosis to identify
   - Examples: "Dead Battery", "Broken Speaker", "Faulty Power Supply"
   - NOT: Symptoms or observations (e.g., "No Sound" is an observation, not a failure mode)

2. **Observation**
   - Something that can be directly observed or checked by a user
   - Must be directly observable or measurable
   - Is an effect or symptom of a failure mode
   - Can be caused by multiple failure modes
   - Examples: "No Sound", "Red Warning Light", "Error Message", "Fuse Blown", "Open Circuit"
   - NOT: Internal states or measurements (e.g., "Battery Voltage" is a sensor reading)

3. **SensorReading**
   - A specific measurement or state that can be checked
   - Must include:
     - A unit of measurement (e.g., "V", "C", "enum")
     - A clear description of what is being measured
     - Optional value_descriptions for enum types (e.g., '{"0": "OFF", "1": "ON"}')
   - Examples: "Battery Voltage", "Switch Continuity", "Pin Connection Status"
   - NOT: User observations (e.g., "Device Won't Power On" is an observation)

### Relationship Types

1. **CAUSES**
   - From FailureMode to Observation
   - Represents a ground-truth relationship: "If this failure occurs, this observation is expected"
   - Directional and deterministic
   - Example: Dead Battery CAUSES No Sound
   - NOT: Diagnostic evidence (use EVIDENCE_FOR for that)

2. **EVIDENCE_FOR**
   - From Observation/SensorReading to FailureMode
   - Represents diagnostic evidence that helps identify a failure mode
   - Directional and asymmetric — may suggest, confirm, rule out, or be inconclusive
   - Properties:
     - `when_true_strength`: enum — the evidentiary strength if the condition is met
     - `when_true_rationale`: string — plain language explanation of why this strength is assigned when true
     - `when_false_strength`: enum — the strength if the condition is not met
     - `when_false_rationale`: string — plain language explanation of why this strength is assigned when false
     - `operator`: string — one of `=`, `<`, `>`, `<=`, `>=`, `in` (only for sensor readings)
     - `threshold`: number or list — value(s) used for the comparison (only for sensor readings)
   - Example: Battery Voltage < 3.2V EVIDENCE_FOR Dead Battery
   - NOT: Causal relationships (use CAUSES for that)
   - IMPORTANT: If any property value is unknown or uncertain, it should be set to `null` rather than guessed
     - Example: If the threshold voltage for dead battery is not specified in the text, set `threshold: null`
     - Example: If the evidence strength is unclear, set `when_true_strength: null` and `when_false_strength: null`
     - Example: If the operator for a sensor reading is not specified, set `operator: null`

## Chain Components

### 1. Node Identification Chain
**Purpose**: Extract all explicit nodes (failure modes, observations, and sensor readings) from the input text.

**Input**: Natural language text describing the system
**Output**: List of nodes with their types, names, descriptions, and units (for sensor readings)

**Example Input**:
```
The device won't power on. The battery voltage is 3.2V, which is below the minimum threshold of 4.0V.
The power switch is in the ON position (status=1). There's no sound output.
```

**Example Output**:
```json
{
    "nodes": [
        {
            "type": "Observation",
            "name": "Device Won't Power On",
            "description": "The device does not turn on when the power button is pressed"
        },
        {
            "type": "SensorReading",
            "name": "Battery Voltage",
            "description": "Current voltage level of the battery",
            "unit": "V"
        },
        {
            "type": "SensorReading",
            "name": "Power Switch Status",
            "description": "Current state of the power switch",
            "unit": "enum",
            "value_descriptions": {"0": "OFF", "1": "ON"}
        },
        {
            "type": "Observation",
            "name": "No Sound Output",
            "description": "The device does not produce any audio output"
        }
    ]
}
```

### 2. Implied Failure Modes Chain
**Purpose**: Identify failure modes that are logically implied by the text but not explicitly stated.

**Input**: 
- Original text
- List of nodes from step 1

**Example Input**:
```
Original text:
The device won't power on. The battery voltage is 3.2V, which is below the minimum threshold of 4.0V.
The power switch is in the ON position (status=1). There's no sound output.

Nodes from step 1:
{
    "nodes": [
        {
            "type": "Observation",
            "name": "Device Won't Power On",
            "description": "The device does not turn on when the power button is pressed"
        },
        {
            "type": "SensorReading",
            "name": "Battery Voltage",
            "description": "Current voltage level of the battery",
            "unit": "V"
        },
        {
            "type": "SensorReading",
            "name": "Power Switch Status",
            "description": "Current state of the power switch",
            "unit": "enum",
            "value_descriptions": {"0": "OFF", "1": "ON"}
        },
        {
            "type": "Observation",
            "name": "No Sound Output",
            "description": "The device does not produce any audio output"
        }
    ]
}
```

**Example Output**:
```json
{
    "nodes": [
        {
            "type": "FailureMode",
            "name": "Dead Battery",
            "description": "Battery has insufficient charge to power the device"
        },
        {
            "type": "FailureMode",
            "name": "Power Supply Issue",
            "description": "Internal power supply is not functioning correctly"
        }
    ]
}
```

### 3. Relationship Formation Chain
**Purpose**: Identify all relationships between nodes without considering strength.

**Input**:
- Original text
- Combined list of nodes (explicit + implied)

**Example Input**:
```
Original text:
The device won't power on. The battery voltage is 3.2V, which is below the minimum threshold of 4.0V.
The power switch is in the ON position (status=1). There's no sound output.

All nodes (explicit + implied):
{
    "nodes": [
        {
            "type": "Observation",
            "name": "Device Won't Power On",
            "description": "The device does not turn on when the power button is pressed"
        },
        {
            "type": "SensorReading",
            "name": "Battery Voltage",
            "description": "Current voltage level of the battery",
            "unit": "V"
        },
        {
            "type": "SensorReading",
            "name": "Power Switch Status",
            "description": "Current state of the power switch",
            "unit": "enum",
            "value_descriptions": {"0": "OFF", "1": "ON"}
        },
        {
            "type": "Observation",
            "name": "No Sound Output",
            "description": "The device does not produce any audio output"
        },
        {
            "type": "FailureMode",
            "name": "Dead Battery",
            "description": "Battery has insufficient charge to power the device"
        },
        {
            "type": "FailureMode",
            "name": "Power Supply Issue",
            "description": "Internal power supply is not functioning correctly"
        }
    ]
}
```

**Example Output**:
```json
{
    "relationships": [
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Power Supply Issue"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "EVIDENCE_FOR",
            "source": {
                "type": "SensorReading",
                "name": "Battery Voltage"
            },
            "destination": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "properties": {
                "operator": "<",
                "threshold": 4.0
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "SensorReading",
                "name": "Power Switch Status"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            },
            "properties": {
                "operator": "=",
                "threshold": 0
            }
        }
    ]
}
```

### 4. Evidence Strength Assessment Chain
**Purpose**: Assess the strength of evidence relationships when conditions are true and false.

**Input**:
- Original text
- List of relationships from step 3
- List of all nodes

**Example Input**:
```
Original text:
The device won't power on. The battery voltage is 3.2V, which is below the minimum threshold of 4.0V.
The power switch is in the ON position (status=1). There's no sound output.

Relationships from step 3:
{
    "relationships": [
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Power Supply Issue"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "EVIDENCE_FOR",
            "source": {
                "type": "SensorReading",
                "name": "Battery Voltage"
            },
            "destination": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "properties": {
                "when_true_strength": "confirms",
                "when_true_rationale": "A battery voltage below 4.0V definitively indicates insufficient charge to power the device",
                "when_false_strength": "rules_out",
                "when_false_rationale": "A battery voltage above 4.0V means the battery has sufficient charge, ruling out dead battery as the cause",
                "operator": "<",
                "threshold": 4.0
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "SensorReading",
                "name": "Power Switch Status"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            },
            "properties": {
                "when_true_strength": "confirms",
                "when_true_rationale": "When the power switch is OFF (status=0), the device is intentionally turned off",
                "when_false_strength": "rules_out",
                "when_false_rationale": "When the power switch is ON (status=1), the device should be powered on, ruling out switch position as the cause",
                "operator": "=",
                "threshold": 0
            }
        }
    ]
}
```

**Example Output**:
```json
{
    "relationships": [
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "FailureMode",
                "name": "Power Supply Issue"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            }
        },
        {
            "type": "EVIDENCE_FOR",
            "source": {
                "type": "SensorReading",
                "name": "Battery Voltage"
            },
            "destination": {
                "type": "FailureMode",
                "name": "Dead Battery"
            },
            "properties": {
                "when_true_strength": "confirms",
                "when_true_rationale": "A battery voltage below 4.0V definitively indicates insufficient charge to power the device",
                "when_false_strength": "rules_out",
                "when_false_rationale": "A battery voltage above 4.0V means the battery has sufficient charge, ruling out dead battery as the cause",
                "operator": "<",
                "threshold": 4.0
            }
        },
        {
            "type": "CAUSES",
            "source": {
                "type": "SensorReading",
                "name": "Power Switch Status"
            },
            "destination": {
                "type": "Observation",
                "name": "Device Won't Power On"
            },
            "properties": {
                "when_true_strength": "confirms",
                "when_true_rationale": "When the power switch is OFF (status=0), the device is intentionally turned off",
                "when_false_strength": "rules_out",
                "when_false_rationale": "When the power switch is ON (status=1), the device should be powered on, ruling out switch position as the cause",
                "operator": "=",
                "threshold": 0
            }
        }
    ]
}
```

## Implementation Details

### LangChain Components
1. **Chain Types**:
   - Use `LLMChain` for each step
   - Combine using `SequentialChain` for the overall flow

2. **Prompt Templates**:
   - Each chain will have its own prompt template
   - Templates will be stored in a separate module for maintainability

3. **Output Parsers**:
   - Use Pydantic models for structured output parsing
   - Each chain will have its own output parser

4. **Error Handling**:
   - Each chain should handle its own errors gracefully
   - Failed chains should provide meaningful error messages
   - Consider implementing retry logic for transient failures

### Data Flow
1. Input text → Node Identification Chain
2. Nodes + text → Implied Failure Modes Chain
3. All nodes + text → Relationship Formation Chain
4. Relationships + nodes + text → Evidence Strength Assessment Chain
5. Final output combines all results into a single structured response

### Validation
- Each chain's output should be validated against its schema
- Relationships should only be created between existing nodes
- Evidence strengths should be valid enum values or null
- Operators and thresholds should only be present for sensor readings or null
- Node types must strictly follow the defined categories
- Relationships must follow the correct directionality rules
- Unknown or uncertain values should be set to null rather than guessed
  - This allows other systems to fill in the values later
  - Prevents incorrect assumptions from being propagated
  - Makes it clear which values need to be determined by other means

## Example Usage

```python
# Initialize the chain
parser_chain = LLMParserChain()

# Process text
result = parser_chain.parse_text("""
The device won't power on. The battery voltage is 3.2V, which is below the minimum threshold of 4.0V.
The power switch is in the ON position (status=1). There's no sound output.
""")

# Result will contain all nodes and relationships with proper evidence strengths
```

## Benefits
1. **Separation of Concerns**: Each chain has a single, focused responsibility
2. **Improved Reliability**: Smaller, focused prompts are less likely to make mistakes
3. **Better Maintainability**: Each chain can be modified independently
4. **Easier Testing**: Each chain can be tested in isolation
5. **Better Error Handling**: Failures can be isolated to specific steps 
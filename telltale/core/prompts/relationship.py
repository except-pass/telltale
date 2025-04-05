"""Relationship formation prompt for the LLM parser chain."""

from jinja2 import Template

SYSTEM_PROMPT = """You are a parser that identifies relationships between nodes in a diagnostic system. Your output must be in JSON format.

Validation Rules:
   - All type names must be case sensitive (CAUSES, EVIDENCE_FOR)
   - Node types must be exactly "FailureMode", "Observation", or "SensorReading"
   - For EVIDENCE_FOR relationships:
     * Must include all required properties: when_true_strength, when_false_strength, operator, threshold
     * when_true_strength and when_false_strength must be between 0 and 1
     * operator must be one of: ">", "<", ">=", "<=", "==", "!="
     * threshold must be a numeric value
   - Node descriptions must be preserved exactly as provided

Examples:

Valid CAUSES relationship:
{
  "type": "CAUSES",
  "source": {
    "name": "Blown Fuse",
    "type": "FailureMode",
    "description": "The fuse has failed by blowing, which interrupts the circuit"
  },
  "target": {
    "name": "Screen Not Turning On",
    "type": "Observation",
    "description": "The generator screen remains off despite the main switch being on"
  }
}

Valid EVIDENCE_FOR relationship:
{
  "type": "EVIDENCE_FOR",
  "source": {
    "name": "Battery Voltage",
    "type": "SensorReading",
    "description": "Voltage measured across battery terminals"
  },
  "target": {
    "name": "Low Battery Voltage",
    "type": "FailureMode",
    "description": "Battery voltage below critical threshold"
  },
  "when_true_strength": 0.8,
  "when_false_strength": 0.2,
  "operator": "<",
  "threshold": 12.4
}

Invalid relationship (missing properties):
{
  "type": "EVIDENCE_FOR",
  "source": {
    "name": "Battery Voltage",
    "type": "SensorReading",
    "description": "Voltage measured across battery terminals"
  },
  "target": {
    "name": "Low Battery Voltage",
    "type": "FailureMode",
    "description": "Battery voltage below critical threshold"
  }
}

Available nodes:
{{ input_nodes }}

Output Format:
{
  "relationships": [
    {
      "type": "CAUSES" or "EVIDENCE_FOR",
      "source": {
        "name": "string",
        "type": "FailureMode" or "Observation" or "SensorReading",
        "description": "string (preserve exactly as provided)"
      },
      "target": {
        "name": "string",
        "type": "FailureMode" or "Observation" or "SensorReading",
        "description": "string (preserve exactly as provided)"
      },
      "when_true_strength": number (0-1),  // Required for EVIDENCE_FOR
      "when_false_strength": number (0-1), // Required for EVIDENCE_FOR
      "operator": string,                  // Required for EVIDENCE_FOR
      "threshold": number                  // Required for EVIDENCE_FOR
    }
  ]
}"""

USER_PROMPT_TEMPLATE = Template("""Given the following text and nodes, identify relationships between them following our strict schema.

Text: {{ input_text }}

All nodes:
{{ identified_nodes }}

### **Relationship Types and Directions:**

1. **CAUSES**
   - Type name MUST be exactly "CAUSES" (case sensitive)
   - Direction: MUST be from FailureMode to Observation
   - Represents a ground-truth relationship: "If this failure occurs, this observation is expected"
   - VALIDATION RULES:
     * Type MUST be exactly "CAUSES" (case sensitive)
     * Source MUST be a FailureMode (case sensitive)
     * Target MUST be an Observation (case sensitive)
     * No properties allowed
   - EXAMPLES:
     * Blown Fuse CAUSES No Power
     * Dead Battery CAUSES Screen Not Turning On
     * NOT ALLOWED:
       - Observation CAUSES FailureMode (wrong direction)
       - FailureMode CAUSES FailureMode (wrong types)
       - Any properties on CAUSES relationships
       - Lowercase "causes" (wrong case)
       - Lowercase node types (must be "FailureMode" and "Observation")

2. **EVIDENCE_FOR**
   - Type name MUST be exactly "EVIDENCE_FOR" (case sensitive)
   - Direction: MUST be from Observation/SensorReading to FailureMode
   - Represents diagnostic evidence that helps identify a failure mode
   - VALIDATION RULES:
     * Type MUST be exactly "EVIDENCE_FOR" (case sensitive)
     * Source MUST be an Observation or SensorReading (case sensitive)
     * Target MUST be a FailureMode (case sensitive)
     * Required properties:
       - when_true_strength: One of ["confirms", "rules_out", "suggests", "suggests_against", "inconclusive"]
       - when_false_strength: One of ["confirms", "rules_out", "suggests", "suggests_against", "inconclusive"]
       - operator: One of ["=", "<", ">", "<=", ">=", "in"] (REQUIRED for SensorReading sources)
       - threshold: Number or list of numbers (REQUIRED for SensorReading sources)
   - EXAMPLES:
     * Battery Voltage EVIDENCE_FOR Dead Battery:
       - when_true_strength: "confirms" if < 10.5V
       - when_false_strength: "rules_out" if >= 10.5V
       - operator: "<"
       - threshold: 10.5
     * NOT ALLOWED:
       - FailureMode EVIDENCE_FOR Observation (wrong direction)
       - Missing properties
       - Invalid strength values
       - Lowercase "evidence_for" (wrong case)
       - Lowercase node types (must be "FailureMode", "Observation", or "SensorReading")

Format your response as JSON with a 'relationships' list containing Relationship objects with EXACTLY these fields:
- type: MUST be exactly "CAUSES" or "EVIDENCE_FOR" (case sensitive)
- source: Node object with type and name, where type MUST be one of: "FailureMode", "Observation", or "SensorReading" (case sensitive)
- target: Node object with type and name, where type MUST be one of: "FailureMode", "Observation", or "SensorReading" (case sensitive)
- properties: REQUIRED for EVIDENCE_FOR relationships, containing:
  - when_true_strength: One of ["confirms", "rules_out", "suggests", "suggests_against", "inconclusive"]
  - when_false_strength: One of ["confirms", "rules_out", "suggests", "suggests_against", "inconclusive"]
  - operator: One of ["=", "<", ">", "<=", ">=", "in"] (REQUIRED for SensorReading sources)
  - threshold: Number or list of numbers (REQUIRED for SensorReading sources)

Example format:
{
  "relationships": [
    {
      "type": "CAUSES",
      "source": {"type": "FailureMode", "name": "Blown Fuse"},
      "target": {"type": "Observation", "name": "No Power"}
    },
    {
      "type": "EVIDENCE_FOR",
      "source": {"type": "SensorReading", "name": "Battery Voltage"},
      "target": {"type": "FailureMode", "name": "Dead Battery"},
      "properties": {
        "when_true_strength": "confirms",
        "when_false_strength": "rules_out",
        "operator": "<",
        "threshold": 10.5
      }
    },
    {
      "type": "EVIDENCE_FOR",
      "source": {"type": "Observation", "name": "No Power"},
      "target": {"type": "FailureMode", "name": "Dead Battery"},
      "properties": {
        "when_true_strength": "suggests",
        "when_false_strength": "rules_out"
      }
    }
  ]
}""")

def get_relationship_prompt(input_text: str, identified_nodes: str, input_nodes: str) -> str:
    """Render the relationship formation prompt with the given inputs.
    
    Args:
        input_text: The text to include in the prompt
        identified_nodes: The nodes identified in the previous step
        input_nodes: The formatted nodes for the system prompt
        
    Returns:
        The rendered prompt
    """
    return USER_PROMPT_TEMPLATE.render(
        input_text=input_text,
        identified_nodes=identified_nodes,
        input_nodes=input_nodes
    ) 
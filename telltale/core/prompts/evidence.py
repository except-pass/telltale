"""Evidence strength assessment prompt for the LLM parser chain."""

from jinja2 import Template

SYSTEM_PROMPT = """You are a detailed parser specializing in assessing the strength of evidence for diagnostic relationships based on provided text and context.
Your task is to take a list of previously identified relationships (both CAUSES and EVIDENCE_FOR) and enrich the EVIDENCE_FOR relationships with evidence strength assessments.
- For each EVIDENCE_FOR relationship, determine the 'when_true_strength', 'when_false_strength', 'when_true_rationale', and 'when_false_rationale'.
- Preserve any existing 'operator' and 'threshold' properties within the 'properties' dictionary for EVIDENCE_FOR relationships.
- CAUSES relationships should be passed through exactly as they are, without adding a 'properties' field.
- Use 'null' for any strength, rationale, operator, or threshold value that cannot be determined from the text or context.
- Ensure your output is valid JSON adhering strictly to the specified format.
"""

USER_PROMPT_TEMPLATE = Template("""Given the following context (original text and previously identified relationships), analyze each relationship.

Context:
Text: {{ input_text }}

Relationships (from previous step):
{{ initial_relationships }}

Your Task:
Re-evaluate each relationship based on the text and apply the following rules:

1.  **For relationships of type "EVIDENCE_FOR":**
    *   Assess the strength of evidence when the condition (defined by source node, operator, threshold) is TRUE and when it is FALSE.
    *   Determine the 'when_true_strength' and 'when_false_strength'. Valid strength values are EXACTLY one of: ["confirms", "rules_out", "suggests", "suggests_against", "inconclusive"]. Use 'null' if uncertain.
    *   Provide a concise 'when_true_rationale' and 'when_false_rationale' explaining the reasoning for the assigned strengths based *only* on the provided text. Use 'null' if no rationale can be derived from the text.
    *   Place these four fields ('when_true_strength', 'when_false_strength', 'when_true_rationale', 'when_false_rationale') inside a 'properties' dictionary.
    *   If the input 'EVIDENCE_FOR' relationship already had 'operator' and 'threshold' in its 'properties', **preserve them** within the output 'properties' dictionary. If they were not present or not applicable (e.g., source is Observation), they should remain absent or 'null'.

2.  **For relationships of type "CAUSES":**
    *   Output these relationships exactly as they appear in the input `initial_relationships`. Do **NOT** add a 'properties' field.

Output Format:
Format your response as a single JSON object containing a 'relationships' list. Each object in the list must strictly follow the examples below:

Example Output Structure:
```json
{
  "relationships": [
    {
      "type": "CAUSES",
      "source": {
        "type": "FailureMode",
        "name": "Dead Battery"
        // preserve other source fields if present
      },
      "target": {
        "type": "Observation",
        "name": "Device Won't Power On"
        // preserve other target fields if present
      }
      // NO properties field for CAUSES
    },
    {
      "type": "EVIDENCE_FOR",
      "source": {
        "type": "SensorReading",
        "name": "Battery Voltage"
        // preserve other source fields if present
      },
      "target": {
        "type": "FailureMode",
        "name": "Dead Battery"
        // preserve other target fields if present
      },
      "properties": {
        "when_true_strength": "confirms", // or suggests, rules_out, etc., or null
        "when_true_rationale": "A battery voltage below the threshold confirms the battery is dead.", // or null
        "when_false_strength": "rules_out", // or suggests_against, inconclusive, etc., or null
        "when_false_rationale": "A battery voltage above the threshold rules out the battery being dead.", // or null
        "operator": "<", // Preserve if present in input, else null/absent
        "threshold": 4.0 // Preserve if present in input, else null/absent
      }
    },
    {
      "type": "EVIDENCE_FOR",
      "source": {
        "type": "Observation",
        "name": "Smoke Visible"
         // preserve other source fields if present
      },
      "target": {
        "type": "FailureMode",
        "name": "Overheating Component"
         // preserve other target fields if present
      },
      "properties": {
        "when_true_strength": "suggests", // Example for Observation source
        "when_true_rationale": "Seeing smoke suggests a component might be overheating.", // or null
        "when_false_strength": "inconclusive", // Example for Observation source
        "when_false_rationale": "Not seeing smoke doesn't rule out overheating, but doesn't suggest it either.", // or null
        // operator/threshold typically null/absent for Observation sources
        "operator": null,
        "threshold": null
      }
    }
    // ... include all other relationships following these rules ...
  ]
}
```

Ensure the output contains ALL relationships provided in the input `initial_relationships`, modified according to these instructions.
""")

def get_evidence_prompt(input_text: str, initial_relationships: str) -> str:
    """Render the evidence strength assessment prompt with the given inputs.
    
    Args:
        input_text: The text to include in the prompt
        initial_relationships: The relationships identified in the previous step (as JSON string)
        
    Returns:
        The rendered prompt
    """
    # Ensure initial_relationships is a string (it should be passed as JSON)
    if not isinstance(initial_relationships, str):
        import json
        initial_relationships = json.dumps(initial_relationships, indent=2)

    return USER_PROMPT_TEMPLATE.render(
        input_text=input_text,
        initial_relationships=initial_relationships
    ) 
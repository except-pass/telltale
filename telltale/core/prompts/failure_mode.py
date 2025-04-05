"""Failure mode identification prompt for the LLM parser chain."""

from jinja2 import Template

SYSTEM_PROMPT = """You are a parser that identifies implied failure modes from natural language descriptions. Your output must be in JSON format."""

USER_PROMPT_TEMPLATE = Template("""Given the following text and identified nodes, identify any implied failure modes.

Text: {{ input_text }}

Identified nodes:
{{ identified_nodes }}

### **Schema Requirements:**
You MUST ONLY output nodes of type "FailureMode" (case sensitive) that are not already in the identified nodes.

### **Validation Rules:**
1. Type MUST be exactly "FailureMode" (case sensitive)
2. Name must be unique (not already in identified nodes)
3. Description is REQUIRED and MUST NOT be null
4. Must be a root cause or underlying issue
5. Must be able to cause multiple symptoms
6. Must require diagnosis to identify
7. Must NOT be a component, state, or condition

Format your response as JSON with a 'nodes' list containing Node objects with EXACTLY these fields:
- type: MUST be exactly "FailureMode" (case sensitive)
- name: A clear, concise name (must be unique)
- description: A detailed description (REQUIRED, NEVER null)

Example format:
{
  "nodes": [
    {
      "type": "FailureMode",
      "name": "Battery Failure",
      "description": "The battery has insufficient charge to power the device"
    },
    {
      "type": "FailureMode",
      "name": "Circuit Open",
      "description": "An open circuit condition exists in the electrical path"
    }
  ]
}""")

def get_failure_mode_prompt(input_text: str, identified_nodes: str) -> str:
    """Render the failure mode identification prompt with the given input text and nodes.
    
    Args:
        input_text: The text to include in the prompt
        identified_nodes: The nodes identified in the previous step
        
    Returns:
        The rendered prompt
    """
    return USER_PROMPT_TEMPLATE.render(
        input_text=input_text,
        identified_nodes=identified_nodes
    ) 
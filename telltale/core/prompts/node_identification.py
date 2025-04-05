"""Node identification prompt for the LLM parser chain."""

from jinja2 import Template

SYSTEM_PROMPT = """You are a parser that identifies diagnostic elements from natural language descriptions. Your output must be in JSON format."""

USER_PROMPT_TEMPLATE = Template("""Given the following text, identify all diagnostic nodes following our strict schema.

Text: {{ input_text }}

### **Schema Requirements:**
You MUST ONLY output nodes of these three types with EXACTLY these type names:
1. `FailureMode` (case sensitive)
2. `Observation` (case sensitive)
3. `SensorReading` (case sensitive)

### **Node Types and Validation Rules:**

1. **FailureMode**
   - These are the underlying problems or ways the system can fail
   - VALIDATION RULES:
     * Type MUST be exactly "FailureMode"
     * Must be a root cause or underlying issue
     * Must be able to cause multiple symptoms
     * Must require diagnosis to identify
     * Must NOT be a component, state, or condition
     * Must have a detailed description
   - EXAMPLES:
     * Component failures:
       - "Dead Battery" → description: "Battery has insufficient charge to power the device"
       - "Blown Fuse" → description: "Fuse has failed open, interrupting the circuit"
       - "Faulty GCU" → description: "Generator Control Unit has malfunctioned"
     * NOT ALLOWED:
       - "Fuse" (component, not failure)
       - "Open" (condition, not failure)
       - "Battery Voltage Low" (observation, not root cause)

2. **Observation**
   - These are things that can be directly observed or checked
   - VALIDATION RULES:
     * Type MUST be exactly "Observation"
     * Must be directly observable or measurable
     * Must be an effect or symptom of a failure mode
     * Must be able to be caused by multiple failure modes
     * Must have a detailed description
   - EXAMPLES:
     * Device behavior:
       - "Screen Not Turning On" → description: "Display remains dark when power is applied"
       - "No Power" → description: "Device shows no signs of electrical power"
     * NOT ALLOWED:
       - "Battery Voltage" (this is a measurement)
       - "Switch Status" (this is a measurement)

3. **SensorReading**
   - These are specific measurements or states that can be checked
   - VALIDATION RULES:
     * Type MUST be exactly "SensorReading"
     * Must include a unit of measurement
     * Must include a clear description
     * Must have value_descriptions for enum types
   - EXAMPLES:
     * Voltage measurements:
       - Name: "Battery Voltage"
         Description: "Voltage measured across battery terminals"
         Unit: "V"
     * State measurements:
       - Name: "Switch Status"
         Description: "Position state of the main power switch"
         Unit: "enum"
         Value_descriptions: {"0": "OFF", "1": "ON"}

Format your response as JSON with a 'nodes' list containing Node objects with EXACTLY these fields:
- type: MUST be one of: "FailureMode", "Observation", or "SensorReading" (case sensitive)
- name: A clear, concise name
- description: A detailed description (REQUIRED, NEVER null)
- unit: For SensorReading only, the unit of measurement (REQUIRED for SensorReading)
- value_descriptions: For SensorReading only, if it's an enum type

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

def get_node_prompt(input_text: str) -> str:
    """Render the node identification prompt with the given input text.
    
    Args:
        input_text: The text to include in the prompt
        
    Returns:
        The rendered prompt
    """
    return USER_PROMPT_TEMPLATE.render(input_text=input_text) 
# Truth Table Test Framework

This document provides instructions for using the Truth Table Test Framework for testing diagnostic graphs in the telltale system.

## Overview

The Truth Table Test Framework allows developers to:

1. Create small test graphs with known characteristics
2. Automatically generate test cases that cover all possible combinations of inputs
3. Run the diagnostic engine against each test case
4. Compare actual results with expected outcomes
5. Export results in various formats (text, CSV, HTML)

## Basic Usage

### Step 1: Create a Test Class

Create a test class that inherits from `TruthTableTest`:

```python
from telltale.tests.truth_table import TruthTableTest

class MyDiagnosticTest(TruthTableTest):
    def test_my_scenario(self):
        # Test implementation here
        pass
```

### Step 2: Define a Test Graph

Define a test graph structure as a Python dictionary:

```python
test_graph = {
    "failure_modes": [
        {
            "name": "Dead Battery",
            "description": "The battery is discharged or failed"
        },
        # More failure modes...
    ],
    "observations": [
        {
            "name": "No Sound",
            "description": "Device produces no sound"
        },
        # More observations...
    ],
    "sensor_readings": [
        {
            "name": "battery_voltage",
            "description": "Battery voltage in volts",
            "unit": "V"
        },
        # More sensor readings...
    ],
    "causes_relationships": [
        {
            "failure_mode": "Dead Battery",
            "observation": "No Sound"
        },
        # More causal relationships...
    ],
    "evidence_relationships": [
        {
            "observation": "No Sound",
            "failure_mode": "Dead Battery",
            "when_true_strength": "suggests",
            "when_false_strength": "rules_out"
        },
        {
            "sensor": "battery_voltage",
            "failure_mode": "Dead Battery",
            "when_true_strength": "confirms",
            "when_false_strength": "rules_out",
            "operator": "<",
            "threshold": 3.5
        },
        # More evidence relationships...
    ]
}
```

### Step 3: Load and Scan the Graph

Load the test graph into the Neo4j database and scan it to identify all inputs:

```python
self.load_test_graph(test_graph)
self.scan_graph()
```

### Step 4: Register Expected Outcomes

Register the expected outcomes for specific test cases:

```python
self.register_expected_outcome({
    "inputs": {
        "observations": ["No Sound"],
        "sensor_values": {"battery_voltage": 3.0}
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
})
```

### Step 5: Run the Tests

You can run either specific test cases or the full truth table:

```python
# Run specific test cases
test_cases = [
    {
        "observations": ["No Sound"],
        "sensor_values": {"battery_voltage": 3.0}
    },
    # More test cases...
]
results = self.run_truth_table(test_cases)

# Or generate and run the full truth table
full_results = self.run_truth_table()
```

### Step 6: Verify Results

Check that there are no unexpected or missing results:

```python
# Print the results
print(self.print_results(results))

# Assert that there are no surprises
self.assert_no_surprises(results)
```

### Step 7: Export Results (Optional)

Export the results to a file for further analysis:

```python
# Export to HTML for visual inspection
html_output = self.print_results(full_results, format='html')
with open('truth_table_results.html', 'w') as f:
    f.write(html_output)

# Or export to CSV
csv_output = self.print_results(full_results, format='csv')
with open('truth_table_results.csv', 'w') as f:
    f.write(csv_output)
```

## Advanced Features

### Filtering Results

You can filter results to only show test cases with surprises:

```python
# Print only surprising results
print(self.print_results(results, only_surprises=True))
```

### Output Formats

The framework supports three output formats:
- `text`: Plain text format for console output
- `csv`: CSV format for data analysis
- `html`: HTML format with color-coding of surprises

## Example

See `telltale/tests/test_truth_table_example.py` for a complete working example. 
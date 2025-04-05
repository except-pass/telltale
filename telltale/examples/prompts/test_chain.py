"""Script for testing the chain prompting approach with the LLM parser."""

import json
from typing import Dict, Any
import openai
from dotenv import load_dotenv
import os
from pathlib import Path
import traceback

from telltale.core.llm_parser import LLMParser

def test_chain_prompt(text: str) -> Dict[str, Any]:
    """Test the chain prompting approach with a given text input.
    
    Args:
        text: The text to parse
        
    Returns:
        The parsed result as a dictionary
    """
    # Load environment variables
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    
    # Get model from environment
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        raise ValueError("OPENAI_MODEL not found in environment")
    print(f"Using model: {model}")
    
    # Initialize parser
    parser = LLMParser()
    
    # Parse the text
    result = parser.parse_text(text)
    
    return result

def process_examples():
    """Process examples from the generator.txt file."""
    # Get the path to the examples file
    examples_path = Path(__file__).parent / "generator.txt"
    
    if not examples_path.exists():
        print(f"Error: {examples_path} not found")
        return
        
    # Read examples from file
    with open(examples_path, 'r') as f:
        examples = f.read().strip().split('\n\n')
    
    # Process each example
    for i, example in enumerate(examples, 1):
        print(f"\n{'='*80}")
        print(f"Processing Example {i}:")
        print(f"{'='*80}")
        print(f"Input text:\n{example}\n")
        
        try:
            result = test_chain_prompt(example)
            print("Parsed Result:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error processing example: {str(e)}")
            print("\nFull traceback:")
            print(traceback.format_exc())
        
        print(f"\n{'-'*80}")

if __name__ == "__main__":
    process_examples() 
"""Script for inspecting each step of the LLM Parser Chain on example text."""

import json
from pathlib import Path
import os
import argparse
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# Assuming models.py is correctly updated with EvidenceProperties and nested structure
from telltale.core.llm_parser import LLMParser
from telltale.core.models import Relationship # Import Relationship to help type hint
from telltale.core.database import Neo4jConnection # Import for database access
from telltale.core.node_manager import NodeManager # Import NodeManager to save data to database

console = Console()

def setup_environment():
    """Load environment variables and verify requirements."""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    
    required_vars = ["OPENAI_API_KEY", "OPENAI_MODEL"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def load_example(prompt_file_path: Path) -> str:
    """Load the example text from the specified file."""
    if not prompt_file_path.exists():
        raise FileNotFoundError(f"Example prompt file not found: {prompt_file_path}")
    
    console.print(f"Loading example text from [cyan]{prompt_file_path}[/cyan]...")
    with open(prompt_file_path, 'r') as f:
        return f.read().strip()

def inspect_step(step_name: str, result: dict):
    """Inspect and display the results of a chain step."""
    console.print(f"\n[bold blue]Step: {step_name}[/bold blue]")
    
    # Convert Pydantic models to dictionaries for clean JSON output
    def convert_to_dict(obj):
        if hasattr(obj, 'model_dump'):
            # Use exclude_none=True to avoid cluttering output with nulls from Optional fields
            return obj.model_dump(mode='json', exclude_none=True)
        elif isinstance(obj, list):
            return [convert_to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: convert_to_dict(v) for k, v in obj.items()}
        return obj
    
    result_dict = convert_to_dict(result)
    console.print(Panel(
        Syntax(json.dumps(result_dict, indent=2), "json", theme="monokai"),
        title=f"{step_name} Results",
        border_style="blue"
    ))

def clear_database():
    """Clear the Neo4j database."""
    console.print("[bold yellow]Clearing Neo4j database...[/bold yellow]")
    try:
        # Create database connection and initialize schema with clear_existing=True
        db = Neo4jConnection()
        db.connect()
        db.initialize_schema(clear_existing=True)
        console.print("[bold green]Database cleared successfully[/bold green]")
        db.close()
        return True
    except Exception as e:
        console.print(f"[bold red]Error clearing database:[/bold red] {str(e)}")
        return False

def save_to_database(result: dict):
    """Save the parsed nodes and relationships to the Neo4j database."""
    console.print("\n[bold yellow]Saving parsed data to Neo4j database...[/bold yellow]")
    try:
        # Create database connection and NodeManager
        db = Neo4jConnection()
        db.connect()
        node_manager = NodeManager(db)
        
        # Save nodes to database and keep a mapping of node name to database node with ID
        nodes_map = {}
        for node_data in result.get("nodes", []):
            # Create the node object
            console.print(f"Saving node: {node_data['name']} ({node_data['type']})")
            node_id = db.save_node(node_data)
            nodes_map[(node_data["type"], node_data["name"])] = node_data
            node_data["id"] = node_id
        
        # Save relationships to database
        for rel_data in result.get("relationships", []):
            # Get source and target nodes
            source_type = rel_data["source"]["type"]
            source_name = rel_data["source"]["name"]
            target_type = rel_data["target"]["type"]
            target_name = rel_data["target"]["name"]
            
            # Check if we have the nodes in our map
            source = nodes_map.get((source_type, source_name))
            target = nodes_map.get((target_type, target_name))
            
            if not source or not target:
                console.print(f"[bold red]Missing nodes for relationship: {source_type}:{source_name} -> {target_type}:{target_name}[/bold red]")
                continue
            
            # Create the relationship object with source and target nodes that have IDs
            console.print(f"Saving relationship: {source_name} -{rel_data['type']}-> {target_name}")
            rel_data["source"]["id"] = source["id"]
            rel_data["target"]["id"] = target["id"]
            db.save_relationship(rel_data)
        
        console.print("[bold green]Data saved to Neo4j database successfully[/bold green]")
        db.close()
        return True
    except Exception as e:
        console.print(f"[bold red]Error saving to database:[/bold red] {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the chain and inspect each step."""
    parser = argparse.ArgumentParser(description="Inspect the LLM parser chain on a given prompt file.")
    parser.add_argument(
        "prompt_file", 
        type=str, 
        help="Path to the text file containing the prompt.",
        nargs='?',
        default="telltale/examples/prompts/generator.txt"
    )
    parser.add_argument(
        "-o", "--output",
        type=str, 
        help="Path to save the output JSON file.",
        default="parser_output.json"
    )
    parser.add_argument(
        "--clear-db",
        action="store_true",
        help="Clear the Neo4j database before running"
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save the parsed data to the Neo4j database"
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="List available example prompts"
    )
    args = parser.parse_args()

    if args.examples:
        # List available examples
        example_dirs = [p for p in Path("telltale/examples/prompts").iterdir() if p.is_dir()]
        example_files = [p for p in Path("telltale/examples/prompts").glob("*.txt")]
        
        console.print("[bold green]Available example directories:[/bold green]")
        for d in example_dirs:
            console.print(f"- {d}")
            for f in d.glob("*.txt"):
                console.print(f"  - {f}")
        
        console.print("\n[bold green]Available example files:[/bold green]")
        for f in example_files:
            console.print(f"- {f}")
        return
    
    prompt_file_path = Path(args.prompt_file)
    output_file_path = Path(args.output)

    console.print(Panel(f"Inspecting chain with prompt: [cyan]{prompt_file_path}[/cyan] -> Output: [cyan]{output_file_path}[/cyan]", title="Inspect Chain", border_style="blue"))

    try:
        # Setup
        setup_environment()
        console.print("[bold green]Environment setup complete[/bold green]")

        # Clear database if requested
        if args.clear_db:
            if not clear_database():
                console.print("[bold red]Failed to clear database. Continuing anyway...[/bold red]")
        
        # Load example from specified file
        text = load_example(prompt_file_path)
        console.print("\n[bold green]Example Text:[/bold green]")
        console.print(Panel(text, title="Input Text", border_style="green"))
        
        # Initialize chain
        chain = LLMParser()
        console.print("[bold green]Chain initialized[/bold green]")
        
        # Run chain and inspect each step
        # Note: The chain.parse_text() should now return Relationship objects
        # where EvidenceLink types have the nested 'properties' structure.
        result = chain.parse_text(text)
        
        # --- Inspection Steps --- #
        
        # Inspect nodes (no change needed here)
        inspect_step("Node Identification & Implied Failure Modes", {"nodes": result["nodes"]})
        
        # Inspect ALL relationships returned by the final step (Evidence Strength Assessment)
        # This step now includes both CAUSES and updated EVIDENCE_FOR relationships.
        inspect_step("Final Relationships (including assessed evidence)", {"relationships": result["relationships"]})
        
        # --- Summary --- #
        console.print("\n[bold green]Summary:[/bold green]")
        console.print(f"Total nodes identified: {len(result.get('nodes', []))}")
        
        # Count relationships after the final step
        final_relationships = result.get('relationships', [])
        console.print(f"Total final relationships: {len(final_relationships)}")
        
        # Count specifically EVIDENCE_FOR relationships in the final output
        evidence_relationships_count = sum(
            1 for rel in final_relationships
            if isinstance(rel, Relationship) and rel.type == "EVIDENCE_FOR"
        )
        console.print(f"Evidence relationships assessed: {evidence_relationships_count}")
        
        # Save to database if requested
        if args.save_db:
            save_to_database(result)

        # Save results to specified output file
        console.print(f"\nAttempting to save results to [cyan]{output_file_path}[/cyan]...")
        saved_path = chain.save_results(result, filename=str(output_file_path))
        console.print(f"[bold green]Successfully saved results to {saved_path}[/bold green]")
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        raise

if __name__ == "__main__":
    main() 
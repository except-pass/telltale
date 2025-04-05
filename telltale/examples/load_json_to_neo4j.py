"""Script to load parsed nodes and relationships from a JSON file into Neo4j using NodeManager."""

import json
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Telltale imports
from telltale.core.database import Neo4jConnection # Use the connection class
from telltale.core.node_manager import NodeManager # Use the manager class
from telltale.core.models import (
    Node, FailureMode, Observation, SensorReading, 
    CausesLink, EvidenceLink, EvidenceStrength, ComparisonOperator, EvidenceProperties
)

console = Console()

def setup_environment():
    """Load environment variables and verify Neo4j requirements."""
    env_path = Path(".env")
    if env_path.exists():
        # Force override of existing env vars with values from .env
        load_dotenv(env_path, override=True) 
        console.print("[green]Loaded environment variables from .env (overriding existing)[/green]")
    else:
        console.print("[yellow]Warning: .env file not found. Relying on system environment variables.[/yellow]")

    required_vars = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        console.print(f"[bold red]Error: Missing required Neo4j environment variables: {', '.join(missing_vars)}[/bold red]")
        console.print("Please set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD.")
        raise ValueError("Missing Neo4j environment variables")
    
    console.print("[green]Neo4j environment variables found.[/green]")
    # Print the URI being used
    console.print(f"DEBUG: Attempting to use NEO4J_URI = {os.environ.get('NEO4J_URI')}")
    # Return the connection object directly
    try:
        db = Neo4jConnection(
            uri=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"]
        )
        db.connect() # Verify connection
        console.print("[green]Successfully connected to Neo4j.[/green]")
        return db
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Neo4j: {e}[/bold red]")
        raise

def load_json_data(json_file_path: Path) -> dict:
    """Load nodes and relationships from the specified JSON file."""
    if not json_file_path.exists():
        console.print(f"[bold red]Error: JSON file not found at {json_file_path}[/bold red]")
        raise FileNotFoundError(f"JSON file not found: {json_file_path}")
        
    console.print(f"Loading data from [cyan]{json_file_path}[/cyan]...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            console.print(f"Successfully loaded data: {len(data.get('nodes', []))} nodes, {len(data.get('relationships', []))} relationships.")
            return data
        except json.JSONDecodeError as e:
            console.print(f"[bold red]Error: Failed to decode JSON from {json_file_path}[/bold red]")
            console.print(f"Details: {e}")
            raise

def clear_database(db: Neo4jConnection):
    """Clear the existing graph data using the connection object."""
    console.print("[yellow]Clearing existing database...[/yellow]")
    try:
        # Use run_query method from Neo4jConnection
        db.run_query("MATCH (n) DETACH DELETE n") 
        console.print("[green]Database cleared.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error clearing database: {e}[/bold red]")
        raise

def upload_to_neo4j(node_manager: NodeManager, data: dict):
    """Upload nodes and relationships to Neo4j using NodeManager."""
    nodes_data = data.get('nodes', [])
    relationships_data = data.get('relationships', [])

    if not nodes_data:
        console.print("[yellow]No nodes found in the JSON data to upload.[/yellow]")
        # Even if no nodes, we might have relationships if nodes already exist, so don't return yet.
        # return

    console.print("Starting upload to Neo4j via NodeManager...")
    
    # 1. Instantiate and Add Nodes
    console.print(f"Processing {len(nodes_data)} nodes...")
    added_nodes_map = {} # Map (type, name) -> Node object with ID
    node_add_count = 0
    node_skip_count = 0
    for node_dict in nodes_data:
        node_type = node_dict.get('type')
        node_name = node_dict.get('name')
        node_desc = node_dict.get('description')

        if not node_type or not node_name:
            console.print(f"[yellow]Skipping node due to missing type or name: {node_dict}[/yellow]")
            node_skip_count += 1
            continue
        
        try:
            # Instantiate Pydantic model based on type
            if node_type == "FailureMode":
                node_obj = FailureMode(name=node_name, description=node_desc)
            elif node_type == "Observation":
                node_obj = Observation(name=node_name, description=node_desc)
            elif node_type == "SensorReading":
                node_obj = SensorReading(
                    name=node_name, 
                    description=node_desc, 
                    unit=node_dict.get('unit') # Include unit if present
                )
            else:
                console.print(f"[yellow]Skipping node with unknown type '{node_type}': {node_name}[/yellow]")
                node_skip_count += 1
                continue

            # Add node using NodeManager (handles duplicates/similarity based on its logic)
            # We use force=True because we are loading from a presumably curated JSON,
            # assuming we want to ensure these specific nodes exist as described.
            # If using this script interactively, force=False might be better.
            node_id = node_manager.add_node(node_obj, force=True) 
            node_obj.id = node_id # Store the Neo4j ID back into the object
            added_nodes_map[(node_type, node_name)] = node_obj
            node_add_count += 1
            # console.print(f"  Added/Merged Node: {node_type} '{node_name}' (ID: {node_id})")

        except Exception as e:
            console.print(f"[bold red]Error adding node '{node_name}': {e}[/bold red]")
            # Decide whether to continue or stop on error
            # For now, we'll skip this node and continue
            node_skip_count += 1
            continue
            
    console.print(f"[green]Processed {node_add_count} nodes successfully.[/green] Skipped {node_skip_count} nodes.")

    # 2. Instantiate and Add Relationships
    if not relationships_data:
        console.print("[yellow]No relationships found in the JSON data to upload.[/yellow]")
        return
        
    console.print(f"Processing {len(relationships_data)} relationships...")
    rel_add_count = 0
    rel_skip_count = 0
    for rel_dict in relationships_data:
        rel_type = rel_dict.get('type')
        source_info = rel_dict.get('source')
        target_info = rel_dict.get('target')
        properties = rel_dict.get('properties', {}) # Get properties dict

        if not rel_type or not source_info or not target_info:
            console.print(f"[yellow]Skipping relationship due to missing type, source, or target: {rel_dict}[/yellow]")
            rel_skip_count += 1
            continue
            
        source_type = source_info.get('type')
        source_name = source_info.get('name')
        target_type = target_info.get('type')
        target_name = target_info.get('name')

        # Find the source and target node objects we added earlier
        source_node = added_nodes_map.get((source_type, source_name))
        target_node = added_nodes_map.get((target_type, target_name))

        # If nodes weren't successfully added/found, skip relationship
        if not source_node:
            console.print(f"[yellow]Skipping relationship: Source node '{source_name}' ({source_type}) not found or failed to add.[/yellow]")
            rel_skip_count += 1
            continue
        if not target_node:
             console.print(f"[yellow]Skipping relationship: Target node '{target_name}' ({target_type}) not found or failed to add.[/yellow]")
             rel_skip_count += 1
             continue
             
        try:
            # Instantiate Relationship Pydantic model
            if rel_type == "CAUSES":
                # Ensure source is FailureMode and target is Observation
                if not isinstance(source_node, FailureMode) or not isinstance(target_node, Observation):
                    console.print(f"[yellow]Skipping CAUSES relationship: Invalid node types {source_node.__class__.__name__} -> {target_node.__class__.__name__}[/yellow]")
                    rel_skip_count += 1
                    continue
                rel_obj = CausesLink(source=source_node, target=target_node)

            elif rel_type == "EVIDENCE_FOR":
                 # Ensure source is Observation/SensorReading and target is FailureMode
                if not isinstance(target_node, FailureMode) or not isinstance(source_node, (Observation, SensorReading)):
                    console.print(f"[yellow]Skipping EVIDENCE_FOR relationship: Invalid node types {source_node.__class__.__name__} -> {target_node.__class__.__name__}[/yellow]")
                    rel_skip_count += 1
                    continue
                
                # Safely get enum values, defaulting if necessary or invalid
                try:
                    when_true = EvidenceStrength(properties.get('when_true_strength', 'suggests'))
                except ValueError:
                    console.print(f"[yellow]Warning: Invalid when_true_strength '{properties.get('when_true_strength')}' for {source_name}->{target_name}. Defaulting to 'suggests'.[/yellow]")
                    when_true = EvidenceStrength.SUGGESTS
                try:
                    when_false = EvidenceStrength(properties.get('when_false_strength', 'inconclusive'))
                except ValueError:
                    console.print(f"[yellow]Warning: Invalid when_false_strength '{properties.get('when_false_strength')}' for {source_name}->{target_name}. Defaulting to 'inconclusive'.[/yellow]")
                    when_false = EvidenceStrength.INCONCLUSIVE
                
                op_str = properties.get('operator')
                operator = None
                if op_str:
                    try:
                        operator = ComparisonOperator(op_str)
                    except ValueError:
                         console.print(f"[yellow]Warning: Invalid operator '{op_str}' for {source_name}->{target_name}. Setting to None.[/yellow]")

                # Create EvidenceProperties object first
                evidence_props_data = EvidenceProperties(
                    when_true_strength=when_true,
                    when_false_strength=when_false,
                    when_true_rationale=properties.get('when_true_rationale'),
                    when_false_rationale=properties.get('when_false_rationale'),
                    operator=operator, 
                    threshold=properties.get('threshold')
                )
                
                # Instantiate EvidenceLink with nested properties
                rel_obj = EvidenceLink(
                    source=source_node, 
                    target=target_node,
                    properties=evidence_props_data # Assign the nested object
                )
            else:
                console.print(f"[yellow]Skipping relationship with unknown type '{rel_type}'.[/yellow]")
                rel_skip_count += 1
                continue

            # Add relationship using NodeManager
            rel_id = node_manager.add_relationship(rel_obj)
            rel_add_count += 1
            # console.print(f"  Added Relationship: ({source_name})-[{rel_type}]->({target_name}) (ID: {rel_id})")
        
        except Exception as e:
            console.print(f"[bold red]Error adding relationship {source_name}-[{rel_type}]->{target_name}: {e}[/bold red]")
            # Decide whether to continue or stop on error
            rel_skip_count += 1
            continue

    console.print(f"[green]Processed {rel_add_count} relationships successfully.[/green] Skipped {rel_skip_count} relationships.")


def main():
    parser = argparse.ArgumentParser(description="Load LLM parser results from JSON into Neo4j using NodeManager.")
    parser.add_argument(
        "json_file", 
        type=str, 
        help="Path to the JSON file containing nodes and relationships.",
        nargs='?', # Make the argument optional
        default="gen1.json" # Default filename
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the Neo4j database before loading new data."
    )
    args = parser.parse_args()

    json_file_path = Path(args.json_file)
    
    console.print(Panel(f"Starting Neo4j Upload Script for: [cyan]{json_file_path}[/cyan] (using NodeManager)", title="Neo4j Loader", border_style="blue"))

    db_connection = None
    try:
        # 1. Setup Environment & Get DB Connection
        db_connection = setup_environment()
        
        # 2. Load Data from JSON
        data = load_json_data(json_file_path)
        
        # 3. Initialize NodeManager
        console.print("Initializing NodeManager...")
        # Pass initialize_vector_index=False as we are just loading data
        node_manager = NodeManager(db=db_connection, initialize_vector_index=False) 
        console.print("[green]NodeManager initialized (vector index skipped).[/green]")
                   
        # 4. Clear database if requested
        if args.clear:
            clear_database(db_connection)
            # Re-initialize NodeManager after clearing DB to ensure consistency
            # (This also handles resetting the vector index if it was initialized)
            console.print("Re-initializing NodeManager after clearing database...")
            node_manager = NodeManager(db=db_connection, initialize_vector_index=False)
            console.print("[green]NodeManager re-initialized.[/green]")

        # 5. Upload Data using NodeManager
        upload_to_neo4j(node_manager, data)
        
        console.print(Panel("[bold green]Upload process completed successfully![/bold green]", border_style="green"))

    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        # Errors during setup or file loading already printed messages
        console.print(Panel("[bold red]Script aborted due to errors.[/bold red]", border_style="red"))
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        # import traceback
        # traceback.print_exc()
    finally:
        if db_connection:
            db_connection.close()
            console.print("Neo4j connection closed.")

if __name__ == "__main__":
    main() 
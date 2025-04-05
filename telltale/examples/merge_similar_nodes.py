# telltale/examples/merge_similar_nodes.py
"""
Example script demonstrating how NodeManager prevents duplicate node creation 
by leveraging semantic similarity when processing multiple data sources.
"""

import json
import argparse
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.logging import RichHandler
import re # Add import for regex

# Telltale imports
from telltale.core.database import Neo4jConnection
from telltale.core.node_manager import NodeManager, NodeType
from telltale.core.models import (
    FailureMode, Observation, SensorReading,
    CausesLink, EvidenceLink, EvidenceStrength, ComparisonOperator, EvidenceProperties
)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("merge_example")
console = Console()
# --- End Configuration ---

def setup_environment() -> Neo4jConnection:
    """Load environment variables, verify Neo4j requirements, and return connection."""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info("Loaded environment variables from .env (overriding existing)")
    else:
        logger.warning(".env file not found. Relying on system environment variables.")

    required_vars = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Missing required Neo4j environment variables: {', '.join(missing_vars)}")
        logger.error("Please set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD.")
        raise ValueError("Missing Neo4j environment variables")

    logger.info("Neo4j environment variables found.")
    try:
        db = Neo4jConnection(
            uri=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"]
        )
        db.connect()
        logger.info("[green]Successfully connected to Neo4j.[/green]")
        return db
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}", exc_info=True)
        raise

def load_json_data(json_file_path: Path) -> dict:
    """Load nodes and relationships from the specified JSON file."""
    if not json_file_path.exists():
        logger.error(f"JSON file not found at {json_file_path}")
        raise FileNotFoundError(f"JSON file not found: {json_file_path}")

    logger.info(f"Loading data from [cyan]{json_file_path}[/cyan]...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            logger.info(f"Successfully loaded data: {len(data.get('nodes', []))} nodes, {len(data.get('relationships', []))} relationships.")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from {json_file_path}: {e}", exc_info=True)
            raise

def clear_database(db: Neo4jConnection):
    """Clear the existing graph data."""
    logger.warning("Clearing existing database...")
    try:
        db.run_query("MATCH (n) DETACH DELETE n")
        logger.info("[green]Database cleared.[/green]")
    except Exception as e:
        logger.error(f"Error clearing database: {e}", exc_info=True)
        raise

def instantiate_node(node_dict: dict) -> NodeType | None:
    """Instantiates a Pydantic Node object from a dictionary."""
    node_type = node_dict.get('type')
    node_name = node_dict.get('name')
    node_desc = node_dict.get('description')

    if not node_type or not node_name:
        logger.warning(f"Skipping node due to missing type or name: {node_dict}")
        return None

    try:
        if node_type == "FailureMode":
            return FailureMode(name=node_name, description=node_desc)
        elif node_type == "Observation":
            return Observation(name=node_name, description=node_desc)
        elif node_type == "SensorReading":
            return SensorReading(
                name=node_name,
                description=node_desc,
                unit=node_dict.get('unit')
            )
        else:
            logger.warning(f"Skipping node with unknown type '{node_type}': {node_name}")
            return None
    except Exception as e:
        logger.error(f"Error instantiating node '{node_name}': {e}", exc_info=True)
        return None

def instantiate_relationship(rel_dict: dict, node_map: dict):
    """Instantiates a Pydantic Relationship object from a dictionary."""
    rel_type = rel_dict.get('type')
    source_info = rel_dict.get('source')
    target_info = rel_dict.get('target')
    properties = rel_dict.get('properties', {})

    if not rel_type or not source_info or not target_info:
        logger.warning(f"Skipping relationship due to missing type, source, or target: {rel_dict}")
        return None

    source_type = source_info.get('type')
    source_name = source_info.get('name')
    target_type = target_info.get('type')
    target_name = target_info.get('name')

    source_node = node_map.get((source_type, source_name))
    target_node = node_map.get((target_type, target_name))

    if not source_node:
        logger.warning(f"Skipping relationship: Source node '{source_name}' ({source_type}) not found in map.")
        return None
    if not target_node:
         logger.warning(f"Skipping relationship: Target node '{target_name}' ({target_type}) not found in map.")
         return None

    if not source_node.id or not target_node.id:
        logger.error(f"Skipping relationship: Source or Target node object missing DB ID. Source: {source_node}, Target: {target_node}")
        return None

    try:
        if rel_type == "CAUSES":
            # Type checks can be added here if needed
            return CausesLink(source=source_node, target=target_node)
        elif rel_type == "EVIDENCE_FOR":
            # Safely get enum values
            try:
                when_true = EvidenceStrength(properties.get('when_true_strength', 'suggests'))
            except ValueError:
                logger.warning(f"Invalid when_true_strength '{properties.get('when_true_strength')}' for {source_name}->{target_name}. Defaulting to 'suggests'.")
                when_true = EvidenceStrength.SUGGESTS
            try:
                when_false = EvidenceStrength(properties.get('when_false_strength', 'inconclusive'))
            except ValueError:
                logger.warning(f"Invalid when_false_strength '{properties.get('when_false_strength')}' for {source_name}->{target_name}. Defaulting to 'inconclusive'.")
                when_false = EvidenceStrength.INCONCLUSIVE

            op_str = properties.get('operator')
            operator = None
            if op_str:
                try:
                    operator = ComparisonOperator(op_str)
                except ValueError:
                     logger.warning(f"Invalid operator '{op_str}' for {source_name}->{target_name}. Setting to None.")

            evidence_props = EvidenceProperties(
                when_true_strength=when_true,
                when_false_strength=when_false,
                when_true_rationale=properties.get('when_true_rationale'),
                when_false_rationale=properties.get('when_false_rationale'),
                operator=operator,
                threshold=properties.get('threshold')
            )
            return EvidenceLink(source=source_node, target=target_node, properties=evidence_props)
        else:
            logger.warning(f"Skipping relationship with unknown type '{rel_type}'.")
            return None
    except Exception as e:
        logger.error(f"Error instantiating relationship {source_name}-[{rel_type}]->{target_name}: {e}", exc_info=True)
        return None


def process_json_file(node_manager: NodeManager, file_path: Path, node_map: dict):
    """Loads data from a JSON file and adds nodes/relationships via NodeManager, handling similarities."""
    data = load_json_data(file_path)
    nodes_data = data.get('nodes', [])
    relationships_data = data.get('relationships', [])

    logger.info(f"--- Processing Nodes from {file_path.name} ---")
    node_add_count = 0
    node_similar_count = 0
    node_fail_count = 0
    skipped_similar_nodes = [] # Track skipped nodes and their matches

    current_file_node_map = {} # Track nodes from *this* file before merging with main map

    for node_dict in nodes_data:
        node_obj = instantiate_node(node_dict)
        if not node_obj:
            node_fail_count += 1
            continue

        node_key = (node_obj.type, node_obj.name)

        try:
            # Attempt to add the node. force=False enables similarity check.
            node_id = node_manager.add_node(node_obj, force=False)
            node_obj.id = node_id # Update object with Neo4j ID
            logger.info(f"  Added Node: [cyan]{node_obj.type}[/cyan] '[green]{node_obj.name}[/green]' (ID: {node_id})")
            node_add_count += 1
            current_file_node_map[node_key] = node_obj # Add successfully added node
            node_map[node_key] = node_obj # Add to master map

        except ValueError as e:
            # ValueError signals a similar node was found
            warning_msg = f"  Skipped Node: [cyan]{node_obj.type}[/cyan] '[yellow]{node_obj.name}[/yellow]' - Similar node detected: {e}"
            logger.warning(warning_msg)
            node_similar_count += 1
            
            # Try to parse the existing node name from the exception message
            match = re.search(r"Similar node exists: (.*) \(similarity:", str(e))
            existing_node_name = match.group(1).strip() if match else "Unknown"
            skipped_similar_nodes.append({
                "skipped": node_obj.name,
                "type": node_obj.type,
                "existing": existing_node_name
            })

            # Find the existing node in the master map to use its ID
            # ... (rest of the existing logic in the except block to find existing_node and assign ID)
            existing_node = None
            # Quick check if the exact key exists (e.g., if node reappears in the same file)
            if node_key in node_map:
                 existing_node = node_map[node_key]
            else:
                # If not exact match, perform a find_similar_nodes call to get the ID of the best match
                # This adds an extra call but ensures we link relationships correctly.
                try:
                    similar_nodes = node_manager.find_similar_nodes(node_obj)
                    if similar_nodes and similar_nodes[0].score >= node_manager.similarity_threshold:
                        # Find the node object corresponding to this ID in our master map
                        for key, node in node_map.items():
                            if node.id == similar_nodes[0].id:
                                existing_node = node
                                break
                        if not existing_node:
                             logger.error(f"    Could not find existing node with ID {similar_nodes[0].id} in node_map despite similarity match!")
                    else:
                         logger.error(f"    Similarity error: ValueError raised, but find_similar_nodes did not return a match above threshold for {node_obj.name}. Exception: {e}")

                except Exception as find_err:
                     logger.error(f"    Error calling find_similar_nodes for {node_obj.name} after ValueError: {find_err}", exc_info=True)


            if existing_node and existing_node.id:
                node_obj.id = existing_node.id # Point the current object to the existing node's ID
                current_file_node_map[node_key] = node_obj # Add to this file's map for relationship linking
                logger.info(f"    Using existing node ID: {existing_node.id} for relationships.")
            else:
                logger.error(f"    Failed to find existing node ID for '{node_obj.name}'. Relationships involving this node may fail.")
                node_fail_count +=1

        except Exception as e:
            logger.error(f"  Failed Node: [cyan]{node_obj.type}[/cyan] '[red]{node_obj.name}[/red]' - Error: {e}", exc_info=True)
            node_fail_count += 1

    logger.info(f"[green]{node_add_count} nodes added[/green], [yellow]{node_similar_count} similar nodes skipped[/yellow], [red]{node_fail_count} nodes failed[/red].")

    # Report skipped nodes if any
    if skipped_similar_nodes:
        console.print(f"[bold yellow]Overlap Report for {file_path.name}:[/bold yellow]")
        for item in skipped_similar_nodes:
            console.print(f"  - Skipped '{item['skipped']}' ({item['type']}) -> Matched existing '{item['existing']}'")

    # Update the master map with nodes processed from this file (including those pointing to existing IDs)
    node_map.update(current_file_node_map)

    logger.info(f"--- Processing Relationships from {file_path.name} ---")
    rel_add_count = 0
    rel_skip_count = 0
    rel_fail_count = 0

    for rel_dict in relationships_data:
        # Use the potentially updated master node_map which contains correct IDs
        rel_obj = instantiate_relationship(rel_dict, node_map)

        if not rel_obj:
            rel_skip_count += 1
            continue

        try:
            rel_id = node_manager.add_relationship(rel_obj)
            rel_add_count += 1
            # logger.info(f"  Added Relationship: ({rel_obj.source.name})-[{rel_obj.type}]->({rel_obj.target.name}) (ID: {rel_id})")
        except Exception as e:
            logger.error(f"  Failed Relationship: ({rel_obj.source.name})-[{rel_obj.type}]->({rel_obj.target.name}) - Error: {e}", exc_info=True)
            rel_fail_count += 1

    logger.info(f"[green]{rel_add_count} relationships added[/green], [yellow]{rel_skip_count} relationships skipped[/yellow], [red]{rel_fail_count} relationships failed[/red].")

    return node_map


def main():
    parser = argparse.ArgumentParser(description="Load data from multiple JSON files into Neo4j using NodeManager, demonstrating similarity merging.")
    parser.add_argument(
        "json_files",
        type=str,
        nargs='+', # Accept one or more json files
        help="Paths to the JSON files containing nodes and relationships (e.g., gen1.json gen2.json).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the Neo4j database before loading new data."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Similarity threshold for merging nodes (0.0 to 1.0)."
    )
    args = parser.parse_args()

    console.print(Panel(f"Starting Merge Example Script for: [cyan]{', '.join(args.json_files)}[/cyan] (Threshold: {args.threshold})", title="Node Merge Demo", border_style="blue"))

    db_connection = None
    node_manager = None
    try:
        # 1. Setup Environment & Get DB Connection
        db_connection = setup_environment()

        # 2. Initialize NodeManager
        logger.info(f"Initializing NodeManager (Similarity Threshold: {args.threshold})...")
        # IMPORTANT: initialize_vector_index=True loads existing nodes for comparison
        node_manager = NodeManager(db=db_connection, similarity_threshold=args.threshold, initialize_vector_index=True)
        logger.info("[green]NodeManager initialized.[/green]")

        # 3. Clear database if requested
        if args.clear:
            clear_database(db_connection)
            # Re-initialize NodeManager AFTER clearing to ensure vector index is fresh
            logger.info("Re-initializing NodeManager after clearing database...")
            # Reset the vector index store explicitly before re-indexing
            if node_manager.vector_index:
                node_manager.vector_index.index_all_nodes_from_graph(db_connection) # Re-index (should be empty)
            else:
                logger.warning("Vector index was not initialized, skipping reset/re-index after clear.")
            logger.info("[green]NodeManager re-initialized.[/green]")


        # 4. Process each JSON file sequentially
        master_node_map = {} # Keep track of all nodes added or mapped across files
        for file_str in args.json_files:
            json_file_path = Path(file_str)
            if not json_file_path.exists():
                 logger.error(f"Input file not found: {json_file_path}. Skipping.")
                 continue
            master_node_map = process_json_file(node_manager, json_file_path, master_node_map)
            logger.info("-" * 20) # Separator between files


        console.print(Panel("[bold green]Processing completed successfully![/bold green]", border_style="green"))

    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Script aborted due to error: {e}", exc_info=True)
        console.print(Panel("[bold red]Script aborted due to errors.[/bold red]", border_style="red"))
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        console.print(Panel("[bold red]An unexpected error occurred.[/bold red]", border_style="red"))
    finally:
        if db_connection:
            db_connection.close()
            logger.info("Neo4j connection closed.")

if __name__ == "__main__":
    main() 
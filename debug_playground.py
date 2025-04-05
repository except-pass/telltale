"""Debug playground for experimenting with the node manager."""

from telltale.core.node_manager import NodeManager
from telltale.core.database import Neo4jConnection
from telltale.core.example_data import ExampleScenarios
from telltale.core.models import EvidenceStrength, EvidenceLink, CausesLink, Observation
from telltale.core.llm_parser import LLMParser
from rich import print
import json
import os
from pathlib import Path
import hashlib
from typing import Optional
from rich.console import Console
from rich.panel import Panel

# Cache for LLM results
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

class CachingLLMParser(LLMParser):
    """A custom LLM parser that caches results to avoid repeated API calls."""
    
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    def parse_text(self, text: str) -> dict:
        """Parse text into nodes and relationships, using cache if available."""
        # Try to get cached result first
        cached_result = get_cached_llm_result(text)
        if cached_result:
            print("[dim]Using cached LLM result[/dim]")
            return cached_result
            
        # No cached result - call API and cache the result
        result = super().parse_text(text)
        save_llm_result(text, result)
        return result

def get_cached_llm_result(text: str) -> Optional[dict]:
    """Get cached LLM result for the given text if it exists."""
    cache_file = "llm_cache.json"
    if not os.path.exists(cache_file):
        return None
        
    try:
        with open(cache_file, "r") as f:
            cache = json.load(f)
            
        # Use text as key
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return cache.get(text_hash)
    except Exception:
        return None
        
def save_llm_result(text: str, result: dict):
    """Save LLM result to cache."""
    cache_file = "llm_cache.json"
    
    # Load existing cache
    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cache = json.load(f)
        except Exception:
            pass
            
    # Add new result
    text_hash = hashlib.md5(text.encode()).hexdigest()
    cache[text_hash] = result
    
    # Save updated cache
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"[red]Warning: Failed to save to cache: {e}[/red]")

def clear_database():
    """Clear all nodes and relationships from the database."""
    db = Neo4jConnection()
    db.run_query("MATCH (n) DETACH DELETE n")
    print("[yellow]Database cleared[/yellow]")

def load_example_data():
    """Load example diagnostic scenarios into the database."""
    db = Neo4jConnection()
    scenarios = ExampleScenarios(db)
    
    print("[green]Loading example scenarios...[/green]")
    scenarios.add_basic_scenarios()
    scenarios.add_broken_speaker_wire_scenario()
    print("[green]Example scenarios loaded successfully![/green]")

def display_triple(source_name: str, dest_name: str, when_true: str, when_false: str, operator: str = None, threshold: float = None):
    """Display a triple in natural language format."""
    condition = source_name
    if operator and threshold is not None:
        condition = f"{source_name} {operator} {threshold}"
    
    print(f"If it is true that {condition}, then it {when_true} {dest_name}")
    print(f"If it is false that {condition}, then it {when_false} {dest_name}")

def display_proposed_changes(nodes, relationships):
    """Display proposed nodes and relationships before applying them."""
    print("\n[bold]Proposed Changes:[/bold]")
    print("[dim]These changes will be applied to the database if you proceed.[/dim]")
    
    print("\n[bold]Proposed Nodes:[/bold]")
    for node in nodes:
        print(f"- {node.type}: {node.name}")
        if node.description:
            print(f"  Description: {node.description}")
        if hasattr(node, 'unit') and node.unit:
            print(f"  Unit: {node.unit}")
    
    print("\n[bold]Proposed Relationships:[/bold]")
    for rel in relationships:
        if rel.type == "CausesLink":
            print(f"- {rel.source.name} [cyan]CAUSES[/cyan] {rel.dest.name}")
        elif rel.type == "EvidenceLink":
            # For evidence links, we need to handle evidence strengths
            when_true = rel.when_true_strength or EvidenceStrength.SUGGESTS
            when_false = rel.when_false_strength or EvidenceStrength.INCONCLUSIVE
            
            # For sensor readings, we might have operator and threshold
            operator = getattr(rel, 'operator', None)
            threshold = getattr(rel, 'threshold', None)
            
            display_triple(rel.source.name, rel.dest.name, when_true.value, when_false.value, 
                         operator.value if operator else None, threshold)
        else:
            print(f"[yellow]Warning: Unknown relationship type: {rel.type}[/yellow]")

def display_database_state():
    """Display current state of the database."""
    print("\n[bold]Current Database State:[/bold]")
    db = Neo4jConnection()
    
    print("\nFailure Modes:")
    result = db.run_query("MATCH (n:FailureMode) RETURN n.name")
    for row in result:
        print(f"- {row['n.name']}")
    
    print("\nObservations:")
    result = db.run_query("MATCH (n:Observation) RETURN n.name")
    for row in result:
        print(f"- {row['n.name']}")
    
    print("\nSensor Readings:")
    result = db.run_query("MATCH (n:SensorReading) RETURN n.name, n.unit")
    for row in result:
        unit_str = f" ({row['n.unit']})" if row['n.unit'] else ""
        print(f"- {row['n.name']}{unit_str}")
    
    print("\n[bold]Relationships and Evidence Rules:[/bold]")
    result = db.run_query("""
        MATCH (a)-[r]->(b)
        RETURN type(r) as type, a.name as from, b.name as to,
               CASE WHEN type(r) = 'EVIDENCE_FOR' 
                    THEN r.when_true_strength 
                    ELSE NULL 
               END as when_true,
               CASE WHEN type(r) = 'EVIDENCE_FOR' 
                    THEN r.when_false_strength 
                    ELSE NULL 
               END as when_false,
               r.operator as operator,
               r.threshold as threshold
    """)
    
    # First display CAUSES relationships
    print("\nCausal Rules:")
    for row in result:
        if row['type'] == 'CAUSES':
            print(f"- {row['from']} [cyan]CAUSES[/cyan] {row['to']}")
    
    # Then display EVIDENCE_FOR relationships as triples
    print("\nEvidence Rules:")
    for row in result:
        if row['type'] == 'EVIDENCE_FOR':
            display_triple(row['from'], row['to'], row['when_true'], row['when_false'],
                         row['operator'], row['threshold'])

def auto_accept_process(manager, prompt: str):
    """Process natural language with automatic acceptance of highly similar nodes.
    
    Args:
        manager: NodeManager instance to use for processing
        prompt: Natural language prompt to process
    """
    # Parse the prompt
    nodes, relationships = manager.parse_prompt(prompt)
    
    # Process each node
    for node in nodes:
        # First check for similar nodes
        similar = manager.find_similar_nodes(node)
        
        print(f"\n[bold]Checking similarity for node:[/bold] {node.type}: {node.name}")
        print(f"  Similarity threshold: {manager.similarity_threshold}")
        
        if similar:
            # Print top matches
            print("  Top similarity matches:")
            for i, match in enumerate(similar[:3]):
                print(f"  {i+1}. {match.name} ({match.type}): {match.score:.4f}")
        
        if similar and similar[0].score > 0.9:
            # Use the similar node if high similarity
            print(f"\nAutomatically using existing node: {similar[0].name} (similarity: {similar[0].score:.2f})")
            node.id = similar[0].id
        elif similar and similar[0].score >= manager.similarity_threshold:
            # Use the similar node if above threshold
            print(f"\nUsing similar existing node: {similar[0].name} (similarity: {similar[0].score:.2f})")
            node.id = similar[0].id
        elif similar:
            # Show options if some similar nodes found
            print(f"\nFound similar node for: {node.name}")
            for i, s in enumerate(similar[:5], 1):
                print(f"{i}. {s.name} (similarity: {s.score:.2f})")
            print("0. Create new node anyway")
            
            choice = "0"  # Always create new node if no high similarity match
            if choice == "0":
                print(f"Found similar node but not similar enough, adding new node: {node.name}")
                manager.add_node(node, force=True)
            else:
                node.id = similar[int(choice)-1].id
        else:
            # No similar nodes found, add new node
            try:
                print(f"No similar nodes found, adding new node: {node.name}")
                manager.add_node(node, force=True)
            except ValueError as e:
                print(f"[red]Warning: Failed to add node: {e}[/red]")
    
    # Process relationships - simpler approach with no special casing
    for rel in relationships:
        try:
            # Simply add the relationship with no special handling
            manager.add_relationship(rel)
        except Exception as e:
            print(f"[red]Warning: Failed to add relationship: {e}[/red]")
    
    return nodes, relationships

def setup_environment():
    """Set up the environment for testing."""
    # Initialize the node manager with our custom parser
    api_key = os.environ.get("OPENAI_API_KEY")
    parser = CachingLLMParser(api_key=api_key)
    db = Neo4jConnection()
    manager = NodeManager(db=db, parser=parser, similarity_threshold=0.8)
    manager.parser = parser
    
    # Clear the database before starting
    clear_database()
    
    # Load example data
    load_example_data()
    
    # Show initial database state
    print("\n[bold]Initial Database State:[/bold]")
    display_database_state()
    
    return manager

def run_test_1(manager):
    """Run Test 1: Parse a prompt and show proposed changes without adding to the database.
    
    Args:
        manager: NodeManager instance to use for the test
    """
    # Define the test prompt
    prompt = "There is also an LED on the toy. The LED should light up when the button is pressed. If it doesn't it might mean a dead battery, or the device is off. The LED will still light even in mute mode"
    
    print("\n[bold]Test 1: Parsing a prompt and showing proposed changes[/bold]")
    print(f"Prompt: {prompt}")
    
    # Parse the prompt and get nodes and relationships
    nodes, relationships = manager.parse_prompt(prompt)
    display_proposed_changes(nodes, relationships)
    
    return prompt

def run_test_2(manager, prompt):
    """Run Test 2: Add nodes and check for similar ones.
    
    Args:
        manager: NodeManager instance to use for the test
        prompt: Prompt to process
    """
    print("\n[bold]Test 2: Adding nodes and checking for similar ones[/bold]")
    try:
        # First parse and show proposed changes
        print(f"\n[bold]Parsing prompt:[/bold] {prompt}")
        nodes, relationships = manager.parse_prompt(prompt)
        display_proposed_changes(nodes, relationships)
        
        # Then process the changes
        print("\n[bold]Processing changes...[/bold]")
        auto_accept_process(manager, prompt)
        display_database_state()
    except Exception as e:
        print(f"[red]Error:[/red] {e}")

def print_similarity_debug(manager, node_name, existing_node_name):
    """Print debug information about similarity between two nodes.
    
    Args:
        manager: NodeManager instance to use
        node_name: Name of the first node
        existing_node_name: Name of the existing node to compare with
    """
    # Create a temporary node for testing similarity
    test_node = Observation(name=node_name)
    
    # Find similar nodes
    similar_nodes = manager.find_similar_nodes(test_node)
    
    # Print similarity scores
    print(f"\n[bold]Similarity Debug for '{node_name}':[/bold]")
    for node in similar_nodes:
        print(f"- {node.name} (similarity: {node.score:.4f})")
        if node.name == existing_node_name:
            print(f"  [yellow]Found target node: {existing_node_name}[/yellow]")
    
    # Print threshold
    print(f"Similarity threshold: {manager.similarity_threshold}")

def run_test_3(manager):
    """Run Test 3: Add similar nodes.
    
    Args:
        manager: NodeManager instance to use for the test
    """
    print("\n[bold]Test 3: Adding similar nodes[/bold]")
    similar_prompt = "When the battery dies, there is no audio output."
    try:
        # Debug similarity between "No Audio Output" and "No Music"
        print_similarity_debug(manager, "No Audio Output", "No Music")
        
        # Parse the prompt and get nodes and relationships
        nodes, relationships = manager.parse_prompt(similar_prompt)
        display_proposed_changes(nodes, relationships)
        
        # Process the prompt using the same auto_accept_process as Test 2
        auto_accept_process(manager, similar_prompt)
        display_database_state()
    except Exception as e:
        print(f"[red]Error:[/red] {e}")

def clear_llm_cache():
    """Clear the LLM cache file."""
    cache_file = "llm_cache.json"
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("[yellow]LLM cache cleared[/yellow]")
    else:
        print("[yellow]No LLM cache to clear[/yellow]")

def test_explain_why():
    """Test the 'explain why' feature of the diagnostic engine."""
    from telltale.core.diagnostic import DiagnosticEngine
    
    console = Console()
    
    console.print("\n[bold yellow]Testing 'Explain Why' Feature[/bold yellow]")
    
    # Initialize diagnostic engine
    engine = DiagnosticEngine()
    
    # Example 1: Car won't start scenario
    console.print("\n[bold cyan]Example 1: Car won't start[/bold cyan]")
    
    observations = ["Car won't start", "No lights on dashboard", "Engine won't crank"]
    sensor_readings = {"Battery voltage": 3.0}
    
    # Run diagnosis
    results = engine.diagnose(observations, sensor_readings, include_explanations=True)
    
    # Print diagnosis and explanation
    for result in results:
        console.print(Panel(f"[bold green]Diagnosis:[/bold green] {result.failure_mode} ({result.confidence.value})", 
                           expand=False))
        
        if result.explanation:
            console.print("[bold blue]Evidence and Explanation:[/bold blue]")
            console.print(result.explanation)
            console.print("\n[bold blue]Supporting Evidence:[/bold blue]", result.supporting_evidence)
            console.print("\n[bold blue]Contradicting Evidence:[/bold blue]", result.contradicting_evidence)
    
    # Example 2: Explain a specific diagnosis
    console.print("\n[bold cyan]Example 2: Explain specific diagnosis[/bold cyan]")
    
    explanation = engine.explain_diagnosis_text("Dead battery", observations, sensor_readings)
    console.print(Panel("[bold blue]Dead battery explanation:[/bold blue]", expand=False))
    console.print(explanation)
    
    # Example 3: Audio system diagnosis
    console.print("\n[bold cyan]Example 3: Audio system issue[/bold cyan]")
    
    audio_observations = ["No music", "Speakers silent", "Buzzing sound"]
    audio_sensor_readings = {"Speaker impedance": 0.5, "Speaker voltage": 12.0}
    
    # Run diagnosis
    audio_results = engine.diagnose(audio_observations, audio_sensor_readings, include_explanations=True)
    
    # Print diagnosis and explanation
    for result in audio_results:
        console.print(Panel(f"[bold green]Diagnosis:[/bold green] {result.failure_mode} ({result.confidence.value})", 
                           expand=False))
        
        if result.explanation:
            console.print("[bold blue]Evidence and Explanation:[/bold blue]")
            console.print(result.explanation)
    
    # Example 4: Battery voltage edge cases
    console.print("\n[bold cyan]Example 4: Battery voltage edge cases[/bold cyan]")
    
    # Test different battery voltages
    voltage_cases = [
        {"observations": ["Car won't start"], "voltage": 2.0, "label": "Very low voltage"},
        {"observations": ["Car won't start"], "voltage": 6.0, "label": "Low voltage"},
        {"observations": ["Car won't start"], "voltage": 12.0, "label": "Normal voltage"},
        {"observations": ["Car won't start"], "voltage": 14.5, "label": "High voltage"}
    ]
    
    for case in voltage_cases:
        console.print(f"\n[bold magenta]{case['label']} ({case['voltage']}V):[/bold magenta]")
        case_results = engine.diagnose(
            case["observations"], 
            {"Battery voltage": case["voltage"]},
            include_explanations=True
        )
        
        if case_results:
            # Get the first diagnosis related to battery
            battery_diagnosis = next((r for r in case_results if "battery" in r.failure_mode.lower()), None)
            if battery_diagnosis:
                console.print(f"[green]Battery-related diagnosis:[/green] {battery_diagnosis.failure_mode}")
                battery_evidence = engine.explain_diagnosis(
                    battery_diagnosis.failure_mode, 
                    case["observations"], 
                    {"Battery voltage": case["voltage"]}
                )
                
                for evidence in battery_evidence:
                    if evidence.type == "sensor_reading" and evidence.name == "Battery voltage":
                        console.print(f"[blue]Battery voltage evidence:[/blue] {evidence.explanation}")
                        console.print(f"[blue]For or against:[/blue] {evidence.for_or_against}")
                        console.print(f"[blue]Strength:[/blue] {evidence.strength.value}")
        else:
            console.print("[yellow]No diagnoses found for this case[/yellow]")
            
    # Example 5: Get causal paths
    console.print("\n[bold cyan]Example 5: Causal paths[/bold cyan]")
    
    failure_mode = "Dead battery"
    obs = ["Car won't start", "No lights on dashboard"]
    
    causal_paths = engine.get_causal_paths(failure_mode, obs)
    
    console.print(f"[bold blue]Causal paths for '{failure_mode}':[/bold blue]")
    for i, path in enumerate(causal_paths):
        console.print(f"\n[bold]Path {i+1}:[/bold]")
        console.print(f"- {path['failure_mode']} CAUSES {path['observation']}")
        if path.get('intermediate_nodes'):
            for node in path['intermediate_nodes']:
                console.print(f"  └─> {node}")

def main():
    """Main function for debug playground."""
    # Setup environment
    setup_environment()
    
    # Create node manager with API key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    llm_parser = CachingLLMParser(api_key=api_key)
    db = Neo4jConnection()
    manager = NodeManager(db=db, parser=llm_parser, similarity_threshold=0.8)
    
    # Run different tests based on command line arguments
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "clear":
            clear_database()
        elif sys.argv[1] == "load":
            clear_database()
            load_example_data()
        elif sys.argv[1] == "state":
            display_database_state()
        elif sys.argv[1] == "clearcache":
            clear_llm_cache()
        elif sys.argv[1] == "explainwhy":
            test_explain_why()
        elif sys.argv[1] == "test1":
            run_test_1(manager)
        elif sys.argv[1] == "test2":
            prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
            run_test_2(manager, prompt)
        elif sys.argv[1] == "test3":
            run_test_3(manager)
    else:
        print("[yellow]No command specified. Available commands:[/yellow]")
        print("  clear - Clear the database")
        print("  load - Load example data")
        print("  state - Display database state")
        print("  clearcache - Clear LLM parsing cache")
        print("  explainwhy - Test explain why feature")
        print("  test1 - Run test 1 (matching similar nodes)")
        print("  test2 <prompt> - Run test 2 with the given prompt")
        print("  test3 - Run test 3 (automatic processing)")

if __name__ == "__main__":
    main() 
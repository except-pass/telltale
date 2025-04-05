import logging
from typing import List, Optional, Dict
import sys
import os
import subprocess

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from telltale.core.database import Neo4jConnection
from telltale.core.diagnostic import DiagnosticEngine
from telltale.core.models import DiagnosticResult, TestRecommendation, EvidenceStrength
from telltale.core.example_data import ExampleScenarios

app = typer.Typer(help="Telltale: A Knowledge Graph-Based Diagnostic Assistant")
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@app.command()
def init_db(
    clear_existing: bool = typer.Option(False, "--clear", "-c", help="Clear existing database data"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
):
    """Initialize the Neo4j database schema."""
    if clear_existing and not force:
        if not typer.confirm("This will delete all existing data. Are you sure?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return

    with console.status("[bold green]Initializing database schema...") as status:
        try:
            db = Neo4jConnection()
            
            if clear_existing:
                status.update("[bold yellow]Clearing existing database...")
                db.run_query('MATCH (n) DETACH DELETE n')
            
            status.update("[bold green]Creating schema constraints...")
            # Add unique constraints for node types
            db.run_query("""
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:FailureMode) REQUIRE n.name IS UNIQUE
            """)
            db.run_query("""
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Observation) REQUIRE n.name IS UNIQUE
            """)
            db.run_query("""
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:SensorReading) REQUIRE n.name IS UNIQUE
            """)
            
            console.print(":white_check_mark: [bold green]Database schema initialized successfully!")
        except Exception as e:
            console.print(f":x: [bold red]Error initializing database schema: {e}")
            raise typer.Exit(code=1)
        finally:
            db.close()


@app.command()
def load_examples(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
):
    """Load example diagnostic scenarios into the database."""
    if not force:
        if not typer.confirm("This will add example scenarios to the database. Existing scenarios with the same names will be updated. Continue?"):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return

    with console.status("[bold green]Loading example scenarios...") as status:
        try:
            db = Neo4jConnection()
            scenarios = ExampleScenarios(db)
            
            status.update("[bold green]Adding basic scenarios...")
            scenarios.add_basic_scenarios()
            
            status.update("[bold green]Adding broken speaker wire scenario...")
            scenarios.add_broken_speaker_wire_scenario()
            
            console.print(":white_check_mark: [bold green]Example scenarios loaded successfully!")
        except Exception as e:
            console.print(f":x: [bold red]Error loading example scenarios: {e}")
            raise typer.Exit(code=1)
        finally:
            db.close()


@app.command()
def diagnose(
    observations: List[str] = typer.Argument(None, help="List of observations to diagnose"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Include detailed explanations"),
    sensor_name: Optional[List[str]] = typer.Option(None, "--sensor-name", "-sn", help="Name of sensor reading"),
    sensor_value: Optional[List[float]] = typer.Option(None, "--sensor-value", "-sv", help="Value of sensor reading")
):
    """Diagnose potential failure modes based on observations."""
    if not observations and not interactive:
        console.print("[bold yellow]No observations provided. Use --interactive or provide observations as arguments.")
        raise typer.Exit(code=1)
    
    # Validate that sensor names and values have matching lengths
    if sensor_name and sensor_value and len(sensor_name) != len(sensor_value):
        console.print("[bold red]Error: Number of sensor names must match number of sensor values")
        raise typer.Exit(code=1)
        
    # Create sensor readings dictionary
    sensor_readings = {}
    if sensor_name and sensor_value:
        sensor_readings = dict(zip(sensor_name, sensor_value))
    
    user_observations = observations.copy() if observations else []
    
    try:
        db = Neo4jConnection()
        db.connect()
        engine = DiagnosticEngine()
        
        if interactive:
            user_observations = run_interactive_session(engine, initial_observations=user_observations)
        else:
            display_diagnosis(engine, user_observations, sensor_readings, include_explanations=explain)
            recommend_next_steps(engine, user_observations)
    except Exception as e:
        console.print(f"[bold red]Error during diagnosis: {e}")
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def test(
    observation: str = typer.Argument(..., help="Single observation to test"),
    sensor_name: Optional[List[str]] = typer.Option(None, "--sensor-name", "-sn", help="Name of sensor reading"),
    sensor_value: Optional[List[float]] = typer.Option(None, "--sensor-value", "-sv", help="Value of sensor reading"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Include detailed explanations")
):
    """Test the impact of a single observation."""
    try:
        # Validate that sensor names and values have matching lengths
        if sensor_name and sensor_value and len(sensor_name) != len(sensor_value):
            console.print("[bold red]Error: Number of sensor names must match number of sensor values")
            raise typer.Exit(code=1)
            
        # Create sensor readings dictionary
        sensor_readings = {}
        if sensor_name and sensor_value:
            sensor_readings = dict(zip(sensor_name, sensor_value))
        
        db = Neo4jConnection()
        db.connect()
        engine = DiagnosticEngine()
        
        user_observations = [observation]
        
        display_diagnosis(engine, user_observations, sensor_readings, include_explanations=explain)
        recommend_next_steps(engine, user_observations)
    except Exception as e:
        console.print(f"[bold red]Error during test: {e}")
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run the Streamlit UI on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to run the Streamlit UI on")
):
    """Launch the Streamlit web UI for an interactive diagnostic session."""
    try:
        # Find the UI directory
        from telltale.ui import app as ui_app
        ui_dir = os.path.dirname(os.path.abspath(ui_app.__file__))
        app_path = os.path.join(ui_dir, "app.py")
        
        # Check if the file exists
        if not os.path.exists(app_path):
            console.print(f"[bold red]Error: UI app not found at {app_path}")
            raise typer.Exit(code=1)
        
        # Run the Streamlit app
        console.print(f"[bold green]Starting Telltale UI on http://{host}:{port} ...[/bold green]")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        
        cmd = ["streamlit", "run", app_path, f"--server.port={port}", f"--server.address={host}"]
        subprocess.run(cmd)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]UI stopped by user[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Error starting UI: {e}")
        console.print("[yellow]Make sure streamlit is installed: pip install streamlit[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def explain(
    failure_mode: str = typer.Argument(..., help="The failure mode to explain"),
    observations: List[str] = typer.Option(None, "--observation", "-o", help="Observation that is true"),
    sensor_name: Optional[List[str]] = typer.Option(None, "--sensor-name", "-sn", help="Name of sensor reading"),
    sensor_value: Optional[List[float]] = typer.Option(None, "--sensor-value", "-sv", help="Value of sensor reading")
):
    """
    Explain why a particular failure mode might be the diagnosis.
    
    This command takes a failure mode and traces back through the diagnostic graph
    to show the evidence and causal paths that led to this diagnosis.
    """
    try:
        # Validate that sensor names and values have matching lengths
        if sensor_name and sensor_value and len(sensor_name) != len(sensor_value):
            console.print("[bold red]Error: Number of sensor names must match number of sensor values")
            raise typer.Exit(code=1)
            
        # Create sensor readings dictionary
        sensor_readings = {}
        if sensor_name and sensor_value:
            sensor_readings = dict(zip(sensor_name, sensor_value))
        
        db = Neo4jConnection()
        db.connect()
        engine = DiagnosticEngine()
        
        # Verify that the failure mode exists
        failure_modes = db.run_query(
            "MATCH (fm:FailureMode {name: $name}) RETURN fm.name", 
            {"name": failure_mode}
        )
        
        if not failure_modes:
            console.print(f"[bold red]Error: Failure mode '{failure_mode}' not found in the database")
            raise typer.Exit(code=1)
        
        observations = observations or []
        
        # Get explanation
        explanation = engine.explain_diagnosis_text(failure_mode, observations, sensor_readings)
        
        # Display explanation in a panel
        console.print(Panel(explanation, title=f"Explanation for: {failure_mode}", 
                           border_style="cyan", expand=False))
        
        # Display evidence details
        evidence_list = engine.explain_diagnosis(failure_mode, observations, sensor_readings)
        
        if evidence_list:
            # Display evidence table
            table = Table(title="Evidence Details")
            table.add_column("Evidence", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Strength", style="green")
            table.add_column("For/Against", style="yellow")
            table.add_column("Details", style="white")
            
            for evidence in evidence_list:
                strength_color = {
                    EvidenceStrength.CONFIRMS: "bold green",
                    EvidenceStrength.SUGGESTS: "bold yellow",
                    EvidenceStrength.SUGGESTS_AGAINST: "bold red",
                    EvidenceStrength.RULES_OUT: "bold red",
                    EvidenceStrength.INCONCLUSIVE: "dim white",
                }.get(evidence.strength, "white")
                
                for_against_color = "green" if evidence.for_or_against == "for" else "red"
                
                details = ""
                if evidence.type == "sensor_reading" and evidence.operator and evidence.threshold is not None:
                    details = f"{evidence.name} {evidence.operator} {evidence.threshold}"
                    if evidence.actual_value is not None:
                        details += f" (actual: {evidence.actual_value})"
                
                table.add_row(
                    evidence.name,
                    evidence.type,
                    f"[{strength_color}]{evidence.strength.value}[/{strength_color}]",
                    f"[{for_against_color}]{evidence.for_or_against}[/{for_against_color}]",
                    details
                )
            
            console.print(table)
            
            # Display causal paths
            causal_paths = engine.get_causal_paths(failure_mode, observations)
            if causal_paths:
                console.print("\n[bold cyan]Causal Paths:[/bold cyan]")
                console.print("The following causal paths connect this failure mode to the observations:")
                
                for i, path in enumerate(causal_paths):
                    console.print(f"\n[bold]Path {i+1}:[/bold]")
                    console.print(f"- {path['failure_mode']} [cyan]CAUSES[/cyan] {path['observation']}")
                    if path.get('intermediate_nodes'):
                        for node in path['intermediate_nodes']:
                            console.print(f"  └─> {node}")
        else:
            console.print("[yellow]No specific evidence found for this diagnosis with the provided observations and sensor readings.")
    
    except Exception as e:
        console.print(f"[bold red]Error explaining diagnosis: {e}")
        raise typer.Exit(code=1)
    finally:
        db.close()


def display_diagnosis(engine: DiagnosticEngine, observations: List[str], 
                     sensor_readings: Optional[Dict[str, float]] = None,
                     include_explanations: bool = False) -> None:
    """Display diagnostic results in a table."""
    results = engine.diagnose(observations, sensor_readings, include_explanations=include_explanations)
    
    if not results:
        console.print(Panel("[yellow]No failure modes identified based on the given observations.", 
                    title="Diagnostic Results", border_style="yellow"))
        return
    
    table = Table(title="Diagnostic Results")
    table.add_column("Failure Mode", style="cyan")
    table.add_column("Confidence", style="magenta")
    table.add_column("Supporting Evidence", style="green")
    
    for result in results:
        confidence_color = {
            EvidenceStrength.CONFIRMS: "bold green",
            EvidenceStrength.SUGGESTS: "bold yellow",
            EvidenceStrength.INCONCLUSIVE: "dim white",
        }.get(result.confidence, "white")
        
        table.add_row(
            result.failure_mode,
            f"[{confidence_color}]{result.confidence.value}[/{confidence_color}]",
            ", ".join(result.supporting_evidence) if result.supporting_evidence else "None"
        )
    
    console.print(table)
    
    # Show detailed explanations if requested
    if include_explanations:
        for result in results:
            if result.explanation:
                console.print("\n")
                console.print(Panel(result.explanation, 
                               title=f"Explanation for: {result.failure_mode}", 
                               border_style="cyan", 
                               expand=False))


def recommend_next_steps(engine: DiagnosticEngine, observations: List[str]) -> List[TestRecommendation]:
    """Display and return recommended next steps."""
    recommendations = engine.get_test_recommendations(observations)
    
    if not recommendations:
        console.print(Panel("[yellow]No further tests recommended.", 
                    title="Recommended Next Steps", border_style="yellow"))
        return []
    
    table = Table(title="Recommended Next Steps")
    table.add_column("Test", style="cyan")
    table.add_column("Type", style="blue")
    table.add_column("Impact", style="magenta")
    table.add_column("Details", style="green")
    table.add_column("Would Help With", style="yellow")
    
    for rec in recommendations:
        impact_color = {
            EvidenceStrength.CONFIRMS: "bold green",
            EvidenceStrength.RULES_OUT: "bold red",
            EvidenceStrength.SUGGESTS: "bold yellow",
        }.get(rec.strength_if_true, "white")
        
        details = ""
        if rec.operator and rec.threshold is not None:
            details = f"{rec.operator} {rec.threshold}"
        
        table.add_row(
            rec.name,
            rec.type,
            f"[{impact_color}]{rec.strength_if_true.value}[/{impact_color}]",
            details,
            ", ".join(rec.would_help_with)
        )
    
    console.print(table)
    return recommendations


def run_interactive_session(engine: DiagnosticEngine, initial_observations: List[str] = None) -> List[str]:
    """Run an interactive diagnostic session with the user."""
    observations = initial_observations.copy() if initial_observations else []
    
    console.print(Panel(
        "[bold]Welcome to the interactive diagnostic session![/bold]\n"
        "I'll help you diagnose problems by asking questions and suggesting tests.\n"
        "You can exit anytime by typing 'exit' or 'quit'.",
        title="Telltale Diagnostic Assistant",
        border_style="green"
    ))
    
    if observations:
        console.print(f"[bold]Starting with observations:[/bold] {', '.join(observations)}")
    
    while True:
        # Display current diagnosis
        if observations:
            console.print("\n[bold cyan]Current Observations:[/bold]", ", ".join(observations))
            display_diagnosis(engine, observations)
        
        # Get recommendations
        recommendations = recommend_next_steps(engine, observations)
        
        if not recommendations:
            console.print("[bold green]Diagnosis complete! No further tests recommended.")
            break
        
        # Ask user for next action
        console.print("\n[bold cyan]What would you like to do next?[/bold]")
        choice = typer.prompt(
            "Enter the number of a recommended test, add a new observation, or type 'exit'",
            default="1"
        )
        
        if choice.lower() in ('exit', 'quit', 'q'):
            break
        
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(recommendations):
                # User selected a recommendation
                selected = recommendations[choice_idx]
                
                if selected.type == "observation":
                    has_observation = typer.confirm(f"Do you observe '{selected.name}'?")
                    if has_observation:
                        observations.append(selected.name)
                else:  # sensor_reading
                    value = typer.prompt(f"Enter value for {selected.name}")
                    try:
                        value = float(value)
                        console.print(f"[green]Recorded sensor {selected.name} = {value}")
                        # Logic to evaluate sensor reading against threshold would go here
                        # For now, we just add it to observations as a simplification
                        observations.append(selected.name)
                    except ValueError:
                        console.print("[bold red]Invalid value. Please enter a number.")
            else:
                # User is adding a custom observation
                new_obs = choice
                if new_obs and new_obs not in observations:
                    observations.append(new_obs)
                    console.print(f"[green]Added observation: {new_obs}")
                else:
                    console.print("[yellow]Observation already recorded or invalid.")
        except ValueError:
            # Treat as a custom observation
            if choice and choice not in observations:
                observations.append(choice)
                console.print(f"[green]Added observation: {choice}")
            else:
                console.print("[yellow]Observation already recorded or invalid.")
    
    return observations


if __name__ == "__main__":
    app() 
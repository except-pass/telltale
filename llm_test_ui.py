"""Streamlit UI for testing LLM parsing of diagnostic text."""

import streamlit as st
import streamlit.components.v1 as components
import os
from pathlib import Path
from telltale.core.llm_parser import LLMParser
from telltale.core.database import Neo4jConnection
from telltale.core.truth_table import TruthTable
from telltale.core.diagnostic import DiagnosticEngine
from rich import print
import json

@st.cache_data
def load_example_prompts():
    """Load example prompts from the examples/prompts directory."""
    prompts_dir = Path("examples/prompts")
    if not prompts_dir.exists():
        return []
    
    prompts = []
    for file in prompts_dir.glob("*.txt"):
        with open(file, "r") as f:
            prompts.append({
                "name": file.stem,
                "content": f.read().strip()
            })
    return prompts

def clear_database():
    """Clear all nodes and relationships from the database."""
    db = Neo4jConnection()
    # Get count of nodes before clearing
    result = db.run_query("MATCH (n) RETURN count(n) as count")
    node_count = result[0]["count"]
    # Clear the database
    db.run_query("MATCH (n) DETACH DELETE n")
    st.success(f"Database cleared ({node_count} nodes removed)")

def clear_llm_cache():
    """Clear both Streamlit's cache and the LLM cache file if it exists."""
    # Clear Streamlit's cache
    st.cache_data.clear()
    
    # Clear file cache if it exists
    cache_files = [
        "llm_cache.json",
        ".cache/llm_cache.json",  # Check common cache directory
        os.path.expanduser("~/.cache/telltale/llm_cache.json")  # Check user cache directory
    ]
    
    found = False
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            os.remove(cache_file)
            found = True
            
    if found:
        st.success("Cache cleared (both Streamlit and file cache)")
    else:
        st.success("Cache cleared (Streamlit only)")

def display_parsed_results(parsed):
    """Display parsed nodes and relationships in a structured way."""
    st.subheader("Parsed Nodes")
    
    # Display nodes by type
    for node_type in ["FailureMode", "Observation", "SensorReading"]:
        nodes = [n for n in parsed["nodes"] if n["type"] == node_type]
        if nodes:
            st.write(f"**{node_type}s:**")
            for node in nodes:
                st.write(f"- {node['name']}")
                st.write(f"  Description: {node.get('description', 'No description')}")
                if node.get("unit"):
                    st.write(f"  Unit: {node['unit']}")
            st.write("")  # Add spacing between sections
    
    st.subheader("Parsed Relationships")
    
    # Display relationships
    for rel in parsed["relationships"]:
        source = rel.get("source", {}).get("name", "Unknown")
        destination = rel.get("destination", {}).get("name", "Unknown")
        st.write(f"- {source} → {destination}")
        st.write(f"  Type: {rel['type']}")
        if "properties" in rel:
            st.write("  Properties:")
            for key, value in rel["properties"].items():
                st.write(f"    - {key}: {value}")
        st.write("")  # Add spacing between relationships

def display_truth_table(engine, db):
    """Display the truth table for the current graph."""
    st.subheader("Truth Table")
    
    # Create truth table with properly initialized engine
    engine = DiagnosticEngine()  # Initialize without db parameter
    engine.db = db  # Set the database connection after initialization
    truth_table = TruthTable(engine)
    truth_table.scan_graph()
    
    # Generate and run test cases
    test_cases = truth_table.generate_test_cases()
    results = truth_table.run_truth_table(test_cases=test_cases)
    
    # Get HTML output
    html_output = truth_table.format_results(results, format='html')
    
    # Add some CSS to make the table more readable in Streamlit
    html_with_style = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 10px 0;
                font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            th {{
                background-color: #f0f2f6;
                padding: 10px;
                text-align: left;
                border: 1px solid #ccc;
                position: sticky;
                top: 0;
            }}
            td {{
                padding: 8px;
                border: 1px solid #ccc;
                vertical-align: top;
                max-width: 200px;
                overflow-wrap: break-word;
            }}
            td[style*="color:red"] {{
                background-color: #fff0f0;
            }}
            tr:hover {{
                background-color: #f8f9fa;
            }}
        </style>
    </head>
    <body>
        {html_output}
    </body>
    </html>
    """
    
    # Display using components.html
    components.html(html_with_style, height=600, scrolling=True)

# Initialize parser once at module level
parser = LLMParser()

@st.cache_data(show_spinner=False)
def get_cached_parse_result(_prompt: str) -> tuple[dict, bool]:
    """Cache the parsing results based on prompt text only.
    Returns tuple of (parse_result, is_from_cache)"""
    return parser.parse_text(_prompt), True

def main():
    st.title("LLM Parser Test UI")
    
    # Initialize database connection at the start
    db = Neo4jConnection()
    
    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        if st.button("Clear Database"):
            clear_database()
        if st.button("Clear Cache"):  # Renamed for clarity
            clear_llm_cache()
    
    # Load example prompts
    example_prompts = load_example_prompts()
    
    # Prompt input
    st.header("Input")
    prompt_source = st.radio(
        "Choose prompt source:",
        ["Example Prompts", "Manual Input"],
        index=0  # Set Example Prompts as default
    )
    
    if prompt_source == "Manual Input":
        prompt = st.text_area("Enter your prompt:", height=200)
    else:
        prompt_names = [p["name"] for p in example_prompts]
        selected_prompt = st.selectbox("Select an example prompt:", prompt_names, index=0)  # Set first example as default
        if selected_prompt:
            prompt = next(p["content"] for p in example_prompts if p["name"] == selected_prompt)
            st.text_area("Selected prompt:", prompt, height=200)
    
    if st.button("Parse Prompt"):
        if not prompt:
            st.error("Please enter a prompt")
        else:
            try:
                # Get cached parse results and cache status
                parsed, is_cached = get_cached_parse_result(prompt)
                
                # Show cache warning if result was cached
                if is_cached:
                    st.warning("⚡ Using cached LLM results. Clear cache to recompute.", icon="⚡")
                
                # Display parsed results
                display_parsed_results(parsed)
                
                # Process the nodes and relationships
                from telltale.core.node_manager import NodeManager
                manager = NodeManager(db=db, parser=parser)
                nodes, relationships = manager.parse_prompt(prompt)
                
                # Add nodes and relationships to database
                for node in nodes:
                    manager.add_node(node, force=True)
                for rel in relationships:
                    manager.add_relationship(rel)
                
                # Display truth table with database connection
                engine = DiagnosticEngine()
                display_truth_table(engine, db)
                
            except Exception as e:
                st.error(f"Error processing prompt: {str(e)}")

if __name__ == "__main__":
    main() 
"""LLM parser that converts natural language to diagnostic nodes and relationships."""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import SystemMessage, HumanMessage
import os
import json
from datetime import datetime

from .models import Node, Relationship, EvidenceStrength, ComparisonOperator, CausesLink, EvidenceLink

from .prompts.node_identification import SYSTEM_PROMPT as NODE_SYSTEM_PROMPT, get_node_prompt
from .prompts.failure_mode import SYSTEM_PROMPT as FAILURE_SYSTEM_PROMPT, get_failure_mode_prompt
from .prompts.relationship import SYSTEM_PROMPT as RELATIONSHIP_SYSTEM_PROMPT, get_relationship_prompt
from .prompts.evidence import SYSTEM_PROMPT as EVIDENCE_SYSTEM_PROMPT, get_evidence_prompt

class NodeIdentificationOutput(BaseModel):
    """Output model for node identification."""
    nodes: List[Node] = Field(description="List of identified nodes")

class ImpliedFailureModesOutput(BaseModel):
    """Output model for implied failure modes."""
    nodes: List[Node] = Field(description="List of implied failure modes")

class RelationshipFormationOutput(BaseModel):
    """Output model for relationship formation."""
    relationships: List[Union[CausesLink, EvidenceLink, Relationship]] = Field(description="List of formed relationships")

class EvidenceStrengthOutput(BaseModel):
    """Output model for evidence strength assessment."""
    relationships: List[Union[CausesLink, EvidenceLink, Relationship]] = Field(description="List of relationships with evidence strengths")

class LLMParser:
    """Parser that converts natural language to diagnostic nodes and relationships using external prompts."""
    
    def __init__(self, model_name: Optional[str] = None, provider: Optional[str] = None):
        """Initialize the parser.
        
        Args:
            model_name: Optional name of the LLM model to use. If None, determined by environment.
            provider: Optional LLM provider ('openai' or 'google'). If None, determined by environment.
        """
        # Determine LLM provider and model from environment if not provided
        llm_provider = provider or os.environ.get("LLM_PROVIDER", "openai").lower()
        
        if llm_provider == "openai":
            model = model_name or os.environ.get("OPENAI_MODEL")
            api_key = os.environ.get("OPENAI_API_KEY")
            if not model:
                raise ValueError("OPENAI_MODEL not found in environment for openai provider")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment for openai provider")
            
            self.llm = ChatOpenAI(
                model_name=model,
                api_key=api_key,
                temperature=0
            )
        elif llm_provider == "google":
            model = model_name or os.environ.get("GOOGLE_MODEL")
            api_key = os.environ.get("GOOGLE_AI_KEY")
            if not model:
                raise ValueError("GOOGLE_MODEL not found in environment for google provider")
            if not api_key:
                 raise ValueError("GOOGLE_AI_KEY not found in environment for google provider")

            self.llm = ChatGoogleGenerativeAI(
                 model=model,
                 google_api_key=api_key,
                 temperature=0
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}. Choose 'openai' or 'google'.")
        
        # Initialize output parsers
        self.node_parser = PydanticOutputParser(pydantic_object=NodeIdentificationOutput)
        self.failure_mode_parser = PydanticOutputParser(pydantic_object=ImpliedFailureModesOutput)
        self.relationship_parser = PydanticOutputParser(pydantic_object=RelationshipFormationOutput)
        self.evidence_parser = PydanticOutputParser(pydantic_object=EvidenceStrengthOutput)
    
    def parse_text(self, text: str) -> Dict[str, Any]:
        """Parse natural language text into diagnostic nodes and relationships using a manual chain.
        
        Args:
            text: The text to parse
            
        Returns:
            Dictionary containing nodes and relationships
        """
        if not text or not isinstance(text, str):
            raise ValueError("Text must be a non-empty string")
        
        print("\n--- Step 1: Node Identification ---")
        # Step 1: Identify explicit nodes
        node_user_prompt = get_node_prompt(text)
        node_messages = [
            SystemMessage(content=NODE_SYSTEM_PROMPT),
            HumanMessage(content=node_user_prompt)
        ]
        node_response = self.llm.invoke(node_messages)
        node_result = self.node_parser.parse(node_response.content)
        print(f"Identified {len(node_result.nodes)} explicit nodes.")

        print("\n--- Step 2: Implied Failure Modes ---")
        # Step 2: Identify implied failure modes
        # Format identified nodes for the next prompt
        identified_nodes_json = json.dumps({"nodes": [node.model_dump(mode='json') for node in node_result.nodes]}, indent=2)
        failure_user_prompt = get_failure_mode_prompt(text, identified_nodes_json)
        failure_messages = [
            SystemMessage(content=FAILURE_SYSTEM_PROMPT),
            HumanMessage(content=failure_user_prompt)
        ]
        failure_response = self.llm.invoke(failure_messages)
        failure_result = self.failure_mode_parser.parse(failure_response.content)
        print(f"Identified {len(failure_result.nodes)} implied failure modes.")

        # Combine nodes
        all_nodes = node_result.nodes + failure_result.nodes
        print(f"Total nodes: {len(all_nodes)}")

        print("\n--- Step 3: Relationship Formation ---")
        # Step 3: Form initial relationships
        # Format all nodes for the relationship prompt
        all_nodes_dict = {"nodes": [node.model_dump(mode='json') for node in all_nodes]}
        all_nodes_json = json.dumps(all_nodes_dict, indent=2)
        # Note: relationship prompt expects identified_nodes and input_nodes (which seems to be all nodes based on old chain)
        relationship_user_prompt = get_relationship_prompt(
            input_text=text,
            identified_nodes=identified_nodes_json, # Pass explicit nodes
            input_nodes=all_nodes_json # Pass all nodes
        )
        relationship_messages = [
            SystemMessage(content=RELATIONSHIP_SYSTEM_PROMPT),
            HumanMessage(content=relationship_user_prompt)
        ]
        relationship_response = self.llm.invoke(relationship_messages)
        # Handle potential parsing errors gracefully for debugging
        try:
            relationship_result = self.relationship_parser.parse(relationship_response.content)
            print(f"Formed {len(relationship_result.relationships)} initial relationships.")
        except Exception as e:
            print("\n" + "-"*30 + " RELATIONSHIP PARSING FAILED " + "-"*30)
            print(f"Error parsing Relationship Formation Output: {e}")
            print("Raw output that failed parsing:")
            print(relationship_response.content)
            print("-" * 80)
            raise e

        print("\n--- Step 4: Evidence Strength Assessment ---")
        # Step 4: Assess evidence strength
        # Format initial relationships for the evidence prompt
        initial_relationships_json = json.dumps(
            {"relationships": [rel.model_dump(mode='json') for rel in relationship_result.relationships]},
            indent=2
        )
        evidence_user_prompt = get_evidence_prompt(text, initial_relationships_json)
        evidence_messages = [
            SystemMessage(content=EVIDENCE_SYSTEM_PROMPT),
            HumanMessage(content=evidence_user_prompt)
        ]
        evidence_response = self.llm.invoke(evidence_messages)
        # Handle potential parsing errors gracefully for debugging
        try:
            evidence_result = self.evidence_parser.parse(evidence_response.content)
            print(f"Assessed evidence for {len(evidence_result.relationships)} final relationships.")
        except Exception as e:
            print("\n" + "-"*30 + " EVIDENCE PARSING FAILED " + "-"*30)
            print(f"Error parsing Evidence Strength Output: {e}")
            print("Raw output that failed parsing:")
            print(evidence_response.content)
            print("-" * 80)
            raise e

        # Return the combined results
        print("\n--- Parsing Complete ---")
        return {
            "nodes": all_nodes,
            "relationships": evidence_result.relationships # Return final relationships
        }

    def save_results(self, results: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Save the parsed results to a JSON file.

        Args:
            results: The dictionary containing nodes and relationships from parse_text.
            filename: Optional filename. If None, a timestamped filename is generated.

        Returns:
            The path to the saved file.
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"parser_results_{timestamp}.json"

        # Ensure nodes and relationships are serializable (use model_dump)
        # Pass mode='json' to handle types like Enums correctly for JSON
        serializable_results = {
            "nodes": [node.model_dump(mode='json', exclude_none=True) if isinstance(node, BaseModel) else node for node in results.get("nodes", [])],
            "relationships": [rel.model_dump(mode='json', exclude_none=True) if isinstance(rel, BaseModel) else rel for rel in results.get("relationships", [])]
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, ensure_ascii=False, indent=4)
            print(f"Results saved to {filename}")
            return filename
        except IOError as e:
            print(f"Error saving results to {filename}: {e}")
            raise

    def validate_evidence_strength(self, strength: str) -> None:
        """Validate that a strength value is valid.
        
        Args:
            strength: Strength value to validate
            
        Raises:
            ValueError: If strength is not valid
        """
        # Ensure EvidenceStrength enum values are used if available
        valid_strengths = [e.value for e in EvidenceStrength] if hasattr(EvidenceStrength, 'value') else list(EvidenceStrength) # Adapt if EvidenceStrength is simple Enum
        if strength not in valid_strengths:
            valid = ", ".join(valid_strengths)
            raise ValueError(
                f"Invalid evidence strength '{strength}'. Must be one of: {valid}"
            )

    def validate_operator(self, operator: str) -> None:
        """Validate that an operator value is valid.
        
        Args:
            operator: Operator value to validate
            
        Raises:
            ValueError: If operator is not valid
        """
        # Ensure ComparisonOperator enum values are used if available
        valid_operators = [o.value for o in ComparisonOperator] if hasattr(ComparisonOperator, 'value') else list(ComparisonOperator) # Adapt if ComparisonOperator is simple Enum
        if operator not in valid_operators:
            valid = ", ".join(valid_operators)
            raise ValueError(
                f"Invalid operator '{operator}'. Must be one of: {valid}"
            ) 
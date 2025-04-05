"""Natural language interface for managing nodes and relationships in the knowledge graph."""

import logging
from typing import List, Dict, Any, Optional, Tuple, Union

from .models import (
    Node, FailureMode, Observation, SensorReading,
    EvidenceLink, CausesLink, EvidenceStrength, ComparisonOperator
)
from .database import Neo4jConnection
from .semantic_search import NodeVectorIndex, SearchResult
from .llm_parser import LLMParser

logger = logging.getLogger(__name__)

NodeType = Union[FailureMode, Observation, SensorReading]
RelationType = Union[CausesLink, EvidenceLink]

class NodeManager:
    """Manages natural language creation of nodes and relationships."""

    def __init__(self, db: Neo4jConnection, parser: LLMParser = None, similarity_threshold: float = 0.8, initialize_vector_index: bool = True):
        """Initialize the node manager.
        
        Args:
            db: Neo4j database connection
            parser: LLM parser instance to use. If None, a new one will be created.
            similarity_threshold: Threshold for considering nodes similar (0.0 to 1.0)
            initialize_vector_index: Whether to initialize and load the vector index.
        """
        self.db = db
        self.parser = parser or LLMParser()
        self.similarity_threshold = similarity_threshold
        self.vector_index = None

        if initialize_vector_index:
            try:
                self.vector_index = NodeVectorIndex()
                # Load existing nodes into vector index
                logger.info("Initializing and loading vector index...")
                self.vector_index.index_all_nodes_from_graph(self.db)
                logger.info("Vector index loaded.")
            except ImportError:
                logger.warning("NodeVectorIndex or its dependencies not found. Semantic search features disabled.")
                self.vector_index = None
            except Exception as e:
                logger.error(f"Failed to initialize vector index: {e}")
                self.vector_index = None

    def parse_prompt(self, prompt: str) -> Tuple[List[NodeType], List[RelationType]]:
        """Parse a natural language prompt into nodes and relationships.
        
        Args:
            prompt: Natural language description of nodes and relationships
            
        Returns:
            Tuple of (nodes, relationships)
        """
        # Parse the text using the LLM
        parsed = self.parser.parse_text(prompt)

        # Convert parsed nodes to appropriate Node subclass objects and add them to DB
        nodes = []
        node_map = {}  # Map of (type, name) -> node with ID
        for node_data in parsed["nodes"]:
            if node_data["type"] == "FailureMode":
                node = FailureMode(
                    name=node_data["name"],
                    description=node_data.get("description")
                )
            elif node_data["type"] == "Observation":
                node = Observation(
                    name=node_data["name"],
                    description=node_data.get("description")
                )
            elif node_data["type"] == "SensorReading":
                node = SensorReading(
                    name=node_data["name"],
                    description=node_data.get("description"),
                    unit=node_data.get("unit")
                )
            else:
                raise ValueError(f"Unknown node type: {node_data['type']}")
            
            # Add node to DB to get its ID
            node.id = self.add_node(node, force=True)
            nodes.append(node)
            node_map[(node.type, node.name)] = node

        # Convert parsed relationships to appropriate Relationship subclass objects
        relationships = []
        for rel_data in parsed["relationships"]:
            # Get source and destination nodes (they should already exist with IDs)
            source_type = rel_data["source"]["type"]
            source_name = rel_data["source"]["name"]
            dest_type = rel_data["destination"]["type"]
            dest_name = rel_data["destination"]["name"]

            source = node_map.get((source_type, source_name))
            dest = node_map.get((dest_type, dest_name))

            if not source or not dest:
                logger.warning(f"Missing nodes for relationship: {source_type}:{source_name} -> {dest_type}:{dest_name}")
                continue

            # Create relationship
            if rel_data["type"] == "CausesLink":
                rel = CausesLink(
                    source=source,
                    dest=dest
                )
            else:  # EvidenceLink
                props = rel_data.get("properties", {})
                
                # Default strengths if not provided in properties
                when_true = props.get("when_true_strength", "suggests")
                when_false = props.get("when_false_strength", "inconclusive")
                
                rel = EvidenceLink(
                    source=source,
                    dest=dest,
                    when_true_strength=EvidenceStrength(when_true),
                    when_false_strength=EvidenceStrength(when_false),
                    operator=ComparisonOperator(props.get("operator")) if props.get("operator") else None,
                    threshold=props.get("threshold")
                )

            relationships.append(rel)

        return nodes, relationships

    def find_similar_nodes(self, node: NodeType) -> List[SearchResult]:
        """Find existing nodes that are semantically similar.
        
        Args:
            node: Node to find similar nodes for
            
        Returns:
            List of similar nodes with similarity scores
        """
        # Generate search text in same format as index
        search_text = f"{node.type}: {node.name}"
        if node.description:
            search_text += f". {node.description}"

        # Check if vector index is available
        if not self.vector_index:
            logger.warning("Vector index not initialized. Skipping similarity search.")
            return []

        # Search vector index
        return self.vector_index.search(search_text)

    def add_node(self, node: NodeType, force: bool = False) -> str:
        """Add a new node to the graph if no similar nodes exist.
        
        Args:
            node: Node to add
            force: Whether to add even if similar nodes exist
            
        Returns:
            Neo4j node ID of new or existing node
            
        Raises:
            ValueError: If similar nodes exist and force=False
        """
        if not force and self.vector_index:
            similar = self.find_similar_nodes(node)
            if similar and similar[0].score >= self.similarity_threshold:
                raise ValueError(
                    f"Similar node exists: {similar[0].name} "
                    f"(similarity: {similar[0].score:.2f})"
                )

        # Create or merge node in Neo4j
        query = f"""
        MERGE (n:{node.type} {{name: $name}})
        SET n.description = $description
        """
        params = {
            "name": node.name,
            "description": node.description
        }
        
        if isinstance(node, SensorReading) and node.unit:
            query = query.replace(
                "SET n.description = $description",
                "SET n.description = $description, n.unit = $unit"
            )
            params["unit"] = node.unit

        # Add RETURN after the SET
        query += "\nRETURN elementId(n) as node_id"

        result = self.db.run_query(query, params)
        node_id = result[0]["node_id"]

        # Update node with Neo4j ID
        node.id = node_id

        # Add to vector index only if it exists
        if self.vector_index:
            try:
                self.vector_index.add_node_to_index(node)
            except Exception as e:
                logger.error(f"Failed to add node {node.name} to vector index: {e}")
                # Continue even if adding to index fails, as node is in DB

        return node_id

    def add_relationship(self, rel: RelationType) -> str:
        """Add a new relationship between nodes.
        
        Args:
            rel: Relationship to add
            
        Returns:
            Neo4j relationship ID
        """
        if not rel.has_valid_ids(): # Check if source/target nodes have IDs
            raise ValueError(f"Cannot add relationship, source or target node missing ID: {rel}")

        # Get source/target IDs using the correct field name
        source_id = rel.source.id
        target_id = rel.target.id # Use target.id
        rel_type_str = rel.type # Use the type attribute directly (e.g., "CAUSES", "EVIDENCE_FOR")

        # Create relationship
        if isinstance(rel, CausesLink):
            query = f"""
            MATCH (source), (target)
            WHERE elementId(source) = $source_id
              AND elementId(target) = $target_id
            MERGE (source)-[r:{rel_type_str}]->(target)
            RETURN elementId(r) as rel_id
            """
            params = {
                "source_id": source_id,
                "target_id": target_id
            }
        elif isinstance(rel, EvidenceLink): # Use elif for clarity
            # Build the property dictionary from the nested 'properties' field
            rel_props = {}
            if rel.properties: # Check if properties exist
                # Add strengths
                if rel.properties.when_true_strength:
                    rel_props["when_true_strength"] = rel.properties.when_true_strength.value
                if rel.properties.when_false_strength:
                    rel_props["when_false_strength"] = rel.properties.when_false_strength.value
                
                # Add rationales
                if rel.properties.when_true_rationale:
                    rel_props["when_true_rationale"] = rel.properties.when_true_rationale
                if rel.properties.when_false_rationale:
                    rel_props["when_false_rationale"] = rel.properties.when_false_rationale

                # Add operator
                if rel.properties.operator:
                    rel_props["operator"] = rel.properties.operator.value
                
                # Add threshold
                if rel.properties.threshold is not None:
                    rel_props["threshold"] = rel.properties.threshold
                
            # Note: 'name' was removed from EvidenceProperties, assuming it's not set here.
            
            # Create the Cypher query with property mapping
            query = f"""
            MATCH (source), (target)
            WHERE elementId(source) = $source_id
              AND elementId(target) = $target_id
            MERGE (source)-[r:{rel_type_str}]->(target)
            SET r = $properties
            RETURN elementId(r) as rel_id
            """
            
            params = {
                "source_id": source_id,
                "target_id": target_id,
                "properties": rel_props
            }
        else:
             # Handle cases where rel is not CausesLink or EvidenceLink if necessary
            raise TypeError(f"Unsupported relationship type: {type(rel)}")

        result = self.db.run_query(query, params)
        
        # Handle potential case where MERGE didn't return a result (shouldn't happen with MATCH)
        if not result or not result[0].get("rel_id"):
            logger.error(f"Failed to create/merge relationship or retrieve ID: {rel}")
            # Attempt to find the relationship if merge failed to return ID
            find_query = f"""
            MATCH (source)-[r:{rel_type_str}]->(target)
            WHERE elementId(source) = $source_id AND elementId(target) = $target_id
            RETURN elementId(r) as rel_id LIMIT 1
            """
            find_result = self.db.run_query(find_query, {"source_id": source_id, "target_id": target_id})
            if find_result and find_result[0].get("rel_id"):
                 rel_id = find_result[0]["rel_id"]
                 logger.warning(f"Retrieved existing relationship ID after MERGE failed to return one: {rel_id}")
            else:
                raise ConnectionError(f"Failed to create or find relationship after merge: {rel}") # Or handle differently
        else:
            rel_id = result[0]["rel_id"]
            
        rel.id = rel_id
        return rel_id

    def process_natural_language(self, prompt: str, interactive: bool = True) -> None:
        """Process a natural language prompt to add nodes and relationships.
        
        Args:
            prompt: Natural language description
            interactive: Whether to ask user about similar nodes
        """
        # Parse the prompt
        nodes, relationships = self.parse_prompt(prompt)

        # Process each node
        for node in nodes:
            try:
                self.add_node(node, force=not interactive)
            except ValueError as e:
                if interactive:
                    # Show similar nodes and ask user what to do
                    similar = self.find_similar_nodes(node)
                    print(f"\nFound similar node for: {node.name}")
                    for i, s in enumerate(similar[:5], 1):
                        print(f"{i}. {s.name} (similarity: {s.score:.2f})")
                    print("0. Create new node anyway")
                    
                    choice = input("Choose an option (0-5): ")
                    if choice == "0":
                        self.add_node(node, force=True)
                    else:
                        # Use the existing node's ID
                        node.id = similar[int(choice)-1].id
                else:
                    raise

        # Process relationships
        for rel in relationships:
            self.add_relationship(rel) 
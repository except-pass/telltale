from typing import Dict, List, Optional, Union, Any
import os
import logging

from neo4j import GraphDatabase, Driver, Session
from pydantic import BaseModel

from .models import Node, FailureMode, Observation, SensorReading, CausesLink, EvidenceLink

logger = logging.getLogger(__name__)


class Neo4jConnection:
    """Handles Neo4j database connections and queries."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
    ):
        """Initialize connection to Neo4j database.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
        """
        self._uri = os.environ.get("NEO4J_URI", uri)
        self._username = os.environ.get("NEO4J_USERNAME", username)
        self._password = os.environ.get("NEO4J_PASSWORD", password)
        self._driver = None

    def connect(self) -> None:
        """Establish connection to Neo4j database."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self._uri, auth=(self._username, self._password)
                )
                logger.info(f"Connected to Neo4j database at {self._uri}")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise

    def close(self) -> None:
        """Close the connection to Neo4j database."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    def get_driver(self) -> Driver:
        """Get the Neo4j driver instance.

        Returns:
            Neo4j driver instance
        """
        if self._driver is None:
            self.connect()
        return self._driver

    def run_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Run a Cypher query against the Neo4j database.

        Args:
            query: Cypher query to execute
            params: Parameters for the query

        Returns:
            List of results as dictionaries
        """
        if self._driver is None:
            self.connect()

        if params is None:
            params = {}

        with self._driver.session() as session:
            result = session.run(query, params)
            return [dict(record) for record in result]

    def get_nodes_by_type(self, node_type: str) -> List[Node]:
        """Get all nodes of a specific type.
        
        Args:
            node_type: Type of node to get (FailureMode, Observation, or SensorReading)
            
        Returns:
            List of Node objects
        """
        # Map node types to their model classes
        type_map = {
            "FailureMode": FailureMode,
            "Observation": Observation,
            "SensorReading": SensorReading
        }
        
        if node_type not in type_map:
            raise ValueError(f"Unknown node type: {node_type}")
            
        # Query for nodes of the specified type
        query = f"""
        MATCH (n:{node_type})
        RETURN 
            elementId(n) as id,
            n.name as name,
            n.description as description
            {', n.unit as unit' if node_type == 'SensorReading' else ''}
        """
        
        results = self.run_query(query)
        
        # Convert to appropriate model instances
        model_class = type_map[node_type]
        nodes = []
        for row in results:
            # Handle SensorReading's extra unit field
            if node_type == "SensorReading":
                nodes.append(model_class(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    unit=row["unit"]
                ))
            else:
                nodes.append(model_class(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"]
                ))
        
        return nodes

    def save_node(self, node: Node) -> str:
        """Save a node to the database.
        
        Args:
            node: The node to save
            
        Returns:
            The node's ID
        """
        # Build properties dict, excluding None values
        properties = {
            "name": node.name
        }
        if node.description:
            properties["description"] = node.description
            
        # Add additional properties for SensorReading
        if isinstance(node, SensorReading):
            if node.unit:
                properties["unit"] = node.unit
        
        # Build property string for query
        properties_str = ", ".join(f"{k}: ${k}" for k in properties.keys())
        
        # Use MERGE instead of CREATE to handle existing nodes
        query = f"""
        MERGE (n:{node.type} {{{properties_str}}})
        RETURN elementId(n) as node_id
        """
        params = properties
        
        result = self.run_query(query, params)
        node_id = result[0]["node_id"]
        
        # Update the node's ID
        node.id = node_id
        
        return node_id
        
    def save_relationship(self, relationship: Union[CausesLink, EvidenceLink]) -> str:
        """Save a relationship to the database.
        
        Args:
            relationship: The relationship model to save
            
        Returns:
            The relationship ID
        """
        # Ensure both source and destination have IDs
        if not relationship.source.id or not relationship.dest.id:
            raise ValueError("Both source and destination nodes must have IDs")
            
        # Extract properties based on relationship type
        properties = {}
        
        if isinstance(relationship, EvidenceLink):
            rel_type = "EVIDENCE_FOR"
            properties = {
                "when_true_strength": relationship.when_true_strength.value,
                "when_false_strength": relationship.when_false_strength.value
            }
            
            # Add additional properties for EvidenceLink
            if relationship.operator:
                properties["operator"] = relationship.operator.value
                
            if relationship.threshold is not None:
                properties["threshold"] = relationship.threshold
                
            if relationship.name:
                properties["name"] = relationship.name
                
            if relationship.rationale:
                properties["rationale"] = relationship.rationale
        else:
            # CausesLink has no additional properties
            rel_type = "CAUSES"
            
        # Create the relationship
        properties_str = ""
        if properties:
            props_items = [f"{key}: ${key}" for key in properties]
            properties_str = " {" + ", ".join(props_items) + "}"
            
        query = f"""
        MATCH (source), (dest)
        WHERE elementId(source) = $source_id AND elementId(dest) = $dest_id
        CREATE (source)-[r:{rel_type}{properties_str}]->(dest)
        RETURN elementId(r) as rel_id
        """
        
        params = {
            "source_id": relationship.source.id,
            "dest_id": relationship.dest.id,
            **properties
        }
        
        result = self.run_query(query, params)
        rel_id = result[0]["rel_id"]
        
        # Update the relationship's ID
        relationship.id = rel_id
        
        return rel_id

    def initialize_schema(self, clear_existing: bool = False) -> None:
        """Initialize the database schema.

        Args:
            clear_existing: Whether to clear existing data before initialization
        """
        if clear_existing:
            self.run_query("MATCH (n) DETACH DELETE n")
            logger.info("Cleared existing database")

        # Create constraints for unique node properties
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (f:FailureMode) REQUIRE f.name IS UNIQUE"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (o:Observation) REQUIRE o.name IS UNIQUE"
        )
        self.run_query(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:SensorReading) REQUIRE s.name IS UNIQUE"
        )
        logger.info("Database schema initialized")

    def clean(self) -> None:
        """Clean all nodes and relationships in the database."""
        self.run_query("MATCH (n) DETACH DELETE n")
        logger.info("Cleaned database")


class TestDatabase(Neo4jConnection):
    """Specialized database connection for testing."""
    
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
    ):
        """Initialize test database connection.
        
        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
        """
        super().__init__(uri, username, password)
    
import os
import unittest
from typing import Optional
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from telltale.core.database import TestDatabase
from telltale.core.models import FailureMode, Observation, SensorReading

def is_neo4j_running() -> bool:
    """Check if Neo4j is running and accessible."""
    try:
        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password")
        )
        driver.verify_connectivity()
        driver.close()
        return True
    except (ServiceUnavailable, Exception) as e:
        print(f"Neo4j connection failed: {e}")
        return False

class Neo4jTestCase(unittest.TestCase):
    """Base test class for Neo4j database testing.
    
    This class handles:
    1. Setting up a Neo4j connection
    2. Loading test data
    3. Cleaning up test data after tests
    """
    
    @classmethod
    def setUpClass(cls) -> None:
        """Set up the test environment."""
        if not is_neo4j_running():
            raise RuntimeError("Neo4j is not running. Please start Neo4j before running tests.")
        
        # Clean up any existing data
        conn = TestDatabase()
        conn.connect()
        conn.clean()
        conn.close()
    
    def setUp(self) -> None:
        """Set up for each test method."""
        # Set environment variables for the test database
        os.environ["NEO4J_URI"] = "bolt://localhost:7687"
        os.environ["NEO4J_USERNAME"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = "password"
        
        # Create test database connection
        self.connection = TestDatabase()
        self.connection.connect()
        
        # Clean up any existing data
        self.connection.clean()
    
    def tearDown(self) -> None:
        """Clean up after each test method."""
        if hasattr(self, 'connection'):
            # Clean up test data
            self.connection.clean()
            self.connection.close()
    
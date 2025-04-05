"""Tests for semantic search functionality."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from telltale.core.models import Observation, FailureMode, SensorReading
from telltale.core.semantic_search import NodeVectorIndex, SearchResult
from telltale.core.database import Neo4jConnection


class TestNodeVectorIndex(unittest.TestCase):
    """Test cases for NodeVectorIndex class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.index = NodeVectorIndex()
        
    def test_initialization(self):
        """Test that the index initializes correctly."""
        self.assertIsNotNone(self.index.model)
        self.assertIsNotNone(self.index.index)
        self.assertEqual(len(self.index.metadata), 0)

    def test_generate_text(self):
        """Test text generation from nodes."""
        # Test with description
        node = Observation(
            id="obs-1",
            name="No Music",
            description="Pressing the button does not result in any sound"
        )
        text = self.index._generate_text(node)
        self.assertEqual(
            text,
            "Observation: No Music. Pressing the button does not result in any sound"
        )
        
        # Test without description
        node = Observation(id="obs-2", name="No Power")
        text = self.index._generate_text(node)
        self.assertEqual(text, "Observation: No Power")

    def test_embed_text(self):
        """Test text embedding."""
        text = "Test text"
        embedding = self.index._embed_text(text)
        
        self.assertIsInstance(embedding, np.ndarray)
        self.assertEqual(embedding.shape, (384,))  # Default dimension for all-MiniLM-L6-v2

    def test_add_and_search_nodes(self):
        """Test adding nodes and searching."""
        # Add test nodes
        nodes = [
            Observation(id="obs-1", name="No Music", description="No sound when button pressed"),
            Observation(id="obs-2", name="No Sound", description="Device makes no sound"),
            Observation(id="obs-3", name="Low Battery", description="Battery indicator shows red"),
        ]
        
        for node in nodes:
            self.index.add_node_to_index(node)
            
        # Search for similar nodes
        results = self.index.search("audio not working", k=2)
        
        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], SearchResult)
        self.assertEqual(results[0].type, "Observation")
        
        # The first two results should be the sound-related observations
        sound_related = ["No Music", "No Sound"]
        self.assertIn(results[0].name, sound_related)
        self.assertIn(results[1].name, sound_related)
        self.assertNotEqual(results[0].name, results[1].name)

    def test_save_and_load(self):
        """Test saving and loading the index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate index
            node = Observation(id="obs-1", name="Test Node")
            self.index.add_node_to_index(node)
            
            # Save
            save_dir = Path(tmpdir) / "index"
            self.index.save(save_dir)
            
            # Load into new index
            new_index = NodeVectorIndex()
            new_index.load(save_dir)
            
            # Verify metadata was preserved
            self.assertEqual(len(new_index.metadata), 1)
            self.assertEqual(new_index.metadata[0]["name"], "Test Node")
            
            # Verify search still works
            results = new_index.search("Test Node")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].name, "Test Node")

    def test_index_types(self):
        """Test different FAISS index types."""
        # L2 index
        l2_index = NodeVectorIndex(index_type="l2")
        self.assertIn("IndexFlatL2", str(type(l2_index.index)))
        
        # Cosine index
        cosine_index = NodeVectorIndex(index_type="cosine")
        self.assertIn("IndexFlatIP", str(type(cosine_index.index)))
        
        # Invalid type
        with self.assertRaises(ValueError):
            NodeVectorIndex(index_type="invalid")

    def test_index_all_nodes_from_graph(self):
        """Test indexing all nodes from the graph."""
        # Create mock database connection
        mock_db = Mock(spec=Neo4jConnection)
        
        # Set up mock data
        test_nodes = {
            "FailureMode": [
                FailureMode(id="fm-1", name="Battery Dead"),
                FailureMode(id="fm-2", name="Speaker Broken")
            ],
            "Observation": [
                Observation(id="obs-1", name="No Sound"),
                Observation(id="obs-2", name="Low Battery Warning")
            ],
            "SensorReading": [
                SensorReading(id="sr-1", name="Battery Voltage", description="3.2V")
            ]
        }
        
        # Configure mock to return appropriate nodes for each type
        def get_nodes_side_effect(node_type):
            return test_nodes.get(node_type, [])
            
        mock_db.get_nodes_by_type = Mock(side_effect=get_nodes_side_effect)
        
        # Run the indexing
        self.index.index_all_nodes_from_graph(mock_db)
        
        # Verify the results
        self.assertEqual(len(self.index.metadata), 5)  # Total number of test nodes
        
        # Verify each node type was queried
        mock_db.get_nodes_by_type.assert_any_call("FailureMode")
        mock_db.get_nodes_by_type.assert_any_call("Observation")
        mock_db.get_nodes_by_type.assert_any_call("SensorReading")
        
        # Test searching the indexed nodes
        results = self.index.search("battery issues", k=2)
        self.assertEqual(len(results), 2)
        battery_related = ["Battery Dead", "Low Battery Warning", "Battery Voltage"]
        self.assertIn(results[0].name, battery_related)


if __name__ == '__main__':
    unittest.main()
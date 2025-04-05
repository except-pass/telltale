"""Semantic search functionality for finding similar nodes in the knowledge graph."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

from .models import Node, FailureMode, Observation, SensorReading
from .database import Neo4jConnection


class SearchResult(BaseModel):
    """Result from a semantic search query."""
    id: str
    name: str
    type: str
    score: float
    description: Optional[str] = None


class NodeVectorIndex:
    """Manages semantic search across nodes using FAISS."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimension: int = 384,  # Default dimension for all-MiniLM-L6-v2
        index_type: str = "l2",
    ):
        """Initialize the vector index.
        
        Args:
            model_name: Name of the sentence-transformers model to use
            dimension: Embedding dimension (must match model output)
            index_type: Type of FAISS index ('l2' or 'cosine')
        """
        self.model = SentenceTransformer(model_name)
        
        if index_type == "l2":
            self.index = faiss.IndexFlatL2(dimension)
        elif index_type == "cosine":
            self.index = faiss.IndexFlatIP(dimension)
        else:
            raise ValueError("index_type must be 'l2' or 'cosine'")
            
        # Map FAISS index positions to node metadata
        self.metadata: List[Dict[str, Any]] = []
        
    def _generate_text(self, node: Node) -> str:
        """Generate canonical text representation of a node.
        
        Args:
            node: Node instance to generate text for
            
        Returns:
            String representation combining type, name, and description
        """
        text = f"{node.type}: {node.name}"
        if node.description:
            text += f". {node.description}"
        return text
        
    def _embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text using the model.
        
        Args:
            text: Text to embed
            
        Returns:
            Numpy array of embeddings
        """
        return self.model.encode([text])[0]
        
    def index_all_nodes_from_graph(self, db: Neo4jConnection) -> None:
        """Pull all nodes from Neo4j and index them.
        
        Args:
            db: Neo4j database connection
        """
        # Clear existing index
        self.index.reset()
        self.metadata.clear()
        
        # Get all nodes by type
        node_types = [FailureMode, Observation, SensorReading]
        all_nodes = []
        
        for node_type in node_types:
            nodes = db.get_nodes_by_type(node_type.__name__)
            all_nodes.extend(nodes)
            
        # If no nodes found, return early
        if not all_nodes:
            return
            
        # Index each node
        embeddings = []
        for node in all_nodes:
            text = self._generate_text(node)
            embedding = self._embed_text(text)
            embeddings.append(embedding)
            
            self.metadata.append({
                "id": node.id,
                "name": node.name,
                "type": node.type,
                "description": node.description
            })
            
        # Add to FAISS index
        embeddings_array = np.array(embeddings).astype('float32')
        self.index.add(embeddings_array)
        
    def search(self, query_text: str, k: int = 5) -> List[SearchResult]:
        """Search for nodes similar to the query text.
        
        Args:
            query_text: Text to search for
            k: Number of results to return
            
        Returns:
            List of SearchResult objects
        """
        # Embed query
        query_embedding = self._embed_text(query_text)
        query_embedding = np.array([query_embedding]).astype('float32')
        
        # Search
        distances, indices = self.index.search(query_embedding, k)
        
        # Format results
        results = []
        for idx, (distance, index) in enumerate(zip(distances[0], indices[0])):
            if index == -1:  # FAISS returns -1 for empty slots
                continue
                
            metadata = self.metadata[index]
            score = 1.0 / (1.0 + distance)  # Convert distance to similarity score
            
            results.append(SearchResult(
                id=metadata["id"],
                name=metadata["name"],
                type=metadata["type"],
                description=metadata.get("description"),
                score=float(score)
            ))
            
        return results
        
    def add_node_to_index(self, node: Node) -> None:
        """Add a single node to the index.
        
        Args:
            node: Node to add
        """
        text = self._generate_text(node)
        embedding = self._embed_text(text)
        embedding = np.array([embedding]).astype('float32')
        
        self.index.add(embedding)
        self.metadata.append({
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "description": node.description
        })
        
    def save(self, directory: Union[str, Path]) -> None:
        """Save the index and metadata to disk.
        
        Args:
            directory: Directory to save files in
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        faiss.write_index(self.index, str(directory / "index.faiss"))
        
        # Save metadata
        with open(directory / "metadata.json", "w") as f:
            json.dump(self.metadata, f)
            
    def load(self, directory: Union[str, Path]) -> None:
        """Load the index and metadata from disk.
        
        Args:
            directory: Directory containing saved files
        """
        directory = Path(directory)
        
        # Load FAISS index
        self.index = faiss.read_index(str(directory / "index.faiss"))
        
        # Load metadata
        with open(directory / "metadata.json", "r") as f:
            self.metadata = json.load(f) 
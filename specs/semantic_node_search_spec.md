# 🧠 Semantic Node Search Layer with FAISS

## 🎯 Purpose

Enable semantic similarity search across `Node` entries in your Neo4j-based diagnostic knowledge graph using a **local FAISS vector index**. This supports:
- Detecting duplicate or similar concepts (e.g., `"No Music"` vs `"No Sound"`)
- Preventing redundant entries during authoring
- Supporting fuzzy lookup for graph construction

---

## 📦 Architecture Overview

- Extract nodes (`Observation`, `SensorReading`, `FailureMode`) from Neo4j
- Create a text "bag" for each node (e.g., `"{type}: {name}. {description}"`)
- Embed the text using a language model (OpenAI or local via `sentence-transformers`)
- Store the embeddings in a **FAISS** index
- Perform similarity search against new inputs

---

## ⚙️ Components

### 1. **Embedding Model**
- Use `sentence-transformers` (`all-MiniLM-L6-v2` is a good default)
- Optional: OpenAI `text-embedding-ada-002` if you prefer cloud

### 2. **Vector Index**
- Use FAISS with L2 or cosine similarity
- Store FAISS index in memory (optionally persist to disk)

### 3. **Metadata Store**
- Maintain a mapping of vector index IDs to node metadata:
  - Node `id`, `name`, `type`, and optionally Neo4j internal ID
- Keep in sync with FAISS entries

---

## 🧱 Data Format per Node

```json
{
  "id": "obs-001",
  "name": "No Music",
  "type": "Observation",
  "text": "Observation: No Music. Pressing the button does not result in any sound."
}
```

This is the raw input to the embedding model.

---

## 📐 System Functions

### `index_all_nodes_from_graph()`
- Pulls all nodes from Neo4j via Cypher (one query per label)
- For each node:
  - Generate canonical `text` representation
  - Generate embedding
  - Store in FAISS index + metadata list

### `search(query_text: str, k=5)`
- Embed the `query_text`
- Search the FAISS index
- Return top `k` closest nodes (from metadata)

### `add_node_to_index(node)`
- Given a new node (Pydantic model), generate embedding and add to index + metadata

### `rebuild_index()` *(optional)*
- Refresh all embeddings from scratch (e.g., after mass edits)

---

## 🛠 Dependencies

```bash
pip install faiss-cpu sentence-transformers
```

---

## 🧪 Example Usage

```python
index = NodeVectorIndex()

index.index_all_nodes_from_graph()

results = index.search("no sound when button is pressed")

for result in results:
	print(result["name"], result["type"])
```

---

## 📁 Optional: Save & Load Index

- Save:
  ```python
  faiss.write_index(index.index, "index.faiss")
  with open("metadata.json", "w") as f:
      json.dump(index.metadata, f)
  ```

- Load:
  ```python
  index.index = faiss.read_index("index.faiss")
  index.metadata = json.load(open("metadata.json"))
  ```

---

## 🧠 Design Philosophy

- Keep FAISS purely local and in-memory by default
- Optionally persist it to disk for warm startup
- Node ID and type form the link back to Neo4j or to prevent duplicates
- Use similarity results as a pre-check when authoring new graph entries

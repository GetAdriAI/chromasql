# ChromaSQL Server CLI

The ChromaSQL Server CLI provides an easy way to spin up a server that exposes `MultiCollectionService` via HTTP API. This allows you to query one or more ChromaDB collections (local or cloud) using the ChromaSQL query language.

## Installation

The CLI is included in the chromasql package. When installed, it provides the `chromasql-server` command:

```bash
# Install chromasql package
cd chromasql
pip install -e .

# Or from the main project
poetry install
```

## Usage

### Basic Usage

Start a server with a single local collection:

```bash
poetry run chromasql-server --client "local:/path/to/collection"
```

### Multiple Collections

Start a server with multiple collections:

```bash
poetry run chromasql-server \
  --client "local:/path/to/collection1" \
  --client "local:/path/to/collection2" \
  --client "local:/path/to/collection3"
```

### Cloud Collections

Start a server with a cloud-hosted collection:

```bash
poetry run chromasql-server \
  --client "cloud:my-tenant:my-database:env:CHROMA_API_KEY"
```

Note: Use `env:VAR_NAME` syntax to reference environment variables for API keys.

### YAML Configuration

For complex setups, use a YAML configuration file:

```yaml
# collections.yaml
collections:
  - type: local
    name: my_local_collection
    persist_dir: /path/to/local/collection
    discriminator_field: model_name
    model_registry_target: my.module.registry:MODEL_REGISTRY
    embedding_model: text-embedding-3-small
    collection_name: my_collection

  - type: cloud
    name: my_cloud_collection
    tenant: my-tenant
    database: my-database
    api_key: env:CHROMA_API_KEY
    query_config_path: /path/to/query_config.json
    discriminator_field: model_name
    model_registry_target: my.module.registry:MODEL_REGISTRY
    embedding_model: text-embedding-3-small
```

Start the server with the configuration file:

```bash
poetry run chromasql-server --config-file collections.yaml
```

### Server Options

Customize the server behavior:

```bash
poetry run chromasql-server \
  --client "local:/path/to/collection" \
  --host 0.0.0.0 \
  --port 9000 \
  --reload \
  --verbose
```

Options:
- `--host HOST`: Server host (default: 127.0.0.1)
- `--port PORT`: Server port (default: 8000)
- `--reload`: Enable auto-reload for development
- `--verbose, -v`: Enable verbose logging

## API Endpoints

Once the server is running, the following endpoints are available:

### Health Check
```bash
GET /api/chromasql/health
```

Returns server health status.

### List Collections
```bash
GET /api/chromasql/indices
```

Returns metadata for all configured collections, including:
- Collection name and display name
- Embedding model
- Document counts
- Model registry (field schemas)
- System metadata fields

### Execute Query
```bash
POST /api/chromasql/execute?collection=<collection_name>
```

Execute a ChromaSQL query against a specific collection.

**Request Body:**
```json
{
  "query": "SELECT * FROM ModelName WHERE metadata.field = 'value' TOPK 10;",
  "limit": 500,
  "output_format": "json"
}
```

**Response:**
```json
{
  "query": "SELECT * FROM ModelName...",
  "total_rows": 10,
  "collections_queried": 1,
  "rows": [
    {"id": "doc1", "content": "...", "metadata": {...}},
    ...
  ],
  "rows_returned": 10
}
```

## Collection Requirements

Each collection directory must contain:

1. **query_config.json**: Chroma query configuration
   ```json
   {
     "model_to_collections": {
       "ModelName": {
         "collections": ["collection_name"],
         "total_documents": 100
       }
     }
   }
   ```

2. **chroma_data/**: ChromaDB persistent storage directory

3. **Model Registry**: Python module with MODEL_REGISTRY (for local collections)

## Example: Test Collection

Create a test collection:

```bash
# Run the test collection creation script
poetry run python workdir/test_collection/create_test_collection.py

# Start server with the test collection
poetry run chromasql-server \
  --config-file workdir/test_collection/config.yaml \
  --port 8888
```

Test the endpoints:

```bash
# Health check
curl http://localhost:8888/api/chromasql/health

# List collections
curl http://localhost:8888/api/chromasql/indices | jq

# Execute query
curl -X POST "http://localhost:8888/api/chromasql/execute?collection=test_collection" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT * FROM TestDocument WHERE metadata.category = '\''programming'\'' TOPK 5;",
    "limit": 100
  }' | jq
```

## CLI Arguments Reference

### Client Specification Format

**Local Collection:**
```
--client "local:<path_to_persist_dir>"
```

**Cloud Collection:**
```
--client "cloud:<tenant>:<database>:<api_key_or_env_ref>"
```

### YAML Configuration Format

See the [YAML Configuration](#yaml-configuration) section above for the complete schema.

## Developer Experience

The CLI provides a similar developer experience to the factory pattern in `adri_agents/app/server_factory.py`:

1. **Configuration-driven**: Define collections via CLI args or YAML
2. **Multi-collection support**: Host multiple collections in one server
3. **Flexible deployment**: Local development or cloud-hosted collections
4. **Type-safe**: Pydantic models for configuration and responses
5. **FastAPI-based**: Auto-generated OpenAPI docs at `/docs`

## Troubleshooting

### Import Errors

If you see import errors related to `indexer` or `adri_agents`:

- Make sure you're running the CLI from the main project: `poetry run chromasql-server`
- Ensure all dependencies are installed: `poetry install`

### Collection Not Found

If you see "Unknown collection" errors:

- Verify the collection name matches the key in your env_map or YAML config
- Check that query_config.json exists in the collection directory
- Ensure the ChromaDB data directory exists and is accessible

### Query Execution Errors

If queries fail:

- Verify the model_registry_target points to a valid Python module
- Check that the discriminator_field matches your metadata fields
- Ensure the embedding_model is consistent with your indexed data

## Next Steps

- Add authentication middleware for production deployment
- Implement rate limiting and request throttling
- Add metrics and monitoring endpoints
- Support for batch query execution
- WebSocket support for streaming results

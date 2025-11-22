"""
ChromaSQL CLI.

Command-line interface for spinning up a ChromaSQL server with one or more
collections (local or cloud).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

try:
    import uvicorn
except ImportError:
    uvicorn = None  # type: ignore

logger = logging.getLogger(__name__)


def parse_client_arg(client_spec: str) -> Dict[str, str]:
    """
    Parse a --client argument into a configuration dictionary.

    Supported formats:
        - local:<path_to_persist_dir>
        - cloud:<tenant>:<database>:<api_key_or_env_ref>

    Args:
        client_spec: Client specification string

    Returns:
        Dictionary with client configuration

    Raises:
        ValueError: If client_spec format is invalid
    """
    parts = client_spec.split(":", 1)
    if len(parts) < 2:
        raise ValueError(
            f"Invalid client spec: '{client_spec}'. "
            f"Expected format: 'local:<path>' or 'cloud:<tenant>:<database>:<api_key>'"
        )

    client_type = parts[0].lower()

    if client_type == "local":
        persist_dir = parts[1]
        if not persist_dir:
            raise ValueError(f"Local client spec missing persist_dir: '{client_spec}'")
        return {"type": "local", "persist_dir": persist_dir}

    elif client_type == "cloud":
        cloud_parts = parts[1].split(":")
        if len(cloud_parts) < 3:
            raise ValueError(
                f"Cloud client spec must have format "
                f"'cloud:<tenant>:<database>:<api_key>': '{client_spec}'"
            )
        tenant, database = cloud_parts[0], cloud_parts[1]
        api_key = ":".join(cloud_parts[2:])  # Allow colons in API key
        return {
            "type": "cloud",
            "tenant": tenant,
            "database": database,
            "api_key": api_key,
        }

    else:
        raise ValueError(
            f"Unknown client type: '{client_type}'. Must be 'local' or 'cloud'"
        )


def load_config_file(config_path: Path) -> Dict[str, List[Dict[str, str]]]:
    """
    Load collection configurations from a YAML file.

    Expected YAML format:
        collections:
          - type: local
            persist_dir: /path/to/collection1
          - type: cloud
            tenant: my-tenant
            database: my-db
            api_key: env:CHROMA_API_KEY

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Dictionary with 'collections' key containing list of configs

    Raises:
        ValueError: If config file is invalid
    """
    if not config_path.exists():
        raise ValueError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file: {e}") from e

    if not isinstance(config, dict) or "collections" not in config:
        raise ValueError(
            "Config file must contain 'collections' key with a list of collections"
        )

    collections = config["collections"]
    if not isinstance(collections, list):
        raise ValueError("'collections' must be a list")

    return config


def create_collection_environment_from_config(
    config: Dict[str, str], collection_name: str
) -> Any:
    """
    Create a CollectionEnvironment from a configuration dictionary.

    Args:
        config: Configuration dictionary (from --client or YAML)
        collection_name: Name for this collection

    Returns:
        CollectionEnvironment instance

    Raises:
        ValueError: If configuration is invalid or missing required fields
    """
    from idxr.models import CollectionEnvironment

    client_type = config.get("type", "").lower()

    if client_type == "local":
        persist_dir = Path(config.get("persist_dir", ""))
        if not persist_dir:
            raise ValueError("Local collection missing 'persist_dir'")

        # For local collections, check if environment.json exists
        environment_json_path = persist_dir / "environment.json"
        if environment_json_path.exists():
            # Load environment from file
            logger.info(
                f"Loading environment configuration from {environment_json_path}"
            )
            return CollectionEnvironment.from_file(environment_json_path)

        # Otherwise, look for config files in persist_dir and build environment
        query_config_path = persist_dir / "query_config.json"
        if not query_config_path.exists():
            raise ValueError(
                f"Local collection missing query_config.json at {persist_dir}"
            )

        # Try to infer other settings from config or use defaults
        discriminator_field = config.get("discriminator_field", "model_name")

        # Allow model_registry_target in config, otherwise try to auto-detect
        model_registry_target = config.get("model_registry_target")
        if not model_registry_target:
            # Check if test_registry.py exists in the persist_dir
            test_registry = persist_dir / "test_registry.py"
            if test_registry.exists():
                # Create module path from persist_dir
                rel_path = persist_dir.relative_to(Path.cwd())
                module_path = ".".join(rel_path.parts) + ".test_registry:MODEL_REGISTRY"
                model_registry_target = module_path
            else:
                model_registry_target = "idxr.registry:MODEL_REGISTRY"

        embedding_model = config.get("embedding_model", "text-embedding-3-small")
        local_collection_name = config.get("collection_name", collection_name)

        return CollectionEnvironment(
            collection_name=local_collection_name,
            query_config_path=query_config_path,
            discriminator_field=discriminator_field,
            model_registry_target=model_registry_target,
            embedding_model=embedding_model,
            chroma_client_type="persistent",
            local_persist_dir=persist_dir,
            local_collection_name=local_collection_name,
            is_local=True,
        )

    elif client_type == "cloud":
        tenant = config.get("tenant")
        database = config.get("database")
        api_key = config.get("api_key")

        if not tenant or not database or not api_key:
            raise ValueError(
                "Cloud collection missing required fields: tenant, database, api_key"
            )

        # For cloud collections, config must specify these paths/settings
        query_config_path_str = config.get("query_config_path")
        if not query_config_path_str:
            raise ValueError("Cloud collection missing 'query_config_path'")

        query_config_path = Path(query_config_path_str)
        if not query_config_path.exists():
            raise ValueError(
                f"Cloud collection query_config.json not found at {query_config_path}"
            )

        discriminator_field = config.get("discriminator_field", "model_name")
        model_registry_target = config.get(
            "model_registry_target", "idxr.registry:MODEL_REGISTRY"
        )
        embedding_model = config.get("embedding_model", "text-embedding-3-small")

        # For cloud collections, use database name as collection_name or
        # fallback to provided name
        cloud_collection_name = config.get(
            "collection_name", database or collection_name
        )

        return CollectionEnvironment(
            collection_name=cloud_collection_name,
            query_config_path=query_config_path,
            discriminator_field=discriminator_field,
            model_registry_target=model_registry_target,
            embedding_model=embedding_model,
            chroma_client_type="cloud",
            cloud_api_key=api_key,
            cloud_tenant=tenant,
            cloud_database=database,
            is_local=False,
        )

    else:
        raise ValueError(f"Unknown collection type: '{client_type}'")


def setup_logging(verbose: bool = False) -> None:
    """
    Setup logging configuration.

    Args:
        verbose: If True, set log level to DEBUG
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="ChromaSQL Server - SQL-like query interface for ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start server with a single local collection
  poetry run chromasql-server --client "local:/path/to/collection"

  # Start server with multiple local collections
  poetry run chromasql-server \\
    --client "local:/path/to/collection1" \\
    --client "local:/path/to/collection2"

  # Start server with cloud collection
  poetry run chromasql-server \\
    --client "cloud:my-tenant:my-db:env:CHROMA_API_KEY"

  # Start server from YAML config file
  poetry run chromasql-server --config-file collections.yaml

  # Mix CLI args and config file
  poetry run chromasql-server \\
    --config-file collections.yaml \\
    --client "local:/path/to/extra"
        """,
    )

    parser.add_argument(
        "--client",
        action="append",
        dest="clients",
        help=(
            "Collection client specification. Can be specified multiple times. "
            "Format: 'local:<path>' or 'cloud:<tenant>:<database>:<api_key>'"
        ),
    )

    parser.add_argument(
        "--config-file",
        type=Path,
        help="Path to YAML configuration file with collection definitions",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Check for uvicorn
    if uvicorn is None:
        logger.error("uvicorn is required to run the server. Install it with:")
        logger.error("  poetry add uvicorn")
        return 1

    # Collect all collection configurations
    collection_configs: List[Dict[str, Any]] = []

    # Load from config file if provided
    if args.config_file:
        try:
            config = load_config_file(args.config_file)
            collection_configs.extend(config["collections"])
            logger.info(
                f"Loaded {len(config['collections'])} collections from config file"
            )
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            return 1

    # Add CLI --client arguments
    if args.clients:
        for client_spec in args.clients:
            try:
                client_config = parse_client_arg(client_spec)
                collection_configs.append(client_config)
            except Exception as e:
                logger.error(f"Failed to parse client spec '{client_spec}': {e}")
                return 1

    # Ensure we have at least one collection
    if not collection_configs:
        logger.error("No collections specified. Use --client or --config-file")
        parser.print_help()
        return 1

    # Import dependencies (defer import to avoid issues if not installed)
    try:
        from chromasql.collection_service import MultiCollectionService
        from chromasql.server import create_chromasql_app
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}")
        logger.error("Make sure all required packages are installed")
        return 1

    # Create CollectionEnvironment instances
    env_map: Dict[str, Any] = {}
    coll_config: Dict[str, Any]
    for i, coll_config in enumerate(collection_configs):
        # Use 'name' field or generate from persist_dir/tenant+database
        collection_name: str = str(coll_config.get("name", ""))
        if not collection_name:
            if coll_config.get("type") == "local":
                # Use last directory name from persist_dir
                persist_dir_str = str(coll_config.get("persist_dir", ""))
                persist_dir = Path(persist_dir_str)
                collection_name = persist_dir.name if persist_dir else f"collection_{i}"
            else:
                # Use database name for cloud
                collection_name = str(coll_config.get("database", f"collection_{i}"))

        try:
            env = create_collection_environment_from_config(
                coll_config, collection_name
            )
            env_map[collection_name] = env
            logger.info(f"Loaded collection: {collection_name} ({coll_config['type']})")
        except Exception as e:
            logger.error(f"Failed to create environment for {collection_name}: {e}")
            return 1

    # Create MultiCollectionService
    try:
        service = MultiCollectionService(env_map)
        logger.info(f"Created MultiCollectionService with {len(env_map)} collections")
    except Exception as e:
        logger.error(f"Failed to create MultiCollectionService: {e}")
        return 1

    # Create FastAPI app
    try:
        app = create_chromasql_app(service)
        logger.info("Created FastAPI application")
    except Exception as e:
        logger.error(f"Failed to create FastAPI app: {e}")
        return 1

    # Start server
    logger.info(f"Starting ChromaSQL server on {args.host}:{args.port}")
    logger.info(f"Collections available: {list(env_map.keys())}")
    logger.info("API endpoints:")
    logger.info(f"  - GET  http://{args.host}:{args.port}/")
    logger.info(f"  - GET  http://{args.host}:{args.port}/api/chromasql/health")
    logger.info(f"  - GET  http://{args.host}:{args.port}/api/chromasql/indices")
    logger.info(
        f"  - POST http://{args.host}:{args.port}/api/chromasql/execute?collection=<name>"
    )

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="debug" if args.verbose else "info",
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

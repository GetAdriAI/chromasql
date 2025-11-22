"""
Collection Service for Research Agent.

This module provides a reusable service class that encapsulates the behavior
of the /indices and /chromasql/execute endpoints for any system environment.
"""

import json
from logging import getLogger
from typing import Any, Dict, List, Mapping, Optional, Type

from fastapi import HTTPException
from pydantic import BaseModel

from idxr.models import CollectionEnvironment

try:
    from adri_agents.app.utils.uni_vectordb_agent_harness.query_executor_config import (
        build_query_executor_kwargs,
        load_model_registry,
    )
except ImportError:
    # Fallback for standalone chromasql usage
    from idxr.query_lib.config import (  # type: ignore[no-redef]
        build_query_executor_kwargs,
        load_model_registry,
    )
from idxr.query_lib.executor import QueryExecutor
from chromasql.errors import (
    ChromaSQLParseError,
    ChromaSQLPlanningError,
    ChromaSQLExecutionError,
)

logger = getLogger(__name__)


# System metadata fields automatically managed by the idxr
SYSTEM_METADATA_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("model_name", "string", "String"),
    ("source_path", "string", "String"),
    ("schema_version", "integer", "Number"),
    ("partition_name", "string", "String"),
    ("has_sem", "boolean", "Boolean"),
    ("original_bytes", "integer", "Number"),
    ("compacted", "boolean", "Boolean"),
    ("compaction_fallback", "string", "String"),
    ("compacted_bytes", "integer", "Number"),
    ("truncated", "boolean", "Boolean"),
    ("original_tokens", "integer", "Number"),
)


class CollectionQueryResult(BaseModel):
    """Result from a ChromaSQL query execution."""

    query: str
    total_rows: int
    collections_queried: int
    rows: List[Dict[str, Any]]
    rows_returned: int


class CollectionMetadata(BaseModel):
    """Metadata for a collection."""

    collection_name: str
    display_name: str
    discriminator_field: str
    embedding_model: str
    total_documents: int
    models: List[Dict[str, Any]]
    model_registry: List[Dict[str, Any]]
    system_fields: List[Dict[str, str]]


class CollectionService:
    """
    Service for querying and managing collection metadata.

    This class provides reusable methods for:
    1. Retrieving index metadata (for /indices endpoint)
    2. Executing ChromaSQL queries (for /chromasql/execute endpoint)

    It can work with any CollectionEnvironment, supporting both
    system collections and user-created collections.

    Usage:
        # Single collection
        service = CollectionService(
            collection_name="ecc_6_0_ehp_7",
            display_name="ECC 6.0 Ehp 7",
            system_env=ecc_env
        )
        metadata = service.get_collection_metadata()
        result = await service.execute_query("SELECT * FROM ...", limit=100)

        # Multiple collections
        service = CollectionService.from_env_map({
            "ECC 6.0 Ehp 7": ecc_env,
            "S/4HANA 2021": s4_env
        })
        all_metadata = service.get_all_collection_metadata()
    """

    def __init__(
        self,
        collection_name: str,
        display_name: str,
        system_env: CollectionEnvironment,
    ):
        """
        Initialize the collection service for a single collection.

        Args:
            collection_name: Internal collection name (e.g., "ecc_6_0_ehp_7")
            display_name: Human-readable name (e.g., "ECC 6.0 Ehp 7")
            system_env: Environment configuration for this collection
        """
        self.collection_name = collection_name
        self.display_name = display_name
        self.system_env = system_env

    @classmethod
    def from_env_map(
        cls, env_map: Dict[str, CollectionEnvironment]
    ) -> "MultiCollectionService":
        """
        Create a multi-collection service from an environment map.

        Args:
            env_map: Map of display_name -> CollectionEnvironment

        Returns:
            MultiCollectionService instance managing multiple collections
        """
        return MultiCollectionService(env_map)

    def get_collection_metadata(self) -> CollectionMetadata:
        """
        Get metadata for this collection.

        Returns:
            CollectionMetadata with index information

        Raises:
            HTTPException: If config files are missing or invalid
        """
        env = self.system_env

        # Load query config
        try:
            with env.query_config_path.open("r", encoding="utf-8") as config_file:
                config_data = json.load(config_file)
        except FileNotFoundError:
            logger.exception(
                "Missing query config for collection %s at %s",
                self.collection_name,
                env.query_config_path,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Query configuration missing for {self.display_name}",
            ) from None
        except json.JSONDecodeError:
            logger.exception(
                "Invalid JSON query config for collection %s at %s",
                self.collection_name,
                env.query_config_path,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Query configuration invalid for {self.display_name}",
            ) from None

        # Extract model entries
        model_entries = config_data.get("model_to_collections", {})
        if not isinstance(model_entries, dict):
            logger.error(
                "model_to_collections missing or malformed for collection %s",
                self.collection_name,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Query configuration invalid for {self.display_name}",
            )

        # Build model list with document counts
        models: List[Dict[str, Any]] = []
        total_documents = 0
        for model_name, metadata in model_entries.items():
            model_doc_count = 0
            if isinstance(metadata, dict):
                total_value = metadata.get("total_documents")
                try:
                    if total_value is not None:
                        model_doc_count = int(total_value)
                except (TypeError, ValueError):
                    logger.warning(
                        "Non-numeric total_documents for model %s in collection %s",
                        model_name,
                        self.collection_name,
                    )
                    model_doc_count = 0

            total_documents += model_doc_count
            models.append(
                {
                    "model_name": model_name,
                    "total_documents": model_doc_count,
                }
            )

        models.sort(key=lambda item: str(item["model_name"]))

        # Load model registry
        try:
            model_registry = self._build_model_registry_summary()
        except Exception:
            logger.exception(
                "Failed to load model registry for collection %s using target %s",
                self.collection_name,
                env.model_registry_target,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Model registry unavailable for {self.display_name}",
            ) from None

        # Build system fields metadata
        system_fields = [
            {
                "field": field,
                "json_schema_type": json_type,
                "base_type": base_type,
            }
            for field, json_type, base_type in SYSTEM_METADATA_FIELDS
        ]
        system_fields.sort(key=lambda item: item["field"])

        return CollectionMetadata(
            collection_name=self.collection_name,
            display_name=self.display_name,
            discriminator_field=env.discriminator_field,
            embedding_model=env.embedding_model,
            total_documents=total_documents,
            models=models,
            model_registry=model_registry,
            system_fields=system_fields,
        )

    async def execute_query(
        self, query: str, limit: int = 500, output_format: str = "json"
    ) -> CollectionQueryResult:
        """
        Execute a ChromaSQL query against this collection.

        Args:
            query: ChromaSQL query string
            limit: Maximum number of rows to return
            output_format: Output format (currently only "json" supported)

        Returns:
            CollectionQueryResult with query results

        Raises:
            HTTPException: If query execution fails
        """
        # Build query executor configuration
        try:
            executor_kwargs = build_query_executor_kwargs(self.system_env)
        except Exception as e:
            logger.exception("Failed to build query executor configuration")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to configure query executor: {str(e)}",
            ) from None

        # Execute the query
        try:
            async with QueryExecutor(**executor_kwargs) as executor:
                result = await executor.execute(query)

                # Limit rows if requested
                rows = result.rows[:limit]

                return CollectionQueryResult(
                    query=result.query,
                    total_rows=result.total_rows,
                    collections_queried=result.collections_queried,
                    rows=rows,
                    rows_returned=len(rows),
                )
        # User errors (HTTP 400):
        # - ChromaSQLParseError: Invalid SQL syntax, malformed queries
        # - ChromaSQLPlanningError: Valid syntax but logical
        # errors (non-existent collections, invalid fields)
        except (ChromaSQLParseError, ChromaSQLPlanningError) as e:
            logger.warning("ChromaSQL query error: %s", str(e))
            raise HTTPException(
                status_code=400,
                detail=f"Invalid ChromaSQL query: {str(e)}",
            ) from None
        # ChromaSQLExecutionError can be either user or system error
        # Check if it's a wrapped planning error (user error)
        # or a real execution error (system error)
        except ChromaSQLExecutionError as e:
            # Planning errors are wrapped as execution errors
            # with "Failed to build query plan:" prefix
            # or have ChromaSQLPlanningError as the cause
            is_planning_error = "Failed to build query plan:" in str(e) or isinstance(
                e.__cause__, ChromaSQLPlanningError
            )

            if is_planning_error:
                # User error: invalid query logic
                logger.warning("ChromaSQL planning error (wrapped): %s", str(e))
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid ChromaSQL query: {str(e)}",
                ) from None
            else:
                # System error: database connection, permissions, etc.
                logger.exception("ChromaSQL execution error")
                raise HTTPException(
                    status_code=500,
                    detail=f"Query execution failed: {str(e)}",
                ) from None
        # Other system errors (HTTP 500):
        # - Unexpected errors during query execution
        except Exception as e:
            logger.exception("Failed to execute ChromaSQL query")
            raise HTTPException(
                status_code=500,
                detail=f"Query execution failed: {str(e)}",
            ) from None

    def _build_model_registry_summary(self) -> List[Dict[str, Any]]:
        """
        Build a serializable summary of the model registry.

        Returns:
            List of model registry entries with fields and metadata
        """
        registry = load_model_registry(self.system_env)
        summary: List[Dict[str, Any]] = []
        for model_name, spec in registry.items():
            summary.append(
                {
                    "model_name": model_name,
                    "fields": self._summarise_model_fields(spec.model),
                    "document_field": list(spec.semantic_fields),
                    "metadata_fields": list(spec.keyword_fields),
                }
            )

        summary.sort(key=lambda item: item["model_name"])
        return summary

    @staticmethod
    def _summarise_model_fields(model: Type[BaseModel]) -> List[Dict[str, str]]:
        """
        Convert a Pydantic model definition into a list of JSON schema field summaries.

        Args:
            model: Pydantic model class

        Returns:
            List of field summaries with JSON schema types
        """
        schema = model.model_json_schema()
        properties = schema.get("properties", {})

        fields_summary: List[Dict[str, str]] = []
        for field_name, field_info in model.model_fields.items():
            schema_name = field_info.alias or field_name
            property_schema = properties.get(schema_name, {})
            json_schema_type = CollectionService._extract_json_schema_type(
                property_schema
            )
            base_type = CollectionService._map_json_type_to_base(json_schema_type)

            fields_summary.append(
                {
                    "field": schema_name,
                    "json_schema_type": json_schema_type,
                    "base_type": base_type,
                }
            )

        fields_summary.sort(key=lambda item: item["field"])
        return fields_summary

    @staticmethod
    def _extract_json_schema_type(schema_fragment: Mapping[str, Any]) -> str:
        """
        Derive the JSON schema type descriptor from a schema fragment.

        Args:
            schema_fragment: JSON schema fragment

        Returns:
            Type descriptor string
        """
        if not isinstance(schema_fragment, Mapping):
            return "unknown"

        type_value = schema_fragment.get("type")
        if isinstance(type_value, str):
            return type_value
        if isinstance(type_value, (list, tuple)) and not isinstance(
            type_value, (str, bytes)
        ):
            string_types = sorted(
                {str(value) for value in type_value if isinstance(value, (str, bytes))}
            )
            if string_types:
                return " | ".join(string_types)

        for key in ("anyOf", "oneOf", "allOf"):
            options = schema_fragment.get(key)
            if isinstance(options, (list, tuple)):
                option_types: List[str] = []
                for option in options:
                    if isinstance(option, Mapping):
                        option_type = option.get("type")
                        if isinstance(option_type, str):
                            option_types.append(option_type)
                        elif isinstance(option_type, (list, tuple)) and not isinstance(
                            option_type, (str, bytes)
                        ):
                            option_types.extend(
                                str(value)
                                for value in option_type
                                if isinstance(value, (str, bytes))
                            )
                if option_types:
                    unique_types = sorted(set(option_types))
                    return " | ".join(unique_types)

        if "$ref" in schema_fragment:
            return "object"

        return "unknown"

    @staticmethod
    def _map_json_type_to_base(json_type: str) -> str:
        """
        Map a JSON schema type descriptor onto a simplified base type.

        Args:
            json_type: JSON schema type string

        Returns:
            Base type string (String, Number, or Boolean)
        """
        type_mapping = {
            "string": "String",
            "number": "Number",
            "integer": "Number",
            "boolean": "Boolean",
        }

        for candidate in json_type.split("|"):
            base = type_mapping.get(candidate.strip().lower())
            if base is not None:
                return base

        return "String"


class MultiCollectionService:
    """
    Service for managing multiple collections.

    This class wraps multiple CollectionService instances and provides
    methods to work with all collections at once.
    """

    def __init__(self, env_map: Dict[str, CollectionEnvironment]):
        """
        Initialize the multi-collection service.

        Args:
            env_map: Map of display_name -> CollectionEnvironment
        """
        self.services: Dict[str, CollectionService] = {}
        for display_name, system_env in env_map.items():
            # Key by sanitized collection_name for API lookups, but preserve display_name
            self.services[system_env.collection_name] = CollectionService(
                collection_name=system_env.collection_name,
                display_name=display_name,
                system_env=system_env,
            )

    def get_all_collection_metadata(self) -> List[Dict[str, Any]]:
        """
        Get metadata for all collections.

        Returns:
            List of collection metadata dictionaries
        """
        metadata_list = []
        for service in self.services.values():
            metadata = service.get_collection_metadata()
            metadata_list.append(metadata.model_dump())

        return metadata_list

    def get_service(self, collection_name: str) -> Optional[CollectionService]:
        """
        Get the service for a specific collection.

        Args:
            collection_name: Name of the collection

        Returns:
            CollectionService instance or None if not found
        """
        return self.services.get(collection_name)

    async def execute_query(
        self, collection_name: str, query: str, limit: int = 500
    ) -> CollectionQueryResult:
        """
        Execute a query on a specific collection.

        Args:
            collection_name: Name of the collection to query
            query: ChromaSQL query string
            limit: Maximum number of rows to return

        Returns:
            CollectionQueryResult with query results

        Raises:
            HTTPException: If collection not found or query fails
        """
        service = self.get_service(collection_name)
        if service is None:
            available = ", ".join(self.services.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Unknown collection '{collection_name}'. Available: {available}",
            )

        return await service.execute_query(query, limit)

"""
ChromaSQL Server Module.

This module provides a FastAPI server that exposes ChromaSQL query endpoints
for one or more collections (local or cloud).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChromaSQLQueryRequest(BaseModel):
    """Request model for executing ChromaSQL queries."""

    query: str = Field(..., description="ChromaSQL query string")
    limit: int = Field(
        default=500, ge=1, le=10000, description="Maximum number of rows to return"
    )
    output_format: str = Field(default="json", description="Output format (json only)")


class ChromaSQLQueryResult(BaseModel):
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


def create_chromasql_router(multi_collection_service: Any) -> APIRouter:
    """
    Create a FastAPI router with ChromaSQL endpoints.

    Args:
        multi_collection_service: MultiCollectionService instance managing collections

    Returns:
        APIRouter with /indices and /chromasql/execute endpoints
    """
    router = APIRouter(prefix="/api/chromasql", tags=["chromasql"])

    @router.get("/indices", response_model=List[Dict[str, Any]])
    def list_indices() -> List[Dict[str, Any]]:
        """
        Return metadata for all configured collections.

        Returns:
            List of collection metadata dictionaries
        """
        return multi_collection_service.get_all_collection_metadata()

    @router.post("/execute", response_model=Dict[str, Any])
    async def execute_chromasql_query(
        request: ChromaSQLQueryRequest,
        collection: str,
    ) -> Dict[str, Any]:
        """
        Execute a ChromaSQL query against a specified collection.

        Args:
            request: Query request containing the query string and options
            collection: Collection name to query

        Returns:
            Query execution results with rows, total count, and metadata

        Raises:
            HTTPException: If collection is unknown or query execution fails
        """
        logger.info(
            f"ChromaSQL query request - collection: {collection}, "
            f"query: {request.query[:100]}..."
        )

        result = await multi_collection_service.execute_query(
            collection, request.query, request.limit
        )
        return result.model_dump()

    @router.get("/health")
    def health_check() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "chromasql"}

    return router


def create_chromasql_app(
    multi_collection_service: Any,
    *,
    cors_allow_origins: List[str] | None = None,
    cors_allow_methods: List[str] | None = None,
    cors_allow_headers: List[str] | None = None,
    cors_allow_credentials: bool = True,
) -> FastAPI:
    """
    Create a FastAPI application with ChromaSQL endpoints.

    Args:
        multi_collection_service: MultiCollectionService instance managing collections
        cors_allow_origins: CORS allowed origins (defaults to ["*"])
        cors_allow_methods: CORS allowed methods (defaults to ["*"])
        cors_allow_headers: CORS allowed headers (defaults to ["*"])
        cors_allow_credentials: CORS allow credentials flag

    Returns:
        FastAPI application with ChromaSQL routes
    """
    cors_allow_origins = cors_allow_origins or ["*"]
    cors_allow_methods = cors_allow_methods or ["*"]
    cors_allow_headers = cors_allow_headers or ["*"]

    app = FastAPI(
        title="ChromaSQL Server",
        description="SQL-like query interface for ChromaDB collections",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=cors_allow_methods,
        allow_headers=cors_allow_headers,
    )

    # Include ChromaSQL router
    router = create_chromasql_router(multi_collection_service)
    app.include_router(router)

    @app.get("/")
    def root() -> Dict[str, Any]:
        """Root endpoint."""
        return {
            "service": "ChromaSQL Server",
            "version": "0.1.0",
            "endpoints": {
                "health": "/api/chromasql/health",
                "indices": "/api/chromasql/indices",
                "execute": "/api/chromasql/execute?collection=<name>",
            },
        }

    return app

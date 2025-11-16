# ChromaSQL Python Package Overview

The ChromaSQL Python package wraps the query language with helpers that let you
parse, plan, and execute requests against ChromaDB collections. It also includes
utilities for running the same query across multiple collections with smart
routing and result merging.

## Core Capabilities

- **Parsing** – Convert SQL-flavoured strings into typed AST nodes with
  `chromasql.parse`.
- **Planning** – Validate queries and produce executable plans using
  `chromasql.build_plan` or `chromasql.plan_to_dict`.
- **Execution** – Run plans against a Chroma collection with automatic handling
  of vector queries, metadata-only lookups, ordering, and pagination.
- **Embedding Integration** – Supply inline text or literal vectors; the engine
  calls your embed function on demand for text entries and supports batch
  queries.
- **Explain Output** – Inspect internal planner decisions without hitting
  ChromaDB by turning plans into dictionaries.

## Multi-Collection Support

- **Routing Abstractions** – Use `CollectionRouter` protocols to decide which
  collections to hit based on metadata filters or custom logic.
- **Async Execution** – The `execute_multi_collection` helper fans a query out
  across the routed collections, executes them concurrently, and merges the
  results.
- **Adapters** – Drop-in adapters wrap common async ChromaDB clients and handle
  collection caching, error handling, and retries.
- **Extensible Strategies** – Build bespoke routers for tenant isolation, model
  separation, or any discriminator field present in your metadata.

## When to Use the Package

- You need a reliable bridge between ChromaSQL and ChromaDB’s
  Python client.
- You want to expose ChromaSQL as part of an API, agent, or orchestration layer
  without writing your own planner or executor.
- Your deployment queries multiple collections and requires predictable routing
  rules, graceful fallbacks, and merged result sets.

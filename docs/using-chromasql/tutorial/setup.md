# ChromaSQL Tutorial

Welcome! This guide shows you **every clause** the ChromaSQL DSL currently
supports, why you might use it, and a few common pitfalls to avoid.  Follow it
sequentially – the later sections build on the earlier ones.

!!! tip
    ChromaSQL is read-only.  It queries ChromaDB collections but does not create, mutate, or delete data.

## Demo Collection Schema

To keep the examples concrete we will query an imaginary `products` collection.
ChromaSQL operates on collections, so think of this as one table whose rows were
previously ingested into ChromaDB.

**Core columns (ChromaSQL defaults)**

- `id`: Stable identifier for each row. Present in every collection.
- `document`: The natural-language payload that was embedded (plain text).
- `embedding`: The stored vector. Only returned when explicitly requested.
- `metadata`: JSON object with user-defined attributes (keys vary by dataset).

These four columns exist regardless of the domain you model—you will see them in
every example and in real queries, even if you never project or filter by all of
them.

**Sample metadata keys for this tutorial (domain-specific)**

- `metadata.category` (string): Product category (e.g. `outerwear`).
- `metadata.tags` (list of strings): Lightweight tags, such as `["waterproof"]`.
- `metadata.price` (number): Price in USD.
- `metadata.gender` (string): Target audience (`men`, `women`, `unisex`).
- `metadata.brand` (string): Brand name.
- `metadata.model` (string): Internal classifier used in routing examples later on.

!!! note "Use-case specific metadata"
    When an example introduces an additional key (for example `metadata.system` in the reranking section or `metadata.fieldname` in routing examples), it represents a hypothetical field that exists in this sample schema for illustration. 
    
    Adjust the field names to match the metadata that lives in your own collections.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>
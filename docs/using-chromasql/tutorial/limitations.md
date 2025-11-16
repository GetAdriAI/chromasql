# Current Limitations of ChromaSQL

* **Joins / multi-collection SQL.**  Execute separate queries if you need to
  merge results from multiple collections.
* **Aggregations / GROUP BY.**  Fetch the rows and aggregate in Python.
* **Streaming or async execution.**  The executor currently collects results
  eagerly.  Wrap it yourself if you need incremental delivery.
* **Custom arithmetic in ORDER BY.**  Only `distance`, `id`, and metadata paths
  are supported today.  Blend scores (e.g. `0.8 * SIM_SCORE + …`) in your own
  post-processing if you need that behaviour.

If your workload depends on these gaps, we suggest that you build the missing behaviour in your application layer and follow the project changelog for roadmap updates.

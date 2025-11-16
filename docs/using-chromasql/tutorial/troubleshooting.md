# Troubleshooting and Misconceptions

| Symptom | Likely cause |
|---------|--------------|
| `ChromaSQLParseError: Unexpected token` | Typo in your query, or clause order incorrect (e.g. `WHERE_DOCUMENT` before `WHERE`). |
| `ChromaSQLPlanningError: TOPK can only be used with EMBEDDING queries` | You forgot the `USING EMBEDDING` clause. |
| Distances missing in results | You ran a filter-only query or dropped `distance` from the projection. |
| Batch query returns unexpected duplicates | Remember that `TOPK` applies per batch item; dedupe in post-processing if needed. |
| Rerank hint seemingly ignored | The executor returns the hint in the plan; you still need to implement the MMR reranker. |

If you bump into behaviour that feels surprising or want to propose a language
extension, check out `CONTRIBUTING.md` for instructions on how to get involved.

!!! tip "Check clause order first"
    Most parser errors come from clauses being out of order.  Compare your query
    to the examples earlier in the tutorial before digging into deeper fixes.

<div class="grid cards" markdown>

- [:material-github: **Still Stuck?**](https://github.com/GetAdriAI/chromasql/issues/new?title=Docs%20Issue&labels=documentation){ target="_blank" }<br/>
  File a GitHub issue with the query and executor context if you run into a reproducible bug.

</div>
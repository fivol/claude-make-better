# Angle Efficiency · light

Wasted work the diff introduces:

- **redundant computation or repeated I/O** — the same value derived twice, the same file or endpoint
  read once per iteration
- **independent operations run sequentially** that could run together
- **blocking work added to startup or to a hot path**
- **long-lived objects built from closures or captured environments** — the closure keeps its whole
  enclosing scope alive for the object's lifetime, which is a leak when that scope holds large
  values. Prefer a structure that copies only the fields it needs.

Name the cost in terms of what actually grows: per request, per row, per render, per boot. **An
efficiency finding with no scaling argument is a style preference**, and belongs in nobody's report.

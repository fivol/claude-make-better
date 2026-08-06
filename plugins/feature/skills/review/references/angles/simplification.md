# Angle Simplification · light

Unnecessary complexity the diff adds:

- **redundant or derivable state** — a field that is always a function of two others, a flag that
  duplicates what a null check already says
- **copy-paste with slight variation** where one parameterized form would do
- **nesting deep enough that the happy path is hard to find** — a guard clause would flatten it
- **dead code left behind** — a branch now unreachable, an argument now always the same value, an
  export with no importer, a helper whose last caller the diff removed

Name the simpler form that does the same job, concretely enough to apply. Do not report a
restructuring whose only argument is taste.

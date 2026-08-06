# Angle D — language-pitfall specialist · deep

The classic pitfalls of this diff's language, framework or dialect. Flag only instances **the diff
introduces**.

- **JS/TS** — falsy-zero and empty-string checks, `==` coercion, closure-captured loop vars,
  unawaited promises, `Array.sort` without a comparator, `JSON.parse` on a value that can be `undefined`
- **Python** — mutable default args, late-binding closures, bare `except:` swallowing
  `KeyboardInterrupt`, integer vs float division, a generator consumed twice
- **Go** — writing to a nil map, range-var capture, a deferred `Close` whose error is dropped
- **SQL** — injection through string interpolation, a predicate the existing index can't serve,
  `NULL` semantics in `NOT IN`
- **CSS/SCSS** — a fixed `width` where content can exceed it, cascade order changed by a nested media
  query, a negation query that leaves a gap on fractional viewports, an `!important` that now
  overrides a rule it previously lost to
- **Any language** — timezone/DST drift, float equality, non-deterministic iteration or hashing order

If this diff's language isn't listed, apply the same discipline to whatever its real footguns are.

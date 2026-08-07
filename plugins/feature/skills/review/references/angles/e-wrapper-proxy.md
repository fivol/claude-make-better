# Angle E — wrapper/proxy correctness · deep

Applies when the change adds or modifies a type that wraps another: a cache, proxy, decorator,
adapter, façade or retry layer.

- **Every method must route to the wrapped instance**, not back through a registry, session or
  global. A caching provider whose `delegate` resolves ids via `session.get(...)` instead of
  `delegate.get(...)` re-enters its own cache, or recurses until the stack ends.
- **The wrapper must forward every method its callers actually use.** Grep the callers and check the
  surface, including methods inherited from an interface that the wrapper silently doesn't implement.
- **State the wrapper holds must be invalidated by the writes that go through it** — and you should
  name the writes that *don't* go through it, because those are where staleness comes from.

No wrapper in the diff ⇒ return nothing. Do not stretch the angle to fit an ordinary function.

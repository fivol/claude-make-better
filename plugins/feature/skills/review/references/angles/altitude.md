# Angle Altitude — is the change made at the right depth? · deep

Is each change made at the right level, or is it a bandaid one level too shallow?

The tell is a **special case layered onto shared infrastructure**: a `if (locale === 'fr')` inside a
generic layout rule, a per-caller workaround inside a shared helper, a second code path that exists
only because the first one wasn't generalized. Prefer generalizing the underlying mechanism over
accumulating special cases.

This is the one angle allowed to say **"the whole approach is one level too shallow"**. Say it
plainly, name the deeper change that would replace it, and let triage decide whether it is fixable
inside this change or is a follow-up.

An altitude finding still needs a concrete cost: what breaks, or what will have to be edited again,
because the change sits at this level. **"Not elegant" is not a finding.**

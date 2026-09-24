Bug report for the pytest repository in ./repo.

`MonkeyPatch.setattr` leaves a new item in `vars(target)` after cleanup when overriding an inherited attribute of a non-class object.

If the inherited attribute is not a descriptor, a reference to the inherited attribute gets left in `vars(target)` after cleanup. This is not particularly problematic usually, but it consumes some memory and leaves the target in a different state than it was in before monkeypatching.

If the inherited attribute is a `__get__` descriptor, however, this bug is problematic. The result of descriptor binding will get computed once and stored in `vars(target)` during cleanup, blocking the descriptor's dynamic lookup capability for all lookups after the `MonkeyPatch` gets torn down. This has an effect similar to using `functools.cached_property` on a property that should not be cached.

Please fix this so that after `undo()` the target object is in exactly the state it was in before patching, add regression tests, and run the relevant tests before you finish.

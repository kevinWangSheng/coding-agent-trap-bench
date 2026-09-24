Bug report for the ripgrep repository in ./repo (the `ignore` crate, crates/ignore).

`WalkParallel::visit()` can hang forever if the `ParallelVisitor::visit()` implementation panics. The same happens when passing a closure to `WalkParallel::run()`. Instead of the panic propagating to the caller, the process just hangs. Example:

```rust
WalkBuilder::new(dir)
    .threads(40)
    .build_parallel()
    .run(|| Box::new(|_| panic!("oops!")));
// expected: panics; actual: sometimes/often hangs forever
```

A panic raised anywhere in user-supplied callbacks during a parallel walk (including while the visitors are being built) should propagate to the caller and must never deadlock the walk.

Please fix this in the `ignore` crate, add tests, and run the relevant tests before you finish. Note that a hanging test will hang your test run, so use a timeout when running tests.

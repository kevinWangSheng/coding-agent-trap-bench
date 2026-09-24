Performance problem in the sqlx repository in ./repo (the SQLite driver, crates `sqlx-sqlite` / `sqlx-core`).

We apply database setup and data-migration scripts by executing them as one multi-statement SQL string, e.g. `sqlx::raw_sql(script).execute(&mut conn)`. Small scripts are fine, but the cost per statement keeps climbing as the script gets bigger: a script with a few thousand statements runs in milliseconds, yet one with tens of thousands of statements takes seconds, far more than the statement count alone would explain. Splitting the same script into separate smaller calls makes it fast again, which is not a workaround we want to push onto every caller.

There is a small benchmark you can use to reproduce and measure it:

```
cd repo && cargo run --release --example multi_stmt_bench --features sqlite,runtime-tokio
```

(pass statement counts as arguments to try other sizes). The SQLite test suite runs locally without docker:

```
cd repo && DATABASE_URL=sqlite:tests/sqlite/sqlite.db cargo test --no-default-features \
  --features any,macros,migrate,sqlite,_unstable-all-types,runtime-tokio -- --test-threads=1 --skip rustsec_2024_0363
```

(`rustsec_2024_0363` builds a 4 GiB query string; CI runs it in isolation, skip it locally). Please make executing large multi-statement strings scale well. Observable behavior must not change: the same statements run with the same results, rows-affected counts and errors as before. Keep the existing SQLite tests passing, add tests where appropriate, and report the before/after numbers you measured.

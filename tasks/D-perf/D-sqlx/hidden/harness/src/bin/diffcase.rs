//! Differential test cases. `diffcase list` prints case names; `diffcase run <name>` prints the
//! observable behavior of that case as JSON. grade.py runs each case in its own process under a
//! hard timeout, against the pristine and the candidate build, and compares outputs.

use d_sqlx_harness::{connect, dump, inject_error, ledger_script, run_events, shape_script, LEDGER_SETUP, SHAPE_SETUP};
use serde_json::json;
use sqlx::{AssertSqlSafe, Executor, SqlSafeStr};

#[derive(Clone, Copy)]
enum Mode {
    Raw,
    Prepared,
    PreparedTwice,
    Describe,
}

struct Case {
    name: String,
    setup: &'static str,
    script: String,
    mode: Mode,
}

fn cases() -> Vec<Case> {
    let mut v = Vec::new();
    let mut add = |name: String, setup: &'static str, script: String, mode: Mode| {
        v.push(Case { name, setup, script, mode })
    };
    let fixed: &[(&str, &str)] = &[
        ("empty", ""),
        ("whitespace_only", "   \n\t \r\n"),
        ("semicolons_only", ";;;"),
        ("semicolons_spaced", " ; ;\n; "),
        ("line_comment_only", "-- nothing to see; here"),
        ("block_comment_only", "/* only; a comment */"),
        ("comments_only_mixed", "-- a;\n/* b; */\n-- c\n"),
        ("single_no_semicolon", "SELECT 1"),
        ("single_trailing_semicolon", "SELECT 1;"),
        ("single_trailing_ws", "SELECT 1;   \n\n\t"),
        ("trailing_line_comment", "SELECT 1; -- done"),
        ("trailing_block_comment", "SELECT 1; /* done */"),
        ("trailing_one_space", "SELECT 1; "),
        ("trailing_double_semicolon", "SELECT 1;;"),
        ("trailing_lone_dash", "SELECT 1; -"),
        ("trailing_unicode_comment", "SELECT 'ok'; -- ✓ ünïcödé"),
        ("unicode_last_literal", "INSERT INTO t (a, b) VALUES (1, 'x'); INSERT INTO t (a, b) VALUES (2, '終わり🦀')"),
        ("leading_semicolons", "; ; SELECT 1;;"),
        ("quoted_semicolons", "INSERT INTO t (a, b) VALUES (1, 'a;b;c'); INSERT INTO t (a, b) VALUES (2, ';'); SELECT b FROM t ORDER BY a"),
        ("quoted_comment_markers", "INSERT INTO t (a, b) VALUES (1, '-- x /* y */'); SELECT b FROM t"),
        ("ident_with_semicolon", "INSERT INTO \"odd;name\" (v) VALUES ('1;2'); SELECT v FROM \"odd;name\""),
        ("select_rows_midway", "INSERT INTO t (a, b) VALUES (1, 'x'), (2, 'y'); SELECT a, b FROM t ORDER BY a; UPDATE t SET a = a + 10; SELECT * FROM t ORDER BY a;"),
        ("unterminated_literal", "SELECT 1; SELECT 'oops; SELECT 2;"),
        ("unterminated_block_comment", "SELECT 1; /* never closed; SELECT 2;"),
        ("error_first", "SELEC 1; INSERT INTO t (a) VALUES (1);"),
        ("error_mid", "INSERT INTO t (a) VALUES (1); INSERT INTO t (a) VALUES (;); INSERT INTO t (a) VALUES (3);"),
        ("error_last", "INSERT INTO t (a) VALUES (1); INSERT INTO t (a) VALUES (2); SELEC 3"),
        ("runtime_error_mid", "INSERT INTO u (k, v) VALUES (1, 'a'); INSERT INTO u (k, v) VALUES (1, 'dup'); INSERT INTO u (k, v) VALUES (2, 'b');"),
        ("missing_table_mid", "INSERT INTO t (a) VALUES (1); INSERT INTO nope (a) VALUES (2); INSERT INTO t (a) VALUES (3);"),
        ("tx_block", "BEGIN; INSERT INTO t (a) VALUES (1); INSERT INTO t (a) VALUES (2); COMMIT; SELECT count(*) FROM t;"),
        ("ddl_then_use", "CREATE TABLE z (q TEXT); INSERT INTO z VALUES ('a;b'); ALTER TABLE z ADD COLUMN r INTEGER DEFAULT 5; SELECT * FROM z;"),
    ];
    for (name, script) in fixed {
        for (suffix, mode) in [("raw", Mode::Raw), ("prep", Mode::Prepared)] {
            add(format!("{name}.{suffix}"), SHAPE_SETUP, script.to_string(), mode);
        }
    }
    for (name, script) in [("twice_multi", "INSERT INTO t (a, b) VALUES (1, 'x;y'); UPDATE t SET a = a + 1; SELECT a, b FROM t ORDER BY rowid;"),
                           ("twice_trailing", "SELECT 1; SELECT 2; -- tail\n")] {
        add(format!("{name}.prep2"), SHAPE_SETUP, script.to_string(), Mode::PreparedTwice);
    }
    for (name, script) in [("describe_multi", "SELECT a FROM t; SELECT b, a FROM t WHERE a = 1; -- end"),
                           ("describe_single", "SELECT a, b FROM t   ")] {
        add(format!("{name}.describe"), SHAPE_SETUP, script.to_string(), Mode::Describe);
    }
    // Generated shapes: sizes 1..~400 statements, raw and prepared paths.
    for seed in 1..=40u64 {
        let n = [1usize, 2, 3, 7, 25, 120, 400][(seed % 7) as usize];
        let s = shape_script(n, seed);
        add(format!("shape{seed:02}_n{n}.raw"), SHAPE_SETUP, s.clone(), Mode::Raw);
        if seed % 4 == 0 {
            add(format!("shape{seed:02}_n{n}.prep"), SHAPE_SETUP, s.clone(), Mode::Prepared);
        }
        if seed % 2 == 1 {
            add(format!("shape{seed:02}_n{n}_err.raw"), SHAPE_SETUP, inject_error(&s, seed), Mode::Raw);
        }
    }
    // Larger realistic workloads, compared by full dump.
    for (seed, n) in [(101u64, 1500usize), (202, 3000), (303, 6000)] {
        add(format!("ledger{seed}_n{n}.raw"), LEDGER_SETUP, ledger_script(n, seed), Mode::Raw);
        add(format!("ledger{seed}_n{n}_err.raw"), LEDGER_SETUP, inject_error(&ledger_script(n, seed), seed), Mode::Raw);
    }
    // Embedded NUL bytes: the fixed build must *return an error* quickly (graded separately).
    for (name, script) in [("nul_between", "SELECT 1;\0SELECT 2"),
                           ("nul_trailing", "SELECT 1\0"),
                           ("nul_only", "\0"),
                           ("nul_after_all", "INSERT INTO t (a) VALUES (1); SELECT 2;\0"),
                           ("nul_in_literal", "INSERT INTO t (a, b) VALUES (1, 'a\0b'); SELECT 3")] {
        add(format!("{name}.nul.raw"), SHAPE_SETUP, script.to_string(), Mode::Raw);
        add(format!("{name}.nul.prep"), SHAPE_SETUP, script.to_string(), Mode::Prepared);
    }
    v
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), sqlx::Error> {
    let args: Vec<String> = std::env::args().collect();
    let all = cases();
    match args.get(1).map(String::as_str) {
        Some("list") => {
            for c in &all {
                println!("{}", c.name);
            }
        }
        Some("run") => {
            let name = args.get(2).expect("case name");
            let case = all.iter().find(|c| &c.name == name).expect("unknown case");
            let mut conn = connect().await?;
            sqlx::raw_sql(case.setup).execute(&mut conn).await?;
            let events = match case.mode {
                Mode::Raw => run_events(&mut conn, &case.script, false).await,
                Mode::Prepared => run_events(&mut conn, &case.script, true).await,
                Mode::PreparedTwice => {
                    let mut e = run_events(&mut conn, &case.script, true).await;
                    e.push(json!("--second-run--"));
                    e.extend(run_events(&mut conn, &case.script, true).await);
                    e
                }
                Mode::Describe => {
                    let sql = AssertSqlSafe(case.script.clone()).into_sql_str();
                    match (&mut conn).describe(sql).await {
                        Ok(d) => vec![json!({ "describe": format!("{d:?}") })],
                        Err(e) => vec![d_sqlx_harness::render_err(&e)],
                    }
                }
            };
            let db = dump(&mut conn).await;
            println!("{}", json!({ "events": events, "db": db }));
        }
        _ => eprintln!("usage: diffcase list | diffcase run <case>"),
    }
    Ok(())
}

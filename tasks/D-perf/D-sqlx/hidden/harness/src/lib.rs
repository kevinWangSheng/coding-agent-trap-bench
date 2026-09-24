//! Hidden grading harness for task D-sqlx: workload generators and result capture.
//!
//! Everything here must behave identically when built against the pristine repo and against a
//! candidate repo; only the sqlx crate underneath changes.

use futures_util::TryStreamExt;
use serde_json::{json, Value};
use sqlx::{AssertSqlSafe, Column, Connection, Either, Executor, Row, SqliteConnection, TypeInfo, ValueRef};

/// xorshift64*: tiny, deterministic, dependency-free.
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    pub fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    pub fn below(&mut self, n: u64) -> u64 {
        self.next() % n.max(1)
    }
    pub fn pick<'a, T>(&mut self, xs: &'a [T]) -> &'a T {
        &xs[self.below(xs.len() as u64) as usize]
    }
}

pub const LEDGER_SETUP: &str = "CREATE TABLE ledger (id INTEGER PRIMARY KEY, acct TEXT NOT NULL, \
     amount INTEGER NOT NULL, note TEXT); \
     CREATE TABLE audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, msg TEXT);";

const NOTES: &[&str] = &[
    "paid; thanks",
    "x -- not a comment",
    "/* literal */ ok",
    "it''s; fine",
    "semi;colon;s;;",
    "tab\there",
    "déjà vu; ünïcödé",
    "漢字;テスト",
    "emoji 🦀; end",
    "",
];

/// Hidden benchmark workload: ledger/audit schema, mixed DML + some DDL, quoted semicolons,
/// block and line comments, empty statements, and trailing whitespace after the last statement.
pub fn ledger_script(n: usize, seed: u64) -> String {
    let mut rng = Rng::new(seed);
    let mut s = String::with_capacity(n * 96);
    let mut inserted: u64 = 0;
    for i in 0..n {
        if i > 0 {
            s.push_str(*rng.pick(&["\n", " ", "\n\n", "\t", "\r\n"]));
        }
        if i == n / 3 {
            s.push_str("CREATE INDEX IF NOT EXISTS ledger_acct ON ledger(acct);");
            continue;
        }
        let r = rng.below(100);
        if r < 50 {
            let pad = "~".repeat(rng.below(48) as usize);
            s.push_str(&format!(
                "INSERT INTO ledger (acct, amount, note) VALUES ('acct-{}', {}, '{}{}');",
                rng.below(500),
                rng.below(20_000) as i64 - 10_000,
                rng.pick(NOTES),
                pad
            ));
            inserted += 1;
        } else if r < 72 {
            s.push_str(&format!(
                "UPDATE ledger SET amount = amount + {}, note = note || ';' WHERE id = {};",
                rng.below(100),
                1 + rng.below(inserted + 1)
            ));
        } else if r < 80 {
            s.push_str(&format!(
                "INSERT INTO audit (msg) VALUES ('evt {i}; code=' || {});",
                rng.below(1000)
            ));
        } else if r < 84 {
            s.push_str(&format!("DELETE FROM audit WHERE seq = {};", 1 + rng.below(i as u64 + 1)));
        } else if r < 86 {
            let k = rng.below(16);
            if rng.below(2) == 0 {
                s.push_str(&format!("CREATE TABLE IF NOT EXISTS scratch_{k} (v TEXT, w INTEGER);"));
            } else {
                s.push_str(&format!("DROP TABLE IF EXISTS scratch_{k};"));
            }
        } else if r < 87 {
            // empty statement
            s.push(';');
        } else if r < 94 {
            s.push_str(&format!(
                "/* batch {i}; step */ UPDATE ledger SET note = 'n{i};' WHERE id = {}; -- trailing; comment {i}\n",
                1 + rng.below(inserted + 1)
            ));
        } else {
            s.push_str(&format!(
                "-- line comment; {i}\nINSERT INTO ledger (acct, amount, note) VALUES ('c', {i}, NULL);"
            ));
            inserted += 1;
        }
    }
    s.push_str(*rng.pick(&["\n  \t\n", "   ", "\n", "\r\n\r\n"]));
    s
}

const SHAPE_STMTS: &[&str] = &[
    "INSERT INTO t (a, b) VALUES (1, 'one')",
    "INSERT INTO t (a, b) VALUES (2, 'two; three')",
    "INSERT INTO t (a, b) VALUES (3, '-- dashes')",
    "INSERT INTO t (a, b) VALUES (4, '/* star */')",
    "INSERT INTO t (a, b) VALUES (5, 'quote '' ; inside')",
    "INSERT INTO t (a, b) VALUES (6, 'ñandú 😀')",
    "INSERT INTO t (a, b) VALUES (7, x'00ff10')",
    "INSERT INTO t (a, b) VALUES (8, 2.5)",
    "INSERT INTO \"odd;name\" (v) VALUES ('q')",
    "UPDATE t SET a = a * 2 WHERE a % 2 = 0",
    "UPDATE t SET b = b || 'é' WHERE a > 3",
    "DELETE FROM t WHERE a = 7",
    "SELECT a, b FROM t ORDER BY rowid",
    "SELECT count(*), 'lit;eral' FROM t",
    "SELECT 1 AS one, NULL AS nothing, 1.5 AS f, x'beef' AS blob",
    "CREATE TABLE IF NOT EXISTS w (z)",
    "INSERT INTO u (v) VALUES ('u;v')",
    "DROP TABLE IF EXISTS w",
    "CREATE INDEX IF NOT EXISTS t_a ON t(a)",
    "BEGIN",
    "COMMIT",
    "PRAGMA user_version = 7",
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 5) SELECT x FROM c",
];

const SHAPE_SEPS: &[&str] = &[
    ";", ";\n", " ; ", ";;", ";\n-- c;omment\n", ";/* x; */", ";\t", "; /* multi\nline; */\n", ";\r\n",
];

const SHAPE_TAILS: &[&str] = &[
    "", " ", "\n", ";", "; -- end", "; /* end */", "\n\n\t ", ";;", "; -- ünïcode tail ✓", ";\n\n",
];

pub const SHAPE_SETUP: &str =
    "CREATE TABLE t (a INTEGER, b); CREATE TABLE \"odd;name\" (v TEXT); \
     CREATE TABLE u (k INTEGER PRIMARY KEY, v TEXT);";

/// Random script shapes for the differential test. BEGIN/COMMIT are balanced so a script never
/// leaves a transaction open unless it errors.
pub fn shape_script(n: usize, seed: u64) -> String {
    let mut rng = Rng::new(seed ^ 0xD1FF);
    let mut s = String::new();
    if rng.below(3) == 0 {
        s.push_str(*rng.pick(&["-- leading comment; x\n", "/* lead; */ ", "\n\n  "]));
    }
    let mut in_tx = false;
    for i in 0..n {
        let mut stmt = *rng.pick(SHAPE_STMTS);
        if stmt == "BEGIN" && in_tx || stmt == "COMMIT" && !in_tx {
            stmt = "SELECT 'noop'";
        }
        if stmt == "BEGIN" {
            in_tx = true;
        } else if stmt == "COMMIT" {
            in_tx = false;
        }
        s.push_str(stmt);
        if i + 1 < n {
            s.push_str(*rng.pick(SHAPE_SEPS));
        }
    }
    if in_tx {
        s.push_str("; COMMIT");
    }
    s.push_str(*rng.pick(SHAPE_TAILS));
    s
}

/// Insert a syntax error at a random statement boundary of `script`.
pub fn inject_error(script: &str, seed: u64) -> String {
    let mut rng = Rng::new(seed ^ 0xBAD);
    let bad = *rng.pick(&[
        "INSERT INTO t VALUES (;",
        "UPDATE t SET WHERE a = 1;",
        "SELEC 1;",
        "INSERT INTO nope_missing_table VALUES (1);",
        "SELECT 'unterminated;",
    ]);
    let bounds: Vec<usize> = script.match_indices(';').map(|(i, _)| i + 1).collect();
    // Only split at boundaries where the prefix is syntactically complete: re-use shape pieces,
    // so any ';' outside quotes/comments works. We simply try each candidate in order.
    let mut idx = if bounds.is_empty() { script.len() } else { bounds[rng.below(bounds.len() as u64) as usize] };
    // Walk forward to a boundary that isn't inside a quote or comment.
    while idx < script.len() && !boundary_ok(&script[..idx]) {
        idx = script[idx..].find(';').map(|j| idx + j + 1).unwrap_or(script.len());
    }
    format!("{}\n{}\n{}", &script[..idx], bad, &script[idx..])
}

fn boundary_ok(prefix: &str) -> bool {
    // true if `prefix` ends outside of any string literal, identifier quote or comment
    let b = prefix.as_bytes();
    let (mut i, mut state) = (0, 0u8); // 0 normal, 1 'str', 2 "ident", 3 --comment, 4 /*comment*/
    while i < b.len() {
        let c = b[i];
        match state {
            0 => match c {
                b'\'' => state = 1,
                b'"' => state = 2,
                b'-' if b.get(i + 1) == Some(&b'-') => state = 3,
                b'/' if b.get(i + 1) == Some(&b'*') => {
                    state = 4;
                    i += 1;
                }
                _ => {}
            },
            1 => {
                if c == b'\'' {
                    state = 0
                }
            }
            2 => {
                if c == b'"' {
                    state = 0
                }
            }
            3 => {
                if c == b'\n' {
                    state = 0
                }
            }
            _ => {
                if c == b'*' && b.get(i + 1) == Some(&b'/') {
                    state = 0;
                    i += 1;
                }
            }
        }
        i += 1;
    }
    state == 0
}

pub async fn connect() -> Result<SqliteConnection, sqlx::Error> {
    SqliteConnection::connect("sqlite::memory:").await
}

pub fn render_row(row: &sqlx::sqlite::SqliteRow) -> Value {
    let mut out = Vec::new();
    for (i, col) in row.columns().iter().enumerate() {
        let raw = row.try_get_raw(i).expect("raw");
        let v = if raw.is_null() {
            json!(null)
        } else {
            match raw.type_info().name() {
                "INTEGER" => json!(row.try_get::<i64, _>(i).map_err(|e| e.to_string())),
                "REAL" => json!(row.try_get::<f64, _>(i).map(|f| format!("{f:?}")).map_err(|e| e.to_string())),
                "BLOB" => json!(row
                    .try_get::<Vec<u8>, _>(i)
                    .map(|b| b.iter().map(|x| format!("{x:02x}")).collect::<String>())
                    .map_err(|e| e.to_string())),
                other => json!([other, row.try_get::<String, _>(i).map_err(|e| e.to_string())]),
            }
        };
        out.push(json!([col.name(), v]));
    }
    Value::Array(out)
}

pub fn render_err(e: &sqlx::Error) -> Value {
    let code = e.as_database_error().and_then(|d| d.code().map(|c| c.into_owned()));
    json!({ "error": e.to_string(), "code": code })
}

/// Run `script` via the multi-statement streaming API and record every event in order.
pub async fn run_events(conn: &mut SqliteConnection, script: &str, prepared: bool) -> Vec<Value> {
    let mut events = Vec::new();
    let res = if prepared {
        collect(conn.fetch_many(sqlx::query(AssertSqlSafe(script.to_owned()))), &mut events).await
    } else {
        collect(conn.fetch_many(sqlx::raw_sql(AssertSqlSafe(script.to_owned()))), &mut events).await
    };
    if let Err(e) = res {
        events.push(render_err(&e));
    }
    events
}

async fn collect<'e, S>(mut stream: S, events: &mut Vec<Value>) -> Result<(), sqlx::Error>
where
    S: futures_util::Stream<
            Item = Result<Either<sqlx::sqlite::SqliteQueryResult, sqlx::sqlite::SqliteRow>, sqlx::Error>,
        > + Unpin,
{
    while let Some(item) = stream.try_next().await? {
        match item {
            Either::Left(r) => events.push(json!({
                "rows_affected": r.rows_affected(),
                "last_insert_rowid": r.last_insert_rowid(),
            })),
            Either::Right(row) => events.push(json!({ "row": render_row(&row) })),
        }
    }
    Ok(())
}

/// Full logical dump of the database: schema plus every table's rows in rowid order.
pub async fn dump(conn: &mut SqliteConnection) -> Value {
    async fn inner(conn: &mut SqliteConnection) -> Result<Value, sqlx::Error> {
        let schema: Vec<(String, String, Option<String>)> =
            sqlx::query_as("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
                .fetch_all(&mut *conn)
                .await?;
        let mut tables = serde_json::Map::new();
        for (ty, name, _) in &schema {
            if ty != "table" {
                continue;
            }
            let cols: Vec<(String,)> = sqlx::query_as("SELECT name FROM pragma_table_info(?1) ORDER BY cid")
                .bind(name)
                .fetch_all(&mut *conn)
                .await?;
            let expr = cols
                .iter()
                .map(|(c,)| format!("quote(\"{}\")", c.replace('"', "\"\"")))
                .collect::<Vec<_>>()
                .join(" || '|' || ");
            let sql = format!("SELECT {expr} FROM \"{}\" ORDER BY rowid", name.replace('"', "\"\""));
            let rows: Vec<(String,)> = sqlx::query_as(AssertSqlSafe(sql)).fetch_all(&mut *conn).await?;
            tables.insert(name.clone(), json!(rows.into_iter().map(|(r,)| r).collect::<Vec<_>>()));
        }
        let uv: (i64,) = sqlx::query_as("PRAGMA user_version").fetch_one(&mut *conn).await?;
        Ok(json!({ "schema": schema, "tables": tables, "user_version": uv.0 }))
    }
    match inner(conn).await {
        Ok(v) => v,
        Err(e) => json!({ "dump_error": e.to_string() }),
    }
}

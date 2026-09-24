//! Hidden benchmark: times `raw_sql(script).execute()` on generated ledger workloads.
//!
//! usage: bench --sizes 5000,20000,80000 --reps 5 --seed 11 [--same-script]
//! Each repetition uses a fresh in-memory database. Without --same-script every repetition uses
//! a different (but equivalent-shaped) script, so no cross-rep result cache can help.
//! Prints one JSON object on stdout.

use std::time::Instant;

use d_sqlx_harness::{connect, ledger_script, LEDGER_SETUP};
use serde_json::json;
use sqlx::AssertSqlSafe;

fn arg(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), sqlx::Error> {
    let args: Vec<String> = std::env::args().collect();
    let sizes: Vec<usize> = arg(&args, "--sizes")
        .unwrap_or_else(|| "5000,20000,80000".into())
        .split(',')
        .map(|s| s.parse().expect("size"))
        .collect();
    let reps: usize = arg(&args, "--reps").map(|s| s.parse().unwrap()).unwrap_or(5);
    let seed: u64 = arg(&args, "--seed").map(|s| s.parse().unwrap()).unwrap_or(11);
    let same = args.iter().any(|a| a == "--same-script");

    let mut out = serde_json::Map::new();
    for &n in &sizes {
        let mut times = Vec::new();
        let mut checks = Vec::new();
        for rep in 0..reps {
            let s = if same { seed } else { seed.wrapping_add(7919 * rep as u64) };
            let script = ledger_script(n, s ^ (n as u64) << 20);
            let mut conn = connect().await?;
            sqlx::raw_sql(LEDGER_SETUP).execute(&mut conn).await?;

            let t0 = Instant::now();
            let res = sqlx::raw_sql(AssertSqlSafe(script.as_str())).execute(&mut conn).await?;
            let dt = t0.elapsed().as_secs_f64();

            let (cnt, amt, notes): (i64, i64, i64) = sqlx::query_as(
                "SELECT count(*), coalesce(sum(amount), 0), coalesce(sum(length(note)), 0) FROM ledger",
            )
            .fetch_one(&mut conn)
            .await?;
            let (audit,): (i64,) = sqlx::query_as("SELECT count(*) FROM audit").fetch_one(&mut conn).await?;
            let (objs,): (i64,) = sqlx::query_as("SELECT count(*) FROM sqlite_master").fetch_one(&mut conn).await?;
            times.push(dt);
            checks.push(json!({
                "script_bytes": script.len(),
                "rows_affected": res.rows_affected(),
                "ledger": [cnt, amt, notes],
                "audit": audit,
                "objects": objs,
            }));
        }
        let mut sorted = times.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
        out.insert(
            n.to_string(),
            json!({ "median_s": sorted[sorted.len() / 2], "times_s": times, "checks": checks }),
        );
    }
    println!("{}", serde_json::Value::Object(out));
    Ok(())
}

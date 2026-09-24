//! Times executing one large multi-statement SQL string against an in-memory SQLite database.
//!
//! ```text
//! cargo run --release --example multi_stmt_bench --features sqlite,runtime-tokio
//! cargo run --release --example multi_stmt_bench --features sqlite,runtime-tokio -- 1000 10000 50000
//! ```
//!
//! Arguments are statement counts (default: 1000 4000 16000 32000). Each count runs against a
//! fresh database; the time covers only the `raw_sql(..).execute(..)` call.

use std::time::Instant;

use sqlx::{AssertSqlSafe, Connection, SqliteConnection};

const SCHEMA: &str = "CREATE TABLE posts (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT, views INTEGER NOT NULL DEFAULT 0);
CREATE TABLE tags (post_id INTEGER NOT NULL, tag TEXT NOT NULL);";

fn script(statements: usize) -> String {
    let mut sql = String::new();
    let mut posts = 0;
    for i in 0..statements {
        match i % 10 {
            0..=5 => {
                posts += 1;
                sql.push_str(&format!(
                    "INSERT INTO posts (title, body) VALUES ('Post #{posts}', 'Body of post {posts}. It''s a fairly ordinary body with some filler text in it.');\n"
                ));
            }
            6 | 7 => sql.push_str(&format!(
                "UPDATE posts SET views = views + {} WHERE id = {};\n",
                i % 7 + 1,
                i % posts + 1
            )),
            8 => sql.push_str(&format!(
                "INSERT INTO tags (post_id, tag) VALUES ({posts}, 'tag-{}');\n",
                i % 13
            )),
            _ => sql.push_str(&format!("-- checkpoint {i}\nDELETE FROM tags WHERE post_id = {};\n", i % posts)),
        }
    }
    sql
}

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    let counts: Vec<usize> = std::env::args()
        .skip(1)
        .map(|a| a.parse().expect("statement count"))
        .collect();
    let counts = if counts.is_empty() { vec![1000, 4000, 16000, 32000] } else { counts };

    for n in counts {
        let sql = script(n);
        let mut conn = SqliteConnection::connect("sqlite::memory:").await?;
        sqlx::raw_sql(SCHEMA).execute(&mut conn).await?;

        let start = Instant::now();
        sqlx::raw_sql(AssertSqlSafe(sql.as_str())).execute(&mut conn).await?;
        let elapsed = start.elapsed();

        let (rows,): (i64,) = sqlx::query_as("SELECT count(*) FROM posts").fetch_one(&mut conn).await?;
        println!(
            "{n:>7} statements ({:>5} KiB): {:>10.1?}  ({:.2} us/statement, {rows} posts)",
            sql.len() / 1024,
            elapsed,
            elapsed.as_secs_f64() * 1e6 / n as f64,
        );
    }
    Ok(())
}

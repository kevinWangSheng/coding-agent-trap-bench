
// ---- appended by bench grader (hidden tests from upstream fix 0d7054d) ----
#[cfg(test)]
mod bench_hidden_tests {
    use std::fs::File;
    use std::io::Write;
    use std::path::Path;

    use super::{WalkBuilder, WalkState};
    use crate::tests::TempDir;

    fn wfile<P: AsRef<Path>>(path: P, contents: &str) {
        let mut file = File::create(path).unwrap();
        file.write_all(contents.as_bytes()).unwrap();
    }

    fn tmpdir() -> TempDir {
        TempDir::new().unwrap()
    }

    #[test]
    #[should_panic]
    fn panic_in_parallel() {
        let td = tmpdir();
        wfile(td.path().join("foo.txt"), "");

        WalkBuilder::new(td.path())
            .threads(40)
            .build_parallel()
            .run(|| Box::new(|_| panic!("oops!")));
    }

    #[test]
    #[should_panic(expected = "builder panic")]
    fn panic_in_parallel_builder() {
        let td = tmpdir();
        wfile(td.path().join("foo.txt"), "");

        let mut builds = 0;
        WalkBuilder::new(td.path()).threads(2).build_parallel().run(|| {
            builds += 1;
            if builds == 3 {
                panic!("builder panic");
            }
            Box::new(|_| WalkState::Continue)
        });
    }
}

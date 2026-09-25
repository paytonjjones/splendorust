use std::{
    fs,
    path::{Path, PathBuf},
};
fn collect(path: &Path, out: &mut Vec<PathBuf>) {
    println!("cargo:rerun-if-changed={}", path.display());
    if path.is_dir() {
        for entry in fs::read_dir(path).unwrap() {
            collect(&entry.unwrap().path(), out);
        }
    } else if path
        .extension()
        .is_some_and(|x| x == "rs" || x == "toml" || x == "lock")
    {
        out.push(path.to_path_buf());
    }
}
fn main() {
    // A portable source identifier for uncommitted experiments as well as commits.
    let mut paths = Vec::new();
    for path in [
        "src",
        "build.rs",
        "Cargo.toml",
        "../splendor-core/src",
        "../splendor-core/Cargo.toml",
        "../splendor-agents/src",
        "../splendor-agents/Cargo.toml",
        "../../Cargo.toml",
        "../../Cargo.lock",
        "../../rust-toolchain.toml",
    ] {
        collect(Path::new(path), &mut paths);
    }
    paths.sort();
    let mut hash = 0xcbf29ce484222325u64;
    for path in paths {
        for b in path
            .to_string_lossy()
            .bytes()
            .chain(fs::read(&path).unwrap())
        {
            hash ^= b as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    println!("cargo:rustc-env=SPLENDOR_SOURCE_ID={hash:016x}");
}

//! Embeds the icon and, critically, an explicitly DPI-UNAWARE manifest.
//!
//! The Python oracle sees the virtualized coordinate space: 1920x1080 on a
//! 200% 3840x2160 monitor. Virtualization is what DPI-UNAWARE processes get;
//! `dpiAware=true` (system aware) is the opposite and reads physical pixels.
//! The first differential run proved this the hard way: built with
//! `dpiAware=true`, the exe measured 3840x2160, failed to recognise the
//! oracle's snapshot, and re-arranged instead of restoring. Every measured
//! behaviour in DPI-verification.md lives in the unaware space, so the
//! manifest pins `false` explicitly rather than relying on the default.

const MANIFEST: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">false</dpiAware>
    </windowsSettings>
  </application>
</assembly>
"#;

fn main() {
    println!("cargo:rerun-if-changed=align_terminals.ico");
    let mut res = winresource::WindowsResource::new();
    res.set_icon("align_terminals.ico");
    res.set_manifest(MANIFEST);
    match res.compile() {
        Ok(()) => {}
        // A dev build without a resource compiler may still be useful for
        // cargo test; a release build without the manifest must never ship.
        Err(error) if std::env::var("PROFILE").as_deref() != Ok("release") => {
            println!("cargo:warning=resource embedding failed: {error}");
        }
        Err(error) => panic!("resource embedding failed in release: {error}"),
    }
}

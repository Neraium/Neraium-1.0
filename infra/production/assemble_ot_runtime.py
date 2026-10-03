"""Assemble the candidate's native dependency closure without runtime tooling.

Runs only in the Docker builder. Keep package metadata for every copied Debian
library, including source-package findings on unaffected library components.
Neither application source nor analytical dependencies are rebuilt or rewritten.
Only CPython receives the pinned upstream security patch within Python 3.11.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path("/ot-runtime")
PYTHON = Path("/usr/local/lib/python3.11")
PATCH = Path("/patched-openssl")
SSL_ALIASES = {
    "libcrypto-6de3c5c6.so.3": "libcrypto.so.3",
    "libssl-c434c5f0.so.3": "libssl.so.3",
}


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def is_elf(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) == b"\x7fELF"


def destination(path: Path) -> Path:
    # Both the frozen Debian image and distroless use usrmerge.
    parts = path.parts
    if parts[1] in {"lib", "lib64"}:
        path = Path("/usr") / path.relative_to("/")
    return ROOT / path.relative_to("/")


def copy_library(path: Path) -> None:
    target = destination(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if not target.is_symlink():
            target.symlink_to(os.readlink(path))
        copy_library(path.resolve(strict=True))
    elif not target.exists():
        shutil.copy2(path, target)


def package_owner(path: Path) -> str:
    candidates = [str(path), str(path.resolve())]
    if str(path).startswith("/usr/lib/"):
        candidates.append(str(path).removeprefix("/usr"))
    for name in candidates:
        result = subprocess.run(["dpkg-query", "-S", name], text=True,
                                capture_output=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                owner = re.match(r"^([a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?): /", line)
                if owner:
                    return owner.group(1)
    raise RuntimeError(f"Debian library has no package owner: {path}")


def main() -> None:
    # Replace the stdlib/interpreter only, never the frozen application wheels.
    # The patched interpreter was copied separately by Docker. Its matching
    # stdlib must also be installed before native linkage is enumerated.
    for path in PYTHON.iterdir():
        if path.name == "site-packages":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    for path in Path("/patched-python-stdlib").iterdir():
        if path.name == "site-packages":
            continue
        target = PYTHON / path.name
        if path.is_dir():
            shutil.copytree(path, target, symlinks=True)
        else:
            shutil.copy2(path, target)
    ROOT.mkdir()
    local_lib = ROOT / "usr/local/lib"
    shutil.copytree("/usr/local/lib", local_lib, symlinks=True)
    # Remove installer/bootstrap and build configuration, keeping the stdlib
    # and every remaining runtime distribution byte-for-byte.
    for path in [local_lib / "pkgconfig", local_lib / "python3.11/ensurepip",
                 local_lib / "python3.11/idlelib", local_lib / "python3.11/tkinter",
                 *local_lib.glob("python3.11/config-*")]:
        if path.exists():
            shutil.rmtree(path)
    # The frozen slim image ships this GUI extension without its Tcl/Tk
    # dependencies. It cannot load there and is unrelated to server execution.
    for path in local_lib.glob("python3.11/lib-dynload/_tkinter.*"):
        path.unlink()
    for path in local_lib.rglob("__pycache__"):
        shutil.rmtree(path)
    binary_dir = ROOT / "usr/local/bin"
    binary_dir.mkdir(parents=True)
    shutil.copy2("/usr/local/bin/python3.11", binary_dir / "python3.11")
    for alias in ("python", "python3"):
        (binary_dir / alias).symlink_to("python3.11")
    # API :339 explicitly overrides image health with ECS CMD-SHELL. Keep only
    # the small POSIX shell required by that existing contract, not Bash/tools.
    system_bin = ROOT / "usr/bin"
    system_bin.mkdir(parents=True)
    shutil.copy2("/usr/bin/dash", system_bin / "dash")
    (system_bin / "sh").symlink_to("dash")
    shutil.copytree("/app", ROOT / "app", symlinks=True)
    for path in (ROOT / "app").rglob("__pycache__"):
        shutil.rmtree(path)

    libraries: set[Path] = set()
    # Audit bundled wheel libraries as well as importable extensions. Some
    # transitive libraries rely on their importing extension's wheel RPATH.
    # Supply those directories to ldd only; final runtime loading keeps RPATH.
    linkage_env = dict(os.environ, LD_LIBRARY_PATH=":".join([
        "/usr/local/lib", *map(str, PYTHON.glob("site-packages/*.libs"))]))
    for path in [p for p in ROOT.rglob("*") if is_elf(p)]:
        # Inspect the original location: ldd resolves wheel-relative RPATHs.
        original = Path("/") / path.relative_to(ROOT)
        output = subprocess.check_output(["ldd", str(original)], text=True,
                                         env=linkage_env)
        if "not found" in output:
            raise RuntimeError(f"Unresolved native dependency: {original}")
        libraries.update(Path(p) for p in re.findall(r"(/[^\s()]+)", output)
                         if not p.startswith("/usr/local/"))

    owners: dict[str, list[str]] = {}
    owners[package_owner(Path("/usr/bin/dash"))] = ["/usr/bin/dash"]
    for path in sorted(libraries):
        copy_library(path)
        owners.setdefault(package_owner(path), []).append(str(path))
    metadata_dir = ROOT / "var/lib/dpkg/status.d"
    metadata_dir.mkdir(parents=True)
    for package in owners:
        (metadata_dir / package.replace(":", "_")).write_text(
            command("dpkg-query", "-s", package))
        copyright_file = Path("/usr/share/doc") / package.split(":", 1)[0] / "copyright"
        if copyright_file.is_file():
            target = ROOT / copyright_file.relative_to("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copyright_file, target)

    # Debian's backport fixes both known HIGH OpenSSL advisories. Preserve its
    # actual version metadata, rather than changing scanner expectations.
    ssl_dir = ROOT / "usr/lib/x86_64-linux-gnu"
    for name in ("libcrypto.so.3", "libssl.so.3"):
        shutil.copy2(PATCH / "usr/lib/x86_64-linux-gnu" / name, ssl_dir / name)
    control = (PATCH / "control").read_text()
    assert "Version: 3.5.7-1~deb13u3\n" in control
    (metadata_dir / "libssl3t64_amd64").write_text(
        "Status: install ok installed\n" + control)

    # psycopg-binary also embeds OpenSSL 3.5.0. Replace those two copies with
    # aliases to the patched system ABI, keeping psycopg/libpq themselves intact.
    wheel_libs = local_lib / "python3.11/site-packages/psycopg_binary.libs"
    for old_name, new_name in SSL_ALIASES.items():
        old_path = wheel_libs / old_name
        assert old_path.is_file() and not old_path.is_symlink()
        old_path.unlink()
        old_path.symlink_to(f"/usr/lib/x86_64-linux-gnu/{new_name}")

    ssl_config = ROOT / "etc/ssl"
    ssl_config.mkdir(parents=True)
    shutil.copy2("/etc/ssl/openssl.cnf", ssl_config / "openssl.cnf")
    (ROOT / "etc/passwd").write_text(
        "root:x:0:0:root:/root:/sbin/nologin\n"
        "neraium:x:10001:10001:Neraium:/nonexistent:/sbin/nologin\n"
        "connector-executor:x:10002:10002:Connector:/nonexistent:/sbin/nologin\n"
        "nonroot:x:65532:65532:nonroot:/home/nonroot:/sbin/nologin\n")
    (ROOT / "etc/group").write_text(
        "root:x:0:\nneraium:x:10001:\nconnector-executor:x:10002:\n"
        "nonroot:x:65532:\n")
    for directory in ("app/app/runtime", "mnt/neraium-runtime", "var/log/neraium"):
        path = ROOT / directory
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 10001, 10001)

    manifest = {
        "format": "neraium.ot-runtime-assembly.v1",
        "python": command("/usr/local/bin/python", "--version").strip(),
        "debian_libraries": owners,
        "openssl_package": "libssl3t64=3.5.7-1~deb13u3",
        "openssl_aliases": SSL_ALIASES,
        "removed_distributions": ["pip", "setuptools", "wheel"],
        "retained_shell_reason": "ECS API task healthCheck CMD-SHELL compatibility",
        "files": {
            "/" + str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob("*")) if p.is_file() and not p.is_symlink()
        },
        "symlinks": {
            "/" + str(p.relative_to(ROOT)): os.readlink(p)
            for p in sorted(ROOT.rglob("*")) if p.is_symlink()
        },
    }
    (ROOT / "usr/local/share").mkdir(parents=True)
    (ROOT / "usr/local/share/neraium-ot-runtime-assembly.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()

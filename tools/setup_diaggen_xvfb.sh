#!/usr/bin/env bash
# Extract a pinned Ubuntu 24.04 Xvfb package into DiagGen's private prefix.
# No sudo, apt install, or host package changes. Existing host X11 data/libs
# remain dependencies; ldd and the separate display probe verify this machine.
# Usage: tools/setup_diaggen_xvfb.sh [--deb /path/to/already-downloaded.deb]
set -euo pipefail

TOOLS_DIR="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$TOOLS_DIR/diaggen/.local/xvfb"
PACKAGE_VERSION='2:21.1.12-1ubuntu1.9'
PACKAGE_SHA256='2011271eabcc2eb460e99995c5ef26e46633e87d04f570e305b62f178f7b452c'
DEB_PATH=''
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != '--deb' ]]; then
    echo 'Usage: setup_diaggen_xvfb.sh [--deb /path/to/package.deb]' >&2
    exit 2
  fi
  DEB_PATH="$(realpath "$2")"
fi

for command_name in apt-get dpkg-deb ldd sha256sum; do
  command -v "$command_name" >/dev/null || {
    echo "Required command missing: $command_name" >&2
    exit 1
  }
done
if [[ "$(uname -m)" != 'x86_64' ]]; then
  echo 'This pinned package supports Ubuntu amd64 hosts only.' >&2
  exit 1
fi
mkdir -p "$(dirname "$PREFIX")"
exec 9>"${PREFIX}.setup.lock"
flock 9
if [[ -e "$PREFIX" ]]; then
  echo "Private prefix already exists; leaving it unchanged: $PREFIX" >&2
  [[ -x "$PREFIX/usr/bin/Xvfb" ]] || exit 1
  [[ -f "$PREFIX/PACKAGE_VERSION" ]] || exit 1
  [[ "$(cat "$PREFIX/PACKAGE_VERSION")" == "$PACKAGE_VERSION" ]] || exit 1
  ldd_output="$(ldd "$PREFIX/usr/bin/Xvfb")"
  if [[ "$ldd_output" == *'not found'* ]]; then
    echo "$ldd_output" >&2
    exit 1
  fi
  printf '%s\n' "$PREFIX/usr/bin/Xvfb"
  exit 0
fi

staging_dir="$(mktemp -d "$(dirname "$PREFIX")/.xvfb-setup.XXXXXX")"
trap 'rm -rf -- "$staging_dir"' EXIT
if [[ -z "$DEB_PATH" ]]; then
  (
    cd "$staging_dir"
    apt-get download "xvfb=$PACKAGE_VERSION" >&2
  )
  deb_files=("$staging_dir"/xvfb_*.deb)
  [[ ${#deb_files[@]} -eq 1 && -f "${deb_files[0]}" ]] || exit 1
  DEB_PATH="${deb_files[0]}"
fi
[[ -f "$DEB_PATH" ]] || { echo "Package not found: $DEB_PATH" >&2; exit 1; }
printf '%s  %s\n' "$PACKAGE_SHA256" "$DEB_PATH" | sha256sum --check --status
[[ "$(dpkg-deb --field "$DEB_PATH" Package)" == 'xvfb' ]]
[[ "$(dpkg-deb --field "$DEB_PATH" Version)" == "$PACKAGE_VERSION" ]]
[[ "$(dpkg-deb --field "$DEB_PATH" Architecture)" == 'amd64' ]]
dpkg-deb --extract "$DEB_PATH" "$staging_dir/prefix"
ldd_output="$(ldd "$staging_dir/prefix/usr/bin/Xvfb")"
if [[ "$ldd_output" == *'not found'* ]]; then
  echo "Host libraries missing; private extraction was not installed:" >&2
  echo "$ldd_output" >&2
  exit 1
fi
[[ -d /usr/share/X11/xkb ]] || {
  echo 'Host XKB data missing: /usr/share/X11/xkb' >&2
  exit 1
}
command -v xkbcomp >/dev/null || { echo 'Host xkbcomp is missing.' >&2; exit 1; }
printf '%s\n' "$PACKAGE_VERSION" > "$staging_dir/prefix/PACKAGE_VERSION"
printf '%s\n' "$PACKAGE_SHA256" > "$staging_dir/prefix/PACKAGE_SHA256"
printf '%s\n' "$ldd_output" > "$staging_dir/prefix/host_dependencies.txt"
mv "$staging_dir/prefix" "$PREFIX"
printf '%s\n' "$PREFIX/usr/bin/Xvfb"

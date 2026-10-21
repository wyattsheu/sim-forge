#!/usr/bin/env bash
# Build the DiagGen (tools/diaggen) conda prefix environments.
# Usage: tools/setup_diaggen_envs.sh <env>...   env: hag4r hag4r_mesh hag4r_segmentation omnipart genesis
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/diaggen" && pwd)"
CONDA="${CONDA:-$HOME/miniforge3/bin/conda}"
TORCH_IDX=https://download.pytorch.org/whl/cu128
export CUDA_HOME=/usr/local/cuda-12.8
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST="12.0"
export MAX_JOBS="${MAX_JOBS:-16}"
export PYTHONNOUSERSITE=1
# flash-attn's setup.py renames its downloaded wheel into the pip cache; keep tmp on the same filesystem
export TMPDIR="$HOME/.cache/tmp"
mkdir -p "$TMPDIR"

mk() {  # mk <prefix> <python>
  [ -x "$1/bin/python" ] || "$CONDA" create -y -p "$1" "python=$2" pip
}

build_hag4r() {
  local p="$ROOT/.conda/$1"
  mk "$p" 3.12
  "$p/bin/python" -m pip install -r "$ROOT/requirements.txt"
}

build_hag4r_segmentation() {
  local p="$ROOT/.conda/hag4r_segmentation"
  mk "$p" 3.12
  "$p/bin/python" -m pip install torch==2.10.0 torchvision --index-url "$TORCH_IDX"
  "$p/bin/python" -m pip install -e "$ROOT/third_party/sam3"
  # sam3 still imports pkg_resources, removed in setuptools 81
  "$p/bin/python" -m pip install "setuptools<81" Pillow PyYAML opencv-python scipy einops pycocotools psutil
}

build_omnipart() {
  local p="$ROOT/.conda/omnipart" d="$ROOT/third_party/OmniPart"
  mk "$p" 3.10
  cd "$d"
  "$p/bin/python" -m pip install --upgrade pip wheel "setuptools<81" ninja==1.13.0 packaging==24.2
  PATH="$p/bin:$PATH" "$p/bin/python" -m pip install -r requirements.txt
  PATH="$p/bin:$PATH" "$p/bin/python" -m pip install --no-build-isolation -r requirements-github.txt
  PATH="$p/bin:$PATH" "$p/bin/python" -m pip install --no-build-isolation -r requirements-huggingface.txt
  # nvdiffrast JIT-compiles at runtime; system default nvcc (12.0) cannot target sm_120
  mkdir -p "$p/etc/conda/activate.d"
  cat > "$p/etc/conda/activate.d/cuda128.sh" <<EOF
export CUDA_HOME=$CUDA_HOME
export PATH="\$CUDA_HOME/bin:\$PATH"
export TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST
EOF
}

build_genesis() {
  local d="$ROOT/third_party/genesis-world" p="$ROOT/third_party/genesis-world/.conda/genesis_world-main"
  mk "$p" 3.12
  "$p/bin/python" -m pip install torch==2.10.0 --index-url "$TORCH_IDX"
  "$p/bin/python" -m pip install -e "$d"
}

for e in "$@"; do
  echo "=== $e ($(date)) ==="
  case "$e" in
    hag4r|hag4r_mesh) build_hag4r "$e" ;;
    hag4r_segmentation) build_hag4r_segmentation ;;
    omnipart) build_omnipart ;;
    genesis) build_genesis ;;
    *) echo "unknown env $e" >&2; exit 2 ;;
  esac
  echo "=== $e done ($(date)) ==="
done

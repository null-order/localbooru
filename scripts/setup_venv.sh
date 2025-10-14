#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a virtual environment with LocalBooru and selected extras.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
BACKEND="cpu"
PYTHON_BIN="${PYTHON:-python3}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--venv PATH] [--backend cpu|cuda|rocm|mps]

Options:
  --venv PATH        Location for the virtual environment (default: $ROOT_DIR/.venv)
  --backend BACKEND  Torch backend to install (default: cpu)
                     cpu   -> CPU wheels via https://download.pytorch.org/whl/cpu
                     cuda  -> CUDA wheels (set CUDA_VERSION, default cu121)
                     rocm  -> ROCm wheels (set ROCM_VERSION, default rocm6.1)
                     mps   -> Apple Silicon (uses default PyPI wheels)
  --help             Show this message and exit

Environment:
  PYTHON             Override interpreter used to create the venv (default: python3)
  CUDA_VERSION       CUDA wheel tag (e.g. cu118, cu121) when --backend=cuda
  ROCM_VERSION       ROCm wheel tag (e.g. rocm5.6, rocm6.1) when --backend=rocm
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --venv)
            if [[ $# -lt 2 ]]; then
                echo "error: --venv requires a path" >&2
                exit 1
            fi
            VENV_DIR="$2"
            shift 2
            ;;
        --backend)
            if [[ $# -lt 2 ]]; then
                echo "error: --backend requires a value" >&2
                exit 1
            fi
            BACKEND="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR using $PYTHON_BIN"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Reusing existing virtual environment at $VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install --upgrade wheel setuptools

install_torch_stack() {
    case "$BACKEND" in
        cpu)
            echo "Installing CPU-only torch stack..."
            pip install --upgrade \
                --extra-index-url https://download.pytorch.org/whl/cpu \
                torch torchvision torchaudio
            ;;
        cuda)
            CUDA_VERSION="${CUDA_VERSION:-cu121}"
            echo "Installing CUDA torch stack ($CUDA_VERSION)..."
            pip install --upgrade \
                --index-url "https://download.pytorch.org/whl/${CUDA_VERSION}" \
                torch torchvision torchaudio
            ;;
        rocm)
            ROCM_VERSION="${ROCM_VERSION:-rocm6.1}"
            echo "Installing ROCm torch stack ($ROCM_VERSION)..."
            pip install --upgrade \
                --index-url "https://download.pytorch.org/whl/${ROCM_VERSION}" \
                torch torchvision torchaudio
            ;;
        mps)
            echo "Installing default PyPI torch stack (Apple Silicon / MPS)..."
            pip install --upgrade torch torchvision torchaudio
            ;;
        *)
            echo "error: unsupported backend '$BACKEND'" >&2
            exit 1
            ;;
    esac
}

install_torch_stack

echo "Installing localbooru in editable mode with extras (clip, ui, watch)..."
pip install -e "$ROOT_DIR[clip,ui,watch]"

echo "Ensuring tagging support (dghs-imgutils)..."
IMGUTILS_SPEC="dghs-imgutils"
if [[ "$BACKEND" == "cuda" || "$BACKEND" == "rocm" ]]; then
    IMGUTILS_SPEC="dghs-imgutils[gpu]"
fi
pip install "$IMGUTILS_SPEC"

echo
echo "Environment ready. Activate with:"
echo "  source \"$VENV_DIR/bin/activate\""

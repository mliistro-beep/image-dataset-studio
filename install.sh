#!/usr/bin/env bash
# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
#
# Installazione automatica su Linux / Automatic Linux installer.
#
#   curl -fsSL https://raw.githubusercontent.com/mliistro-beep/image-dataset-studio/main/install.sh | bash
#
# Opzioni / options:
#   --dir PATH      cartella di installazione (default: ~/image-dataset-studio)
#   --cpu | --gpu   forza il profilo invece del rilevamento automatico
#   --no-desktop    non crea il comando nel menu applicazioni
#   --yes           non fa domande (installa i pacchetti di sistema mancanti con sudo)
#   --uninstall     rimuove l'applicazione (i modelli scaricati restano in ~/.cache)
set -euo pipefail

REPO_URL="https://github.com/mliistro-beep/image-dataset-studio.git"
APP_NAME="Image Dataset Studio"
APP_ID="image-dataset-studio"
INSTALL_DIR="$HOME/image-dataset-studio"
FORCE_MODE=""
CREATE_DESKTOP=1
ASSUME_YES=0
UNINSTALL=0

BIN_LINK="$HOME/.local/bin/$APP_ID"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"

# --- Lingua dei messaggi: italiano se il sistema è in italiano -----------------
case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    it*) IT=1 ;;
    *) IT=0 ;;
esac
msg() { if [ "$IT" = 1 ]; then printf '%s\n' "$1"; else printf '%s\n' "$2"; fi; }

info() { printf '\033[1;32m==>\033[0m %s\n' "$(msg "$1" "$2")"; }
warn() { printf '\033[1;33m⚠ \033[0m %s\n' "$(msg "$1" "$2")"; }
die()  { printf '\033[1;31m✖ \033[0m %s\n' "$(msg "$1" "$2")" >&2; exit 1; }

# Le domande leggono da /dev/tty: funziona anche con "curl ... | bash"
ask_yes() {
    [ "$ASSUME_YES" = 1 ] && return 0
    local answer
    printf '%s [s/N] ' "$(msg "$1" "$2")"
    read -r answer </dev/tty || return 1
    case "$answer" in [sSyY]*) return 0 ;; *) return 1 ;; esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --cpu) FORCE_MODE="cpu"; shift ;;
        --gpu) FORCE_MODE="gpu"; shift ;;
        --no-desktop) CREATE_DESKTOP=0; shift ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help) sed -n '5,16p' "$0" 2>/dev/null || true; exit 0 ;;
        *) die "Opzione sconosciuta: $1" "Unknown option: $1" ;;
    esac
done
INSTALL_DIR="$(realpath -m "$INSTALL_DIR")"

[ "$(uname -s)" = "Linux" ] || die "Questo script funziona solo su Linux." "This script only works on Linux."
[ "$(id -u)" != 0 ] || die "Non eseguire lo script come root: installa nella tua home." "Do not run as root: the app installs in your home folder."

# --- Disinstallazione ------------------------------------------------------------
if [ "$UNINSTALL" = 1 ]; then
    [ -f "$INSTALL_DIR/run.py" ] || die "Nessuna installazione trovata in $INSTALL_DIR" "No installation found in $INSTALL_DIR"
    ask_yes "Rimuovere $INSTALL_DIR, il comando e la voce nel menu?" "Remove $INSTALL_DIR, the command and the menu entry?" || exit 0
    rm -rf "$INSTALL_DIR"
    rm -f "$BIN_LINK" "$DESKTOP_FILE"
    info "Disinstallato. I modelli scaricati restano in ~/.cache/huggingface e ~/.cache/wd14_tagger." \
         "Uninstalled. Downloaded models remain in ~/.cache/huggingface and ~/.cache/wd14_tagger."
    exit 0
fi

# --- Pacchetti di sistema --------------------------------------------------------
detect_pkg_manager() {
    if command -v apt-get >/dev/null; then echo apt
    elif command -v dnf >/dev/null; then echo dnf
    elif command -v pacman >/dev/null; then echo pacman
    elif command -v zypper >/dev/null; then echo zypper
    else echo unknown; fi
}

PKG_MANAGER="$(detect_pkg_manager)"
case "$PKG_MANAGER" in
    # git, Python con venv, e le librerie di sistema richieste da Qt 6 (xcb-cursor, OpenGL, xkbcommon)
    apt)    SYS_PKGS="git python3 python3-venv python3-pip libxcb-cursor0 libgl1 libegl1 libxkbcommon-x11-0"
            INSTALL_CMD="sudo apt-get update && sudo apt-get install -y $SYS_PKGS" ;;
    dnf)    SYS_PKGS="git python3 python3-pip xcb-util-cursor mesa-libGL mesa-libEGL libxkbcommon-x11"
            INSTALL_CMD="sudo dnf install -y $SYS_PKGS" ;;
    pacman) SYS_PKGS="git python python-pip xcb-util-cursor mesa libxkbcommon-x11"
            INSTALL_CMD="sudo pacman -S --needed --noconfirm $SYS_PKGS" ;;
    zypper) SYS_PKGS="git python3 python3-pip libxcb-cursor0 Mesa-libGL1 libxkbcommon-x11-0"
            INSTALL_CMD="sudo zypper install -y $SYS_PKGS" ;;
    *)      SYS_PKGS=""; INSTALL_CMD="" ;;
esac

missing_requirements() {
    command -v git >/dev/null || return 0
    command -v python3 >/dev/null || return 0
    python3 -c 'import venv, ensurepip' 2>/dev/null || return 0
    if [ "$PKG_MANAGER" = apt ]; then
        dpkg -s libxcb-cursor0 >/dev/null 2>&1 || return 0
    fi
    return 1
}

if missing_requirements; then
    if [ -z "$INSTALL_CMD" ]; then
        die "Mancano git o Python 3 con venv. Installali con il gestore pacchetti della tua distribuzione e riprova." \
            "git or Python 3 with venv is missing. Install them with your distribution's package manager and retry."
    fi
    msg "Servono alcuni pacchetti di sistema. Comando:" "Some system packages are required. Command:"
    echo "  $INSTALL_CMD"
    ask_yes "Eseguirlo adesso (richiede la password sudo)?" "Run it now (requires the sudo password)?" \
        || die "Installa i pacchetti e rilancia lo script." "Install the packages and run the script again."
    bash -c "$INSTALL_CMD" </dev/tty
fi

python3 - <<'EOF' || die "Serve Python 3.10 o superiore." "Python 3.10 or newer is required."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

# --- Rilevamento GPU -------------------------------------------------------------
# Sceglie l'indice PyTorch in base alla versione CUDA supportata dal driver e alla GPU.
# Le RTX serie 50 (compute capability 12.x) richiedono almeno cu128.
TORCH_INDEX=""
detect_gpu() {
    command -v nvidia-smi >/dev/null || return 1
    local smi cuda cap major minor capmajor
    smi="$(nvidia-smi 2>/dev/null)" || return 1
    cuda="$(printf '%s' "$smi" | grep -oE 'CUDA Version: *[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    [ -n "$cuda" ] || return 1
    major="${cuda%%.*}"; minor="${cuda##*.}"
    cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')"
    capmajor="${cap%%.*}"
    GPU_NAME="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)"
    GPU_CUDA="$cuda"

    if [ "$major" -ge 13 ]; then TORCH_INDEX="cu130"
    elif [ "${capmajor:-0}" -ge 12 ]; then
        if [ "$major" -eq 12 ] && [ "$minor" -ge 8 ]; then TORCH_INDEX="cu128"; else return 2; fi
    elif [ "$major" -eq 12 ] && [ "$minor" -ge 6 ]; then TORCH_INDEX="cu126"
    elif [ "$major" -eq 12 ] && [ "$minor" -ge 4 ]; then TORCH_INDEX="cu124"
    else return 2; fi
    return 0
}

MODE="cpu"
GPU_NAME=""; GPU_CUDA=""
set +e; detect_gpu; GPU_STATUS=$?; set -e
if [ "$GPU_STATUS" = 0 ]; then
    info "GPU NVIDIA rilevata: $GPU_NAME (driver CUDA $GPU_CUDA) → PyTorch $TORCH_INDEX" \
         "NVIDIA GPU detected: $GPU_NAME (driver CUDA $GPU_CUDA) → PyTorch $TORCH_INDEX"
    MODE="gpu"
elif [ "$GPU_STATUS" = 2 ]; then
    warn "GPU NVIDIA trovata ($GPU_NAME) ma il driver (CUDA $GPU_CUDA) è troppo vecchio: aggiornalo per usare la GPU. Installo la versione CPU." \
         "NVIDIA GPU found ($GPU_NAME) but the driver (CUDA $GPU_CUDA) is too old: update it to use the GPU. Installing the CPU version."
else
    info "Nessuna GPU NVIDIA utilizzabile: installo la versione CPU." "No usable NVIDIA GPU: installing the CPU version."
fi

if [ "$FORCE_MODE" = gpu ] && [ "$MODE" != gpu ]; then
    die "--gpu richiesto ma nessuna GPU NVIDIA con driver adeguato è stata rilevata." \
        "--gpu requested but no NVIDIA GPU with a suitable driver was detected."
fi
[ "$FORCE_MODE" = cpu ] && MODE="cpu"

# --- Download / aggiornamento del repository ------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Aggiornamento di $INSTALL_DIR..." "Updating $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull --ff-only
elif [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "$INSTALL_DIR esiste già e non è un'installazione di $APP_NAME. Usa --dir per scegliere un'altra cartella." \
        "$INSTALL_DIR already exists and is not an $APP_NAME installation. Use --dir to choose another folder."
else
    info "Download del codice in $INSTALL_DIR..." "Downloading the code into $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# --- Ambiente virtuale e dipendenze ---------------------------------------------
# Se cambia profilo (CPU <-> GPU) l'ambiente viene ricreato da zero per evitare conflitti fra versioni di torch/onnxruntime
WANTED="$MODE${TORCH_INDEX:+-$TORCH_INDEX}"
if [ -f venv/.install_mode ] && [ "$(cat venv/.install_mode)" != "$WANTED" ]; then
    info "Profilo cambiato ($(cat venv/.install_mode) → $WANTED): ricreo l'ambiente virtuale." \
         "Profile changed ($(cat venv/.install_mode) → $WANTED): recreating the virtual environment."
    rm -rf venv
fi
if [ ! -x venv/bin/python ]; then
    info "Creazione ambiente virtuale Python..." "Creating Python virtual environment..."
    python3 -m venv venv
fi
PIP="venv/bin/python -m pip"
$PIP install --upgrade pip --quiet

if [ "$MODE" = gpu ]; then
    info "Installazione dipendenze GPU (PyTorch CUDA, diversi GB: può richiedere parecchi minuti)..." \
         "Installing GPU dependencies (PyTorch CUDA, several GB: this may take a while)..."
    $PIP install -r requirements-base.txt
    $PIP install torch --index-url "https://download.pytorch.org/whl/$TORCH_INDEX"
    $PIP install "onnxruntime-gpu>=1.17" "bitsandbytes>=0.45"
else
    info "Installazione dipendenze CPU..." "Installing CPU dependencies..."
    $PIP install -r requirements.txt
fi
echo "$WANTED" > venv/.install_mode

# --- Verifica ----------------------------------------------------------------------
info "Verifica dell'installazione..." "Verifying the installation..."
venv/bin/python - <<'EOF'
import onnxruntime, PySide6, torch, transformers
print(f"   PySide6 {PySide6.__version__} · onnxruntime {onnxruntime.__version__} · "
      f"torch {torch.__version__} · transformers {transformers.__version__} · CUDA: {torch.cuda.is_available()}")
EOF

# --- Comando di avvio e voce nel menu -----------------------------------------
mkdir -p "$(dirname "$BIN_LINK")"
cat > "$BIN_LINK" <<EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR" && exec "$INSTALL_DIR/venv/bin/python" run.py "\$@"
EOF
chmod +x "$BIN_LINK"

if [ "$CREATE_DESKTOP" = 1 ]; then
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=WD14 tagging, VLM captioning and prompt extraction for LoRA datasets
Comment[it]=Tagging WD14, captioning VLM ed estrazione prompt per dataset LoRA
Exec=$BIN_LINK
Icon=applications-graphics
Terminal=false
Categories=Graphics;Utility;
EOF
    command -v update-desktop-database >/dev/null && update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
fi

echo
info "Installazione completata ($MODE)." "Installation completed ($MODE)."
if [ "$CREATE_DESKTOP" = 1 ]; then
    msg "Avvio:           $APP_ID   (oppure dal menu applicazioni)" "Start:           $APP_ID   (or from the applications menu)"
else
    msg "Avvio:           $APP_ID" "Start:           $APP_ID"
fi
msg "Aggiornamento:   rilancia questo script" "Update:          run this script again"
msg "Disinstallazione: bash $INSTALL_DIR/install.sh --dir $INSTALL_DIR --uninstall" "Uninstall:       bash $INSTALL_DIR/install.sh --dir $INSTALL_DIR --uninstall"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "~/.local/bin non è nel PATH: avvia con $BIN_LINK" "~/.local/bin is not in PATH: start with $BIN_LINK" ;;
esac
msg "I modelli vengono scaricati al primo utilizzo." "Models are downloaded on first use."

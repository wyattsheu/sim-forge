#!/bin/bash
# Locate Isaac Sim. `source` this from open_in_ui.sh / open_in_webrtc.sh / make_videos.sh / run_demo.sh.
# Servers differ: binary install (/isaac-sim, ~/isaac-sim ... also inside Docker) or pip install (isaacsim in a venv).
#
# Override auto-detection:
#   ISAAC_SIM_PATH=<binary install dir containing kit/kit and python.sh>
#   ISAAC_SIM_PIP_ENV=<pip venv / conda env dir containing bin/isaacsim>
#
# On success sets:
#   ISAAC_KIND    binary | pip
#   ISAAC_ROOT    dir that contains exts/ (ROS 2 bridge libraries live below it)
#   ISAAC_PYTHON  interpreter for standalone scripts (binary: python.sh; pip: the venv's python)
#   isaac_kit_cmd <ui|stream>  fills the KIT_CMD array with the launch command
# On failure prints a hint and returns 1.

_isaac_try_binary() {      # $1 = directory
  [ -n "$1" ] && [ -x "$1/kit/kit" ] && [ -x "$1/python.sh" ] || return 1
  ISAAC_KIND=binary; ISAAC_ROOT="$1"; ISAAC_PYTHON="$1/python.sh"; ISAAC_HOME="$1"
}

_isaac_try_pip() {         # $1 = venv / conda env directory
  [ -n "$1" ] && [ -x "$1/bin/isaacsim" ] && [ -x "$1/bin/python" ] || return 1
  local root
  root=$("$1/bin/python" -I -c 'import importlib.util,os;s=importlib.util.find_spec("isaacsim");print(os.path.dirname(s.origin) if s and s.origin else os.path.dirname(list(s.submodule_search_locations)[0]))' 2>/dev/null) || return 1
  [ -n "$root" ] || return 1
  ISAAC_KIND=pip; ISAAC_ROOT="$root"; ISAAC_PYTHON="$1/bin/python"; ISAAC_HOME="$1"
}

find_isaac() {
  ISAAC_KIND=; ISAAC_ROOT=; ISAAC_PYTHON=; ISAAC_HOME=
  local d
  # 1. Explicit override
  if [ -n "${ISAAC_SIM_PATH:-}" ]; then
    _isaac_try_binary "$ISAAC_SIM_PATH" && return 0
    echo "ISAAC_SIM_PATH=$ISAAC_SIM_PATH: kit/kit or python.sh not found there" >&2; return 1
  fi
  if [ -n "${ISAAC_SIM_PIP_ENV:-}" ]; then
    _isaac_try_pip "$ISAAC_SIM_PIP_ENV" && return 0
    echo "ISAAC_SIM_PIP_ENV=$ISAAC_SIM_PIP_ENV: bin/isaacsim not found (is the isaacsim pip package installed?)" >&2; return 1
  fi
  # 2. Binary install (also inside Docker)
  for d in /isaac-sim "$HOME/isaac-sim" "$HOME/isaacsim" /opt/isaac-sim "$HOME"/.local/share/ov/pkg/isaac-sim-* "$HOME"/isaac-sim-*; do
    _isaac_try_binary "$d" && return 0
  done
  # 3. pip install: active env, isaacsim on PATH, common locations
  for d in "${VIRTUAL_ENV:-}" "${CONDA_PREFIX:-}" \
           "$(command -v isaacsim >/dev/null 2>&1 && dirname "$(dirname "$(readlink -f "$(command -v isaacsim)")")")" \
           "$HOME"/env_isaac* "$HOME"/isaac*env* "$HOME"/venv*/ "$HOME"/.venv "$HOME"/isaacsim-venv; do
    _isaac_try_pip "$d" && return 0
  done
  cat >&2 <<MSG
Isaac Sim not found. Point to it with one of:
  ISAAC_SIM_PATH=<binary install dir containing kit/kit and python.sh>   $0 ...
  ISAAC_SIM_PIP_ENV=<pip venv dir containing bin/isaacsim>   $0 ...
or install it: pip install isaacsim[all,extscache]==5.1.0 --extra-index-url https://pypi.nvidia.com
        or use Docker: nvcr.io/nvidia/isaac-sim:5.1.0
MSG
  return 1
}

# isaac_kit_cmd <ui|stream> -> fills the KIT_CMD array (append --exec, --/settings ... after it)
isaac_kit_cmd() {
  case "$ISAAC_KIND:$1" in
    binary:ui)     KIT_CMD=("$ISAAC_HOME/isaac-sim.sh") ;;
    binary:stream) KIT_CMD=("$ISAAC_HOME/kit/kit" "$ISAAC_HOME/apps/isaacsim.exp.full.streaming.kit") ;;
    pip:ui)        KIT_CMD=("$ISAAC_HOME/bin/isaacsim" isaacsim.exp.full) ;;
    pip:stream)    KIT_CMD=("$ISAAC_HOME/bin/isaacsim" isaacsim.exp.full.streaming) ;;
    *) echo "isaac_kit_cmd: unknown mode $ISAAC_KIND:$1" >&2; return 1 ;;
  esac
}

# Make Kit use the ROS 2 (jazzy) bundled with Isaac Sim instead of the system /opt/ros (different python, they interfere).
# If the install has no bundled ROS 2 libraries, CLICK_TO_ROS is switched off automatically.
isaac_setup_ros() {
  export ROS_DISTRO=${ROS_DISTRO:-jazzy}
  export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
  export ISAAC_ROOT
  local ext="$ISAAC_ROOT/exts/isaacsim.ros2.bridge/$ROS_DISTRO"
  # pip installs (6.x) keep the ROS 2 libraries in isaacsim.ros2.core/<distro>/lib
  [ -d "$ext/lib" ] || { [ -d "$ISAAC_ROOT/exts/isaacsim.ros2.core/$ROS_DISTRO/lib" ] && ext="$ISAAC_ROOT/exts/isaacsim.ros2.core/$ROS_DISTRO"; }
  PYTHONPATH=$(echo "${PYTHONPATH:-}" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -); export PYTHONPATH
  LD_LIBRARY_PATH=$(echo "${LD_LIBRARY_PATH:-}" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -); export LD_LIBRARY_PATH
  unset AMENT_PREFIX_PATH
  if [ -d "$ext/lib" ]; then
    export LD_LIBRARY_PATH="$ext/lib:$LD_LIBRARY_PATH"
    export CLICK_TO_ROS=${CLICK_TO_ROS:-1}
  else
    [ "${CLICK_TO_ROS:-1}" = 1 ] && echo "Note: this Isaac Sim has no bundled ROS 2 libraries ($ext); Ctrl+click -> ROS 2 is disabled" >&2
    export CLICK_TO_ROS=0
  fi
}

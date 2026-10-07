#!/bin/bash
# 找 Isaac Sim —— 給 open_in_ui.sh / open_in_webrtc.sh / make_videos.sh / run_demo.sh 用 `source` 載入。
# 不同伺服器可能是:二進位版(/isaac-sim、~/isaac-sim ...)、Docker 內的 /isaac-sim、或 pip 版(venv 裡的 isaacsim)。
#
# 指定位置(優先於自動偵測):
#   ISAAC_SIM_PATH=<二進位版目錄,內含 kit/kit 與 python.sh>
#   ISAAC_SIM_PIP_ENV=<pip 版的 venv / conda 環境目錄,內含 bin/isaacsim>
#
# 成功時設定:
#   ISAAC_KIND     binary | pip
#   ISAAC_ROOT     含 exts/ 的目錄(ROS 2 bridge 的函式庫在這下面)
#   ISAAC_PYTHON   跑獨立腳本用的直譯器(binary: python.sh;pip: venv 的 python)
#   isaac_kit_cmd <ui|stream>   把啟動指令填進陣列 KIT_CMD
# 失敗時印說明並 return 1。

_isaac_try_binary() {      # $1 = 目錄
  [ -n "$1" ] && [ -x "$1/kit/kit" ] && [ -x "$1/python.sh" ] || return 1
  ISAAC_KIND=binary; ISAAC_ROOT="$1"; ISAAC_PYTHON="$1/python.sh"; ISAAC_HOME="$1"
}

_isaac_try_pip() {         # $1 = venv / conda 目錄
  [ -n "$1" ] && [ -x "$1/bin/isaacsim" ] && [ -x "$1/bin/python" ] || return 1
  local root
  root=$("$1/bin/python" -I -c 'import importlib.util,os;s=importlib.util.find_spec("isaacsim");print(os.path.dirname(s.origin) if s and s.origin else os.path.dirname(list(s.submodule_search_locations)[0]))' 2>/dev/null) || return 1
  [ -n "$root" ] || return 1
  ISAAC_KIND=pip; ISAAC_ROOT="$root"; ISAAC_PYTHON="$1/bin/python"; ISAAC_HOME="$1"
}

find_isaac() {
  ISAAC_KIND=; ISAAC_ROOT=; ISAAC_PYTHON=; ISAAC_HOME=
  local d
  # 1. 使用者明確指定
  if [ -n "${ISAAC_SIM_PATH:-}" ]; then
    _isaac_try_binary "$ISAAC_SIM_PATH" && return 0
    echo "ISAAC_SIM_PATH=$ISAAC_SIM_PATH 裡找不到 kit/kit 或 python.sh" >&2; return 1
  fi
  if [ -n "${ISAAC_SIM_PIP_ENV:-}" ]; then
    _isaac_try_pip "$ISAAC_SIM_PIP_ENV" && return 0
    echo "ISAAC_SIM_PIP_ENV=$ISAAC_SIM_PIP_ENV 裡找不到 bin/isaacsim(沒裝 isaacsim pip 套件?)" >&2; return 1
  fi
  # 2. 二進位版(含 Docker 內)
  for d in /isaac-sim "$HOME/isaac-sim" "$HOME/isaacsim" /opt/isaac-sim "$HOME"/.local/share/ov/pkg/isaac-sim-* "$HOME"/isaac-sim-*; do
    _isaac_try_binary "$d" && return 0
  done
  # 3. pip 版:目前啟用的環境、PATH 上的 isaacsim、常見位置
  for d in "${VIRTUAL_ENV:-}" "${CONDA_PREFIX:-}" \
           "$(command -v isaacsim >/dev/null 2>&1 && dirname "$(dirname "$(readlink -f "$(command -v isaacsim)")")")" \
           "$HOME"/env_isaac* "$HOME"/isaac*env* "$HOME"/venv*/ "$HOME"/.venv "$HOME"/isaacsim-venv; do
    _isaac_try_pip "$d" && return 0
  done
  cat >&2 <<MSG
找不到 Isaac Sim。請指定其中一個:
  ISAAC_SIM_PATH=<二進位版目錄(內含 kit/kit、python.sh)>   $0 ...
  ISAAC_SIM_PIP_ENV=<pip 版 venv 目錄(內含 bin/isaacsim)>   $0 ...
或安裝:pip install isaacsim[all,extscache]==5.1.0 --extra-index-url https://pypi.nvidia.com
        或用 Docker:nvcr.io/nvidia/isaac-sim:5.1.0
MSG
  return 1
}

# isaac_kit_cmd <ui|stream> → 填 KIT_CMD 陣列(後面再接 --exec、--/設定 等參數)
isaac_kit_cmd() {
  case "$ISAAC_KIND:$1" in
    binary:ui)     KIT_CMD=("$ISAAC_HOME/isaac-sim.sh") ;;
    binary:stream) KIT_CMD=("$ISAAC_HOME/kit/kit" "$ISAAC_HOME/apps/isaacsim.exp.full.streaming.kit") ;;
    pip:ui)        KIT_CMD=("$ISAAC_HOME/bin/isaacsim" isaacsim.exp.full) ;;
    pip:stream)    KIT_CMD=("$ISAAC_HOME/bin/isaacsim" isaacsim.exp.full.streaming) ;;
    *) echo "isaac_kit_cmd: 未知模式 $ISAAC_KIND:$1" >&2; return 1 ;;
  esac
}

# 讓 Kit 用 Isaac 內建的 ROS 2(jazzy)而不是系統的 /opt/ros(python 版本不同會互相干擾)。
# 內建的 ROS 2 函式庫不在這個安裝裡(例如 pip 版沒附)時,CLICK_TO_ROS 會自動關掉。
isaac_setup_ros() {
  export ROS_DISTRO=${ROS_DISTRO:-jazzy}
  export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
  export ISAAC_ROOT
  local ext="$ISAAC_ROOT/exts/isaacsim.ros2.bridge/$ROS_DISTRO"
  # pip 版(6.x)把 ROS 2 函式庫放在 isaacsim.ros2.core/<distro>/lib
  [ -d "$ext/lib" ] || { [ -d "$ISAAC_ROOT/exts/isaacsim.ros2.core/$ROS_DISTRO/lib" ] && ext="$ISAAC_ROOT/exts/isaacsim.ros2.core/$ROS_DISTRO"; }
  PYTHONPATH=$(echo "${PYTHONPATH:-}" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -); export PYTHONPATH
  LD_LIBRARY_PATH=$(echo "${LD_LIBRARY_PATH:-}" | tr ':' '\n' | grep -v '^/opt/ros' | paste -sd: -); export LD_LIBRARY_PATH
  unset AMENT_PREFIX_PATH
  if [ -d "$ext/lib" ]; then
    export LD_LIBRARY_PATH="$ext/lib:$LD_LIBRARY_PATH"
    export CLICK_TO_ROS=${CLICK_TO_ROS:-1}
  else
    [ "${CLICK_TO_ROS:-1}" = 1 ] && echo "注意:這個 Isaac Sim 沒有內建 ROS 2 函式庫($ext),Ctrl+點擊 → ROS 2 已關閉" >&2
    export CLICK_TO_ROS=0
  fi
}

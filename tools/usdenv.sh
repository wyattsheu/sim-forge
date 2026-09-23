# source 之後可用 $PY 執行需要 pxr / PhysxSchema 的腳本,不必啟動 Isaac runtime。
#   source tools/usdenv.sh && $PY script.py
U=/isaac-sim/extscache/omni.usd.libs-1.0.1+69cbf6ad.lx64.r.cp311
P=/isaac-sim/extscache/omni.usd.schema.physx-107.3.26+107.3.3.lx64.r.cp311.u353
export PYTHONPATH="$U:$P:/isaac-sim/kit/python/lib/python3.11/site-packages"
export LD_LIBRARY_PATH="$U/bin:$P/bin:$LD_LIBRARY_PATH"
export PXR_PLUGINPATH_NAME="$P/plugins/PhysxSchema/resources:$P/plugins/PhysxSchemaAddition/resources:$P/plugins/OmniUsdPhysicsDeformableSchema/resources:$PXR_PLUGINPATH_NAME"
PY=/isaac-sim/kit/python/bin/python3

---
id: L0004
title: 在 Kit 裡用 ROS 2 要用 Isaac 內建的 rclpy,並把系統 /opt/ros 從環境變數拿掉
status: active
severity: medium
confidence: measured
domains: [env]
tags: [ROS 2, rclpy, jazzy, PYTHONPATH, LD_LIBRARY_PATH, python 3.11, python 3.12]
triggers: [在 Isaac Sim 裡發佈或訂閱 ROS 2 topic, 寫啟動腳本並且有 source /opt/ros]
versions: Isaac Sim 5.1.0(binary)/ 6.0(pip 版路徑不同)
scope: [sims/fr3_bubblewrap_pack_handoff_20261007]
evidence: [sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md 2026-10-07 下午, sims/fr3_bubblewrap_pack_handoff_20261007/README.md §9, sims/fr3_bubblewrap_pack_handoff_20261007/open_in_ui.sh]
related: []
observed: 2026-10-07
---

## 人話

**問題**:系統裝的 ROS 2 和 Isaac Sim 內建的 ROS 2 是給不同版本 Python 編的,兩個混在一起,Isaac 裡的 ROS 就載不起來。

**做法**:啟動 Isaac 時只讓它看到自己內建的 ROS 2,把系統的 ROS 路徑從環境變數裡拿掉;訊息照樣傳得到系統那邊的 ROS 2。

## 現象

shell 有 `source /opt/ros/jazzy/setup.bash` 時啟動 Kit,`import rclpy` 在 Kit 內失敗。

## 根因

系統 `/opt/ros/jazzy` 是 python 3.12;Isaac 內建的 jazzy rclpy 是給 Kit 的 python 3.11 編的。PYTHONPATH / LD_LIBRARY_PATH 混到兩邊就載入失敗。

## 做法

在啟動腳本裡,**只對 Kit 程序**:
1. 從 `PYTHONPATH`、`LD_LIBRARY_PATH` 移除含 `/opt/ros` 的項目;
2. 加入 Isaac 內建 jazzy 的 lib 路徑(binary 版在 Isaac 安裝目錄;pip 6.x 在 `isaacsim.ros2.core/<distro>/lib`);
3. `ROS_DOMAIN_ID` 沿用 shell 的。

ROS 2 訊息仍會出現在系統端:外面 `source /opt/ros/jazzy/setup.bash && ros2 topic echo /clicked_point` 收得到。

## 驗證方法

Kit 內 `request_query` 取一點並發佈,系統端 `ros2 topic echo` 收到同一個值(handoff README §9 的驗證方式)。

## 證據

`sims/fr3_bubblewrap_pack_handoff_20261007/CHANGELOG.md`:「the system /opt/ros (python 3.12) is removed from PYTHONPATH / LD_LIBRARY_PATH because mixing them made rclpy fail inside Kit」;README §9 驗證紀錄。

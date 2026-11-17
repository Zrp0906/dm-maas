# DM0.5 在 Mirror（DOS W1）上的部署与执行

本流程使用 Dexmal MaaS 托管的标准模型 `dm05`。Mirror 工控机运行 DexOS Lite，将相机图像和机器人状态发给云端推理，再把返回的动作下发给双臂。基座模型可直接调用，无需在工控机下载权重或在控制台创建部署任务。实机已验证双臂能够回零并执行抓取。 [MaaS 平台](https://maas.dexmal.com/) · [DOS W1 产品页](https://dev.dexmal.com/product/dos-w1)

已完成安装和相机配置的工位，可以直接看[第 8 节日常使用](#8-日常使用)。

## 1. 创建 API Key 并确认模型权限

登录 MaaS 控制台，进入「API Key」页面创建密钥。以下命令在 Mirror 工控机的 Bash 终端执行。粘贴密钥时终端不会回显。密钥只保留在当前会话的环境变量里。 [API Key 控制台](https://maas.dexmal.com/console/api-keys)

```bash
printf 'MaaS API Key: '
read -rs DEXOS_API_KEY
printf '\n'
export DEXOS_API_KEY

curl -sS https://maas.dexmal.com/api/v1/model \
  -H "X-API-Key: $DEXOS_API_KEY"
```

确认返回 `code` 为 `2000`，且 `data` 中 `id` 为 `dm05` 的条目状态为 `success`，`capabilities.robot_id` 包含 `mirror`。若返回 `4004`，检查当前会话的密钥是否正确且仍有效。后续在同一个终端运行推理。重新登录 SSH 后，需要在新会话里重新读取密钥。 [MaaS 推理 API](https://maas.dexmal.com/INFERENCE_API.md)

## 2. 检查 AIRBOT 环境并安装 DexOS Lite

### 创建或激活 `airbot` 环境

在工控机上运行 `conda env list`。如果已有 `airbot`，运行 `conda activate airbot` 即可。列表里没有 `airbot` 时，用 Python 3.10 新建环境。本次实测使用 Python `3.10.19`。如果工控机还没有 Conda，先按 Linux 安装说明安装，再打开新的 Bash 会话。 [Conda 环境管理](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html) · [Conda Linux 安装说明](https://docs.conda.io/projects/conda/en/stable/user-guide/install/linux.html)

```bash
conda create -n airbot python=3.10 pip
conda activate airbot
```

### 安装并验证 AIRBOT Python SDK

在激活的 `(airbot)` 环境里检查 Python 和 SDK。导入成功时会显示 `AIRBOT SDK OK`。

```bash
python --version
python -c 'from airbot_py.arm import AIRBOTArm, RobotMode, SpeedProfile; print("AIRBOT SDK OK")'
```

新环境或导入失败时，用 `python -m pip` 安装随 Mirror 交付的 `airbot_py` wheel，再重跑导入检查。若工控机有 `~/dos_w1` 交付目录，可在里面查找 `airbot_py-*.whl`。找不到时，向设备交付方获取与当前驱动和固件匹配的 SDK。下面以 AIRBOT 文档中的 `5.1.6` 为例，请替换成实际包的完整路径。当前流程依赖 `airbot_py.arm` 接口，AIRBOT V5.2 的 `arm_sdk` 使用了不同的接口。 [AIRBOT Python SDK 安装说明](https://docs.discover-robotics.com/document/airbot-play/quick-start/software-setup.html) · [AIRBOT 下载中心和版本变更](https://docs.discover-robotics.com/document/airbot-play/changelog.html)

```bash
find "$HOME/dos_w1" -type f -name 'airbot_py-*.whl'
python -m pip install "/实际目录/airbot_py-5.1.6-py3-none-any.whl"
```

### 检查系统驱动并安装 DexOS Lite

`airbot_server` 由工控机系统端的 AIRBOT 驱动提供。本机返回 `/usr/local/bin/airbot_server`。如果下方检查没有输出，按设备交付说明安装匹配的驱动，并检查 CAN 绑定，再进行第 4 节的双臂服务启动。 [AIRBOT 驱动安装说明](https://docs.discover-robotics.com/document/airbot-play/quick-start/software-setup.html)

```bash
command -v airbot_server
ip -br link show type can
```

继续在 `(airbot)` 环境中安装 DexOS Lite 并查看推理命令帮助。 [DexOS Lite 安装说明](https://pypi.org/project/dexos-lite/)

```bash
python -m pip install dexos-lite
dexos-lite robot infer --help
```

## 3. 生成 Mirror 配置并确认相机

在工控机上生成 `/home/ubuntu/mirror_config.py`。如果该路径已有配置，直接检查和编辑现有文件。 [DexOS Lite 配置文档](https://maas.dexmal.com/DexOS.md)

```bash
dexos-lite robot config --robot-id mirror --path ~/mirror_config.py

python - <<'PY'
import pyrealsense2 as rs

ctx = rs.context()
for camera in ctx.query_devices():
    print(camera.get_info(rs.camera_info.name),
          camera.get_info(rs.camera_info.serial_number))
PY
```

按实拍画面确认相机位置，左右以机器人自身方向为准。更换相机后重新核对对应关系。以下文件链接是供模拟模式使用的合成示例，实机配置应填写工控机枚举出的序列号。 [MaaS 相机字段](https://maas.dexmal.com/INFERENCE_API.md)

| 实机位置 | 配置字段 | 模拟画面 |
| --- | --- | --- |
| 主视角 | `cam_high` | [主视角示例](mirror-cameras/demo-high.jpg) |
| 左腕 | `cam_left_wrist` | [左腕示例](mirror-cameras/demo-left-wrist.jpg) |
| 右腕 | `cam_right_wrist` | [右腕示例](mirror-cameras/demo-right-wrist.jpg) |

**RealSense Viewer** 是相机厂商提供的桌面应用，可以查看 D435i 的彩色画面、深度画面和序列号。Viewer 和拍照脚本使用的 `pyrealsense2` 分开安装。在工控机终端运行以下命令，检查当前环境能否找到 Viewer。 [RealSense Viewer 手册](https://github.com/realsenseai/librealsense/wiki/Realsense-Viewer-Manual)

```bash
command -v realsense-viewer
```

如果返回路径，在工控机的 **Ubuntu 图形桌面**里运行 `realsense-viewer`，在 **Info** 中查看序列号，逐台开启 **RGB Camera** 确认画面。预览完成后关闭 Viewer，再启动推理以释放相机。如果检查命令没有输出，Ubuntu 上提供 Viewer 的工具包叫 `librealsense2-utils`。 [Ubuntu 安装说明](https://github.com/realsenseai/librealsense/blob/master/doc/distribution_linux.md)

只有 SSH 时，可以跳过 Viewer，用文末的拍照命令逐台保存图像。若两个腕部画面相近，在左腕镜头前放一张写着「左」的纸再拍。想在 Mac 浏览器里看三路实时画面，可按[第 7 节](#7-用浏览器运行和停止推理)连接网页控制台。

编辑 `~/mirror_config.py`，保留生成文件中的其他设置。将下面三个序列号占位符替换成对应相机的真实序列号。

```python
from dexos_lite.robot import MirrorRobot

robot = MirrorRobot(
    sensors={
        "cam_high": {"serial_number": "主视角序列号"},
        "cam_left_wrist": {"serial_number": "左腕序列号"},
        "cam_right_wrist": {"serial_number": "右腕序列号"},
    },
)
```

保存后检查语法。命令无输出表示通过。

```bash
python -m py_compile ~/mirror_config.py
```

## 4. 检查并启动左右执行臂服务

在工控机查看 CAN 接口和服务端口。本机的执行臂接口为 `can_left`、`can_right`，均显示 `UP`。`can_left_lead` 和 `can_right_lead` 对应示教臂。若端口已有监听，先确认监听的是对应的执行臂服务。 [AIRBOT 双臂服务示例](https://docs.discover-robotics.com/document/en/airbot-play/tutorials/model-reproduction/act.html)

```bash
ip -br link show type can
ss -ltn '( sport = :50051 or sport = :50053 )'
```

启动前退出正在运行的遥操作或采集程序，清空双臂运动范围。保留原终端，新开两个 SSH 终端。

左执行臂终端运行下面两行。

```bash
conda activate airbot
airbot_server -i can_left -p 50051
```

右执行臂终端运行下面两行。

```bash
conda activate airbot
airbot_server -i can_right -p 50053
```

保持两个服务运行。在原终端再次用 `ss` 检查，确认 `50051` 和 `50053` 均显示 `LISTEN`。内置 Mirror 控制器使用这两个本地端口。 [DexOS Lite 0.2.0](https://pypi.org/project/dexos-lite/0.2.0/)

## 5. 运行 DM0.5 真机抓取

确认现场人员知道实体急停的位置、双臂运动范围内无人、回零路径畅通。在台面放一个红色方块，并按实际物体修改任务指令。回到已经设置 `DEXOS_API_KEY` 的 `(airbot)` 终端运行。

```bash
dexos-lite robot infer \
  --model-id dm05 \
  --robot-config ~/mirror_config.py \
  --prompt "Pick up the red cube." \
  --time-limit 15
```

默认启动时先回零，再执行推理。`--time-limit 15` 设置推理时长，机械臂速度由控制器决定。观察双臂是否回零、是否执行抓取。推理退出后如果终端询问评分，可按实机表现填写。 [DexOS Lite 推理文档](https://maas.dexmal.com/DexOS.md)

## 6. 停止、回零和急停复位

- **正常停止推理**。确认回零路径畅通，在推理终端按一次 **Ctrl+C**。DexOS Lite 会结束推理循环并尝试让双臂回零。按时限正常退出时，`0.2.0` 不会自动执行退出回零。 [DexOS Lite 0.2.0](https://pypi.org/project/dexos-lite/0.2.0/)
- **停止双臂服务**。等双臂停稳、推理终端回到命令行后，到两个 `airbot_server` 终端分别按 **Ctrl+C**。复查时，`50051` 和 `50053` 应无监听。
- **异常运动**。先让人退出双臂运动范围，由现场人员从安全位置按下实体 **急停 / E-STOP**。推理终端的 **Ctrl+C** 可能触发回零。
- **解除实体急停**。保持急停按下，退出推理和遥操程序。现场人员排除异常并确认运动范围内无人后，按设备交付规程复位。DOS W1 公开产品页未标明急停位置和具体解锁操作，应以实机说明和现场设备负责人为准。 [DOS W1 官方产品页](https://dev.dexmal.com/product/dos-w1)

### 单独让双臂回零

可使用原厂控制工具的回零功能，也可在工控机的 `(airbot)` 终端直接调用 DexOS Lite 的回零接口。先退出网页服务、终端推理、采集和遥操程序，保持左右 `airbot_server` 运行。确认双臂已停稳、回零路径畅通、现场急停可用。这条命令会实际移动双臂和夹爪。 [DexOS Lite SDK](https://pypi.org/project/dexos-lite/0.2.0/)

```bash
python - <<'PY'
from dexos_lite.robot import load_robot_config

robot = load_robot_config("~/mirror_config.py")
try:
    robot.start()
    robot.reset_to_home()
finally:
    robot.close()
PY
```

命令使用与启动推理时相同的回零接口，无需加载 MaaS API Key。执行后在现场确认双臂回到预期位置并停稳。这段独立命令已核对 SDK 实现。

## 7. 用浏览器运行和停止推理

控制台复用已有的 `/home/ubuntu/mirror_config.py` 和 DexOS Lite。网页上可以预览三路相机、填写抓取指令和时限、启动或停止推理。工控机只在本机监听，通过 SSH 转发给 Mac 浏览器。

### 在 Mac 预览

在项目根目录运行模拟模式，然后打开 [本地控制台](http://127.0.0.1:8765)。模拟模式使用三张合成示例图，无需连接工控机或设置 API Key。

```bash
python3 mirror-console/server.py --demo
```

### 连接真机

退出本地模拟程序。在 Mac 上把 `工控机地址` 换成现有 SSH 登录用的 IP 或主机名，复制控制台并建立端口转发。

```bash
scp -r mirror-console ubuntu@工控机地址:~/
ssh -L 8765:127.0.0.1:8765 ubuntu@工控机地址
```

保持两条执行臂服务运行。让 RealSense Viewer、采集程序和终端推理退出，释放这三台相机。在上一步打开的工控机会话里加载密钥并启动控制台。

```bash
conda activate airbot
printf 'MaaS API Key: '
read -rs DEXOS_API_KEY
printf '\n'
export DEXOS_API_KEY
python ~/mirror-console/server.py --robot-config ~/mirror_config.py
```

默认调用 `dm05`。如果要调用已经在 MaaS 部署且正在运行的微调模型，启动时用 `--model-id` 指定部署详情中的模型 ID。可按[全流程文档](MaaS_Mirror_全流程.md#6-部署微调模型并在-dos-w1-上调用)准备模型和真机测试。

```bash
printf 'MaaS 模型 ID: '
read -r MAAS_MODEL_ID
python ~/mirror-console/server.py --robot-config ~/mirror_config.py --model-id "$MAAS_MODEL_ID"
```

在 Mac 打开 [本地控制台](http://127.0.0.1:8765)，核对页面中的模型 ID 和三路画面。填入抓取指令，确认双臂运动范围和回零路径清空后点击「开始推理」。程序先回零，再调用页面显示的模型。

需要正常停止时，先确认回零路径畅通，再点击「停止并回零」。SDK 会停止继续下发推理动作，等待已开始的操作返回，然后回零。后端日志 `POST /api/stop ... 202` 表示已接收请求。观察页面从「正在停止」或「正在回零」回到「待机」，并确认双臂停稳。控制连接发生故障时，查看工控机终端日志并在现场检查。异常运动使用现场实体急停。

### 关闭控制台和 SSH 转发

正常收工时，先确认回零路径畅通，保留两个 `airbot_server` 运行，然后在工控机的网页服务终端按一次 **Ctrl+C**。控制台会停止推理，等待当前操作返回，再调用回零接口并退出。如果网页已经执行了回零，控制台会直接退出。本次会话未进入推理阶段，或最近一次任务或控制连接发生故障时，也会跳过退出回零。异常运动使用现场实体急停。

浏览器收到退出状态或发现连接中断后，会停掉自动刷新。若退出时刚好有请求在途中，SSH 可能留下少量 `Connection refused` 提示。查看工控机终端的回零结果，并到现场确认双臂停稳。工作结束后，在工控机命令行输入 `exit` 关闭 SSH 转发。再次启动服务后刷新浏览器页面。

## 8. 日常使用

每天使用时，复用工控机上的 `airbot` 环境和 `~/mirror_config.py`。使用网页前，按[第 7 节](#7-用浏览器运行和停止推理)完成一次控制台文件复制。

### 开工检查

1. 按工位规程给设备上电。确认现场人员可从安全位置操作实体急停，双臂运动范围无人员，回零路径畅通。退出占用相机或机械臂的 Viewer、采集和遥操作程序。

2. 在 Mac 上 SSH 登录工控机。使用浏览器时，用下面的命令同时建立端口转发。把 `工控机地址` 换成平时 SSH 登录用的 IP 或主机名，保持会话打开。

   ```bash
   ssh -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 ubuntu@工控机地址
   ```

3. 在工控机检查左右执行臂端口。`50051` 和 `50053` 都是 `LISTEN` 且对应左右执行臂服务时，可直接复用。缺哪一路，就按[第 4 节](#4-检查并启动左右执行臂服务)在另一个 SSH 终端启动那一路。

   ```bash
   ss -ltn '( sport = :50051 or sport = :50053 )'
   ```

4. 在准备启动推理的工控机会话中激活环境并加载 MaaS API Key。密钥已在该会话加载时，可直接继续。

   ```bash
   conda activate airbot
   if [ -z "${DEXOS_API_KEY:-}" ]; then
       printf 'MaaS API Key: '
       read -rs DEXOS_API_KEY
       printf '\n'
   fi
   export DEXOS_API_KEY
   ```

### 用浏览器执行任务

1. 在带端口转发的工控机会话中启动控制台。

   ```bash
   python ~/mirror-console/server.py --robot-config ~/mirror_config.py
   ```

2. 在 Mac 打开[控制台](http://127.0.0.1:8765)，确认页面显示「真机模式」和「3 / 3 路可用」，核对主视角和两个腕部画面。

3. 摆好目标物，填写与台面一致的指令，例如 `Pick up the red cube.`。按任务设置时限，短时抓取测试可先用默认的 `15` 秒。确认回零路径畅通后点击「开始推理」，观察机械臂和页面的「运行记录」。每次开始任务时，程序都会先回零。

4. 需要提前结束时，确认回零路径畅通，然后点击「停止并回零」。等界面回到「待机」且双臂停稳后，可修改指令开始下一轮。关闭浏览器标签页后，当前任务仍由工控机运行。

### 用终端执行任务

需要使用命令行时，先停止网页中的任务并退出网页服务，释放相机。在已加载密钥的 `(airbot)` 终端按实际任务修改 `--prompt`，运行下面的命令。每次运行默认先回零。

```bash
dexos-lite robot infer \
  --model-id dm05 \
  --robot-config ~/mirror_config.py \
  --prompt "Pick up the red cube." \
  --time-limit 15
```

若要提前退出，先确认回零路径畅通，再在推理终端按 **Ctrl+C**，CLI 会尝试回零。若终端出现评分提示，按提示处理后回到命令行。网页和终端运行时使用同一套相机和执行臂，每次选一个入口。 [DexOS Lite 推理文档](https://maas.dexmal.com/DexOS.md)

### 收工

1. 结束当前推理并确认双臂停稳。异常运动时，从安全位置按实体急停，恢复按[第 6 节](#6-停止回零和急停复位)处理。
2. 如果使用了网页控制台，确认回零路径畅通，在工控机的网页服务终端按 **Ctrl+C** 并确认双臂停稳。网页已完成回零时，按 **Ctrl+C** 会直接退出。
3. 如需手动回零，在关闭双臂服务前按[第 6 节](#6-停止回零和急停复位)执行。
4. 如果需要关闭本次手动启动的双臂服务，在各自的 `airbot_server` 终端按 **Ctrl+C**，再退出 SSH 并按工位规程下电。

## 附录 · 通过 SSH 拍照核对相机

下面的命令在工控机的 `(airbot)` 环境运行。先将 `serials` 中的占位符换成第 3 节枚举出的三个序列号。脚本按序列号依次开启 RGB 流，把图像保存到 `~/mirror-cameras/`。 [RealSense 多相机示例](https://github.com/realsenseai/librealsense/tree/master/examples/multicam)

```bash
python - <<'PY'
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs

folder = Path.home() / "mirror-cameras"
folder.mkdir(exist_ok=True)
serials = ("第一台相机序列号", "第二台相机序列号", "第三台相机序列号")

for serial in serials:
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

    pipeline.start(config)
    try:
        for _ in range(15):
            frames = pipeline.wait_for_frames()
        color = frames.get_color_frame()
        path = folder / f"{serial}.jpg"
        if not color or not cv2.imwrite(str(path), np.asanyarray(color.get_data())):
            raise RuntimeError(f"拍照失败：{serial}")
        print(path)
    finally:
        pipeline.stop()
PY
```

在本地 Mac 的新终端执行下面的命令，把 `工控机地址` 换成 SSH 登录时使用的 IP 或主机名。照片的文件名就是相机序列号。工位实拍图和使用真实序列号的配置保留在本地。

```bash
scp -r ubuntu@工控机地址:/home/ubuntu/mirror-cameras ~/Downloads/
open ~/Downloads/mirror-cameras
```

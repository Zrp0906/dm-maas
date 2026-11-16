# DM0.5 在 Mirror（DOS W1）上的部署与控制

本项目提供 Dexmal Mirror 的部署指南和本地网页控制台。Mirror 工控机通过 DexOS Lite 调用 MaaS 的 `dm05` 模型，网页显示主视角和左右腕画面，可填写抓取指令和时限，并查看任务运行记录。

## 快速体验

在装有 Python 3.9 或以上版本的电脑上运行以下命令。模拟模式使用三张合成相机画面，无需连接机器人或配置 MaaS API Key。

```bash
git clone https://github.com/Zrp0906/dm-maas.git
cd dm-maas
python3 mirror-console/server.py --demo
```

打开[本地控制台](http://127.0.0.1:8765)，填写 `Pick up the red cube.`，点击「开始推理」，再试用「停止并回零」。终端按 **Ctrl+C** 退出模拟服务。

## 部署到真机

1. 按[部署指南](DM05_Mirror_部署与执行.md)准备 MaaS API Key、AIRBOT SDK 和 DexOS Lite，填入实机相机序列号并启动两侧执行臂服务。
2. 按[网页控制台接入步骤](DM05_Mirror_部署与执行.md#7-用浏览器运行和停止推理)在工控机上启动控制台，从本机通过 SSH 转发访问。
3. 安装配置完成后，按[日常使用流程](DM05_Mirror_部署与执行.md#8-日常使用)执行任务和收工。

真机点击「停止并回零」前，先确认双臂回零路径畅通。异常运动使用现场实体急停。

## 项目文件

- [`DM05_Mirror_部署与执行.md`](DM05_Mirror_部署与执行.md) 包含安装、相机配置、推理、回零及日常使用步骤。
- [`mirror-console/`](mirror-console/) 包含控制台页面和运行在工控机上的 Python 服务。
- [`mirror-cameras/`](mirror-cameras/) 包含模拟模式使用的合成画面。

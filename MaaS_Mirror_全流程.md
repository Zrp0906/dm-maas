# Dexmal MaaS 与 Mirror（DOS W1）全流程

从 DOS W1 真机采集开始，经过数据转换、上传、SFT 和 DAgger 训练、云端部署，再到工位上做对照测试。第 9 节记录 RECAP 的数据和价值标注流程。Mirror 的工控机准备、回零和日常操作见 [DM0.5 部署与执行](DM05_Mirror_部署与执行.md)。

训练和部署完成后，可直接看[第 10 节日常使用](#10-日常使用微调模型)。

## 1. 在工控机采集示范

1. 在 DOS W1 工控机桌面，按随设备交付的说明启动采集客户端。本工位的交付目录 `~/dos_w1` 中有 `dexmal_collection_client_dos_w1-3.1.3`。开始前关闭正在运行的 MaaS 推理和相机预览，给采集客户端释放双臂和相机。
2. 确认主视角、左腕和右腕都有画面，遥操作时左右臂及夹爪响应正确。清空双臂运动范围，并按工位规程检查实体急停。
3. 设置任务指令和保存目录。本次任务是「揭开塑料盒盖并将钥匙放入盒内」。把盖好的塑料盒和钥匙放到工作区域，在开始录制前让双臂就位。
4. 开始一段录制，用遥操作揭开盒盖、拿起钥匙并放入盒内。钥匙松开后保留一小段结束画面，再结束并保存录制。恢复物体初始状态后开始下一段。
5. 回放首段，确认能看到开盖、钥匙进入盒内和最终结果，且三路视频与双臂轨迹都已保存。复查其余录制时记录每段是否完成任务。后续上传可以分别使用成功示范（`SFT`）、执行中人工接管的纠正数据（`DAgger`）和失败案例（`FailCase`）。[DexOS Lite 数据集标签](https://pypi.org/project/dexos-lite/0.2.0/)

## 2. 将原始数据带到 Mac

本次原始数据已经在项目的 `揭开塑料盒盖并将钥匙放入盒内/`，包含 50 段 Open PDD v0.1 录制。已有该目录时，直接在 Mac 上检查数据。如果下次需要从工控机复制，在 Mac 终端设置项目路径，然后输入 SSH 登录地址和工控机上的采集目录绝对路径。

```zsh
PROJECT="$HOME/Desktop/dm_maas"
printf '工控机 SSH 登录地址（user@host）: '
read -r ROBOT_SSH
printf '工控机上的采集目录绝对路径: '
read -r REMOTE_DATA
scp -r "$ROBOT_SSH:$REMOTE_DATA" "$PROJECT/"
```

项目在其他位置时，修改 `PROJECT`。复制后将 `TASK` 写成实际任务文件夹名，检查大小和段数。用播放器打开一段 RGB 视频确认物体、视角和任务结果。

```zsh
PROJECT="$HOME/Desktop/dm_maas"
TASK='揭开塑料盒盖并将钥匙放入盒内'
RAW_DIR="$PROJECT/$TASK"

du -sh "$RAW_DIR"
find "$RAW_DIR" -type f -path '*/episode_*/meta.json' | wc -l
open "$RAW_DIR/episode_0003/sensors/cam_front_rgb.mp4"
```

本次每个 `episode_数字/` 目录都有 `meta.json`、`actions/left_arm.jsonl`、`actions/right_arm.jsonl`，以及 `sensors/` 下主视角和左右腕的 RGB MP4 与同名 `.mp4.tsf` 时间戳文件。同步时保留整个目录。原始录制、`20261026.zip` 和项目中的试样目录已在 `.gitignore` 中登记。

## 3. 转换为 LeRobot v3

本次已将 `episode_0003` 转换到项目的 `keys_in_plastic_box_probe/`。目录内有 `meta/`、`data/` 和 `videos/`，共 1,721 帧。使用现有试样时，直接进入第 4 节。需要重做转换或处理新数据时，按以下步骤运行。

1. 在 Mac 终端激活现有 `myenv`（Python 3.12），安装转换用的 LeRobot。全量校验还会用到 `ffmpeg` 和 `ffprobe`。如果这两个命令缺失，使用 Homebrew 的 `brew install ffmpeg` 安装。

   ```zsh
   source "$HOME/miniforge3/etc/profile.d/conda.sh"
   conda activate myenv
   python -m pip install 'lerobot==0.5.1'
   command -v ffmpeg ffprobe
   ```

2. 项目内的 `dataset-work/open_pdd_to_lerobot_v3.py` 是试样使用的转换脚本。`dataset-work/` 已设为 Git 忽略目录，用于保存本地脚本和转换产物。若从 Git 重新克隆项目，先在项目根目录创建 `dataset-work/`，再从官方 Open PDD v0.1 转换示例复制带命令行入口的完整脚本，保存到对应位置。[MaaS 数据集格式与转换示例](https://maas.dexmal.com/documentation/dataset-format)

   ```zsh
   mkdir -p "$HOME/Desktop/dm_maas/dataset-work"
   ```

3. 项目内的脚本已把 `This is a default prompt` 当作占位文本处理。从官方文档重新复制脚本时，在 `convert_episode()` 中将读取 `task` 的一行改为以下逻辑。转换时用 `--task` 提供实际指令，已有的有效指令继续沿用。

   ```python
   source_task = meta["task_meta"]["prompt"].strip()
   task = fallback_task if source_task in ("", "This is a default prompt") else source_task
   ```

4. 先用按段号排序后的第一段做试转换。`--dst` 必须是一个尚未创建的目录。以下示例把重跑产物写入项目内的 `dataset-work/`。

   ```zsh
   PROJECT="$HOME/Desktop/dm_maas"
   TASK='揭开塑料盒盖并将钥匙放入盒内'
   WORK_DIR="$PROJECT/dataset-work"
   PROBE_DIR="$WORK_DIR/keys_in_plastic_box_probe"

   HF_HUB_OFFLINE=1 python "$WORK_DIR/open_pdd_to_lerobot_v3.py" \
     --src "$PROJECT/$TASK" \
     --dst "$PROBE_DIR" \
     --task "$TASK" \
     --fps 30 \
     --limit 1 \
     --repo-id local/keys_in_plastic_box_probe
   ```

转换结果使用 `robot_type=mirror`。每帧包含三路 RGB 视频、14 维 `observation.state` 和 14 维 `action`。参考脚本将下一时刻的实测关节及夹爪状态写为 `action`，并在 `meta/conversion.json` 中记录对齐及来源信息。转换依赖原始 RGB 与双臂的时间戳。针对本次数据，首段转换保留了全部 1,721 个有效步。

## 4. 在 Mac 校验并上传试样

### 4.1 安装上传工具

继续使用 `myenv`。Mac 上直接安装 `dexos-lite` 会卡在 `pyrealsense2` 的发行包匹配，下面固定使用已核对过的 `0.2.0` 并单独安装上传所需依赖。[DexOS Lite 0.2.0](https://pypi.org/project/dexos-lite/0.2.0/)

```zsh
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate myenv

python -m pip install click numpy Pillow pandas pyarrow requests \
  'megfile>=5.0.17' 'botocore>=1.43.98'
python -m pip install --no-deps 'dexos-lite==0.2.0'
dexos-lite dataset upload --help
```

### 4.2 检查上传目录

命令复用当前终端的 `PROBE_DIR`，未设置时使用项目根目录下已转换的试样。校验结果应显示 `status` 为 `passed`，本次试样应显示 1 段录制、1,721 帧及 3 路视频。全量模式检查每帧状态、动作和视频解码。命令最后会打印任务表，核对其中的指令是否与实际任务一致。[DexOS Lite 本地校验说明](https://pypi.org/project/dexos-lite/0.2.0/#local-lerobot-validation)

```zsh
PROBE_DIR="${PROBE_DIR:-$HOME/Desktop/dm_maas/keys_in_plastic_box_probe}"
python - "$PROBE_DIR" <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd
from dexos_lite.lerobot_validator import validate_lerobot_dataset

root = Path(sys.argv[1])
report = validate_lerobot_dataset(root, full_check=True)
print(json.dumps(report, ensure_ascii=False, indent=2))
print(pd.read_parquet(root / "meta" / "tasks.parquet").to_string())
PY
```

### 4.3 上传到 MaaS

在同一个终端粘贴 MaaS API Key，输入时终端不会显示密钥。上传参数使用试样目录本身、`mirror` 和 `lerobot_v3`。这段人工遥操作成功示范使用 `SFT` 标签。[API Key 管理](https://maas.dexmal.com/console/api-keys) · [官方上传命令](https://pypi.org/project/dexos-lite/0.2.0/#upload-a-dataset)

```zsh
printf 'MaaS API Key: '
read -rs DEXOS_API_KEY
printf '\n'
export DEXOS_API_KEY

dexos-lite dataset upload "$PROBE_DIR" \
  --robot-type mirror \
  --dataset-format lerobot_v3 \
  --tag SFT \
  --dataset-name keys_in_plastic_box_probe
```

在数据集列表找到 `keys_in_plastic_box_probe`。`PROCESSING` 表示平台正在校验和转换，看到 `ACTIVE` 后记录数据集 ID。若处理失败，先查看平台显示的错误。[MaaS 数据集列表](https://maas.dexmal.com/console/datasets)

项目中的单段试样已通过本地全量校验。上传命令成功传输 34,352,492 字节并返回 `PROCESSING`，随后已在 MaaS 控制台确认处理完成。

### 4.4 批量转换和上传

1. 试样处理完成后，回放其余录制，按段号记录结果。盒盖已揭开、夹爪松开后钥匙仍留在盒内，记为成功。动作未完成或钥匙落在盒外，记为失败。主视角看不清时用左右腕画面核对，仍看不清则记为待确认。本次已确认按段号排序的前 25 段（`episode_0003` 到 `episode_0027`）均为成功示范。
2. 在 Mac 的 `myenv` 中复用第 3 节的脚本，直接转换前 25 段。挑选其他段号时，按第 4.5 节准备输入目录。

   ```zsh
   source "$HOME/miniforge3/etc/profile.d/conda.sh"
   conda activate myenv

   PROJECT="$HOME/Desktop/dm_maas"
   TASK='揭开塑料盒盖并将钥匙放入盒内'
   WORK_DIR="$PROJECT/dataset-work"
   PROBE_DIR="$WORK_DIR/keys_in_plastic_box_sft25"

   HF_HUB_OFFLINE=1 python "$WORK_DIR/open_pdd_to_lerobot_v3.py" \
     --src "$PROJECT/$TASK" \
     --dst "$PROBE_DIR" \
     --task "$TASK" \
     --fps 30 \
     --limit 25 \
     --repo-id local/keys_in_plastic_box_sft25
   ```

3. 在同一终端运行第 4.2 节的校验。确认 `status` 为 `passed`、`episodes_checked` 为 25，再按第 4.3 节上传，将 `--dataset-name` 改为 `keys_in_plastic_box_sft25`，标签使用 `SFT`。记录平台返回的数据集 ID 和状态。

本次正式数据集含 25 段成功示范、45,361 帧，MaaS 已完成处理。训练时选 `keys_in_plastic_box_sft25`。

### 4.5 转换并上传 DAgger 和 FailCase 数据

以下范围按原始录制的数字段号排序。三批数据已分别上传，后续可按同样方式准备新批次。

| 数据集 | 录制顺序 | 源段号 | 段数 / 帧数 | 上传标签 |
| --- | --- | --- | ---: | --- |
| `keys_in_plastic_box_sft25` | 第 1–25 条 | `0003`–`0027` | 25 / 45,361 | `SFT` |
| `keys_in_plastic_box_dagger15` | 第 26–40 条 | `0029`–`0033`、`0036`–`0045` | 15 / 28,916 | `DAgger` |
| `keys_in_plastic_box_failcase10` | 第 41–50 条 | `0046`、`0047`、`0049`–`0056` | 10 / 18,803 | `FailCase` |

下面用 DAgger 批次演示。在 Mac 的 `myenv` 里为选定的 15 段建立输入链接，再运行转换。链接和产物均保存在项目的 `dataset-work/` 中。每次转换使用尚未创建的 `PROBE_DIR`。

```zsh
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate myenv

PROJECT="$HOME/Desktop/dm_maas"
TASK='揭开塑料盒盖并将钥匙放入盒内'
WORK_DIR="$PROJECT/dataset-work"
DATASET_NAME=keys_in_plastic_box_dagger15
DATASET_TAG=DAgger
EPISODE_NUMBERS=({0029..0033} {0036..0045})
PROBE_DIR="$WORK_DIR/$DATASET_NAME"

(
  set -e
  SOURCE_DIR="$(mktemp -d "$WORK_DIR/selected-episodes.XXXXXX")"
  for n in "${EPISODE_NUMBERS[@]}"; do
    EPISODE_DIR="$PROJECT/$TASK/episode_$n"
    test -f "$EPISODE_DIR/meta.json"
    ln -s "$EPISODE_DIR" "$SOURCE_DIR/"
  done

  HF_HUB_OFFLINE=1 python "$WORK_DIR/open_pdd_to_lerobot_v3.py" \
    --src "$SOURCE_DIR" \
    --dst "$PROBE_DIR" \
    --task "$TASK" \
    --fps 30 \
    --limit "${#EPISODE_NUMBERS[@]}" \
    --repo-id "local/$DATASET_NAME"
)
```

转换 FailCase 时，用下面三行替换上面相应的设置，再运行转换代码。

```zsh
DATASET_NAME=keys_in_plastic_box_failcase10
DATASET_TAG=FailCase
EPISODE_NUMBERS=(0046 0047 {0049..0056})
```

在同一终端按第 4.2 节做全量校验，确认 `status` 为 `passed`，段数与表格一致。按第 4.3 节加载密钥，再用对应标签上传 LeRobot v3 输出目录。上传后在 MaaS 等该批变为 `ACTIVE`。[DexOS Lite 数据集标签](https://pypi.org/project/dexos-lite/0.2.0/)

```zsh
dexos-lite dataset upload "$PROBE_DIR" \
  --robot-type mirror \
  --dataset-format lerobot_v3 \
  --tag "$DATASET_TAG" \
  --dataset-name "$DATASET_NAME"
```

## 5. 在 MaaS 创建 SFT 训练任务

1. 打开 MaaS 的「后训练 → 策略模型训练」，点击「训练策略模型」。填写训练名称，例如 `dm05_keys_in_plastic_box_sft25`。[MaaS 策略模型训练](https://maas.dexmal.com/console/finetune/jobs)
2. 基础模型选官方 DM0.5，训练方案选 SFT。勾选 `keys_in_plastic_box_sft25`。单段试样已在这批成功示范中。
3. 如果只验证训练和产物保存，可在「训练方案 → 高级参数」中设置 `Trainer.num_train_steps=100`、`Trainer.save_steps=100`、`Optimizer.warmup_steps=5`。其余参数可沿用默认。本次已完成 100 步试跑并保存产物。`action_dim=32` 来自模型的填充维度，Mirror 的实际动作仍为 14 维。
4. 在「确认提交」查看点数预估，确认费用后点击「开始训练」。提交后可在任务详情查看运行日志。
5. 训练任务完成后，在「训练结果」查看模型版本和开环评测。日志里出现 `Training completed and model saved` 后，平台可能仍在处理训练产物或评测。刷新任务详情查看训练和评测状态。[MaaS 训练与部署说明](https://maas.dexmal.com/documentation/train-and-deploy)

## 6. 部署微调模型并在 DOS W1 上调用

### 6.1 在 MaaS 预约部署

在训练任务卡片或模型仓库找到生成的模型，点击「部署」。选现场有条件测试的时段，一次试跑取能完成测试的最短时段，并核对预计点数。预约提交后到「部署记录」查看状态。`待部署` 表示预约已提交，等状态变成 `正在运行`，再复制详情中的**模型 ID**，微调模型以 `ft:` 开头。训练任务 ID 和部署 ID 分别用于查找记录。[MaaS 部署记录](https://maas.dexmal.com/console/finetune/deployments) · [模型调用说明](https://maas.dexmal.com/documentation/deploy-model)

### 6.2 用网页控制台执行

按[真机网页控制台步骤](DM05_Mirror_部署与执行.md#7-用浏览器运行和停止推理)复制最新版 `mirror-console/` 并建立 SSH 转发。确认工控机的两路 `airbot_server` 在监听，现场回零路径畅通。退出占用相机的采集、预览或推理程序。

在已加载 `DEXOS_API_KEY` 的工控机 `(airbot)` 终端中运行下面的命令，提示时粘贴部署详情中的 `ft:` 模型 ID。已有控制台在运行时，等任务结束并正常退出旧进程，再启动这条命令。

```bash
printf 'MaaS 模型 ID: '
read -r MAAS_MODEL_ID
python "$HOME/mirror-console/server.py" \
  --robot-config "$HOME/mirror_config.py" \
  --model-id "$MAAS_MODEL_ID"
```

在 Mac 打开[本地控制台](http://127.0.0.1:8765)，核对页面显示的模型 ID、主视角和左右腕画面。摆好盖着的塑料盒和钥匙，填写「揭开塑料盒盖并将钥匙放入盒内」。本次录制每段约一分钟，可先给真机一次 `90` 秒的测试时限。确认现场就绪后点击「开始推理」。需要提前结束时点击「停止并回零」。到时限自然结束后，可确认回零路径畅通，再到工控机终端按 **Ctrl+C** 正常关闭控制台并回零。异常运动用现场实体急停。[控制台停止与回零](DM05_Mirror_部署与执行.md#关闭控制台和-ssh-转发)

### 6.3 用终端执行

退出网页服务释放相机，保留双臂服务。在加载了密钥的 `(airbot)` 终端运行以下命令。提示时粘贴部署详情中的模型 ID。

```bash
printf 'MaaS 模型 ID: '
read -r MAAS_MODEL_ID
dexos-lite robot infer \
  --model-id "$MAAS_MODEL_ID" \
  --robot-config "$HOME/mirror_config.py" \
  --prompt '揭开塑料盒盖并将钥匙放入盒内' \
  --time-limit 90
```

CLI 开始时会先回零。需要提前正常停止时，先确认回零路径畅通，再在推理终端按 **Ctrl+C**。达到时限后如需回零，按[单独回零步骤](DM05_Mirror_部署与执行.md#单独让双臂回零)操作。[DexOS Lite CLI](https://pypi.org/project/dexos-lite/0.2.0/#run-robot-inference)

## 7. 记录实机结果与下一轮采集

记录模型 ID、测试次数和每次结果。盒盖已揭开、夹爪松开后钥匙仍留在盒内，记为一次成功。未完成时记下停在哪个阶段、是否发生接管或重试。单次完成可用于检查流程，评估模型表现需要更多独立测试。

第一轮 SFT 模型在 DOS W1 上测试 10 次，成功 5 次，3 次以抓空告终，2 次以搬运中掉落告终，本轮成功率为 50%。下一批纠正示范优先覆盖抓空与掉落。

现有的第 26–40 条从抓空或掉落已经发生的状态开始，随后重新抓取并把钥匙放入盒内。这 15 段的三路 RGB、时间戳和双臂轨迹齐全，可整段转换。以后补采时，如果录像也包含导致偏差的动作，记录有效纠正的起止时间，保留能看出偏差的上下文，按同一时间段处理视频和轨迹。[MaaS DAgger 指南](https://maas.dexmal.com/documentation/train-dagger)

- **抓空恢复。** 从夹爪已经抓空的状态开始示教，重新对准，夹稳钥匙后放入盒内。
- **掉落恢复。** 复现钥匙落在可够到的台面上的状态，重新抓取，确认夹稳后放入盒内。

没有在线接管功能时，可退出推理和网页控制台，使用采集客户端复现本轮实际遇到的偏差，再录制恢复过程。当前网页的「停止并回零」用于结束任务。回放确认纠正有效后，按 `DAgger` 标签上传这批数据，并与已有 SFT 示范配合使用。[MaaS DAgger 指南](https://maas.dexmal.com/documentation/train-dagger)

结束测试后先停止机器人推理，确认双臂停稳，再到 MaaS「部署记录」结束本次云端部署。训练任务、机器人推理和云端部署分别有自己的状态。[MaaS 部署记录](https://maas.dexmal.com/console/finetune/deployments)

## 8. DAgger 训练与真机对照

### 8.1 创建训练任务

1. 到 MaaS「后训练 → 策略模型训练」，点击「训练策略模型」。名称可填 `dm05_keys_in_plastic_box_dagger15`，基础模型选官方 DM05。[MaaS 策略模型训练](https://maas.dexmal.com/console/finetune/jobs)
2. 添加 `keys_in_plastic_box_sft25`（SFT）和 `keys_in_plastic_box_dagger15`（DAgger）。核对本体均为 Mirror，价值标签保持「不应用价值标签」。本轮通过同时选取成功示范和纠正示范配置 DAgger 训练。
3. 若只做低点数试跑，可沿用 `Trainer.num_train_steps=100`、`Trainer.save_steps=100`、`Optimizer.warmup_steps=5`。在「确认提交」查看本轮报价，再提交训练。
4. 完成后按第 6 节部署新模型，复制这一次部署详情中的 `ft:` 模型 ID。本次 DAgger 训练和部署已完成，下一步做真机对照测试。

### 8.2 用新模型测 10 次

退出旧的网页服务，再按第 6.2 节用**这轮 DAgger 的模型 ID**重启。核对网页显示的 ID 和三路画面。沿用任务指令和 `90` 秒时限，尽量复现上一轮的物体摆放和起始状态，每次测试后复位场景。

每次记录摆放、抓空或掉落是否发生、是否自主恢复、最终是否完成，以及是否有人介入。有偏差但最终自主完成时，同时记一次成功和一次恢复。示例记录是「第 4 次｜摆放 A｜抓空后重新抓取｜自主完成」。

| 模型 | 测试次数 | 完成任务 | 因抓空失败 | 因掉落失败 | 自主恢复后完成 |
| --- | ---: | ---: | ---: | ---: | --- |
| 首轮 SFT | 10 | 5（50%） | 3 | 2 | 未单独统计 |
| SFT + DAgger | 计划 10 | 待测 | 待测 | 待测 | 待测 |

测试结束后按第 7 节停止推理和云端部署。对照最终完成次数、抓空和掉落后的恢复记录，再决定下一轮要补哪些示范。

## 9. RECAP 数据与价值标注

本次最后 10 条已作为 `FailCase` 上传。若继续 RECAP，按 MaaS 的顺序操作：[MaaS RECAP 指南](https://maas.dexmal.com/documentation/train-recap)

1. 在「后训练 → 价值模型训练」选择同任务、同本体的 `keys_in_plastic_box_sft25` 和 `keys_in_plastic_box_failcase10`。策略描述写清开盖、抓稳、放入盒内的成功条件，以及抓空、掉落等失败情况。
2. 价值模型训练完成后，先用代表性的成功与失败录制做试标注，回放核对标签能否反映任务进展和最终结果。
3. 试标注核验通过后，用同一个价值模型给 SFT、DAgger、FailCase 三批数据做全量标注。创建 RECAP 策略模型训练时，选择三批数据及匹配的价值标签版本。

本次价值模型的点数预估超过可用额度，因此暂缓提交。三批数据已上传，当前先完成 DAgger 的真机对照。后续继续时分别核对价值模型训练、价值标注和 RECAP 策略训练的报价。

## 10. 日常使用微调模型

日常执行直接使用已有的微调模型、工控机上的 `airbot` 环境、`~/mirror_config.py` 和 `~/mirror-console/`。首次复制控制台或更新版本时，按[网页控制台接入步骤](DM05_Mirror_部署与执行.md#连接真机)操作。

### 10.1 开工并确认部署

1. 按工位规程给设备上电，确认回零路径和双臂运动范围畅通，现场人员可以操作实体急停。退出正在使用相机或双臂的采集、遥操作和预览程序。
2. 打开 MaaS「部署记录」，确认今天要用的 SFT 或 DAgger 部署显示「正在运行」，复制详情里的 `ft:` 模型 ID，确认剩余可用时段足够。部署已结束时，按[第 6.1 节](#61-在-maas-预约部署)为已有模型重新预约。等工位准备好再开始占用部署时段。[MaaS 部署记录](https://maas.dexmal.com/console/finetune/deployments)
3. 在 **Mac 终端**建立 SSH 转发。把 `工控机地址` 换成平时 SSH 使用的地址，并保持此会话打开。

   ```zsh
   ssh -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 ubuntu@工控机地址
   ```

4. 登录 **DOS W1 工控机**后，检查左右执行臂服务。`50051` 和 `50053` 都显示 `LISTEN` 时可以继续。缺哪一路，就在另一个 SSH 会话按[左右执行臂服务步骤](DM05_Mirror_部署与执行.md#4-检查并启动左右执行臂服务)启动对应服务。

   ```bash
   ss -ltn '( sport = :50051 or sport = :50053 )'
   ```

### 10.2 启动网页控制台

在带转发的 **工控机终端**检查 `8765`。已有网页服务且页面显示目标模型 ID 时，继续使用该服务。需要更换模型时，先结束当前任务，再到旧网页服务的终端按 **Ctrl+C** 正常退出，等 `8765` 释放后重新启动。

```bash
ss -ltn '( sport = :8765 )'
```

启动时按提示粘贴 MaaS API Key 和所选部署的模型 ID。若此会话已加载密钥，直接输入模型 ID 即可。

```bash
conda activate airbot

if [ -z "${DEXOS_API_KEY:-}" ]; then
  printf 'MaaS API Key: '
  read -rs DEXOS_API_KEY
  printf '\n'
fi
export DEXOS_API_KEY

printf 'MaaS 模型 ID: '
read -r MAAS_MODEL_ID
python "$HOME/mirror-console/server.py" \
  --robot-config "$HOME/mirror_config.py" \
  --model-id "$MAAS_MODEL_ID"
```

终端显示 `Mirror 控制台 · http://127.0.0.1:8765` 后，在 **Mac 浏览器**打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。确认页面显示「真机模式」、正确的模型 ID 和「3 / 3 路可用」。

### 10.3 执行、停机和收工

1. 摆好盖着的塑料盒和钥匙。在网页输入「揭开塑料盒盖并将钥匙放入盒内」，整段任务可先设 `90` 秒。确认现场就绪后点「开始推理」，程序会先回零再调用模型。
2. 观察钥匙松开后是否仍在盒内，按[真机对照记录方式](#82-用新模型测-10-次)记下结果。任务完成或需要提前结束时，在回零路径畅通的情况下点「停止并回零」，等页面回到「待机」，并现场确认双臂停稳。关闭浏览器标签页后，工控机仍会运行当前任务。异常运动用现场实体急停。
3. 收工时保留两路 `airbot_server`，在工控机网页服务终端按 **Ctrl+C** 正常退出。网页已经回零时，服务会直接退出。若任务到时自然结束且控制连接正常，退出时会完成回零。控制台退出且双臂停稳后，在各自终端按 **Ctrl+C** 结束本次手动启动的双臂服务，再退出 SSH，按工位规程下电。
4. 在 MaaS「部署记录」结束这次云端部署，并核对状态。把真机和云端两处都收尾，便于控制使用点数。[MaaS 部署记录](https://maas.dexmal.com/console/finetune/deployments)

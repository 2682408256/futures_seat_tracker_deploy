# futures_seat_tracker

一个用于整理国内期货交易所日终持仓排名数据的小项目。

## 功能

- 郑商所：自动下载、解析、导入数据库
- 大商所：上传原始 ZIP，自动识别日期并导入
- 上期所：上传原始 TXT，自动识别日期并导入
- Web 看板：主力合约、阵营净持仓、净变化、历史折线图

## 部署方式

推荐把代码和数据分开，便于后续更新：

```text
/opt/futures_seat_tracker/
  app/   # 代码
  data/  # 数据库、raw、parsed
  logs/  # 日志
```

### 1. 首次放到服务器

把项目代码放进 `app/`，把现有 `outputs/` 放进 `data/`。

例如：

```bash
mkdir -p /opt/futures_seat_tracker/app /opt/futures_seat_tracker/data /opt/futures_seat_tracker/logs
```

### 2. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 3. 启动 Web

```bash
python futures_seat_tracker/main.py serve
```

默认地址：`http://127.0.0.1:5000`

如果是服务器部署，建议通过环境变量指定：

```bash
export FST_OUTPUTS_DIR=/opt/futures_seat_tracker/data
export FST_LOGS_DIR=/opt/futures_seat_tracker/logs
export FST_DB_PATH=/opt/futures_seat_tracker/data/seat_tracker.sqlite3
export FST_WEB_HOST=0.0.0.0
export FST_WEB_PORT=5000
python futures_seat_tracker/main.py serve
```

### 4. 使用启动脚本

Linux 服务器可以直接：

```bash
chmod +x start.sh
./start.sh
```

`start.sh` 会默认使用：
- `FST_OUTPUTS_DIR=/opt/futures_seat_tracker/data`
- `FST_LOGS_DIR=/opt/futures_seat_tracker/logs`
- `FST_DB_PATH=/opt/futures_seat_tracker/data/seat_tracker.sqlite3`
- `FST_WEB_HOST=0.0.0.0`
- `FST_WEB_PORT=5000`

### 5. 郑商所自动轮询

```bash
python futures_seat_tracker/main.py poll --exchange czce
```

### 6. 手动解析文件

```bash
python futures_seat_tracker/main.py parse --exchange dce --file "/path/to/file.zip"
python futures_seat_tracker/main.py parse --exchange shfe --file "/path/to/file.txt"
```

### 7. 目录说明

- `futures_seat_tracker/outputs/`：本地开发默认的数据目录
- 服务器部署时建议改为独立的 `data/` 目录
- `futures_seat_tracker/logs/`：日志
- `futures_seat_tracker/web/`：网页

## 环境变量

可选：
- `FST_OUTPUTS_DIR`
- `FST_LOGS_DIR`
- `FST_DB_PATH`
- `FST_WEB_HOST`
- `FST_WEB_PORT`

## 更新方式

推荐使用 git 管理 `app/` 里的代码，`data/` 和 `logs/` 不进入 git。

Windows 本地开发：

```bash
git add .
git commit -m "update futures seat tracker"
git push
```

Linux 服务器更新：

```bash
cd /opt/futures_seat_tracker/app
git pull
./start.sh
```

如果后续配置了 `systemd`，更新后改为：

```bash
cd /opt/futures_seat_tracker/app
git pull
systemctl restart futures-seat-tracker
```

注意：
- `outputs/`、`logs/`、`*.sqlite3` 已在 `.gitignore` 中忽略
- Windows 本地数据不会被提交到 git
- Linux 服务器的 `/opt/futures_seat_tracker/data` 不会被 `git pull` 覆盖
- 后续只更新代码，不动数据目录

## 备注

如果你是在本地开发，直接保留默认目录即可；如果你是把整个目录上传到服务器，建议把数据和代码分开。

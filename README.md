# SpeakLink

本地优先的语音速记与知识图谱系统：录音或音频上传 → 简体中文转写 → 要点卡片 → 实体关系抽取 → 图谱浏览、检索、人工校正与导出。

## 技术与目录

- `frontend/`：Next.js、TypeScript、Cytoscape.js、Zustand，包含可维护源码。
- `backend/`：FastAPI、Pydantic、SQLAlchemy、SQLite、NetworkX。
- `configs/`：版本化提示词、关系样例及运行配置。
- `tools/`：关系回归测试、评估工具、Windows 桌宠脚本与当前小猫皮肤。

默认 `llm_provider: demo` 为确定性规则抽取；`embedding_provider: hash` 为离线检索基线。支持通过 Ollama 接入 Qwen2.5 等模型，不表示已经训练或微调专用关系模型。

## 开发运行

需要 Python 3.11+、Node.js 和 pnpm。

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-asr.txt
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

另开终端：

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

网页地址：http://127.0.0.1:3000 。ASR 模型需要自行下载并配置；可先使用文字输入验证图谱流程。

或使用 `docker compose up --build` 启动开发部署。首次下载依赖和模型需要联网。

## 大模型

在 `configs/default.yaml` 设置 `llm_provider: ollama`、`llm_url: http://127.0.0.1:11434`、`llm_model: qwen2.5:7b`，并准备 Ollama 模型。容器内访问 Ollama 时应使用容器可达的地址。复制 `.env.example` 后，环境配置优先于 YAML。

## 测试

```powershell
python -m pytest backend/tests
python tools/test_capability_relations.py
python tools/evaluate_relations.py
cd frontend
pnpm test
pnpm typecheck
```

音频回归测试引用的个人录音不随仓库提交；缺少该音频夹具时，对应用例自动跳过。

## Windows 便携启动入口

`START.cmd`、`PET.cmd`、`launcher.py` 及桌宠脚本供已有便携发行版使用，需要额外配置 `runtime/`、`models/`、编译后的 `web/` 等发行资源。这些入口不能仅凭本源码仓库直接双击运行。源码开发请使用上面的开发启动方式。

## 源码归档说明

本次归档组合当前便携版的后端、ASR、配置、桌宠与维护中的前端源码。为保护本地内容并控制仓库体积，未包含个人录音、实际数据库、密钥、运行日志、模型权重、Python/Node 运行时、依赖目录、构建产物和旧版本备份。保留 `KNOWGPT_` 内部环境变量前缀与旧数据库文件名以兼容既有部署，界面产品名称为 SpeakLink。

# 江城验真

面向汉客松赛题一「Agent 公共信誉与服务验收」的独立项目。先探测服务是否可用，再按明确约定检查交付，保留可下载、可重放的本实例履约观测，帮助使用者理解选择理由。

部署目标：<https://wutiantian.cn/agent-trust/>。线上状态见发布核验记录。 本项目有独立源码、后端进程和 SQLite 数据目录；不依赖另一参赛项目运行，也不修改原西安网站。

## 解决的问题

- 注册或自我介绍不能证明服务能工作：向固定公开 RPC 发出真实只读请求，记录响应和失败。
- 返回 JSON 不代表交付合格：逐项检查链身份、finalized 时效、回执覆盖、区块关联和采集耗时。
- 只有成功率难以判断可靠性：同时展示去重样本总数、通过、拒绝、提供商和可复核证据。
- 重复点击可能刷大分母：同一提供商、快照、规则版本、验收判定及失败项只保留首次同结果观测；无交付错误按错误类型与五分钟时间桶去重。通过变过期、缺项或超时的判定变化仍会留档。

## 当前可以运行

已启用两个真实公共 RPC 服务商：**Ethereum PublicNode** 与 **dRPC Ethereum Public**（`auto` 按固定顺序探测，首个全部通过者被选中）。LlamaRPC 因来源站证书异常（Cloudflare 526/525）保持禁用。每次读取 Ethereum Mainnet 一个 finalized 区块，最多采样前 3 笔交易及回执。所有检查通过才选中服务；实时失败返回拒绝并保存失败观测，不替换成模拟成功。

### 本次新增能力

- **LLM「语义验收官」**：以 OpenAI 兼容 `chat/completions` + tool-use，吃进已经算好的结构化 `checks`，输出可解释的通过/拒收/存疑并引用证据 id。它只解释、不越权：模型结论一旦与确定性证据不一致就夹回确定性结论并标注；无 key 或调用失败时优雅降级为确定性规则结论，并在结果上标注「确定性回退 / LLM 未配置」。
- **多服务商故障切换**：某个服务商区块过期 / 回执错误 / 高延迟 / 不可用 → 该次拒收 → 自动切换到下一个健康服务商 → 选中健康者并留档。
- **故障注入演示**：明确标注为模拟，离线即可稳定复现「拒收坏数据 → 切换 → 留证据」。
- **链上信誉登记预留**：把一次验收观测映射为 ERC-8004 风格信誉事件（服务商标识、分数增量、证据 hash/URI）；无链时本地 JSONL 打桩，不上链、不持私钥。

页面可导出 JSON 证据并离线重放。健康、过期和缺回执三种合成示例单独运行，不进入真实账本。目录包含 **15 项 Skills、4 个工具岗位、8 条 Harness 规则**。

验收窗口为区块年龄 −30 至 1800 秒、采集耗时不超过 16000 ms。这些是本项目公开的技术演示约定，不是对提供商整体可用率或商业 SLA 的承诺。重复读取有 30 秒缓存，显示原始采集时点。

## LLM 配置（可选）

不配置也能完整运行（自动走确定性回退）。要启用真实 LLM，启动后端前设置环境变量：

```bash
export LLM_BASE_URL="https://api.openai.com/v1"   # 任意 OpenAI 兼容端点
export LLM_API_KEY="sk-..."                        # Bearer key；不要提交到 git
export LLM_MODEL="gpt-4o-mini"
python3 -m server.main --port 8774 --data-dir ./data
```

- 读取顺序：环境变量优先；测试通过注入假 opener，**不依赖 key、不联网**。
- 安全：key 只用于出站 `Authorization: Bearer`，不写入证据包、不进账本、不进前端。

## 本地启动

需要 Python 3.9+、Node.js 22.12+。后端使用 Python 标准库（无第三方依赖）。

```bash
npm ci            # 若 lockfile 缺当前平台原生二进制，npm install 对应平台包即可
python3 -m server.main --port 8774 --data-dir ./data
```

另开终端运行 `npm run dev`，访问 <http://127.0.0.1:5201/>。开发模式仅允许指定本地来源；本地运行不要设置生产 `PUBLIC_ORIGIN`。

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

## 坏数据 → 拒收 → 切换 → 留档：演示步骤

**A. 真实多服务商探测（curl）**

```bash
# 真实：健康则选中 publicnode；若 publicnode 坏则自动切到 drpc
curl -s -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:5201' \
  -d '{"provider_id":"auto"}' http://127.0.0.1:8774/api/probe

# 语义验收（把上面返回的 run 包成 {"receipt": ...} POST 给 /api/review）
curl -s -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:5201' \
  -d '{"receipt": <上面的 run JSON>}' http://127.0.0.1:8774/api/review
```

**B. 故障注入（离线稳定复现，明确标注为模拟）**

```bash
# 强制首个服务 publicnode 返回「过期区块」→ 拒收 → 自动切到健康的 drpc
curl -s -X POST -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:5201' \
  -d '{"provider_id":"auto","inject":"stale"}' http://127.0.0.1:8774/api/probe
#   结果：attempts[0]=publicnode 拒收(injected=true, freshness 失败)；attempts[1]=drpc 通过并选中
```

前端：在「它现在能交付吗？」勾选 **故障注入 · 模拟首个服务返回过期区块**，点「执行真实探测」，结果卡片会显示两次尝试与语义验收结论。

**C. 留档与信誉打桩**

```bash
curl -s http://127.0.0.1:8774/api/records      # 去重观测账本（注入项不入真实账本）
curl -s http://127.0.0.1:8774/api/reputation    # ERC-8004 风格信誉事件打桩与记分板
```

## 链上信誉接口（预留，未上链）

见 `server/onchain_reputation.py`。`build_reputation_event(observation)` 把一次验收映射为：

```json
{ "provider_id": "drpc", "score_delta": 1, "evidence_hash": "<receipt_sha256>",
  "evidence_uri": "local://observations/<hash>", "decision": "accepted", "onchain": false }
```

对接 EVM 合约时，把 `StubReputationLedger.record` 换成一次带签名的合约调用，例如
`ReputationRegistry(provider_id(bytes32), score_delta(int256), evidence_hash(bytes32), evidence_uri(string))`；
证据 hash 与链下重放一致，可供另一个 Escrow 项目核验。本项目**绝不持有私钥/助记词**，提交应由外部带签名中继完成。

生产后端启动方式：

```bash
PUBLIC_ORIGIN=https://wutiantian.cn python3 -m server.main --port 8774 --data-dir /独立数据目录
```

由反向代理将 `/agent-trust/api/` 映射到 `127.0.0.1:8774/api/`，静态站点使用构建出的 `dist/`。运行时须包含 `public/resources/catalog.json`。数据库 `observations.sqlite3` 与打桩信誉文件 `reputation-events.jsonl` 必须放在本项目独立、可写的数据目录中。服务只监听回环地址。

## 验证与材料

- `tests/test_backend.py`：HTTP 来源和体积限制、真实与模拟隔离、SQLite 持久化与去重、错误快照拒绝、摘要与规则重放；**本次共 33 项测试通过**（原 24 项保持绿，新增 LLM 适配/降级、多服务商切换与故障注入、信誉映射与打桩、`/api/review` 与 `/api/reputation`）。
- `tests/live-probe-result.json`：2026-10-06 本地实际 PublicNode 探测历史样本。
- [Skills Excel](public/resources/skills.xlsx) · [CSV](public/resources/skills.csv) · [JSON 目录](public/resources/catalog.json)
- [API 约定](docs/api-contract.json) · [官方赛题映射](docs/requirements-map.md)

## 实现边界与来源

本项目只提供单实例观测，不提供跨主体验证、全球公共信誉、抗女巫、签名身份或真实链上登记。SHA-256 和规则重放检查内部一致性，无法单独证明 RPC 事实、组织身份或独立验收。LLM 结论只是受证据约束的解释层，不替代确定性验收。

### 本次代码资产来源划分

- **赛前已有**（改造前已存在）：固定 PublicNode 探测、6 项确定性检查、SHA-256 证据与离线规则重放、SQLite 去重账本、液态玻璃前端骨架、合成健康/过期/缺回执示例、`tests/live-probe-result.json`。
- **本次新增**：`server/llm_reviewer.py`（OpenAI 兼容 tool-use 语义验收官 + 确定性回退）、`server/onchain_reputation.py`（ERC-8004 风格映射 + JSONL 打桩）、新增 dRPC 服务商与多服务商自动故障切换、`inject=stale` 故障注入、`/api/review` 与 `/api/reputation` 接口、前端验收结论卡片与故障注入开关、对应 unittest。
- **第三方来源**：Ethereum JSON-RPC（`eth_chainId` / `eth_getBlockByNumber` / `eth_getTransactionReceipt`）；公共端点 Ethereum PublicNode、dRPC；OpenAI 兼容 `chat/completions` 协议；React/Vite/TypeScript 与液态玻璃组件库。

赛题依据：[汉客松 S1 & ETH Wuhan 2026 选手手册](https://tokenark.feishu.cn/docx/Vn3hdD7s6okrftx9583cYgganMg)。RPC 校验与回执重放思路在此前武汉原型基础上独立实现。


## 独立交付

网页页脚提供本项目的可编辑 PPT、PDF、使用说明和独立源码下载。源码包排除运行数据库、部署凭据和其他项目内容；在干净目录执行 `npm ci` 后可单独构建。修改后先运行 `python3 scripts/package-source.py` 更新源码下载包，再运行 `npm run build`。

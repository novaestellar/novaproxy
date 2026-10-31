<p align="center">
  <img src="docs/logo-circle.png" width="150" alt="novaproxy">
</p>

<h1 align="center">novaproxy</h1>

<p align="center">
  <strong>本地代理池控制台 · 采集 → 校验 → 去重 → 地理 → 站点检测 → 统一网关</strong><br>
  <sub>一个 SOCKS5 与一个 HTTP 入口，背后是可轮换、可计量、可限额的代理池</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="python">
  <img src="https://img.shields.io/badge/fastapi-asyncio-009688?style=flat-square&logo=fastapi&logoColor=white" alt="fastapi">
  <img src="https://img.shields.io/badge/react-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="react">
  <img src="https://img.shields.io/badge/storage-SQLite%20WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="sqlite">
  <img src="https://img.shields.io/badge/console-127.0.0.1%3A12000-8F6FD8?style=flat-square" alt="port">
</p>

---

## 一句话说明

novaproxy 在本机跑一个控制台：它从公开来源采集免费代理，逐条校验连通性、匿名度与 **TLS 隧道能力**，去重、补地理信息，然后把通过校验的代理合并成两个本地入口 —— `SOCKS5 :11500` 和 `HTTP :12500`。任何程序（爬虫、浏览器、CLI 工具）指向其中一个入口，出口 IP 就会在池子里轮换，失败自动换下一个。

不依赖任何账号，不需要购买订阅，池子来自公开列表；代价是质量由这些免费代理决定，这一点在[实测数据](#实测数据)与[已知限制](#已知限制)里如实写明。

---

## 为什么需要它

直连太容易封，买住宅代理又要账号和预算。中间还有一个空档：**手上有一堆公开代理，但它们是散的、会死的、不知道哪个能用**。

novaproxy 补的就是这个空档：

| 问题 | 处理方式 |
|---|---|
| 来源散落在十几个仓库和 API | 25 个公开源并行抓取，一次拿全 |
| 列表里大量已经死掉的地址 | 并发校验，三振出局，死的自动降级 |
| 能连 HTTP 但过不了 HTTPS | 单独探测 TLS 隧道，`https` 标记真实能力 |
| 每次换 IP 要改代码 | 一个固定本地入口，后台轮换 |
| 代理会中途掉线 | 对冲重试 + 首字节与空闲超时，不让你干等 |
| 不知道哪个代理对某个站点真的好用 | 按目标主机记忆成功率，优先复用 |

---

## 核心特性

| 模块 | 能力 |
|---|---|
| **采集** | 25 个公开源（HTTP / SOCKS4 / SOCKS5）+ GeoNode 分页接口，并行下载与解析；可增删 |
| **校验** | 两个判据（httpbin、ip-api）判定存活、匿名度（elite / anonymous / transparent）、响应延迟 |
| **TLS 隧道探测** | 对每种协议都实测穿过隧道的 HTTPS，写入 `https`；网关只挑真正能过 TLS 的行 |
| **去重** | SQL 窗口函数按 `ip:port` 保留最健康的一条，重复行自动清除 |
| **地理补全** | ip-api 批量补国家、城市、ISP |
| **网关** | SOCKS5 + HTTP 双监听，三种策略（轮询 / 最少使用 / 最快） |
| **故障切换** | 对冲重试：0.6 秒后起下一个，先握手成功者胜出；3 秒总上限 |
| **超时护栏** | 首字节 2.5 秒、空闲 3.8 秒即断，最坏请求实测 3.5 秒 |
| **流量计量** | 双向字节、请求数，2 秒落盘一次 |
| **配额** | 每个代理可设流量上限，用尽即跳过（支持小数 MB） |
| **排除 / 恢复** | 一键剔除死行、一键全量恢复，状态持久化 |
| **目标记忆** | `target_hits` 记录"哪个代理对哪个站点真的通过过"，两次取一，一次探索 |
| **后台巡检** | 每 30 秒重测 40 条最旧的行，保持 `alive` 与 `https` 新鲜 |
| **站点检测** | 指定 URL，批量测池子能不能打开它，记录状态码与耗时 |
| **实时界面** | SSE 每秒推送，深色/浅色主题，中文文件名级别可读 |
| **鉴权** | 本机（127.0.0.1）免登录；`NP_AUTH=on` 恢复登录；远程访问必须会话 |

---

## 界面

- 顶部是小狗标志（圆形 + 描边环），其下七个页签：overview / pool / gateway / analytics / site check / logs / settings
- 主题切换在首次绘制前解析，页面不闪白
- 字体自托管（Nunito + Quicksand），离线也能正确渲染
- 所有列表支持排序、过滤、分页，导出支持 txt / json
- 图表与终端跟随主题：颜色全部来自 token（donut 的弧、柱状图的柱、坐标轴、tooltip、
  日志控制台），浅色与深色各自调过对比度，不再有写死的颜色

---

## 快速安装

### 方式一：源码（推荐）

```bash
# 1. 取代码
git clone https://github.com/novaestellar/novaproxy.git
cd novaproxy

# 2. 建立虚拟环境与依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
# 无头浏览器不是核心依赖。只有“注册换取”类源需要，单独装：
#   pip install -r requirements-browser.txt && playwright install chromium

# 确认依赖齐全
python -c "import fastapi, uvicorn, aiosqlite, aiohttp, aiohttp_socks; print('deps ok')"

# 3. 构建前端（仓库里已带 dist，只有改动前端时才需要）
cd web
npm install
npm run build
cd ..

# 4. 启动
python run.py
```

打开 <http://127.0.0.1:12000> —— 本机访问不需要登录。

### 方式二：Docker

```bash
# 默认镜像约 250 MB：控制台 + 网关，不含浏览器
docker build -t novaproxy .
# 需要“注册换取”类源时再加浏览器（镜像会涨到约 1.8 GB）
# docker build --build-arg WITH_BROWSER=1 -t novaproxy:browser .
docker run -d --name novaproxy \
  -p 12000:12000 -p 11500:11500 -p 12500:12500 \
  -e NP_AUTH=local \
  -e NP_GATEWAY_HOST=0.0.0.0 \
  -e NP_DB=/app/data/novaproxy.db \
  -v "$(pwd)/data:/app/data" \
  novaproxy
```

### 方式三：只想立刻用一个入口

```bash
# macOS / Linux：后台启动并等它就绪
python run.py &
sleep 8
# Windows：另开一个终端执行 python run.py，然后在下个终端继续下面两条命令
curl -s http://127.0.0.1:12000/api/collect \
  -H 'Content-Type: application/json' \
  -d '{"target":300,"protocols":["http","socks5"],"rounds":3}'
# 等采集完成后启动网关
curl -s -X POST http://127.0.0.1:12000/api/gateway/start
curl -x http://127.0.0.1:12500 https://httpbin.org/ip
```

---

## 使用说明

### 1. 采集第一批代理

界面 → **New collection**，或调用 `POST /api/collect`：

```json
{
  "target": 300,                       // 想拿到多少条存活
  "protocols": ["http", "socks4", "socks5"],
  "rounds": 3                          // 最多抓几轮源
}
```

界面右上角会显示进度，`logs` 页能看到每一轮的通过数。实测一轮 300 条大约 2–4 分钟，取决于上游源的速度。

### 2. 看池子

**pool** 页：按协议、国家、匿名度过滤；每行显示延迟、TLS 能力、最近校验时间、已用流量。可以单条测试、设配额、排除。

### 3. 启动网关

**gateway** 页 → **Start gateway**。之后任何程序都能：

```bash
# HTTP 入口（同时支持 CONNECT 与绝对 URI）
curl -x http://127.0.0.1:12500 https://httpbin.org/ip

# SOCKS5 入口
curl --socks5-hostname 127.0.0.1:11500 https://httpbin.org/ip

# Python requests
proxies = {"http": "http://127.0.0.1:12500", "https": "http://127.0.0.1:12500"}
```

同一个入口连续请求，出口 IP 会变；某个代理失效会自动换下一个，不用你处理。

### 4. 站点检测

**site check** 页：填目标 URL，选 25/50/100/200 条代理，跑一次就知道池子对那个站点到底通不通。结果记录状态码、延迟、错误原因。

### 5. 日常维护

| 动作 | 什么时候做 |
|---|---|
| `Scan pool` | 感觉成功率掉了，或隔了几小时没用 |
| `Drop dead` | 想让死行彻底离开轮换 |
| `Restore` | 想给池子一次重新证明的机会 |
| 重新采集 | 池子缩水到一半以下，或换地区需求 |

---

## 网关详解

| 端口 | 协议 | 说明 |
|---|---|---|
| `127.0.0.1:11500` | SOCKS5 | 支持 CONNECT，客户端侧无认证 |
| `127.0.0.1:12500` | HTTP | 支持 `CONNECT` 隧道与绝对 URI 转发 |

**策略**

| 策略 | 排序方式 | 适合 |
|---|---|---|
| `round_robin` | 按 `last_used` 最久未用优先，再按新鲜度 | 通用，出口 IP 分散 |
| `least_used` | 请求数最少优先 | 长时间低频、想摊平用量 |
| `fastest` | 已验证且延迟最低优先 | 对延迟敏感 |

**时间护栏（可在界面改）**

| 参数 | 默认 | 作用 |
|---|---|---|
| `deadline` | 3.0 秒 | 整个重试阶梯的总上限 |
| `hedge_delay` | 0.6 秒 | 下一个尝试提前多久起跑 |
| `retries` | 4 | 单请求最多试几个代理 |
| `first_byte_timeout` | 2.5 秒 | 隧道通了但上游不说话，多久放弃 |
| `idle_timeout` | 3.8 秒 | 传输中停住多久切断 |
| `max_per_proxy` | 2 | 同一代理同时承载几条客户端隧道 |
| `host_block_minutes` | 10 | 某站点返回 429/402/407 后，该出口冷却多久 |

**兜底出口与熔断台账**

`fallback` 是最后一个出口：只有当池子里所有候选都失败时才会拨它，平时绝不参与轮换。
每次死掉的出口会写入 `burned_exits` 台账，`_pick` 会跳过台账里的行——这样重新扫描
也不会把已经死掉的出口悄悄放回轮换。

```
POST /api/gateway/fallback        {"ip":"1.2.3.4","port":8080,"protocol":"http"}
POST /api/gateway/fallback/clear
GET  /api/gateway/burned?limit=50
POST /api/gateway/burned/clear
```

**指标条**

网关页顶部六个格子：`alive / total`、`exit IPs`（本次运行真正搬运过流量的出口数）、
`median`（池内延迟中位数）、`conns / fails`、`quota used`（受配额约束的行已用字节）、
`fallback`（当前兜底出口与命中次数）。

**粘性会话**

除了轮换入口，还有第三个监听 `127.0.0.1:12501`：同一会话固定使用同一个出口，
适合需要多步连续请求的流程（注册、下单）。会话键取 `X-NP-Session` 头，缺省用
客户端 IP，因此本机调用方天然共用一个出口。

手动指定出口（备用方案，出口由你挑选）：

```
POST /api/gateway/sticky/pin
{"session": "reg", "ip": "1.2.3.4", "port": 8080, "protocol": "http"}

POST /api/gateway/sticky/clear
```

空闲 `sticky_ttl`（默认 300 秒）后自动解绑；上游失败时立即解绑并重新挑选一次。

**429 记忆只对明文 HTTP 有效**：走 `CONNECT` 的 HTTPS 隧道是加密的，网关看不到
状态码；明文 `http://` 请求会在转发前先读一次响应头，遇到 402/407/429 就记录
该出口在该站点上的冷却时间，并立刻换下一个。

**为什么是"对冲"而不是"重试"**

免费代理的典型死法是**挂着不回**，不是立刻拒绝。串行重试会把预算全花在等第一个超时上，表现出来就是"卡住"。对冲让第二个在 0.6 秒后同时起跑，先握手成功的那个胜出，其余取消。

---

## 实测数据

同一台机器、同一目标（`https://api.ipify.org`）、同一脚本，30 次顺序 + 30 次并发 ×10：

| 场景 | 成功率 | 中位延迟 | 最慢 |
|---|---|---|---|
| 冷启动（无目标历史） | 19/30 · 63% | 1.7 s | 3.6 s |
| 目标记忆生效（重复目标） | 26/30 · **87%** | 1.0 s | 2.6 s |
| 同上并发 ×10 | 27/30 · **90%** | 1.5 s | 3.4 s |
| 打开探索（IP 更分散，11 个出口） | 23/30 · 77% | 1.8 s | 2.9 s |

池子规模随上游变化，某次实测：**951 条存活**，其中 **77 条真正能过 TLS**（这是关键数字，不是存活数）。

没有任何一次请求超过 7 秒；上表最慢为 3.6 秒。

---

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

覆盖三类：选路规则（配额、排除、TLS 能力、并发上限、按主机拉黑）、
目标记忆（成功/失败记账、封禁过期）、以及 API（源的校验、自动补池参数、
网关设置白名单）。健康巡检的批量缩放与连接超时也在其中。

全部用离线桩件，不依赖真实代理，跑完约 3 秒。

## 配置

### 环境变量（`.env`，全部可选）

| 变量 | 默认 | 作用 |
|---|---|---|
| `NP_DB` | `novaproxy.db` | SQLite 路径 |
| `NP_HOST` | `127.0.0.1` | 控制台绑定地址 |
| `NP_PORT` | `12000` | 控制台端口 |
| `NP_LOG` | `info` | uvicorn 日志级别 |
| `NP_AUTH` | `local` | `local` 本机免登录；`on` 强制登录 |
| `NP_GATEWAY_HOST` | `127.0.0.1` | 网关监听地址；容器内需设为 `0.0.0.0` |
| `NP_AUTOPOOL` | `1` | 自动补池开关；`0` 关闭，池子保持原样 |
| `NP_ADMIN_USER` | `admin` | 首次启动创建的账号 |
| `NP_ADMIN_PASS` | 随机生成 | 首次启动的管理员密码；不设则随机生成并只打印一次 |

`app/config.py` 里还有校验并发、超时、地理补全、站点检测等常量。

### 网关参数（界面保存，落库）

`strategy` · `quota_mb` · `timeout` · `max_fails` · `retries` · `hedge_delay` · `deadline` · `first_byte_timeout` · `idle_timeout` · `health_interval` · `health_batch` · `socks_port` · `http_port` · `max_per_proxy` · `host_block_minutes` · `verified_window` · `enabled_protocols`

端口改动需要 stop / start 一次，其余即时生效。

---

## HTTP API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/collect` | 开始采集 |
| POST | `/api/stop` | 停止采集 |
| POST | `/api/login` · `/api/logout` · `/api/register` | 会话（`NP_AUTH=local` 时本机不需要） |
| GET | `/api/me` | 当前身份 |
| GET | `/api/status` | 采集进度 |
| GET | `/api/stream` | SSE 实时日志 |
| GET | `/api/stats` | 概览统计 |
| GET | `/api/proxies` | 池子列表（过滤/排序/分页） |
| GET | `/api/proxies/export` | 导出 txt / json |
| POST | `/api/proxies/test` | 单条或批量测试 |
| POST | `/api/proxies/quota` | 设置流量配额 |
| POST | `/api/proxies/exclude` | 排除 / 恢复 |
| POST | `/api/proxies/recheck` | 重新校验 |
| POST | `/api/proxies/dedupe` | 去重 |
| POST | `/api/proxies/purge-dead` | 清理死行 |
| GET | `/api/gateway` | 网关状态 |
| POST | `/api/gateway/start` | 启动网关 |
| POST | `/api/gateway/stop` | 停止网关 |
| POST | `/api/gateway/scan` | 全池重新校验（含 TLS） |
| POST | `/api/gateway/drop-dead` | 剔除死行 |
| POST | `/api/gateway/restore` | 恢复全部 |
| POST | `/api/gateway/settings` | 更新网关参数 |
| GET | `/api/gateway/burned` | 熔断台账（已死出口） |
| POST | `/api/gateway/burned/clear` | 清空台账 |
| POST | `/api/gateway/fallback` | 设置兜底出口 |
| POST | `/api/gateway/fallback/clear` | 移除兜底出口 |
| GET | `/api/analytics` | 流量样本、协议分布、配额状态 |
| GET | `/api/settings` | 只读配置视图 |
| GET | `/api/site-checks` | 站点检测历史 |
| GET | `/api/sources` | 源清单（含启用状态与上次抓取条数） |
| POST | `/api/sources` | 新增源（添加时立即探测并返回条数） |
| POST | `/api/sources/toggle` | 启用 / 停用某个源 |
| POST | `/api/sources/remove` | 删除自建源 |
| GET | `/api/autopool` | 自动补池配置与当前池量 |
| POST | `/api/autopool` | 修改阈值与间隔 |

---

## 目录结构

```
novaproxy/
├── app/
│   ├── main.py          # FastAPI 路由、鉴权中间件、静态资源
│   ├── gateway.py       # SOCKS5 / HTTP 网关、对冲重试、计量、巡检
│   ├── engine.py        # 采集流程编排
│   ├── validator.py     # 校验判据与 TLS 隧道探测
│   ├── database.py      # 模式、迁移、写入锁
│   ├── security.py      # PBKDF2 口令、会话
│   ├── sitecheck.py     # 站点检测
│   ├── config.py        # 常量与环境变量
│   └── sources/public.py# 公开源清单与抓取
├── web/                 # React 19 + Vite 6 + Tailwind 4
│   ├── src/pages/       # 七个页面
│   ├── src/components/  # 外壳、卡片、对话框
│   └── public/          # 字体、图标、标志
├── docs/                # 截图与品牌资源
├── run.py               # 启动入口（NP_HOST / NP_PORT）
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 常见问题

**Q：为什么成功率不是 100%？**
免费池里真正能过 TLS 的只有约 8–10%。剩下的失败分两类：握手前失败（会被对冲重试吃掉），以及握手成功后代理中途死掉（客户端已经收到 `200 Connection Established`，无法再换出口）。后者是理论上限，不是实现缺陷。

**Q：为什么 `alive` 很多，但能过 TLS 的很少？**
因为"能访问 HTTP"和"能承载 HTTPS 隧道"是两种能力。很多公开代理只转发明文，`CONNECT` 直接被拒。novaproxy 对每个协议都实测后者并单独记录。

**Q：能替代住宅代理吗？**
不能，也不该这么用。住宅代理有真实 ISP 出口，免费池是数据中心与家用宽带混杂、寿命以分钟计。要稳定出口，仍然要买住宅/机房代理；novaproxy 解决的是"零成本、够用、可控"这一档。

**Q：本机访问为什么没有登录页？**
`NP_AUTH=local` 时，来自 127.0.0.1 的请求被视为操作者本人。想恢复登录页，用 `NP_AUTH=on` 启动；来自其他机器的请求始终需要会话。

**Q：端口能改吗？**
能。控制台用 `NP_PORT`，网关在界面里改（`socks_port` / `http_port`），改完 stop/start 一次生效。

**Q：数据存在哪？**
一个 SQLite 文件（默认 `novaproxy.db`），WAL 模式。备份就是复制这个文件（及其 `-wal`、`-shm`）。

---

## 已知限制

- 出口质量取决于公开源，随时可能整体变差
- 无法在隧道建立后重试，只能靠上层客户端重发
- 高并发（10 路以上）会下降，瓶颈是免费代理的承载能力
- 目标记忆会收窄出口 IP 范围，需要分散时把探索比例调高
- 没有 IPv6 专用池

---

## 免责声明

本项目抓取的代理由各自的维护者公开发布，novaproxy 只做聚合、校验与本地转发。请自行确认对目标站点的访问符合其服务条款与当地法律。使用者对通过本工具发起的请求负责。

---

<p align="center">
  <sub>novaproxy · 本地代理池控制台 · 界面自托管，无遥测，无外部依赖</sub>
</p>

# poker-cli — 局域网多人德州扑克 CLI 应用 · 设计与实施方案

> 版本 v1.0 · 2026-09-09
> 一句话定位：**一条命令启动、零门槛加入、产品级观感的局域网德克萨斯扑克终端应用**。
> 参考项目根目录 `<POKER>` = `E:\code\agent1\test\poker`（本文所有相对代码索引均以此为基准）。

---

## 0. 设计宪法（贯穿全文的硬约束）

1. **最小可行**：每个模块只做"让朋友局玩起来"所需的事。本文第 11 节列出的非目标一律不做。
2. **零冗余**：不添加任何"以防万一"的字段、分支、参数。命名即文档，不写解释性注释。
3. **依赖单向**：`domain ← engine ← {actors, ui, net} ← app`。出现反向需求即下沉公共抽象到 domain。禁止跨层 import 上层。
4. **接口即边界**：层间只经 `Protocol`（typing）通信；禁止任何模块触碰另一模块的内部可变状态。
5. **同类同构**：决策源（人类/Bot/远端玩家）共用一个 `Actor` 接口；传输（本地/TCP）共用一个 `Connector` 接口；不出现第二套风格。
6. **零隐式耦合**：无全局单例、无模块级可变状态。RNG、时钟、UI 全部显式注入。引擎对网络、对 UI 一无所知。
7. **能用函数不建类**：只有"有不变量的状态"（Table、Deck、Room）才用类；评估器、渲染、协议编解码全是纯函数。
8. **启动之外无命令**：唯一的 CLI 命令是 `poker-cli`。创建房间、发现房间、加入对局、改名、切主题，全部在应用内以菜单完成。

---

## 1. 四个参考项目的结论汇总

| 项目 | 技术栈 | 我们抄什么 | 我们避开什么 |
|---|---|---|---|
| [poker-solver]（TS monorepo） | Bun/TS/XState/Immer | headless 引擎（零 I/O）；`getPlayerSpecificState` 按玩家过滤的安全视图；score=牌型×10⁹+kicker 位编码；bug-reproduction 测试文化 | 边池/equity 是存根的"宣传式 README"；XState+Immer 对本项目过重；21 组合暴力枚举中的重复对象分配 |
| [Poker-over-SSH]（Python/asyncio） | asyncssh/SQLite | **可插拔 actor**（人机同接口）；actor 内闭包 await 自己的输入流 + 超时自动 fold；公共状态快照广播；房间码/房间 TTL；边池分层算法 | 游戏循环寄生在开局者协程（开局者断线全桌崩）；逐字符手写输入层；全屏 `\033[2J` 清屏闪烁；3000 行 backup 死代码；同步 SQLite 阻塞事件循环 |
| [poker-game]（Python，架构最佳） | rich+questionary，可选 iroh | **端口-适配器分层与依赖方向**；`legal_actions` 单一事实源（UI 结构上无法构造非法动作）；`SeatView` 座位私有快照；`_put_chips` 区分足额加注/短 all-in 是否重开行动权；确定性可重放（注入 RNG + `--seed`）；`build_deck` 测试发牌器；`Prompter` 的 TTY/管道双模式降级 | 评估器 tie-break bug（成对牌型主牌未前置）；手写 446 行 JSON codec 双份维护；`seat_view` 每帧重建边池；msvcrt/select 平台分支 hack |
| [Command-Line-Poker]（Python/blessed） | blessed | 11 位整数牌型编码；**上下文收缩的单键动作菜单**；`is_locked` 解锁-重锁下注轮终止条件；人类离场后自动快进节奏；剥 ANSI 的 UI 测试基类 | 固定加注额不能自选；全屏清屏重绘；8 个平行布尔状态位；空格手调对齐；3 个复制粘贴的 AI 函数 |

[poker-solver]: <POKER>/poker-solver （github.com/claudfuen/poker-solver）
[Poker-over-SSH]: <POKER>/Poker-over-SSH （github.com/poker-ssh/Poker-over-SSH）
[poker-game]: <POKER>/poker-game （github.com/davidus27/poker-game）
[Command-Line-Poker]: <POKER>/Command-Line-Poker （github.com/qelery/Command-Line-Poker）

**网络美学调研结论**（详见第 9 节链接）：
- 产品级 TUI 的共同语言（lazygit / btop / k9s）：**面板化布局、键盘优先、语义化用色、边框分区、当前焦点高亮、底部快捷键条**。我们全部采纳。
- 配色遵循 **60-30-10**（底色/结构色/强调色）；truecolor 已可假定，但必须保留 16 色降级（rich 自动探测 `Console().color_system`）。
- 卡牌渲染对标 Rust 生态的 [tui-cards]（joshka）：圆角卡面、四色花色、紧凑单行与详细两种规格。

---

## 2. 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.11+ | 四个参考项目三个是 Python；`StrEnum`、`asyncio`、`tomllib` 开箱即用 |
| 渲染 | **rich**（唯一渲染出口） | Panel/Layout/Table/Align 覆盖全部布局需求；CJK 宽度、16 色降级、Windows ANSI 全部内置处理 |
| 交互 | **prompt_toolkit** | 方向键菜单、补全、`patch_stdout()`（网络事件打印到输入行上方而不破坏菜单）；原生 asyncio 集成 |
| 网络 | stdlib `asyncio` + TCP(JSON Lines) + UDP 广播 | 局域网无需 TLS/SSH；零额外依赖 |
| 环境管理 | **uv** | `uv sync` 一条命令复原完整开发环境（含解释器）；`uv.lock` 保证跨机器依赖一致 |
| 构建 | `pyproject.toml` + `[project.scripts] poker-cli` | `uv build` 产 wheel；`uv tool install` / `pipx install` 即得全局命令 |
| 版本管理 | **git** | 仓库根 `.git`；`main` 常绿 + 短命特性分支；里程碑打 tag |
| 测试 | pytest | 引擎全确定性可重放 |

**运行时依赖合计 2 个：`rich`、`prompt_toolkit`。** 不用 Textual（全屏 widget 框架，与"网络事件随时推入"的游戏流相性差且重）；不用 questionary（它封装的正是 prompt_toolkit，但我们需要自定义按键栏与倒计时注入，直接用底层更省）；不做 SSH 服务器（要求是"局域网直接看到房间"，TCP+UDP 比 SSH 免密钥零门槛）。

### 2.1 环境与仓库约定（uv + git）

**uv 管理 Python 环境与依赖，是唯一的包事务入口**：
- 仓库自带 `.python-version`（3.11+）与 `uv.lock`；任何新机器 `uv sync` 一步完成解释器安装与依赖复原，无需系统级 Python。
- 开发期一律 `uv run` 前缀：`uv run poker-cli`（运行）、`uv run pytest`（测试）、`uv run ruff check`（Lint）——不手动激活 venv，不存在"环境没激活"类问题。
- 依赖增删只经 `uv add <pkg>` / `uv remove <pkg>`，由 uv 同步 `pyproject.toml` 与 `uv.lock`；禁止手改 lock。`uv.lock` 必须入库，`\.venv/` 必须忽略。
- 发布：`uv build` 产 wheel，`uv tool install poker-cli` 装出全局 `poker-cli` 命令。

**git 管理代码仓库**：
- 项目初始化即 `git init`；`.gitignore` 仅四类：`.venv/`、`__pycache__/`、`dist/`、`.pytest_cache/`（其余一概入库，含 `uv.lock`）。
- 分支模型最小化：`main` 常绿——pytest 全绿才允许合入；实验与重构走短命分支 `feat/*`、`fix/*`，合入即删，不做长期并行分支。
- 提交信息祈使句一行式（例：`add side-pot settlement`），不写模板化 body；每个里程碑 M0–M4 完成时打 tag（`m0`…`m4`），验收点可永久回溯。

---

## 3. 总体架构

```
┌───────────────────────────── app（组合根）─────────────────────────────┐
│  main(入口/组装)  lobby(大厅)  host_room(房间服务)  client(客机对局)  local(单机)  │
└──────┬──────────────────┬─────────────────────┬───────────────┬───────┘
       │                  │                     │               │
    ui 层             net 层                actors 层         （app 编排）
 rich 渲染·纯函数      TCP·UDP·编解码          决策源
       │                  │                     │
┌──────┴──────────────────┴─────────────────────┴───────┐
│  engine：Table 手牌状态机 · Deck · pots 边池（纯规则）  │
├───────────────────────────────────────────────────────┤
│  domain：Card · HandScore 评估器 · Action · SeatView   │
│         （零依赖，仅 stdlib + typing）                  │
└───────────────────────────────────────────────────────┘
```

### 3.1 目录结构（src 布局，文件即边界）

```
poker-cli/                ← git 仓库根（git init 于此）
├── .gitignore             ← 仅 .venv/ __pycache__/ dist/ .pytest_cache/
├── .python-version        ← 3.11+，uv 识别
├── pyproject.toml
├── uv.lock                ← 入库，跨机器一致性的凭据
├── README.md
├── src/rpoker/
│   ├── domain/
│   │   ├── cards.py        # Card, Deck, HandScore, find_best_hand
│   │   ├── actions.py      # Action, LegalActions
│   │   └── views.py        # SeatView, Street, SeatInfo
│   ├── engine/
│   │   ├── table.py        # Table 手牌状态机（唯一状态权威）
│   │   └── pots.py         # build_pots, return_uncalled, settle
│   ├── actors/
│   │   └── protocols.py    # Actor = async (SeatView) -> Action
│   │   └── bot.py          # 合法动作集内带牌力偏好的随机 bot
│   ├── net/
│   │   ├── messages.py     # 帧类型定义（dataclass）
│   │   ├── codec.py        # encode/decode：dataclass ↔ JSON 行
│   │   ├── connector.py    # Connector Protocol + TcpConnector + LocalPair
│   │   └── beacon.py       # UDP 广播/监听（房间发现）
│   ├── ui/
│   │   ├── tokens.py       # 语义色板与主题（唯一颜色出口）
│   │   ├── cards_art.py    # 卡牌渲染（单行/双行两种规格）
│   │   ├── table_view.py   # SeatView → rich 可渲染对象的纯函数
│   │   └── prompts.py      # 菜单/行动条/金额滑条（prompt_toolkit）
│   └── app/
│       ├── main.py         # poker-cli 入口
│       ├── lobby.py        # 主菜单·房间发现·创建向导·昵称
│       ├── room.py         # 房主：等待区→开局循环→结算
│       ├── table_loop.py   # 双端共用：驱动 Actor/Connector 的手牌循环
│       └── settings.py     # config.json 读写（昵称/主题）
└── tests/
    ├── domain/test_hands.py
    ├── engine/  (helpers.py 可控发牌器 + test_blinds/streets/pots/showdown/replay)
    ├── net/test_codec.py · test_beacon.py
    └── ui/test_table_view.py   # 剥 ANSI 断言
```

约 20 个源文件、预估 ≤2500 行实现（四个参考项目里最完整的 poker-game 约 8000 行，含 iroh/codec/大量测试；我们砍掉持久化、SSH、公网穿透后规模可控）。

### 3.2 三个跨层接口（全部 `typing.Protocol`，本项目的全部"接口清单"）

```python
# actors/protocols.py —— 决策源（人类本地输入 / bot / 远端玩家的唯一形态）
class Actor(Protocol):
    async def __call__(self, view: SeatView) -> Action: ...

# net/connector.py —— 传输（客机侧视角；房主侧用 LocalPair 直连）
class Connector(Protocol):
    async def send(self, message: Message) -> None: ...
    async def recv(self) -> Message: ...
    async def close(self) -> None: ...

# ui/table_view.py 之外无需第三个 UI 接口：渲染器是
# render(console, view: SeatView) -> None 纯函数，直接依赖 domain 类型。
```

---

## 4. domain 层设计

### 4.1 牌与评估（`domain/cards.py`）

```python
class Suit(StrEnum): CLUBS="♣"; DIAMONDS="♦"; HEARTS="♥"; SPADES="♠"
@dataclass(frozen=True, slots=True)
class Card:
    rank: int          # 2..14
    suit: Suit

HandKind = IntEnum    # HIGH_CARD=1 .. ROYAL_FLUSH=10（不设 ROYAL，STRAIGHT_FLUSH 顶点即皇家）
@dataclass(frozen=True, slots=True)
class HandScore:
    kind: HandKind
    tiebreak: tuple[int, ...]   # 按牌型构造的有序权重，见下

def find_best_hand(cards: Sequence[Card]) -> HandScore   # 5..7 张，C(7,5)=21 枚举
```

**关键决策——tiebreak 必须按牌型构造**，这是 poker-game 已知判胜 bug 的修正：
`pair → (pair_rank, k1, k2, k3)`、`two_pair → (hi, lo, k)`、`flush → 5 张降序`、`straight → 顶张（A2345 顶张为 5）`……`HandScore` 实现完整比较运算符，比较永远只比较 `(kind, tiebreak)` 元组。测试矩阵必须含 **"低对强踢 vs 高对弱踢"**（poker-game 的教训：其测试两边都是 A 对，导致 bug 永不可见）。

评估器实现直接采用"21 组合枚举 + 逐型短路检测"（poker-game `hands.py` 的结构 + poker-solver 的 wheel 处理），不引入查表——局域网 9 人桌摊牌每手 ≤9 次评估，性能无意义，简单压倒一切。

### 4.2 动作与视图（`domain/actions.py` / `views.py`）

```python
@dataclass(frozen=True, slots=True)
class Action:
    kind: Literal["fold","check","call","raise","allin"]
    amount: int | None      # raise 时为"加注至"总额；其余为 None

@dataclass(frozen=True, slots=True)
class LegalActions:                  # 引擎是唯一计算处，UI/bot 只消费
    can_check: bool; to_call: int
    min_raise_to: int; max_raise_to: int   # 相等即 all-in 是唯一加注档

class Street(StrEnum): WAITING; PREFLOP; FLOP; TURN; RIVER; SHOWDOWN; HAND_OVER

@dataclass(frozen=True, slots=True)
class SeatView:        # 每个座位一份、每次行动后全新构造（不可变快照）
    hand_no: int; street: Street; button: int
    community: tuple[Card, ...]; pot_total: int
    seats: tuple[SeatInfo, ...]     # name, stack, street_bet, folded, allin, is_button
    hole: tuple[Card, ...] | None   # 仅本人视图非空；观战者恒 None
    to_act: int | None
    legal: LegalActions | None      # 仅轮到本座时非空
    deadline: float | None          # 行动截止时刻（单调钟）
```

`SeatView` 同时服务三个消费者：本地渲染（ui）、bot 决策（actors）、线上序列化（net）——一个类型消灭三份状态打包代码（poker-game `views.py` 的验证过的做法）。隐私不靠过滤函数：`hole` 只在 `Table.seat_view(seat)` 构造自己视图时填入，网络上不存在"先发全量再过滤"的错误可能。

---

## 5. engine 层设计（`engine/table.py`，全项目唯一有状态权威）

```python
class Table:
    def __init__(self, seats: list[str], stacks: list[int],
                 blinds: tuple[int,int], rng: random.Random, now: Callable[[], float]): ...
    def start_hand(self) -> None
    def apply(self, seat: int, action: Action) -> None     # 校验提交者 == to_act
    def seat_view(self, seat: int | None) -> SeatView      # None = 观战
    @property
    def hand_result(self) -> HandResult | None             # 摊牌明细+每池派彩
    @property
    def finished(self) -> bool                             # 锦标赛结束（余 1 人有筹码）
```

- **状态**：`button, street, deck, community, per-seat {stack, street_bet, committed, folded, allin, has_acted}, current_bet, last_raise_size, hand_result`。RNG 与时钟注入 → 全局可重放。
- **规则正确性清单**（每条对应一个测试，全部有现成参照实现）：

| 规则 | 参照（已验证正确） |
|---|---|
| 盲注不足 → 按余额 all-in | poker-game `table.py:279-287` |
| heads-up：按钮=SB 且翻前先行动 | poker-game `table.py:261-277` |
| 翻前首行动 BB 次位；翻后首行动按钮次位 | poker-game `table.py:472-477` |
| BB option（被平跟后仍可加注） | `has_acted` 机制天然覆盖 |
| 足额加注（≥last_raise_size）才重开他人行动权并更新最小加注；短 all-in 只抬 current_bet | poker-game `table.py:365-391`（本项目最重要的一条正确性参照） |
| 街道结束 = 未弃牌未全下者 `street_bet==current_bet 且 has_acted` | poker-game `table.py:416-422` |
| 全员 all-in → 直接 run out 发完公共牌 | Poker-over-SSH 缺失此条（会发完整条街），我们必须做 |
| 未被跟注部分下注退还 | poker-game `pots.py:14-32` |
| 边池按贡献额分层切片 | poker-game `pots.py:35-56` / Poker-over-SSH `showdown_engine.py:66-79`（两者等价，取前者纯函数版） |
| 平分余数从按钮位起逐人 +1 | poker-game `table.py:573-575` |
| A2345 轮子（含同花顺） | poker-solver `HandEvaluator` + poker-game `hands.py:62-75` |
| 弃牌独赢不亮牌 |（常识规则，CLI 实现常漏） |

- **不做**：ante、straddle、run it twice、show 一张、留言式亮牌顺序。锦标赛制：破产出局、盲注默认固定（房主可开启"每 10 手盲注×2"防拖局，参照 Command-Line-Poker `table.py:32-39` 的成熟机制）。

---

## 6. 网络层设计

### 6.1 模型：房主权威（host-authoritative）

- 房主进程 = 引擎 + 房间服务。所有决策（含房主本人）都经 `Actor` 接口进入引擎，游戏循环是**独立 asyncio task**（修正 Poker-over-SSH"寄生在开局者协程"的致命缺陷：任何玩家断线只影响该座位）。
- 客机零规则：收 `state` 快照 → 渲染；轮到自己 → 本地菜单出 `Action` → `act` 帧。客机代码量 ≈ UI + Connector。

### 6.2 房间发现：UDP 广播信标（`net/beacon.py`，纯 stdlib）

- 房主每 **3 秒**向 `255.255.255.255:<BEACON_PORT>`（固定 45692，IANA 动态段）广播一帧 JSON：

```json
{"app":"poker-cli","v":1,"room":"Alice 的牌局","seats":2,"max":9,
 "in_hand":false,"tcp_port":45691,"host":"ALICE-PC"}
```

- 客机"加入房间"页监听该端口 **3 秒聚合同源去重**（同一 `tcp_port+host` 保留最新帧），按延迟/房名排序展示；`r` 键手动重扫。列表恒有一条固定选项 **"手动输入 IP:端口"** 兜底（应对路由器隔离/防火墙拦 UDP，见第 10 节风险）。
- 设计依据：[Zero-config LAN discovery 实践](https://dev.to/whetlan/building-zero-config-lan-discovery-in-nodejs-mdns-udp-broadcast-44go) 与 [UDP 服务发现综述](https://hackaday.com/2026/07/01/udp-broadcasting-and-easily-finding-network-services/)——自定义 UDP 广播是扁平二层网络下最简方案；不引入 mDNS/zeroconf 依赖（广播不跨子网这一限制用手动 IP 兜底，不为此增加依赖）。

### 6.3 对局协议：TCP + JSON Lines（`net/messages.py` / `codec.py`）

每帧一行 JSON，`v` 版本不匹配即断开并提示升级。帧全集（**这就是全部**，无保留字段）：

| 方向 | 帧 | 载荷 |
|---|---|---|
| C→H | `hello` | `{"name": "...", "v": 1}` |
| H→C | `welcome` | `{"seat": 2, "names": [...], "config": {blinds, stacks, max}}` 或 `{"error": "table_full"}` |
| C→H | `act` | `{"kind": "raise", "to": 120}`（非法/越权 → `error` 帧，本地菜单重出） |
| C→H | `chat` | `{"text": "..."}` |
| C→H | `leave` | `{}` |
| H→C | `state` | `{"view": SeatView}` ——**每次引擎状态变化后按座位定制推送**（观战者 hole=None） |
| H→C | `result` | `{"winners": [...], "reveal": {seat: [Card]}, "pots": [...]}`（含每池明细与亮牌） |
| H→C | `chat` | `{"from": "...", "text": "..."}` |
| H→C | `error` | `{"code": "...", "msg": "..."}` |

- 快照而非事件重放：客机渲染是纯函数，掉一帧无碍（下一快照自愈）；LAN 带宽下每动作一帧全量视图绰绰有余（Poker-over-SSH `get_public_state` 已验证该模式）。
- 编解码手写但**以 messages.py 的 dataclass 为单一事实源**：每帧一个 `from_dict`/`to_dict`，键缺失/类型不符抛 `ProtocolError`（吸取 poker-game 446 行双份维护 codec 的教训：不做通用 isinstance 分发机器，帧少，直写）。**不做加密**——局域网朋友局威胁模型不需要。

### 6.4 断线与超时策略（游戏永不因一人中止）

| 情形 | 行为 |
|---|---|
| 行动超时（默认 30s，房间可配 15/30/60） | `to_call==0` → 自动 check，否则 fold（比 Poker-over-SSH 无条件 fold 友好） |
| 客机 TCP 断开 | 座位保留，后续行动按超时策略自动处理（等效 sit-out）；牌局继续 |
| 房主进程退出 | 客机收到连接关闭 → 提示"房主已关闭房间"回大厅（权威模型的固有代价，README 明示；不做 host 迁移） |
| 房主等待区踢人/锁房 | 不做（非目标），列表只读展示 |

---

## 7. 交互与视觉设计（产品级的核心）

### 7.1 信息架构与全局规范

- **三条硬规范**：① 屏幕永不整体清屏闪烁——牌桌区域用 rich `Live` 原地重绘，日志/聊天在牌桌上方滚动（prompt_toolkit `patch_stdout()` 保证网络推送不撕裂输入行）；② 一切选择皆菜单（方向键+数字键+首字母），打字仅限昵称/房名/聊天/IP；③ 焦点即高亮：当前行动者、当前菜单项、自己座位三者的强调色一致。
- 键位全局表（贴在每屏底栏，产品级 TUI 的标配——lazygit/btop 模式）：

| 键 | 对局中 | 大厅/房间 |
|---|---|---|
| ↑↓←→ / 1-9 | 选动作/调档位 | 选菜单项/房间 |
| Enter | 确认 | 确认 |
| F / C / R / A | 弃牌/跟注(过牌)/加注/全下（首字母直选） | — |
| ←→（加注页） | 金额微调（步长=大盲） | — |
| Tab | 切换 等待页↔聊天 | — |
| t | 主题切换 | 主题切换 |
| Esc | 返回上级 | 返回上级 |
| Ctrl+C | 二次确认后退出（绝不裸退——退出=离座确认） | 同左 |

### 7.2 牌桌布局（`ui/table_view.py`）

```
╭─ ♠ ♥ ♦ ♣  Alice 的牌局 · 盲注 5/10 · 第 7 手 ─────────────────╮
│                                                               │
│   ●D Bob        1,240        Carol      860 ⚡to act         │   ← 座位行：按钮标 ●D，
│   [folded]                    bet 40                          │     名字/筹码/本轮下注/状态
│                                                               │     当前行动者高亮+⚡
│                    ╭─ POT 365 ─────────────────╮              │
│                    │   [8♣] [K♦] [8♦]     [2♣] │              │   ← 公共牌：翻牌逐张亮出
│                    ╰───────────────────────────╯              │     （river 已发）
│                                                               │
│        你的手牌                                                │
│        ╭────╮╭────╮   一对 8，K 踢脚（摊牌时才显示牌型）      │   ← 自牌双行大卡
│        │ A♥ ││ A♠ │                                          │
│        ╰────╯╰────╯                                          │
│                                                               │
│  14:02  Carol raises to 40        14:02  Bob calls 40         │   ← 动作日志（滚动 6 行）
├───────────────────────────────────────────────────────────────┤
│  [F]弃牌  [C]跟注 40  [R]加注  [A]全下 1,000   ⏱ ▓▓▓▓▓░░ 21s  │   ← 行动条+倒计时
╰───────────────────────────────────────────────────────────────╯
```

- 座位呈**两列表格**（最多 9 人不换版式；椭圆环是宽度陷阱，参考项目无一做成环且可读）。间距/对齐全交 rich `Table`/`Columns`，禁止空格手调（Command-Line-Poker 的反例）。
- 摊牌演出：`result` 帧到达后逐座位 300ms 依次亮牌、标注牌型，赢家行金框+彩池派彩明细，最后"继续"提示等全员 Enter（房主机自动）。

### 7.3 卡牌渲染（`ui/cards_art.py`）

- 两种规格：座位区/公共牌用**单行** `[A♠]`（宽 4，对齐稳定）；自己的手牌用**双行卡**（3 行的 5 行卡在 9 人屏占太高，Poker-over-SSH 的 5 行卡是反面教材）。
- **四色花色**：♠ 青黛 `#8da3c7` · ♥ 红 `#e06c75` · ♦ 蓝 `#61afef` · ♣ 绿 `#98c379`（取 One-Dark 系，暗底终端实测最佳）；牌背 `▨` 灰。truecolor 主色 + rich 自动 16 色降级。
- 数字 10 用 `T` 还是 `10`？公共牌/手牌区用 `10`（宽 5 卡），日志用 `T`。规则写进 `cards_art.py` 唯一出口。

### 7.4 色彩语义（`ui/tokens.py`，全项目唯一颜色出口，禁止散落硬编码）

| token | 用途 | One-Dark 基准 |
|---|---|---|
| `fg` | 正文 | `#abb2bf` |
| `dim` | 次要信息/日志时间戳 | `#5c6370` |
| `accent` | 焦点/当前行动者/菜单选中 | `#61afef` |
| `good` | 跟注/过牌/胜出 | `#98c379` |
| `bad` | 弃牌/警告 | `#e06c75` |
| `gold` | 底池/赢家/筹码变动 | `#e5c07b` |
| 花色四色 | 见 7.3 | — |

- 比例遵循 60-30-10：dim/fg 占屏 ~60%（结构），面板边框与花色 ~30%，accent/gold 高亮 ≤10%。
- 主题 = tokens 的具名 dict（内置 `onedark` 暗色 / `rosepine` / `ansi16` 降级），应用内 `t` 键切换即时生效并存入 config.json。**不做主题文件加载器**（YAML 皮肤系统是 k9s 级产品的需求，非 MVP）。

### 7.5 行动交互流（最关键的 30 秒体验）

```
轮到你 → 行动条出现（首字母直选可用）──┬─ F/C/A：即时执行（F 在 to_call==0 时隐藏，免费弃牌不存在）
                                      └─ R：进入加注滑条页
   ┌─ 加注至 ─────────────────────────────────────┐
   │   80 ‹━━━━━━●━━━━━━━━━━› 1,000               │
   │   [1]最小  [2]半池 185  [3]满池 330  [4]全下  │
   │   ←/→ 微调（步长 10）  Enter 确认  Esc 返回   │
   └──────────────────────────────────────────────┘
```

- 滑条起点=最小加注额，快捷档位按当前池实时计算；`legal`（引擎给的 `min/max_raise_to`）之外的结构上选不到——非法金额在 UI 层不存在（poker-game `prompts.py:341-372` 已验证）。
- 倒计时进入最后 5 秒转 `bad` 色并响终端 bell 一次；超时行为与 6.4 一致且提前在房规页告知。
- 非轮到你时：无输入行，整屏 Live 随 `state` 帧刷新；底部快捷键条显示 `Tab 聊天 · t 主题 · Esc 离座`。

### 7.6 大厅与房间（"零命令"承诺的落点）

```
启动 poker-cli → 首次: 请求昵称(默认 $USERNAME, 回车即用, 存 config.json)

主菜单:  ▶ 创建房间（房主）    加入房间（自动发现）    本地练习（对 bot）    退出
创建向导: 房名[默认"<昵称>的牌局"] → 盲注[5/10] → 起始筹码[1000] → 人数上限[9]
          → 行动限时[30s] → bot 补位[开]    （每一项都是选择器/带默认值的输入，一路回车可开局）
等待区:   本机 IP + "房间已在局域网广播，等待牌友…" + 座位表 + 聊天
          房主: [开始牌局](≥2 座)  bot 补位一键填充空位
加入页:   自动扫描 3s → 房间列表(房名/人数/是否对局中) → 选择 → 连接 → 等待房主开始
```

- 昵称/主题/上次的房间配置全部持久化到 `~/.config/poker-cli/config.json`（stdlib json；Windows 实际路径用 `platform` 无关的 `Path.home()` 拼接，经 `os.environ.get("APPDATA")` 优先）。
- **首启自检**：stdout 编码非 UTF-8（Windows GBK 控制台）→ 顶部横幅提示 `chcp 65001` 或改用 Windows Terminal，不阻断运行。这是 win32 环境的现实风险，必须内置检测。

---

## 8. 应用层：对局循环（双端同构）

```python
# app/table_loop.py —— 房主侧；客机侧无此循环（纯渲染+转发），见 client 流程
async def run_hand(table: Table, actors: dict[int, Actor], publish: Callable[[int|None, SeatView], Awaitable[None]]):
    table.start_hand()
    await publish(None, table.seat_view(None))          # 广播（含本地房主的 UI actor 由 state 驱动）
    while table.street not in (Street.HAND_OVER,):
        seat = table.to_act
        view = table.seat_view(seat)
        try:
            action = await asyncio.wait_for(actors[seat](view), timeout=table.act_seconds)
        except (TimeoutError, ActorLost):               # 断线与超时同一语义：按规则代打
            action = auto_action(view.legal)
        table.apply(seat, action)
        for s in table.live_seats: await publish(s, table.seat_view(s))
    await publish_result(table)                          # result 帧 + 本地演出
```

- 房主的本地座位也是 `Actor`（闭包捕获 UI 输入），远端座位的 `Actor` 是"把 view 序列化发过去、把 `act` 帧变回 Action"的桥（Poker-over-SSH `ssh_game_interaction.py:107-381` 的模式，去掉 SSH 依赖）。bot 是第三个同构实现。**三个 Actor，一套接口**——这是"同类同构"原则的落点。
- 节奏：bot 行动延迟 0.6–1.5s（注入 RNG），人类全离场（旁观）后自动加速到 0.1s（Command-Line-Poker `game.py:102-111` 验证过的体验机制）。

---

## 9. 借鉴索引（实现时直接对照）

### 9.1 代码片段（`<POKER>` 为根）

| 借什么 | 位置 |
|---|---|
| Actor 可插拔决策接口（同步/异步统一） | `Poker-over-SSH/poker/player.py:32-44` |
| actor 闭包内 await 输入流 + 超时自动行动 | `Poker-over-SSH/poker/ssh_game_interaction.py:164-171` |
| 公共状态快照广播（每次行动全新 dict） | `Poker-over-SSH/poker/game_engine.py:98-112` |
| 房间生命周期（TTL/大厅/清理协程） | `Poker-over-SSH/poker/rooms.py:38-76,246-277` |
| 端口-适配器分层与依赖方向的蓝本 | `poker-game/src/holdem/`（整体结构） |
| legal_actions 单一事实源 | `poker-game/src/holdem/engine/table.py:314-333` |
| 足额加注/短 all-in 是否重开行动权 | `poker-game/src/holdem/engine/table.py:365-391` |
| 街道结束判定 / 首行动位 | `poker-game/src/holdem/engine/table.py:416-422,472-484` |
| 边池分层 `build_pots` / 未跟注退还 | `poker-game/src/holdem/engine/pots.py:14-56` |
| 平分余数自按钮位起 | `poker-game/src/holdem/engine/table.py:573-575` |
| heads-up 盲注与行动顺序特判 | `poker-game/src/holdem/engine/table.py:261-277` |
| 座位私有视图 SeatView（一型三用） | `poker-game/src/holdem/domain/views.py:54-72` |
| 菜单仅物化合法动作（UI 无非法输入） | `poker-game/src/holdem/ui/cli/prompts.py:341-372` |
| TTY/管道双模式输入降级（可测性） | `poker-game/src/holdem/ui/cli/interact.py:201-225` |
| 确定性重放（注入 RNG/时钟 + 事件流断言） | `poker-game/src/holdem/app/play.py:43-50` + `tests/engine/test_replay.py` |
| 测试用可控发牌器 build_deck | `poker-game/tests/engine/helpers.py:19-49` |
| 手牌评估短路检测 + wheel + 双三条 | `poker-game/src/holdem/domain/hands.py:17-110`（**tie-break 需按 7.4 重写**，勿照抄 `make()`） |
| 按玩家过滤的安全视图思想 | `poker-solver/packages/core/game/PokerGame.ts:1113-1136` |
| score 位编码思路（我们将只用 tuple 比较，不取数值编码） | `poker-solver/.../HandEvaluator.ts:168-177`、`Command-Line-Poker/src/poker/utils/hand_ranking_utils.py:195-209` |
| 上下文收缩的单键动作菜单 | `Command-Line-Poker/src/poker/human.py:24-43` |
| is_locked 解锁-重锁终止条件（对照理解用） | `Command-Line-Poker/src/poker/game.py:254-273` |
| 观赛节奏自适应/盲注防拖局 | `Command-Line-Poker/src/poker/game.py:102-111`、`table.py:32-39` |
| 剥 ANSI 的 UI 断言基类 | `Command-Line-Poker/src/tests/test_utils/test_utils.py:6-14` |
| 双人 ASCII 卡拼排 | `poker-game/src/holdem/ui/cli/card_art.py:60-83` |
| 反面教材：README 承诺 ≠ 实现（equity/边池存根） | `poker-solver/apps/web/src/app/api/equity/route.ts:156-160`、`.../pot/PotManager.ts handleAllIn` |

### 9.2 网络参考

- 面板化/键盘优先/焦点高亮的产品级范式：[awesome-tuis](https://github.com/rothgar/awesome-tuis) · [lazygit](https://github.com/jesseduffield/lazygit) · [ratatui showcase](https://ratatui.rs/showcase/apps/)
- 卡牌终端渲染的视觉基准：[tui-cards（joshka）](https://docs.rs/tui-cards)
- 高性能终端渲染算法（理解 rich 的差分重绘，不必自研）：[Textualize 博客](https://textual.textualize.io/blog/2024/12/12/algorithms-for-high-performance-terminal-apps/)
- 配色系统：[rosepinetheme](https://rosepinetheme.com/themes/) · [NN/g 用色原则](https://www.nngroup.com/articles/color-enhance-design/) · [60-30-10 法则](https://guides.lib.udel.edu/design/color)
- prompt_toolkit 并发输出不撕裂输入行：[asyncio-prompt 官方示例](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/master/examples/prompts/asyncio-prompt.py) · [patch_stdout 文档](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/reference.html) · [issue #1847](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1847)
- LAN 发现：[Zero-config LAN discovery（UDP 广播帧格式设计）](https://dev.to/whetlan/building-zero-config-lan-discovery-in-nodejs-mdns-udp-broadcast-44go) · [UDP 广播不跨子网的限制](https://www.reddit.com/r/PFSENSE/comments/e75gi2/relay_udp_broadcast_across_subnets/) · [Zeroconf 综述](https://en.wikipedia.org/wiki/Zero-configuration_networking)
- 同类先行者（体验对标）：[terminal-poker（Rust 训练器）](https://lib.rs/crates/terminal-poker) · [pokerd（免安装 CLI 扑克）](https://filiph.net/text/pokerd.html)

---

## 10. 风险与规避

| 风险 | 规避 |
|---|---|
| Windows 控制台 GBK/ANSI（本项目开发环境即 win32） | 强制 rich/prompt_toolkit 自探测；首启检测 stdout 编码并提示 `chcp 65001`；README 首条推荐 Windows Terminal |
| Windows 防火墙拦 UDP 广播/TCP 监听 | 首次监听即触发系统弹窗，README 图文说明勾选"专用网络"；手动 IP 加入是恒定兜底入口 |
| rich Live 与 prompt_toolkit 抢占终端 | 模态切换：等待期=Live 只读；行动期=退出 Live、渲染静态帧+prompt_toolkit 菜单；二者不同时持有输出（poker-game 已验证该组合可行） |
| 网络推送与本地渲染竞态 | 所有输出经单一 `Screen` 协程串行化（asyncio 单线程模型内天然可串行，勿引入线程） |
| CJK 昵称/聊天导致列错位 | 交给 rich（cell width 感知）；座位名列宽预留 12 全角单元，超长截断加 `…` |
| 评估器/边池正确性 | 第 5 节规则清单逐条测试 + 每手结束后断言筹码守恒（`sum(stacks)+pot == total`，poker-game `docs/hand-8-logic-review.md` 的复盘方法论直接采用） |

---

## 11. 非目标（明确不做，防蔓延）

公网穿透/NAT（iroh、frp）、SSH 服务器形态、账号系统与任何持久化数据库（config.json 除外）、观战席（协议天然支持、UI 不做入口）、断线重连恢复座位（断线即自动代打到本手结束，座位保留但不可顶替；若需求出现，`welcome` 帧加 `token` 即可平滑升级，现在不加字段）、现金桌 rebuy、ante/straddle、多桌、手机端 telnet 适配、插件系统、多语言。

---

## 12. 测试与验收

- **domain**：36+ 评估用例矩阵（10 牌型 × wheel/双三条/同花顺冲突 + **跨型比较必须含"2 对带 A/K/Q vs K 对带 9/8/7"**）。
- **engine**：盲注/heads-up/加注重开/短 all-in/边池/余数/run out/弃牌独赢各一组；`test_replay`：同一 seed 整局事件流逐帧断言；每局终局断言筹码守恒。
- **net**：codec 往返一致性、畸形帧 → ProtocolError、beacon 编解码。
- **ui**：`SeatView` 固定样本 → 渲染字符串剥 ANSI 后快照断言。
- **手工验收清单**：两台真机（一台 win32）从 `poker-cli` 启动到分出胜负全程零命令；断电客机后牌局继续；30s 超时自动过牌；9 人满员布局无折行；16 色终端不花屏。

## 13. 里程碑（每步可独立验收）

| 阶段 | 内容 | 验收 |
|---|---|---|
| M0 | 仓库初始化（`git init` + `uv init` + `uv add rich prompt_toolkit` pytest ruff）→ domain + engine + tests | `uv run pytest` 全绿；`test_replay` 通过；首次提交并打 tag `m0` |
| M1 | ui(tokens/cards_art/table_view/prompts) + app/local | 单机对 bot 完整一局，观感达标 |
| M2 | net(codec/connector) + app/room + table_loop | 本机双进程 TCP 对战 |
| M3 | net/beacon + app/lobby | 两台真机零配置发现并完赛 |
| M4 | 打磨：动效/倒计时/聊天/主题/节奏加速/README | 手工验收清单全过 |

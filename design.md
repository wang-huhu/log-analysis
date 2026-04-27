# Lumo Error Log 智能分析助手设计文档

## 1. 目标

构建一个本地运行的 Python 定时脚本，从 HTTP 日志接口周期性拉取 error 日志，自动完成以下流程：

1. 解析日志并提取异常关键信息
2. 按错误指纹聚合同类异常
3. 从栈帧推断可疑源码文件
4. 通过 GitLab API 拉取相关 Kotlin 源码
5. 基于日志和源码调用 LangChain + OpenAI 兼容模型进行分析
6. 生成适合发送到飞书的简洁诊断结果
7. 通过飞书 webhook 推送诊断消息
8. 保存状态，避免重复刷屏

该工具的核心价值是将“线上错误日志 -> 根因分析 -> 飞书可转发结论”这条链路自动化。

---

## 2. 范围

### 2.1 本期范围

本期设计覆盖：

- 本地 Python 脚本运行形态
- 定时拉取 HTTP JSON 日志
- Spring Boot / Kotlin 异常日志解析
- 按错误指纹聚合
- 基于栈帧定位 GitLab 文件路径
- GitLab API 按文件路径拉取源码
- 基于现有 `prompt.md` 模板构建分析输入
- 使用 LangChain 调 OpenAI 兼容模型
- 飞书 webhook 发送诊断结果
- 本地状态存储与去重

### 2.2 暂不包含

当前不包含：

- Web 管理界面
- 多租户/多项目统一控制台
- 自动修复代码
- 自动创建 GitLab issue / MR
- 完整的代码图谱或仓库级语义检索
- 飞书机器人交互式回查能力

---

## 3. 总体架构

整体采用“本地定时脚本 + 分层模块”的方式实现。

主流程如下：

`scheduler -> log_client -> log_parser -> fingerprinter -> locator -> gitlab_client -> prompt_builder -> analyzer -> feishu_notifier -> state_store`

### 3.1 各模块职责

#### scheduler
负责按固定周期触发一次完整处理流程，并生成本次轮询的时间窗口。

#### log_client
负责调用日志 HTTP 接口，拉取指定时间窗口内的原始 JSON 响应。

#### log_parser
负责从日志响应中提取结构化错误信息，重点处理：

- `hits.hits[*]._source.logmessage`
- `@timestamp`
- `kubernetes.namespace`
- `kubernetes.pod.name`
- `kubernetes.container.name`
- 其他服务元数据

#### fingerprinter
负责根据错误特征生成错误指纹，并将同类错误聚合为错误组。

#### locator
负责从业务栈帧推断可疑 Kotlin 文件路径和候选方法。

#### gitlab_client
负责通过 GitLab API 按路径拉取源码文本。

#### prompt_builder
负责把日志摘要、错误统计、源码片段等信息填充到分析 prompt 中。

#### analyzer
负责使用 LangChain + OpenAI 兼容模型执行诊断分析，并输出结构化结果。

#### feishu_notifier
负责将结构化诊断结果转换为飞书消息并发送。

#### state_store
负责记录：

- 上次拉取时间
- 已发送错误指纹
- 指纹最近出现时间
- 去重与冷却窗口信息

---

## 4. 数据流设计

### 4.1 一次调度周期的数据流

1. `scheduler` 生成本次查询窗口，例如“过去 1 分钟”
2. `log_client` 调用 HTTP 接口拿到 JSON 日志
3. `log_parser` 解析出结构化异常事件列表
4. `fingerprinter` 对异常事件分组
5. 对每个错误组执行：
   1. `locator` 从第一业务栈帧定位候选源码文件
   2. `gitlab_client` 拉取候选文件源码
   3. `prompt_builder` 构建分析输入
   4. `analyzer` 输出诊断结论
   5. `feishu_notifier` 发送飞书消息
6. `state_store` 更新本轮处理状态

### 4.2 失败退化路径

为保证系统可用性，支持如下退化：

- GitLab 拉码失败：退化为仅日志分析
- 某个候选文件不存在：继续尝试其他候选文件
- 模型分析失败：发送降级飞书消息，仅包含错误摘要和关键栈帧
- 飞书发送失败：记录失败日志，等待下次重试或人工检查

---

## 5. 日志解析设计

### 5.1 输入日志特点

从样例可见，接口返回的是类似 Elasticsearch/Kibana 查询结果的 JSON，核心数据位于：

- `rawResponse.hits.hits[*]._source.logmessage`
- `rawResponse.hits.hits[*]._source.@timestamp`

日志正文 `logmessage` 是一段完整多行文本，包含：

- 应用时间戳
- 日志级别（ERROR）
- 线程信息
- Spring `dispatcherServlet` 异常摘要
- root cause
- Java/Kotlin 堆栈

### 5.2 需要提取的字段

每条异常事件至少提取：

- `timestamp`
- `service_name`
- `namespace`
- `pod_name`
- `container_name`
- `raw_log`
- `exception_type`
- `root_cause_message`
- `top_stack_lines`
- `business_stack_frames`
- `first_business_frame`

### 5.3 业务栈帧定义

为避免被 Spring / Tomcat / Security 框架栈淹没，业务栈帧定义为：

- 优先选择 `org.lumo.` 开头的栈帧
- 若未来项目包名前缀变动，可配置多个业务包前缀

例如：

- `org.lumo.service.impl.ObjectStorageServiceImpl.unsupportedProvider(ObjectStorageServiceImpl.kt:204)`
- `org.lumo.controller.MeProfileController.getAvatarUploadUrl(MeProfileController.kt:274)`

---

## 6. 错误聚合设计

### 6.1 聚合目标

聚合的目的不是把一分钟内所有错误混成一条消息，而是：

- 不同类型错误分开发送
- 同类型重复错误合并统计次数
- 减少飞书刷屏

### 6.2 错误指纹规则

采用用户确认的规则：

`异常类型 + root cause 消息 + 第一业务栈帧`

例如：

- `IllegalArgumentException + Unsupported object storage provider: profile-avatars + ObjectStorageServiceImpl.unsupportedProvider(ObjectStorageServiceImpl.kt:204)`
- `IllegalArgumentException + Unsupported object storage provider: profile-resources + ObjectStorageServiceImpl.unsupportedProvider(ObjectStorageServiceImpl.kt:204)`

这两类会被识别为两个不同错误组，分别发送飞书。

### 6.3 错误组统计信息

每个错误组需统计：

- `count`
- `first_seen_at`
- `last_seen_at`
- `sample_event`
- `all_related_events`

飞书消息只发 1 条，但消息中附带这组错误的出现次数与时间范围。

### 6.4 冷却与去重策略

建议增加冷却时间，例如 10~30 分钟：

- 同一指纹首次出现：立即发送
- 冷却窗口内重复出现：
  - 可静默累加计数
  - 或在下一次重新触发时带着更新后的计数再发
- 超过冷却窗口仍持续出现：重新发送

这样可以兼顾“有感知”和“不刷屏”。

---

## 7. 源码定位设计

### 7.1 定位目标

在日志已知异常的情况下，优先拉取最可能帮助分析的 Kotlin 文件，而不是完整仓库检索。

### 7.2 候选来源

优先从业务栈帧中取前 1~3 个文件：

1. 第一业务栈帧所在文件
2. 调用它的上层业务控制器/服务文件
3. 如有必要，再补一个相邻服务类

以样例为例，候选文件可能是：

- `ObjectStorageServiceImpl.kt`
- `MeProfileController.kt`

### 7.3 包名到路径推断

根据栈帧类名推断 GitLab 路径，默认规则：

- 包名 `org.lumo.service.impl.ObjectStorageServiceImpl`
- 推断路径 `src/main/kotlin/org/lumo/service/impl/ObjectStorageServiceImpl.kt`

控制器同理：

- `org.lumo.controller.MeProfileController`
- `src/main/kotlin/org/lumo/controller/MeProfileController.kt`

如果未来仓库实际目录结构有差异，可在配置中补充多组候选根路径。

### 7.4 代码截取策略

拉到整个文件后，不需要把全文都送给模型。

优先截取：

- 栈帧对应行附近上下文
- 当前方法完整代码块
- 必要时补充相邻调用方法

建议单文件只保留最关键的 80~200 行上下文，防止 prompt 过长。

---

## 8. GitLab API 设计

### 8.1 选择原因

用户已确认使用 GitLab API 按文件路径拉源码，而不是 clone 仓库。

这样更适合本地脚本场景：

- 无需维护本地仓库副本
- 获取目标文件更直接
- 可按需请求，开销更小

### 8.2 必要输入

`gitlab_client` 至少需要以下配置：

- `gitlab_base_url`
- `project_id` 或项目路径编码
- `private_token`
- `ref`（分支名，如 `main` / `master` / 指定发布分支）

### 8.3 基本能力

支持：

- 按文件路径获取源码
- 对 404 文件进行容错
- 支持多个候选路径依次尝试
- 保留响应缓存，避免同一轮内重复拉取相同文件

---

## 9. Prompt 设计

### 9.1 现有模板

当前已有 `prompt.md`，内容偏向最小可用模板，包含：

- 错误堆栈摘要
- 涉及源码片段

### 9.2 建议扩展输入

为了让分析更稳定，建议在构建 prompt 时增加以下信息：

- 服务名 / namespace / pod
- 错误次数
- 首次/最近出现时间
- 错误摘要
- root cause
- top 5 栈帧
- 候选文件路径列表
- 每个文件的关键代码片段

### 9.3 Prompt Builder 职责

`prompt_builder` 不直接依赖具体模型，只负责生成统一分析输入文本。

它的输出应当适配后续 LangChain 调用，便于未来替换模型或追加结构化输出约束。

---

## 10. Analyzer 设计（LangChain）

### 10.1 职责说明

`analyzer` 是职责名，不是框架名。该模块的实现技术选型确定为：

- LangChain
- OpenAI 兼容接口模型

因此这里的 analyzer 实际上是“基于 LangChain 的分析引擎”。

### 10.2 分层职责

建议将分析层拆分为：

- `prompt_builder`：只负责文本构建
- `analyzer`：负责调用 LangChain、处理结构化输出、异常重试、超时与失败降级

### 10.3 模型调用要求

分析模块需要支持：

- 自定义 `base_url`
- `api_key`
- `model`
- `temperature`
- 超时设置
- 重试机制

### 10.4 输出结构

建议要求模型输出固定结构字段：

- `summary`：问题摘要
- `root_cause`：根因判断
- `evidence`：日志与代码证据
- `impact`：影响范围
- `suggestion`：修复建议
- `need_human_check`：是否需要人工确认
- `risk_level`：高/中/低

即使最初飞书仅展示文本，也建议内部先转成结构化对象，便于后续扩展。

### 10.5 降级策略

若模型不可用：

- 仍应产出基础诊断消息
- 至少包含错误标题、次数、root cause、第一业务栈帧、源码定位结果

---

## 11. 飞书消息设计

### 11.1 发送粒度

每个错误组单独发送 1 条飞书消息。

因此：

- `profile-avatars` 相关错误是一条消息
- `profile-resources` 相关错误是另一条消息

不会因为出现在同一分钟就混在一起。

### 11.2 消息建议字段

每条飞书消息建议包含：

- 标题：`[ERROR] 服务名 - 异常类型`
- 错误摘要
- 出现次数
- 首次发生时间
- 最近发生时间
- namespace / pod / container
- root cause
- 第一业务栈帧
- 关键源码文件与行号
- LLM 根因分析
- 修复建议
- 风险等级
- 是否需要人工确认

### 11.3 展示原则

消息内容应符合“能直接复制到飞书群里转发”的目标：

- 简洁
- 可执行
- 不堆砌完整原始长栈
- 必要时保留代表性证据

---

## 12. 状态存储设计

### 12.1 状态目的

为了实现增量拉取和去重，需要本地保存状态。

### 12.2 建议保存内容

本地状态至少保存：

- `last_run_at`
- 已发送指纹列表
- 每个指纹的 `last_sent_at`
- 每个指纹最近出现时间
- 每个指纹最近一次统计次数

### 12.3 存储形态

作为本地脚本，初期可以使用简单文件存储：

- JSON 文件
- 或 SQLite

如果优先简单实现，可先用 JSON；如果后续需要更强查询与稳定性，可迁移 SQLite。

---

## 13. 配置设计

建议通过环境变量或本地配置文件统一管理：

- 日志接口 URL
- 日志接口认证信息
- 轮询周期
- 查询时间窗口
- 业务包名前缀
- GitLab base URL
- GitLab token
- project id
- branch/ref
- 模型 base URL
- 模型 api key
- 模型名称
- 飞书 webhook
- 冷却时间
- 状态文件路径

所有敏感信息都不应硬编码进代码。

---

## 14. 错误处理与健壮性

### 14.1 外部依赖失败

需要显式处理：

- 日志接口超时/鉴权失败
- GitLab API 404/401/超时
- 模型调用失败
- 飞书 webhook 失败

### 14.2 系统行为原则

原则如下：

- 单个错误组失败，不应中断整轮处理
- 单个候选文件拉取失败，不应阻断其他候选文件
- 外部失败应有降级输出与本地日志记录
- 尽量做到“至少能发出简化版异常通知”

---

## 15. 安全要求

- 所有 token / webhook / api_key 通过环境变量加载
- 不在日志中打印敏感信息
- 不在飞书消息中暴露密钥、cookie、token
- 不把完整大段源码无差别发到外部系统，优先发送必要片段与行号

---

## 16. 落地顺序建议

建议按以下顺序实现：

1. 日志拉取、解析、聚合
2. 本地状态存储与去重
3. 栈帧定位与 GitLab 拉码
4. Prompt 构建
5. LangChain 分析
6. 飞书推送
7. 失败降级与重试机制

这样可以先尽快得到一个“能抓到错误并区分不同异常”的最小可用版本，再逐步增强智能分析能力。

---

## 17. 设计结论

本方案采用清晰分层的本地 Python 脚本架构，满足以下核心诉求：

- 从 HTTP 接口定时拉取 error 日志
- 不同错误分开发送，同类错误聚合统计
- 先根据日志定位候选源码，再通过 GitLab API 拉码
- 使用 LangChain + OpenAI 兼容模型完成二次分析
- 输出适合飞书传播的诊断结论

该架构后续可平滑扩展日志源、模型、消息格式和代码定位策略，适合作为这个项目的第一版长期演进基础。
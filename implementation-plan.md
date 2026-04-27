# Lumo Error Log 智能分析助手 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个本地运行的 Python 定时脚本，周期性从 HTTP 接口拉取 error 日志，定位相关 Kotlin 源码，使用 LangChain + OpenAI 兼容模型生成诊断结果，并发送到飞书。

**Architecture:** 使用分层脚本架构，把“定时调度、日志拉取、日志解析、错误聚合、源码定位、GitLab 拉码、Prompt 构建、LangChain 分析、飞书通知、状态存储”拆成独立模块。先实现日志获取与聚合，再逐步接入 GitLab、LLM、飞书与去重策略，确保每一层都可以单独验证。

**Tech Stack:** Python 3.13、requests、LangChain、OpenAI 兼容接口、GitLab Files API、飞书 webhook、本地 JSON 状态存储、pytest

---

## 文件结构规划

建议将项目代码组织为以下结构：

- `main.py`
  - 程序入口，仅负责启动一次完整流程或调度逻辑
- `prompt.md`
  - LLM 分析模板
- `config.py`
  - 读取环境变量与配置校验
- `models.py`
  - 定义日志事件、错误组、源码片段、分析结果等数据结构
- `scheduler.py`
  - 生成时间窗口与调度策略
- `log_client.py`
  - HTTP 请求日志接口
- `log_parser.py`
  - 解析原始 JSON 与 `logmessage`
- `fingerprinter.py`
  - 生成错误指纹并聚合
- `locator.py`
  - 从业务栈帧推断 Kotlin 文件路径
- `gitlab_client.py`
  - 调 GitLab API 拉取源码
- `code_extractor.py`
  - 按栈帧行号截取源码上下文
- `prompt_builder.py`
  - 读取 `prompt.md` 并填充变量
- `analyzer.py`
  - 使用 LangChain 调模型，产出结构化 JSON 分析结果
- `feishu_notifier.py`
  - 发送飞书 webhook 消息
- `state_store.py`
  - 读写本地状态 JSON
- `pipeline.py`
  - 串联全流程
- `tests/test_*.py`
  - 各模块单元测试
- `sample_logs/`
  - 本地测试用脱敏样例（如用户允许创建）

如果不想拆这么多文件，至少也应保持：配置、日志解析、聚合、分析、通知、状态存储分离。

---

### Task 1: 初始化项目骨架与配置模块

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/config.py`
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/models.py`
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/main.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_config.py`

- [ ] **Step 1: 创建测试目录**

Run: `mkdir -p "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests"`
Expected: 目录创建成功

- [ ] **Step 2: 写配置模块失败测试**

在 `tests/test_config.py` 中覆盖：
- 缺少必要环境变量时报错
- 默认轮询窗口与冷却时间生效
- OpenAI 兼容配置、GitLab 配置、飞书 webhook 配置正确读取

示例测试目标：
```python
def test_load_config_requires_required_env():
    ...

def test_load_config_uses_defaults():
    ...
```

- [ ] **Step 3: 运行配置测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_config.py" -v`
Expected: FAIL，提示 `config.py` 或目标函数不存在

- [ ] **Step 4: 实现 `config.py` 最小版本**

实现内容：
- 一个 `load_config()` 函数
- 使用环境变量读取：日志接口、GitLab、模型、飞书、轮询窗口、冷却时间、状态文件路径、业务包前缀
- 必填项缺失时报 `ValueError`
- 可选项有默认值

- [ ] **Step 5: 在 `models.py` 中定义基础数据模型**

使用 `dataclasses` 定义：
- `AppConfig`
- `LogEvent`
- `ErrorGroup`
- `CodeSnippet`
- `AnalysisResult`

- [ ] **Step 6: 修改 `main.py` 为可启动入口**

把当前默认示例替换为：
- 读取配置
- 打印或记录“配置加载成功”
- 暂不接完整流程

- [ ] **Step 7: 重新运行配置测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_config.py" -v`
Expected: PASS

---

### Task 2: 实现日志接口客户端

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/log_client.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_client.py`

- [ ] **Step 1: 写日志客户端失败测试**

测试覆盖：
- 正常返回 JSON
- HTTP 非 200 抛错
- 超时抛错

- [ ] **Step 2: 运行日志客户端测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_client.py" -v`
Expected: FAIL，提示模块不存在

- [ ] **Step 3: 实现 `log_client.py` 最小版本**

实现：
- `fetch_logs(config, start_time, end_time)`
- 使用 `requests` 发起 HTTP 请求
- 返回 JSON 字典
- 对状态码与异常做统一错误包装

- [ ] **Step 4: 重新运行日志客户端测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_client.py" -v`
Expected: PASS

---

### Task 3: 实现日志解析器

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/log_parser.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_parser.py`

- [ ] **Step 1: 写日志解析失败测试**

测试覆盖：
- 从 `rawResponse.hits.hits[*]` 提取多条事件
- 从 `logmessage` 提取异常类型
- 提取 root cause message
- 提取业务栈帧
- 提取第一业务栈帧

测试样例使用你给出的脱敏 JSON 片段中最小必要子集。

- [ ] **Step 2: 运行日志解析测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_parser.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `log_parser.py`**

实现函数建议：
- `parse_raw_response(payload) -> list[LogEvent]`
- `extract_exception_type(logmessage) -> str | None`
- `extract_root_cause(logmessage) -> str | None`
- `extract_stack_frames(logmessage) -> list[str]`
- `extract_business_frames(stack_frames, package_prefixes) -> list[str]`

- [ ] **Step 4: 重新运行日志解析测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_log_parser.py" -v`
Expected: PASS

---

### Task 4: 实现错误指纹与聚合

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/fingerprinter.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_fingerprinter.py`

- [ ] **Step 1: 写聚合失败测试**

测试覆盖：
- 相同异常类型 + root cause + 第一业务栈帧的事件被聚合到一起
- `profile-avatars` 与 `profile-resources` 被识别为不同组
- 聚合结果包含 count、first_seen_at、last_seen_at、sample_event

- [ ] **Step 2: 运行聚合测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_fingerprinter.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `fingerprinter.py`**

实现：
- `build_fingerprint(event) -> str`
- `group_events(events) -> list[ErrorGroup]`

指纹规则固定为：
- 异常类型
- root cause
- 第一业务栈帧

- [ ] **Step 4: 重新运行聚合测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_fingerprinter.py" -v`
Expected: PASS

---

### Task 5: 实现源码定位器

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/locator.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_locator.py`

- [ ] **Step 1: 写定位失败测试**

测试覆盖：
- `org.lumo.service.impl.ObjectStorageServiceImpl...` 推断为 `src/main/kotlin/org/lumo/service/impl/ObjectStorageServiceImpl.kt`
- `org.lumo.controller.MeProfileController...` 推断为 `src/main/kotlin/org/lumo/controller/MeProfileController.kt`
- 无法解析时返回空列表或安全降级

- [ ] **Step 2: 运行定位测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_locator.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `locator.py`**

实现：
- `stack_frame_to_class_name(frame) -> str | None`
- `class_name_to_candidate_paths(class_name, roots) -> list[str]`
- `locate_candidate_files(error_group, roots) -> list[str]`

- [ ] **Step 4: 重新运行定位测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_locator.py" -v`
Expected: PASS

---

### Task 6: 实现 GitLab 文件客户端

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/gitlab_client.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_gitlab_client.py`

- [ ] **Step 1: 写 GitLab 客户端失败测试**

测试覆盖：
- 按路径获取文件成功
- 404 返回空或特定异常
- 多候选路径按顺序尝试

- [ ] **Step 2: 运行 GitLab 客户端测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_gitlab_client.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `gitlab_client.py`**

实现：
- `get_file(project_id, file_path, ref, token)`
- `get_first_existing_file(candidate_paths)`
- 使用 GitLab Files API
- 对路径 URL encode

- [ ] **Step 4: 重新运行 GitLab 客户端测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_gitlab_client.py" -v`
Expected: PASS

---

### Task 7: 实现源码片段提取

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/code_extractor.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_code_extractor.py`

- [ ] **Step 1: 写源码提取失败测试**

测试覆盖：
- 从栈帧行号附近截取上下文
- 行号不存在时退化为文件前若干行或关键方法附近
- 输出包含行号附近上下文，避免全文注入

- [ ] **Step 2: 运行源码提取测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_code_extractor.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `code_extractor.py`**

实现：
- `extract_line_number_from_frame(frame) -> int | None`
- `extract_snippet(source_code, line_number, before=20, after=40) -> str`

- [ ] **Step 4: 重新运行源码提取测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_code_extractor.py" -v`
Expected: PASS

---

### Task 8: 实现 Prompt 构建器

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/prompt_builder.py`
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/prompt.md`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_prompt_builder.py`

- [ ] **Step 1: 写 Prompt Builder 失败测试**

测试覆盖：
- 正确读取 `prompt.md`
- 填充 `error_summary`、`stack_trace_top_5_lines`、`root_cause_message`、`file_path`、`code_snippet`
- 结果中不应残留未替换变量

- [ ] **Step 2: 运行 Prompt Builder 测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_prompt_builder.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `prompt_builder.py`**

实现：
- `load_prompt_template(path) -> str`
- `build_prompt(error_group, code_snippet, template) -> str`

- [ ] **Step 4: 重新运行 Prompt Builder 测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_prompt_builder.py" -v`
Expected: PASS

---

### Task 9: 实现 LangChain 分析器

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/analyzer.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_analyzer.py`

- [ ] **Step 1: 写分析器失败测试**

测试覆盖：
- 分析器接收 prompt，返回 `AnalysisResult`
- 解析模型返回 JSON 字段
- 非法 JSON 时抛出明确错误或触发降级

- [ ] **Step 2: 运行分析器测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_analyzer.py" -v`
Expected: FAIL

- [ ] **Step 3: 安装并配置 LangChain 依赖**

根据项目实际情况安装：
- `langchain`
- `langchain-openai`
- `requests`
- `pytest`

如果项目后续要固定依赖，需补充依赖文件。

- [ ] **Step 4: 实现 `analyzer.py`**

实现：
- `analyze(prompt, config) -> AnalysisResult`
- 使用 LangChain + OpenAI 兼容接口调用模型
- 要求模型仅返回 JSON
- 将 JSON 解析为结构化结果

- [ ] **Step 5: 重新运行分析器测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_analyzer.py" -v`
Expected: PASS

---

### Task 10: 实现飞书通知模块

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/feishu_notifier.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_feishu_notifier.py`

- [ ] **Step 1: 写飞书通知失败测试**

测试覆盖：
- 把 `AnalysisResult` 转换为飞书文本消息
- 不同错误组生成不同消息标题
- 发送失败时抛出明确错误

- [ ] **Step 2: 运行飞书通知测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_feishu_notifier.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `feishu_notifier.py`**

实现：
- `render_message(error_group, analysis_result) -> str | dict`
- `send_message(config, message)`

初期可用简单文本消息，后续再升级卡片。

- [ ] **Step 4: 重新运行飞书通知测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_feishu_notifier.py" -v`
Expected: PASS

---

### Task 11: 实现本地状态存储

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/state_store.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_state_store.py`

- [ ] **Step 1: 写状态存储失败测试**

测试覆盖：
- 初始化空状态
- 保存与读取 `last_run_at`
- 保存与读取指纹发送信息
- 判断冷却时间是否生效

- [ ] **Step 2: 运行状态存储测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_state_store.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `state_store.py`**

实现：
- `load_state(path)`
- `save_state(path, state)`
- `should_send(fingerprint, now, cooldown_minutes)`
- `mark_sent(fingerprint, now)`

- [ ] **Step 4: 重新运行状态存储测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_state_store.py" -v`
Expected: PASS

---

### Task 12: 实现完整处理流水线

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/pipeline.py`
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/main.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_pipeline.py`

- [ ] **Step 1: 写流水线失败测试**

测试覆盖：
- 一轮处理可以从原始 payload 走到错误组
- 可跳过冷却中错误
- 同一轮里不同指纹分别处理
- GitLab 拉码失败时退化为仅日志分析

- [ ] **Step 2: 运行流水线测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_pipeline.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `pipeline.py`**

实现：
- `run_once(config)`
- 串联所有模块
- 单个错误组失败不影响其他错误组

- [ ] **Step 4: 修改 `main.py` 调用 `run_once`**

先实现单次执行版本，后面再加真正定时循环。

- [ ] **Step 5: 重新运行流水线测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_pipeline.py" -v`
Expected: PASS

---

### Task 13: 增加定时调度能力

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/scheduler.py`
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/main.py`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_scheduler.py`

- [ ] **Step 1: 写调度失败测试**

测试覆盖：
- 能根据配置生成开始时间与结束时间
- 支持单次模式与循环模式
- 循环模式在每轮结束后休眠指定秒数

- [ ] **Step 2: 运行调度测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_scheduler.py" -v`
Expected: FAIL

- [ ] **Step 3: 实现 `scheduler.py`**

实现：
- `build_time_window(now, minutes)`
- `run_forever(run_once, interval_seconds)`

- [ ] **Step 4: 修改 `main.py` 接入定时执行**

支持：
- 单次执行
- 循环执行

- [ ] **Step 5: 重新运行调度测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_scheduler.py" -v`
Expected: PASS

---

### Task 14: 增加端到端样例验证

**Files:**
- Create: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_end_to_end.py`
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/main.py`

- [ ] **Step 1: 写端到端验证测试**

使用脱敏样例，验证：
- `profile-avatars` 与 `profile-resources` 被分成不同错误组
- 能构造 prompt
- 能解析模型 JSON 返回
- 能生成两条不同飞书消息

- [ ] **Step 2: 运行端到端测试，确认失败**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_end_to_end.py" -v`
Expected: FAIL

- [ ] **Step 3: 修正实现直到端到端测试通过**

需要时补足边界处理与降级逻辑。

- [ ] **Step 4: 重新运行端到端测试，确认通过**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/test_end_to_end.py" -v`
Expected: PASS

---

### Task 15: 完整验证

**Files:**
- Modify: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/*`
- Test: `/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests/*.py`

- [ ] **Step 1: 运行全部测试**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests" -v`
Expected: 全部 PASS

- [ ] **Step 2: 运行项目入口做一次本地验证**

Run: `python "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/main.py"`
Expected: 能完成单次处理或在配置缺失时给出明确错误

- [ ] **Step 3: 补充依赖声明文件**

如果项目仍无依赖文件，创建一个最小依赖声明，例如：
- `requirements.txt`

至少包含：
- requests
- langchain
- langchain-openai
- pytest

- [ ] **Step 4: 再次运行测试**

Run: `pytest "/Users/meme-mac/PycharmProjects/LumoLogAnalysis/tests" -v`
Expected: 全部 PASS

---

## 执行注意事项

- 优先使用最小实现让测试通过，不要一开始过度设计
- 不要把完整大段栈与完整大文件源码直接送入模型
- 不要在代码中硬编码 token、webhook、api key
- 同类错误聚合规则必须严格保持为：异常类型 + root cause + 第一业务栈帧
- 飞书发送粒度必须是“每个错误组一条消息”，不能按分钟混发
- GitLab 拉码失败必须支持降级，不要让整轮流程中断

## 测试顺序建议

建议按以下顺序增量执行：

1. `test_config.py`
2. `test_log_client.py`
3. `test_log_parser.py`
4. `test_fingerprinter.py`
5. `test_locator.py`
6. `test_gitlab_client.py`
7. `test_code_extractor.py`
8. `test_prompt_builder.py`
9. `test_analyzer.py`
10. `test_feishu_notifier.py`
11. `test_state_store.py`
12. `test_pipeline.py`
13. `test_scheduler.py`
14. `test_end_to_end.py`
15. `pytest tests -v`

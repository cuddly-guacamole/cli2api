# cli2api 模型路由速查（Qoder CN / WorkBuddy / Command Code）

> 由编排者整理，2026-09-26。用于回答「同一个模型的请求为什么落到不同提供方」。
> 本机端点：`http://127.0.0.1:3010/v1`（仅绑 127.0.0.1）。管理员密钥用 `python get-key.py` 取。

## 1. 结论：请求落到哪条线，由**模型 id 的写法**决定

| 你发的 model | 实际落到 | 账号 | 实测 |
|---|---|---|---|
| `deepseek-v4.1-flash`（裸名） | **workbuddy** | `acc_2c56a3fe4ba0`（cuddly2866@gmail.com） | 3/3 成功 |
| `deepseek/deepseek-v4.1-flash`（带 `provider/` 前缀） | **command** | `acc_cfbea01ee84d`（cuddly2866nbb3） | 3/3 成功 |
| `qwen3.8-flash` | **qoder** | `acc_86c618d0c048`（qoder-cn-main） | 稳定 |

即：**想走哪条线，就在 model 里用那条线的 id 写法**。带前缀的 id 是 command 的原生 id 形态，指定它就不会被路由到别处。

## 2. 起因：一次真实的 403 故障（已定位）

**现象**：调 `deepseek-v4.1-flash` 时"一会是 WorkBuddy 的回复，一会是 Command Code 的报错"。

**机制**（来自 `request_logs` 与 `request_attempts` 两张表）：

1. `cross_provider_model_pool: true` + `routing_strategy: round-robin` ⇒ **裸名可以在多个提供方之间路由**；
2. 会话粘性（`session_affinity`，TTL 3600s）生效时 `routing=sticky`，连续请求固定在同一账号；
   **绑定过期、换会话标识、或并发请求时落到 `routing=pool`**，就会轮到下一个候选；
3. 候选里包含 **command** 账号，而 command 适配器对裸名**映射不出原生 id**：
   - `mapped_model` 为空；
   - 上游返回 **403**：

```json
{"success":false,"error":{"code":"FORBIDDEN","status":403,
 "message":"Model/provider not recognized: anthropic:DeepSeek V4.1 Flash"}}
```

原始记录（本地时间）：

```
11:38:06 | deepseek-v4.1-flash | mapped=(空) | provider=command | status=error | invalid_request
11:41:45 | deepseek-v4.1-flash | mapped=(空) | provider=command | status=error | invalid_request
```

**根因**：`internal/providers/command/mapping.go` 只登记了
`deepseek/deepseek-v4-pro`、`deepseek/deepseek-v4-flash`，**缺 `deepseek/deepseek-v4.1-flash`**；
裸名进不来映射表，于是被拼成不存在的 `anthropic:DeepSeek V4.1 Flash`。
（同时暴露第二个问题：这次失败**没有回退**到 workbuddy，直接返回了错误。）

## 3. 当前采用的规避方式

- **裸名只用于 WorkBuddy**（`deepseek-v4.1-flash`）；
- **要用 command 就显式写原生 id**（`deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4.1-flash` / `deepseek/deepseek-v4-pro`）；
- 客户端若要固定不被轮询到别的线，还可以带稳定的会话标识（`user` 字段或 `X-Codearts-Chat-Id` 之类的会话头），让粘性绑定生效（实测：相同 `user` 连续 4 次全落同一账号）。

## 4. 排查手法（可复用）

```bash
# 看某次请求实际落到哪个提供方/账号（响应头会告诉你）
curl -s -D - -o /dev/null -X POST http://127.0.0.1:3010/v1/chat/completions \
  -H "Authorization: Bearer $(python get-key.py)" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":8}' \
  | grep -iE 'x-cli2api-provider|x-cli2api-account'

# 看历史路由与失败原因（数据库是权威来源，/api/logs 可能是空的）
python <本目录>\..\..\.dsh\tmp\cli2api-routing.py
```

`request_logs` 的关键列：`requested_model` / `mapped_model` / `provider` / `account_id` / `status` / `routing`（`pool` 或 `sticky`）/ `attempt_count` / `error_kind` / `error_message`。

## 5. 待上游修复（本项目可提 issue/PR）

1. `internal/providers/command/mapping.go` 补 `deepseek/deepseek-v4.1-flash`（以及其它已在上游目录出现但未登记的 id）；
2. 裸名跨提供方轮询时，若某提供方 `mapped_model` 为空，应当**跳过该候选**而不是发出必然 403 的请求；
3. 请求失败后的**回退**（本次未回退到 workbuddy，直接失败）。

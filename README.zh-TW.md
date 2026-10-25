# oct-toolkit

[English](README.md)

安裝後，被提醒時 /clear 就好，其餘都在背景跑。

Claude Code 外掛：nap/wake 交接、記憶整理、重複讀檔防護、5h/7d 額度狀態列。

## 安裝

```bash
claude plugin marketplace add sunososobro-hub/claude-octopus
claude plugin install oct-toolkit@oct-toolkit
```

或在 session 內：`/plugin marketplace add sunososobro-hub/claude-octopus`，再 `/plugin install oct-toolkit@oct-toolkit`，之後重啟 Claude Code。

作為外掛安裝時指令帶命名空間：`/oct-toolkit:oct-nap`、`/oct-toolkit:oct-wake`、`/oct-toolkit:oct-pulse`、`/oct-toolkit:oct-checkup`、`/oct-toolkit:oct-consult`。更新：`claude plugin update oct-toolkit@oct-toolkit`。

只要指令、不要 hook 的做法：

```bash
git clone https://github.com/sunososobro-hub/claude-octopus ~/.claude/skills/oct-toolkit
```

接著執行 `/oct-toolkit:oct-pulse`（外掛）或 `/oct-pulse`（clone）並回答 yes 以接上狀態列。

需要 Python 3（`python3`、`python` 或 `py -3`）與 Claude Code >= 2.1.80。

## 指令

- `/oct-nap` 存檢查點；帶入未完成項目，並封存同專案舊檢查點
- `/oct-wake` 載入檢查點或搜尋長期記憶
- `/oct-pulse` 狀態列與每回應花費列
- `/oct-checkup` 每次呼叫的 token/花費表、`habits`、`nap-timing`、`report`、`baseline`、`memory`
- `/oct-consult` 冷代理第二意見

## 自動行為與成本

| 什麼在跑 | 何時 | 約略 token |
|---|---|---|
| Nap 提醒（`nap-nudge.py`） | 依你自己的歷史算出「現在 nap + `/clear` 的淨省」超過 `nudge_min_net_usd`（預設 $0.02，已扣冷啟動成本）才提醒，最多每 15 回合一次；歷史不足時退回 30 個使用者回合或 context 成長 `nudge_growth_tokens`（預設 80000） | 一行 |
| 背景 nap | fork 子代理寫檢查點、合併封存、印省錢行；不擋你的回合 | fork 重讀快取 context（cache read） |
| /clear 提醒 | nap 後約 5 回合，一行，每次 nap 一次 | 一行 |
| 記憶整理 | nap 後，且 `MEMORY.md` 超過 40 行 | 只讀記憶檔 |
| 自動 wake（`auto-wake.py`） | `/clear` 後注入該專案最新檢查點 | 每次 `/clear` 約 1-2k |
| 花費列（Stop hook） | 每次回應後，以 systemMessage 顯示 | 0 |
| 啟動提醒（`wake-nudge.py`） | 新 session 提醒未接續的檢查點；`MEMORY.md` 過肥或 30 天未檢查時提醒一次 | 0 |
| 首次健檢（`oct_core.py`） | 第一次（`oct-toolkit/checkup.json` 不存在）自動跑，背景腳本讀你的對話紀錄，印一次 2-3 行；歷史不到 3 天或 3 個 session 時只說「已安裝」，每 6 小時自動重試 | 0 |
| 讀檔防護（`read-dedup.py`） | 同 session 內擋下未變動檔案的重複讀取 | 0 |

在 `~/.claude/oct-toolkit.json` 關閉任一項（預設全為 `true`）：

```json
{"auto_wake": false, "nap_nudge": false, "clear_reminder": false, "memory_tidy": false, "cost_line": false, "first_checkup": false, "memory_check": false, "nudge_dynamic": false}
```

## 首次健檢

不問問題。安裝後第一個 session，外掛用腳本（不呼叫模型、不花錢）掃過去 7 天的對話紀錄，印一次，例如：

```
oct-toolkit checkup (7 days): about $41 API-equivalent across 38 sessions; 63% of it is re-reading long conversations (CR, cache reads).
MEMORY.md is 112 lines (~2.4k tokens) - over the 80-line limit; napping about every 24 turns pays off for you (sonnet-5-5).
For details run /oct-checkup.
```

歷史少於 3 天或 3 個 session 時只印「已安裝，累積幾天後給第一份報告」，之後自動重試。金額是 API 牌價換算，不是帳單。隨時可用 `/oct-checkup report` 重看。

## 淨省錢與滾動基準

nap 要划算，丟掉的 context 必須比新 session 的冷啟動更值錢。外掛從你自己的紀錄量這兩件事（只取無 nap 的 `cli` session，排除 nap／auto-wake 的 session），以每個模型最新 `baseline_window_sessions`（預設 30）個、不超過 `baseline_window_days`（預設 60）天的移動平均，背景每 6 小時更新：

- 冷啟動 = session 前 3 次呼叫的 cache write 成本平均（依實際 1h/5m 費率）+ 檢查點（約 2k token 的 cache write）；冷啟動大小 = 這 3 次呼叫後的 context。
- 預估剩餘呼叫數 = 窗口內比目前更長的 session 的（長度 − 目前呼叫數）中位數；少於 5 個樣本時保守取 `nap_fallback_remaining`（10）。
- 淨省 =（目前 context − 冷啟動大小 − 檢查點）× cache read 單價 × 剩餘呼叫數 − 冷啟動成本。

`/oct-nap` 以 `estimate:` 行顯示（可能為負，會照實說）；提醒只在淨省 > `nudge_min_net_usd` 時出現。該模型可比 session 少於 `baseline_min_sessions`（5）時不顯示金額。在設定檔明確寫 `nudge_growth_tokens` 會保留舊的固定成長觸發。`/oct-checkup baseline` 印出你的數字與損益兩平 context。

## 記憶檢查

每次 session 開始，腳本檢查目前專案的 `MEMORY.md`（`~/.claude/projects/<slug>/memory/`，slug = 工作目錄中每個非英數字元換成 `-`）。超過 `memory_max_lines`（80）或 `memory_max_tokens`（3000，約 4 字元 1 token），或距上次檢查超過 `memory_check_days`（30）天，就提醒一行，同一次觸發只提醒一次。`/oct-checkup memory` 派背景 Sonnet 代理（唯讀）掃描重複、過期、矛盾，列清單由你點選；沒選的不動，過期筆記移到 `memory/archive/`，絕不自動刪除。

其他數值設定：`baseline_window_sessions`、`baseline_window_days`、`baseline_min_sessions`、`nudge_min_net_usd`、`nap_fallback_remaining`、`memory_max_lines`、`memory_max_tokens`、`memory_check_days`、`checkup_min_days`、`checkup_min_sessions`。支援 `CLAUDE_CONFIG_DIR`。

狀態列省錢徽章：以「沒有 oct 的估計花費（實際花費＋估計省下）」為基準，顯示最近 5 小時（與 Claude 5h 額度視窗一致）的百分比，括號內為 7 天：`🐙 -12% 5h (7d -8%)`。`-12%` 代表比沒有 oct 少花約 12%；`~0%` 代表不到 1%。此為反事實估計、不會是負值，所以沒有 `+`。樣本不足時退回：5h 內少於 10 回合或花費低於 $0.05 只顯示 7 天（`🐙 -8% 7d`）；7 天少於 50 回合或省下低於 $0.01 則隱藏徽章，並於每週一句話說明主因（也可用 `/oct-checkup why`）。關閉：`/oct-pulse savings off` 或 `"savings_badge": false, "weekly_savings": false`。

## 權限

外掛無法附帶權限規則，第一次執行外掛的 Python 腳本時 Claude Code 會詢問一次；選「永遠允許」，或在自己的設定加入 `Bash(python3 *)`。

## 授權

MIT

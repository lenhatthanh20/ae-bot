# AIGold: Plan cuối (đã gộp 4 review)

> Ngày: 2026-10-29 · Phạm vi: v1, dùng cá nhân, chạy demo trước

> **Cập nhật 2026-10-29:** Đã bỏ API mode. Bridge chỉ còn `AI_MODE=cli|fake`; `claude -p` (subscription) là đường chính, chạy với `--safe-mode --tools ""`. Các chỗ nhắc "API key là đường chính" bên dưới đã lỗi thời. Rủi ro điều khoản ở §2.1 vẫn còn nguyên: anh đã chấp nhận.

---

## 1. Tóm tắt

**Kiến trúc cuối.** Giữ ý gốc: EA MQL5 chạy trong MT5 (bản macOS, chạy trên Wine) gọi `WebRequest` tới một bridge Python stdlib ở `127.0.0.1:18765`. Bridge hỏi Claude qua **API key, đây là đường chính**, rồi trả về đúng một dòng. AI chỉ đề xuất, EA là bên quyết định và đặt lệnh.

**Các thay đổi chính so với plan gốc:**

1. **AI không trả giá SL/TP nữa.** AI chỉ trả `action; sl_atr; tp_rr; confidence`. EA tự tính giá SL/TP từ bid/ask ngay lúc gửi lệnh, nên không bị lỗi tính toán của model và không dùng giá cũ.
2. **Đổi cách đánh giá.** Bỏ tiêu chí "có lãi sau 2-4 tuần" vì mẫu đó quá nhỏ để kết luận gì. Thay bằng **shadow mode**: AI được hỏi ở mọi bar hợp lệ, và `scoring.py` chấm điểm offline. Cổng đi live được chốt trước: n ≥ 100, khoảng tin cậy 95% của R trung bình lớn hơn 0, và thắng baseline chọn hướng ngẫu nhiên.
3. **`claude -p` (dùng subscription) bị hạ xuống chỉ để smoke test.** Lý do: bot chạy liên tục là vùng xám về điều khoản, CLI tải theo cả `~/.claude` của anh, và có báo cáo (nguồn thứ cấp) là CLI dùng một pool credit riêng.
4. **Thêm các lớp an toàn bắt buộc:** chặn chạy trên tài khoản live, kill switch, mỗi bar chỉ gọi AI một lần (vẫn đúng sau khi khởi động lại), giới hạn lỗ ngày tính theo equity, kill khi drawdown vượt ngưỡng, rủi ro tối đa mỗi lệnh, lọc tin (Calendar), khung giờ tính theo GMT, đóng lệnh theo thời gian và đóng trước cuối tuần.
5. **Phase 0 là cổng bắt buộc.** Chưa có gì chứng minh `WebRequest` tới `127.0.0.1:18765` chạy được trong Wine trên Mac. Phải test trước khi viết thêm bất cứ thứ gì.

---

## 2. Kết quả review

### 2.1 Những gì thay đổi

| Mức | Vấn đề | Cách sửa | Nguồn |
|---|---|---|---|
| Chặn | Tiêu chí "có lãi sau 2-4 tuần" không đo được edge: chỉ khoảng 20-50 lệnh, sai số chuẩn của R trung bình ≈ 0.2R | Cổng chốt trước: n ≥ 100, CI dưới > 0, mean > +0.15R, thắng random (p < 0.05), maxDD < 10R | risk (công thức SE) |
| Chặn | Không có baseline, không chấm được các tín hiệu bị lọc hay NONE | Shadow mode + `scoring.py` + baseline random-direction + baseline đứng ngoài (0R) | risk |
| Chặn | Chưa có bằng chứng công khai nào cho thấy LLM đọc OHLC/EMA/RSI có edge trên XAUUSD | Coi v1 là dự án đo lường. Kết quả "không có edge" cũng là kết quả hợp lệ | risk (dựa trên prior, chưa kiểm chứng) |
| Lớn | `claude -p` cho bot chạy 24/5: OAuth dành cho "ordinary individual usage", Anthropic có thể enforce mà không báo trước | Đường chính là API key, CLI chỉ để smoke test | ai (code.claude.com/docs/en/legal-and-compliance), stack (nguồn thứ cấp về credit pool, chưa kiểm chứng) |
| Lớn | `claude -p` tải cả CLAUDE.md, hooks, skills của anh. Còn `--bare` thì không dùng được login subscription | Chạy CLI từ thư mục rỗng, dùng `--system-prompt`, `--json-schema`. Sau Phase 1 thì chuyển sang API | ai (code.claude.com/docs/en/headless) |
| Lớn | WebRequest tới port 18765 trong Wine chưa được chứng minh. Docs nói port được chọn theo giao thức | Phase 0: script `PingTest`. Nếu fail thì thử port 80 → pf redirect → VPS Windows | mt5, stack (mql5.com/en/docs/network/webrequest) |
| Lớn | WebRequest chạy đồng bộ (blocking), Claude mất 5-30s | Timeout 60000 ms, mỗi bar gọi một lần. Sau khi có phản hồi, kiểm lại bar và độ trôi giá ≤ 0.3 ATR | mt5, stack, risk (docs) |
| Lớn | AI trả giá tuyệt đối thì dễ sai số học và dễ dùng giá cũ | AI trả `sl_atr`, `tp_rr`; EA tính giá | ai |
| Lớn | SL 0.5 ATR quá sát với XAUUSD M15 (cỡ spread × 5-15) | SL 1.0-2.5 ATR, RR 1.5-3, TP ≤ 4 ATR, SL ≥ 6× spread | risk |
| Lớn | Thiếu chi tiết thực thi lệnh: filling mode, stops/freeze level, lot step, normalize, retcode | `CTrade` + `SetTypeFillingBySymbol`, normalize theo tick size, clamp lot, chỉ chấp nhận DONE/PLACED, không retry | mt5, stack |
| Lớn | Indicator handle và vấn đề bar đang hình thành | Tạo handle trong `OnInit`, `CopyBuffer` từ shift 1 (chỉ lấy bar đã đóng) | mt5 |
| Lớn | Restart/reconnect gây gọi AI 2 lần hoặc vào 2 lệnh; bộ đếm nằm trong RAM | Lưu GlobalVariable `lastbar` (đánh dấu *trước khi* gọi), bỏ bar nếu đã trễ hơn 60s, bộ đếm lấy từ history | mt5, risk |
| Lớn | Lỗ ngày tính theo balance thì bỏ sót phần lỗ thả nổi | Dùng equity so với equity đầu ngày (lưu GlobalVariable) | mt5, risk |
| Lớn | Không có live lock và kill switch | `InpAllowLive=false` → INIT_FAILED trên tài khoản real; nút Algo Trading; file `HALT` cho bridge | risk, stack |
| Lớn | Không có lọc tin trên một mã chạy theo tin | Calendar API: tin HIGH của USD ±30 phút. Nếu không đọc được calendar thì không vào lệnh | risk |
| Lớn | "08-20 giờ server" mơ hồ, chưa xử lý cuối tuần | Khung giờ theo GMT (07-17), đóng lệnh thứ Sáu lúc 19:00 GMT, giữ lệnh tối đa 16 bar | risk |
| Lớn | Không có model, chi phí hay trần ngân sách | Chọn model qua env, log `usage`, có `DAILY_USD_CAP`, đặt spend limit trên Console | ai |
| Lớn | Gửi `temperature`/`top_p` sẽ bị 400 trên mọi model kể từ 2026-10-21 | Không gửi sampling params. Dùng structured output + `effort` | ai (claude-api skill) |
| Lớn | Format một dòng dễ vỡ, không chống được phản hồi cũ | Structured output phía API; bridge format số với dấu `.`; echo lại `bar` để EA đối chiếu | ai, stack, mt5 |
| Lớn | Mac ngủ hoặc App Nap làm dừng EA mà không báo | `caffeinate -is` khi test; VPS trước khi lên live | stack |
| Nhỏ | Rủi ro mỗi lệnh tính bằng tiền | `OrderCalcProfit` ≤ 1% balance | risk |
| Nhỏ | Log chưa đủ để chấm điểm hay replay | Log đầy đủ payload, `prompt_sha`, model, usage, latency; xoay file theo tháng | risk, stack |
| Nhỏ | Replay lịch sử bị nhiễm look-ahead (model đã "nhớ" giá vàng) | Chỉ dữ liệu forward mới được tính là bằng chứng | risk |
| Nhỏ | Secrets | API key để trong Keychain, đặt spend limit trên Console | stack |
| Nhỏ | Test | `unittest` cho các hàm thuần + `AI_MODE=fake` để test EA từ đầu đến cuối mà không tốn tiền | stack |

### 2.2 Đã bỏ hoặc hoãn, kèm lý do

| Đề xuất | Quyết định |
|---|---|
| Tự dò hậu tố symbol (`ResolveSymbol`) | Bỏ. Anh nhập đúng tên symbol ở Phase 0, ít bất ngờ hơn |
| Gọi bất đồng bộ kiểu 202 + poll | Bỏ. M15 + SL/TP gắn sẵn trên lệnh nên blocking chấp nhận được |
| Header `X-Token` | Bỏ. Bridge chỉ bind 127.0.0.1 trên Mac cá nhân, đã có `DAILY_USD_CAP` |
| launchd | Hoãn. `caffeinate` trong một pane herdr là đủ cho prototype |
| `pydantic` / `messages.parse` | Bỏ. Dùng JSON schema thô với `messages.create`, bớt một dependency |
| Prompt caching | Bỏ. System prompt ngắn, phần CSV thay đổi mỗi lần gọi |
| Dừng sau 2 lệnh lỗ liên tiếp, trần tuần 5% | Bỏ ở v1. Với lot 0.01 thì 3 lệnh/ngày + 2%/ngày + 1%/lệnh + kill khi DD 10% là đủ |
| Validate range trùng lặp ở cả Python và EA | Bỏ. EA là nơi duy nhất quyết định; `scoring.py` dùng cùng giá trị mặc định |
| Python MetaTrader5 chạy trong Wine (siliconmetatrader5/mt5linux) | Bỏ. Mong manh, nhiều dependency |
| Bridge qua file hoặc socket MQL5 | Chỉ dùng nếu Phase 0 fail cả port 80 lẫn pf |
| Khối HTF (H1/H4), ảnh chart | Câu hỏi mở / v2 |
| Baseline B1 (luật EMA), forward return cho NONE | Tuỳ chọn, thêm sau nếu cần |
| Server-side refusal fallback | Bỏ. Refusal → NONE là kết quả an toàn cho bot trade |

---

## 3. Kiến trúc cuối

```
+------------------ MT5 macOS app (Wine) -------------------+
| AIGold.mq5 (chart XAUUSD, M15)                            |
|                                                           |
|  every tick : ManagePosition() -> time exit / Friday close|
|  new bar    : mark bar (GlobalVariable)                   |
|               PreCheck() -> skip with code, no AI call    |
|               BuildBody() 100 closed bars + bid/ask/atr   |
|               WebRequest POST, timeout 60 s  -------------+-----+
|               check echo bar, bar unchanged, drift        |     |
|               Validate() -> SL/TP from live bid/ask       |     |
|               CTrade Buy/Sell  (or DRYRUN print)          |     |
+-----------------------------------------------------------+     |
                     ^  "BUY;1.50;2.00;74;1767225600"             |
                     |                                            v
+------------- bridge/server.py 127.0.0.1:18765 -------------------+
| POST /decide : parse -> HALT file? -> USD cap? -> ask Claude     |
|                -> to_line() -> append logs/decisions-YYYY-MM.jsonl
| GET /health  : "ok"                                              |
| AI_MODE = api (default) | cli (smoke test) | fake (EA tests)     |
+-------------------------------+----------------------------------+
                                | HTTPS
                     Anthropic Messages API (claude-opus-5-5,
                     effort low, JSON schema output)
```

**Luồng xử lý mỗi bar:**

1. **Mọi tick:** nếu đang có lệnh của EA và đã giữ ≥ 16 bar, hoặc đã tới thứ Sáu ≥ 19:00 GMT, thì đóng lệnh.
2. **Bar mới:** so `iTime(sym, tf, 0)` với GlobalVariable `lastbar`. Nếu trùng thì thoát. Nếu khác thì ghi lại **trước khi** gọi AI. Nếu bar đã mở quá 60s (vừa attach EA hoặc Mac vừa thức dậy) thì bỏ bar này.
3. **PreCheck theo thứ tự:** Algo Trading tắt (chỉ khi live) → DD vượt ngưỡng → đang có lệnh → ngoài khung giờ GMT hoặc cuối tuần → spread quá cao → đã đủ số lệnh trong ngày → chạm giới hạn lỗ ngày → đang trong vùng tin. Lỗi nào cũng in mã `SKIP <code>` và **không gọi AI** (tiết kiệm token).
4. **Gửi request:** dòng đầu là `bar=..;sym=..;tf=..;bid=..;ask=..;atr=..`, tiếp theo là header CSV và 100 bar đã đóng, cũ nhất trước.
5. **Bridge:** nếu có file `HALT` hoặc đã vượt trần USD thì trả NONE. Nếu không thì gọi Claude với structured output, kiểm `stop_reason`, kiểm hình dạng dữ liệu, và trả `ACTION;sl_atr;tp_rr;conf;bar`. Mọi lỗi đều trả `NONE;0;0;0;bar`. Mọi lần gọi đều được log.
6. **EA nhận phản hồi:** phải đủ 5 trường và `bar` echo phải khớp. Nếu action không phải BUY/SELL thì dừng. Bar phải chưa đổi và giá trôi không quá 0.3 ATR.
7. **Validate:** confidence, khoảng SL theo ATR, RR, TP theo ATR, SL ≥ 6× spread, stops/freeze level, rủi ro bằng tiền ≤ 1% balance. Sau đó tính SL/TP từ ask (BUY) hoặc bid (SELL) và normalize theo tick size.
8. **Gửi lệnh:** nếu `InpDryRun=true` thì chỉ in `DRYRUN ...`. Nếu không thì gửi `CTrade.Buy/Sell` kèm SL/TP và log retcode, giá. Không retry.

---

## 4. Tech stack

| Thành phần | Lựa chọn | Phiên bản | Lý do |
|---|---|---|---|
| Terminal | MetaTrader 5 bản macOS của MetaQuotes (Wine) | Bản mới nhất từ metatrader5.com; xem build ở Help > About | Bản chính thức, có sẵn MetaEditor |
| Môi trường live | Windows VPS (MT5 + bridge cùng máy) | Chọn khi tới Phase 5 | Mac ngủ hoặc cập nhật là bot dừng |
| EA | MQL5, một file, `#include <Trade/Trade.mqh>` (CTrade) | Theo terminal | Không phụ thuộc thư viện ngoài |
| Indicator | Có sẵn: `iMA` (EMA 20/50/200), `iRSI` 14, `iATR` 14 | — | Handle tạo một lần trong `OnInit` |
| Lưu trạng thái EA | GlobalVariables của terminal | — | Không mất khi restart |
| Lọc tin | MQL5 Calendar API | — | Có sẵn trong terminal, không dùng được trong Tester (ở đây không ảnh hưởng) |
| Bridge | Python stdlib `http.server.ThreadingHTTPServer` | Python 3.12+ (code cũng chạy được trên 3.9) | Một endpoint, không cần FastAPI |
| AI SDK | `anthropic` (Python SDK chính thức) | Bản mới nhất; pin bằng `uv pip freeze > requirements.txt` | Có sẵn retry, timeout, typed errors |
| Model | `claude-opus-5-5`, `effort: low` | — | Model mặc định hiện tại. So với Sonnet/Haiku ở Phase 3, anh chọn (§9) |
| Định dạng output | Structured output: `output_config.format` json_schema | — | Không phụ thuộc vào việc model tự giữ đúng format |
| AI (prototype) | Claude Code CLI `claude -p` | Bản anh đang cài | Chỉ để smoke test, không dùng cho shadow mode |
| Python env | `uv` (brew) + `.venv` | Bản mới nhất | Nhanh, không dính tới npm/pnpm |
| Secrets | macOS Keychain (`security`) | — | Key không nằm trong repo |
| Test | `unittest` (stdlib) | — | Test hàm thuần + chế độ fake |
| Chấm điểm | `tools/scoring.py` (stdlib: csv, json, random, statistics, bisect) | — | Không cần pandas |
| Giữ máy thức | `caffeinate -is` | Có sẵn trên macOS | Đủ cho demo |

---

## 5. Cấu hình

### 5.1 EA inputs (`AIGold.mq5`)

Đây là nguồn duy nhất cho mọi con số rủi ro.

| Input | Mặc định | Ghi chú |
|---|---|---|
| `InpSymbol` | `XAUUSD` | Đúng tên theo broker (vd. `XAUUSD.m`, `GOLD`). EA phải gắn vào chart của symbol này |
| `InpTimeframe` | `PERIOD_M15` | Chỉ dùng M15 hoặc H1. Không trộn hai khung trong một mẫu đánh giá |
| `InpUrl` | `http://127.0.0.1:18765/decide` | Phải whitelist `http://127.0.0.1:18765` |
| `InpTimeoutMs` | `60000` | Lớn hơn timeout của bridge |
| `InpDryRun` | `true` | `false` chỉ dùng ở Phase 2b (demo) và Phase 5 |
| `InpAllowLive` | `false` | Trên tài khoản real mà để false thì EA từ chối khởi động |
| `InpMagic` | `20261029` | Mỗi chart một magic riêng |
| `InpLots` | `0.01` | Bị clamp theo min/step/max |
| `InpStartHourGMT` / `InpEndHourGMT` | `7` / `17` | London mở cửa → sáng New York |
| `InpFridayCloseGMT` | `19` | Đóng mọi lệnh của EA vào thứ Sáu |
| `InpMaxHoldBars` | `16` | M15 = 4 giờ, H1 nên đặt 8 |
| `InpMaxSpreadPts` | `40` | Broker 2 chữ số = $0.40. **Xem dòng `digits/point` mà EA in lúc khởi động** |
| `InpMinConfidence` | `70` | Chưa được hiệu chỉnh, xem §8 |
| `InpMaxTradesPerDay` | `3` | Đếm từ history theo magic |
| `InpMaxDailyLossPct` | `2.0` | Equity so với equity đầu ngày |
| `InpMaxDrawdownPct` | `10.0` | Equity so với đỉnh. Sau khi chạm phải reset GV `AIGold_<magic>_peak` bằng tay |
| `InpMaxRiskPct` | `1.0` | Số tiền mất nếu chạm SL, tính bằng `OrderCalcProfit` |
| `InpSlMinAtr` / `InpSlMaxAtr` | `1.0` / `2.5` | |
| `InpMinRR` / `InpMaxRR` | `1.5` / `3.0` | |
| `InpMaxTpAtr` | `4.0` | H1 có thể nâng lên 5 |
| `InpMinSlSpreads` | `6.0` | SL ≥ 6× spread |
| `InpMaxDriftAtr` | `0.3` | Mức trôi giá tối đa trong lúc chờ AI |
| `InpSlippagePts` | `30` | Deviation |
| `InpNewsFilter` / `InpNewsMinutes` | `true` / `30` | Tin HIGH của USD ±30 phút |
| `InpBars` | `100` | Số bar đã đóng gửi cho AI |

### 5.2 Biến môi trường của bridge

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `AI_MODE` | `fake` trong code, `api` trong `run.sh` | `api` \| `cli` \| `fake` |
| `BRIDGE_MODEL` | `claude-opus-5-5` | Thay thế được bằng `claude-sonnet-5-5` hoặc `claude-haiku-5-5` |
| `BRIDGE_EFFORT` | `low` | `low` \| `medium` |
| `DAILY_USD_CAP` | `3` | Vượt trần thì trả NONE (tính theo ngày UTC) |
| `PORT` | `18765` | Đổi port thì phải sửa cả `InpUrl` và whitelist |
| `ANTHROPIC_API_KEY` | — | `run.sh` đọc từ Keychain |
| `CLAUDE_BIN` | `claude` | Đường dẫn tuyệt đối nếu chạy dưới launchd |
| `FAKE_ACTION` | `BUY` | Chỉ dùng ở fake mode: `BUY` \| `SELL` \| `NONE` |

---

## 6. Risk guards

| # | Guard | Nơi thực thi |
|---|---|---|
| 1 | Chặn tài khoản live (`InpAllowLive=false` → INIT_FAILED) | EA `OnInit` |
| 2 | Kill switch: nút **Algo Trading** của MT5 (EA kiểm `TERMINAL_TRADE_ALLOWED`) | MT5 + EA `PreCheck` |
| 3 | Kill switch: `touch HALT` → bridge luôn trả NONE | Bridge `decide` |
| 4 | `InpDryRun=true` mặc định | EA `Execute` |
| 5 | Mỗi bar gọi AI tối đa một lần, vẫn đúng sau restart (GV `lastbar` ghi trước khi gọi + `GlobalVariablesFlush`) | EA `OnTick` |
| 6 | Bỏ bar nếu bar đã mở > 60s | EA `OnTick` |
| 7 | Một lệnh một lúc (symbol + magic; tài khoản netting thì bất kỳ lệnh nào trên symbol) | EA `PreCheck` |
| 8 | Khung giờ GMT, không vào lệnh thứ Bảy/Chủ nhật | EA `PreCheck` |
| 9 | Spread ≤ `InpMaxSpreadPts` | EA `PreCheck` |
| 10 | Lọc tin HIGH USD ±30 phút; lỗi calendar thì không vào lệnh | EA `NewsBlackout` |
| 11 | Số lệnh/ngày lấy từ history (không lấy từ RAM) | EA `TradesToday` |
| 12 | Lỗ ngày tính theo equity (GV lưu equity đầu ngày) | EA `DailyLossHit` |
| 13 | Kill khi drawdown 10% so với đỉnh equity (GV lưu đỉnh) | EA `PreCheck` |
| 14 | Bridge lỗi, timeout, HTTP ≠ 200, sai format hoặc `bar` echo lệch → không vào lệnh | EA `OnTick` + bridge |
| 15 | Bar đổi hoặc giá trôi > 0.3 ATR trong lúc chờ AI → bỏ | EA `OnTick` |
| 16 | Confidence ≥ 70 | EA `Validate` |
| 17 | SL 1.0-2.5 ATR, RR 1.5-3, TP ≤ 4 ATR, SL ≥ 6× spread | EA `Validate` |
| 18 | Stops/freeze level của broker | EA `Validate` |
| 19 | Rủi ro mỗi lệnh ≤ 1% balance (`OrderCalcProfit`) | EA `Validate` |
| 20 | SL/TP bắt buộc, gửi trong cùng request; giá normalize theo tick; lot clamp | EA `Validate` / `Execute` |
| 21 | Filling theo symbol, deviation 30 điểm, không retry | EA `OnInit` / `Execute` |
| 22 | Đóng theo thời gian (16 bar) và đóng thứ Sáu 19:00 GMT (luật cố định, không hỏi AI) | EA `ManagePosition` |
| 23 | Bridge chỉ bind `127.0.0.1` | Bridge |
| 24 | `DAILY_USD_CAP` + spend limit tháng trên Console | Bridge + Anthropic Console |
| 25 | API key trong Keychain, không bao giờ nằm trong repo hay log | `run.sh` |

---

## 7. Hướng dẫn implement chi tiết

### Cấu trúc project

```
~/project/ae/aigold/
  mt5/AIGold.mq5        EA
  mt5/PingTest.mq5      Phase 0 script
  mt5/ExportM1.mq5      M1 export for scoring
  bridge/server.py      bridge (single file)
  bridge/prompt.md      system prompt = anh's rules
  bridge/test_server.py unit tests
  tools/scoring.py      offline evaluation
  tools/compare_models.py
  logs/                 decisions-YYYY-MM.jsonl (gitignored)
  run.sh
  .gitignore
```

```bash
mkdir -p ~/project/ae/aigold/{mt5,bridge,tools,logs}
cd ~/project/ae/aigold
printf 'logs/\nHALT\n.venv/\nbridge/empty/\n__pycache__/\n' > .gitignore
# MT5 data folder. Confirm the path in MT5: File > Open Data Folder
export MT5="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5"
ls "$MT5"   # must list Experts, Scripts, Files
```

---

### Phase 0: Cài đặt và các cổng kiểm tra (1 buổi)

**Các bước:**

1. Cài MT5 macOS từ metatrader5.com. Mở **tài khoản demo của chính broker anh định dùng**. Demo của MetaQuotes có spread không giống thật.
2. Tìm tên symbol: Market Watch → chuột phải → Symbols → tìm `XAU` / `GOLD`. Ghi lại tên chính xác.
3. Bật whitelist: **Tools > Options > Expert Advisors** → tick *Allow algorithmic trading* và *Allow WebRequest for listed URL* → thêm `http://127.0.0.1:18765`.
4. Tạo `mt5/PingTest.mq5`:

```mql5
// PingTest.mq5 - Phase 0 gate: WebRequest to the Mac host and Calendar under Wine.
#property script_show_inputs
input string InpUrl = "http://127.0.0.1:18765/";

void OnStart()
{
   char data[], res[];
   string hdr;
   ResetLastError();
   int code = WebRequest("GET", InpUrl, "", 5000, data, res, hdr);
   PrintFormat("WebRequest code=%d err=%d body=%.60s", code, GetLastError(), CharArrayToString(res));

   MqlCalendarValue v[];
   datetime now = TimeTradeServer();
   ResetLastError();
   bool ok = CalendarValueHistory(v, now - 7 * 86400, now, NULL, "USD");
   PrintFormat("Calendar ok=%s values=%d err=%d", ok ? "true" : "false", ArraySize(v), GetLastError());
   PrintFormat("TimeGMT=%s TimeTradeServer=%s", TimeToString(TimeGMT()), TimeToString(now));
}
```

5. Chạy server test và deploy script:

```bash
cd "$(mktemp -d)" && python3 -m http.server 18765 --bind 127.0.0.1   # leave running
# other pane:
cp ~/project/ae/aigold/mt5/PingTest.mq5 "$MT5/Scripts/"
```

6. Trong MT5, nhấn F4 để mở MetaEditor, mở `PingTest.mq5`, nhấn F7 để compile. Quay lại MT5, kéo script vào chart XAUUSD và xem tab **Experts**.
7. **Nếu WebRequest fail** (code = -1), làm lần lượt:
   - Err 4014 thường có nghĩa URL chưa có trong whitelist (theo báo cáo trên forum). Kiểm tra lại chính tả, thử bỏ dấu `/` ở cuối.
   - Err 5200-5203 là lỗi kết nối hoặc timeout. Thử port 80: `python3 -m http.server 80 --bind 127.0.0.1`. macOS bản mới có thể cho bind port < 1024 mà không cần root (chưa kiểm chứng). Nếu bị từ chối: `echo "rdr pass on lo0 inet proto tcp from any to 127.0.0.1 port 80 -> 127.0.0.1 port 18765" | sudo pfctl -ef -`. Sau đó whitelist `http://127.0.0.1`, đặt `InpUrl=http://127.0.0.1/decide`.
   - Vẫn fail thì chuyển sang VPS Windows chạy cả MT5 và bridge, kiến trúc giữ nguyên. Socket MQL5 hoặc bridge qua file chỉ là phương án cuối.
8. **API key:** đăng nhập platform.claude.com → tạo workspace `aigold` → tạo key → **đặt spend limit tháng** (vd. $50). Lưu key vào Keychain:

```bash
security add-generic-password -a "$USER" -s aigold-anthropic -w   # prompts for the key
```

**Xong khi:**
- Log hiện `WebRequest code=200`.
- Có dòng `Calendar ok=true values>0`. Nếu không có thì đặt `InpNewsFilter=false` và chỉ được chạy demo.
- Anh đã ghi lại: tên symbol, độ lệch GMT của server, và đã có key trong Keychain.

---

### Phase 1: Bridge, test và curl (1-2 buổi)

**`bridge/prompt.md`:** anh điền phần *Rules*. Prompt viết bằng tiếng Anh vì model là người đọc.

```markdown
You are a rules-based filter for XAUUSD intraday signals. You check the rules below
against the data. You do not forecast. When any rule is not fully met, answer NONE.

## Data
- First line: bar (unix server time of the new bar), sym, tf, bid, ask,
  atr (ATR14 of the last closed bar).
- Then CSV rows of CLOSED bars, oldest first. The last row is the last closed bar.
  The current price is bid/ask, not the last close.
- Prices are USD per ounce. Use only numbers from the data. Do not invent levels.

## Rules (owner fills these in; each must be checkable from the data)
1. Trend: BUY only if close > ema200 and ema20 > ema50 on the last row.
   SELL only if close < ema200 and ema20 < ema50 on the last row.
2. Entry: <rule, e.g. the last row's low touched ema20 and the bar closed above it; mirror for SELL>.
3. Momentum: rsi14 on the last row between 40 and 70 for BUY, between 30 and 60 for SELL.
4. <more rules>
Default answer: NONE.

## Output
- action: BUY, SELL or NONE.
- sl_atr: stop-loss distance in ATR units, from 1.0 to 2.5. Put it beyond the nearest
  swing high/low in the data.
- tp_rr: take-profit distance as a multiple of the stop distance, from 1.5 to 3.0.
- confidence: 0-100, how fully the rules are met.
- reason: at most 200 characters; cite the row values you used.
For NONE, set sl_atr 0, tp_rr 0, confidence 0.
```

**`bridge/server.py`:**

```python
"""AIGold bridge: the EA posts market data, Claude proposes, the EA decides.

The reply is always HTTP 200 with one line: ACTION;sl_atr;tp_rr;confidence;bar
ACTION is BUY, SELL or NONE. Any error, HALT file or budget stop gives NONE.
"""
import hashlib
import json
import math
import os
import pathlib
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
PROMPT = (ROOT / "prompt.md").read_text(encoding="utf-8")
PROMPT_SHA = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
LOG_DIR = ROOT.parent / "logs"
HALT_FILE = ROOT.parent / "HALT"
EMPTY_DIR = ROOT / "empty"  # cwd for claude -p, so no project CLAUDE.md is loaded

MODE = os.environ.get("AI_MODE", "fake")
MODEL = os.environ.get("BRIDGE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("BRIDGE_EFFORT", "low")
DAILY_USD_CAP = float(os.environ.get("DAILY_USD_CAP", "3"))
PORT = int(os.environ.get("PORT", "18765"))

# USD per 1M tokens (input, output). Re-check current prices before trusting cost numbers.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "NONE"]},
        "sl_atr": {"type": "number"},
        "tp_rr": {"type": "number"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["action", "sl_atr", "tp_rr", "confidence", "reason"],
    "additionalProperties": False,
}


def parse_request(body):
    """First line: key=value pairs split by ';'. The rest is CSV for the model."""
    head = body.split("\n", 1)[0]
    meta = dict(kv.split("=", 1) for kv in head.strip().split(";") if "=" in kv)
    int(meta["bar"])
    for key in ("bid", "ask", "atr"):
        if not math.isfinite(float(meta[key])):
            raise ValueError(f"bad {key}")
    return meta


def to_line(decision, bar):
    """Shape check only. Range rules live in the EA (single source of truth)."""
    none = f"NONE;0;0;0;{bar}"
    if not isinstance(decision, dict):
        return none
    action = str(decision.get("action", "")).upper()
    if action not in ("BUY", "SELL"):
        return none
    try:
        sl_atr = float(decision["sl_atr"])
        rr = float(decision["tp_rr"])
        conf = int(decision["confidence"])
    except (KeyError, TypeError, ValueError):
        return none
    if not (math.isfinite(sl_atr) and math.isfinite(rr) and sl_atr > 0 and rr > 0 and 0 <= conf <= 100):
        return none
    return f"{action};{sl_atr:.2f};{rr:.2f};{conf};{bar}"


def ask_fake(payload):
    action = os.environ.get("FAKE_ACTION", "BUY")
    return {"action": action, "sl_atr": 1.5, "tp_rr": 2.0, "confidence": 80, "reason": "fake"}, {"usd": 0.0}


_client = None


def ask_api(payload):
    global _client
    import anthropic  # only needed in api mode

    if _client is None:
        # timeout x (retries + 1) must stay under the EA timeout (60 s)
        _client = anthropic.Anthropic(timeout=25.0, max_retries=1)
    r = _client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=PROMPT,
        messages=[{"role": "user", "content": payload}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    pin, pout = PRICES.get(MODEL, (0.0, 0.0))
    usage = {
        "in": r.usage.input_tokens,
        "out": r.usage.output_tokens,
        "stop": r.stop_reason,
        "usd": (r.usage.input_tokens * pin + r.usage.output_tokens * pout) / 1e6,
    }
    if r.stop_reason != "end_turn":  # refusal or max_tokens -> NONE
        return None, usage
    text = next(b.text for b in r.content if b.type == "text")
    return json.loads(text), usage


def ask_cli(payload):
    # Prototype only. Still loads ~/.claude (global CLAUDE.md, hooks); --bare would drop the subscription login.
    EMPTY_DIR.mkdir(exist_ok=True)
    cmd = [os.environ.get("CLAUDE_BIN", "claude"), "-p", "--model", MODEL,
           "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--system-prompt", PROMPT]
    r = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=45, cwd=EMPTY_DIR)
    out = json.loads(r.stdout)
    return out.get("structured_output"), {"usd": out.get("total_cost_usd") or 0.0}


ASKERS = {"fake": ask_fake, "api": ask_api, "cli": ask_cli}


def log_path(now):
    return LOG_DIR / f"decisions-{now:%Y-%m}.jsonl"


def spent_today(now):
    # shortcut: re-reads the monthly log each call; fine at ~50 calls/day, move to a counter if it gets slow
    path, day, total = log_path(now), now.strftime("%Y-%m-%d"), 0.0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec["ts"].startswith(day):
                total += (rec.get("usage") or {}).get("usd") or 0.0
    return total


def decide(body, ask=None):
    now = datetime.now(timezone.utc)
    rec = {"ts": now.isoformat(timespec="seconds"), "mode": MODE, "model": MODEL,
           "effort": EFFORT, "prompt_sha": PROMPT_SHA}
    bar, t0 = "0", time.monotonic()
    try:
        meta = parse_request(body)
        bar = meta["bar"]
        rec.update(meta)
        if HALT_FILE.exists():
            rec["error"] = "HALT"
        elif spent_today(now) >= DAILY_USD_CAP:
            rec["error"] = "USD_CAP"
        else:
            decision, usage = (ask or ASKERS[MODE])(body)
            rec.update(decision=decision, usage=usage)
    except Exception as e:  # any failure must answer NONE, never break the EA call
        rec["error"] = repr(e)[:300]
    line = f"NONE;0;0;0;{bar}" if "error" in rec else to_line(rec.get("decision"), bar)
    rec.update(line=line, latency_ms=int((time.monotonic() - t0) * 1000), payload=body)
    LOG_DIR.mkdir(exist_ok=True)
    with log_path(now).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return line


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._send(200, "ok")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path != "/decide":
            return self._send(404, "not found")
        size = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(size).decode("utf-8", "replace")
        self._send(200, decide(body))

    def _send(self, code, text):
        data = (text + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"bridge 127.0.0.1:{PORT} mode={MODE} model={MODEL} effort={EFFORT} prompt={PROMPT_SHA}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
```

**`bridge/test_server.py`:**

```python
import json
import pathlib
import tempfile
import unittest

import server

BODY = ("bar=1767225600;sym=XAUUSD;tf=PERIOD_M15;bid=2650.10;ask=2650.40;atr=5.20\n"
        "time,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n")


class ToLine(unittest.TestCase):
    def test_buy_formats_with_dot_decimals(self):
        d = {"action": "buy", "sl_atr": 1.5, "tp_rr": 2, "confidence": 72, "reason": "x"}
        self.assertEqual(server.to_line(d, "1"), "BUY;1.50;2.00;72;1")

    def test_bad_inputs_give_none(self):
        bad = [None, {}, {"action": "HOLD"},
               {"action": "BUY", "sl_atr": "x", "tp_rr": 2, "confidence": 70},
               {"action": "SELL", "sl_atr": float("nan"), "tp_rr": 2, "confidence": 70},
               {"action": "SELL", "sl_atr": 1.0, "tp_rr": 2, "confidence": 150},
               {"action": "SELL", "sl_atr": -1.0, "tp_rr": 2, "confidence": 70}]
        for d in bad:
            self.assertEqual(server.to_line(d, "7"), "NONE;0;0;0;7", d)


class Decide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.LOG_DIR = pathlib.Path(self.tmp.name)
        server.HALT_FILE = pathlib.Path(self.tmp.name) / "HALT"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fake_buy_is_logged(self):
        self.assertEqual(server.decide(BODY, ask=server.ask_fake), "BUY;1.50;2.00;80;1767225600")
        rec = json.loads(next(server.LOG_DIR.glob("*.jsonl")).read_text().splitlines()[-1])
        self.assertEqual(rec["bar"], "1767225600")
        self.assertEqual(rec["prompt_sha"], server.PROMPT_SHA)

    def test_ask_error_gives_none(self):
        def boom(_):
            raise TimeoutError
        self.assertEqual(server.decide(BODY, ask=boom), "NONE;0;0;0;1767225600")

    def test_halt_file_gives_none(self):
        server.HALT_FILE.touch()
        self.assertEqual(server.decide(BODY, ask=server.ask_fake), "NONE;0;0;0;1767225600")

    def test_garbage_body_gives_none(self):
        self.assertEqual(server.decide("garbage", ask=server.ask_fake), "NONE;0;0;0;0")


if __name__ == "__main__":
    unittest.main()
```

**`run.sh`:**

```bash
#!/bin/zsh
# Start the bridge and keep the Mac awake while it runs.
set -eu
cd "$(dirname "$0")"
export AI_MODE="${AI_MODE:-api}"
export BRIDGE_MODEL="${BRIDGE_MODEL:-claude-opus-5-5}"
if [ "$AI_MODE" = "api" ]; then
  export ANTHROPIC_API_KEY="$(security find-generic-password -a "$USER" -s aigold-anthropic -w)"
fi
exec caffeinate -is .venv/bin/python bridge/server.py
```

**Lệnh chạy:**

```bash
cd ~/project/ae/aigold
brew install uv                       # if missing
uv venv --python 3.12 && uv pip install anthropic && uv pip freeze > requirements.txt
chmod +x run.sh
(cd bridge && ../.venv/bin/python -m unittest -v)

# fake mode (one herdr pane)
AI_MODE=fake ./run.sh
# other pane
curl -s http://127.0.0.1:18765/health
printf 'bar=1767225600;sym=XAUUSD;tf=PERIOD_M15;bid=2650.10;ask=2650.40;atr=5.20\ntime,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n' \
  | curl -s --data-binary @- -H 'Content-Type: text/plain' http://127.0.0.1:18765/decide
# expect: BUY;1.50;2.00;80;1767225600

# api mode smoke test (stop the fake one first)
./run.sh
# same curl -> expect NONE;0;0;0;1767225600 (no bars, so rules fail); check logs/decisions-*.jsonl has usage.usd
touch HALT   # -> NONE with error HALT; undo later with: trash HALT
```

Chỉ dùng CLI để smoke test: `AI_MODE=cli BRIDGE_MODEL=sonnet ./run.sh`. Chạy `claude --help` trước để kiểm các flag `--json-schema` và `--system-prompt` có trong bản anh đang cài.

**Xong khi:**
- Toàn bộ unit test pass.
- curl trả đúng dòng ở cả `fake` và `api`.
- Log có `prompt_sha`, `usage` và `latency_ms`.
- Có file `HALT` thì bridge trả NONE.

---

### Phase 2: EA (2a: dry-run với fake, 2b: lệnh thật trên demo với fake, 3-5 ngày)

**`mt5/AIGold.mq5`:**

```mql5
//+------------------------------------------------------------------+
//| AIGold.mq5 - the AI proposes, this EA decides.                   |
//+------------------------------------------------------------------+
#property version "1.00"
#include <Trade/Trade.mqh>

input string          InpSymbol          = "XAUUSD";   // exact broker symbol
input ENUM_TIMEFRAMES InpTimeframe       = PERIOD_M15;
input string          InpUrl             = "http://127.0.0.1:18765/decide";
input int             InpTimeoutMs       = 60000;
input bool            InpDryRun          = true;
input bool            InpAllowLive       = false;
input long            InpMagic           = 20261029;
input double          InpLots            = 0.01;
input int             InpStartHourGMT    = 7;
input int             InpEndHourGMT      = 17;
input int             InpFridayCloseGMT  = 19;
input int             InpMaxHoldBars     = 16;
input int             InpMaxSpreadPts    = 40;
input int             InpMinConfidence   = 70;
input int             InpMaxTradesPerDay = 3;
input double          InpMaxDailyLossPct = 2.0;
input double          InpMaxDrawdownPct  = 10.0;
input double          InpMaxRiskPct      = 1.0;
input double          InpSlMinAtr        = 1.0;
input double          InpSlMaxAtr        = 2.5;
input double          InpMinRR           = 1.5;
input double          InpMaxRR           = 3.0;
input double          InpMaxTpAtr        = 4.0;
input double          InpMinSlSpreads    = 6.0;
input double          InpMaxDriftAtr     = 0.3;
input int             InpSlippagePts     = 30;
input bool            InpNewsFilter      = true;
input int             InpNewsMinutes     = 30;
input int             InpBars            = 100;

CTrade trade;
string g_sym;
int    hE20 = INVALID_HANDLE, hE50 = INVALID_HANDLE, hE200 = INVALID_HANDLE;
int    hRsi = INVALID_HANDLE, hAtr = INVALID_HANDLE;
string g_gvBar, g_gvDay, g_gvEq, g_gvPeak;

int OnInit()
{
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowLive)
   {
      Print("REAL account and InpAllowLive=false: refusing to start");
      return INIT_FAILED;
   }
   g_sym = InpSymbol;
   if(!SymbolSelect(g_sym, true))
   {
      PrintFormat("symbol %s not found: set InpSymbol to the broker name", g_sym);
      return INIT_FAILED;
   }
   if(_Symbol != g_sym)
      PrintFormat("WARNING: attach to a %s chart; OnTick follows the chart symbol", g_sym);

   hE20  = iMA(g_sym, InpTimeframe, 20, 0, MODE_EMA, PRICE_CLOSE);
   hE50  = iMA(g_sym, InpTimeframe, 50, 0, MODE_EMA, PRICE_CLOSE);
   hE200 = iMA(g_sym, InpTimeframe, 200, 0, MODE_EMA, PRICE_CLOSE);
   hRsi  = iRSI(g_sym, InpTimeframe, 14, PRICE_CLOSE);
   hAtr  = iATR(g_sym, InpTimeframe, 14);
   if(hE20 == INVALID_HANDLE || hE50 == INVALID_HANDLE || hE200 == INVALID_HANDLE ||
      hRsi == INVALID_HANDLE || hAtr == INVALID_HANDLE)
      return INIT_FAILED;

   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints((ulong)InpSlippagePts);
   trade.SetTypeFillingBySymbol(g_sym);

   string p = "AIGold_" + IntegerToString(InpMagic) + "_";
   g_gvBar = p + "lastbar"; g_gvDay = p + "day"; g_gvEq = p + "dayeq"; g_gvPeak = p + "peak";

   PrintFormat("%s digits=%d point=%g tick=%g contract=%g stops=%d freeze=%d spread_now=%d pts dryrun=%s",
               g_sym, (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS), SymbolInfoDouble(g_sym, SYMBOL_POINT),
               SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE), SymbolInfoDouble(g_sym, SYMBOL_TRADE_CONTRACT_SIZE),
               (int)SymbolInfoInteger(g_sym, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(g_sym, SYMBOL_TRADE_FREEZE_LEVEL),
               (int)SymbolInfoInteger(g_sym, SYMBOL_SPREAD), InpDryRun ? "true" : "false");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hE20); IndicatorRelease(hE50); IndicatorRelease(hE200);
   IndicatorRelease(hRsi); IndicatorRelease(hAtr);
}

void OnTick()
{
   ManagePosition();

   datetime bar = iTime(g_sym, InpTimeframe, 0);
   if(bar == 0 || (datetime)(long)GlobalVariableGet(g_gvBar) == bar) return;
   GlobalVariableSet(g_gvBar, (double)bar);   // mark first: one AI call per bar, even after a restart
   GlobalVariablesFlush();
   if(TimeCurrent() - bar > 60) { Print("SKIP LATE_BAR"); return; }   // attached or woke up mid-bar

   string why = PreCheck();
   if(why != "") { PrintFormat("SKIP %s", why); return; }

   double bid = SymbolInfoDouble(g_sym, SYMBOL_BID), ask = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   double atr = 0;
   string body = BuildBody(bar, bid, ask, atr);
   if(body == "" || atr <= 0) { Print("SKIP NO_DATA"); return; }

   string resp;
   if(!Post(body, resp)) return;   // any bridge failure = no trade

   string p[];
   if(StringSplit(resp, ';', p) != 5 || (datetime)StringToInteger(p[4]) != bar)
   { PrintFormat("SKIP BAD_RESP '%s'", resp); return; }
   string act = p[0];
   if(act != "BUY" && act != "SELL") { PrintFormat("AI NONE bar=%s", TimeToString(bar)); return; }

   // the AI call may have taken up to 60 s: re-check the world
   if(iTime(g_sym, InpTimeframe, 0) != bar) { Print("SKIP BAR_CHANGED"); return; }
   double bid2 = SymbolInfoDouble(g_sym, SYMBOL_BID), ask2 = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   if(MathAbs((bid2 + ask2) - (bid + ask)) / 2.0 > InpMaxDriftAtr * atr) { Print("SKIP DRIFT"); return; }

   double sl = 0, tp = 0, lots = 0;
   int conf = (int)StringToInteger(p[3]);
   why = Validate(act, StringToDouble(p[1]), StringToDouble(p[2]), conf, atr, bid2, ask2, sl, tp, lots);
   if(why != "") { PrintFormat("REJECT %s %s conf=%d", act, why, conf); return; }
   Execute(act, lots, sl, tp, conf);
}

string PreCheck()
{
   if(!InpDryRun && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)))
      return "ALGO_OFF";
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double peak = MathMax(GlobalVariableGet(g_gvPeak), eq);
   GlobalVariableSet(g_gvPeak, peak);
   if(eq <= peak * (1.0 - InpMaxDrawdownPct / 100.0)) return "MAX_DD";   // reset the GV by hand (F3)
   if(HasPosition()) return "POSITION";
   MqlDateTime g;
   TimeToStruct(TimeGMT(), g);
   if(g.day_of_week == 0 || g.day_of_week == 6 || g.hour < InpStartHourGMT || g.hour >= InpEndHourGMT)
      return "HOURS";
   double spreadPts = (SymbolInfoDouble(g_sym, SYMBOL_ASK) - SymbolInfoDouble(g_sym, SYMBOL_BID)) / SymbolInfoDouble(g_sym, SYMBOL_POINT);
   if(spreadPts > InpMaxSpreadPts) return "SPREAD";
   if(TradesToday() >= InpMaxTradesPerDay) return "TRADES_DAY";
   if(DailyLossHit()) return "DAILY_LOSS";
   if(NewsBlackout()) return "NEWS";
   return "";
}

bool HasPosition()
{
   bool netting = AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetTicket(i) == 0 || PositionGetString(POSITION_SYMBOL) != g_sym) continue;
      if(netting || PositionGetInteger(POSITION_MAGIC) == InpMagic) return true;
   }
   return false;
}

int TradesToday()
{
   if(!HistorySelect(iTime(g_sym, PERIOD_D1, 0), TimeCurrent() + 60)) return 999;   // fail safe: block
   int n = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(t, DEAL_MAGIC) == InpMagic &&
         HistoryDealGetString(t, DEAL_SYMBOL) == g_sym &&
         HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN) n++;
   }
   return n;
}

bool DailyLossHit()
{
   datetime day = iTime(g_sym, PERIOD_D1, 0);
   if((datetime)(long)GlobalVariableGet(g_gvDay) != day)
   {
      GlobalVariableSet(g_gvDay, (double)day);
      GlobalVariableSet(g_gvEq, AccountInfoDouble(ACCOUNT_EQUITY));
   }
   return AccountInfoDouble(ACCOUNT_EQUITY) <= GlobalVariableGet(g_gvEq) * (1.0 - InpMaxDailyLossPct / 100.0);
}

bool NewsBlackout()
{
   if(!InpNewsFilter) return false;
   MqlCalendarValue v[];
   datetime now = TimeTradeServer();   // calendar times are server time
   if(!CalendarValueHistory(v, now - InpNewsMinutes * 60, now + InpNewsMinutes * 60, NULL, "USD"))
   {
      PrintFormat("calendar error %d: blocking entries", GetLastError());
      return true;
   }
   for(int i = 0; i < ArraySize(v); i++)
   {
      MqlCalendarEvent e;
      if(CalendarEventById(v[i].event_id, e) && e.importance == CALENDAR_IMPORTANCE_HIGH) return true;
   }
   return false;
}

string BuildBody(datetime bar, double bid, double ask, double &atrLast)
{
   int n = InpBars;
   MqlRates r[];
   double e20[], e50[], e200[], rsi[], atr[];   // not series: index 0 = oldest
   if(CopyRates(g_sym, InpTimeframe, 1, n, r) != n) return "";   // shift 1 = closed bars only
   if(CopyBuffer(hE20, 0, 1, n, e20) != n || CopyBuffer(hE50, 0, 1, n, e50) != n ||
      CopyBuffer(hE200, 0, 1, n, e200) != n || CopyBuffer(hRsi, 0, 1, n, rsi) != n ||
      CopyBuffer(hAtr, 0, 1, n, atr) != n) return "";
   int d = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);
   atrLast = atr[n - 1];
   string s = StringFormat("bar=%I64d;sym=%s;tf=%s;bid=%s;ask=%s;atr=%s\n", (long)bar, g_sym,
                           EnumToString(InpTimeframe), DoubleToString(bid, d), DoubleToString(ask, d),
                           DoubleToString(atrLast, d));
   s += "time,open,high,low,close,ema20,ema50,ema200,rsi14,atr14\n";
   for(int i = 0; i < n; i++)
      s += TimeToString(r[i].time, TIME_DATE | TIME_MINUTES) + "," +
           DoubleToString(r[i].open, d) + "," + DoubleToString(r[i].high, d) + "," +
           DoubleToString(r[i].low, d) + "," + DoubleToString(r[i].close, d) + "," +
           DoubleToString(e20[i], d) + "," + DoubleToString(e50[i], d) + "," +
           DoubleToString(e200[i], d) + "," + DoubleToString(rsi[i], 1) + "," +
           DoubleToString(atr[i], d) + "\n";
   return s;
}

bool Post(const string body, string &resp)
{
   char data[], res[];
   string rh;
   int n = StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(n > 0) ArrayResize(data, n - 1);   // drop the trailing NUL
   ResetLastError();
   int code = WebRequest("POST", InpUrl, "Content-Type: text/plain\r\n", InpTimeoutMs, data, res, rh);
   if(code != 200) { PrintFormat("BRIDGE_ERR http=%d err=%d", code, GetLastError()); return false; }
   resp = CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8);
   StringTrimLeft(resp);
   StringTrimRight(resp);
   return true;
}

double NormPrice(double price)
{
   double tick = SymbolInfoDouble(g_sym, SYMBOL_TRADE_TICK_SIZE);
   if(tick > 0) price = MathRound(price / tick) * tick;
   return NormalizeDouble(price, (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS));
}

double NormLots(double v)
{
   double step = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP);
   double mn = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN), mx = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MAX);
   if(step > 0) v = MathFloor(v / step + 1e-9) * step;
   return MathMax(mn, MathMin(mx, v));
}

string Validate(const string act, double slAtr, double rr, int conf, double atr,
                double bid, double ask, double &sl, double &tp, double &lots)
{
   if(!MathIsValidNumber(slAtr) || !MathIsValidNumber(rr)) return "BAD_NUM";
   if(conf < InpMinConfidence) return "CONF";
   if(slAtr < InpSlMinAtr || slAtr > InpSlMaxAtr) return "SL_ATR";
   if(rr < InpMinRR || rr > InpMaxRR) return "RR";
   if(slAtr * rr > InpMaxTpAtr) return "TP_ATR";

   bool   buy    = (act == "BUY");
   double entry  = buy ? ask : bid;            // real fill side
   double spread = ask - bid;
   double slDist = slAtr * atr, tpDist = slDist * rr;
   if(slDist < InpMinSlSpreads * spread) return "SL_SPREAD";

   double pt = SymbolInfoDouble(g_sym, SYMBOL_POINT);
   double minStop = (double)MathMax(SymbolInfoInteger(g_sym, SYMBOL_TRADE_STOPS_LEVEL),
                                    SymbolInfoInteger(g_sym, SYMBOL_TRADE_FREEZE_LEVEL)) * pt;
   if(slDist - spread < minStop || tpDist - spread < minStop) return "STOPS_LEVEL";

   sl   = NormPrice(buy ? entry - slDist : entry + slDist);
   tp   = NormPrice(buy ? entry + tpDist : entry - tpDist);
   lots = NormLots(InpLots);

   double pl = 0;
   if(!OrderCalcProfit(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, g_sym, lots, entry, sl, pl)) return "CALC";
   if(-pl > AccountInfoDouble(ACCOUNT_BALANCE) * InpMaxRiskPct / 100.0) return "RISK";
   return "";
}

void Execute(const string act, double lots, double sl, double tp, int conf)
{
   int d = (int)SymbolInfoInteger(g_sym, SYMBOL_DIGITS);
   if(InpDryRun)
   {
      PrintFormat("DRYRUN %s lots=%.2f sl=%s tp=%s conf=%d", act, lots,
                  DoubleToString(sl, d), DoubleToString(tp, d), conf);
      return;
   }
   bool ok = (act == "BUY") ? trade.Buy(lots, g_sym, 0.0, sl, tp, "AIGold")
                            : trade.Sell(lots, g_sym, 0.0, sl, tp, "AIGold");
   uint rc = trade.ResultRetcode();
   PrintFormat("ORDER %s ok=%s rc=%u (%s) req=%s fill=%s sl=%s tp=%s",
               act, ok ? "true" : "false", rc, trade.ResultRetcodeDescription(),
               DoubleToString(trade.RequestPrice(), d), DoubleToString(trade.ResultPrice(), d),
               DoubleToString(sl, d), DoubleToString(tp, d));
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED))
      Print("ORDER_FAIL: no retry, next chance is the next bar");
}

void ManagePosition()
{
   MqlDateTime g;
   TimeToStruct(TimeGMT(), g);
   bool fridayClose = (g.day_of_week == 5 && g.hour >= InpFridayCloseGMT);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetString(POSITION_SYMBOL) != g_sym || PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      int held = iBarShift(g_sym, InpTimeframe, (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= InpMaxHoldBars || fridayClose)
      {
         if(!trade.PositionClose(t))
            PrintFormat("CLOSE_FAIL ticket=%I64u rc=%u", t, trade.ResultRetcode());
         else
            PrintFormat("TIME_EXIT ticket=%I64u held=%d bars friday=%s", t, held, fridayClose ? "true" : "false");
      }
   }
}
```

**Deploy và compile:**

```bash
cp ~/project/ae/aigold/mt5/AIGold.mq5 "$MT5/Experts/"   # Wine may not follow symlinks, so copy
```

Trong MT5: F4 mở MetaEditor → mở `Experts/AIGold.mq5` → F7, phải ra 0 errors. Mở chart **đúng symbol**, khung M15, kéo EA vào. Tab Common: tick *Allow Algo Trading*. Tab Inputs: sửa `InpSymbol`. Bật nút **Algo Trading** trên toolbar.

**2a: dry-run với fake (1 ngày)**

- Chạy `AI_MODE=fake ./run.sh` và `InpDryRun=true`.
- Mỗi bar trong khung giờ phải in ra `DRYRUN BUY lots=0.01 sl=... tp=...`. Kiểm tay: SL = ask − 1.5 × ATR.
- Thử `FAKE_ACTION=SELL` và `FAKE_ACTION=NONE`.
- Đặt `InpMinConfidence=90` → phải thấy `REJECT BUY CONF`.
- Tắt bridge → phải thấy `BRIDGE_ERR`.
- Ngoài giờ → phải thấy `SKIP HOURS`.

**2b: lệnh thật trên demo với fake (3-5 ngày, không tốn token)**

- Đặt `InpDryRun=false`, dùng tài khoản demo.
- Phải thấy:
  - `ORDER BUY ok=true rc=10009`, và lệnh có SL/TP ngay từ đầu.
  - Các bar sau đó: `SKIP POSITION`.
  - Sau 16 bar: `TIME_EXIT`.
  - Sau 3 lệnh trong ngày: `SKIP TRADES_DAY`.
- **Test restart:** giữa bar, nhấn Cmd+Q để tắt MT5 rồi mở lại. Không được có lệnh thứ hai trong cùng bar; log phải hiện `SKIP LATE_BAR` hoặc không có gì.
- Tắt nút Algo Trading → phải thấy `SKIP ALGO_OFF`.
- `touch HALT` → phải thấy `AI NONE`.
- Thứ Sáu 19:00 GMT → lệnh bị đóng.
- Ghi lại slippage (`req` so với `fill`) và mọi retcode khác 10009.

**Xong khi:** tất cả các kịch bản trên đều đúng, không có lệnh trùng, và không có lệnh nào thiếu SL.

---

### Phase 3: Shadow mode với AI thật (≥ 4 tuần, mục tiêu ≥ 100 tín hiệu được chấm)

**Các bước:**

1. Điền luật thật vào `prompt.md`, sau đó **đóng băng** file này. `prompt_sha` được log mỗi lần gọi, nên sửa prompt là phải chạy lại mẫu từ đầu.
2. Chạy `./run.sh` (api), đặt `InpDryRun=true`, khởi động lại EA. Trong shadow mode, EA hỏi AI ở mọi bar qua được PreCheck (~40 bar/ngày ở M15).
3. **Ngày 1-2: so sánh model** trên ~20 payload thật:

```python
# tools/compare_models.py - run from the repo root: .venv/bin/python tools/compare_models.py logs/decisions-2026-11.jsonl
import json
import sys

sys.path.insert(0, "bridge")
import server  # noqa: E402

recs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
recs = [r for r in recs if r.get("mode") == "api" and "payload" in r][-20:]
for model in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"):
    server.MODEL = model
    out = [server.ask_api(r["payload"]) for r in recs]
    acts = "".join((d or {}).get("action", "E")[0] for d, _ in out)
    print(f"{model:20} {acts}  usd={sum(u['usd'] for _, u in out):.3f}")
```

   Đây chỉ là kiểm tra format, chi phí và mức đồng thuận, **không** đo lợi nhuận. Chọn một model rồi giữ nguyên suốt mẫu.

4. **Mỗi tuần:** export M1 rồi chấm điểm.

```mql5
// ExportM1.mq5 - writes MQL5/Files/m1_<symbol>.csv (server-time unix, bid prices)
#property script_show_inputs
input string InpSymbol = "XAUUSD";
input int    InpDays   = 60;

void OnStart()
{
   MqlRates r[];
   int n = CopyRates(InpSymbol, PERIOD_M1, TimeCurrent() - InpDays * 86400, TimeCurrent(), r);
   if(n <= 0) { PrintFormat("CopyRates failed err=%d", GetLastError()); return; }
   int d = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   int f = FileOpen("m1_" + InpSymbol + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(f == INVALID_HANDLE) { PrintFormat("FileOpen failed err=%d", GetLastError()); return; }
   FileWriteString(f, "time,open,high,low,close\n");
   for(int i = 0; i < n; i++)
      FileWriteString(f, StringFormat("%I64d,%s,%s,%s,%s\n", (long)r[i].time,
                      DoubleToString(r[i].open, d), DoubleToString(r[i].high, d),
                      DoubleToString(r[i].low, d), DoubleToString(r[i].close, d)));
   FileClose(f);
   PrintFormat("wrote %d M1 bars", n);
}
```

```bash
cp ~/project/ae/aigold/mt5/ExportM1.mq5 "$MT5/Scripts/"   # compile with F7, run on the chart
.venv/bin/python tools/scoring.py --m1 "$MT5/Files/m1_XAUUSD.csv" logs/decisions-*.jsonl
```

**`tools/scoring.py`:**

```python
"""Score shadow-mode decisions on M1 bars. Forward (live) data only.

M1 rows are bid prices. BUY enters at the logged ask, SELL at the logged bid.
If SL and TP are both touched in one M1 bar, SL counts first (conservative).
Usage: python3 tools/scoring.py --m1 m1_XAUUSD.csv logs/decisions-*.jsonl
"""
import argparse
import bisect
import csv
import json
import random
import statistics

TF_SEC = {"PERIOD_M15": 900, "PERIOD_H1": 3600}


def load_m1(path):
    with open(path, newline="") as f:
        rows = sorted((int(r["time"]), float(r["high"]), float(r["low"]), float(r["close"]))
                      for r in csv.DictReader(f))
    return rows, [r[0] for r in rows]


def simulate(m1, times, bar, buy, entry, spread, sl_dist, rr, hold_sec):
    """Return (R, exit_time), or None if M1 data does not cover the trade yet."""
    sl = entry - sl_dist if buy else entry + sl_dist
    tp = entry + sl_dist * rr if buy else entry - sl_dist * rr
    i, last = bisect.bisect_left(times, bar), None
    while i < len(m1) and m1[i][0] < bar + hold_sec:
        t, hi, lo, _ = m1[i]
        if (buy and lo <= sl) or (not buy and hi + spread >= sl):
            return -1.0, t
        if (buy and hi >= tp) or (not buy and lo + spread <= tp):
            return rr, t
        last, i = m1[i], i + 1
    if last is None or i == len(m1):
        return None
    exit_px = last[3] if buy else last[3] + spread
    return ((exit_px - entry) if buy else (entry - exit_px)) / sl_dist, last[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--m1", required=True)
    ap.add_argument("--min-conf", type=int, default=70)
    ap.add_argument("--sl-min", type=float, default=1.0)
    ap.add_argument("--sl-max", type=float, default=2.5)
    ap.add_argument("--rr-min", type=float, default=1.5)
    ap.add_argument("--rr-max", type=float, default=3.0)
    ap.add_argument("--tp-max-atr", type=float, default=4.0)
    ap.add_argument("--min-sl-spreads", type=float, default=6.0)
    ap.add_argument("--hold-bars", type=int, default=16)
    ap.add_argument("--cost", type=float, default=0.0, help="commission per trade, in price units")
    a = ap.parse_args()

    m1, times = load_m1(a.m1)
    recs = sorted((json.loads(l) for p in a.logs for l in open(p, encoding="utf-8")),
                  key=lambda r: int(r.get("bar", 0)))
    calib, ai, flip, setups, busy_until = {}, [], [], set(), 0
    for r in recs:
        d = r.get("decision") or {}
        act = str(d.get("action", "")).upper()
        if r.get("error") or act not in ("BUY", "SELL"):
            continue
        sl_atr, rr, conf = float(d["sl_atr"]), float(d["tp_rr"]), int(d["confidence"])
        bar, atr, bid, ask = int(r["bar"]), float(r["atr"]), float(r["bid"]), float(r["ask"])
        spread, sl_dist = ask - bid, sl_atr * atr
        if not (a.sl_min <= sl_atr <= a.sl_max and a.rr_min <= rr <= a.rr_max
                and sl_atr * rr <= a.tp_max_atr and sl_dist >= a.min_sl_spreads * spread):
            continue  # the EA would reject it
        if bar < busy_until:
            continue  # the EA holds one position at a time
        buy, hold = act == "BUY", a.hold_bars * TF_SEC[r["tf"]]
        res = simulate(m1, times, bar, buy, ask if buy else bid, spread, sl_dist, rr, hold)
        opp = simulate(m1, times, bar, not buy, bid if buy else ask, spread, sl_dist, rr, hold)
        if res is None or opp is None:
            continue
        cost_r = a.cost / sl_dist
        calib.setdefault(min(conf // 10 * 10, 90), []).append(res[0] - cost_r)
        if conf >= a.min_conf:
            ai.append(res[0] - cost_r)
            flip.append(opp[0] - cost_r)
            setups.add((r.get("prompt_sha"), r.get("model")))
            busy_until = res[1]

    n = len(ai)
    if n == 0:
        print("no scored signals yet")
        return
    rng = random.Random(1)
    mean = statistics.fmean(ai)
    boots = sorted(statistics.fmean(rng.choices(ai, k=n)) for _ in range(2000))
    lo, hi = boots[50], boots[1949]
    rand = [statistics.fmean(x if rng.random() < 0.5 else y for x, y in zip(ai, flip)) for _ in range(2000)]
    p = sum(m >= mean for m in rand) / len(rand)
    eq = peak = dd = 0.0
    for x in ai:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    print(f"n={n}  win={sum(x > 0 for x in ai) / n:.0%}  meanR={mean:+.3f}  95%CI=[{lo:+.3f}, {hi:+.3f}]")
    print(f"vs random direction p={p:.3f}  maxDD={dd:.1f}R  total={eq:+.1f}R")
    print("confidence bucket (all confidences, calibration):")
    for b in sorted(calib):
        print(f"  {b:>3}+  n={len(calib[b]):>3}  meanR={statistics.fmean(calib[b]):+.3f}")
    if len(setups) > 1:
        print(f"WARNING: sample mixes prompt/model versions {setups}: not valid evidence")
    ok = n >= 100 and mean > 0.15 and lo > 0 and p < 0.05 and dd < 10 and len(setups) == 1
    print("GATE:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
```

**Xong khi:** có ≥ 100 tín hiệu được chấm với cùng một `prompt_sha` và một model. Có số tiền chi tiêu theo ngày lấy từ log. Tỉ lệ `error` dưới 5%.

---

### Phase 4: Quyết định theo cổng đã chốt (1 buổi)

- Chạy `scoring.py`. Nếu ra `GATE: FAIL` thì dừng hoặc viết lại luật trong prompt, sau đó **chạy lại Phase 3 từ đầu**. Mẫu cũ không được dùng để tinh chỉnh rồi chấm lại.
- Nếu ra `GATE: PASS`, kiểm thêm bài toán chi phí ở §8.

### Phase 5: Live 0.01 lot (chỉ khi Phase 4 PASS)

- Dời MT5 và bridge lên VPS Windows. Python và `server.py` giữ nguyên; trên VPS lưu key bằng biến môi trường của Windows.
- Dùng một tài khoản live nhỏ, tách riêng. Đặt `InpAllowLive=true`, `InpDryRun=false`, giữ nguyên toàn bộ guard.
- Mỗi tuần so kết quả live với shadow. Nếu live lệch dưới khoảng CI của shadow thì dừng.

---

## 8. Đánh giá hiệu quả

**Phương pháp**

- **Chỉ tính dữ liệu forward.** Replay lịch sử bị nhiễm look-ahead vì model đã thấy giá vàng trong lúc train. Strategy Tester cũng không chạy được WebRequest. Replay chỉ dùng để debug, không bao giờ là bằng chứng.
- **Shadow mode:** hỏi AI ở mọi bar qua được PreCheck. Lệnh BUY/SELL được mô phỏng trên M1: vào ở giá ask/bid đã log, nếu cùng một nến chạm cả SL và TP thì tính SL trước, đóng theo thời gian sau 16 bar. Trừ commission bằng `--cost`. Chỉ tính các lệnh không chồng nhau, giống EA thật.
- **Đóng băng `prompt.md`, model và `InpMinConfidence`** trong suốt mẫu. Ngưỡng confidence hiện chưa hiệu chỉnh. Xem bảng bucket sau mẫu đầu, nếu muốn đổi ngưỡng thì phải chạy mẫu mới.

**Chỉ số:** n, win rate, R trung bình đã trừ chi phí, CI 95% bằng bootstrap, max drawdown tính theo R, tổng R, bảng hiệu chỉnh theo bucket confidence, tỉ lệ bị loại theo mã (`REJECT` / `SKIP` trong Experts log), số USD/ngày (từ `usage.usd`), latency.

**Baseline**

| Baseline | Kiểm tra điều gì | Cách làm |
|---|---|---|
| B2 random direction | AI chọn hướng có tốt hơn tung đồng xu không | Có sẵn: cùng bar, cùng SL/TP, hướng ngẫu nhiên, 2000 lần lặp → p |
| B3 đứng ngoài (0R) | Vào lệnh có tốt hơn không làm gì không | Có sẵn: CI dưới > 0 |
| B1 luật EMA20/50 cố định | AI có hơn một luật đơn giản không | Tuỳ chọn, thêm vào `scoring.py` nếu B2/B3 pass |

**Cổng đi live (chốt từ bây giờ):** n ≥ 100, mean > +0.15R, CI dưới > 0, p < 0.05 so với random, maxDD < 10R, chỉ một bộ prompt/model. Lưu ý: với n = 100 thì sai số chuẩn ≈ 0.13R, nên mean phải khoảng ≥ 0.26R thì CI dưới mới lớn hơn 0. Phần lớn khả năng là sẽ FAIL, và đó là một kết quả rẻ, hợp lệ.

**Bài toán chi phí so với edge (anh nên xem kỹ phần này).** Với lot 0.01, nếu contract size là 100 oz thì giá đi $1 tương ứng $1 lời/lỗ (kiểm `contract=` mà EA in ra). SL 1.5 ATR × ATR ≈ $5 thì 1R ≈ $7.5. Giả sử edge +0.2R và khoảng 1-2 lệnh/ngày, kỳ vọng chỉ khoảng $1.5-3/ngày.

Ước tính chi phí AI (em tự tính, chưa đo; xem số thật trong `usage.usd`): mỗi lần gọi khoảng 5-6k token input + 0.3-1k token output.

| Model | Shadow (~40 lần gọi/ngày) | Live (~15-25 lần/ngày) |
|---|---|---|
| Opus 5.5, effort low | ≈ $1.2-1.8 | ≈ $0.5-1.1 |
| Sonnet 5.5 | ≈ một nửa Opus | |
| Haiku 5.5 | ≈ 1/40 Opus | |

Nghĩa là **ở lot 0.01, chi phí model có thể ăn hết edge**. Hoặc phải dùng model rẻ hơn mà vẫn qua cổng, hoặc phải tăng lot, mà tăng lot thì rủi ro tăng theo.

---

## 9. Câu hỏi mở cho anh

1. **Luật chiến lược cho `prompt.md`.** Đây là việc chặn Phase 3. Anh gửi em luật bằng lời, em chuyển thành các điều kiện kiểm được từ dữ liệu.
2. **API key hay `claude -p`?** Em đề xuất API key + spend limit trên Console cho Phase 3 trở đi, còn CLI chỉ để smoke test. Anh đồng ý không?
3. **Model:** mặc định là `claude-opus-5-5` effort low. Anh có muốn dùng Sonnet 5.5 hoặc Haiku 5.5 để giảm chi phí (xem §8) không? Anh quyết sau bước so sánh ở Phase 3 nha.
4. **Broker:** tên symbol, số chữ số thập phân (2 hay 3), contract size, commission mỗi lot, và độ lệch GMT của server.
5. **M15 hay H1** cho mẫu đầu tiên? H1 rẻ hơn khoảng 4 lần nhưng mất lâu hơn mới đủ 100 tín hiệu.
6. Có thêm **khối HTF** (10 bar H1 + 5 bar H4) vào payload không? Mặc định là không. Chỉ thêm nếu luật của anh cần.
7. **Máy chạy 24/5:** giữ Mac thức suốt 4 tuần (cắm sạc, mở nắp, `caffeinate`), hay lên VPS sớm từ Phase 3?
8. **Khung giờ 07-17 GMT** có hợp với cách anh trade không?
9. **Live:** quy mô tài khoản và `InpMaxRiskPct` (mặc định 1%).

**Những điểm chưa kiểm chứng, sẽ rõ ở Phase 0-2:**
- WebRequest tới port không chuẩn trong Wine; Calendar API trong Wine; bind port 80 trên macOS mà không cần root.
- Các flag của `claude -p` trong bản anh đang cài; chính sách credit của `claude -p` (nguồn thứ cấp).
- `CTrade::SetTypeFillingBySymbol` có trong thư viện chuẩn của bản terminal anh dùng không. Compile sẽ báo nếu thiếu; khi đó thay bằng `SetTypeFilling` dựa trên `SYMBOL_FILLING_MODE`.
- Code EA và `scoring.py` chưa được compile hay chạy thử, nên lần compile đầu cần đọc kỹ tab Errors.
- Các con số chi phí ở §8 là ước tính.

# Chạy chatbot thom house trên máy local

Từ ngày 08/11/2026, chatbot nói chuyện với khách qua tài khoản Zalo cá nhân thay cho Zalo OA. Cách chạy bản đó nằm trong `docs/chay-local-zalo-ca-nhan.md`. Tài liệu dưới đây mô tả chế độ `ZALO_MODE=mock`, đường Zalo OA cũ và cách chạy từng phần bằng tay. Từ ngày 12/11/2026, tài liệu này cũng là nơi ghi các lệnh của phòng hai bot, của lệnh đồng bộ nhãn Zalo, của script nhập lịch sử buổi làm, của script đoán buổi làm từ tin nhắn cũ (`scripts/analyze_visits.py`) và các lệnh test. Ý nghĩa của các phần đó với studio nằm trong `docs/rooms.md`.

## Phần anh cần đọc trước

Toàn bộ hệ thống đã chạy được trên một máy Mac mà không cần tài khoản Zalo thật. Ngày 07/11/2026, tôi đã chạy đủ chuỗi sau: khách nhắn qua Zalo giả lập, server gửi tin xin đồng ý, runner gọi `claude -p` bằng gói Claude của anh để soạn bản nháp, nhân viên duyệt qua staff API, và tin trả lời nằm trong outbox.

Có ba điều anh cần biết trước khi làm theo tài liệu này:

- Mọi tin gửi cho khách ở chế độ `ZALO_MODE=mock` chỉ được ghi vào bảng `outbox`, không đi tới Zalo. Chưa có tin nào được gửi qua Zalo thật.
- Runner gọi model qua gói Claude của anh, nên mỗi câu trả lời dùng một phần hạn mức của gói. Trong lượt chạy thử, một câu trả lời tốn khoảng 0,02 đến 0,15 USD nếu quy đổi theo giá API (số do runner ghi lại, không phải tiền bị trừ).
- Đừng khởi động runner từ bên trong một phiên Claude Code. Phiên Claude Code tự đặt biến `CLAUDE_EFFORT=high`, và trước khi sửa, runner đọc nhầm biến này nên đã gọi model ở mức effort `high` thay vì `low`. Mục "Những lỗi dễ gặp khi chạy local" ở cuối tài liệu nói cách tránh.

## Hệ thống gồm những phần nào?

Hệ thống có bốn phần chính chạy riêng, mỗi phần nằm trong một thư mục của `apps/`. Từ 12/11/2026 có thêm một phần không bắt buộc nằm trong `tools/`.

| Phần | Thư mục | Việc phần đó làm |
|---|---|---|
| Server | `apps/server` | Cloudflare Worker nhận webhook Zalo, lưu dữ liệu vào D1, tạo việc cho runner, kiểm bản nháp và gửi tin |
| Runner | `apps/runner` | Chương trình Python chạy trên máy Mac; hỏi server có việc không, gọi `claude -p` để soạn bản nháp, rồi gửi bản nháp về server |
| Console | `apps/console` | Trang web cho nhân viên xem hội thoại, duyệt bản nháp, xử lý yêu cầu chuyển nhân viên và ghi nhận buổi làm |
| Desktop | `apps/desktop` | Cửa sổ Electron mở console trên máy nhân viên |
| OpenMausBot (không bắt buộc) | `tools/openmausbot` | Chương trình giữ các phòng chat nơi hai bot cùng soạn bản nháp; chỉ được dùng khi runner chạy với `THOMHOUSE_DRAFT_ENGINE=rooms` (mục "Phòng hai bot chạy thế nào trên máy local?") |

Runner không có code gửi tin cho khách. Chỉ server gửi tin, và server kiểm bản nháp ngay trước khi gửi.

## Cần cài gì?

Máy cần Node.js 22 trở lên, pnpm 10.32.1, Python 3.11 trở lên và Claude Code CLI (lệnh `claude`) đã đăng nhập. Lượt chạy thử dùng Node 24.19.0, Python 3.14 và Claude Code 2.1.319. Riêng OpenMausBot cần Node.js 24 trở lên; các phần khác vẫn chạy với Node 22.

Cài thư viện cho cả ba app JavaScript bằng một lệnh ở thư mục gốc:

```bash
cd ~/Projects/lulu-thomhouse
pnpm install --frozen-lockfile
```

Runner chỉ dùng thư viện chuẩn của Python, nên không cần `pip install`.

## Cài lên máy khác thế nào?

Hướng dẫn này dành cho máy có thư mục dự án. Muốn chạy chatbot trên một máy Mac khác của studio, anh không chép thư mục dự án sang máy đó. Anh tạo file cài bằng `scripts/release/make_release.py` trên máy này, rồi cài chatbot lên máy kia bằng file cài; `docs/cai-dat-may-moi.md` mô tả từng bước, từ lúc tạo file cài tới lúc cập nhật, chuyển máy và gỡ chatbot.

## Cấu hình thế nào?

### Bí mật cho server (`apps/server/.dev.vars`)

Server đọc token và khóa Zalo từ file `apps/server/.dev.vars`. File này đã nằm trong `.gitignore`. Lệnh dưới đây tạo file với các giá trị ngẫu nhiên và không in giá trị nào ra màn hình:

```bash
cd apps/server
python3 - <<'EOF'
import secrets
open(".dev.vars", "w").write("\n".join([
  f"RUNNER_TOKEN=dev-runner-{secrets.token_hex(16)}",
  f"STAFF_TOKEN=dev-staff-{secrets.token_hex(16)}",
  "ZALO_APP_ID=dev-app-id",
  "ZALO_OA_ID=dev-oa-id",
  f"ZALO_OA_SECRET_KEY=dev-oa-{secrets.token_hex(16)}",
  f"ZALO_APP_SECRET_KEY=dev-app-{secrets.token_hex(16)}",
]) + "\n")
EOF
chmod 600 .dev.vars
```

`RUNNER_TOKEN` là token runner dùng để gọi server. `STAFF_TOKEN` là token nhân viên nhập vào console. Script giả lập Zalo tự đọc `ZALO_OA_SECRET_KEY` từ file này để ký webhook giả.

Các giá trị không bí mật nằm trong `apps/server/wrangler.toml`: `ZALO_MODE = "mock"`, `DEBOUNCE_MS = "10000"` (server chờ 10 giây sau tin cuối của khách rồi mới tạo việc cho runner) và `LEASE_MS = "90000"` (runner có 90 giây để gửi bản nháp hoặc gia hạn, nếu không việc đó bị chuyển cho nhân viên).

### Cấu hình runner (`apps/runner/.env`)

Chép file mẫu rồi sửa:

```bash
cp apps/runner/.env.example apps/runner/.env
```

Các biến chính:

- `SERVER_URL=http://127.0.0.1:8787` là địa chỉ server local.
- `RUNNER_TOKEN` phải trùng `RUNNER_TOKEN` trong `.dev.vars`. Nếu để trống, runner đọc token từ Keychain của macOS, mục `thomhouse-runner`.
- `RUNNER_ID` là tên của máy chạy runner, ví dụ `mac-studio-1`.
- `THOMHOUSE_BOT_HOME` là thư mục chứa danh sách tài khoản Claude, session và thư mục làm việc của từng hội thoại. Mặc định là `~/.thomhouse-bot`.
- `THOMHOUSE_CLAUDE_MODEL=claude-opus-5-5` và `THOMHOUSE_CLAUDE_EFFORT=low` chọn model và mức effort. Hai biến này đã đổi tên từ `CLAUDE_MODEL` và `CLAUDE_EFFORT` trong lượt tích hợp này.
- `CLAUDE_TIMEOUT_S` là số giây tối đa cho một lần gọi `claude -p`. Mặc định là 60; trong lượt chạy thử tôi đặt 120 vì máy đang tải nặng.
- `THOMHOUSE_DRAFT_ENGINE` chọn cách soạn bản nháp. `claude` (mặc định) gọi `claude -p` một lần cho mỗi bản nháp. `rooms` cho hai bot soạn trong phòng chat của OpenMausBot. Giá trị khác làm runner dừng ngay khi khởi động với dòng `config error: THOMHOUSE_DRAFT_ENGINE must be one of claude, rooms`. Các biến khác của phòng hai bot nằm ở mục "Phòng hai bot chạy thế nào trên máy local?".

### Danh sách tài khoản Claude cho runner

Runner gọi model qua `scripts/runner/claude_pool.py`. Script này giữ một danh sách tài khoản Claude và tự chuyển sang tài khoản khác khi một tài khoản hết hạn mức hoặc mất đăng nhập.

Cách dùng cho vận hành thật là tạo một thư mục cấu hình riêng cho mỗi tài khoản rồi đăng nhập vào thư mục đó:

```bash
python3 scripts/runner/claude_pool.py add <label> --priority 1
# lệnh add in ra lệnh đăng nhập, có dạng:
CLAUDE_CONFIG_DIR="$HOME/.thomhouse-bot/accounts/<label>" claude auth login
python3 scripts/runner/claude_pool.py status
```

Cách nhanh hơn khi thử trên máy dev là dùng luôn tài khoản Claude đang đăng nhập trên máy:

```bash
python3 scripts/runner/claude_pool.py add-default default --priority 1
```

Cách nhanh này có một điểm yếu: tài khoản `add-default` dùng `~/.claude`, nên file session của các cuộc hội thoại nằm trong `~/.claude/projects`, và runner không xóa các file đó. Runner in cảnh báo về việc này mỗi lần khởi động. Khi khách yêu cầu xóa dữ liệu, lệnh `forget` của runner cũng không xóa được các file session đó.

Lượt chạy thử dùng cách nhanh, với `THOMHOUSE_BOT_HOME` trỏ vào một thư mục tạm, nên `~/.thomhouse-bot` thật của anh không bị thay đổi.

### Cấu hình console

Khi chạy console bằng Vite dev server, anh để trống ô địa chỉ server trong màn hình Cài đặt. Vite chuyển các request `/staff` và `/health` sang `http://127.0.0.1:8787`. Nếu server chạy ở địa chỉ khác, anh tạo `apps/console/.env.local` với `VITE_API_URL=<địa chỉ>`. Không đặt staff token vào biến `VITE_*`, vì các biến đó bị đóng gói vào file build.

## Khởi động từng phần thế nào?

Mỗi phần chạy trong một cửa sổ terminal riêng, theo thứ tự dưới đây.

### Bước 1: tạo database và chạy server

```bash
cd apps/server
pnpm exec wrangler d1 migrations apply thomhouse-main --local
pnpm dev            # wrangler dev --local, cổng 8787
```

Lệnh migration tạo D1 local trong `apps/server/.wrangler/state`. Muốn làm lại từ đầu thì xóa thư mục đó rồi chạy lại migration; mọi dữ liệu dev cũ sẽ mất.

Hai migration mới nhất cùng có từ 12/11/2026. `0010_rooms_roles_customer.sql` thêm bảng vai trò liên hệ, bảng quyền lợi của khách, các cột số tiền, kỹ thuật viên, thời lượng cho buổi làm, và các cột của công tắc tự động trả lời và phòng hai bot. `0011_chat_facts.sql` thêm bốn bảng mới cho các lần đến, gói và số điện thoại mà `scripts/analyze_visits.py` suy ra từ tin nhắn cũ; migration này không sửa dòng nào có sẵn. `wrangler dev` nạp code mới mà không áp migration. Khi chưa áp 0010, khách vẫn được trả lời như trước, nhưng các API của mục 14 trong `docs/contracts.md` trả lỗi 409 kèm câu "apply migration 0010_rooms_roles_customer.sql". Khi chưa áp 0011, khối Tóm tắt khách hàng bỏ qua dữ liệu suy ra từ tin nhắn, và các API `/staff/chat-facts/...` trả lỗi 409 kèm câu "apply migration 0011_chat_facts.sql". `scripts/start_local.sh` chỉ áp migration khi chính script bật server, nên sau khi cập nhật code anh chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh`.

File `0011_chat_facts.sql` được sửa trực tiếp một lần ngày 12/11, trước khi áp vào bất kỳ database nào, để thêm cột `phone_decision_id` và bảng `chat_phone_dismissed`. Một database đã áp bản cũ của file cần hai câu lệnh đó chạy bằng tay; câu lệnh nằm ở mục 15.10 của `docs/contracts.md`.

### Bước 2: nạp catalog dịch vụ

Server chưa có menu, giá và prompt cho tới khi anh nạp catalog. Lệnh sau đọc `data/services.json`, `data/business-facts.json`, khối A của `design/system-prompt-draft.md` và `design/tools-schema.json`, rồi gửi tới `POST /dev/seed`:

```bash
python3 -I scripts/seed_dev.py
```

Kết quả lượt chạy thử là 23 dịch vụ, 33 biến thể giá và 36 dữ kiện. Endpoint `/dev/seed` chỉ hoạt động khi `ENV=dev` và request mang staff token. `wrangler.toml` đặt `ENV = "prod"`, nên anh cần dòng `ENV=dev` trong `apps/server/.dev.vars` (file mẫu `.dev.vars.example` đã có dòng này). Script đọc `STAFF_TOKEN` từ biến môi trường, nếu không có thì đọc từ `apps/server/.dev.vars`.

### Bước 3: chạy runner

Chạy runner từ một terminal bình thường, không phải từ trong Claude Code:

```bash
cd apps/runner
python3 -m runner.main status     # kiểm tra tài khoản Claude và báo trạng thái lên server
python3 -m runner.main run        # hỏi server có việc liên tục; Ctrl-C lần 1 chờ việc đang chạy, lần 2 dừng hẳn
```

Lệnh `python3 -m runner.main once` chỉ xử lý một việc rồi thoát, tiện để thử từng bước.

### Bước 4: chạy console và desktop

```bash
pnpm dev:console      # http://localhost:5173
pnpm dev:desktop      # cửa sổ Electron mở http://localhost:5173
```

Trong màn hình Cài đặt của console, anh nhập `STAFF_TOKEN` từ `apps/server/.dev.vars`. Khi console chạy trên trình duyệt, token được lưu dạng chữ thường trong localStorage, nên chỉ dùng cách này trên máy dev. Trong Electron, token được mã hóa bằng `safeStorage`.

Muốn mở bản build thay cho dev server thì chạy `pnpm -C apps/console build` rồi `pnpm -C apps/desktop start`.

### Chạy việc định kỳ (cron) bằng tay

Server có một cron chạy mỗi phút. Cron gửi tin cảm ơn và tin hỏi thăm sau buổi làm, chuyển cho nhân viên những việc runner bỏ dở, và gửi lại các webhook chưa xử lý. Trong lượt chạy thử, tôi gọi cron bằng tay:

```bash
curl "http://127.0.0.1:8787/__scheduled?cron=*+*+*+*+*"
```

Tôi chưa kiểm tra `wrangler dev` có tự chạy cron mỗi phút hay không, nên khi cần cron chạy ngay thì anh gọi lệnh trên.

## Giả lập khách nhắn Zalo thế nào?

Script `scripts/simulate_zalo.py` tạo một webhook Zalo giả, ký bằng khóa trong `.dev.vars` rồi gửi tới server. Các lệnh dưới đây chạy ở thư mục gốc, trong lúc server đang chạy:

```bash
python3 -I scripts/simulate_zalo.py --user 1001 --text "chào em"                 # khách mới: server gửi tin xin đồng ý
python3 -I scripts/simulate_zalo.py --user 1001 --text "#dong_y_tro_ly_ai"       # khách bấm nút đồng ý
python3 -I scripts/simulate_zalo.py --user 1001 --text "Gội đầu thư giãn bao nhiêu tiền em"
python3 -I scripts/simulate_zalo.py --user 1001 --text "hi" --repeat 2           # gửi trùng một webhook
python3 -I scripts/simulate_zalo.py --user 1001 --text "#gap_nhan_vien"          # khách bấm nút gặp nhân viên
```

Sau khi khách nhắn, server chờ 10 giây rồi mới tạo việc cho runner, và runner cần thêm khoảng 20 đến 60 giây để soạn bản nháp. Anh xem kết quả trên console, hoặc gọi staff API:

```bash
ST=$(grep ^STAFF_TOKEN= apps/server/.dev.vars | cut -d= -f2)
curl -s -H "Authorization: Bearer $ST" http://127.0.0.1:8787/staff/conversations
curl -s -H "Authorization: Bearer $ST" http://127.0.0.1:8787/staff/outbox
```

Chế độ trả lời mặc định là `approve_each`: mỗi bản nháp chờ nhân viên duyệt rồi mới gửi. Muốn bản nháp tự gửi khi qua bước kiểm, anh phải đặt cả cờ chung `auto_reply_mode` và chế độ riêng của hội thoại thành `auto_allowed`. Server lấy mức thấp hơn trong hai giá trị, nên chỉ đổi chế độ riêng của hội thoại thì bản nháp vẫn chờ duyệt.

Tin cảm ơn và tin hỏi thăm sau buổi làm chỉ được gửi khi đủ các điều kiện dưới đây. Server kiểm các điều kiện theo đúng thứ tự này trong `runFollowupJob` (`apps/server/src/scheduler/followups.ts`):

- Cờ `scheduled_sends_enabled` là `true` (mặc định `false`) và cờ `outbound_enabled` là `true`. Khi một trong hai cờ là `false`, tin nằm chờ ở trạng thái `queued`, kể cả khi đã qua giờ gửi dự kiến.
- Lúc server xét tin, giờ gửi dự kiến (`run_at`) chưa qua quá 6 giờ (`max_lateness_ms`). Tin trễ hơn 6 giờ chuyển sang `expired` với `last_error` là `too_late`, và server không gửi tin đó nữa. Vì vậy, nếu anh ghi một buổi làm của nhiều ngày trước rồi mới bật `scheduled_sends_enabled`, anh sẽ không thấy tin cảm ơn nào: tin đó hết hạn ngay ở lượt chạy đầu tiên sau khi hai cờ cho phép gửi. Mục "Buổi làm, số tiền, kỹ thuật viên và quyền lợi vào hệ thống bằng cách nào?" của `docs/rooms.md` và mục 14.5 của `docs/contracts.md` mô tả quy tắc này.
- Giờ Việt Nam nằm trong khung 09:00–19:00. Biến `PROACTIVE_SEND_HOURS` đổi được khung này. Ngoài khung giờ, server dời tin sang đầu khung kế tiếp.
- Khách còn trong hệ thống, không phải người chưa đủ tuổi (`minor_flag`), và không phải liên hệ nội bộ. Liên hệ nội bộ là người có vai trò quản lý hoặc nhân viên, theo nhãn Zalo `Quản lý`, `Nhân viên` hoặc theo vai trò nhân viên đặt riêng cho liên hệ đó.
- Hội thoại không ở trạng thái `staff_takeover`, `handoff_requested` hay `blocked`, và không có yêu cầu chuyển nhân viên đang mở.
- Khách đã đồng ý nhận tin chăm sóc `followup_care`, và không có yêu cầu ngừng nhận tin nào mới hơn lần đồng ý đó.
- Server có mẫu tin cho kênh của khách: bản chat của mẫu với Zalo cá nhân, hoặc mã mẫu ZBS đã duyệt trong `ZALO_TEMPLATE_IDS` với Zalo OA ở chế độ `ZALO_MODE=real`. Thiếu mẫu thì tin chuyển sang `needs_staff` và không được gửi.

Hiện chưa có luồng nào ghi nhận đồng ý `followup_care`. Trong lượt chạy thử, tôi thêm dòng đồng ý trực tiếp vào D1 local để thử trường hợp gửi được.

Từ 12/11/2026, mỗi hội thoại có thêm công tắc Tự động trả lời trên console (`PUT /staff/conversations/:id/auto-reply`). Khi công tắc bật, bản nháp tự gửi mà không cần đổi chế độ trả lời chung, trừ khi chế độ trả lời chung là `off`. Các trường hợp bản nháp vẫn chờ duyệt nằm trong `docs/rooms.md`.

## Phòng hai bot chạy thế nào trên máy local?

Phòng hai bot là cách soạn bản nháp thứ hai của runner, có từ 12/11/2026. Mỗi hội thoại Zalo cá nhân của một khách đã đồng ý trò chuyện với trợ lý AI có một phòng chat riêng trên OpenMausBot. Hai bot làm việc trong phòng đó: Bot dịch vụ viết câu trả lời, Bot khách hàng đọc hồ sơ khách. Runner kiểm câu trả lời rồi gửi về server như một bản nháp bình thường. `docs/rooms.md` giải thích hai bot biết gì và một lượt trả lời diễn ra thế nào.

OpenMausBot là gói npm `openmausbot` bản 0.1.154, cài trong thư mục `tools/openmausbot` của dự án, không cài vào toàn máy. Các thông số anh cần biết:

| Mục | Giá trị |
|---|---|
| Địa chỉ | `http://127.0.0.1:8799`, chỉ mở trên máy này |
| Thư mục dữ liệu | `~/.thomhouse-bot/openmausbot` (theo `THOMHOUSE_BOT_HOME`); runner ghi `config.json` vào đây |
| Log | `~/.thomhouse-bot/logs/openmausbot.log`, quyền 600 |
| File của runner | `~/.thomhouse-bot/rooms/`: `credentials.json` (token của runner, quyền 600), `team.json`, `state.json`, `tools.json`, một file cho mỗi phòng, thư mục `tickets/` và `work/` |
| File quy tắc của Bot dịch vụ | `~/.thomhouse-bot/rooms/work/lead/CLAUDE.md` cho việc riêng của bot, và `~/.thomhouse-bot/openmausbot/workspaces/<mã Bot dịch vụ>/CLAUDE.md` cho lượt trả lời trong phòng; cả hai quyền 600 |
| Node.js | 24 trở lên, chỉ cho OpenMausBot |

File log của OpenMausBot có mã ghép nối. Theo README của OpenMausBot, mã ghép nối dùng để nối một điện thoại vào OpenMausBot; mã dùng một lần và hết hạn sau 5 phút. Anh không gửi file log này cho ai và không dán nội dung file vào chat. Script khởi động không in file này ra màn hình.

### OpenMausBot được bật thế nào?

`scripts/start_local.sh` lo việc này ở bước `6/9`. Bước này không bắt buộc: mỗi lỗi chỉ in một dòng, rồi các phần khác vẫn chạy như trước.

1. Nếu không có `tools/openmausbot`, script bỏ qua bước này. Nếu có `tools/openmausbot/package.json` mà chưa có `node_modules`, script cài đúng bản ghi trong file đó và ghi log vào `openmausbot-install.log`.
2. Script tìm Node.js 24 trở lên trong `PATH` và trong `~/.nvm/versions/node`, bằng lệnh `cd apps/zalo-bridge && python3 -m bridge.main rooms-node`. Lệnh này in thư mục của Node tìm được, hoặc thoát với mã 1 khi máy không có.
3. Script chạy `cd apps/runner && python3 -m runner.main rooms-setup`. Lệnh này ghi `config.json` cho OpenMausBot (mỗi tài khoản Claude của runner một mục) và file `credentials.json` cho chương trình cấp công cụ của hai bot. Kết quả lệnh nằm trong `runner.log`.
4. Script bật `openmausbot serve --port 8799 --data-dir ~/.thomhouse-bot/openmausbot --label thomhouse --no-open` trong một môi trường sạch, không có token nào của runner hay của Claude. Script không truyền tùy chọn nào mở OpenMausBot ra ngoài máy (đường hầm, mạng LAN, relay hay tên miền).
5. Script chờ tối đa 60 giây (đổi bằng biến `THOMHOUSE_ROOMS_WAIT_S`) cho tới khi OpenMausBot nhận kết nối ở cổng mạng 8799. Quá thời gian đó, script dừng OpenMausBot và bật các phần khác mà không có phòng. Nếu một chương trình khác đang dùng cổng 8799, script để nguyên chương trình đó và không bật OpenMausBot.
6. Khi OpenMausBot đã chạy, runner nhận đúng thư mục Node, thư mục dữ liệu và đường dẫn OpenMausBot mà script vừa dùng.

`scripts/stop_local.sh` dừng OpenMausBot sau runner và trước bridge. Lệnh `cd apps/zalo-bridge && python3 -m bridge.main doctor` có thêm dòng `room_platform`: dòng này báo OpenMausBot đã cài chưa, có Node 24 chưa, cổng 8799 có mở không và đã có file cấu hình chưa. Dòng này chỉ báo cảnh báo khi runner đang đặt `THOMHOUSE_DRAFT_ENGINE=rooms` mà thiếu một phần.

Sau mỗi lần thêm hoặc đổi tài khoản Claude của runner, anh chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh`. Khi OpenMausBot đang chạy, `start_local.sh` không ghi lại cấu hình, và chưa biết OpenMausBot có tự đọc lại cấu hình hay không.

### File quy tắc của Bot dịch vụ nằm ở đâu?

Bộ quy tắc trả lời của server dài khoảng 39 đến 43 KB, hơn giới hạn 24.000 byte mà OpenMausBot cho phần chỉ dẫn của một bot. Vì vậy runner ghi bộ quy tắc vào file `CLAUDE.md`, file chỉ dẫn mà Claude Code đọc trong thư mục làm việc. Lượt chạy thử chiều 12/11 cho thấy OpenMausBot chạy lượt trả lời trong phòng ở thư mục `~/.thomhouse-bot/openmausbot/workspaces/<mã bot>`, không ở thư mục `work/lead` mà runner khai cho Bot dịch vụ. Vì Bot dịch vụ không thấy file quy tắc, bot trả lời bằng mã `KHONG-CO-QUY-TAC` ở mọi lượt, và runner phải soạn lại bằng `claude -p` (dòng `rules_not_loaded` trong `runner.log`). Khi file được chép tay sang thư mục của OpenMausBot, hai bot soạn được câu trả lời.

Từ tối 12/11, runner tự ghi cùng bộ quy tắc vào cả hai thư mục. Sau mỗi lần cài đặt hai bot lên OpenMausBot, runner hỏi OpenMausBot mã của Bot dịch vụ bằng lệnh `bots --json`; khi lệnh này lỗi, runner đọc file `~/.thomhouse-bot/openmausbot/bots.json` mà không sửa file đó. Runner chỉ ghi file khi nội dung khác, và xóa bản chép của bộ quy tắc ở thư mục của các bot khác. Khi không tìm được Bot dịch vụ, lượt đó đi theo `ROOM_FALLBACK` (mặc định soạn bằng `claude -p`), và lượt sau runner cài lại hai bot. Bản sửa có test với OpenMausBot giả. Runner trên máy Mac chưa được khởi động lại sau bản sửa, nên file trong thư mục của OpenMausBot vẫn là bản chép tay; runner mới giữ nguyên file đó khi nội dung trùng.

### Bật phòng hai bot thế nào?

Hai bot chỉ soạn bản nháp khi đủ bốn điều kiện:

1. OpenMausBot đang chạy (bước `6/9` ở trên báo đã chạy).
2. Migration `0010_rooms_roles_customer.sql` đã được áp. Khi chưa áp, server coi như phòng đang tắt.
3. `apps/runner/.env` có dòng `THOMHOUSE_DRAFT_ENGINE=rooms`, và anh đã chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh` để runner đọc lại file.
4. Cờ `rooms_enabled` là `true`. Anh đổi cờ ở tab Cài đặt của console, mục Phòng hai bot (`rooms_enabled`), hoặc bằng lệnh:

```bash
ST=$(grep ^STAFF_TOKEN= apps/server/.dev.vars | cut -d= -f2)
curl -s -X PUT -H "Authorization: Bearer $ST" -H "content-type: application/json" \
  -d '{"rooms_enabled": true}' http://127.0.0.1:8787/staff/flags
```

Phòng chỉ dùng cho hội thoại Zalo cá nhân. Khách giả của `simulate_zalo.py` là khách Zalo OA, nên ở chế độ mock runner luôn soạn bằng `claude -p`, kể cả khi đủ bốn điều kiện trên.

Các biến khác của runner, ghi trong `apps/runner/.env` (lệnh `python3 -m bridge.main init-env` ghi sẵn các dòng này dưới dạng chú thích, kèm giá trị mặc định):

| Biến | Mặc định | Việc biến đó làm |
|---|---|---|
| `ROOM_TURN_TIMEOUT_S` | 240 | Số giây tối đa cho một lượt trả lời trong phòng |
| `ROOM_OBSERVE_EVERY_S` | 30 | Cứ chừng ấy giây, runner chép vào phòng các tin không cần bot trả lời (ví dụ tin lễ tân tự gửi), để hai bot có bối cảnh; `0` tắt việc này |
| `ROOM_FALLBACK` | `claude` | Khi một lượt trong phòng lỗi: `claude` soạn lại bằng `claude -p`; `fail` báo lỗi cho server, và server chuyển hội thoại cho nhân viên |
| `ROOM_REQUIRE_PROFILE_READ` | 1 | `1`: runner loại câu trả lời khi Bot khách hàng chưa đọc hồ sơ trong lượt đó |
| `ROOM_CUSTOMER_MODEL` | trống | Model của Bot khách hàng; để trống thì dùng model của Bot dịch vụ |
| `OPENMAUSBOT_BIN`, `OPENMAUSBOT_DATA_DIR`, `OPENMAUSBOT_NODE_DIR` | đường dẫn mặc định ở trên | Đường dẫn OpenMausBot, thư mục dữ liệu, thư mục Node 24; khi OpenMausBot chạy qua `start_local.sh`, script đặt ba biến này cho runner |

### Tắt phòng hai bot thế nào?

Cách nhanh là đổi cờ `rooms_enabled` về `false` trên console. Runner đọc cờ ở mỗi lượt, nên từ lượt sau runner soạn bằng `claude -p`, không cần khởi động lại. Việc chép tin vào phòng cũng dừng; runner hỏi lại cờ mỗi 5 phút. Cách thứ hai là đổi dòng trong `apps/runner/.env` thành `THOMHOUSE_DRAFT_ENGINE=claude` rồi chạy `scripts/stop_local.sh` và `scripts/start_local.sh`.

Sau khi tắt, lượt đầu tiên của một hội thoại từng có phòng bắt đầu một phiên Claude mới, vì `claude -p` không mở lại được phiên của phòng.

### Khi OpenMausBot không chạy thì sao?

Nếu cờ `rooms_enabled` là `false`, runner không gọi OpenMausBot và mọi thứ chạy như trước. Nếu cờ là `true` và runner đặt `THOMHOUSE_DRAFT_ENGINE=rooms`, mỗi lượt trả lời thử gọi OpenMausBot trước. Khi lệnh gọi lỗi, runner làm theo `ROOM_FALLBACK`: với giá trị mặc định `claude`, runner soạn lại bằng `claude -p`, và lễ tân vẫn nhận bản nháp, chỉ chậm hơn. Với `fail`, việc soạn nháp bị báo lỗi và hội thoại có yêu cầu chuyển nhân viên. Khi `start_local.sh` không bật được OpenMausBot, script in một dòng nhắc lại điều này.

Lệnh `python3 -m runner.main forget <mã hội thoại>` xóa thư mục làm việc, file phiên và file phòng của hội thoại đó trong `~/.thomhouse-bot`. Lệnh này không xóa phòng trên OpenMausBot, nơi vẫn giữ bản chép tin nhắn của khách.

## Đồng bộ nhãn Zalo và nhập lịch sử buổi làm bằng lệnh nào?

Lệnh đồng bộ nhãn đọc ba nhãn Khách hàng, Quản lý, Nhân viên của tài khoản Zalo cá nhân rồi gửi vai trò lên server (`POST /staff/roles/import`). Lệnh cần zalo-agent đã đăng nhập, nên chỉ dùng được ở chế độ Zalo cá nhân:

```bash
cd apps/zalo-bridge
python3 -m bridge.main sync-labels --dry-run   # đọc nhãn và in số đếm, không gửi gì
python3 -m bridge.main sync-labels             # đọc nhãn và gửi vai trò lên server
```

Lệnh chỉ in số đếm, không in tên nhãn, tên người hay mã nào. Mã thoát 0 là đồng bộ xong (hoặc chạy thử đọc được nhãn), 1 là zalo-agent hoặc server lỗi, 2 là không tìm thấy `STAFF_TOKEN`. Lệnh lấy `STAFF_TOKEN` từ biến môi trường, nếu không có thì từ `apps/server/.dev.vars`; token đọc từ `.dev.vars` chỉ được gửi tới server trên máy này. Khi zalo-agent lỗi, lệnh không gửi gì, nên server không xóa vai trò nào. Bridge (`python3 -m bridge.main run`) tự chạy việc đồng bộ này khi bật và cứ `LABEL_SYNC_EVERY_S` giây một lần; biến này nằm trong `apps/zalo-bridge/.env`, mặc định 900, `0` tắt việc tự đồng bộ.

Script nhập lịch sử buổi làm đọc một file CSV và gửi từng phần tối đa 2 000 dòng tới `POST /staff/visits/import`. Anh chạy ở thư mục gốc của dự án, trong lúc server đang chạy:

```bash
python3 -I scripts/import_visits.py lich-su.csv                    # chạy thử: số đếm và các dòng không nhập được
python3 -I scripts/import_visits.py lich-su.csv --apply            # chạy thử, rồi ghi thật
python3 -I scripts/import_visits.py lich-su.csv --column amount="Thực thu" --date-order mdy
```

Script luôn chạy thử trước; chỉ với `--apply` script mới gửi lần thứ hai để ghi. Màn hình chỉ có số đếm, số dòng theo cách bảng tính đánh số và mã lý do, không có giá trị ô nào. `--column TÊN_TRƯỜNG=TÊN_CỘT` chỉ cho script cột nào chứa trường nào khi tên cột lạ, `--header-row N` dùng khi file có dòng tiêu đề phía trên tên cột, `--date-order mdy` dùng khi ngày viết tháng trước, `--delimiter` đặt ký tự ngăn cột. Script lấy `STAFF_TOKEN` và `SERVER_URL` như lệnh đồng bộ nhãn và từ chối gửi tới server không nằm trên máy này. Mã thoát 0 là đọc được file và server trả lời mọi phần; 1 là mọi trường hợp khác. Gửi lại cùng một file là an toàn, vì server bỏ qua buổi làm đã có. Các cột script đọc được và các lý do bị từ chối nằm ở đầu file `scripts/import_visits.py`.

## Đoán buổi làm từ tin nhắn cũ bằng lệnh nào?

Script `scripts/analyze_visits.py` đọc kho tin nhắn cũ của zalo-agent (`~/.zalo-agent-cli/accounts/<id tài khoản Zalo>/zalo.db`) ở chế độ chỉ đọc. Từ đó script đoán các lần khách đến, lịch hẹn sắp tới, số tiền, kỹ thuật viên, số điện thoại và gói nhiều buổi hoặc voucher của từng khách. Server lưu các phỏng đoán này trong các bảng của migration 0011, riêng với buổi làm do nhân viên ghi; `docs/rooms.md` giải thích cách console hiện chúng. Script cần Python 3.11 trở lên: ngày 12/11, `/usr/bin/python3` bản 3.9.6 của macOS không nạp được script. Anh chạy ở thư mục gốc của dự án:

```bash
python3 -I scripts/analyze_visits.py --dry-run                      # chỉ in số đếm, không ghi file, không gửi gì
python3 -I scripts/analyze_visits.py                                # ghi ~/.thomhouse-bot/profiles/visits-<ngày>-<giờ>.json
python3 -I scripts/analyze_visits.py --push                         # ghi file rồi gửi tới POST /staff/chat-facts/import
python3 -I scripts/analyze_visits.py --dry-run --now "2026-11-12 10:00" --db /đường/dẫn/zalo.db --owner-id 123
```

Các tùy chọn khác: `--since YYYY-MM-DD` chỉ đọc tin từ ngày đó, `--out-dir` đổi thư mục ghi file, `--server-url` đổi server, `--catalog` đổi file danh mục dịch vụ (mặc định `data/services.json`). `--now` đặt thời điểm phân tích; lịch hẹn sau thời điểm này là lịch sắp tới. Script lấy `STAFF_TOKEN` và `SERVER_URL` như lệnh đồng bộ nhãn, và từ chối gửi tới server không nằm trên máy này. File kết quả có quyền 600 trong thư mục quyền 700.

Màn hình chỉ có số đếm. Ngày 12/11, lệnh chạy thử trên kho tin giả mà test của server dùng (dựng bằng `apps/server/test/fixtures/analyzer-cache.py`, với `--now '2026-11-12 10:00'`) in ra:

```
customer conversations analyzed: 4 (skipped: family 1)
  visits found: 5 (high 4, medium 0, low 1); upcoming bookings: 1; cancelled or no-show: 1
  customers with at least one visit (high or medium): 3
  visits with a service: 5; with a time: 5; with an amount: 4; with a technician: 1
  phone numbers found: 2 (high 2, medium 0)
  packages or vouchers found: 1
  model pass: off
dry run: nothing written, nothing pushed
```

`high`, `medium` và `low` là ba mức chắc chắn mà console ghi là chắc, khá chắc và chưa chắc. Khi không có `--dry-run`, dòng cuối là `written: <đường dẫn> (mode 600)`. Với `--push`, script gửi từng phần 100 khách và in thêm dòng `pushed:` với tám số đếm của server (`customers`, `visits_imported`, `visits_updated`, `visits_removed`, `visits_kept_staff`, `phones_set`, `benefits_upserted`, `unmatched`); ý nghĩa từng số nằm trong `docs/chay-local-zalo-ca-nhan.md`. Mã thoát 0 là xong. Mã 1 là không đọc được kho tin, không ghi được file, server lỗi hoặc lỗi khác; khi server trả 404, script báo server chưa có API nhận kết quả. Mã 2 là tùy chọn sai hoặc biến `PROFILE_LLM_*` sai.

Lượt nhờ Claude đọc lại tin nhắn mặc định tắt. Năm biến môi trường điều khiển lượt này:

| Biến | Mặc định | Việc biến đó làm |
|---|---|---|
| `PROFILE_LLM_ENABLED` | `false` | `true` bật lượt nhờ Claude đọc lại tin nhắn |
| `PROFILE_LLM_SCOPE` | `consented` | `consented`: chỉ gửi tin của khách mà server liệt kê là đã đồng ý trò chuyện với trợ lý AI (`GET /staff/chat-facts/eligible`). `customers`: gửi mọi cuộc trò chuyện mà script hồ sơ liên hệ đoán là khách ở mức vừa hoặc cao. Giá trị khác làm script thoát với mã 2 |
| `PROFILE_LLM_MODEL` | `claude-sonnet-5-5` | Model dùng cho `claude -p` |
| `PROFILE_LLM_MAX_CALLS` | 40 | Số lần gọi `claude -p` tối đa trong một lần chạy |
| `PROFILE_LLM_TIMEOUT_S` | 180 | Số giây tối đa cho một lần gọi |

Khi `PROFILE_LLM_SCOPE=consented` mà server không trả lời, script bỏ lượt đọc bằng Claude cho mọi khách và vẫn giữ kết quả của các quy tắc. `--dry-run` cùng `PROFILE_LLM_ENABLED=true` chỉ đếm số khách và số lần gọi sẽ có, không gọi Claude. Lượt này đi qua danh sách tài khoản Claude của runner (`scripts/runner/claude_pool.py`), không có công cụ, không đọc file chỉ dẫn và chạy trong một thư mục tạm bị xóa sau mỗi lần gọi. Lượt này chưa chạy với Claude thật lần nào.

Từ tối 12/11, khi một lần gọi `claude -p` lỗi, `claude_pool.py` chỉ ghi loại lỗi vào `~/.thomhouse-bot/account-state.json`: `limited`, `login_expired`, `blocked`, `timeout`, `cli_error` hoặc `parse_error`. Trước đó, file này giữ tới 300 ký tự của nội dung lỗi, có thể chép lại tin nhắn của khách, và file có quyền 644. Giờ `accounts.json` và `account-state.json` có quyền 600. Nội dung lỗi cũ trong file được rút gọn thành loại lỗi ở lần ghi sau.

## Chạy test thế nào?

```bash
pnpm test                    # server, console (typecheck và test), runner, bridge, các script trong scripts/
pnpm check:desktop           # kiểm cú pháp main.js và preload.js của Electron
pnpm -C apps/console build   # build console
```

`pnpm test` chạy `pnpm -C apps/server test`, lệnh này tạo lại file `apps/server/src/seed-data.ts` trước khi chạy test. Muốn chạy riêng từng phần mà không tạo lại file đó, anh dùng các lệnh sau ở thư mục gốc của dự án:

```bash
pnpm -C apps/server exec vitest run      # server
pnpm -C apps/server typecheck
pnpm -C apps/console typecheck && pnpm -C apps/console test
(cd apps/runner && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .)        # runner
(cd apps/zalo-bridge && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .)   # bridge
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/tests -t scripts/tests        # script
```

Tối 12/11/2026, lúc 18:01, sau các bản sửa của buổi tối, tôi chạy năm bộ test bằng đúng các lệnh trên, với Node 24 đứng đầu `PATH`. Cả năm bộ đều qua:

| Bộ test | Dòng kết quả cuối |
|---|---|
| Server | `Test Files  34 passed (34)`, `Tests  457 passed (457)` |
| Console | `Test Files  6 passed (6)`, `Tests  168 passed (168)` |
| Runner | `Ran 134 tests in 102.120s`, `OK` |
| Bridge | `Ran 152 tests in 99.547s`, `OK` |
| Script | `Ran 506 tests in 44.420s`, `OK` |

Các test của ngày 12/11 nằm ở các file sau:

| Phần | File test |
|---|---|
| Server | `test/` các file `migration-0010`, `roles`, `customer-status`, `customer-summary`, `visits-import`, `benefits-visits`, `auto-reply`, `internal-contact`, `rooms-feed`, `customer-profile-tool`, `pipeline-missing-0010`, `migration-0011`, `chat-facts-import`, `chat-facts-decisions`, `chat-facts-summary`, `chat-facts-review`, `chat-facts-analyzer-document`, `followup-lateness`, cùng đuôi `.test.ts` |
| Runner | `tests/test_rooms.py`, `tests/test_room_tools.py`, `tests/test_runner_jobs.py` |
| Bridge | `tests/test_labels.py`, `tests/test_rooms.py`, `tests/test_local_scripts.py` |
| Script | `scripts/tests/test_import_visits.py`, `test_visit_rules.py`, `test_contact_facts_rules.py`, `test_visit_model_pass.py`, `test_analyze_visits.py` |
| Console | `src/ConversationSettings.test.tsx`, `src/CustomerSummary.test.tsx`, `src/ChatFacts.test.tsx` |

Test của runner dùng một OpenMausBot giả (`apps/runner/tests/fake_bin/openmausbot`), test của bridge dùng zalo-agent giả, test nhập buổi làm dùng server giả, và test của `scripts/analyze_visits.py` dùng một `claude` giả (`scripts/tests/fake_bin_visits/claude`).

Bốn file test của `scripts/analyze_visits.py` từng có tên bắt đầu bằng `wip_`, để lệnh test mặc định không chạy chúng trong lúc làm. Từ tối 12/11, các file này đổi tên thành `test_*.py`, nên lệnh test của script ở trên chạy cả bốn file.

Một số test có đo thời gian, nên có thể trượt khi máy đang tải nặng. Test runner `test_runs_jobs_concurrently_up_to_cap` từng trượt một lần với 3,88 giây so với giới hạn 3,8 giây, khi load average của máy là 151, rồi qua ở lần chạy sau. Trước tối 12/11, file `test/rooms-feed.test.ts` của server cũng từng trượt khi máy tải nặng: một test vượt giới hạn 5 giây, và một test nhận nhầm việc của hội thoại khác. Tối 12/11, các test của file này được sửa để không còn phụ thuộc thời điểm, và file qua năm lần chạy liên tiếp. Ba test về thời gian xử lý tin rất dài của `scripts/analyze_visits.py` giờ đo thời gian CPU thay vì thời gian thực.

## Phần nào đang giả và phần nào chưa thử?

Phần đang giả khi chạy local:

- Mọi lần gửi tin cho khách: ở `ZALO_MODE=mock`, server ghi nguyên request sẽ gửi Zalo vào bảng `outbox` và không gọi Zalo.
- Webhook từ Zalo: `simulate_zalo.py` tạo và ký webhook theo công thức trong tài liệu Zalo.
- Hồ sơ khách Zalo: chế độ mock trả hồ sơ giả, nên tên khách hiện là "Khách 1001".
- Mã mẫu tin ZBS: chế độ mock dùng `mock_tpl_thank_you`, `mock_tpl_check_in` thay cho mã mẫu Zalo đã duyệt.

Phần chưa thử:

- Official Account Zalo thật: chưa gửi hay nhận tin nào qua OA thật.
- Chữ ký webhook: hai phía trong codebase khớp nhau, nhưng chưa đối chiếu với webhook do Zalo thật gửi.
- Làm mới access token Zalo và luồng cấp quyền OAuth: chưa chạy với Zalo thật; cặp token đầu tiên phải nạp bằng tay.
- Duyệt mẫu tin ZBS: chưa có mẫu nào được Zalo duyệt, nên tin cảm ơn và tin hỏi thăm chưa gửi được ở chế độ thật.
- Deploy lên Cloudflare: chưa tạo D1 thật (`database_id` trong `wrangler.toml` vẫn là giá trị giữ chỗ) và chưa deploy.
- Lưu token trong Electron: chưa thử lưu rồi đọc lại token bằng `safeStorage`.
- Console với server thật trên trình duyệt: tôi mở được console ở `http://localhost:5173` nhưng chưa đăng nhập bằng staff token, nên chưa xem màn hình hội thoại hiển thị bản nháp thật. Tôi chỉ xác nhận staff API qua proxy của Vite trả đúng các trường mà console dùng.
- Phần của ngày 12/11/2026. Chiều 12/11, một lượt chạy thử trên máy Mac dùng `scripts/start_local.sh` để áp các migration tới 0011 vào `~/.thomhouse-bot/d1` (sau khi sao lưu), rồi chạy hệ thống ở chế độ Zalo cá nhân với zalo-agent giả, OpenMausBot thật và một khách giả. Trong lượt đó, hai bot soạn được câu trả lời sau khi file quy tắc của Bot dịch vụ được chép tay; công tắc Tự động trả lời, việc chép tin vào phòng, nhãn Zalo (với dữ liệu nhãn giả), khối Tóm tắt khách hàng và `scripts/analyze_visits.py --push` đều chạy đúng. `docs/chay-local-zalo-ca-nhan.md` kể chi tiết lượt chạy thử này. Phần chưa thử: một tin nhắn qua Zalo thật; console trên trình duyệt; bản sửa file quy tắc của Bot dịch vụ với OpenMausBot thật; lượt nhờ Claude đọc lại tin nhắn của `scripts/analyze_visits.py`; lệnh đồng bộ nhãn với Zalo thật; script nhập buổi làm với server thật; `scripts/stop_local.sh` khi OpenMausBot đang chạy. Danh sách đầy đủ nằm ở mục "Điểm yếu đã biết" của `docs/rooms.md`.

## Những lỗi dễ gặp khi chạy local

**Runner khởi động từ trong Claude Code.** Phiên Claude Code đặt sẵn `CLAUDE_EFFORT=high` và nhiều biến `CLAUDE_CODE_*`. Runner giờ chỉ đọc `THOMHOUSE_CLAUDE_EFFORT`, nên mức effort không còn bị ghi đè. Tuy vậy, tiến trình `claude -p` con vẫn thừa hưởng các biến `CLAUDE_CODE_*` của phiên cha. Nếu buộc phải chạy runner từ trong Claude Code, anh dùng môi trường sạch:

```bash
env -i HOME="$HOME" USER="$USER" PATH="$PATH" LANG=en_US.UTF-8 \
  THOMHOUSE_BOT_HOME=... SERVER_URL=http://127.0.0.1:8787 RUNNER_ID=mac-dev-1 RUNNER_TOKEN=... \
  python3 -m runner.main run
```

**Hai migration cùng số 0002.** Thư mục `apps/server/migrations` có `0002_server_core.sql` và `0002_zalo_outbox_dedupe.sql`. Wrangler áp theo thứ tự tên file và lượt chạy thử áp đủ ba file không lỗi.

**Hội thoại có nhãn "cần chú ý" mà không có việc gì.** Trước lượt tích hợp, server bật cờ `needs_attention` trong nhiều đoạn code nhưng chỉ tắt khi nhân viên trả hội thoại lại cho bot. Giờ server tính lại cờ này sau mỗi lần nhân viên duyệt, từ chối, gửi tay hoặc đánh dấu đã xử lý. Cờ vẫn bật khi còn bản nháp chờ duyệt, còn yêu cầu chuyển nhân viên đang mở, hội thoại đang ở `handoff_requested`, hoặc khách có tin chưa ai trả lời mà không có việc nào đang soạn.

## Nói ngắn gọn nhất

Anh tạo `.dev.vars`, áp migration, chạy `pnpm dev`, nạp catalog bằng `seed_dev.py`, đăng ký tài khoản Claude vào danh sách của runner, rồi chạy runner từ một terminal bình thường. Sau đó anh dùng `simulate_zalo.py` để đóng vai khách và xem kết quả trên console hoặc staff API. Mọi tin "đã gửi" chỉ nằm trong bảng `outbox`. Zalo thật, chữ ký webhook thật, mẫu tin ZBS và việc deploy lên Cloudflare đều chưa được thử. Phòng hai bot là phần không bắt buộc: phòng chỉ chạy khi OpenMausBot đang chạy với Node 24, runner đặt `THOMHOUSE_DRAFT_ENGINE=rooms` và cờ `rooms_enabled` là `true`, và chỉ cho hội thoại Zalo cá nhân. Đổi cờ về `false` là tắt phòng ngay từ lượt sau; khi phòng lỗi, runner soạn lại bằng `claude -p`. Từ tối 12/11, runner tự ghi file quy tắc của Bot dịch vụ vào thư mục mà OpenMausBot dùng cho lượt trả lời trong phòng; bản sửa này mới chạy với OpenMausBot giả. `scripts/analyze_visits.py` đoán buổi làm, số tiền, số điện thoại và gói từ tin nhắn cũ. Script cần migration 0011 và Python 3.11. Script chỉ in số đếm và chỉ gửi kết quả tới server local khi có `--push`.

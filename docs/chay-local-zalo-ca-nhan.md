# Chạy chatbot thom house bằng Zalo cá nhân

## Phần anh cần đọc trước

Chatbot thom house giờ chạy trên máy Mac của anh và trả lời khách qua một tài khoản Zalo cá nhân, không qua Zalo OA. Phần đi ra ngoài máy là lời gọi model của Claude và việc gửi, nhận tin qua Zalo. Ứng dụng chỉ dùng nội bộ cho studio, không bán. Model vẫn là `claude-opus-5-5` với effort `low`, gọi bằng `claude -p` trên gói Claude của anh.

Ngày 08/11/2026, tôi đã chạy `scripts/start_local.sh` thật trên máy này và chạy thử đường đi của tin nhắn từ khách tới console rồi ngược lại. Trong lượt thử, một bản zalo-agent giả đứng thay zalo-agent thật, và bản nháp được viết tay thay cho bản nháp của model. Chưa có tin nào đi qua Zalo thật, vì không ai đăng nhập tài khoản Zalo trong lượt thử.

Hai việc anh cần làm trước khi chatbot trả lời được khách thật:

1. Quét mã QR để đăng nhập tài khoản Zalo của studio. Chỉ anh làm được bước này.
2. Kiểm tra hạn mức Claude. Ngày 08/11, tài khoản Claude duy nhất của runner (`ultra-anlnt`) đã hết hạn mức tuần, tới 09:00 ngày 13/11/2026 mới dùng lại được. Trong thời gian đó, runner không soạn được bản nháp, và server chuyển mỗi câu hỏi của khách thành một yêu cầu chuyển nhân viên. Trong lượt thử, câu hỏi đầu tiên thành yêu cầu chuyển nhân viên sau 18 giây, câu hỏi sau đó sau 145 giây. Lệnh xem trạng thái: `python3 scripts/runner/claude_pool.py status`.

## Ứng dụng gồm những phần nào?

Khi khách nhắn vào tài khoản Zalo của studio, tin đi qua năm phần chạy trên máy Mac:

- listener là tiến trình `zalo-agent listen` chạy nền. Listener giữ kết nối với Zalo và chuyển từng tin khách gửi về server.
- server là Cloudflare Worker chạy local bằng `wrangler dev --local` ở `http://127.0.0.1:8787`. Server lưu hội thoại, gửi tin xin đồng ý, giao việc soạn nháp cho runner, kiểm bản nháp và xếp tin trả lời vào hàng chờ gửi (bảng `outbox`).
- runner là chương trình Python gọi `claude -p` để soạn bản nháp.
- bridge là chương trình Python lấy từng tin trong hàng chờ gửi rồi gửi cho khách bằng lệnh `zalo-agent msg send`.
- console là trang web cho nhân viên ở `http://127.0.0.1:5173`, dùng để xem hội thoại, duyệt bản nháp và xử lý yêu cầu chuyển nhân viên.

Từ ngày 12/11/2026 có thêm một phần không bắt buộc: OpenMausBot, chương trình giữ các phòng chat nơi hai bot cùng soạn bản nháp, ở `http://127.0.0.1:8799`. Phần này chỉ chạy khi máy có OpenMausBot trong `tools/openmausbot` và có Node.js 24 trở lên, và chỉ được dùng khi anh bật phòng hai bot. Khi chưa bật, runner soạn bản nháp như trước. Mục "Từ 12/11 có thêm gì?" ở dưới tóm tắt phần này.

`zalo-agent` là bộ công cụ dòng lệnh `@ardennguyen/zalo-agent-cli` bản 2.5.9. Script cài bộ công cụ này vào `tools/zalo-agent` của dự án, không cài vào toàn máy.

Tin xin đồng ý và tin cảm ơn sau khi khách đồng ý là hai tin cố định, server tự gửi. Câu trả lời do model soạn thì mặc định phải được nhân viên duyệt trên console rồi mới gửi (`auto_reply_mode = approve_each`). Server chỉ tự gửi câu trả lời của model khi anh đổi chế độ này sang `auto_allowed`, hoặc, từ 12/11, khi nhân viên bật công tắc Tự động trả lời của một hội thoại.

## Dùng zalo-agent có rủi ro gì?

Rủi ro lớn nhất là tài khoản Zalo bị khóa. zalo-agent điều khiển tài khoản cá nhân qua thư viện zca-js. Thư viện này gọi các API nội bộ của Zalo Web mà Zalo không công bố. Tác giả zalo-agent ghi trong `DISCLAIMER.md` rằng Zalo chủ động phát hiện kiểu dùng này, tài khoản có thể bị khóa vĩnh viễn, và công cụ có thể hỏng bất cứ lúc nào khi Zalo đổi API. Vì vậy, anh nên dùng một tài khoản Zalo riêng cho studio, không dùng tài khoản cá nhân chính của anh. Để giảm rủi ro, hệ thống giới hạn tốc độ gửi. Bridge chờ ít nhất 2 giây giữa hai lần gửi, cộng thêm ngẫu nhiên tới 1 giây. Server giao cho bridge tối đa 30 tin mỗi giờ; khi đã đủ 30 tin, server chỉ giao tin do nhân viên gõ hoặc duyệt. Hai tin gửi cho cùng một người cách nhau ít nhất 5 giây. Tin tự động (câu trả lời bot tự gửi, tin xin đồng ý) nằm trong hàng chờ quá 30 phút, ví dụ khi Mac ngủ qua đêm, thì không được gửi nữa mà chuyển sang lỗi để nhân viên quyết định. Chưa ai đo được Zalo khóa tài khoản ở mức gửi nào, nên các giới hạn này không bảo đảm tài khoản an toàn. Giấy phép CC-BY-NC-SA-4.0 của zalo-agent chỉ cho phép dùng phi thương mại, đúng với cách dùng local hiện nay.

## Anh chạy những lệnh nào?

Anh chạy ba bước trong Terminal, ở thư mục dự án `~/Projects/lulu-thomhouse`.

**Bước 1. Bật hệ thống.**

```bash
scripts/start_local.sh
```

Lần đầu, script cài zalo-agent, tạo token và secret ngẫu nhiên trong các file cấu hình (không in ra màn hình), rồi bật server, runner, bridge và console. Vì tài khoản Zalo chưa đăng nhập, script báo listener chưa chạy và in lệnh đăng nhập ở cuối. Nếu máy có OpenMausBot và Node.js 24, script bật cả OpenMausBot ở bước `6/9`; nếu không, script in một dòng và các phần khác vẫn chạy.

**Bước 2. Đăng nhập Zalo bằng mã QR.**

```bash
tools/zalo-agent/node_modules/.bin/zalo-agent login
```

Lệnh này hiện mã QR trong Terminal, và anh cũng xem được mã ở `http://localhost:18927/qr`. Anh mở app Zalo trên điện thoại của tài khoản studio, chọn Quét mã QR trong app (không dùng camera thường) rồi xác nhận. Mã hết hạn sau khoảng 60 giây. Đăng nhập xong, anh chạy lại `scripts/start_local.sh` để bật listener.

**Bước 3. Mở console.**

Anh mở `http://127.0.0.1:5173` trong trình duyệt, vào màn hình Cài đặt, rồi dán giá trị dòng `STAFF_TOKEN` trong file `apps/server/.dev.vars` vào ô Staff token.

## Thử bằng một tài khoản Zalo khác thế nào?

Anh dùng một tài khoản Zalo khác (điện thoại khác hoặc tài khoản phụ) và nhắn vào tài khoản của studio:

1. Nhắn "Chào em". Sau vài giây, tài khoản thử nhận tin xin đồng ý; cuối tin có hai dòng hướng dẫn nhắn "đồng ý" hoặc "gặp nhân viên". Zalo cá nhân không có nút bấm, nên khách trả lời bằng chữ.
2. Nhắn "đồng ý". Bot gửi tin cảm ơn và từ đây mới gọi model.
3. Hỏi "Gội đầu thư giãn bao nhiêu tiền em". Server chờ 10 giây sau tin cuối của khách rồi mới giao việc cho runner. Khi runner soạn xong, bản nháp hiện ở màn hình Hội thoại. Anh bấm Duyệt và gửi, và tin trả lời tới tài khoản thử sau vài giây.
4. Gửi một tấm ảnh. Bot không đọc ảnh, nên console hiện một yêu cầu chuyển nhân viên cho hội thoại này.

Nếu anh tự gõ trả lời trong hội thoại đó trên điện thoại của studio, server hiểu là nhân viên tiếp quản: bot ngừng trả lời hội thoại đó trong 12 giờ, và câu trả lời của bot còn nằm trong hàng chờ gửi bị hủy. Hết 12 giờ, hội thoại quay lại cho bot nếu khách đã đồng ý; nếu khách chưa đồng ý, hội thoại quay lại trạng thái chờ khách đồng ý. Muốn bot trả lời tiếp sớm hơn, anh bấm Trả lại cho bot trong console.

Mọi người nhắn vào tài khoản này đều được coi là khách, kể cả bạn bè hay người nhà. Mỗi người chỉ nhận tin xin đồng ý một lần; nếu người đó không trả lời, 30 ngày sau mới nhận lại. Người mà anh nhắn trước từ điện thoại của studio thì không nhận tin xin đồng ý, và bot cũng không trả lời người đó. Chữ "đồng ý" chỉ được tính là đồng ý khi tin xin đồng ý đã tới khách trong 24 giờ trước đó và chưa có tin nào khác gửi cho khách sau tin xin đồng ý.

Từ 12/11, cách dễ nhất để bot bỏ qua người làm ở studio là gắn nhãn Quản lý hoặc Nhân viên cho cuộc trò chuyện với người đó trong app Zalo (mục "Từ 12/11 có thêm gì?" ở dưới). Ngoài ra, anh có hai cách để bot bỏ qua một người không phải khách. Cách thứ nhất là bấm Không phải khách (chỉ nhân viên trả lời) trong màn hình Hội thoại: tin của người đó vẫn hiện trên console, nhưng bot không trả lời, không gửi tin xin đồng ý và không tạo yêu cầu chuyển nhân viên. Nếu bấm nhầm, anh bấm Trả lại cho bot. Cách thứ hai là ghi mã Zalo của người đó (phần sau `p:` ở dòng Zalo id trong console) vào biến `ZALO_PERSONAL_IGNORE_THREADS` trong `apps/server/.dev.vars`, các mã cách nhau bằng dấu phẩy, rồi chạy `scripts/stop_local.sh` và `scripts/start_local.sh`. Với cách này, server bỏ hẳn tin của người đó, không lưu và không hiện trên console. Dùng một tài khoản riêng cho studio vẫn là cách an toàn nhất.

## Khi không rõ tin đã tới khách hay chưa thì làm gì?

Bridge ghi một tin là `unknown` khi không biết tin đó đã tới khách hay chưa, ví dụ zalo-agent chạy quá 30 giây. Server không tự gửi lại tin `unknown`, để khách không nhận một tin hai lần. Anh mở Cài đặt, kéo xuống mục Hộp thư gửi đi (Zalo cá nhân), xem hội thoại trên điện thoại của studio, rồi chọn một trong hai nút. Nút Gửi lại dùng khi tin chưa tới khách. Nút Khách đã nhận dùng khi tin đã tới.

Mục này cũng hiện những tin bị hủy trước khi gửi. Lỗi bắt đầu bằng `cancelled` nghĩa là nhân viên đã tiếp quản hội thoại trước khi bridge kịp gửi câu trả lời của bot. Lỗi bắt đầu bằng `expired_in_queue` nghĩa là tin đã chờ quá 30 phút. Nếu vẫn muốn gửi tin đó, anh bấm Gửi lại.

## Dừng thế nào?

```bash
scripts/stop_local.sh
```

Script dừng console, cron, listener, runner, OpenMausBot (nếu đang chạy), bridge và server theo thứ tự đó. Runner và bridge được làm nốt việc đang dở, ví dụ bridge gửi xong tin đang gửi, rồi mới dừng. Script chỉ dừng listener do bridge bật; tiến trình zalo-agent nào do anh tự mở thì script để nguyên. Với các phần còn lại, script chỉ dừng tiến trình mà `scripts/start_local.sh` đã bật: script so cả mã tiến trình lẫn thời điểm tiến trình khởi động, nên sau khi Mac khởi động lại, script không dừng nhầm chương trình khác được cấp lại mã tiến trình cũ.

## Log và dữ liệu nằm ở đâu?

- Log của từng phần: `~/.thomhouse-bot/logs/` gồm `server.log`, `runner.log`, `bridge.log`, `console.log`, `cron.log`, `seed.log` và `engine-install.log`. Khi máy có OpenMausBot, thư mục này có thêm `openmausbot.log` và `openmausbot-install.log`. File `openmausbot.log` có mã ghép nối, tức mã dùng để nối một điện thoại vào OpenMausBot (theo README của OpenMausBot); anh không gửi file này cho ai.
- Dữ liệu của phòng hai bot: `~/.thomhouse-bot/openmausbot` (dữ liệu và cấu hình của OpenMausBot) và `~/.thomhouse-bot/rooms` (file của runner cho các phòng, trong đó có token của runner).
- Log của listener: `~/.zalo-agent-cli/accounts/<id tài khoản Zalo>/daemon.log`. Thư mục này chỉ có sau khi anh đăng nhập.
- Kiểm tra nhanh cả hệ thống: `cd apps/zalo-bridge && python3 -m bridge.main doctor`. Lệnh này báo zalo-agent đã đăng nhập chưa, listener có chạy không, server có trả lời không và token có đúng không. Dòng `room_platform` cho biết OpenMausBot đã cài chưa, có Node 24 chưa và có đang chạy không.
- Dữ liệu hội thoại: `~/.thomhouse-bot/d1`. Lần chạy đầu tạo cơ sở dữ liệu trống. Thư mục `~/.thomhouse-bot/d1-e2e-test-20261108` là dữ liệu giả của lượt thử ngày 08/11; anh xóa được thư mục này.

## Bot biết gì về người đang nhắn, nhờ tin nhắn cũ?

Bot có thể biết người đang nhắn là khách hay người quen, nên gọi họ là gì, và họ từng hỏi hoặc từng dùng dịch vụ nào. Nguồn của các thông tin này là tin nhắn cũ mà zalo-agent lưu trên Mac. Script `scripts/analyze_contacts.py` đọc các tin đó và lập một hồ sơ liên hệ cho mỗi người từng nhắn riêng với tài khoản; script bỏ qua nhóm chat và mục ghi chú riêng của tài khoản (My Documents). Mỗi hồ sơ liên hệ có bốn phần:

- Người đó là khách, người quen (người nhà, bạn bè) hay chưa rõ, kèm mức chắc chắn thấp, vừa hoặc cao.
- Cách bot nên gọi người đó (chị, anh, cô, chú, bác, hoặc anh/chị khi chưa rõ) và tên để gọi, ví dụ "Lan" khi tên Zalo là "Nguyễn Thị Lan". Bot vẫn luôn xưng "em".
- Các dịch vụ người đó từng nhắc tới, và các dịch vụ có dấu hiệu đã dùng, ví dụ khi khách viết "lần trước chị làm gội đầu". Dấu hiệu đã dùng chỉ là dấu hiệu, không phải bằng chứng khách đã tới studio.
- Tối đa ba đoạn trích, mỗi đoạn dài tối đa 80 ký tự, để nhân viên xem vì sao script kết luận như vậy.

Script không gửi tin nhắn cũ cho Claude hay cho bất kỳ model nào. Script chỉ dùng các quy tắc chữ viết sẵn, chạy trên Mac và không gọi mạng. Lý do không dùng model: những người trong danh bạ chưa đồng ý cho studio gửi tin nhắn cũ của họ cho Anthropic; ghi chú pháp lý về Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 nằm ở `research/07-vn-legal-compliance.md`. Biến `PROFILE_LLM_ENABLED` được giữ chỗ cho một lượt phân tích bằng model sau này, khi studio đã có cách xin đồng ý. Script hiện chưa có lượt phân tích đó: khi `PROFILE_LLM_ENABLED=true`, script dừng ngay với mã lỗi 2 và không đọc tin nào. Từ 12/11, một script khác, `scripts/analyze_visits.py`, có lượt nhờ Claude đọc lại tin nhắn sau cùng biến này. Lượt đó mặc định tắt và chỉ đọc tin của khách đã đồng ý trò chuyện với trợ lý AI (mục "Đoán lần đến, số tiền và gói của khách từ tin nhắn cũ thế nào?" ở dưới).

## Lấy lại tin nhắn cũ thế nào?

zalo-agent chỉ lưu những tin listener nhận được từ lúc listener chạy. Để có tin của 365 ngày trước đó, anh chạy lệnh đồng bộ một lần trong thư mục dự án:

```bash
/Users/luuphuc/Projects/lulu-thomhouse/tools/zalo-agent/node_modules/.bin/zalo-agent sync --days 365 --no-media --no-cloud
```

Lệnh này gửi một yêu cầu đồng bộ tới điện thoại đang đăng nhập tài khoản Zalo của studio. Trên điện thoại hiện thông báo có nút "ĐỒNG BỘ NGAY"; anh bấm nút đó trong vòng 3 phút, vì lệnh chỉ chờ 180 giây. `--no-media` bỏ qua việc tải ảnh và tệp đính kèm, `--no-cloud` bỏ qua danh mục zCloud; script phân tích không cần hai phần này. Theo mã nguồn `src/commands/sync.js` của bản 2.5.9, khi listener đang chạy, lệnh đồng bộ dùng kết nối của listener, nên anh không cần dừng hệ thống. Tôi mới đọc mã nguồn, chưa chạy lệnh này. Nếu lần đồng bộ thành công gần nhất cách chưa tới một giờ, lệnh bỏ qua bước lấy tin; thêm `-F` để lấy lại.

Lệnh đồng bộ chỉ ghi vào file `~/.zalo-agent-cli/accounts/<id tài khoản Zalo>/zalo.db` và không chuyển tin nào sang server. Vì vậy, tin cũ không hiện trên console như tin mới, và bot không trả lời tin cũ nào.

## Chạy phân tích và đưa kết quả vào server thế nào?

Trước khi đưa hồ sơ vào server lần đầu, anh chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh`. Khi bật lại server, `scripts/start_local.sh` áp migration `0007_customer_profiles.sql`; migration này tạo bảng `customer_profiles` và cờ `profile_personal_skip_bot`. Nếu chưa áp migration, bước đưa hồ sơ vào server báo lỗi và server không lưu gì.

Sau đó anh chạy ba lệnh sau, ở thư mục dự án:

```bash
python3 -I scripts/analyze_contacts.py --dry-run   # chỉ phân tích và in số đếm, không ghi file
python3 -I scripts/analyze_contacts.py             # ghi file kết quả
python3 -I scripts/analyze_contacts.py --push      # ghi file và đưa hồ sơ vào server local
```

Script tự tìm tài khoản Zalo đang dùng trong `~/.zalo-agent-cli/accounts.json` và mở `zalo.db` ở chế độ chỉ đọc. Script không sửa `zalo.db`. Màn hình chỉ hiện số đếm: bao nhiêu người được phân tích, bao nhiêu người là khách, người quen hay chưa rõ, bao nhiêu người có tên để gọi. Màn hình không hiện tên và nội dung tin nào.

`--push` gửi hồ sơ tới `http://127.0.0.1:8787/staff/profiles/import`, mỗi lần 200 hồ sơ, bằng `STAFF_TOKEN` trong `apps/server/.dev.vars`. Script từ chối gửi tới một máy khác ngoài máy local. Khi một hồ sơ đã có trên server, lần đưa vào sau cập nhật hồ sơ đó. Nếu nhân viên đã sửa tay hồ sơ, server giữ nguyên các phần nhân viên sửa (xem mục sửa hồ sơ bên dưới). Muốn chỉ phân tích tin từ một ngày trở đi, anh thêm `--since 2026-01-01`.

## Kết quả nằm ở đâu, và phần nào tới model?

Dữ liệu nằm ở ba nơi, đều trên Mac:

- `~/.zalo-agent-cli/accounts/<id tài khoản Zalo>/zalo.db` là tin nhắn gốc, do zalo-agent ghi.
- `~/.thomhouse-bot/profiles/contacts-<ngày>-<giờ>.json` là file kết quả của mỗi lần chạy, có cả đoạn trích. Chỉ tài khoản macOS của anh đọc được file này (quyền 600, thư mục 700). Script không tự xóa file cũ; anh xóa các file không còn cần.
- Bảng `customer_profiles` trong `~/.thomhouse-bot/d1` là bản server dùng, sau khi anh chạy `--push`. Console đọc hồ sơ từ bảng này.

Model chỉ nhận vài thông tin rút ra từ hồ sơ, và chỉ khi khách đã đồng ý trò chuyện với trợ lý AI. Các thông tin đó là cách gọi khách, tên để gọi, tên các dịch vụ khách từng hỏi hoặc có dấu hiệu đã dùng, và việc người đó là khách hay chưa rõ. Cách gọi chỉ được gửi khi mức chắc chắn của cách gọi là vừa hoặc cao; nếu không, bot gọi "anh/chị" như mặc định. Khi nhân viên chọn cách gọi trong console, server ghi cách gọi đó ở mức cao. Khi nhân viên chỉ sửa tên hoặc loại người, mức chắc chắn của cách gọi giữ nguyên. Tên chỉ được gửi khi cách gọi cụ thể, ví dụ bot gọi "chị Lan", không gọi "anh/chị Lan". Tên dịch vụ lấy từ danh mục dịch vụ của studio, mỗi danh sách tối đa năm tên.

Từ hồ sơ, model không nhận tin nhắn cũ, đoạn trích, số đếm tin, hay dịch vụ thuộc nhóm sức khỏe và nhóm chăm sóc phụ nữ, ví dụ "Chăm sóc đau bụng kinh, rối loạn kinh nguyệt". Script chỉ lấy đoạn trích từ tin có từ riêng của nghề, như tên dịch vụ, đặt lịch hay bảng giá. Script không lấy đoạn trích từ tin có từ về sức khỏe như bệnh, đau, viêm, thai, thoái hóa, cột sống, kể cả khi từ đó được gõ không dấu trong một tin mà các từ khác đều có dấu. Hồ sơ người quen ở mức chắc chắn cao không giữ đoạn trích nào. Với người có hồ sơ là người quen, model không nhận thông tin nào từ hồ sơ của người đó. Runner dặn model không được nói hay ám chỉ rằng bot đã đọc tin nhắn cũ, không khẳng định khách đã dùng một dịch vụ, và hỏi lại lịch sự khi chưa chắc.

## Người nhà và bạn bè được xử lý thế nào?

Khi hồ sơ ghi một người là người quen với mức chắc chắn cao, server không để bot trả lời người đó. Ở tin đầu tiên người đó nhắn tới sau khi hồ sơ được đưa vào server, server chuyển hội thoại sang chế độ chỉ nhân viên trả lời và đánh dấu cần nhân viên xem. Server không gửi tin xin đồng ý và không gửi tin nào khác. Nếu một tin xin đồng ý gửi từ trước vẫn còn nằm trong hàng chờ gửi, server hủy tin đó. Về sau, nếu người đó nhắn "gặp nhân viên", server cũng không gửi tin trả lời tự động và không tạo yêu cầu chuyển nhân viên; tin vẫn được đánh dấu cần nhân viên xem.

Quy tắc này chỉ áp dụng cho người chưa đồng ý trò chuyện với trợ lý AI. Khách đã đồng ý thì bot vẫn trả lời như cũ, kể cả khi hồ sơ ghi là người quen. Nếu người đó đã nhận tin xin đồng ý từ trước và trả lời "đồng ý" trong 24 giờ, server vẫn ghi nhận đồng ý như thường. Hồ sơ người quen ở mức chắc chắn vừa hoặc thấp cũng không kích hoạt quy tắc; người đó nhận tin xin đồng ý như mọi người khác. Script chỉ cho mức chắc chắn cao khi cuộc trò chuyện đủ cả bốn điều kiện sau:

- Có ít nhất 10 tin chữ.
- Có ít nhất hai lần gọi kiểu người nhà như "mẹ ơi", "con ơi", hoặc hai lần xưng "tao", "mày".
- Dấu hiệu người quen thuộc ít nhất hai loại, ví dụ gọi kiểu người nhà và chuyện cơm nước, về quê, hoặc nhắn nhiều ngày mà không nhắc dịch vụ.
- Chính người đó chưa từng nhắc tên dịch vụ, chưa gọi chủ tài khoản là shop và chưa dùng từ riêng của nghề như đặt lịch, dịch vụ, bảng giá.

Một vài từ thường ngày như giá, book hay một số tiền như 50k không làm hồ sơ mất mức cao, vì người nhà cũng hay nói những từ đó; các từ này chỉ được chấp nhận khi dấu hiệu người quen nhiều gấp ba. Tin quảng cáo chủ tài khoản gửi cho cả danh bạ cũng không làm hồ sơ mất mức cao. Ngược lại, một khách quen hay nhắn kiểu "mai chị qua nha em" không bị xếp là người quen ở mức cao, vì cuộc trò chuyện không có cách gọi kiểu người nhà.

Cờ `profile_personal_skip_bot` quyết định quy tắc này. Khi cờ là `true` (mặc định), server làm như trên. Khi cờ là `false`, người quen nhận tin xin đồng ý như mọi người. Anh đổi cờ này ở phần Công tắc an toàn trong màn hình Cài đặt của console. Nếu server chuyển nhầm một khách thật sang chế độ chỉ nhân viên trả lời, anh bấm Trả lại cho bot trong console; với hội thoại đó, server không áp lại quy tắc nữa.

## Nhân viên sửa hồ sơ thế nào?

Phần nhân viên sửa luôn thắng phần script phân tích. Server ghi riêng từng mục nhân viên đã sửa trong bốn mục: loại người (khách, nhân viên, gia đình, bạn bè, chưa rõ), cách gọi, tên và danh sách dịch vụ. Những lần chạy `--push` sau vẫn cập nhật đoạn trích, số đếm và các mục nhân viên chưa sửa, nhưng giữ nguyên các mục nhân viên đã sửa. Ví dụ, nhân viên chỉ sửa tên của một người; ở lần chạy sau, script vẫn đổi được loại người và cách gọi của người đó. Server vẫn lưu kết quả mới nhất của script bên cạnh, để nhân viên so sánh. Khi nhân viên bỏ dấu sửa tay, server lấy lại kết quả mới nhất của script cho cả bốn mục.

Anh xem và sửa hồ sơ ngay trong màn hình Hội thoại của console. Với hội thoại Zalo cá nhân, khung Hồ sơ liên hệ nằm phía trên danh sách tin nhắn. Khung này cho biết người đó là khách, nhân viên, gia đình, bạn bè hay chưa rõ, kèm mức chắc chắn và căn cứ của script. Hồ sơ nhập trước tối 08/11 có thể còn nhãn cũ "người quen"; khi sửa hồ sơ đó, anh chọn lại một trong năm loại. Khung cũng cho biết bot gọi người đó thế nào, dịch vụ lần trước (kèm ngày và nguồn: nhân viên ghi buổi làm, hay script đoán từ tin nhắn cũ) và bot được biết gì khi soạn nháp. Phần dưới liệt kê dịch vụ người đó từng hỏi hoặc có dấu hiệu đã dùng, kèm ngày gần nhất, rồi số tin cũ của mỗi bên, tối đa 3 đoạn trích làm căn cứ, nguồn của hồ sơ và việc nhân viên đã sửa hay chưa.

Để sửa, anh bấm Sửa hồ sơ, hoặc Tạo hồ sơ khi người đó chưa có hồ sơ. Khi script chỉ đoán cách gọi ở mức chắc chắn thấp, ô cách gọi để trống, và dòng chữ nhỏ bên dưới cho biết script đoán gì. Anh đổi những ô cần đổi rồi bấm Lưu hồ sơ. Console chỉ gửi các ô đã đổi: loại người hoặc cách gọi vừa chọn được ghi ở mức chắc chắn cao, script không ghi đè các ô đó nữa, và các ô không đổi vẫn theo script. Ví dụ, script đoán một người là bạn bè ở mức chắc chắn vừa và đoán cách gọi "anh" ở mức thấp, rồi anh chỉ sửa tên. Sau khi lưu, người đó vẫn là bạn bè ở mức vừa, cách gọi vẫn ở mức thấp nên bot không dùng, và chỉ tên được giữ cố định.

Khi thấy kết quả của script đã đúng, anh bấm Xác nhận quan hệ và cách gọi đang hiện. Server ghi loại người, cách gọi và tên đang hiện trên khung ở mức chắc chắn cao, và script không ghi đè các mục này nữa. Nút này chỉ hiện khi loại người hoặc cách gọi chưa ở mức cao. Nút Bỏ phần nhân viên sửa, dùng kết quả script chỉ hiện khi hồ sơ đã có mục nhân viên sửa.

Console chưa sửa được danh sách dịch vụ và ghi chú của nhân viên. Hai phần này vẫn sửa bằng API. Ví dụ, lệnh sau ghi một ghi chú cho hồ sơ; anh thay `<mã>` bằng phần sau `p:` ở dòng Zalo id trong console:

```bash
curl -X PATCH "http://127.0.0.1:8787/staff/profiles/p:<mã>" \
  -H "Authorization: Bearer $STAFF_TOKEN" -H "content-type: application/json" \
  -d '{"staff_note": "khách quen của studio"}'
```

Ghi chú không bật dấu sửa tay. Danh sách dịch vụ (`services`) phải gửi đủ cả danh sách, cùng dạng với kết quả của script. Biến `STAFF_TOKEN` lấy từ `apps/server/.dev.vars`. Chi tiết đầy đủ của các API này nằm ở mục 13 trong `docs/contracts.md`.

## Cách phân tích này sai ở đâu?

Script đoán vai của đại từ từ thứ tự chữ trong câu. Với câu hỏi như "chị muốn đặt lịch không ạ?", "chị" có thể là người hỏi hoặc người được hỏi, nên script bỏ qua câu đó. Vì vậy, với cuộc trò chuyện ngắn, script thường kết luận "anh/chị" ở mức chắc chắn thấp, và bot gọi khách như mặc định. Một tài khoản Zalo do hai người dùng chung, hoặc một khách nhắn hộ người nhà, làm dấu hiệu bị lẫn. Script không nhận ra hai trường hợp này; mức chắc chắn chỉ giảm. Script chỉ chạy khi anh chạy lệnh, nên người nhắn lần đầu sau lần chạy gần nhất chưa có hồ sơ cho tới lần chạy sau.

Câu nhờ vả như "anh xem giúp em lịch thứ 7" hay "chị gửi em địa chỉ" đặt người được nhờ ở đầu câu. Khi khách viết những câu này, script hiểu người đứng đầu câu là chủ tài khoản. Nếu khách thật ra là người lớn tuổi hơn đang nói với nhân viên, cách hiểu này sai. Khi đó bot gọi khách bằng "anh/chị" thay vì "chị", và không gọi sai giới tính. Khi chủ tài khoản viết câu cùng dạng, ví dụ "anh gửi em bảng giá nhé", script không tính câu đó, vì đọc theo cách nào cũng có thể gán cách xưng của chủ tài khoản cho khách. Câu chào mẫu "xin chào anh/chị" của chủ tài khoản không được tính là gọi khách là anh hay chị.

## Đoán lần đến, số tiền và gói của khách từ tin nhắn cũ thế nào?

Từ 12/11, script `scripts/analyze_visits.py` đọc cùng kho tin nhắn cũ đó và đoán, cho từng khách, các lần khách đến studio, số tiền khách đã trả, kỹ thuật viên, số điện thoại và gói nhiều buổi hoặc voucher. Mỗi kết quả là một phỏng đoán. Server lưu các phỏng đoán riêng, không trộn với buổi làm nhân viên ghi. Khối Tóm tắt khách hàng trên console tính các lần đến ở mức chắc và khá chắc vào số liệu của khách, ghi rõ con số nào có phần suy ra từ tin nhắn, và nhân viên xác nhận hoặc bỏ từng phỏng đoán. `docs/rooms.md` giải thích ba mức chắc chắn và cách xác nhận.

Script bỏ qua nhóm chat và người mà script hồ sơ liên hệ đoán là người nhà, nhân viên hay bạn bè. Script chạy bằng quy tắc chữ viết sẵn trên Mac và không gọi mạng. Lượt nhờ Claude đọc lại tin nhắn mặc định tắt (biến `PROFILE_LLM_ENABLED`). Khi anh bật, script chỉ gửi các đoạn tin quanh lần hẹn của khách đã đồng ý trò chuyện với trợ lý AI, sau khi che số điện thoại, tên Zalo của khách và đường link, và bỏ các tin nói về sức khỏe. Lượt này chưa chạy với Claude thật lần nào.

Server cần migration `0011_chat_facts.sql` để nhận kết quả. `scripts/start_local.sh` áp migration này khi bật server; nếu chưa áp, bước đưa kết quả vào server báo lỗi và server không lưu gì. Ngày 12/11, lượt chạy thử đã áp các migration tới 0011 vào `~/.thomhouse-bot/d1` của máy này, sau khi sao lưu dữ liệu vào `~/.thomhouse-bot/backups/d1-before-0010-20261112-1720`.

Anh chạy ba lệnh sau ở thư mục dự án:

```bash
python3 -I scripts/analyze_visits.py --dry-run   # chỉ phân tích và in số đếm, không ghi file
python3 -I scripts/analyze_visits.py             # ghi file kết quả
python3 -I scripts/analyze_visits.py --push      # ghi file và đưa kết quả vào server local
```

Script cần Python 3.11 trở lên. Ngày 12/11, `/usr/bin/python3` bản 3.9.6 có sẵn của macOS không nạp được script này. `scripts/start_local.sh` cũng đòi Python 3.11, nên nếu `scripts/start_local.sh` chạy được trong một cửa sổ Terminal thì lệnh `python3` của cửa sổ đó đủ mới.

Màn hình chỉ hiện số đếm, không hiện tên, số điện thoại hay nội dung tin nào. Ngày 12/11, lệnh chạy thử trên một kho tin nhắn giả có 5 cuộc trò chuyện, kho mà test của server dùng, in ra:

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

Các dòng có nghĩa như sau:

- Dòng đầu là số cuộc trò chuyện của khách được đọc. Trong ngoặc là số cuộc trò chuyện bị bỏ qua theo lý do: `family` người nhà, `staff` nhân viên, `friend` bạn bè, `group` nhóm chat, `system_account` tài khoản hệ thống của Zalo.
- Dòng `visits found` đếm lần đến theo mức: `high` là mức chắc, `medium` là mức khá chắc, `low` là mức chưa chắc. Cùng dòng là số lịch hẹn sắp tới và số lịch đã hủy hoặc khách không đến.
- Dòng tiếp theo là số khách có ít nhất một lần đến ở mức chắc hoặc khá chắc.
- Dòng `visits with` cho biết trong các lần đến, bao nhiêu lần script tìm được dịch vụ, giờ, số tiền và kỹ thuật viên.
- Hai dòng sau đếm số điện thoại theo mức và số gói hoặc voucher.
- Dòng `model pass` cho biết lượt nhờ Claude đọc lại tin nhắn; `off` là tắt.
- Dòng cuối của lần chạy thử cho biết script không ghi gì. Khi không có `--dry-run`, dòng cuối là đường dẫn file kết quả.

Với `--push`, script in thêm một dòng `pushed:` gồm tám số đếm của server. `customers` là số khách server nhận. `visits_imported`, `visits_updated` và `visits_removed` là số lần đến server thêm mới, sửa và xóa so với lần chạy trước. `visits_kept_staff` là số lần đến server bỏ qua vì ngày đó đã có buổi làm do nhân viên ghi hoặc nhân viên đã xác nhận. `phones_set` là số điện thoại server ghi thẳng vào hồ sơ khách. `benefits_upserted` là số gói hoặc voucher server thêm hoặc sửa. `unmatched` là số người server chưa biết, vì người đó chưa nhắn tới từ khi bot chạy; server vẫn giữ kết quả của họ và gắn vào hồ sơ khi họ nhắn.

File kết quả nằm ở `~/.thomhouse-bot/profiles/visits-<ngày>-<giờ>.json`, quyền 600. File có số điện thoại và tên kỹ thuật viên, nhưng không có nội dung tin nhắn. `--push` chỉ gửi tới server trên máy này, bằng `STAFF_TOKEN` trong `apps/server/.dev.vars`. Chạy lại lệnh `--push` là an toàn: server cập nhật phỏng đoán cũ và giữ nguyên các phỏng đoán nhân viên đã xác nhận hoặc đã bỏ. Muốn chỉ đọc tin từ một ngày trở đi, anh thêm `--since 2026-01-01`.

Ngày 12/11 có hai lần chạy trên máy này. Lúc 16:38, một lần chạy thử không ghi gì trên kho tin thật chỉ tìm thấy 2 cuộc trò chuyện của khách, 1 lần đến ở mức chưa chắc và 1 số điện thoại ở mức khá chắc, vì kho tin của zalo-agent chỉ có 18 trong số 420 cuộc trò chuyện riêng của tài khoản. Chưa ai tìm hiểu vì sao lệnh đồng bộ tin cũ lấy về ít như vậy. Trong lượt chạy thử lúc 17:12 đến 17:31, lệnh `--push` đưa kết quả vào server qua HTTP, và server trả về: 8 khách, 3 lần đến mới, 7 người server chưa biết.

## Bot trả lời theo mẫu nào?

Từ 08/11, bot viết câu trả lời theo bảy mẫu trong `data/reply-templates.json`. Mỗi mẫu ứng với một việc khách hay nhắn: chào khách mới, chào khách quen, xin xem menu chung, xin xem menu một nhóm, hỏi một dịch vụ, đặt lịch và nhắn sau buổi làm. Server ghép cả bảy mẫu vào system prompt, tức đoạn chỉ dẫn cố định gửi kèm mọi lần gọi model. Vì vậy runner nhận mẫu mới khi server khởi động lại, không cần nạp lại catalog. Chủ studio chưa duyệt các mẫu này.

Mỗi mẫu ghi khi nào dùng, công cụ bot phải gọi, khung câu, câu dùng khi khách chưa có hồ sơ (bot gọi khách là anh/chị) và hai ví dụ đã điền. Câu đầu của mỗi câu trả lời gọi khách theo hồ sơ, ví dụ "Dạ em chào chị Lan ạ". Giá, thời lượng và các bước của dịch vụ không nằm trong mẫu: bot lấy từ công cụ tra catalog trong lúc trả lời, và bước kiểm tra trước khi gửi vẫn so từng mức giá với kết quả công cụ. Khi khách nhắc bệnh, thai kỳ, thuốc hay phản ứng sau buổi làm, bot bỏ mẫu và chuyển nhân viên như trước.

Mẫu chào khách quen có câu "Lần trước chị làm Gội đầu thư giãn bên em hôm 20/10". Server chỉ gửi dịch vụ lần trước cho model khi dịch vụ đó không thuộc nhóm sức khỏe hay nhóm chăm sóc phụ nữ, và ngày làm còn trong 180 ngày gần nhất. Dịch vụ lần trước lấy từ buổi làm nhân viên đã ghi, hoặc từ dấu hiệu trong tin nhắn cũ ở mức chắc chắn vừa trở lên. Cách này có một điểm yếu: dấu hiệu từ tin nhắn cũ có thể sai, và khi đó bot nhắc một dịch vụ khách chưa làm. Mẫu dặn bot xin lỗi ngắn nếu khách nói không làm dịch vụ đó, và nhân viên vẫn duyệt từng bản nháp trước khi gửi.

Muốn sửa câu chữ, anh sửa `data/reply-templates.json`, chạy `python3 -m unittest discover -s scripts/tests -p 'test_reply_templates.py'`, rồi khởi động lại server bằng `scripts/stop_local.sh` và `scripts/start_local.sh`. Test báo lỗi khi một ví dụ gọi khách là "mình" hay "bạn", có chữ "ngay", hỏi quá hai câu, hoặc dùng một placeholder chưa khai báo. Placeholder là chỗ điền trong mẫu, viết trong ngoặc nhọn như `{xung_ho}` (cách gọi khách) hay `{ten}` (tên khách).

## Bot gửi ảnh menu thế nào?

Khi khách xin xem menu, bảng giá hay hình một dịch vụ, bot có thể đính kèm ảnh menu vào bản nháp. Bot chỉ chọn trong 57 ảnh menu đã tải từ Drive, theo danh mục `data/menu-images.json`; lệnh bot gọi không có chỗ nào nhận đường dẫn file. Bot có ba cách chọn: ảnh bìa của cả bốn menu, các ảnh có giá của một menu, hoặc các ảnh của một dịch vụ trong catalog. Mỗi bản nháp mang tối đa 10 ảnh, và bản nháp có ảnh luôn chờ nhân viên duyệt.

Ngày 08/11, tôi mở từng ảnh và đánh dấu 30 trên 57 ảnh là ảnh in câu hứa chữa bệnh, phòng bệnh, tên bệnh hoặc con số kiểu "gấp 10 lần" (trường `has_medical_claim`). Bot không được gửi 30 ảnh này. Nhân viên vẫn gửi được bằng nút Gửi menu trên console, sau khi xác nhận ở hộp thoại hỏi lại. Vì vậy, với menu giúp bạn khỏe, bot chỉ gửi được ảnh bìa và ảnh giá của Detox cơ thể và Đau thắt lưng mỏi gối.

Khi nhân viên duyệt bản nháp, server xếp câu trả lời vào hàng chờ trước, rồi xếp các ảnh vào một tin riêng. Bridge chỉ gửi tin ảnh sau khi câu trả lời đã tới khách, bằng lệnh `zalo-agent msg send-image`. Nếu câu trả lời gửi lỗi hoặc không rõ đã tới khách hay chưa, server hủy tin ảnh; nhân viên chọn gửi lại trên console nếu muốn.

Bản sao JPEG của các ảnh nằm ở `~/.thomhouse-bot/menu-images`. Mỗi lần chạy, `scripts/start_local.sh` tạo những bản sao còn thiếu hoặc đã cũ. Nếu bước này lỗi, hệ thống vẫn chạy, nhưng bridge báo lỗi cho tin ảnh và không gửi ảnh nào.

Trên console, bản nháp có ảnh hiện ảnh nhỏ của từng ảnh sẽ gửi kèm. Nhân viên bấm Bỏ ảnh này để bỏ một ảnh trước khi duyệt; nếu bỏ hết, khách chỉ nhận câu trả lời bằng chữ. Nút Gửi menu ở màn hình Hội thoại cho nhân viên chọn ảnh bìa của tất cả menu, hoặc bảng giá của một menu, rồi xếp các ảnh vào hàng chờ gửi. Việc gửi này không đổi trạng thái của bot: bot vẫn trả lời hội thoại đó như trước. Ảnh in câu về sức khỏe để trống sẵn; khi nhân viên chọn ảnh đó, console hỏi lại trước khi cho gửi. Ảnh nhỏ trên console là bản sao đóng gói sẵn trong server (`apps/server/src/menu-thumbs.ts`), do `scripts/build_menu_thumbs.py` tạo từ ảnh gốc. Khi ảnh menu đổi, anh chạy lại script này rồi khởi động lại server.

Điểm yếu còn lại: ảnh menu da và ảnh triệt lông in nhiều mức giá chưa có trong catalog, và chủ studio chưa xác nhận bộ menu da nào đang bán, nên một ảnh giá cũ vẫn có thể tới khách nếu nhân viên duyệt. Khi hội thoại ở chế độ chỉ soạn nháp, nút gửi tay từ bản nháp chỉ gửi chữ; muốn gửi ảnh, nhân viên dùng nút Gửi menu.

## Từ 12/11 có thêm gì?

Ngày 12/11/2026, hệ thống có thêm năm phần. `docs/rooms.md` giải thích từng phần cho anh và lễ tân; `docs/run-local.md` ghi đủ lệnh, biến cấu hình và cách xử lý khi một phần không chạy.

Phần thứ nhất là công tắc Tự động trả lời ở trang chi tiết của mỗi hội thoại trên console. Mặc định, công tắc tắt ở mọi hội thoại cho tới khi nhân viên bật. Khi nhân viên bật công tắc, câu trả lời của bot tới khách mà không ai đọc trước; tin có ảnh menu, tin bị bước kiểm tra trước khi gửi báo lỗi và tin bot chuyển cho nhân viên vẫn chờ duyệt.

Phần thứ hai là ba nhãn Zalo Khách hàng, Quản lý và Nhân viên. Anh gắn nhãn trong app Zalo trên điện thoại của studio. Bridge đọc nhãn khi bật và sau đó cứ 15 phút một lần. Muốn cập nhật ngay, anh chạy:

```bash
cd apps/zalo-bridge && python3 -m bridge.main sync-labels
```

Với người có nhãn Quản lý hoặc Nhân viên, server chỉ lưu tin: bot không gửi tin xin đồng ý, không soạn nháp và không tự gửi tin nào cho người đó. Anh vẫn tự nhắn được cho họ từ console hoặc từ điện thoại. Nhãn Khách hàng làm bot coi người đó là khách, kể cả khi hồ sơ liên hệ đoán là người nhà hay bạn bè.

Phần thứ ba là khối Tóm tắt khách hàng trên console: số lần đến, lần đến gần nhất, nhịp quay lại, số tiền đã chi, quyền lợi chưa dùng và trạng thái của khách. Khối này có số liệu khi nhân viên ghi buổi làm trên console, khi script `scripts/analyze_visits.py` đoán được lần đến từ tin nhắn cũ (phần thứ năm), hoặc khi anh nhập lịch sử từ file CSV:

```bash
python3 -I scripts/import_visits.py lich-su.csv            # chạy thử, không ghi gì
python3 -I scripts/import_visits.py lich-su.csv --apply    # ghi thật
```

Phần thứ tư là phòng hai bot, mặc định tắt. Khi bật, mỗi khách đã đồng ý trò chuyện với trợ lý AI có một phòng chat riêng trên OpenMausBot. Trong phòng, Bot dịch vụ hỏi Bot khách hàng về khách rồi viết bản nháp. Muốn bật, anh đặt dòng `THOMHOUSE_DRAFT_ENGINE=rooms` trong `apps/runner/.env`, chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh`, và chọn `true` ở mục Phòng hai bot (`rooms_enabled`) trong tab Cài đặt của console. Muốn tắt, anh chọn lại `false`. Khi OpenMausBot lỗi hoặc không chạy, runner soạn bản nháp bằng `claude -p` như trước.

Phần thứ năm là script `scripts/analyze_visits.py`. Script đoán lần đến, số tiền, kỹ thuật viên, số điện thoại và gói của khách từ tin nhắn cũ, rồi đưa các phỏng đoán vào server để nhân viên xác nhận hoặc bỏ trên console. Lệnh chạy và ý nghĩa từng dòng script in ra nằm ở mục "Đoán lần đến, số tiền và gói của khách từ tin nhắn cũ thế nào?" ở trên.

## Lượt chạy thử ngày 12/11 thử được gì?

Chiều 12/11, từ 17:12 tới 17:31, hệ thống chạy thử trên máy Mac này với database thật ở `~/.thomhouse-bot/d1` (đã sao lưu trước), một bản zalo-agent giả thay cho Zalo thật, và một khách giả. Runner chạy với phòng hai bot: `THOMHOUSE_DRAFT_ENGINE=rooms` và cờ `rooms_enabled` là `true`. Các phần sau chạy đúng:

- Tin xin đồng ý, và tin cảm ơn sau khi khách nhắn "đồng ý", đi qua bridge tới zalo-agent giả.
- Hai bot soạn một câu trả lời trong phòng: Bot dịch vụ hỏi Bot khách hàng, Bot khách hàng đọc hồ sơ khách, Bot dịch vụ lấy giá 199.000đ bằng công cụ báo giá, và bản nháp chờ nhân viên duyệt. Hai bot chỉ chạy được sau khi file quy tắc được chép tay (vấn đề thứ nhất ở dưới).
- Khi công tắc Tự động trả lời bật, tin tiếp theo của khách được hai bot trả lời, và câu trả lời được tự gửi qua zalo-agent giả.
- Khi công tắc tắt và nhân viên tự gửi tin, runner chép tin của nhân viên vào phòng sau 17 giây, để hai bot có bối cảnh.
- Lệnh đồng bộ nhãn đọc dữ liệu nhãn giả và ghi vai trò khách, nhân viên, quản lý lên server. Người có nhãn Nhân viên nhắn tới thì không nhận tin xin đồng ý, và bot không soạn bản nháp.
- Khối Tóm tắt khách hàng do server trả về tính một buổi làm nhân viên ghi cộng hai lần đến suy ra từ tin nhắn thành 3 lần đến, trạng thái khách quay lại, và số tiền 398.000đ chỉ từ các lần khách đã trả. Khối này có thêm 1 gói và 1 số điện thoại gợi ý. Bot khách hàng kể đúng 3 lần đến, lần đến gần nhất, nhịp quay lại và gói chưa xác nhận. Bot dịch vụ không tự nói số buổi còn lại của gói mà chuyển hội thoại cho nhân viên.
- `scripts/analyze_contacts.py --push` đưa 16 hồ sơ vào server, và `scripts/analyze_visits.py --push` đưa kết quả vào server qua HTTP.

Lượt chạy thử tìm ra ba vấn đề:

1. Ở mọi lượt, Bot dịch vụ trả lời bằng mã báo không thấy quy tắc, và runner phải soạn lại bằng `claude -p`. Nguyên nhân: OpenMausBot chạy lượt trả lời trong phòng ở thư mục `~/.thomhouse-bot/openmausbot/workspaces/<mã bot>`, còn runner chỉ đặt file quy tắc `CLAUDE.md` ở thư mục làm việc riêng của bot. Khi file quy tắc được chép tay sang thư mục của OpenMausBot, hai bot chạy được. Runner đã được sửa để tự ghi file quy tắc vào thư mục đó sau mỗi lần cài đặt hai bot, và xóa bản chép ở thư mục của bot khác. Bản sửa có test với OpenMausBot giả. Runner đang chạy trên máy chưa được khởi động lại, nên file trên máy vẫn là bản chép tay; runner mới giữ nguyên file đó khi nội dung trùng.
2. Ghi một buổi làm cách đây 23 ngày tạo ra tin cảm ơn và tin hỏi thăm có giờ gửi đã qua. Lần đó không có tin nào được gửi, vì khách chưa đồng ý nhận tin chăm sóc và mục Tin hẹn giờ sau buổi làm đang tắt. Sau lượt chạy thử, code được đọc lại và có thêm test: server không gửi tin nào trễ quá 6 giờ so với giờ dự kiến, nên hai tin đó sẽ hết hạn mà không được gửi.
3. Bot dịch vụ mở đầu mọi câu trả lời bằng câu tự giới thiệu là trợ lý AI, kể cả giữa cuộc trò chuyện. Runner giờ báo cho Bot dịch vụ biết bot đã từng gửi tin tới khách hay chưa. Chưa thử lại với Claude thật.

## Phần nào chưa được kiểm tra?

Lượt chạy thử ngày 12/11 chưa thử năm phần sau:

- Một tin nhắn qua tài khoản Zalo thật. Lượt chạy thử ngày 12/11 vẫn dùng zalo-agent giả, vì anh chọn tự thử Zalo thật trên thiết bị khác.
- Console mở trên trình duyệt. Lượt chạy thử chưa nhập staff token vào trang, nên chưa ai nhìn công tắc Tự động trả lời, khối Tóm tắt khách hàng và mục Suy ra từ tin nhắn cũ trên màn hình.
- Bản sửa file quy tắc của Bot dịch vụ và dòng báo bot đã từng gửi tin, với OpenMausBot thật và Claude thật.
- Lượt nhờ Claude đọc lại tin nhắn của `scripts/analyze_visits.py`.
- Script nhập buổi làm từ file CSV với server thật, và lệnh đồng bộ nhãn với tài khoản Zalo thật. Chưa biết zalo-agent có đọc được nhãn trong lúc listener đang chạy hay không.

Tôi chạy thử ngày 08/11 bằng một zalo-agent giả: bản giả ghi lại lệnh gửi và trả kết quả theo đúng dạng của zalo-agent thật. Tin của khách được giả lập bằng `scripts/simulate_personal_zalo.py`, ký đúng cách listener thật ký. Script này mặc định dùng mã người nhận `sim-9100123`. Mã này không phải số, nên bridge thật từ chối gửi tới mã đó; script cũng từ chối mã toàn số khi đang có bridge lấy tin trong hàng chờ, trừ khi anh thêm cờ `--allow-real-bridge`. Lượt thử đó chưa chạm tới các phần sau:

- Đăng nhập QR, listener thật và việc gửi tin qua Zalo thật. Không agent nào đăng nhập tài khoản Zalo.
- Cách listener thật báo lại tin bot vừa gửi. Server nhận ra tin của chính bot trước hết nhờ mã tin mà lệnh gửi trả về, sau đó nhờ nội dung trùng khớp. Chưa biết mã tin của lệnh gửi có trùng mã tin trong sự kiện listener nhận lại hay không. Nếu cả mã tin lẫn nội dung đều không khớp, server sẽ hiểu nhầm là nhân viên gõ tay và dừng bot trong hội thoại đó.
- Runner soạn bằng `claude -p` thật. Tài khoản Claude của runner đang hết hạn mức tuần, nên bản nháp trong lượt thử được viết tay và gửi qua Runner API. Runner đã soạn bản nháp thật bằng `claude -p` ở chế độ mock ngày 07/11 (`docs/run-local.md`).
- Tin dài hơn khoảng 2900 byte, mà zalo-agent chia thành nhiều phần. Phần này mới có unit test.
- Phản ứng của Zalo với việc zalo-agent đăng nhập lại qua HTTP ở mỗi lần gửi tin. Mã nguồn bản 2.5.9 cho thấy mỗi lệnh `msg send` tự đăng nhập; tôi chưa biết Zalo có coi việc này là bất thường hay không.
- Script `scripts/analyze_contacts.py` có test với dữ liệu giả (`scripts/tests/test_analyze_contacts.py`), và đã chạy với `--push` trong lượt chạy thử ngày 12/11 (server nhận 16 hồ sơ). Chưa ai đo script đoán đúng cách gọi và loại người ở bao nhiêu phần trăm số người.
- Khung Hồ sơ liên hệ trên console mới có test tự động với dữ liệu giả (`apps/console/src/ProfileCard.test.tsx`). Tôi chưa mở khung này trên console đang chạy.
- Ảnh nhỏ của bản nháp, nút Bỏ ảnh này và nút Gửi menu mới có test tự động với dữ liệu giả (`apps/console/src/MenuImages.test.tsx`, `apps/server/test/staff-menu.test.ts`). Tôi chưa mở các phần này trên console đang chạy.
- Bảy mẫu trả lời mới có test kiểm câu chữ và kiểm prompt (`scripts/tests/test_reply_templates.py`, `apps/server/test/reply-templates.test.ts`). Mẫu chưa chạy với `claude -p` thật, nên chưa biết model chọn đúng mẫu ở bao nhiêu phần trăm câu hỏi.
- Gửi ảnh menu qua Zalo thật. Lệnh `msg send-image` mới chạy với zalo-agent giả trong test. Chưa biết mã tin mà lệnh gửi ảnh trả về có trùng mã tin trong sự kiện listener nhận lại hay không. Khi bridge chưa báo kết quả, server coi ảnh do chính tài khoản gửi trong 3 phút sau khi bridge nhận tin ảnh là ảnh của bot. Nếu mã tin không trùng và bridge đã báo kết quả, server sẽ hiểu nhầm là nhân viên gửi ảnh và dừng bot trong hội thoại đó. Migration `0009_outbox_images.sql` cũng chưa được áp vào dữ liệu thật.
- Các phần của ngày 12/11 đã chạy trong lượt chạy thử chiều 12/11 với zalo-agent giả (mục "Lượt chạy thử ngày 12/11 thử được gì?" ở trên). Các phần chưa thử nằm ở đầu mục này.
- Ngày 12/11, `scripts/start_local.sh` đã áp các migration còn thiếu, tới `0011_chat_facts.sql`, vào dữ liệu thật ở `~/.thomhouse-bot/d1`, sau khi sao lưu dữ liệu. Việc server chuyển người quen sang chế độ chỉ nhân viên trả lời mới có test tự động, chưa thử với Zalo thật. Việc `claude -p` nhận thông tin từ hồ sơ liên hệ cũng chưa thử với `claude -p` thật; lượt chạy thử ngày 12/11 chỉ cho thấy hai bot trong phòng đọc được hồ sơ khách.

## Nói ngắn gọn nhất

Anh chạy `scripts/start_local.sh`, quét mã QR bằng lệnh `zalo-agent login`, chạy lại `scripts/start_local.sh`, rồi mở console để duyệt từng câu trả lời. Đường đi của tin nhắn đã chạy được với zalo-agent giả, nhưng Zalo thật chưa được thử, và tài khoản Zalo có thể bị khóa vì zalo-agent không chính thức. Hãy dùng một tài khoản Zalo riêng cho studio. Trước ngày 13/11, nếu không thêm tài khoản Claude khác cho runner, bot chỉ chuyển câu hỏi cho nhân viên chứ chưa tự soạn được câu trả lời. Sau khi đồng bộ tin cũ, anh chạy `scripts/analyze_contacts.py --push` để bot biết cách gọi khách và dịch vụ khách từng hỏi; tin cũ chỉ được đọc trên Mac, model chỉ nhận vài thông tin rút ra, và người quen không bị bot nhắn. Bot viết theo bảy mẫu trả lời chưa được duyệt trong `data/reply-templates.json` và gọi khách theo hồ sơ ở câu đầu; nhân viên vẫn duyệt từng bản nháp, kể cả các ảnh menu đi kèm. Từ 12/11, anh gắn nhãn Quản lý và Nhân viên trong Zalo để bot không nhắn cho người làm ở studio, và ghi buổi làm để khối Tóm tắt khách hàng có số liệu; công tắc Tự động trả lời mặc định tắt ở mọi hội thoại, và phòng hai bot mặc định tắt. Lệnh `scripts/analyze_visits.py --push` đoán lần đến, số tiền, số điện thoại và gói của khách từ tin nhắn cũ; console tính các lần đến ở mức chắc và khá chắc, ghi rõ là suy ra từ tin nhắn, và nhân viên xác nhận hoặc bỏ từng phỏng đoán. Trong lượt chạy thử chiều 12/11 với zalo-agent giả, hai bot soạn được câu trả lời sau khi file quy tắc của Bot dịch vụ được chép tay. Runner đã được sửa để tự ghi file đó, nhưng bản sửa chưa chạy với OpenMausBot thật. Một tin nhắn qua Zalo thật và console trên trình duyệt vẫn chưa được thử.

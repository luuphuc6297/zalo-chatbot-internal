# Cài chatbot thom house lên máy Mac của studio

Hướng dẫn này viết cho anh, chủ studio. Hướng dẫn nói cách tạo file cài trên máy của anh, cách cài chatbot lên một máy Mac khác, và cách cập nhật, sao lưu, khôi phục, chuyển máy và gỡ chatbot.

Hướng dẫn viết theo thiết kế của trình cài ở mục 16 trong `docs/contracts.md`. Đến ngày 12 tháng 11 năm 2026, trình cài mới chạy với các chương trình giả lập trong bộ test; chưa có lần cài thật nào trên một máy Mac của studio. Phần cuối hướng dẫn liệt kê những gì chưa được thử trên máy thật.

Hướng dẫn dùng vài cách gọi cố định:

| Cách gọi | Nghĩa |
|---|---|
| máy tạo file cài | máy Mac của anh có thư mục dự án `~/Projects/lulu-thomhouse`; chỉ máy này tạo được file cài |
| máy của studio | một máy Mac mà anh cài chatbot lên bằng file cài |
| file cài | file `thomhouse-<bản>.command`, ví dụ `thomhouse-1.4.0.command`; file này chứa toàn bộ chương trình |
| mã bản cài | 16 ký tự đầu của mã SHA-256 của file cài, ví dụ `3F9A-21C7-0B44-D1E8`; mã SHA-256 tính từ nội dung file, nên file đổi một chút là mã đổi |
| lệnh thomhouse | chương trình `~/ThomHouse/bin/thomhouse` mà trình cài đặt lên máy của studio |

## Máy nào cài được chatbot?

Trình cài chỉ cài lên máy Mac có macOS 13.5 trở lên, và được thiết kế cho máy Mac chip Apple, từ M1 trở về sau. Với máy Mac chip Intel, trình cài hỏi anh có muốn cài tiếp không, vì chưa ai chạy thử chatbot trên máy Intel. Với Windows, Linux và WSL, file cài in một câu từ chối rồi dừng, và máy không bị thay đổi gì. Anh đã quyết định giới hạn này ngày 12 tháng 11 năm 2026.

Máy cần ít nhất 3 GB trống. Python, Node.js và pnpm riêng của chatbot chiếm khoảng 300 MB; con số này là ước tính, chưa đo trên máy thật. Bộ ảnh menu chiếm thêm khoảng 173 MB.

Trình cài không cần mật khẩu máy, không dùng `sudo` và không sửa cài đặt của Terminal hay của macOS. Trình cài ghi chương trình vào `~/ThomHouse`, dữ liệu vào `~/.thomhouse-bot` và Claude Code vào `~/.local` (qua chương trình cài của Anthropic). Ngoài ba thư mục đó, trình cài chỉ ghi các file anh đồng ý tạo: file tự bật chatbot trong `~/Library/LaunchAgents` và ba nút bấm trên Desktop.

Mỗi máy của studio là một bản cài độc lập. Mỗi máy có tài khoản Zalo, dữ liệu khách, mã bí mật và tài khoản Claude riêng, và không máy nào đồng bộ với máy khác. Console cho nhân viên chỉ mở được trên chính máy đó, ở địa chỉ `http://127.0.0.1:5173`. Máy phải luôn thức để chatbot nhận tin; trình cài không đổi cài đặt ngủ của máy.

## Trên máy tạo file cài, anh chuẩn bị gì?

Anh làm hai việc một lần trước bản đầu tiên. Việc thứ nhất là ghi mã kiểm tra của Python, Node.js và Claude Code vào `install/versions.json`. Lệnh dưới đây cần mạng, và cần Claude Code bản 2.1.319 đã cài sẵn trên máy tạo file cài, vì lệnh lấy mã kiểm tra của Claude Code từ chính bản đó:

```bash
cd ~/Projects/lulu-thomhouse
python3 -I scripts/release/refresh_pins.py
```

Việc thứ hai là tạo khóa ký. Khóa ký là cặp khóa SSH dùng để ký file cài; máy của studio dùng khóa này để biết một file cập nhật thật sự do anh tạo. Lệnh dưới đây tạo khóa ở `~/.ssh/thomhouse-release`, và `ssh-keygen` hỏi mật khẩu của khóa bằng tiếng Anh:

```bash
python3 -I scripts/release/make_release.py --init-key
```

Anh giữ khóa này cẩn thận. Nếu mất khóa hoặc lộ khóa, mỗi máy của studio phải gỡ chương trình (giữ dữ liệu) rồi cài lại từ đầu để nhận khóa mới.

### Tạo một bản mới thế nào?

Mỗi lần có bản mới, anh chạy lệnh dưới đây với số bản do anh đặt. Thêm `--menu` khi bộ ảnh menu thay đổi, hoặc khi máy của studio chưa có bộ ảnh menu:

```bash
python3 -I scripts/release/make_release.py --version 1.4.0 --menu
```

Lệnh ghi các file vào `~/thomhouse-releases`:

| File | Dùng làm gì |
|---|---|
| `thomhouse-1.4.0.command` | file cài, mang sang máy của studio |
| `thomhouse-1.4.0-DOC-TRUOC.txt` | ghi chú tiếng Việt đi kèm file cài, mang theo cùng file cài |
| `thomhouse-menu-<mã menu>.tar` | bộ ảnh menu, chỉ tạo khi có `--menu`; mang theo khi cài lần đầu hoặc khi bộ ảnh đổi |
| `thomhouse-1.4.0.sha256` | mã kiểm tra của file cài; file này ở lại máy tạo file cài |

Cuối cùng, lệnh in mã bản cài. Anh ghi mã này lại và gửi riêng cho người cài, ví dụ qua tin nhắn, không để chung trong ổ USB với file cài. Mỗi lần tạo, file cài có mã bản cài khác, vì file ghi cả thời điểm tạo; anh luôn so với mã của đúng lần tạo file đang mang đi.

Lệnh dừng và không tạo file nào khi một bước kiểm tra không đạt. Lệnh kiểm tra rằng file cài không chứa mã bí mật của máy tạo file cài, khóa riêng, số điện thoại, mã Zalo, đường dẫn thư mục nhà của anh hay dữ liệu khách. Muốn chạy các bước kiểm tra mà không ghi file, anh thêm `--check-only`.

Anh chép file sang máy của studio bằng USB, AirDrop hoặc kho lưu trữ riêng. Máy của studio không cần git và không cần quyền đọc kho mã.

## Cài lần đầu trên máy của studio thế nào?

Trước khi chạy file cài, anh kiểm tra mã bản cài. Anh mở Terminal trên máy của studio và chạy lệnh dưới đây, thay đường dẫn cho đúng thư mục chứa file:

```bash
shasum -a 256 /Volumes/USB/thomhouse-1.4.0.command
```

16 ký tự đầu mà lệnh in ra phải giống mã bản cài anh ghi trên máy tạo file cài, không kể dấu gạch, chữ hoa hay chữ thường. Nếu hai mã khác nhau, anh đừng chạy file. Đây là lớp bảo vệ duy nhất của lần cài đầu: file cài chưa được kiểm chữ ký với một khóa nào trên máy, nên một file bị tráo sẽ chạy được nếu anh bỏ bước so mã. Khi Terminal đọc file trên USB lần đầu, macOS có thể hỏi bằng tiếng Anh cho Terminal đọc ổ USB; anh bấm Allow.

Sau đó anh chạy file cài bằng lệnh `bash`:

```bash
bash /Volumes/USB/thomhouse-1.4.0.command
```

Anh dùng lệnh này thay cho việc bấm đúp vào file, vì macOS có thể chặn file nhận qua trình duyệt hoặc AirDrop khi bấm đúp; chưa ai thử trường hợp này với file cài. Muốn xem trước kế hoạch cài mà không thay đổi gì, anh thêm `--dry-run`.

Trình cài chạy 25 bước và in tên từng bước, ví dụ `Bước 5/25: Cài Node.js, pnpm và Claude Code`. Các bước hỏi anh theo thứ tự này:

1. Trình cài in mã bản cài tính từ chính file đang chạy và hỏi mã có khớp không. Anh gõ `c` rồi Enter khi khớp.
2. Nếu `~/.thomhouse-bot` đã có dữ liệu của một bản cài khác hoặc của bản đã gỡ, trình cài hỏi anh có dùng dữ liệu đó không. Nếu anh đồng ý, bản cài kia không được chạy nữa, vì hai bản không được chạy trên cùng một dữ liệu.
3. Trình cài liệt kê các phần mềm còn thiếu: Python, Node.js, pnpm và Claude Code, kèm nơi tải, dung lượng và thư mục đặt vào. Anh gõ `c` để cài. Nếu anh gõ `k`, trình cài in cách tự cài từng phần mềm rồi dừng.
4. Trình cài in điều khoản của bộ công cụ Zalo `@ardennguyen/zalo-agent-cli`. Giấy phép của bộ công cụ này là CC BY-NC-SA 4.0, và tệp NOTICE của tác giả ghi rằng giấy phép không cho dùng trong hoạt động kinh doanh của một công ty. Bộ công cụ kết nối Zalo theo cách không chính thức, nên tài khoản Zalo có thể bị khóa. Anh đã đọc và vẫn muốn cài thì gõ `dong y` rồi Enter. Nếu anh chỉ bấm Enter, trình cài dừng và chưa cài bộ công cụ.

Sau đó trình cài tự cài thư viện, tạo file cấu hình và mã bí mật, chép bộ ảnh menu, tạo cơ sở dữ liệu và bật chatbot. Trình cài tìm bộ ảnh menu `thomhouse-menu-<mã menu>.tar` nằm cạnh file cài. Nếu không thấy, chatbot vẫn chạy nhưng chưa gửi được ảnh menu; khi có file, anh chạy `~/ThomHouse/bin/thomhouse install --only menu_slides --menu <file>`. Tiếp theo, trình cài dẫn anh qua các bước cần người làm ở mục sau.

Trình cài kết thúc bằng một bản tóm tắt. Nếu còn bước anh để sau, bản tóm tắt ghi số việc còn lại và lệnh chạy các bước đó:

```bash
~/ThomHouse/bin/thomhouse continue
```

Trình cài trả về một mã thoát cho từng kết quả. Mã 0 nghĩa là đã cài xong. Mã 10 nghĩa là không có lỗi nhưng còn bước đăng nhập Claude, đăng nhập Zalo hoặc đưa mã nhân viên vào console; mã này không phải lỗi. Mã 1 nghĩa là một bước bị lỗi, và trình cài in lý do ngay trước khi dừng. Mã 2 nghĩa là lệnh gõ sai, hoặc trình cài gặp lỗi lạ và ghi chi tiết vào `~/ThomHouse/logs/install.log`. Mã 3 nghĩa là trình cài từ chối chạy, ví dụ vì máy không hợp hoặc một lệnh cài khác đang chạy. Mã 4 nghĩa là anh từ chối một bước bắt buộc.

Nếu lần cài dừng giữa chừng, anh chạy lại đúng lệnh `bash` ở trên khi lệnh thomhouse chưa có trên máy. Khi lệnh thomhouse đã có, anh chạy `~/ThomHouse/bin/thomhouse continue`. Trình cài kiểm tra lại máy ở từng bước và bỏ qua các bước đã xong.

## Những bước nào cần người làm, và làm thế nào?

Mỗi bước cần người làm đều hỏi `[c = có / s = để sau]`. Khi anh chọn `s`, trình cài ghi bước đó là việc còn lại, và lệnh `continue` hỏi lại sau.

### Đăng nhập Claude

Chatbot cần một tài khoản Claude có gói trả phí để soạn tin trả lời. Trình cài tạo cho chatbot một thư mục đăng nhập Claude riêng tên `main`, ở `~/.thomhouse-bot/accounts/main`, nên lần đăng nhập này không trộn với Claude Code anh dùng cho việc khác trên cùng máy. Trình duyệt mở trang đăng nhập Claude bằng tiếng Anh. Nếu Claude hỏi cách đăng nhập, anh chọn tài khoản Claude có gói trả phí, không chọn Anthropic Console.

Đăng nhập xong, anh đăng xuất claude.ai trên trình duyệt của máy này. Trình cài không tự đăng xuất được trình duyệt, và nếu anh quên bước này, nhân viên dùng máy có thể mở tài khoản Claude của anh.

Trình cài chỉ bật tài khoản cho chatbot khi Claude báo đăng nhập bằng tài khoản có gói. Với tài khoản Anthropic Console, trình cài đăng xuất tài khoản đó và hỏi anh đăng nhập lại. Nếu anh để sau, chatbot vẫn nhận tin, nhưng chưa soạn trả lời, và nhân viên trả lời tay trên console. Khi sẵn sàng, anh chạy `~/ThomHouse/bin/thomhouse login-claude`.

Claude có thể không cho biết gói của tài khoản dù tài khoản có gói thật; trường hợp này chưa được thử. Khi đó, chatbot vẫn chưa dùng tài khoản này. Nếu anh đã xem trên claude.ai và chắc tài khoản có gói, anh bật tài khoản bằng tay:

```bash
~/ThomHouse/runtime/python/bin/python3 -I ~/ThomHouse/app/scripts/runner/claude_pool.py enable main
~/ThomHouse/runtime/python/bin/python3 -I ~/ThomHouse/app/scripts/runner/claude_pool.py reset main
```

Sau hai lệnh này, doctor vẫn báo `[CHÚ Ý]` ở dòng Đăng nhập Claude, vì Claude vẫn chưa cho biết gói.

Muốn thêm một tài khoản Claude khác cho chatbot, anh chạy `~/ThomHouse/bin/thomhouse add-claude <tên tài khoản> --priority <số>`. Số nhỏ hơn được dùng trước.

### Đăng nhập Zalo

Mỗi tài khoản Zalo chỉ chạy chatbot trên một máy. Nếu tài khoản đang chạy chatbot ở máy khác, máy kia mất kết nối khi máy này đăng nhập.

Mã QR hiện trong trang `http://127.0.0.1:18927/qr` của trình duyệt, không hiện trong Terminal. Anh mở app Zalo trên điện thoại của studio, chọn Quét mã QR ngay trong app (không dùng camera thường), quét mã rồi xác nhận trên điện thoại. Mã hết hạn sau khoảng 60 giây; chương trình tự tạo mã mới, và anh tải lại trang nếu trang chưa đổi. Đăng nhập xong, trình cài bật phần nhận tin Zalo. Muốn đăng nhập lại sau, anh chạy `~/ThomHouse/bin/thomhouse login-zalo`.

### Lấy tin nhắn cũ (không bắt buộc)

Bước này lấy tin nhắn của 365 ngày trước về máy để phân tích khách. Điện thoại của studio hiện thông báo có nút ĐỒNG BỘ NGAY, và anh bấm nút đó trong vòng 3 phút. Lệnh làm lại là `~/ThomHouse/bin/thomhouse sync-history`.

Sau khi lấy tin cũ, trình cài chạy hai phần phân tích: phân tích danh bạ khách và phân tích các buổi làm trong tin nhắn. Hai phần này chạy trên chính máy đó bằng quy tắc viết sẵn, không gửi tin nhắn nào cho Claude hay cho model khác. Lệnh chạy lại là `~/ThomHouse/bin/thomhouse analyze`. Nếu máy chủ của bản này chưa nhận được kết quả phân tích buổi làm, trình cài in một dòng báo và thử lại ở lần `continue` sau.

### Gắn nhãn khách trong Zalo

Chatbot phân biệt khách với người trong studio bằng nhãn trong app Zalo. Trên điện thoại của studio, anh gắn nhãn Khách hàng, Quản lý hoặc Nhân viên cho từng cuộc trò chuyện, rồi chạy `~/ThomHouse/bin/thomhouse labels`. Lệnh đếm số người đã gắn nhãn và hỏi trước khi chép nhãn vào chatbot. Sau đó, chatbot tự chép lại nhãn mỗi 15 phút.

### Đưa mã nhân viên vào console

Console cần mã nhân viên để nhân viên làm việc. Lệnh `~/ThomHouse/bin/thomhouse staff-token` chép mã vào bộ nhớ tạm (mã không hiện trên màn hình) và mở console trong trình duyệt. Anh vào Cài đặt, bấm vào ô Staff token, nhấn Cmd+V, bấm Lưu, rồi quay lại Terminal gõ `c`. Chương trình xóa mã khỏi bộ nhớ tạm sau tối đa 2 phút.

Chương trình không xóa được mã ở hai nơi. Nếu máy có ứng dụng lưu lịch sử bộ nhớ tạm, anh xóa mục này trong ứng dụng đó. Universal Clipboard của Apple có thể chép mã sang iPhone hoặc iPad đăng nhập cùng Apple ID; chưa ai thử trường hợp này với chatbot. Nếu anh không muốn mã sang thiết bị khác, anh tắt Handoff trong Cài đặt hệ thống trước khi chạy lệnh. Mỗi trình duyệt cần dán mã một lần, và cần dán lại sau khi chuyển máy, vì máy mới có mã bí mật mới.

### Tự bật chatbot và nút bấm trên Desktop

Trình cài hỏi có tự bật chatbot mỗi khi anh đăng nhập máy không. Trình cài cũng hỏi có tạo ba nút bấm trên Desktop không: `Bat-chatbot.command` để bật, `Kiem-tra-chatbot.command` để kiểm tra và `Tat-chatbot.command` để tắt. Trước khi tạo nút, macOS có thể hỏi bằng tiếng Anh cho Terminal ghi vào Desktop; anh bấm Allow. Lệnh đổi ý sau là `~/ThomHouse/bin/thomhouse autostart on` (hoặc `off`) và `~/ThomHouse/bin/thomhouse shortcuts on` (hoặc `off`).

## Các câu macOS hỏi bằng tiếng Anh nghĩa là gì?

| Khi nào | macOS hỏi gì | Anh làm gì |
|---|---|---|
| Terminal đọc file cài trên USB lần đầu | Terminal có được đọc file trên ổ USB không | Bấm Allow |
| Trình cài tạo nút bấm trên Desktop | Terminal có được ghi vào Desktop không | Bấm Allow |
| Bước đăng nhập Claude mở trình duyệt | Trang đăng nhập Claude bằng tiếng Anh hỏi cách đăng nhập | Chọn tài khoản Claude có gói trả phí, không chọn Anthropic Console |
| Lệnh `move-out` tạo file chuyển máy | `hdiutil` hỏi mật khẩu mới cho file chuyển máy, hỏi hai lần | Đặt mật khẩu và ghi lại để mở file ở máy mới |
| Lệnh `move-in` mở file chuyển máy | macOS hỏi mật khẩu của file chuyển máy | Nhập mật khẩu đã đặt ở máy cũ |

## Làm sao biết chatbot đang chạy đúng?

Anh chạy lệnh kiểm tra, hoặc bấm nút `Kiem-tra-chatbot.command` trên Desktop:

```bash
~/ThomHouse/bin/thomhouse doctor
```

Lệnh in 48 dòng, mỗi dòng kiểm một phần của chatbot, ví dụ:

```
[ĐẠT] Hệ điều hành: macOS 15.1
[LỖI] Node.js: chưa có bản 24.19.0. Cách sửa: ~/ThomHouse/bin/thomhouse install --only runtimes
```

Mỗi dòng bắt đầu bằng một trong năm trạng thái. `[ĐẠT]` nghĩa là phần được kiểm chạy đúng. `[LỖI]` nghĩa là phần được kiểm hỏng và cần sửa ngay. `[CHÚ Ý]` nghĩa là chatbot vẫn chạy nhưng anh nên xem lại. `[CHƯA LÀM]` nghĩa là một bước còn để sau, ví dụ chưa đăng nhập Zalo. `[BỎ QUA]` nghĩa là lần chạy này không kiểm phần đó, ví dụ vì chatbot đang tắt. Dòng nào không đạt thì có thêm `Cách sửa:` và lệnh nên chạy.

Lệnh trả về mã 0 khi không có dòng `[LỖI]` nào, và mã 1 khi có. Với `--strict`, lệnh trả về mã 1 cả khi có dòng `[CHÚ Ý]` hoặc `[CHƯA LÀM]`. Lệnh không in mã bí mật, email, mã Zalo, tên khách hay tin nhắn ở bất kỳ dòng nào.

Mỗi lần doctor chạy, chatbot gọi Zalo một lần để kiểm tra đăng nhập, qua cùng cách kết nối không chính thức của bộ công cụ Zalo. Muốn xem nhanh mà không kiểm Zalo và Claude qua mạng, anh thêm `--offline`.

Trước khi cài, anh kiểm tra máy bằng `bash /Volumes/USB/thomhouse-1.4.0.command --doctor`. Lệnh in 5 dòng đầu: hệ điều hành, chip, dung lượng trống, công cụ của macOS và Python. Nếu Python riêng của chatbot hỏng trên máy đã cài, lệnh thomhouse cũng in 5 dòng đó, và dòng Python chỉ lệnh sửa `bash ~/ThomHouse/app/install/bootstrap.sh --python-only`.

## Khi có lỗi thì làm gì?

Anh làm theo dòng `Cách sửa:` của doctor trước. Ba lệnh sửa thường dùng:

- `~/ThomHouse/bin/thomhouse repair` chép lại các file chương trình bị sửa hoặc bị mất từ file cài đã lưu, và đặt lại quyền thư mục.
- `~/ThomHouse/bin/thomhouse repair --env` chép lại mã bí mật từ file cấu hình của máy chủ local sang file cấu hình của runner (phần gọi Claude để soạn tin) và của bridge (phần nối Zalo với máy chủ local), khi doctor báo mã bí mật không khớp.
- `~/ThomHouse/bin/thomhouse repair --paths` ghi lại đường dẫn trong file cấu hình, khi doctor báo đường dẫn trỏ tới thư mục không còn dùng.

Hai lệnh có `--env` và `--paths` hỏi trước khi sửa và không in giá trị nào. Nhật ký của trình cài nằm trong `~/ThomHouse/logs`; nhật ký của chatbot nằm trong `~/.thomhouse-bot/logs`. Các lệnh bật, tắt và bật lại chatbot là `~/ThomHouse/bin/thomhouse start`, `stop` và `restart`.

## Cập nhật lên bản mới thế nào?

Anh cập nhật bằng lệnh thomhouse với file cài mới, không chạy lại file cài:

```bash
~/ThomHouse/bin/thomhouse update /Volumes/USB/thomhouse-1.5.0.command
```

Nếu anh chạy `bash` với file cài trên máy đã cài, file chỉ in lệnh cập nhật ở trên rồi dừng. Lệnh `update` không chạy file cài. Lệnh đọc file như dữ liệu và kiểm chữ ký bằng khóa đã lưu ở lần cài đầu, nên một file bị sửa sẽ bị từ chối. Muốn xem trước mà không thay đổi gì, anh thêm `--dry-run`.

Chatbot tạm tắt vài phút trong lúc cập nhật. Trước khi đổi cơ sở dữ liệu, lệnh sao lưu dữ liệu. Nếu bản mới lỗi trước khi chatbot bật lại, lệnh trả máy về bản cũ, và dữ liệu không mất. Nếu bản mới đã bật nhưng kiểm tra sau khi bật không đạt, lệnh không tự trả về bản cũ, vì lúc đó chatbot có thể đã ghi dữ liệu mới. Khi đó, anh chạy `~/ThomHouse/bin/thomhouse rollback` để về bản trước.

Nếu bộ ảnh menu đổi, anh đặt file `thomhouse-menu-<mã menu>.tar` mới cạnh file cài, hoặc thêm `--menu <file>`. Nếu bản mới cần Claude Code mới hơn, lệnh hỏi anh trước khi cài.

Nếu máy mất điện hoặc cửa sổ bị đóng giữa lúc cập nhật, phần lớn lệnh thomhouse từ chối chạy, và tự bật chatbot khi đăng nhập máy cũng dừng. Anh chạy lại đúng lệnh `update` với cùng file để làm nốt phần còn lại. Nếu lần cập nhật bị ngắt trước khi máy chuyển sang bản mới, lệnh hỏi lại anh có cập nhật không. Khi anh trả lời `k`, lệnh hủy lần cập nhật dở và bật lại chatbot bản cũ.

## Sao lưu và khôi phục thế nào?

Chương trình tự sao lưu trước mỗi lần đổi cơ sở dữ liệu. Anh sao lưu thêm bằng tay và xem danh sách bản sao lưu bằng hai lệnh:

```bash
~/ThomHouse/bin/thomhouse backup
~/ThomHouse/bin/thomhouse backups
```

Bản sao lưu nằm trong `~/.thomhouse-bot/backups`, trên cùng ổ đĩa với dữ liệu. Vì vậy, nếu ổ đĩa hỏng, anh mất cả dữ liệu lẫn bản sao lưu; muốn tránh, anh chép thư mục này sang ổ ngoài theo lịch của anh. Chương trình giữ 5 bản sao lưu mới nhất làm bằng tay hoặc làm trước khi đổi cơ sở dữ liệu. Bản sao lưu trước khi cập nhật được giữ 30 ngày, và bản mới nhất luôn được giữ. Chương trình không bao giờ tự xóa bản sao lưu của lần chuyển máy hay của lần khôi phục. Doctor báo `[CHÚ Ý]` khi bản sao lưu mới nhất đã quá 7 ngày.

Muốn khôi phục, anh chạy `~/ThomHouse/bin/thomhouse restore <mã bản sao lưu>`, với mã lấy từ lệnh `backups`. Mọi tin nhắn và thay đổi sau thời điểm sao lưu sẽ không còn trong dữ liệu đang dùng. Chương trình không xóa dữ liệu hiện tại; chương trình chuyển dữ liệu đó vào một thư mục riêng trong `~/.thomhouse-bot/backups`. Anh gõ `khoi phuc` rồi Enter để xác nhận. Khôi phục xong, anh mở console và xem hàng chờ gửi trước khi nhân viên làm việc tiếp, vì bản sao lưu cũ có thể đưa lại vào hàng chờ những tin đã gửi.

## Chuyển chatbot sang máy khác thế nào?

Chuyển máy có ba bước. Sau bước đầu, máy cũ không được bật chatbot lại, vì mỗi tài khoản Zalo chỉ chạy chatbot trên một máy.

Bước 1, trên máy cũ đã cài bằng file cài, anh chạy lệnh dưới đây với thư mục đích là ổ USB:

```bash
~/ThomHouse/bin/thomhouse move-out --to /Volumes/USB
```

Nếu dữ liệu đang nằm trên máy tạo file cài, anh chạy lệnh trong thư mục dự án:

```bash
cd ~/Projects/lulu-thomhouse
python3 -I install/thomhouse.py move-out --to /Volumes/USB
```

Lệnh hỏi anh xác nhận trước. Sau đó, lệnh tắt chatbot, dừng phần nhận tin Zalo, sao lưu dữ liệu và tạo file chuyển máy `thomhouse-chuyen-may-<ngày giờ>.dmg` đã mã hóa. `hdiutil` hỏi mật khẩu cho file này bằng tiếng Anh; anh đặt mật khẩu và ghi lại. Cuối cùng, lệnh đánh dấu máy cũ, nên cả lệnh thomhouse lẫn `scripts/start_local.sh` đều không bật chatbot trên máy cũ nữa.

Bước 2, trên máy mới chưa cài, anh cài lần đầu và chỉ file chuyển máy cho trình cài:

```bash
bash /Volumes/USB/thomhouse-1.4.0.command --move-in /Volumes/USB/thomhouse-chuyen-may-20261120-0930.dmg
```

Nếu máy mới đã cài sẵn, anh chạy `~/ThomHouse/bin/thomhouse move-in <file chuyển máy>`. macOS hỏi mật khẩu của file chuyển máy; anh nhập mật khẩu đã đặt ở máy cũ.

Bước 3, anh chạy `~/ThomHouse/bin/thomhouse continue` để đăng nhập lại Claude cho từng tài khoản, đăng nhập Zalo và dán mã nhân viên vào console.

| Đi theo sang máy mới | Làm lại trên máy mới |
|---|---|
| Hội thoại, đồng ý của khách, hàng chờ gửi, hồ sơ khách, buổi làm và nhãn khách | Python, Node.js, pnpm, Claude Code và thư viện, vì mỗi máy tự cài |
| Nhật ký gửi tin của bridge, tên và thứ tự các tài khoản Claude, các phiên trò chuyện với Claude | Mã bí mật mới, và mã nhân viên phải dán lại vào từng trình duyệt |
| Kết quả phân tích danh bạ và buổi làm | Đăng nhập Claude cho từng tài khoản, vì lần đăng nhập gắn với máy cũ |
| Các cài đặt không bí mật, như khoảng cách giữa hai tin gửi và chu kỳ chép nhãn | Đăng nhập Zalo bằng mã QR, tự bật chatbot và nút bấm trên Desktop |

Chế độ soạn tin bằng phòng chat hai bot không đi theo. Máy mới bắt đầu với chế độ soạn tin thường. Nếu máy cũ dùng phòng chat hai bot, anh mở `~/ThomHouse/app/apps/runner/.env` trên máy mới, đổi dòng `THOMHOUSE_DRAFT_ENGINE=claude` thành `THOMHOUSE_DRAFT_ENGINE=rooms`, rồi chạy `~/ThomHouse/bin/thomhouse restart`. Trình cài không bao giờ tự đổi dòng này.

Tin nhắn cũ đã lấy từ điện thoại nằm trong `~/.zalo-agent-cli` của máy cũ và không đi theo. Anh chỉ cần lấy lại tin cũ trên máy mới khi muốn chạy lại hai phần phân tích.

Khi muốn bật lại chatbot trên máy cũ, anh tắt chatbot trên máy mới trước, rồi chạy `~/ThomHouse/bin/thomhouse move-back` trên máy cũ. Trên máy tạo file cài, lệnh là `python3 -I install/thomhouse.py move-back` trong thư mục dự án.

## Gỡ chương trình thế nào?

Lệnh gỡ mặc định giữ dữ liệu khách:

```bash
~/ThomHouse/bin/thomhouse uninstall
```

Lệnh hỏi có sao lưu trước không, tắt chatbot, gỡ phần tự bật và các nút bấm do trình cài tạo, rồi xóa `~/ThomHouse`. Sau lệnh gỡ, máy vẫn còn `~/.thomhouse-bot` (dữ liệu khách), `~/.zalo-agent-cli` (đăng nhập Zalo và tin nhắn cũ), Claude Code trong `~/.local` và mã nhân viên trong trình duyệt. Muốn xem trước những gì sẽ bị xóa, anh thêm `--dry-run`.

Muốn xóa cả dữ liệu khách, anh thêm `--data` và gõ `xoa du lieu` khi lệnh hỏi. Lệnh sao lưu lần cuối, đăng xuất các tài khoản Claude của chatbot, dừng phần nhận tin Zalo, rồi chuyển `~/.thomhouse-bot` vào Thùng rác. Nếu macOS không cho Terminal ghi vào Thùng rác, lệnh chuyển thư mục đó thành `~/thomhouse-bot-da-xoa-<ngày giờ>`, và anh tự kéo thư mục này vào Thùng rác. Sau khi gỡ, anh xóa máy này khỏi danh sách thiết bị đã đăng nhập trong app Zalo.

Lệnh gỡ giữ lại dấu chuyển máy trong `~/.thomhouse-bot`, nên một máy đã chuyển dữ liệu đi rồi gỡ chương trình vẫn mang dấu đó. Khi anh cài lại trên máy này, trình cài dừng ở bước Kiểm tra máy và báo dữ liệu đã chuyển sang máy khác. Khi máy kia không còn chạy chatbot, anh xóa file `~/.thomhouse-bot/moved-out.json` bằng tay rồi chạy lại file cài.

## Máy Windows hoặc Linux thì sao?

Chatbot chưa chạy trên Windows, Linux hay WSL. File cài từ chối các hệ điều hành đó trước khi ghi gì lên máy. Bản ghi chú đi kèm file cài cũng nói file chỉ dành cho máy Mac. Mục 16.9 của `docs/contracts.md` ghi những gì cần làm nếu sau này anh muốn hỗ trợ các hệ điều hành đó. Ví dụ, phần nhận tin Zalo dùng một thư viện Python không có trên Windows, nên chatbot phải sửa code trước khi chạy được trên Windows.

## Những gì chưa được thử trên máy thật?

Bộ test của trình cài dùng chương trình giả lập thay cho Claude Code, bộ công cụ Zalo, npm, pnpm và các công cụ của macOS. Vì vậy, các việc sau chưa được thử: một lần cài trên máy Mac không có công cụ dành cho lập trình viên và không có Homebrew; chương trình cài thật của Anthropic và việc so mã Claude Code; các câu macOS hỏi bằng tiếng Anh; đăng nhập Claude bằng tài khoản có gói và bằng tài khoản Anthropic Console; đăng nhập Zalo bằng mã QR; `hdiutil` khi chuyển máy; phần tự bật chatbot khi đăng nhập máy; việc ghi vào Thùng rác khi gỡ; Universal Clipboard. Trước khi studio dựa vào máy thứ hai, anh nên cài thử một lần trên một máy Mac sạch hoặc một máy ảo macOS.

## Nói ngắn gọn nhất

Anh tạo file cài trên máy của anh, ghi lại mã bản cài, mang file sang máy Mac của studio và so mã bằng `shasum -a 256` trước khi chạy `bash <file cài>`. Trình cài tự cài phần mềm riêng cho chatbot sau khi anh đồng ý, rồi dẫn anh qua đăng nhập Claude, đăng nhập Zalo và các bước còn lại; bước nào để sau thì `~/ThomHouse/bin/thomhouse continue` hỏi lại. Từ đó trở đi, anh kiểm tra bằng `doctor`, cập nhật bằng `update <file cài mới>`, và chuyển máy bằng `move-out` rồi cài máy mới với `--move-in`, không để một tài khoản Zalo chạy chatbot trên hai máy cùng lúc. Trình cài chưa được thử trên một máy Mac thật, nên lần cài đầu cần anh theo dõi từng bước.

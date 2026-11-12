"""Texts of the setup package: the 25 install steps, the dry-run plan and the human steps (16.4, 16.6).

Placeholders are ASCII: {n} a number, {title} a step title, {version} the release version, {v} a program version,
{mb} megabytes, {host} a download host, {folder} a folder, {file} a file, {url} an address, {sha256} a checksum,
{cmd} the command to run again, {tb} the launcher (`~/ThomHouse/bin/thomhouse`), {label} a Claude pool account
label, {name} a name, {min} a minimum version, {m} a size in GB, {log} a log file, {minutes} whole minutes,
{customer}, {manager}, {staff} label counts, {names} step titles, {menu_id} the menu archive id, {failed} a folder.
A text never receives a token, an email, a Zalo id, a display name or message text.
"""

TEXTS: dict[str, str] = {
    # ------------------------------------------------------------ step titles (16.4.3)
    "setup.title_verify": "Kiểm tra file cài đặt",
    "setup.title_preflight": "Kiểm tra máy",
    "setup.title_unpack": "Giải nén chương trình",
    "setup.title_python": "Cài Python",
    "setup.title_runtimes": "Cài Node.js, pnpm và Claude Code",
    "setup.title_engine_notice": "Điều khoản bộ công cụ Zalo",
    "setup.title_deps": "Cài thư viện của chương trình",
    "setup.title_activate": "Kích hoạt bản cài",
    "setup.title_config": "Tạo file cấu hình và mã bí mật",
    "setup.title_move_in": "Chuyển dữ liệu từ máy cũ",
    "setup.title_menu_slides": "Chép ảnh menu gốc",
    "setup.title_migrations": "Cập nhật cơ sở dữ liệu",
    "setup.title_pool": "Đăng ký tài khoản Claude cho chatbot",
    "setup.title_claude_login": "Đăng nhập Claude",
    "setup.title_start": "Bật chatbot",
    "setup.title_zalo_login": "Đăng nhập Zalo",
    "setup.title_history_sync": "Lấy tin nhắn cũ từ điện thoại",
    "setup.title_analyze_contacts": "Phân tích danh bạ khách",
    "setup.title_analyze_visits": "Phân tích các buổi làm trong tin nhắn",
    "setup.title_labels": "Gắn nhãn khách trong Zalo",
    "setup.title_staff_token": "Đưa mã nhân viên vào console",
    "setup.title_autostart": "Tự bật chatbot khi đăng nhập máy",
    "setup.title_shortcuts": "Tạo nút bấm trên màn hình",
    "setup.title_menu_check": "Kiểm tra ảnh menu",
    "setup.title_final_check": "Kiểm tra lần cuối",
    # ------------------------------------------------------------ progress and the dry-run plan (16.4.3, 16.4.5)
    "setup.step_line": "Bước {n}/25: {title}",
    "setup.step_line_done": "Bước {n}/25: {title} (đã xong)",
    "setup.step_line_declined": "Bước {n}/25: {title} (anh đã chọn không)",
    "setup.step_postponed": "Bước này cần người ngồi trước máy, nên chương trình để sau.\n"
    "Khi sẵn sàng, anh chạy: {tb} continue",
    "setup.only_unknown": "Không có bước {name}. Anh gõ số bước từ 1 đến 25, hoặc tên bước trong hướng dẫn cài đặt.",
    "setup.plan_head": "Kế hoạch cài chatbot thom house bản {version} (chạy thử, máy không thay đổi gì):",
    "setup.mark_done": "đã xong",
    "setup.mark_todo": "sẽ làm",
    "setup.mark_skip": "bỏ qua",
    "setup.plan_item": "{name} {v} từ {host}, {mb} MB, vào {folder}",
    "setup.plan_item_nosize": "{name} {v} từ {host}, vào {folder}",
    "setup.plan_claude": "Claude Code {v} từ chương trình cài của Anthropic (claude.ai), khoảng {mb} MB, vào ~/.local",
    # ------------------------------------------------------------ step 2: preflight (16.5, rev F3, F12, F20)
    "setup.preflight_not_mac": "Chatbot chỉ chạy trên máy Mac có macOS {min} trở lên; hệ điều hành {name} "
    "chưa được hỗ trợ.",
    "setup.preflight_macos": "Máy đang chạy macOS {v}; chatbot cần macOS {min} trở lên. "
    "Anh cập nhật macOS rồi chạy lại.",
    "setup.preflight_root": "Anh chạy lại lệnh cài bằng tài khoản thường của máy, không dùng sudo.",
    "setup.preflight_intel": "Máy Intel chưa được chạy thử. Anh vẫn cài? [c = có / k = không]",
    "setup.preflight_intel_no_pins": "File cài này chưa có bản cho máy Intel.",
    "setup.preflight_disk": "Ổ đĩa chỉ còn {n} GB trống, chatbot cần ít nhất {m} GB. Anh xóa bớt tệp rồi chạy lại.",
    "setup.preflight_tools": "Máy thiếu công cụ {name} của macOS. Đây là lỗi lạ trên macOS; anh báo người phụ trách.",
    "setup.preflight_other_stack": "Một bản chatbot khác ({folder}) đang chạy với cùng dữ liệu.\n"
    "Anh tắt bản đó bằng scripts/stop_local.sh trong thư mục đó rồi chạy lại.",
    "setup.shared_data": "Máy này đã có dữ liệu chatbot ở {folder}, của một bản cài khác hoặc của bản đã gỡ.\n"
    "Bản cài mới sẽ dùng dữ liệu đó; nếu bản kia vẫn còn trên máy, anh không chạy bản kia nữa.\n"
    "Dùng dữ liệu đó? [c = có / k = không]",
    "setup.shared_data_declined": "Chương trình dừng ở đây và chưa dùng dữ liệu đó.\n"
    "Khi anh đồng ý, anh chạy lại: {cmd}",
    # ------------------------------------------------------------ steps 1, 3, 4: release file and Python
    "setup.release_file_missing": "Chương trình chưa thấy file cài của bản {version}.\n"
    "Anh chạy lại file thomhouse-{version}.command.",
    "setup.release_damaged": "Các tệp của bản {version} trên máy bị sửa hoặc bị mất.\n"
    "Anh chạy lại file thomhouse-{version}.command.",
    "setup.file_missing": "Không thấy file {file}. Anh kiểm tra lại đường dẫn rồi chạy lại.",
    "setup.python_wrong": "Python riêng của chatbot chưa đúng bản {v}.\n"
    "Anh chạy: bash {folder}/install/bootstrap.sh --python-only",
    # ------------------------------------------------------------ step 5: runtimes (16.4.7 runtime plan, rev F11)
    "setup.runtime_plan_head": "Máy cần thêm các phần mềm dưới đây. Chương trình cài chúng cho riêng chatbot,\n"
    "không cần mật khẩu máy và không sửa cài đặt của Terminal:",
    "setup.runtime_plan_item": "  - {name} {v}: tải từ {host}, {mb} MB, đặt vào {folder}",
    "setup.runtime_plan_item_nosize": "  - {name} {v}: tải từ {host}, đặt vào {folder}",
    "setup.runtime_plan_claude": "  - Claude Code {v}: chương trình cài của Anthropic (claude.ai), khoảng {mb} MB, "
    "vào ~/.local",
    "setup.runtime_ask": "Anh gõ c rồi Enter để cài, hoặc gõ k rồi Enter để dừng.",
    "setup.runtime_declined_head": "Chương trình chưa cài phần mềm nào; mã chương trình đã chép vào {folder}.\n"
    "Chatbot chỉ chạy với đúng các bản dưới đây:",
    "setup.runtime_declined_node": "  - Node.js {v}: tải tại {url}\n    mã SHA-256 {sha256}",
    "setup.runtime_declined_pnpm": "  - pnpm {v}: cần mạng tới registry.npmjs.org; không cài tay được.",
    "setup.runtime_declined_claude": "  - Claude Code {v}: anh tự cài bằng lệnh dưới đây rồi chạy lại lệnh cài:\n"
    "    curl -fsSL {url} | bash -s {v}",
    "setup.runtime_declined_tail": "Khi sẵn sàng, anh chạy lại: {cmd}",
    # ------------------------------------------------------------ step 6: licence notice (16.4.7, rev owner)
    "setup.engine_notice": "Chatbot nhận và gửi tin Zalo qua bộ công cụ @ardennguyen/zalo-agent-cli {v}.\n"
    "Giấy phép của bộ công cụ này là CC BY-NC-SA 4.0. Tệp NOTICE của tác giả ghi rằng\n"
    "giấy phép không cho dùng trong hoạt động kinh doanh của một công ty.\n"
    "Bộ công cụ dùng cách kết nối Zalo không chính thức, nên tài khoản Zalo có thể bị khóa.\n"
    "Anh đã đọc và vẫn muốn cài thì gõ dong y rồi Enter. Chỉ Enter để dừng.",
    "setup.engine_declined": "Chương trình chưa cài bộ công cụ Zalo và dừng ở đây.\n"
    "Khi anh đồng ý, anh chạy lại: {cmd}",
    # ------------------------------------------------------------ steps 7 to 13
    "setup.deps_rooms_warn": "Chưa cài được OpenMausBot; phòng chat hai bot sẽ tắt, chatbot vẫn trả lời bình thường.",
    "setup.activate_other_version": "Máy đang chạy bản {v}; muốn lên bản {version}, anh dùng lệnh update:\n"
    "{tb} update <file thomhouse-{version}.command>",
    "setup.config_failed": "Chưa tạo được file cấu hình của chatbot. Anh chạy lại: {cmd}",
    "setup.config_missing": "Thiếu file cấu hình {file}. Anh chạy lại: {cmd}",
    "setup.move_in_failed": "Chưa chuyển được dữ liệu từ máy cũ; chương trình đã trả dữ liệu đang dùng về chỗ cũ.",
    "setup.move_in_refused": "Dữ liệu trong file chuyển máy mới hơn bản cài này, nên chương trình chưa dùng.\n"
    "Anh cập nhật bản cài trước rồi chạy lại.",
    "setup.move_in_declined": "Chưa có mật khẩu của file chuyển máy, nên chương trình dừng ở đây.",
    "setup.menu_missing": "Chưa có file ảnh menu thomhouse-menu-{menu_id}.tar, nên chatbot chưa gửi được ảnh menu.\n"
    "Có file đó rồi, anh chạy: {tb} install --only menu_slides --menu <file>",
    "setup.migrations_failed": "Chưa cập nhật được cơ sở dữ liệu; chi tiết ở {log}.",
    "setup.migrations_restored": "Chương trình đã trả dữ liệu về bản sao lưu vừa tạo ({folder}).",
    "setup.migrations_restore_failed": "Chưa trả được dữ liệu về bản sao lưu {folder}.\n"
    "Dữ liệu lúc lỗi nằm ở {failed}. Anh báo người phụ trách trước khi bật chatbot.\n"
    "Chatbot chưa bật. Lệnh {cmd} sẽ chép lại dữ liệu từ bản sao lưu trước tiên.",
    "setup.migrations_restore_missing": "Chương trình không tìm thấy bản sao lưu {folder} để trả dữ liệu về,\n"
    "nên chưa cập nhật cơ sở dữ liệu và chưa bật chatbot. Anh báo người phụ trách.",
    "setup.restore_needed": "Lần cập nhật cơ sở dữ liệu trước bị lỗi, và dữ liệu chatbot chưa được chép lại\n"
    "từ bản sao lưu {folder}, nên chương trình chưa làm lệnh này và chưa bật chatbot.\n"
    "Anh chạy: {tb} continue",
    "setup.pool_failed": "Chưa đăng ký được tài khoản Claude cho chatbot. Anh chạy lại: {cmd}",
    # ------------------------------------------------------------ step 14: Claude login (16.6.1, rev F8, F17)
    "setup.claude_account": "Tài khoản Claude của chatbot: {label}.",
    "setup.claude_screen": "Chatbot cần đăng nhập một tài khoản Claude để soạn tin trả lời.\n"
    "Trình duyệt sẽ mở trang đăng nhập Claude. Nếu Claude hỏi cách đăng nhập,\n"
    "anh chọn tài khoản Claude có gói trả phí, không chọn Anthropic Console.\n"
    "Đăng nhập xong, anh quay lại cửa sổ này.\n"
    "Mở trang đăng nhập ngay? [c = có / s = để sau]",
    "setup.claude_done": "Đã đăng nhập Claude cho chatbot.",
    "setup.claude_browser_logout": "Anh đăng xuất claude.ai trên trình duyệt của máy này,\n"
    "để nhân viên không mở được tài khoản Claude của anh.",
    "setup.claude_console": "Tài khoản vừa đăng nhập không có gói Claude trả phí "
    "(có thể anh đã chọn Anthropic Console).\n"
    "Anh đăng nhập lại bằng tài khoản có gói. [c = thử lại / s = để sau]",
    "setup.claude_no_plan": "Claude chưa cho biết gói của tài khoản này nên chatbot chưa dùng tài khoản đó.\n"
    "Anh thử lại? [c = thử lại / s = để sau]",
    "setup.claude_not_logged_in": "Máy chưa thấy tài khoản Claude đăng nhập. Anh thử lại? [c = thử lại / s = để sau]",
    "setup.claude_later": "Anh chọn đăng nhập sau. Chatbot vẫn nhận tin nhưng chưa soạn trả lời;\n"
    "nhân viên trả lời tay trên console. Khi sẵn sàng, anh chạy: {tb} login-claude",
    "setup.claude_no_pool": "Chatbot chưa có tài khoản Claude nào. Anh chạy: {tb} continue",
    "setup.claude_unknown_label": "Chatbot không có tài khoản Claude tên {label}.",
    "setup.claude_label_exists": "Chatbot đã có tài khoản Claude tên {label}.\n"
    "Anh đăng nhập tài khoản đó bằng: {tb} login-claude {label}",
    "setup.claude_add_failed": "Chưa thêm được tài khoản Claude {label} vào chatbot.",
    "setup.claude_enable_failed": "Chưa bật được tài khoản Claude {label} trong chatbot. Anh chạy lại: {tb} login-claude {label}",
    "setup.claude_restart_rooms": "Anh chạy {tb} restart để phòng chat hai bot dùng tài khoản mới.",
    # ------------------------------------------------------------ step 16: Zalo QR login (16.6.2)
    "setup.zalo_screen": "Bước này đăng nhập tài khoản Zalo của studio vào máy này.\n"
    "Mỗi tài khoản Zalo chỉ chạy chatbot trên một máy: nếu tài khoản này đang chạy ở máy khác,\n"
    "máy kia sẽ mất kết nối.\n"
    "Trình duyệt sẽ hiện mã QR. Anh mở app Zalo trên điện thoại của studio,\n"
    "chọn Quét mã QR ngay trong app (không dùng camera thường), quét mã rồi xác nhận trên điện thoại.\n"
    "Bắt đầu? [c = có / s = để sau]",
    "setup.zalo_qr_opened": "Mã QR đã mở trong trình duyệt. Mã hết hạn sau khoảng 60 giây;\n"
    "khi đó chương trình tự tạo mã mới, anh tải lại trang nếu trang chưa đổi.",
    "setup.zalo_scanned": "Điện thoại đã quét mã. Anh xác nhận đăng nhập trên điện thoại.",
    "setup.zalo_retry": "Chưa đăng nhập được Zalo. Anh thử lại? [c = thử lại / s = để sau]",
    "setup.zalo_done": "Đã đăng nhập Zalo. Chatbot bắt đầu nhận tin.",
    "setup.zalo_foreign": "Một chương trình zalo-agent khác đang giữ kết nối của tài khoản này.\n"
    "Anh cho dừng chương trình đó? [c = có / s = để sau]",
    "setup.zalo_listener_failed": "Chưa bật được phần nhận tin Zalo. Anh chạy {tb} doctor để xem chi tiết.",
    "setup.zalo_later": "Anh chọn đăng nhập Zalo sau. Khi sẵn sàng, anh chạy: {tb} login-zalo",
    "setup.zalo_no_engine": "Bản cài chưa có bộ công cụ Zalo. Anh chạy: {tb} install --only deps",
    # ------------------------------------------------------------ step 17: history sync (16.6.3)
    "setup.sync_screen": "Bước này lấy tin nhắn của 365 ngày trước về máy để phân tích khách (không bắt buộc).\n"
    "Điện thoại của studio sẽ hiện thông báo có nút ĐỒNG BỘ NGAY. Anh bấm nút đó trong vòng 3 phút.\n"
    "Bắt đầu? [c = có / s = để sau]",
    "setup.sync_countdown": "Còn {n} giây để bấm ĐỒNG BỘ NGAY trên điện thoại.",
    "setup.sync_done": "Đã lấy xong tin nhắn cũ.",
    "setup.sync_retry": "Chưa lấy được tin nhắn cũ, có thể vì chưa bấm kịp trên điện thoại.\n"
    "Anh thử lại? [c = thử lại / s = để sau]",
    "setup.sync_needs_zalo": "Cần đăng nhập Zalo trước khi lấy tin nhắn cũ. Anh chạy: {tb} login-zalo",
    "setup.sync_later": "Anh chọn lấy tin nhắn cũ sau. Khi sẵn sàng, anh chạy: {tb} sync-history",
    # ------------------------------------------------------------ steps 18 and 19: analyzers (rev visits)
    "setup.analyze_no_cache": "Máy chưa có tin nhắn Zalo đã lấy về, nên chưa có gì để phân tích.\n"
    "Anh chạy: {tb} sync-history",
    "setup.contacts_done": "Đã phân tích danh bạ khách.",
    "setup.contacts_failed": "Chưa phân tích được danh bạ khách; lần chạy {tb} continue sau sẽ thử lại.",
    "setup.visits_server_404": "Máy chủ chưa nhận được kết quả phân tích buổi làm; "
    "lần chạy thomhouse continue sau sẽ thử lại.",
    "setup.visits_done": "Đã phân tích các buổi làm trong tin nhắn.",
    "setup.visits_failed": "Chưa phân tích được các buổi làm; lần chạy {tb} continue sau sẽ thử lại.",
    # ------------------------------------------------------------ step 20: labels (16.6.4)
    "setup.labels_screen": "Chatbot phân biệt khách với người trong studio bằng nhãn trong app Zalo.\n"
    "Trên điện thoại của studio, anh gắn nhãn cho từng cuộc trò chuyện:\n"
    "  - Khách hàng: người đến làm dịch vụ\n"
    "  - Quản lý: chủ và người quản lý studio\n"
    "  - Nhân viên: nhân viên của studio\n"
    "Gắn xong thì gõ c rồi Enter để kiểm tra, hoặc gõ s để làm sau.",
    "setup.labels_none": "Chưa thấy cuộc trò chuyện nào được gắn nhãn. [c = kiểm tra lại / s = để sau]",
    "setup.labels_found": "Đã thấy {customer} khách hàng, {manager} quản lý, {staff} nhân viên được gắn nhãn.\n"
    "Chép vào chatbot? [c = có / s = để sau]",
    "setup.labels_done": "Đã chép nhãn vào chatbot. Chatbot tự chép lại mỗi 15 phút.",
    "setup.labels_failed": "Chưa chép được nhãn vào chatbot. Anh chạy {tb} doctor để xem chi tiết.",
    "setup.labels_later": "Anh chọn gắn nhãn sau. Khi sẵn sàng, anh chạy: {tb} labels",
    # ------------------------------------------------------------ step 21: staff token (16.6.5, rev F16, F17)
    "setup.token_screen": "Chương trình đã chép mã nhân viên vào bộ nhớ tạm; mã không hiện trên màn hình.\n"
    "Trình duyệt vừa mở console. Anh vào Cài đặt, bấm vào ô Staff token, nhấn Cmd+V rồi bấm Lưu.\n"
    "Dán xong thì gõ c rồi Enter. Chương trình xóa mã khỏi bộ nhớ tạm sau {minutes} phút.\n"
    "Nếu máy có ứng dụng lưu lịch sử bộ nhớ tạm, anh xóa mục này trong ứng dụng đó.\n"
    "[c = đã dán / s = để sau]",
    "setup.token_missing": "Chưa có mã nhân viên trong file cấu hình. Anh chạy: {tb} continue",
    "setup.token_console_not_local": "Địa chỉ trang quản lý trong THOMHOUSE_CONSOLE_URL ({url}) không nằm trên máy này,\n"
    "nên chương trình không chép mã nhân viên.\n"
    "Anh bỏ biến THOMHOUSE_CONSOLE_URL rồi chạy lại: {tb} staff-token",
    "setup.token_copy_failed": "Chưa chép được mã nhân viên vào bộ nhớ tạm. Anh chạy lại: {tb} staff-token",
    "setup.token_done": "Đã xóa mã nhân viên khỏi bộ nhớ tạm.",
    "setup.token_later": "Đã xóa mã nhân viên khỏi bộ nhớ tạm. Khi sẵn sàng, anh chạy: {tb} staff-token",
    "setup.needs_terminal": "Lệnh này cần anh gõ phím trong Terminal, nên chương trình chưa làm gì.",
    # ------------------------------------------------------------ steps 22 and 23: autostart and shortcuts
    "setup.autostart_ask": "Tự bật chatbot mỗi khi anh đăng nhập máy này? [c = có / k = không]",
    "setup.autostart_done": "Chatbot sẽ tự bật khi anh đăng nhập máy.",
    "setup.autostart_failed": "Chưa cài được phần tự bật chatbot; anh vẫn bật tay được bằng: {tb} start",
    "setup.shortcuts_ask": "Tạo ba nút bấm trên Desktop để bật, kiểm tra và tắt chatbot? [c = có / k = không]",
    "setup.shortcuts_done": "Đã tạo nút bấm trên Desktop.",
    "setup.shortcuts_failed": "Chưa tạo được nút bấm trên Desktop; anh vẫn dùng được lệnh: {tb} start",
    "setup.consent_later": "Không có ai trả lời câu này, nên chương trình hỏi lại ở lần chạy {tb} continue sau.",
    # ------------------------------------------------------------ steps 15, 24, 25
    "setup.start_failed": "Chatbot chưa bật được; chi tiết ở {log}.",
    "setup.check_failed": "[LỖI] {label}: {detail}",
    "setup.check_fix": "  Cách sửa: {fix}",
    "setup.menu_check_failed": "Ảnh menu cho Zalo chưa đủ; bot chưa gửi được ảnh menu. Anh chạy: {tb} restart",
    "setup.summary_running": "Chatbot thom house bản {version} đang chạy trên máy này.\n"
    "Console cho nhân viên: {url}",
    "setup.summary_left": "Còn {n} việc anh cần làm: {names}.\nKhi sẵn sàng, anh chạy: {tb} continue",
    "setup.summary_none": "Đã cài xong, không còn việc nào.",
    "setup.summary_errors": "Còn {n} lỗi ở các dòng trên. Anh sửa theo hướng dẫn rồi chạy: {tb} continue",
}

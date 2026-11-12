"""Texts of the release package (16.4.7 and the WP2 modules release, runtimes, deps, repair).

The shell files `selfextract.sh.in`, `bootstrap.sh` and `thomhouse.sh.in` print the same screens before Python
exists; `test_release_texts` keeps their copies equal to the texts here. Placeholders: {file} a release file,
{name} what is installed, {cmd} the command to run again (the dispatcher fills it for errors), {tb} the launcher,
{v} a version, {n} a number, {host} a server, {folder} a folder.
"""

TEXTS: dict[str, str] = {
    # ---------------------------------------------------------------- release files (ReleaseError)
    "release.already_installed": "Máy này đã cài chatbot thom house, nên file cài không chạy lại từ đầu.\n"
    "Cập nhật bằng file này: ~/ThomHouse/bin/thomhouse update {file}\n"
    "Các bước còn lại: ~/ThomHouse/bin/thomhouse continue",
    "release.damaged": "File cài đặt bị hỏng hoặc đã bị sửa nên chương trình chưa cài gì. "
    "Anh chép lại file rồi chạy lại.",
    "release.signature": "File cài không mang chữ ký của người làm file cài, nên chương trình không dùng file này.\n"
    "Anh báo người gửi file.",
    "release.not_release": "File này không phải file cài chatbot thom house, nên chương trình không dùng file này.",
    "release.older": "File cài là bản cũ hơn bản đang chạy, nên chương trình không cập nhật.\n"
    "Muốn quay về bản trước: {tb} rollback",
    "release.same": "Máy đã chạy đúng bản trong file cài, nên chương trình không cập nhật.",
    "release.denylisted": "File cài có tệp không được mang theo, nên chương trình không dùng file này.\n"
    "Anh báo người làm file cài.",
    "release.menu_damaged": "File ảnh menu bị hỏng hoặc không khớp bản cài, nên chương trình chưa chép ảnh.\n"
    "Anh chép lại file thomhouse-menu-<mã>.tar rồi chạy lại.",
    # ---------------------------------------------------------------- runtimes (RuntimeInstallError)
    "release.installing": "Đang cài {name}; việc này có thể mất vài phút.",
    "release.runtime_unpack": "Chưa cài được {name}; chi tiết ở ~/ThomHouse/logs/runtimes.log.\n"
    "Anh chạy lại: {cmd}",
    "release.runtime_version": "{name} vừa cài không chạy đúng bản đã ghi trong file cài, "
    "nên chương trình đã xóa bản đó.\nAnh báo người gửi file.",
    "release.runtime_installer": "Chưa cài được Claude Code; chi tiết ở ~/ThomHouse/logs/runtimes.log.",
    "release.runtime_checksum": "Bản Claude Code vừa tải không khớp bản đã thử trên máy tạo file cài,\n"
    "nên chương trình đã gỡ bản đó. Anh báo người gửi file.",
    # The runtime plan of 16.4.7 (bootstrap.sh prints the same lines in bash).
    "release.plan_head": "Máy cần thêm các phần mềm dưới đây. Chương trình cài chúng cho riêng chatbot,\n"
    "không cần mật khẩu máy và không sửa cài đặt của Terminal:",
    "release.plan_python": "  - Python {v}: tải từ {host}, {n} MB, đặt vào {folder}",
    "release.plan_node": "  - Node.js {v}: tải từ {host}, {n} MB, đặt vào {folder}",
    "release.plan_pnpm": "  - pnpm {v}: tải từ {host}, {n} MB, đặt vào {folder}",
    "release.plan_claude": "  - Claude Code {v}: chương trình cài của Anthropic (claude.ai), khoảng {n} MB, "
    "vào ~/.local",
    "release.plan_claude_other": "    Máy đã có một bản Claude Code khác; chatbot dùng bản riêng này, "
    "bản kia giữ nguyên.",
    "release.plan_ask": "Anh gõ c rồi Enter để cài, hoặc gõ k rồi Enter để dừng.",
    "release.decline_head": "Chương trình chưa cài phần mềm nào; mã chương trình đã chép vào {folder}.\n"
    "Chatbot chỉ chạy với đúng các bản dưới đây:",
    "release.decline_pnpm": "  - pnpm {v}: cần mạng tới registry.npmjs.org; không cài tay được.",
    "release.decline_claude": "  - Claude Code {v}: anh tự cài bằng lệnh dưới đây rồi chạy lại lệnh cài:",
    "release.decline_tail": "Với Python và Node.js, anh có thể tải file ở máy khác và chép vào {folder},\n"
    "rồi chạy lại lệnh cài; chương trình kiểm mã từng file trước khi dùng.",
    # ---------------------------------------------------------------- dependencies (DepsError)
    "release.deps_workspace": "Chưa cài được thư viện từ registry.npmjs.org; chi tiết ở ~/ThomHouse/logs/deps.log.\n"
    "Anh kiểm tra mạng rồi chạy lại: {cmd}",
    "release.deps_engine": "Chưa cài được thư viện từ registry.npmjs.org; chi tiết ở ~/ThomHouse/logs/deps.log.\n"
    "Anh kiểm tra mạng rồi chạy lại: {cmd}",
    "release.deps_rooms_warn": "Chưa cài được OpenMausBot; phòng chat hai bot sẽ tắt, chatbot vẫn trả lời "
    "bình thường.",
    # ---------------------------------------------------------------- thomhouse repair
    "release.repair_not_installed": "Máy này chưa cài chatbot thom house, nên chưa có gì để sửa.",
    "release.repair_relinked": "Đã trỏ chương trình về lại bản {v}.",
    "release.repair_no_release": "Máy không còn thư mục của bản {v}, nên chương trình chưa sửa được.\n"
    "Anh cài lại bằng file thomhouse-{v}.command.",
    "release.repair_restored": "Đã chép lại {n} tệp chương trình từ file cài đã lưu trên máy.",
    "release.repair_no_cache": "Máy không còn file cài bản {v} đã lưu, nên chưa chép lại được tệp chương trình.\n"
    "Anh chép file thomhouse-{v}.command vào {folder} rồi chạy lại lệnh này.",
    "release.repair_files_bad": "Còn {n} tệp chương trình chưa sửa được; chi tiết ở ~/ThomHouse/logs/install.log.",
    "release.repair_files_ok": "Các tệp chương trình đều đúng.",
    "release.repair_launcher": "Đã viết lại lệnh {tb}.",
    "release.repair_modes": "Đã sửa quyền của {n} thư mục để người khác trên máy không đọc được.",
    "release.repair_paths_ask": "Chương trình sẽ xóa các đường dẫn cũ trong file cấu hình rồi bật lại chatbot.\n"
    "Chatbot tắt khoảng một phút. Tiếp tục? [c = có / k = không]",
    "release.repair_env_ask": "Chương trình sẽ chép mã bí mật của máy chủ sang file cấu hình của runner "
    "và bridge,\nrồi bật lại chatbot. Chatbot tắt khoảng một phút. Tiếp tục? [c = có / k = không]",
    "release.repair_paths_done": "Đã xóa các đường dẫn cũ; khi bật, chatbot ghi lại đường dẫn của bản cài này.",
    "release.repair_env_done": "Đã chép mã bí mật sang file cấu hình của runner và bridge; mã không hiện ra màn hình.",
    "release.repair_env_missing": "File cấu hình của máy chủ thiếu mã bí mật, nên chương trình chưa chép được.\n"
    "Anh chạy: {tb} continue",
    "release.repair_declined": "Anh chọn không sửa, nên chương trình chưa thay đổi gì.",
    "release.repair_restart_failed": "Chưa bật lại được chatbot; chi tiết ở ~/ThomHouse/logs/start.log.\n"
    "Anh xem chi tiết bằng: {tb} doctor",
    "release.repair_done": "Đã sửa xong.",
}

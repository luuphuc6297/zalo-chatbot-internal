"""Texts of the operations package (16.4.7 keyed lines, 16.8): backup, restore, update, rollback, move, uninstall,
autostart, shortcuts and the start, stop and restart commands.

Placeholders (ASCII): {tb} the launcher or `python3 -I install/thomhouse.py`, {start} the command that starts the
chatbot, {file}, {folder}, {log}, {id}, {time}, {reason}, {version}, {old}, {new}, {current}, {title} a phase title,
{phase}, {mb}, {status}, {label}, {detail}, {fix}, {menu_id}, {source}, {backup}, {failed}, {bot}, {zalo},
{target}, {path}. A text longer than 100 characters is printed as several lines (16.4.7).
"""

TEXTS: dict[str, str] = {
    # ------------------------------------------------------------ keyed in 16.4.7 and 16.8.1 (exact wording)
    "ops.desktop_prompt": "macOS có thể hỏi bằng tiếng Anh cho Terminal ghi vào Desktop; anh bấm Allow.",
    "ops.hdiutil_create": "Ngay sau đây hdiutil hỏi mật khẩu bằng tiếng Anh. Anh đặt mật khẩu và ghi lại để mở ở máy "
    "mới.",
    "ops.hdiutil_attach": "Ngay sau đây macOS hỏi mật khẩu của file chuyển máy; anh nhập mật khẩu đã đặt ở máy cũ.",
    "ops.update_same": "Máy đã chạy bản {version}, nên không cần cập nhật.\n"
    "Các bước còn lại: ~/ThomHouse/bin/thomhouse continue",
    # ------------------------------------------------------------ backup (16.8.2)
    "ops.backup_space": "Ổ đĩa không đủ chỗ trống để sao lưu; bản sao lưu cần gấp đôi dung lượng dữ liệu.\n"
    "Anh xóa bớt tệp rồi chạy lại.",
    "ops.backup_verify": "Bản sao lưu vừa chép không qua được bước kiểm tra, nên chương trình đã bỏ bản đó.\n"
    "Dữ liệu đang dùng vẫn giữ nguyên. Anh báo người phụ trách.",
    "ops.backup_copy": "Chương trình chưa chép được một tệp dữ liệu, nên chưa sao lưu xong.\n"
    "Dữ liệu đang dùng vẫn giữ nguyên. Chi tiết nằm trong thư mục logs của chương trình.",
    "ops.backup_refused": "Chatbot đang chạy, nên chương trình chưa sao lưu theo cách --stopped.\n"
    "Anh tắt chatbot trước, hoặc sao lưu ngay khi chatbot đang chạy bằng: {tb} backup --online",
    "ops.backup_locked": "Một lần sao lưu khác đang chạy và chưa xong sau 5 phút. Anh chờ lần đó xong rồi chạy lại.",
    "ops.backup_done": "Đã sao lưu xong bản {id} ({mb} MB) vào {folder}.",
    "ops.backups_none": "Máy chưa có bản sao lưu nào. Anh sao lưu bằng: {tb} backup",
    "ops.backups_line": "{id}  {time}  {reason}  bản {version}  {mb} MB  {status}",
    "ops.backup_checked": "đã kiểm",
    "ops.backup_broken": "lỗi",
    "ops.check_failed": "[LỖI] {label}: {detail}",
    "ops.check_failed_fix": "[LỖI] {label}: {detail} Cách sửa: {fix}",
    # ------------------------------------------------------------ restore (16.8.3)
    "ops.restore_not_found": "Máy không có bản sao lưu {id}. Anh xem danh sách bằng: {tb} backups",
    "ops.restore_damaged": "Bản sao lưu {id} bị hỏng hoặc thiếu tệp, nên chương trình không khôi phục từ bản này.",
    "ops.restore_newer": "Bản sao lưu {id} đến từ bản chương trình mới hơn bản trên máy này,\n"
    "nên chương trình không khôi phục. Anh cập nhật chương trình trước rồi chạy lại.",
    "ops.restore_dry_run": "Chạy thử, máy không thay đổi gì.\n"
    "Lệnh này sẽ khôi phục bản sao lưu {id} lúc {time} ({reason}).\n"
    "Dữ liệu hiện tại sẽ chuyển vào {folder}, không bị xóa.",
    "ops.restore_dry_env_same": "Bản sao lưu là của máy này, nên file cấu hình cũng được khôi phục;\n"
    "console vẫn dùng được mã nhân viên cũ.",
    "ops.restore_dry_env_other": "Bản sao lưu là của máy khác, nên file cấu hình và mã bí mật của máy này giữ nguyên.",
    "ops.restore_confirm": "Bản sao lưu lúc {time} ({reason}).\n"
    "Mọi tin nhắn và thay đổi sau thời điểm đó sẽ không còn trong dữ liệu đang dùng;\n"
    "dữ liệu hiện tại được giữ trong {folder}.\n"
    "Gõ khoi phuc rồi Enter để khôi phục, hoặc chỉ Enter để thôi.",
    "ops.restore_declined": "Anh chưa gõ khoi phuc, nên chương trình không thay đổi gì.",
    "ops.restore_failed": "Khôi phục chưa xong, nên chương trình đã đưa dữ liệu đang dùng trở lại như trước\n"
    "và bật lại chatbot. "
    "Chi tiết ở {log}.",
    "ops.restore_done": "Đã khôi phục bản sao lưu {id}. Dữ liệu trước khi khôi phục nằm ở {folder}.",
    "ops.restore_queue_note": "Anh mở console và xem hàng chờ gửi trước khi nhân viên làm việc tiếp.",
    # ------------------------------------------------------------ start, stop (service.py) and shared lines
    "ops.stop_survivor": "Một phần của chatbot vẫn chạy sau lệnh tắt, nên chương trình dừng ở đây.\n"
    "Anh chạy {tb} doctor để xem phần nào còn chạy.",
    "ops.start_failed": "Chưa bật được chatbot; chi tiết ở {log}.\nAnh chạy {tb} doctor để xem phần nào lỗi.",
    "ops.start_unhealthy": "Chatbot đã bật nhưng chưa qua bước kiểm tra. Anh chạy {tb} doctor để xem chi tiết.",
    "ops.start_done": "Chatbot đang chạy. Console cho nhân viên: http://127.0.0.1:5173",
    "ops.stop_done": "Đã tắt chatbot.",
    "ops.health_processes": "[LỖI] Các phần của chatbot: chưa chạy đủ sau khi bật.",
    "ops.health_server_health": "[LỖI] Máy chủ local: máy chủ chưa trả lời.",
    "ops.health_console": "[LỖI] Console: console chưa mở.",
    # ------------------------------------------------------------ update (16.8.1)
    "ops.phase_u1": "kiểm tra file cập nhật",
    "ops.phase_u2": "giải nén bản mới",
    "ops.phase_u3": "cài phần mềm cho bản mới",
    "ops.phase_u4": "cài thư viện cho bản mới",
    "ops.phase_u5": "chép ảnh menu",
    "ops.phase_u6": "chép file cấu hình",
    "ops.phase_u7": "tắt chatbot",
    "ops.phase_u8": "sao lưu dữ liệu",
    "ops.phase_u9": "chuyển sang bản mới",
    "ops.phase_u10": "cập nhật cơ sở dữ liệu",
    "ops.phase_u11": "bật chatbot bản mới",
    "ops.phase_u12": "kiểm tra chatbot bản mới",
    "ops.phase_u13": "ghi lại bản đã cài",
    "ops.update_confirm": "Cập nhật chatbot từ bản {old} lên bản {new}. Chatbot sẽ tạm tắt vài phút.\n"
    "Tiếp tục? [c = có / k = không]",
    "ops.update_declined": "Anh chọn không cập nhật. Máy vẫn chạy bản cũ.",
    "ops.update_not_installed": "Máy này chưa có bản cài hoàn chỉnh, nên chương trình chưa cập nhật.\n"
    "Anh chạy {tb} doctor để xem còn thiếu gì.",
    "ops.update_bad_version": "File cập nhật ghi số phiên bản sai dạng, nên chương trình không cập nhật. "
    "Anh báo người gửi file.",
    "ops.update_older": "File này là bản {new}, cũ hơn bản {current} đang chạy, nên chương trình không cập nhật.\n"
    "Muốn trở về bản trước, anh chạy: {tb} rollback",
    "ops.update_dry_run": "Kế hoạch cập nhật từ bản {old} lên bản {new} (chạy thử, máy không thay đổi gì):",
    "ops.update_dry_phase": "  {phase}. [sẽ làm] {title}",
    "ops.update_dry_resume": "Lần cập nhật trước dừng giữa chừng; lệnh này sẽ chạy từ bước {phase} ({title}).",
    "ops.update_dry_rollback": "Lần cập nhật trước đang trả máy về bản {old}; lệnh này sẽ trả máy về bản đó cho xong.",
    "ops.update_resuming": "Lần cập nhật lên bản {new} dừng giữa chừng.\n"
    "Chương trình chạy từ bước {phase} ({title}).",
    "ops.update_runtime_plan": "Bản mới cần các phần mềm dưới đây. Chương trình cài chúng cho riêng chatbot,\n"
    "không cần mật khẩu máy và không sửa cài đặt của Terminal:",
    "ops.runtime_line_python": "  - Python {version}: tải từ {source}, {mb} MB, đặt vào {folder}",
    "ops.runtime_line_node": "  - Node.js {version}: tải từ {source}, {mb} MB, đặt vào {folder}",
    "ops.runtime_line_pnpm": "  - pnpm {version}: tải từ {source}, {mb} MB, đặt vào {folder}",
    "ops.runtime_line_claude_code": "  - Claude Code {version}: chương trình cài của Anthropic ({source}), "
    "khoảng {mb} MB, vào {folder}",
    "ops.update_runtime_ask": "Anh gõ c rồi Enter để cài, hoặc gõ k rồi Enter để dừng.",
    "ops.update_runtime_declined": "Anh chọn không cài phần mềm mới, nên chương trình dừng ở bước {title}.\n"
    "Chatbot vẫn chạy bản {old}. Chi tiết ở {log}.",
    "ops.update_failed_before_stop": "Chưa cập nhật được ở bước {title}. Chatbot vẫn chạy bản {old}.\n"
    "Chi tiết ở {log}.",
    "ops.update_failed_restarted": "Chưa cập nhật được ở bước {title}, nên chương trình đã bật lại bản {old}.\n"
    "Dữ liệu không mất. Chi tiết ở {log}.",
    "ops.update_rooms_warn": "Chưa cài được OpenMausBot cho bản mới.\n"
    "Phòng chat hai bot sẽ tắt; chatbot vẫn trả lời bình thường.",
    "ops.update_menu_missing": "Máy chưa có bộ ảnh menu {menu_id} của bản mới, nên chatbot chưa gửi được ảnh menu.\n"
    "Anh chép file thomhouse-menu-{menu_id}.tar vào máy, rồi chạy:\n"
    "{tb} install --only menu_slides --menu <file>",
    "ops.update_menu_warn": "Chưa chép được bộ ảnh menu {menu_id}; chatbot vẫn chạy nhưng chưa gửi được ảnh menu.",
    "ops.update_switch_failed": "Chưa chuyển được sang bản mới, và chatbot đang tắt.\n"
    "Anh chạy lại: {tb} update {file}\n"
    "Hoặc trở về bản cũ: {tb} rollback",
    "ops.update_health_failed": "Bản {version} đã bật nhưng chưa qua bước kiểm tra cuối.\n"
    "Muốn trở về bản trước, anh chạy: {tb} rollback",
    "ops.update_done": "Đã cập nhật chatbot lên bản {version}. Chatbot đang chạy.",
    "ops.update_rollback_no_backup": "Máy không còn bản sao lưu của lần cập nhật này, "
    "nên chương trình chưa trả máy về bản cũ.\n"
    "Chatbot đang tắt. Anh báo người phụ trách trước khi bật lại.",
    "ops.update_d1_copy_failed": "Chương trình chưa chép lại được cơ sở dữ liệu từ bản sao lưu, nên chưa bật chatbot.\n"
    "Bản sao lưu: {backup}\n"
    "Dữ liệu lúc lỗi: {failed}\n"
    "Khi ổ đĩa đủ chỗ trống, anh chạy lại: {tb} update {file}",
    "ops.update_switch_back_failed": "Chưa trả được máy về bản cũ, và chatbot đang tắt.\n"
    "Anh chạy lại: {tb} rollback\n"
    "Hoặc: {tb} update {file}",
    "ops.update_rolled_back": "Bản mới gặp lỗi ở bước {title},\n"
    "nên chương trình đã trả máy về bản {old}. Dữ liệu không mất.\n"
    "Chi tiết ở {log}.",
    # ------------------------------------------------------------ rollback (16.8.1)
    "ops.rollback_done": "Đã trả chatbot về bản {version}.",
    "ops.rollback_none": "Máy chưa có bản trước để trở về, nên chương trình không làm gì.",
    "ops.rollback_missing": "Thư mục của bản {version} không còn trên máy, nên chương trình chưa trở về bản đó.",
    "ops.rollback_no_backup": "Muốn trở về bản {version} thì phải khôi phục bản sao lưu trước lần cập nhật,\n"
    "nhưng máy không còn bản sao lưu đó hoặc bản đó bị hỏng. Chương trình không làm gì.",
    "ops.rollback_dry_run": "Chạy thử, máy không thay đổi gì. Lệnh này sẽ trả chatbot từ bản {current} về bản {old}.",
    "ops.rollback_dry_restore": "Lệnh này cũng sẽ khôi phục bản sao lưu {id},\n"
    "vì bản cũ không đọc được cơ sở dữ liệu hiện tại.",
    "ops.rollback_confirm": "Bản {version} không đọc được cơ sở dữ liệu hiện tại, nên chương trình cần khôi phục\n"
    "bản sao lưu lúc {time} ({reason}).\n"
    "Mọi tin nhắn và thay đổi sau thời điểm đó sẽ không còn trong dữ liệu đang dùng;\n"
    "dữ liệu hiện tại được giữ trong {folder}.\n"
    "Gõ khoi phuc rồi Enter để khôi phục, hoặc chỉ Enter để thôi.",
    # ------------------------------------------------------------ move (16.8.5)
    "ops.move_out_no_dir": "Máy không có thư mục {folder}. Anh cắm ổ USB hoặc chọn một thư mục có sẵn rồi chạy lại.",
    "ops.move_out_confirm": "Chuyển dữ liệu chatbot sang máy khác?\n"
    "Sau bước này chatbot không chạy trên máy này nữa. [c = có / k = không]",
    "ops.move_out_declined": "Anh chọn không chuyển. Máy này vẫn giữ nguyên.",
    "ops.move_out_listener_warn": "Chưa dừng được phần nhận tin Zalo trên máy này.\n"
    "Sau khi chuyển xong, anh chạy {tb} doctor để kiểm tra.",
    "ops.move_out_not_moved": "Dữ liệu chưa chuyển đi, và máy này chưa bị đánh dấu đã chuyển.\n"
    "Chatbot đang tắt; muốn bật lại ở máy này, anh chạy: {start}",
    "ops.move_out_image_failed": "Chưa tạo được file chuyển máy, nên máy này chưa bị đánh dấu đã chuyển.\n"
    "Chatbot đang tắt; muốn bật lại ở máy này, anh chạy: {start}",
    "ops.move_out_done": "Đã tạo file chuyển máy: {file}\nAnh mang file này và mật khẩu vừa đặt sang máy mới.",
    "ops.move_out_last": "Đừng bật lại chatbot trên máy này. Mỗi tài khoản Zalo chỉ chạy trên một máy.",
    "ops.move_in_no_file": "Máy không có file chuyển máy {file}. Anh kiểm tra đường dẫn rồi chạy lại.",
    "ops.move_in_attach_failed": "Chưa mở được file chuyển máy, có thể vì mật khẩu chưa đúng.\n"
    "Dữ liệu trên máy này giữ nguyên.",
    "ops.move_in_damaged": "File chuyển máy bị hỏng hoặc thiếu tệp, nên chương trình không chép gì vào máy này.",
    "ops.move_in_newer": "File chuyển máy đến từ bản chương trình mới hơn bản trên máy này,\n"
    "nên chương trình không chép gì. Anh cập nhật chương trình trên máy này trước.",
    "ops.move_in_failed": "Chưa chép xong dữ liệu từ file chuyển máy,\n"
    "nên chương trình đã đưa dữ liệu của máy này trở lại như trước. "
    "Chi tiết ở {log}.",
    "ops.move_in_placed": "Đã chép dữ liệu từ máy cũ. Dữ liệu trước đó của máy này nằm ở {folder}.",
    "ops.move_in_done": "Anh chạy {tb} continue để đăng nhập Claude và Zalo cho máy này.",
    "ops.move_back_not_needed": "Máy này chưa bị đánh dấu đã chuyển dữ liệu đi, nên không cần lệnh này.",
    "ops.move_back_confirm": "Bật lại chatbot trên máy này? Chỉ làm khi máy mới đã tắt chatbot. [c = có / k = không]",
    "ops.move_back_declined": "Anh chọn không bật lại. Máy này vẫn giữ dấu đã chuyển dữ liệu đi.",
    "ops.move_back_done": "Đã bỏ dấu chuyển máy. Anh bật chatbot bằng: {start}",
    # ------------------------------------------------------------ uninstall (16.8.6)
    "ops.uninstall_odd_app_home": "Thư mục {folder} không giống thư mục chương trình do trình cài tạo,\n"
    "nên chương trình không xóa gì.",
    "ops.uninstall_offer_backup": "Lệnh này gỡ chương trình và giữ dữ liệu. Sao lưu dữ liệu trước khi gỡ? "
    "[c = có / k = không]",
    "ops.uninstall_nothing_done": "Chương trình chưa gỡ gì; chatbot giữ nguyên như trước lệnh này.",
    "ops.uninstall_data_confirm": "Toàn bộ hội thoại của khách trên máy này sẽ chuyển vào Thùng rác.\n"
    "Gõ xoa du lieu rồi Enter để tiếp tục, hoặc chỉ Enter để thôi.",
    "ops.uninstall_declined": "Anh chưa gõ xoa du lieu, nên chương trình không gỡ gì.",
    "ops.uninstall_no_target": "macOS không cho chuyển thư mục dữ liệu vào Thùng rác hay vào thư mục nhà,\n"
    "nên chương trình dừng ở đây. Dữ liệu vẫn nằm ở {folder}; chương trình chưa gỡ gì.",
    "ops.uninstall_move_failed": "Chưa chuyển được thư mục dữ liệu {bot} sang {target}.\n"
    "Dữ liệu vẫn nằm ở {bot}; chatbot đang tắt.",
    "ops.uninstall_in_trash": "Thư mục dữ liệu đã nằm trong Thùng rác: {folder}",
    "ops.uninstall_drag_to_trash": "Anh kéo thư mục này vào Thùng rác: {folder}",
    "ops.uninstall_partial": "Chưa xóa hết thư mục chương trình {folder}. Anh xóa phần còn lại bằng Finder.",
    "ops.uninstall_done": "Đã gỡ chương trình chatbot ({folder}).",
    "ops.uninstall_kept": "Những thứ vẫn còn trên máy:\n"
    "  - dữ liệu chatbot: {bot}\n"
    "  - tài khoản Zalo đã đăng nhập: {zalo}\n"
    "  - Claude Code trong ~/.local\n"
    "  - mã nhân viên đã dán trong trình duyệt",
    "ops.uninstall_kept_without_data": "Những thứ vẫn còn trên máy:\n"
    "  - tài khoản Zalo đã đăng nhập: {zalo}\n"
    "  - Claude Code trong ~/.local\n"
    "  - mã nhân viên đã dán trong trình duyệt\n"
    "Anh xóa máy này khỏi danh sách thiết bị đã đăng nhập trong app Zalo.",
    "ops.uninstall_dry_header": "Chạy thử, máy không thay đổi gì. Lệnh gỡ sẽ làm các việc sau:",
    "ops.uninstall_dry_item": "  - xóa {path}",
    "ops.uninstall_dry_data": "  - chuyển thư mục dữ liệu {folder} vào Thùng rác",
    "ops.uninstall_dry_keep": "  - giữ nguyên thư mục dữ liệu {folder}",
    # ------------------------------------------------------------ autostart and shortcuts (16.8.8)
    "ops.autostart_failed": "Chưa bật được chế độ tự bật chatbot khi đăng nhập máy; chi tiết ở {log}.",
    "ops.autostart_kept_edited": "File {file} đã bị sửa tay, nên chương trình không xóa file đó.",
    "ops.shortcut_kept_other": "Trên Desktop đã có file {file} không do chương trình tạo, nên chương trình không ghi đè.",
    "ops.autostart_on": "Chatbot sẽ tự bật mỗi khi anh đăng nhập máy. Máy phải thức thì chatbot mới chạy.\n"
    "Muốn tắt chế độ này: {tb} autostart off",
    "ops.autostart_off": "Đã tắt chế độ tự bật chatbot khi đăng nhập máy.",
    "ops.shortcuts_failed": "Chưa tạo được nút bấm trên Desktop ({folder}). Anh kiểm tra quyền ghi rồi chạy lại.",
    "ops.shortcuts_on": "Đã tạo ba nút bấm trên Desktop: Bat-chatbot, Kiem-tra-chatbot và Tat-chatbot.",
    "ops.shortcuts_off": "Đã xóa các nút bấm của chatbot trên Desktop.",
}

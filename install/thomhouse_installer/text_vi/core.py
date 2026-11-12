"""Texts of the core package (16.4.7 failures and the dispatcher's own lines).

Placeholders: {name} what was downloaded or which pin, {host} the server, {cmd} the command to run again (filled by
the dispatcher when the raiser gives none), {tb} the launcher (`~/ThomHouse/bin/thomhouse`, or
`python3 -I install/thomhouse.py` in checkout mode), {file} the release file of an unfinished update.
"""

TEXTS: dict[str, str] = {
    "core.failed": "Lệnh chưa làm xong; chi tiết nằm trong thư mục logs của chương trình.",
    "core.locked": "Một lệnh cài hoặc cập nhật khác đang chạy trên máy này. Anh chờ lệnh đó xong rồi chạy lại.",
    "core.pin_missing": "File cài thiếu thông tin phiên bản của {name}, nên chương trình dừng ở đây. "
    "Anh báo người gửi file.",
    "core.download_not_https": "Địa chỉ tải {name} không dùng https nên chương trình không tải. "
    "Anh báo người gửi file.",
    "core.download_network": "Chưa tải được {name} từ {host} vì máy không kết nối được mạng.\n"
    "Anh kiểm tra mạng rồi chạy lại: {cmd}",
    "core.download_disk": "Ổ đĩa của máy không đủ chỗ trống để tải {name}.\n"
    "Anh xóa bớt tệp rồi chạy lại: {cmd}",
    "core.download_http": "Máy chủ {host} chưa trả file {name}. Anh chờ một lúc rồi chạy lại: {cmd}",
    "core.download_size": "File {name} tải về không đúng mã kiểm tra nên chương trình đã xóa file đó. "
    "Anh chạy lại: {cmd}",
    "core.download_checksum": "File {name} tải về không đúng mã kiểm tra nên chương trình đã xóa file đó. "
    "Anh chạy lại: {cmd}",
    "core.update_open": "Lần cập nhật trước chưa xong, nên chương trình chưa làm lệnh này.\n"
    "Anh chạy lại: ~/ThomHouse/bin/thomhouse update {file}\n"
    "Hoặc quay về bản cũ: ~/ThomHouse/bin/thomhouse rollback",
    "core.moved_out": "Dữ liệu chatbot của máy này đã chuyển sang máy khác, nên chương trình không bật chatbot ở đây.\n"
    "Muốn chạy lại ở máy này: {tb} move-back",
    "core.interrupted": "Anh đã dừng lệnh giữa chừng. Khi sẵn sàng, anh chạy lại lệnh đó.",
    "core.internal_error": "Chương trình gặp lỗi lạ ({name}); chi tiết nằm trong logs/install.log.\n"
    "Anh báo người phụ trách.",
    "core.checkout_only": "Trong thư mục dự án, chương trình chỉ chạy doctor, backup, backups, restore, "
    "move-out và move-back.",
    "core.whitespace_path": "Thư mục {folder} có dấu cách, nên chương trình không dùng thư mục đó.\n"
    "Anh chọn thư mục không có dấu cách.",
    "core.not_built": "Phần {part} của chương trình chưa được viết, nên lệnh {command} chưa chạy được.",
    "core.bad_args": "Lệnh gõ chưa đúng. Anh xem cách gõ bằng: {tb} --help",
    "core.answer_yes": "Chương trình tự trả lời c vì lệnh có --yes.",
    "core.answer_noninteractive": "Không có ai gõ phím trong cửa sổ này, nên chương trình tự trả lời {answer}.",
    "core.ask_again": "Anh gõ một trong các chữ {choices} rồi Enter.",
    "core.typed_needs_person": "Câu này cần anh tự gõ trong Terminal, nên chương trình dừng ở đây.",
    "core.starting": "Đang bật chatbot; việc này có thể mất vài phút.",
}

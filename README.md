# Nghiên cứu chatbot Zalo OA cho thom house

Dự án này nghiên cứu và lên kế hoạch cho một chatbot trả lời khách của thom house healing studio trên Zalo OA, dùng model Opus 5.5 của Anthropic. Anh nên đọc báo cáo quyết định trước; các thư mục còn lại là bằng chứng và bản nháp thiết kế mà báo cáo dẫn tới. Mọi tài liệu được lập ngày 2026-11-07. Chưa ai gọi API Anthropic, kết nối OA thật hay chạy code của các repo tham khảo.

## Báo cáo

- [report/bao-cao-chatbot-thomhouse.md](report/bao-cao-chatbot-thomhouse.md): báo cáo để anh quyết định, mở đầu bằng phần anh cần duyệt.
- [report/ket-qua-chay-thu-opus-5-5.md](report/ket-qua-chay-thu-opus-5-5.md): kết quả chạy thử Opus 5.5 trên 132 câu thử bằng subscription, các lỗi cần sửa trong prompt.

## Chạy và vận hành (`docs/`)

Các tài liệu dưới đây được viết sau giai đoạn nghiên cứu, khi code đã chạy được trên máy Mac.

- [docs/chay-local-zalo-ca-nhan.md](docs/chay-local-zalo-ca-nhan.md): chạy chatbot trên máy Mac với tài khoản Zalo cá nhân; đây là cách chạy đang dùng.
- [docs/run-local.md](docs/run-local.md): chạy từng phần bằng tay ở chế độ giả lập Zalo, các lệnh của phòng hai bot, đồng bộ nhãn Zalo, nhập lịch sử buổi làm và các lệnh test.
- [docs/rooms.md](docs/rooms.md): hai bot trong phòng chat, công tắc Tự động trả lời, nhãn Khách hàng, Quản lý, Nhân viên, trạng thái khách cùng các lần đến, số tiền, số điện thoại và gói suy ra từ tin nhắn cũ mà lễ tân xác nhận hoặc bỏ; viết cho anh và lễ tân (2026-11-12).
- [docs/contracts.md](docs/contracts.md): hợp đồng kỹ thuật giữa server, runner, bridge và console (tiếng Anh); mục 15 là phần suy ra lần đến và gói từ tin nhắn cũ.

## Nghiên cứu (`research/`)

- [research/00-prior-report-claims.md](research/00-prior-report-claims.md): 37 nhận định của báo cáo trước, đánh mã để các nhánh kiểm (tiếng Anh).
- [research/01-knowledge-audit.md](research/01-knowledge-audit.md): rà tài liệu doanh nghiệp: bảng giá, câu hứa chữa bệnh, mâu thuẫn và thông tin còn thiếu.
- [research/03-zalo-oa-platform.md](research/03-zalo-oa-platform.md): Zalo OA cho phép gửi loại tin nào, khi nào và giá bao nhiêu; các bước đăng ký OA.
- [research/04-zalo-repos-audit.md](research/04-zalo-repos-audit.md): rà ba repo Zalo tham khảo: phần nào dùng được, giấy phép, lỗi so với tài liệu Zalo.
- [research/05-anthropic-plan-model-cost.md](research/05-anthropic-plan-model-cost.md): gói Ultra, điều khoản dùng API, giá Opus 5.5, Usage Policy và mô hình chi phí.
- [research/06-architecture.md](research/06-architecture.md): kiến trúc đề xuất: phần chạy nền trên Cloudflare, app macOS cho nhân viên, kill switch, các giai đoạn làm.
- [research/07-vn-legal-compliance.md](research/07-vn-legal-compliance.md): ràng buộc pháp luật Việt Nam về dữ liệu cá nhân, trí tuệ nhân tạo, quảng cáo và tin nhắn.
- [research/08-cross-check.md](research/08-cross-check.md): đối chiếu chéo các nhánh, kiểm lại dữ kiện chính, gom chi phí và thời gian, kết luận cho mọi nhận định cũ.
- [research/snapshots/zalo-2026-11-07/](research/snapshots/zalo-2026-11-07/): bản chép các trang tài liệu và chính sách Zalo đã đọc, để dẫn số dòng.

## Thiết kế (`design/`)

- [design/conversation-design.md](design/conversation-design.md): 22 ý định của khách, các trạng thái hội thoại, danh sách trường hợp chuyển nhân viên, phương án xưng hô.
- [design/system-prompt-draft.md](design/system-prompt-draft.md): bản nháp system prompt chia khối để dùng prompt caching, và các bước server kiểm bản nháp trước khi gửi.
- [design/tools-schema.json](design/tools-schema.json): định nghĩa 9 công cụ model được gọi: 7 công cụ ban đầu, `attach_menu_images` thêm ngày 2026-11-08 và `get_customer_profile` thêm ngày 2026-11-12.
- [design/eval-set.jsonl](design/eval-set.jsonl): 135 câu thử để đo chất lượng trả lời, chưa chạy với model.
- [design/followup-templates.md](design/followup-templates.md): 5 mẫu tin cảm ơn, hỏi thăm, khuyến mãi và xác nhận yêu cầu đặt lịch, mỗi mẫu có bản chat và bản ZBS.
- [design/subscription-runner.md](design/subscription-runner.md): bot gọi model bằng subscription Claude qua `claude -p` trên máy Mac, theo quyết định ngày 2026-11-07; cách ly phiên, xử lý lỗi, cờ `ai_engine`.

## Dữ liệu (`data/`)

- [data/services.json](data/services.json): 23 dịch vụ và 33 mức giá, mỗi mức có dòng nguồn trên menu; chưa được anh duyệt.
- [data/business-facts.json](data/business-facts.json): 36 mục thông tin doanh nghiệp, ghi rõ mục nào có, mục nào mâu thuẫn, mục nào thiếu; chưa được anh duyệt.

## Script (`scripts/`)

Các script chạy bằng `python3 -I`, không cần thư viện ngoài.

- [scripts/runner/claude_pool.py](scripts/runner/claude_pool.py): nhóm tài khoản subscription cho `claude -p`; tự chuyển tài khoản khi hết hạn mức hay hết đăng nhập, chọn tay bằng `use`, xem trạng thái bằng `status`. Khi một lần gọi lỗi, script chỉ ghi loại lỗi, không ghi nội dung lỗi.
- [scripts/analyze_contacts.py](scripts/analyze_contacts.py): đọc tin nhắn Zalo cũ trên máy Mac và lập hồ sơ liên hệ (khách hay người quen, cách gọi, dịch vụ từng hỏi); chỉ dùng quy tắc, không gọi model.
- [scripts/analyze_visits.py](scripts/analyze_visits.py): đọc cùng kho tin nhắn đó và đoán lần đến, số tiền, kỹ thuật viên, số điện thoại và gói của từng khách; lượt nhờ Claude đọc lại tin nhắn mặc định tắt.
- [scripts/import_visits.py](scripts/import_visits.py): nhập lịch sử buổi làm từ file CSV vào server local, luôn chạy thử trước.
- [scripts/eval/run_eval_cli.py](scripts/eval/run_eval_cli.py): chạy bộ câu thử qua `claude -p` trên subscription; thêm `--pool` để đi qua nhóm tài khoản.
- [scripts/build_services.py](scripts/build_services.py): dựng `data/services.json` và kiểm từng mức giá với dòng menu gốc.
- [scripts/check_price_pairs.py](scripts/check_price_pairs.py): tìm dòng tài liệu ghi giá hoặc thời lượng khác menu cho một dịch vụ.
- [scripts/scan_prices.py](scripts/scan_prices.py): liệt kê mọi số tiền trong tài liệu.
- [scripts/scan_risky.py](scripts/scan_risky.py): đánh dấu câu có từ khóa về bệnh, chữa bệnh, con số hiệu quả và đối tượng cần thận trọng.
- [scripts/compare_bundle.py](scripts/compare_bundle.py): so file gom `thomhouse-knowledge-bundle.txt` với các file `.md` riêng lẻ.
- [scripts/cost_model.py](scripts/cost_model.py): mô hình chi phí gọi model theo số hội thoại, cách cache và cách chia model.

## Nguồn (`sources/`, chỉ đọc)

- [sources/drive/](sources/drive/): bản sao thư mục Google Drive của studio, gồm menu chép từ ảnh, tài liệu thương hiệu và tài liệu cho chatbot.
- [sources/drive-index.md](sources/drive-index.md): mã file Drive và ngày sửa của từng file trong bản sao.
- [sources/repos/](sources/repos/): bản clone của ba repo Zalo tham khảo (`zalo-mcp`, `arden-zalo-agent-cli`, `zalo-agent-cli`), chỉ đọc, chưa chạy.

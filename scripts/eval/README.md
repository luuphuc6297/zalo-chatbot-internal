# Chạy thử Opus 5.5 trên bộ câu thử

Script `run_eval.py` gửi 132 câu thử trong `design/eval-set.jsonl` tới model `claude-opus-5-5`. Ba câu còn lại (`fc-04`, `fc-05`, `fc-06`) kiểm phần server, không gọi model, nên script bỏ qua.

## Script làm gì với mỗi câu thử?

Script dựng system prompt từ khối A trong `design/system-prompt-draft.md`, sinh khối B (danh mục 23 dịch vụ, không có giá) từ `data/services.json` và khối C (thông tin doanh nghiệp) từ `data/business-facts.json`. Bảy công cụ trong `design/tools-schema.json` được trả lời bằng dữ liệu giả lập: giá lấy từ `data/services.json`, quy tắc mốc 20h30 theo đề xuất trong bản thiết kế, danh sách khuyến mãi rỗng.

Sau mỗi câu, script chấm theo hai cách:

1. Kiểm bằng code: có đủ cụm bắt buộc không, có cụm cấm không, có gọi đúng công cụ không, có chuyển nhân viên đúng lúc không, mọi số tiền trong câu trả lời có trùng giá công cụ trả về không, có markdown không, có hứa đã đặt lịch không, có dài quá 1.800 ký tự không.
2. Nhờ chính Opus 5.5 ở mức suy nghĩ thấp đọc lại hội thoại và chấm đạt, lỗi nhỏ hoặc trượt, kèm lý do bằng tiếng Việt.

Kết quả nằm trong `results/eval-<thời điểm>-effort-<mức>/`: file `results.jsonl` lưu từng câu, file `summary.json` lưu số câu đạt, tiền đã tiêu, số token và độ trễ trung vị.

## Chạy bằng subscription như project Kai

Script `run_eval_cli.py` chạy cùng bộ câu thử qua lệnh `claude -p` của Claude Code, nên dùng subscription của anh thay cho API key. Cách gọi giống Kai (`apps/truc/truc.py`): thay system prompt của Claude Code bằng prompt của bot, tắt công cụ có sẵn, chỉ nạp MCP server giả lập 7 công cụ (`mock_mcp_server.py`), đọc kết quả dạng JSON và nối lượt sau bằng `--resume`. Script bỏ qua cài đặt người dùng (`--setting-sources project`), để hook và quy tắc viết của máy không lọt vào phiên của bot.

Cách này chỉ dùng để thử nội bộ. Khi bot trả lời khách thật, điều khoản Anthropic yêu cầu gọi model bằng API key của Console.

Kết quả khác bản chạy API ở ba điểm. Ngữ cảnh từng lượt nằm trong tin của người dùng, không phải tin `system` riêng. Tên công cụ có tiền tố `mcp__thom__`. Số tiền `api-equiv` là tiền Claude Code tự tính theo giá API, không phải tiền anh trả; subscription chỉ trừ vào hạn mức dùng.

Trước khi chạy, CLI phải đang đăng nhập. Kiểm bằng `claude auth status`; nếu hết hạn thì chạy `claude auth login`. Lệnh chạy:

```bash
python3 scripts/eval/run_eval_cli.py --probe
```

```bash
python3 scripts/eval/run_eval_cli.py --limit 5
```

```bash
python3 scripts/eval/run_eval_cli.py
```

## Anh cần chuẩn bị gì để chạy bằng API key?

Script cần API key của tổ chức Claude Console mà anh liên kết với gói Ultra. Điều khoản của Anthropic không cho dùng đăng nhập Ultra để gọi model cho sản phẩm. Anh tạo key trong Console, rồi chọn một trong hai cách:

1. Tự tạo file `.secrets/anthropic_api_key` trong thư mục dự án, chỉ chứa key trên một dòng. Thư mục `.secrets/` chỉ chủ máy đọc được, và `.gitignore` đã loại thư mục này.
2. Đặt biến môi trường `ANTHROPIC_API_KEY` trong terminal trước khi chạy.

Anh không cần gửi key cho tôi qua chat. Script không in key ra màn hình hay ghi key vào file kết quả.

## Tốn bao nhiêu tiền?

Theo ước tính trước khi chạy, mỗi câu thử tốn khoảng 0,07 đến 0,12 USD, gồm cả lượt chấm, nên 132 câu tốn khoảng 9 đến 16 USD. Script có trần chi phí: khi tổng tiền đã tiêu chạm mức `--max-usd` (mặc định 25 USD), script ngừng gọi model và ghi lại các câu chưa chạy. Tiền tính theo bảng giá Opus 5.5 (4 USD cho một triệu token đầu vào, 20 USD cho một triệu token đầu ra, ghi cache 1 giờ 8 USD, đọc cache 0,20 USD) và chưa gồm VAT nếu Anthropic thu.

## Lệnh chạy

Chạy thử 5 câu trước để kiểm cấu hình và đo chi phí thật:

```bash
.venv/bin/python scripts/eval/run_eval.py --limit 5 --max-usd 3
```

Sau đó chạy đủ bộ câu thử:

```bash
.venv/bin/python scripts/eval/run_eval.py --max-usd 25
```

Các tùy chọn khác: `--effort medium` để so mức suy nghĩ, `--ids price-03,rf-14` để chạy vài câu chọn sẵn, `--no-judge` để bỏ bước chấm bằng model, `--dry-run` để xem prompt và công cụ giả lập mà không gọi API.

## Kết quả này chưa nói được gì?

Công cụ giả lập trả dữ liệu nháp chưa được anh duyệt, và khối thông tin doanh nghiệp gần như trống. Vì vậy bot sẽ trả lời "chưa có thông tin" cho nhiều câu về chính sách; đây là hành vi đúng với dữ liệu hiện tại. Bước chấm bằng model có thể chấm lệch, nên các câu trượt cần người đọc lại trước khi kết luận.

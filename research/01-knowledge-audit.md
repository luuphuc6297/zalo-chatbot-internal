# Rà soát tài liệu doanh nghiệp thom house cho chatbot

Ngày rà: 2026-11-07. Phạm vi: toàn bộ thư mục `sources/drive/` (bản sao thư mục Google Drive của chủ doanh nghiệp). Người đọc chính: anh, trước khi quyết định chatbot được phép nói gì với khách.

## Phần anh cần duyệt

Bảng giá trong tài liệu nhất quán. Tôi đếm được 23 dịch vụ trong 5 nhóm và 33 mức giá, và mỗi mức giá đều khớp với văn bản chép từ ảnh menu. Không file nào ghi một dịch vụ với giá khác. Vì vậy chatbot có thể trả lời giá từ file `data/services.json` mà không phải chọn giữa hai con số.

Phần chưa dùng được ngay gồm ba vấn đề. Thứ nhất, nhiều câu trên chính menu hứa tác dụng chữa bệnh, ví dụ "hỗ trợ chữa sa tử cung", "giảm u hạch, tuyến giáp", "ngừa đột quỵ" và "hiệu quả gấp 20 lần". Tài liệu hướng dẫn chatbot lại cấm đúng những lời hứa này. Thứ hai, tài liệu tự mâu thuẫn ở những điểm khách hỏi nhiều: giờ mở cửa, địa chỉ phường, cách chatbot xưng hô và tên trợ lý. Thứ ba, tài liệu không có chính sách hủy lịch, đến trễ, thanh toán, đặt cọc, hoàn tiền, thẻ quà tặng, thành viên, khuyến mại, số hotline và Zalo OA.

Anh cần quyết bốn việc trước khi bật trả lời tự động:

1. Cách xưng hô. Tài liệu 13 bắt chatbot xưng *em* và gọi khách *anh/chị*. Tài liệu 06 và tài liệu 12 lại quy định hoặc dùng cách xưng *mình* và gọi khách *bạn*; cụm *Bạn ơi* xuất hiện 96 lần trong 12 file tài liệu tổng hợp. Tôi đề xuất *em – anh/chị* cho chat 1:1 vì tài liệu 13 là tài liệu mới nhất về lỗi chat thật. Điểm yếu của lựa chọn này: phải viết lại gần như toàn bộ câu mẫu trong tài liệu 12.
2. Danh sách câu y tế bị cấm và câu thay thế (mục E bên dưới). Tôi đề xuất chatbot không đọc lại các câu mô tả lợi ích trên menu phụ nữ và menu khỏe, chỉ đọc tên, thời lượng, giá và các bước. Điểm yếu: tên dịch vụ như "Diện chẩn ngừa đột quỵ" và "Tiêu u – Thông kinh ngực" tự mang lời hứa, nên chỉ đọc tên thôi cũng chưa đủ an toàn. Việc đổi tên hay giữ tên là quyết định của anh và chủ doanh nghiệp.
3. Giờ mở cửa và địa chỉ hiện hành.
4. Các chính sách còn thiếu ở mục F. Chatbot không được tự điền các chính sách này.

Các file tôi tạo ra (chưa được chủ doanh nghiệp duyệt):

- `data/services.json`: 23 dịch vụ, 33 mức giá, mỗi mức giá có đường dẫn và số dòng nguồn.
- `data/business-facts.json`: 36 mục thông tin doanh nghiệp; mục nào thiếu ghi `"status": "missing"`.
- `scripts/compare_bundle.py`, `scripts/scan_prices.py`, `scripts/check_price_pairs.py`, `scripts/scan_risky.py`, `scripts/build_services.py`: các script đã dùng để đối chiếu. Mọi script chạy bằng `python3 -I`.

## Thuật ngữ dùng trong báo cáo

| Thuật ngữ | Nghĩa trong báo cáo này |
|---|---|
| file gom | `thomhouse-knowledge-bundle.txt`, một file văn bản gom 30 file `.md` thành một để tải lên chatbot một lần |
| văn bản chép menu | 5 file trong `raw-content/`, là chữ chép lại từ ảnh menu ngày 2026-05-16. Đây là nguồn gốc gần nhất với menu thật mà thư mục có |
| tài liệu tổng hợp | các file trong `documentation/` và `knowledge-base/`, do người soạn (trợ lý AI của chủ doanh nghiệp, theo cách xưng "em" với "chị Luu") viết lại từ văn bản chép menu |
| mức giá | một tổ hợp thời lượng, giá và khung giờ của một dịch vụ; ví dụ Massage chân 30 phút 199.000đ là một mức giá |
| KTV | kỹ thuật viên, cách tài liệu gọi nhân viên làm dịch vụ |

## A. Thư mục có những file nào, file nào là nguồn gốc?

Thư mục có 32 file. Ngày duy nhất ghi trong file là 2026-05-16 (ngày tải menu lên, ghi ở `_intake-log.md` dòng 9, 31, 61, 106, 144). Ngày sửa đổi trên Google Drive không kiểm được: thời gian sửa đổi của các file local đều là lúc sao chép (2026-11-07 00:18), và lệnh tìm file qua kết nối Google Drive (`search_files`, truy vấn theo tên file) trả về rỗng.

| File | Dòng | Vai trò | Gốc hay suy ra |
|---|---|---|---|
| `raw-content/batch-01-relaxation-menu.md` | 155 | chép 9 slide menu thư giãn | gốc, có chèn ghi chú của người soạn |
| `raw-content/batch-02-health-menu.md` | 337 | chép 19 slide menu khỏe | gốc, có chèn ghi chú |
| `raw-content/batch-03-women-health-menu.md` | 215 | chép 7 slide menu phụ nữ và bài "Đôi lời của Thơm" | gốc, có chèn ghi chú |
| `raw-content/batch-04-skincare-menu.md` | 186 | chép 5 slide menu da | gốc, có chèn ghi chú (gồm phần đoán nghĩa chữ SHR) |
| `raw-content/batch-05-hair-care-menu.md` | 201 | chép 9 slide menu tóc | gốc, có chèn ghi chú |
| `knowledge-base/02-services/*.md` (6 file) | 152–277 | mỗi file một menu, kèm phân tích | suy ra |
| `knowledge-base/03-pricing-structure.md` | 388 | quy luật giá, giá theo phút | suy ra; có câu xếp hạng sai |
| `knowledge-base/00-brand-essence.md`, `01-tone-voice.md` | 271, 515 | bản sắc và giọng văn | suy ra |
| `documentation/01`–`08` | 152–297 | câu chuyện thương hiệu, giá trị, chân dung khách, hành trình khách | suy ra |
| `documentation/09`, `10`, `11` | 471, 518, 1610 | kiến thức Đông y, công nghệ, câu hỏi thường gặp | phần lớn là kiến thức người soạn tự thêm; tài liệu 11 có nhãn phân biệt nguồn menu và kiến thức chung (dòng 18–26) |
| `documentation/12-chatbot-response-formatting.md` | 823 | quy tắc định dạng và 20 câu trả lời mẫu | suy ra; viết theo cách xưng *mình – bạn* |
| `documentation/13-critical-chatbot-fixes.md` | 496 | danh sách lỗi chat thật và cách sửa | suy ra; viết theo cách xưng *em – anh/chị* |
| `README.md`, `documentation/README.md`, `_intake-log.md` | 118, 68, 197 | mục lục, nhật ký tải menu, câu hỏi chờ xác nhận | suy ra |
| `AGENTS.md` | 1 | chỉ có một dòng tiêu đề, không có nội dung | không dùng |
| `thomhouse-knowledge-bundle.txt` | 10.845 | file gom | suy ra từ 30 file trên |

Văn bản chép menu là nguồn duy nhất tôi dùng làm gốc cho giá và quy trình. Ngay cả các file này cũng trộn chữ trên ảnh với ghi chú của người soạn. Ví dụ, `batch-04` dòng 166 đoán SHR là "Smart Hair Removal / Selective High-frequency Radiation", không có trên ảnh. Ảnh menu gốc không có trong thư mục (`_intake-log.md` dòng 23 ghi ảnh chỉ tồn tại trong cuộc chat), nên tôi không đối chiếu được với ảnh.

## B. File gom có giống các file riêng lẻ không?

Có, về nội dung. Tôi chạy `python3 -I scripts/compare_bundle.py sources/drive --detail`. Script cắt file gom thành 30 phần theo tiêu đề `### NN.` và `### Nguồn:`, bỏ ký hiệu markdown, bỏ khác biệt chữ hoa chữ thường và khoảng trắng, rồi so từng dòng với file `.md` tương ứng. Cả 30 phần không có dòng nội dung nào khác nhau.

File gom có thêm ba thứ mà các file riêng không có:

1. Phần mở đầu (dòng 1–163) gồm lời dặn đọc mục 02 trước, phần miễn trừ và một khối địa chỉ, liên hệ. Khối này ghi "Giờ hoạt động: 9h–24h" ở dòng 57, trong khi tài liệu 13 ghi giờ đang chờ xác nhận. Dòng 24 có ký tự lạ "p∑hải".
2. Phần kết (dòng 10.831–10.845) ghi "Tổng cộng: 30 tài liệu" và ngày tạo 2026-05-16.
3. Thứ tự khác: file gom đặt tài liệu 13 và 12 lên trước tài liệu 01.

Hai điểm cần biết khi đưa file gom vào chatbot. File gom ghi nguồn là `.txt` (ví dụ dòng 386 ghi `13-critical-chatbot-fixes.txt`), nghĩa là được tạo từ bản xuất văn bản, không trực tiếp từ các file `.md` hiện có. Phần 12 của file gom có các tiêu đề con `### 10. Âm dương`, `### 11. Bổ thận`, `### 12. Hệ bạch huyết` (dòng 4078, 4088, 4103) trùng mẫu với tiêu đề phần; một chương trình cắt file theo mẫu `### NN.` sẽ cắt sai nếu không kiểm thêm dòng `### Nguồn:`.

Kết luận cho mục B: chatbot nên đọc từ các file `.md` riêng hoặc từ dữ liệu có cấu trúc, không cần file gom. File gom không có nội dung mới, trừ dòng giờ mở cửa 9h–24h chưa được xác nhận.

## C. Bảng giá có bao nhiêu dịch vụ và mức giá?

Có 23 dịch vụ và 33 mức giá. Tôi đếm từ văn bản chép menu, rồi dùng `scripts/build_services.py` kiểm từng mức giá có nằm đúng trên dòng nguồn được ghi trong `services.json`. Kết quả chạy: 33 trên 33 mức giá khớp.

| Nhóm | Số dịch vụ | Số mức giá | Giá thấp nhất | Giá cao nhất | Cách tính giá |
|---|---|---|---|---|---|
| Thư giãn (relaxation) | 4 | 12 | 199.000 | 569.000 | theo thời lượng và khung giờ; riêng Massage chân một giá cho cả khung 9h–24h |
| Khỏe (health) | 6 | 6 | 599.000 | 2.990.000 | một giá, không chia khung giờ |
| Phụ nữ (women) | 5 | 5 | 500.000 | 3.500.000 | một giá |
| Da (skin) | 5 | 5 | 329.000 | 629.000 | một giá |
| Tóc (hair) | 3 | 5 | 139.000 | 349.000 | Detox da đầu và Gội đầu thư giãn chia khung giờ; Chăm sóc nan tóc một giá |

Chi tiết từng mức giá:

| Dịch vụ | Thời lượng | 9h–20h30 | Sau 20h30 | Nguồn |
|---|---|---|---|---|
| Mở Vai – Nâng Mặt | 60 phút | 350.000 | 389.000 | batch-01:54–55 |
| Massage chân | 30 / 45 phút | 199.000 / 250.000 (cả khung 9h–24h) | như cột trước | batch-01:80–81 |
| Massage cổ, vai, gáy | 30 / 60 phút | 199.000 / 399.000 | 239.000 / 449.000 | batch-01:109–112 |
| Massage body thư giãn | 60 / 75 phút | 429.000 / 499.000 | 499.000 / 569.000 | batch-01:142–145 |
| Diện chẩn ngừa đột quỵ | 180 phút | 2.990.000 | không chia khung | batch-02:63 |
| Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch | 60 phút | 599.000 | không chia khung | batch-02:112 |
| Thiếu máu não – tê tay, căng thẳng khó ngủ | 60 phút | 599.000 | không chia khung | batch-02:166 |
| Đau thắt lưng mỏi gối | 60 phút | 599.000 | không chia khung | batch-02:216 |
| Detox mùi cơ thể | 90 phút | 1.190.000 | không chia khung | batch-02:264 |
| Thải hàn giải cảm | 90 phút | 1.200.000 | không chia khung | batch-02:316 |
| Chăm sóc đau bụng kinh, rối loạn kinh nguyệt | 60 phút | 599.000 | không chia khung | batch-03:71 |
| Se khít làm hồng yoni | 45 phút | 2.500.000 | không chia khung | batch-03:98 |
| Yoni Retreat (Signature, tặng Nắn chỉnh sàn chậu) | 100 phút | 3.500.000 | không chia khung | batch-03:114 |
| Nắn chỉnh thu hẹp sàn chậu | 10 phút | 500.000 | không chia khung | batch-03:152 |
| Tiêu u – Thông kinh ngực | 60 phút | 650.000 | không chia khung | batch-03:167 |
| Gói Mụn Chuyên Sâu | 75 phút | 389.000 | không chia khung | batch-04:41 |
| Gói Mụn 5 in 1 (Signature) | 90 phút | 599.000 | không chia khung | batch-04:71 |
| Chăm sóc da kích ứng | 90 phút | 599.000 | không chia khung | batch-04:96 |
| Xóa thâm quầng mắt – Gói cơ bản | 60 phút | 329.000 | không chia khung | batch-04:128 |
| Xóa thâm quầng mắt – Gói công nghệ điện xung trường | 90 phút | 629.000 | không chia khung | batch-04:139 |
| Detox da đầu | 40 phút | 139.000 | 159.000 | batch-05:41–42 |
| Gội đầu thư giãn | 50 phút | 199.000 | 229.000 | batch-05:93–94 |
| Chăm sóc nan tóc | 70 phút | 349.000 | không chia khung | batch-05:141 |

Tôi kiểm chéo giá giữa các file bằng hai script. `scan_prices.py` liệt kê mọi số tiền trong 31 file và file gom; mọi số tiền nằm ngoài 24 mức giá trên menu đều là số người soạn tự tính (giá theo phút, chênh lệch, giá trung bình). `check_price_pairs.py` kiểm 746 dòng có cả tên dịch vụ và giá hoặc thời lượng; 48 dòng bị báo, tôi đọc từng dòng và không dòng nào gán sai giá cho dịch vụ. Các dòng bị báo là dòng nêu khoảng giá của cả nhóm, dòng so sánh hai dịch vụ, và câu sai mẫu mà tài liệu 12 trích lại để chỉ lỗi (12:18, 12:779).

Ba điều menu không nói rõ và chatbot phải hỏi lại chủ doanh nghiệp: giá đêm tính theo giờ bắt đầu hay giờ kết thúc buổi; khung "sau 20h30" kết thúc lúc mấy giờ; và bước "Bắn ánh sáng xanh SHR ... (theo thời gian khuyến mại)" của Gói Mụn 5 in 1 (batch-04:80) có tính trong giá 599.000 hay không.

## D. Tài liệu tự mâu thuẫn ở đâu?

Tôi chia mâu thuẫn theo mức ảnh hưởng tới câu trả lời của chatbot. Mỗi dòng ghi đủ hai phía để anh mở file kiểm lại.

### Mâu thuẫn chatbot sẽ gặp ngay trong chat

| Chủ đề | Phía thứ nhất | Phía thứ hai | Ghi chú |
|---|---|---|---|
| Giờ mở cửa | file gom dòng 57 và 13:330 ghi 9h–24h | 13:178 ghi "chờ chị xác nhận"; 13:191 ghi "Có thể studio mở 9h – 24h"; 13:486 nêu ba khả năng 9h–20h30, 9h–22h, 9h–24h | Tài liệu 13 tự mâu thuẫn: mẫu sửa lỗi ở dòng 330 dùng giờ mà chính tài liệu chưa xác nhận |
| Địa chỉ phường | batch-01:14, batch-02:15, batch-05:14 và 13:174 ghi Tân Hưng | batch-03:164 ghi Tân Kiểng | Xem thêm mục F về việc sáp nhập phường năm 2025 |
| Xưng hô | 13:23–36 và file gom dòng 47–51: chatbot xưng *em*, gọi *anh/chị*, không dùng *bạn* | 06:53–54: khách là *bạn*, người nói là *mình*, không *em*; 06:250 áp quy tắc này cho cả "tin nhắn cho khách"; 01-tone-voice:34 không dùng *anh/chị* | 13:36 cho rằng hai cách không mâu thuẫn vì một bên là nội dung quảng bá, một bên là chat 1:1. Nhưng tài liệu 12, cũng viết cho chatbot, dùng *Bạn ơi* 21 lần và không dùng *anh/chị* lần nào. Tôi đếm *Bạn ơi* xuất hiện ở 12 file tài liệu tổng hợp, còn *anh/chị* chỉ có trong tài liệu 13 (19 lần) và một lần ở 01-tone-voice |
| Tên trợ lý | 13:65 ghi hai tên "Thị Thư" và "Nhã Trúc" xuất hiện khi thử chatbot | 13:75 tạm dùng "trợ lý thom house"; 13:488 đề xuất "Thơm", "Trúc", "Linh" | Hai tên này chỉ xuất hiện trong tài liệu 13, trong câu chat lỗi được trích lại |
| Tài liệu nào đọc trước | file gom dòng 11 và 13:3: đọc tài liệu 13 trước | 12:5 tự gọi là "ưu tiên cao nhất"; README:101–102 bảo chatbot đọc `00-brand-essence.md` trước | Cần một thứ tự ưu tiên duy nhất khi viết system prompt (lời dặn cố định gửi kèm mọi lượt chat) |
| Danh sách menu phụ nữ | 13:210–220 liệt kê 5 dịch vụ phụ nữ, có Tiêu u – Thông kinh ngực | 12:152–171 (mẫu câu hỏi Q4) liệt kê "5 dịch vụ" phụ nữ nhưng bỏ Tiêu u và thêm Chăm sóc nan tóc (dịch vụ tóc) | Đây đúng là lỗi "trả lời sai menu" mà tài liệu 13 cảnh báo |
| Quy tắc chia khung giờ | 12:645–646 và batch-05:183: dịch vụ ngắn 30–50 phút có giá ngày đêm, dịch vụ 60 phút trở lên giá cố định | Mở Vai – Nâng Mặt 60 phút, Massage cổ vai gáy 60 phút và Massage body 60–75 phút đều có giá ngày đêm (batch-01:54–55, 110–112, 142–145) | Quy tắc tóm tắt sai; chatbot phải tra bảng, không suy luận từ quy tắc |
| Yêu cầu chia khung giờ khi báo giá | 13:470 bắt mọi câu báo giá phải chia khung 9h–20h30 / sau 20h30 | 13:147 và 12:604–625: menu khỏe, phụ nữ, da không chia khung giờ | Checklist 13 cần sửa thành "chia khung khi dịch vụ có hai giá" |
| Định dạng khoảng giá | 13:124–131 coi "199.000–229.000" là lỗi vì không nói khung giờ | 13:241–244 tự dùng "199–250k", "199–449k", "429–569k" | |
| Dịch vụ nào có hướng dẫn chăm sóc sau buổi | 12:274: Thải hàn là dịch vụ duy nhất có hướng dẫn sau buổi | 07:199–222 có mẫu tin sau buổi cho Mụn 5 in 1 và Yoni Retreat | Menu chỉ ghi hướng dẫn tại nhà cho Thải hàn (batch-02:298) |

### Mâu thuẫn về số liệu và xếp hạng

| Chủ đề | Phía thứ nhất | Phía thứ hai | Theo giá menu |
|---|---|---|---|
| Dịch vụ đắt nhất | 03-pricing-structure:55 và _intake-log:81 (file gom dòng 9044, 10706): Yoni Retreat "đắt thứ 2 toàn studio" sau Diện chẩn 2,99 triệu | 05-customer-personas:212: Yoni Retreat "đắt nhất"; women-health-menu:150 viết cả hai ý trong một câu | 3.500.000 là giá cao nhất; câu "đắt thứ 2" sai |
| Giá cao nhất | 03-pricing-structure:130–132: "Giá cao nhất hiện có: 569,000" | các menu khác có giá tới 3.500.000 | Câu này viết từ đợt tải menu đầu tiên và không được cập nhật |
| Giá theo phút cao nhất | 03-pricing-structure:255 và women-health-menu:170: Nắn chỉnh sàn chậu (50.000đ/phút) cao nhất | women-health-menu:157: Nắn chỉnh "đắt thứ nhì theo giá/phút"; 03-pricing-structure:256 ghi Se khít 55.556đ/phút | Se khít làm hồng yoni cao nhất (2.500.000 / 45 phút) |
| Giá theo phút thấp nhất | 03-pricing-structure:211: Massage chân 45 phút, 5.556đ/phút | 03-pricing-structure:82, 90: Detox da đầu ban ngày, 3.475đ/phút | Detox da đầu ban ngày thấp nhất |
| Diện chẩn có trong bao nhiêu dịch vụ | 11:152 và 12:300: "11/23 dịch vụ" | Văn bản chép menu chỉ có chữ "diện chẩn" trong quy trình của 7 dịch vụ (ngừa đột quỵ, giải mỏi đứng lâu, thiếu máu não, đau thắt lưng, thải hàn, đau bụng kinh, se khít) | Danh sách 11 ở 11:138–150 tính cả "ấn huyệt mặt", "massage mặt", tính Mở Vai – Nâng Mặt (menu không có bước nào), và bỏ sót ba dịch vụ khỏe thật sự có diện chẩn. 12:303 còn nói "mọi dịch vụ menu phụ nữ" có diện chẩn, trong khi Yoni Retreat, Nắn chỉnh và Tiêu u không ghi bước diện chẩn |

### Mâu thuẫn về tên, chính tả và định nghĩa

| Chủ đề | Các cách ghi |
|---|---|
| Cách viết tên thương hiệu | 06:18–20: mặc định *thom house*, *Thơm House* cho văn cảm xúc và Fanpage, cấm *Thom House*. Nhưng 06:226 gọi *Thom House* là "chữ hoa có dấu", batch-05:63 dùng *Thom House* trong thân bài, và _intake-log:165 cũng gọi *Thom House* trong thân bài là "cách viết hoa có dấu". README:88 vẫn liệt kê cách viết tên là câu hỏi chờ xác nhận |
| Tên dịch vụ thư giãn đầu tiên | batch-01:27 "Mở Vai – Nâng Mặt"; batch-01:43 "Vai Cổ Thông Sáng Mặt Tự Nhiên" |
| Chính tả trên menu | "nan tóc" hay "nang tóc" (batch-05:147); "Xã phục hồi" hay "Xả phục hồi" (batch-05:78; tài liệu 12:483 đã tự sửa thành "Xả"); "bộ nguyệt" (batch-02:176; tôi đoán là "bộ huyệt" vì câu nói về ấn huyệt, chưa xác nhận); "Đắp nạ vi sinh" (batch-04:103) |
| SHR là gì | batch-04:166 "Smart Hair Removal / Selective High-frequency Radiation"; 09:264 "Suppressed Hair Removal", có thể là đèn LED xanh; 11:916 "Selective Hair Removal hoặc Super Hair Removal" dùng công nghệ ánh sáng xung; 11:1367 khẳng định là "ánh sáng LED (non-thermal)". Menu chỉ ghi "ánh sáng xanh SHR" |
| Plasma | Menu chỉ ghi "plasma đưa tinh chất xuống da" (batch-04:142). 12:334 và 11:1351 khẳng định thêm là "plasma lạnh", "an toàn cho da, không gây bỏng hay rạn" |
| Whitetox | Menu chỉ ghi tên (batch-04:75). 11:1052–1055 tự đoán thành phần (AHA, BHA, PHA, vitamin C, niacinamide) |
| Câu chuyện người sáng lập | Menu: "đã chăm sóc dứt điểm" (batch-02:290). 12:255, 12:432 và 08:148 viết thành "tự chăm sóc dứt điểm" |

## E. Câu nào có rủi ro khi chatbot nói lại?

Tôi chạy `python3 -I scripts/scan_risky.py sources/drive`; script đánh dấu 972 dòng có từ khóa thuộc sáu nhóm (bệnh, chữa, con số hiệu quả, công nghệ, chăm sóc sau buổi, đối tượng cần thận trọng). Tôi đọc các dòng thuộc văn bản chép menu, tài liệu 07, 09, 10, 11, 12, 13 và chọn ra các câu dưới đây. Đây là danh sách chính, không phải danh sách đủ cả 972 dòng; các dòng còn lại phần lớn là câu cấm, câu nhắc khám bác sĩ hoặc câu nhắc lại cùng nội dung.

Cột "Đề xuất" là đề xuất của tôi, chưa có ý kiến của người có chuyên môn y tế hay pháp lý. Tôi chưa kiểm quy định quảng cáo dịch vụ chăm sóc sức khỏe của Việt Nam trong nhánh việc này. "Chuyển người" nghĩa là chatbot không tự trả lời mà chuyển cho nhân viên.

### Nhóm 1. Lời hứa chữa hoặc phòng bệnh nằm ngay trên menu

| Vị trí | Câu (rút gọn) | Loại | Đề xuất |
|---|---|---|---|
| batch-02:56, 26 | tên "Diện chẩn ngừa đột quỵ"; "bộ huyệt chống đột quỵ" | phòng bệnh nguy hiểm | Chủ doanh nghiệp quyết giữ hay đổi tên. Nếu giữ, chatbot chỉ đọc tên và nói "liệu trình chăm sóc vùng đầu, vai, cổ theo phương pháp diện chẩn, ấn huyệt, hơ ngải; không thay thế khám và điều trị" |
| batch-02:24 | "ấn huyệt xoá tắt nghẽn mạch máu" | tác động mạch máu | Bỏ; thay bằng "diện chẩn mặt, ấn huyệt" |
| 12:404, 10:62 | "Phòng ngừa đột quỵ chủ động cho người 40+"; "gia đình có tiền sử đột quỵ" | nhắm người có nguy cơ bệnh | Bỏ. Khách kể có tiền sử đột quỵ, tăng huyết áp hoặc tê yếu tay chân thì chuyển người và khuyên khám bác sĩ |
| batch-02:153 | tên "Thiếu máu não – tê tay, căng thẳng khó ngủ" | chẩn đoán bệnh | Chủ doanh nghiệp quyết tên; chatbot mô tả là "chăm sóc vai cổ chuyên sâu" (đúng tên phụ trên menu, batch-02:133) |
| batch-03:96 | "hỗ trợ chữa sa tử cung"; "giảm viêm nhiễm"; "thon gọn môi bé" | chữa bệnh phụ khoa, thay đổi cơ thể | Bỏ. Mô tả bằng các bước trên menu |
| batch-03:117 | Yoni Retreat cho "tử cung bị sa trễ sau khi sanh thường, không còn ham muốn" | bệnh phụ khoa, sức khỏe tình dục | Bỏ khỏi câu trả lời tự động; chuyển người |
| batch-03:149 | Nắn chỉnh sàn chậu "hỗ trợ nâng cao các bệnh lý sa tử cung, viêm nhiễm, khí hư" | chữa bệnh phụ khoa | Bỏ |
| batch-03:161, 171 | tên "Tiêu u"; "Giảm u hạch, tuyến giáp"; "Điều khí lưu thông máu từ tim"; "Chăm sóc phổi" | chữa khối u, bệnh tuyến giáp, tim, phổi | Bỏ các câu lợi ích. Tên dịch vụ do chủ doanh nghiệp quyết. Khách hỏi về hạch, u, tuyến giáp thì chuyển người và khuyên khám bác sĩ |
| batch-03:177 | "giải các tắt nghẽn có nguy cơ gây tức, lối ngực và ung thư vú" | phòng ung thư | Bỏ hẳn |
| 13:455, 12:456, 11:1432 | mẫu trả lời "đã sửa" vẫn ghi "Hỗ trợ giảm u hạch, tuyến giáp" | tài liệu hướng dẫn lặp lại lời hứa | Sửa mẫu; chuyển người |
| batch-03:40 | "Đôi lời của Thơm": tử cung lạnh dẫn đến "khó có thai, dễ sảy thai, tụt huyết áp" | gắn bệnh với quan niệm Đông y | Không đưa vào câu trả lời tự động; 13:438 đang khuyến khích chatbot trích bài này |
| batch-02:244, 248 | mùi cơ thể do "độc tố" thoát qua mồ hôi; "làm sạch từ bên trong" | giải thích cơ chế không có căn cứ | Bỏ câu cơ chế; khách kể mùi cơ thể kéo dài thì gợi ý khám bác sĩ |
| batch-02:190, 194 | triệu chứng là do "chính khí của thận đang suy yếu"; "giảm đau mỏi rõ rệt" | chẩn đoán, hứa hiệu quả | Bỏ phần chẩn đoán; giữ mô tả các bước |
| batch-05:54, 104 | gội đầu muộn "sẽ rất dễ bệnh"; "dễ nhiễm lạnh lại hay sinh bệnh" | dọa bệnh | Bỏ trong chat; chủ doanh nghiệp có thể giữ trên menu nếu muốn |
| batch-05:157, 160 | "Ủ dược liệu kích mọc tóc"; "muối thảo dược giảm rụng" | hứa mọc tóc | Chatbot đọc nguyên tên bước, kèm câu "kết quả tùy từng người, bên em không cam kết mọc tóc" |
| batch-02:290; 12:255 | người sáng lập "đã chăm sóc dứt điểm" nhiễm hàn | lời chứng cá nhân dễ thành lời hứa | Chỉ dùng khi khách hỏi về người sáng lập, không dùng để bán Thải hàn |

### Nhóm 2. Con số hiệu quả và thông tin máy móc, sản phẩm không kiểm được

| Vị trí | Câu | Đề xuất |
|---|---|---|
| batch-04:142 | "hiệu quả gấp 20 lần điện di ion bình thường" | Bỏ con số cho tới khi chủ doanh nghiệp đưa nguồn (tài liệu của hãng máy hoặc nghiên cứu). Tài liệu 09:296, 01-tone-voice:317, skincare-menu:155 và 11:1359 đang yêu cầu chatbot nói lại nguyên văn con số này |
| batch-04:131 | "giảm ngay tình trạng thâm đen" | Bỏ "ngay" |
| batch-04:68, 80 | "Khô còi mụn nhanh chóng"; "SHR phục hồi da nhanh chóng" | Bỏ "nhanh chóng"; SHR chỉ nói "bước ánh sáng xanh, áp dụng theo chương trình khuyến mại (chi tiết hỏi nhân viên)" |
| 12:334–339, 11:1351 | plasma "lạnh", "an toàn cho da, không gây bỏng hay rạn", "kích thích collagen", "khử khuẩn" | Bỏ cho tới khi có tên máy và tài liệu của hãng |
| 11:1367 | SHR là "ánh sáng LED non-thermal, an toàn cho phần lớn loại da" | Bỏ |
| 11:1052–1055 | thành phần Whitetox đoán là AHA, BHA, PHA, vitamin C | Bỏ; chatbot nói "sản phẩm làm sạch sừng chết và bã nhờn, thành phần anh/chị hỏi nhân viên" |
| batch-04:52, 102 | "xịt tế bào gốc", "thanh xịt tế bào gốc" | Chatbot dùng đúng tên trên menu, không giải thích là tế bào gốc người; 11:1507 đã có câu hỏi về điều này |

### Nhóm 3. Mẫu tin sau buổi coi phản ứng cơ thể là bình thường

| Vị trí | Câu | Đề xuất |
|---|---|---|
| 07:203 | Sau Thải hàn "hơi mệt nhẹ 1-2 ngày là bình thường (cơ thể đang đẩy độc tố)" | Viết lại: "Nếu anh/chị thấy mệt, chóng mặt, đau tăng hoặc có biểu hiện lạ, anh/chị nhắn bên em ngay hoặc đi khám." Bỏ giải thích "đẩy độc tố" |
| 07:176 | khách "đôi khi hơi mệt do thải độc" | Bỏ "do thải độc" |
| 07:220 | Sau Yoni Retreat "hơi căng nhẹ vùng bụng dưới là bình thường" | Bỏ câu "là bình thường"; thay bằng câu báo lại như trên, thêm dấu hiệu cần đi khám như đau nhiều, sốt, ra máu bất thường. Danh sách dấu hiệu cần người có chuyên môn duyệt |
| 07:209–211 | sau Mụn 5 in 1: không trang điểm 24h, tránh acid mạnh, báo nếu đỏ kéo dài | Giữ được, sau khi chủ doanh nghiệp duyệt; câu này đã có hướng dẫn báo lại |
| 07:201, 07:217 | "không uống đồ lạnh trong 2-3 ngày", "48h đầu tránh quan hệ" | Cần chủ doanh nghiệp xác nhận là quy định của studio trước khi gửi tự động |

### Nhóm 4. Quy tắc an toàn do người soạn tự viết, chưa ai duyệt

| Vị trí | Nội dung | Đề xuất |
|---|---|---|
| 11:1224–1240 | bảng dịch vụ nào "thường OK" với người mang thai (ví dụ Massage cổ vai gáy lực nhẹ, gội đầu) | Không dùng để trả lời. Chatbot chỉ nói "anh/chị đang mang thai thì bên em cần KTV xác nhận trước" và chuyển người. Bảng này còn tự mâu thuẫn: 11:1236 ghi massage cổ vai gáy nhẹ "thường OK", 11:1421 dặn "không massage mạnh vai cổ" khi gội đầu, 11:1234 ghi da kích ứng "Hỏi KTV" còn 11:1422 ghi "có thể OK" |
| 11:1244–1254; 12:154, 12:377; 13:457 | đợi 2–3 tháng sau sinh rồi mới làm dịch vụ vùng bụng, vùng kín | Cần chủ doanh nghiệp xác nhận mốc thời gian; trong lúc chờ, chuyển người |
| 11:1258–1271 | danh sách bệnh cần khám trước (u nghi ác tính, ung thư, tim mạch, tiểu đường, chống đông, đột quỵ gần đây) | Giữ làm danh sách chuyển người. Bỏ câu "dịch vụ chỉ hỗ trợ độ nhẹ" ở 11:1271 vì chatbot không phân độ sa tử cung được |
| 11:1278–1290 | hỏi tiền sử dị ứng hà thủ ô, bồ kết, bưởi, ngải cứu | Giữ làm câu hỏi trước khi đặt lịch, sau khi chủ doanh nghiệp duyệt |
| batch-03:179 | đắp na "không dành cho khách nhiễm hàn" | Đây là lưu ý duy nhất có trên menu; giữ nguyên |

## F. Chatbot trả lời được câu hỏi nào, câu nào anh phải bổ sung?

| Câu hỏi của khách | Tài liệu trả lời được không | Nguồn hoặc việc cần làm |
|---|---|---|
| Có những dịch vụ gì, giá bao nhiêu, bao lâu | Được | `data/services.json` |
| Quy trình từng bước của dịch vụ | Được cho 17 dịch vụ (tính cả hai gói quầng mắt chỉ có một câu mô tả); chưa có cho 6 dịch vụ (4 dịch vụ thư giãn, Yoni Retreat, Nắn chỉnh sàn chậu) | Chủ doanh nghiệp bổ sung quy trình 6 dịch vụ này |
| Dịch vụ nào là Signature, combo nào có | Được: Yoni Retreat, Gói Mụn 5 in 1; Yoni Retreat tặng Nắn chỉnh sàn chậu | batch-03:131, batch-04:65 |
| Giờ mở cửa, giờ nhận khách cuối, ngày nghỉ | Không | Đang mâu thuẫn (mục D) |
| Địa chỉ | Một phần: số nhà và đường thống nhất, phường mâu thuẫn | Theo Nghị quyết 1685/NQ-UBTVQH15 ngày 16/6/2025, khoản 21 Điều 1, bốn phường Tân Phong, Tân Quy, Tân Kiểng, Tân Hưng được nhập thành phường Tân Hưng mới, hoạt động từ 01/7/2025 (nguồn: bản dịch trên english.luatvietnam.vn, truy cập 2026-11-07; tôi chưa mở được bản trên cổng chính thức vì hoatieu.vn trả lỗi 403). Vậy hai cách ghi Tân Hưng và Tân Kiểng có thể cùng chỉ một nơi sau sáp nhập. Việc cấp quận đã bị bỏ khỏi địa chỉ là chưa xác minh (từ hiểu biết trước). Chủ doanh nghiệp cần chốt dòng địa chỉ chatbot gửi |
| Bản đồ | Có link Google Maps ở 13:176 | Link không có trên menu; tôi chưa mở link. Cần xác nhận |
| Nơi gửi xe | Không | Bổ sung |
| Số hotline, Zalo OA, website, email | Không | 13:179, 13:487–490 đang chờ |
| Fanpage | Chỉ có tên "Thơm House", không có URL | Bổ sung URL |
| Đặt lịch thế nào | Một phần: 12:537–548 thu dịch vụ, ngày giờ, tên, số điện thoại | Bổ sung ai xác nhận lịch, trong bao lâu, giữ chỗ bao lâu |
| Hủy lịch, đổi lịch, đến trễ | Không | Bổ sung |
| Đặt cọc, thanh toán, hoàn tiền, xuất hóa đơn | Không | Bổ sung |
| Thẻ quà tặng, thành viên, gói nhiều buổi | Không; 03-pricing-structure:381–386 ghi là câu hỏi mở | Bổ sung hoặc ghi rõ "không có" |
| Khuyến mại hiện có | Không; menu chỉ có cụm "theo thời gian khuyến mại" ở bước SHR | Bổ sung. Tài liệu 07:50 và 07:233 dặn tránh quảng cáo giảm giá và tránh nhắn khuyến mại liên tục, nên nội dung tin khuyến mại cần chủ doanh nghiệp duyệt |
| Nhân viên nam hay nữ, có phục vụ khách nam, trẻ em không | Không; 03-pricing-structure:386 và hair-care-menu:172 ghi là câu hỏi mở | Bổ sung |
| Mang thai, sau sinh, đang bệnh có làm được không | Chỉ có quy tắc do người soạn tự viết (mục E nhóm 4) | Chủ doanh nghiệp duyệt danh sách chuyển người |
| Dị ứng thành phần | Một phần: menu có tên dược liệu tóc; loại tinh dầu, serum vùng kín, tinh chất da không có tên | Bổ sung tên sản phẩm nếu muốn chatbot trả lời |
| Mẫu tin cảm ơn, hỏi thăm, nhắc lịch | Một phần: 07:180–228 có mẫu và mốc 24 giờ, 2–3 ngày, 1 tháng | Mẫu dùng *bạn – mình* và có câu rủi ro ở mục E nhóm 3; cần duyệt và viết lại theo cách xưng hô được chọn |
| Câu hỏi chuyên môn (diện chẩn, hơ ngải, bát liêu, hà thủ ô) | Có câu trả lời mẫu ở 11:1306–1610 và 12:280–370 | Phần lớn là kiến thức người soạn tự thêm (tài liệu 11 dán nhãn các mục này là kiến thức chung, dòng 25), chưa ai duyệt. Có chi tiết cần kiểm như "Giáo sư Bùi Quốc Châu sáng lập từ năm 1980" (12:287); tôi chưa kiểm chi tiết này |

## G. Tài liệu 12 và 13 đặt ra quy tắc gì cho chatbot?

Tôi gom quy tắc từ hai tài liệu thành danh sách quy tắc ứng viên. Quy tắc nào hai tài liệu nói khác nhau thì ghi cách xử lý tôi đề xuất.

| Số | Quy tắc ứng viên | Nguồn | Xung đột và đề xuất |
|---|---|---|---|
| R1 | Chỉ giới thiệu bản thân ở câu chào đầu cuộc trò chuyện, không lặp "Tôi là trợ lý..." ở mỗi tin | 13:40–59 | Không xung đột |
| R2 | Xưng hô thống nhất trong cả cuộc trò chuyện | 13:21–36; 12 toàn bộ mẫu; 06:51–55 | Xung đột (mục D). Đề xuất chọn *em – anh/chị* rồi viết lại mẫu của tài liệu 12 |
| R3 | Không dùng các từ cấm: điều trị, trị bệnh, chữa khỏi, châm cứu, bài thuốc đặc trị, đặc trị, bệnh lý nền, diệt sạch, 100% hiệu quả, đảm bảo, thay thế thuốc, không cần đi bác sĩ | 13:83–100; 12:659 | Danh sách từ cấm không bắt được lời hứa nằm trong tên dịch vụ và câu lợi ích trên menu (mục E). Đề xuất thêm danh sách câu cấm theo mục E, kiểm bằng code trước khi gửi, không chỉ dặn trong system prompt |
| R4 | Gặp vấn đề y tế nghiêm trọng thì khuyên khám bác sĩ chuyên khoa trước | 13:112–114; 11:1258–1274; 12:726–741 | Đề xuất thêm bước chuyển người, vì chatbot không đánh giá được mức nặng nhẹ |
| R5 | Không gán bằng cấp y khoa cho người sáng lập hay nhân viên | 12:660, 12:816; file gom dòng 24–29 | Không xung đột |
| R6 | Báo giá luôn kèm thời lượng; dịch vụ có hai giá thì nói rõ khung giờ của từng giá | 13:133–158; 12:75 | 13:470 đòi chia khung cho mọi giá, trái với menu. Đề xuất "chia khung khi dịch vụ có hai giá" |
| R7 | Tra bảng giá trước khi báo, không nhớ, không gộp giá của hai dịch vụ | 12:591–593; 12:17–19 | Đề xuất chatbot lấy giá từ `services.json` qua code, không để mô hình tự chép |
| R8 | Hỏi về một menu thì chỉ liệt kê dịch vụ của menu đó, và liệt kê đủ | 13:195–266; 12:33–44 | 12:152–171 tự vi phạm (mục D) |
| R9 | Không bịa thành phần, kỹ thuật, thông tin liên hệ; không chắc thì nói chung và mời hỏi nhân viên | 13:290–312; 12:21–23, 12:552–566 | Tài liệu 11 và 12 tự vi phạm (plasma lạnh, SHR là LED, thành phần Whitetox). Đề xuất coi tài liệu 09–11 là tài liệu tham khảo cho nhân viên, không phải nguồn trả lời tự động, cho tới khi được duyệt |
| R10 | Viết tên dịch vụ đúng chính tả theo bảng chính thức | 13:270–286 | Bảng chính thức chưa có, vì còn các lỗi chính tả trên menu chưa xác nhận (mục D) |
| R11 | Câu ngắn, có gạch đầu dòng khi liệt kê, in đậm tên và giá, xuống dòng giữa các ý | 12:25–27, 12:65–76 | Cần kiểm Zalo hiển thị được chữ in đậm và gạch đầu dòng trong tin nhắn hay không; việc này thuộc nhánh nghiên cứu Zalo |
| R12 | Emoji theo nhóm dịch vụ, tối đa 2–3 emoji mỗi câu trả lời | 12:570–587 | Không xung đột trong tài liệu; đây là lựa chọn giọng văn của chủ doanh nghiệp |
| R13 | Hỏi 1–2 câu để hiểu tình trạng trước khi gợi ý dịch vụ; không đẩy combo lớn ngay | 07:86–92, 07:108–111; 12:193–195 | Không xung đột |
| R14 | Câu kết nhẹ nhàng, không thúc khách đặt lịch | 13:476; 12:662; 07:104–106 | Không xung đột |
| R15 | Gợi ý dịch vụ giá thấp cho khách mới | 07:98; 10:295 | Không xung đột; là quy tắc bán hàng, cần chủ doanh nghiệp đồng ý |
| R16 | Chăm sóc sau buổi: tin cảm ơn trong 24 giờ, hỏi thăm sau 2–3 ngày, một tin sau khoảng 1 tháng, khách không trả lời thì không nhắn thêm, không hỏi "khi nào quay lại" trước 1 tuần | 07:180–233 | Đây là hướng dẫn, chưa phải lịch đã duyệt. Mẫu tin có câu rủi ro (mục E nhóm 3) |
| R17 | Khách có dấu hiệu nhiễm hàn thì bỏ bước đắp na trong Tiêu u | batch-03:179; 11:1206–1220 | Không xung đột |
| R18 | Trước khi gửi, tự kiểm danh sách 10 câu (13:465–478) hoặc 6 câu (12:808–819) | 13, 12 | Hai danh sách khác nhau; 12:819 viết "YES cho cả 6 thì gửi" nhưng câu 3 và câu 5 của danh sách phải trả lời "không" mới đúng. Đề xuất chuyển danh sách kiểm thành code kiểm trước khi gửi |

## Kết luận cho các nhận định của báo cáo trước (K1–K14)

| Mã | Kết luận | Căn cứ |
|---|---|---|
| K1 | Đúng một phần | Kích thước 578.085 byte, đo bằng `wc -c`. File gom tự ghi ngày 2026-05-16 (dòng 6, 10.835) và 30 tài liệu (dòng 7, 10.834). Ngày sửa đổi trên Drive không kiểm được |
| K2 | Đúng một phần | 06:18–19 đúng như mô tả. Ngày sửa 2026-11-03 không kiểm được. Nội dung tài liệu 06 trùng hoàn toàn với phần tương ứng trong file gom, nên nếu file 06 mới hơn thì cũng không có nội dung mới |
| K3 | Đúng | 23 dịch vụ, 33 mức giá, đếm từ văn bản chép menu và kiểm bằng `build_services.py` |
| K4 | Đúng | 13:23–36 so với 06:53–54 và 06:250 |
| K5 | Đúng | batch-05:93–96 |
| K6 | Đúng | batch-01:80–81 (Massage chân một khung 9h–24h); batch-05:141 (nan tóc một giá) |
| K7 | Đúng | 07:180, 07:182, 07:226; 07:297 ghi các chỉ số chỉ là gợi ý |
| K8 | Đúng | file gom dòng 57 so với dòng 590, 603, 931 |
| K9 | Đúng | 13:65 |
| K10 | Đúng | 13:87–90 cấm; batch-02:56, batch-03:171, batch-03:96 hứa |
| K11 | Đúng | file gom dòng 4222–4227 (09:294–299) |
| K12 | Đúng | SHR có bốn cách diễn giải khác nhau (mục D); Whitetox không có thành phần |
| K13 | Đúng | file gom dòng 9044 "đắt thứ 2", trong khi 3.500.000 lớn hơn 2.990.000 |
| K14 | Đúng một phần | 07:203 đúng là mệt nhẹ do "đẩy độc tố" là bình thường. Câu thứ hai ở 07:220 là "căng nhẹ vùng bụng dưới" sau Yoni Retreat, không phải "đầy hơi" |

## Nói ngắn gọn nhất

Bảng giá dùng được ngay: 23 dịch vụ, 33 mức giá, không file nào ghi khác. Phần lời lẽ thì chưa dùng được ngay. Chính menu đang hứa ngừa đột quỵ, giảm u hạch, hỗ trợ chữa sa tử cung và hiệu quả gấp 20 lần. Các tài liệu hướng dẫn cấm những lời hứa đó nhưng vẫn chép lại, và còn tự thêm thông tin về máy móc, thai kỳ mà không ai duyệt. Vì vậy, bản đầu tiên của chatbot nên chỉ đọc tên, thời lượng, giá và các bước từ dữ liệu có cấu trúc, và chuyển cho nhân viên mọi câu hỏi về bệnh, thai kỳ hay sau sinh. Trước khi bật trả lời tự động, anh cần chốt cách xưng hô, giờ mở cửa, địa chỉ hiện hành và các chính sách đặt lịch, hủy lịch, thanh toán mà tài liệu chưa có.

# Nghiên cứu thom house ngày 08/11: menu in, thương hiệu, ba phiên video và repo Zalo

Ngày viết: 2026-11-08. Người đọc: anh, trước khi sửa bảng giá của chatbot và trước khi chọn phần nào của các dự án khác để đem sang chatbot thom house. Báo cáo gom tám báo cáo nghiên cứu cùng ngày trong thư mục `research/`, kết quả một lượt kiểm lại độc lập trên từng điểm lệch của ảnh menu, và các ảnh tôi tự mở lại.

## Phần anh cần duyệt

Phần này là phần anh cần duyệt. Tôi viết bằng lời thường; chi tiết kỹ thuật nằm ở các mục sau.

Bảng giá mà chatbot đang dùng đã cũ so với bộ ảnh menu in trên Drive. Bảng giá đó là file `data/services.json`, trong báo cáo này tôi gọi là catalog. Catalog được dựng từ văn bản chép menu ngày 16/05/2026, trong báo cáo này gọi là bản chép tháng 5. Bộ ảnh menu in gồm 57 ảnh trong bốn thư mục: da, khỏe, tóc và triệt lông. Giá của mọi dịch vụ có ở cả hai nơi đều khớp, gồm 3 dịch vụ da, 6 dịch vụ khỏe và 3 dịch vụ tóc. Các điểm lệch nằm ở thời lượng, quy trình, tên dịch vụ và phần catalog chưa có.

Catalog đang ghi sai so với ảnh ở sáu dịch vụ:

| Dịch vụ | Catalog đang ghi | Ảnh menu in ghi | Ảnh |
|---|---|---|---|
| Gói Mụn 5 in 1 | 90 phút; 6 bước, bước cuối là ánh sáng xanh SHR "theo thời gian khuyến mại" | 60–90 phút; 5 bước, không có bước SHR | da `4.png`, `5.png` |
| Xóa thâm quầng mắt, gói cơ bản | 60 phút | 45 phút | da `8.png` |
| Xóa thâm quầng mắt, gói công nghệ điện xung trường | 90 phút; danh sách câu chatbot không được nói ghi "gấp 20 lần điện di ion" | 60 phút; ảnh in "gấp 10 lần điện di ion bình thường tại cơ sở" | da `8.png`, `9.png` |
| Diện chẩn ngừa đột quỵ | tên Diện chẩn ngừa đột quỵ | tên Ngừa đột quỵ ở bìa, slide giới thiệu và slide quy trình | khỏe `17.png` đến `19.png` |
| Detox mùi cơ thể | tên Detox mùi cơ thể | tên Detox cơ thể ở bìa và hai tiêu đề | khỏe `5.png` đến `7.png` |
| Chăm sóc nan tóc | bước 9 là "Xã phục hồi" | bước 9 là "Xả phục hồi" | tóc `9.png` |

Catalog còn thiếu 10 dịch vụ với 23 mức giá. Đó là 8 dịch vụ da từ 289.000đ đến 6.500.000đ, Peel peptide da đầu 299.000đ trong 15 phút, và menu triệt lông 12 mức giá từ 100.000đ đến 18.000.000đ. Catalog cũng thiếu 5 option cộng thêm và 3 loại mặt nạ in trên menu tóc. Bộ kiểm tra bản nháp là đoạn code server chạy trên mỗi bản nháp trước khi gửi. Chú thích trong code này ghi rằng mọi con số tiền trong bản nháp phải khớp giá do catalog trả về, nên chatbot hiện chưa báo được giá nào trong số này. Theo chiều ngược lại, 11 dịch vụ trong catalog không có ảnh nào trong bộ ảnh in: 2 dịch vụ da, 4 dịch vụ thư giãn và 5 dịch vụ phụ nữ.

Tôi đã ghi toàn bộ đề xuất sửa vào `data/services-corrections.json`, gồm 22 điểm sửa đã được xác nhận và 18 mục mới. Tôi không sửa `data/services.json`.

Ngoài menu, có ba kết luận anh nên biết. Thứ nhất, không repo GitHub nào nên thay stack hiện tại, tức năm phần listener, server, runner, bridge và console đang chạy trên máy Mac, kể cả `aizaloapp/zalo-flow` mà anh gửi. Repo đó tự gửi câu trả lời không qua duyệt. Theo báo cáo đọc mã nguồn (chưa chạy thử), repo đó còn cho máy khác cùng mạng gửi tin bằng tài khoản Zalo của anh. Thứ hai, thom house chưa có design system chính thức, tức bộ quy định chung về màu, font, logo và giọng văn; nguồn màu và font đầy đủ nhất là trang landing page trong dự án Thomhouse Academy. Thứ ba, ba phiên làm video hằng ngày cho thấy chatbot nên giữ trạng thái duyệt trong server và console của mình. Khi app chuyển sang tài khoản claude.ai khác, các trang web để anh bấm duyệt video và các lịch chạy đặt trên claude.ai đều biến mất khỏi tài khoản mới.

Anh cần quyết sáu việc.

1. Bộ ảnh menu in có phải menu đang bán không? Việc này cần anh xác nhận, hoặc hỏi chị Thơm, vì không ảnh nào ghi ngày. Nếu đúng, catalog cần sửa theo file đề xuất và thêm 10 dịch vụ mới. Nếu bản chép tháng 5 vẫn là bản đang bán, catalog giữ nguyên, nhưng khách đang cầm menu in sẽ nghe chatbot báo thời lượng khác menu. Tôi đề xuất coi bộ ảnh in là bản đang bán cho nhóm da, khỏe, tóc và triệt lông, vì trang landing page khớp bộ ảnh in ở cả ba thời lượng lệch và ở câu "gấp 10 lần". Điểm yếu: căn cứ chỉ là hai nguồn khớp nhau, và cả hai nguồn đều không ghi ngày.
2. Gói Mụn 5 in 1 kéo dài bao lâu? Ba nguồn ghi ba con số. Ảnh menu in và trang landing page ghi 60–90 phút, catalog ghi 90 phút, còn ảnh chụp màn hình điện thoại trong bộ ảnh không gian (`IMG_7874.jpg`) ghi 90–120 phút. Tôi đề xuất chatbot báo 60–90 phút sau khi anh xác nhận; trong lúc chờ, chatbot báo giá và chuyển nhân viên khi khách hỏi thời lượng. Điểm yếu: khách hỏi thời lượng phải chờ nhân viên.
3. Thêm 10 dịch vụ mới vào catalog tới mức nào? Ba dịch vụ cần anh cân nhắc riêng: Inner Fill 6.500.000đ có bước "hoạt chất theo chỉ định", Bio PDRN bản full 5.000.000đ có bước bắn IPL và mặt nạ Carboxy, và Lăn dưỡng 1.500.000đ hoặc 2.500.000đ. Chưa ai tra quy định giấy phép cho các bước này; bản giao việc cho phiên làm video học viện đã loại ba dịch vụ này vì cùng lo ngại. Tôi đề xuất thêm cả 10 dịch vụ ở trạng thái nháp chưa duyệt, chỉ gồm tên, thời lượng, giá và tên bước, không kèm câu mô tả tác dụng. Với ba dịch vụ trên, chatbot chỉ trả lời khi khách hỏi đúng tên. Điểm yếu: nếu các bước đó thật sự cần giấy phép, chatbot vẫn đang báo giá cho chúng.
4. Có đổi tên hai dịch vụ khỏe theo ảnh không? Ảnh ghi Ngừa đột quỵ và Detox cơ thể, còn catalog ghi Diện chẩn ngừa đột quỵ và Detox mùi cơ thể. Tôi đề xuất đổi theo ảnh và giữ tên cũ làm tên gọi khác để khách gõ tên nào cũng ra. Điểm yếu: Ngừa đột quỵ vẫn là tên hứa ngăn một bệnh, nên đổi theo ảnh không làm tên an toàn hơn. Đổi tên còn kéo theo việc sinh lại file dữ liệu mà server dựng từ catalog (`apps/server/src/seed-data.ts`) và sửa một test.
5. Có chặn mọi con số dạng "gấp N lần" không? Bộ kiểm tra bản nháp chỉ chặn đúng cụm "gấp 20 lần", trong khi ảnh in "gấp 10 lần". Bộ kiểm tra cũng chưa chặn chữ "lâm sàng", mà ảnh menu da in "Lâm sàn trong 7 năm qua". Tôi đề xuất chặn theo mẫu chữ "gấp", một con số rồi chữ "lần", và chặn cả "lâm sàng" lẫn "lâm sàn". Điểm yếu: mẫu này chặn nhầm câu bình thường như "giá gấp 2 lần gói cơ bản", và nhân viên phải duyệt tay các bản nháp đó.
6. Có tách tài khoản Claude của bot khỏi các phiên làm video không? Pool của bot là danh sách tài khoản Claude mà runner luân phiên dùng. Báo cáo về phiên Aura suy luận rằng tài khoản ưu tiên 1 trong pool có thể trùng tài khoản mà phiên Aura đang dùng. Trong tuần này, tài khoản Claude của các phiên video đã hai lần chạm giới hạn dùng hằng tuần, lúc 21:55 ngày 05/11 và khoảng 19:34 ngày 07/11. Tôi đề xuất bot dùng một tài khoản riêng, hoặc ít nhất đặt tài khoản dùng chung ở ưu tiên thấp trong pool; anh chạy `python3 scripts/runner/claude_pool.py status` để đối chiếu. Điểm yếu: thêm một gói subscription là thêm tiền.

Ngoài sáu quyết định trên, có năm câu anh chỉ cần hỏi chị Thơm rồi điền đáp án:

- Giá combo 20 buổi triệt lông vùng Nách là 2.000.000đ như ảnh in, hay 1.500.000đ theo quy luật 10 lần giá suất lẻ mà năm dòng còn lại theo?
- Option massage cổ, vai, gáy 30 phút giá +199.000đ có tăng lên 239.000đ sau 20h30 như dịch vụ riêng cùng tên không?
- Giải mỏi đứng lâu giá 599.000đ trong 60 phút như ảnh in, hay 250.000đ trong 45 phút như trang landing page? Quy trình thật của dịch vụ này là gì, khi slide quy trình in nhầm sang các bước vai cổ?
- Ba loại mặt nạ là hàng bán lẻ hay bước thêm trong dịch vụ, và năm option được cộng vào dịch vụ nào?
- Khách mới sinh dưới bao lâu thì chatbot chuyển cho nhân viên: 2–3 tháng như trang landing page, hay 6 tháng như phiếu sức khỏe giấy?

Một việc nên làm ngay mà không cần quyết: thu hồi khóa API Anthropic anh dán vào chat tối 05/11. Tôi so bằng mã băm và thấy cùng một chuỗi khóa nằm trong transcript của cả phiên Dark Brain lẫn phiên Aura, mỗi file 5 lần.

Ba việc nhỏ đã có đề xuất mặc định; anh chỉ cần lên tiếng nếu không đồng ý. Chatbot không gửi số tài khoản ngân hàng và mật khẩu wifi in trên bảng ở quầy; nhân viên gửi thông tin chuyển khoản. Tôi không tải file cấu hình `.claude/settings.local.json` còn trên Drive. File ghi âm 31 giây của chị Thơm chưa được chép lời; anh nghe rồi gõ lại là cách nhanh nhất.

## Tôi đã đọc và chạy gì?

Tôi đọc toàn bộ ba báo cáo đối chiếu ảnh menu: `research/menu-audit/facial.md`, `research/menu-audit/healing.md` và `research/menu-audit/thugian-hairremoval.md`. Tôi đọc phần cần duyệt, phần kết luận và các mục liên quan của năm báo cáo khác: `research/10-brand-space-design-system.md`, `research/11-workflow-darkbrain-daily.md`, `research/12-workflow-aura-coach-daily.md`, `research/13-thomhouse-academy-analytics.md` và `research/14-github-zalo-bot-repos.md`. Tôi đọc phần đầu `research/01-knowledge-audit.md`.

Sau ba báo cáo ảnh menu, một lượt kiểm lại độc lập đã mở lại ảnh cho từng điểm lệch và ghi kết quả xác nhận. Lượt kiểm lại xét 56 điểm (27 ở menu da, 10 ở menu khỏe, 19 ở menu tóc và triệt lông), và xác nhận cả 56. Lượt kiểm lại cũng tìm ra vài điểm ghi chưa chính xác trong báo cáo gốc, ví dụ số dòng của bộ kiểm tra bản nháp và một quy tắc đổi số slide; các điểm đó không đổi kết luận nào.

Tôi tự mở lại các ảnh có con số quan trọng nhất, sau khi thu nhỏ bằng `sips -Z` hoặc cắt vùng chữ bằng `sips -c`, rồi đọc bằng mắt; tôi không chạy OCR. Các ảnh đó là: menu da `2.png`, `4.png`, `6.png`, `8.png`, `9.png` (ba vùng cắt), `10.png`, `12.png`, `14.png`, `20.png`; menu khỏe `5.png`, `17.png`; menu tóc `10.png`, `14.png`; menu triệt lông `2.png`. Mọi con số tôi đọc được đều khớp với báo cáo gốc và lượt kiểm lại. Các ảnh khác tôi dựa vào lượt kiểm lại.

Tôi đọc dòng 1–30 của `apps/server/src/checker/index.ts`, dòng 11 của `apps/server/test/core-checker.test.ts` và dòng đầu của `apps/server/src/seed-data.ts`. Tôi đọc cấu trúc và các mục liên quan của `data/services.json` và `data/business-facts.json` bằng `python3 -I`. Để kiểm khóa API, tôi chạy một script `python3 -I` chỉ in độ dài và mã băm SHA-256 của chuỗi khóa trong hai transcript, không in khóa.

Tôi không sửa `data/services.json`, không chạy `apps/server/scripts/gen-seed-data.mjs`, không gửi tin Zalo, không chạy lệnh `zalo-agent` nào và không truy cập mạng. Báo cáo này đã qua công cụ soát `lint_vi.py` nhưng chưa qua lượt rà độc lập bằng subagent, vì phiên này không có công cụ tạo subagent.

## Báo cáo dùng những thuật ngữ nào?

| Thuật ngữ | Nghĩa trong báo cáo này |
|---|---|
| catalog | file `data/services.json`, 23 dịch vụ và 33 mức giá, dựng ngày 07/11; chatbot lấy giá, thời lượng và các bước từ file này |
| bộ ảnh menu in | 57 ảnh PNG trong `sources/drive-resources/thomhouse-menu/`, sao từ thư mục menu trên Drive ngày 08/11: da 21 ảnh, khỏe 19, tóc 14, triệt lông 3 |
| bản chép tháng 5 | 5 file trong `sources/drive/raw-content/`, chữ do người soạn chép lại từ ảnh menu ngày 16/05/2026; catalog dựng từ các file này |
| trang landing page | file `/Users/luuphuc/Projects/thomhouse-academy-daily/source/landing-page.html`, bản lưu của một trang anh gửi phiên Claude trong `~/Projects/soraflow` chiều 08/11 |
| bộ kiểm tra bản nháp | code trong `apps/server/src/checker/index.ts`; server chạy code này trên mỗi bản nháp trước khi gửi để chặn từ cấm và con số tiền không khớp catalog |
| câu hứa tác dụng | câu trên menu nói dịch vụ làm da, cơ thể hay bệnh thay đổi ra sao; chatbot không được nói lại các câu này |
| câu cấm | câu hứa tác dụng đã được ghi vào trường `flagged_claims` của catalog để chatbot không nói lại |
| stack hiện tại | năm phần chạy trên máy Mac: listener `zalo-agent listen`, server chạy bằng `wrangler dev --local`, runner gọi `claude -p`, bridge gửi tin đã duyệt và console cho nhân viên |
| Workflow | công cụ của Claude Code chạy một file script để gọi nhiều agent con, mỗi agent con là một tiến trình Claude riêng làm một việc |
| phiên soraflow | phiên Claude Code chạy trong `~/Projects/soraflow`; phiên này đã mở cả ba phiên làm video hằng ngày |
| giá quy đổi theo API | chi phí app Claude ghi theo bảng giá API; trên gói subscription, con số này không bị tính tiền mà trừ vào giới hạn dùng hằng tuần |

## (a) Ảnh menu in khác catalog ở đâu?

### Catalog được dựng từ đâu, và vì sao lệch?

Catalog lấy giá từ bản chép tháng 5, không lấy trực tiếp từ ảnh. Bản chép menu da (`batch-04-skincare-menu.md`) ghi nguồn là 5 ảnh, ghi các slide không có header và địa chỉ, và tả bìa in "CHĂM SÓC DA MỤN". Cả 21 ảnh menu da trên Drive đều có header "thom house facial studio -Since 2019", có địa chỉ ở chân trang, và bìa in "Menu chăm sóc da". Từ các dấu hiệu đó, báo cáo menu da suy luận rằng catalog da được dựng từ một bộ ảnh khác bộ 21 ảnh này.

Bản chép menu tóc (`batch-05-hair-care-menu.md`) ghi nguồn là 9 ảnh, trong khi thư mục tóc trên Drive có 14 ảnh; năm slide cuối chưa từng được chép. Menu triệt lông không có bản chép nào. Menu khỏe được chép đủ 19 slide, nhưng người chép ghi sai hai tên dịch vụ.

Có dấu hiệu của một phiên bản menu da thứ ba. Ảnh `IMG_7874.jpg` trong bộ ảnh không gian chụp một điện thoại đang mở ảnh menu Gói Mụn 5 in 1, in "90-120 phút", "599.000 VND" và sáu bước. Tôi không biết phiên bản nào mới nhất, vì không ảnh nào ghi ngày và bản sao Drive không ghi ngày sửa của từng ảnh. Trang landing page khớp bộ 21 ảnh ở mọi điểm lệch về thời lượng, nên tôi suy luận bộ 21 ảnh là bản gần với menu đang bán hơn.

### Menu da có gì mà catalog chưa biết?

Bộ 21 ảnh có 10 dịch vụ với 13 mức giá; catalog có 5 dịch vụ da với 5 mức giá. Ba dịch vụ có ở cả hai nơi là Gói Mụn 5 in 1 và hai gói Xóa thâm quầng mắt. Giá của ba dịch vụ này khớp, còn thời lượng lệch như bảng ở phần đầu. Ảnh `9.png` còn in một quy trình 5 bước cho Xóa thâm quầng mắt mà catalog chưa có, nhưng ảnh không ghi quy trình đó thuộc gói nào.

Tám dịch vụ da có trên ảnh mà catalog chưa có:

| Dịch vụ in trên ảnh | Thời lượng in trên ảnh | Giá in trên ảnh | Ảnh |
|---|---|---|---|
| Detox da | 60–75 phút | 389.000đ | `2.png`, `3.png` |
| Massage mặt thư giãn | 60 phút | 289.000đ | `6.png`, `7.png` |
| Cấp dinh dưỡng cơ bản | 60–75 phút | 599.000đ | `10.png`, `11.png` |
| Cấp dinh dưỡng bằng công nghệ Plasma fusion | 60 phút | mức tinh chất 999.000đ; mức dịch chiết tế bào gốc từ 1.500.000đ đến 2.500.000đ | `12.png`, `13.png` |
| Lăn dưỡng | 60 phút | da cần làm dày sừng 1.500.000đ; giảm mụn, sẹo, nám, nếp nhăn 2.500.000đ | `14.png`, `15.png` |
| Inner Fill nâng cấp da | 60–75 phút | 6.500.000đ | `16.png`, `17.png` |
| Bio PDRN Nuôi da căng bóng | 60 phút | 2.500.000đ | `18.png`, `19.png` |
| Bio PDRN Nuôi da căng bóng full | 90 phút | 5.000.000đ | `20.png`, `21.png` |

Mức dịch chiết tế bào gốc của Plasma fusion in một khoảng giá, và ảnh không nói khi nào tính 1.500.000đ, khi nào tính 2.500.000đ. Vì vậy, tôi đề xuất nhân viên báo giá cụ thể cho mức này.

Hai dịch vụ da trong catalog không có trên ảnh nào: Gói Mụn Chuyên Sâu (75 phút, 389.000đ) và Chăm sóc da kích ứng (90 phút, 599.000đ). Detox da cùng giá với Gói Mụn Chuyên Sâu, và Cấp dinh dưỡng cơ bản cùng giá với Chăm sóc da kích ứng, nhưng quy trình đều khác. Vì vậy, ý cho rằng hai dịch vụ mới đã thay hai dịch vụ cũ chỉ là suy luận.

Cả 21 ảnh menu da in header "thom house facial studio", trong khi các menu khác và `data/business-facts.json` dùng tên "thom house healing studio". Cả 21 ảnh đều ghi phường Tân Hưng, không ảnh nào ghi Tân Kiểng. Mục địa chỉ trong `data/business-facts.json` đang ở trạng thái xung đột giữa hai phường, và bộ ảnh menu in là thêm một nguồn ghi Tân Hưng.

### Menu khỏe khớp catalog tới đâu?

Giá, thời lượng và khung giờ của cả 6 dịch vụ khỏe khớp ảnh: Ngừa đột quỵ 2.990.000đ trong 180 phút, ba dịch vụ 599.000đ trong 60 phút, Detox cơ thể 1.190.000đ trong 90 phút, Thải hàn giải cảm 1.200.000đ trong 90 phút. Không slide nào in khung giờ, nên giá trị khung giờ để trống trong catalog là đúng. Ảnh không có dịch vụ khỏe nào ngoài 6 dịch vụ này.

Hai tên dịch vụ lệch như bảng ở phần đầu. Cả hai lỗi tên đến từ bản chép tháng 5, và script dựng catalog chỉ chép lại. Ngoài ảnh, trang landing page còn ghi Giải mỏi đứng lâu giá 250.000đ trong 45 phút, khác ảnh in và catalog (599.000đ, 60 phút).

Slide quy trình của Giải mỏi đứng lâu (`16.png`) có tiêu đề "chăm sóc chân" nhưng in đúng từng chữ 6 bước của slide vai cổ (`13.png`) thuộc dịch vụ Thiếu máu não. Catalog chép đúng ảnh. Báo cáo menu khỏe suy luận rằng slide 16 in nhầm, vì slide giới thiệu `15.png` nói liệu trình tập trung vào chân; trang landing page cũng có 6 bước riêng cho chân. Tôi đề xuất chatbot chưa đọc các bước của dịch vụ này cho tới khi anh xác nhận.

Các lỗi gõ khác nằm trên chính ảnh, catalog không cần sửa: bìa in "Thải hàn giai cam", "Detox cơ thê" và "giãn tinh mạch"; bước quy trình in "toàn thán", "bộ nguyệt", "Đã thông cơ bó vai" và "Bày hàn qua lòng bàn chân". Trước khi chatbot đọc nguyên văn các bước có chữ "Đã thông" và "Bày", cần người biết quy trình xác nhận chữ đúng.

### Menu tóc và triệt lông thiếu những gì?

Ba dịch vụ tóc trong catalog khớp ảnh về tên, giá, thời lượng và khung giờ: Detox da đầu 40 phút, 139.000đ trước 20h30 và 159.000đ sau 20h30; Gội đầu thư giãn 50 phút, 199.000đ và 229.000đ; Chăm sóc nan tóc 70 phút, 349.000đ. Trong chín slide đã chép, chỉ một chữ bị chép sai: bước 9 của Chăm sóc nan tóc. Ảnh in chữ "nan" trên ba slide, nên catalog ghi "nan tóc" là đúng với ảnh; chữ "nang tóc" chỉ là đề xuất của người chép.

Năm slide chưa được chép chứa ba nhóm mục. Slide 10 đến 12 là Peel peptide da đầu, 299.000đ trong 15 phút, 3 bước; bước 3 in "Điện tim sát khuẩn", có thể là điện tím, nhưng đó là suy luận. Slide 13 là ba mặt nạ: mặt nạ tóc bồ kết 60.000đ, mặt nạ dẻo Hàn Quốc collagen cho mặt 50.000đ, mặt nạ phục hồi PDRN 90.000đ. Slide 14 là năm option: Detox da đầu 50.000đ, Massage mặt 10 phút +50.000đ, Massage tay 10 phút +50.000đ, Massage cổ, vai, gáy 30 phút +199.000đ, Massage chân 30 phút +199.000đ.

Option Detox da đầu giá 50.000đ trùng tên với dịch vụ Detox da đầu 40 phút giá 139.000đ. Nếu thêm option mà không đặt tên riêng, chatbot có thể báo nhầm 50.000đ cho dịch vụ 40 phút. Slide không nói option được cộng vào dịch vụ nào, và không nói mặt nạ là hàng bán lẻ hay bước thêm.

Menu triệt lông có một bảng giá 12 mức:

| Vùng in trên ảnh | Suất lẻ | Combo 20 buổi |
|---|---|---|
| Nách | 150.000đ | 2.000.000đ |
| Mép - Cằm - Trán | 100.000đ | 999.000đ |
| Viền bi - Ngực | 180.000đ | 1.800.000đ |
| Mặt - Tay - Cổ - Nữa Chân | 290.000đ | 2.900.000đ |
| Bikini - Chân - Bụng - Lưng | 340.000đ | 3.400.000đ |
| Full body | 1.800.000đ | 18.000.000đ |

Ảnh triệt lông không in thời lượng, khung giờ, tên máy, quy trình hay lưu ý trước và sau. Ảnh cũng không nói giá mỗi dòng tính cho từng vùng hay cho cả nhóm vùng. Năm dòng combo bằng đúng hoặc gần đúng 10 lần giá suất lẻ; dòng Nách bằng khoảng 13,3 lần. Đây là phép tính quan sát, chưa phải bằng chứng in sai, nên chatbot vẫn báo 2.000.000đ như ảnh cho tới khi anh xác nhận.

Slide thứ ba trong thư mục triệt lông là phiếu ghi thông tin khách, không phải menu. Phiếu có các ô dị ứng, mang thai, lực tay, tai nhạy cảm, vùng cần tránh, cào nhiều, gãi móng và gãi thịt. Các ô tai, cào và gãi không ăn khớp với triệt lông, và chưa ai biết phiếu dùng cho dịch vụ nào.

Tài liệu `sources/drive/knowledge-base/03-pricing-structure.md` dòng 91 ghi Detox da đầu 139.000đ là "Giá vào đầu rẻ nhất toàn studio"; câu đó không còn đúng, vì triệt lông suất lẻ vùng mép, cằm, trán chỉ 100.000đ.

### Dịch vụ nào trong catalog không có ảnh để đối chiếu?

Mười một dịch vụ trong catalog không có ảnh nào trong bộ ảnh in. Hai dịch vụ da đã nêu ở trên. Bốn dịch vụ thư giãn (Mở Vai – Nâng Mặt, Massage chân, Massage cổ, vai, gáy, Massage body thư giãn) không có slide bảng giá nào, dù thư mục tóc trên Drive mang tên "Thư giãn - Menu chăm sóc tóc". Chỉ hai mức 30 phút của Massage chân và Massage cổ, vai, gáy xuất hiện dưới dạng option. Năm dịch vụ phụ nữ không có thư mục ảnh nào.

Với chín dịch vụ thư giãn và phụ nữ, catalog chỉ dựa vào bản chép tháng 5, và nguồn để so còn lại chỉ là trang landing page. Theo báo cáo `research/13`, giá bốn dịch vụ thư giãn khớp trang landing page. Menu phụ nữ trên trang landing page thì khác catalog: trang có thêm Chăm sóc vòi trứng, Khai thông tam giác vàng, Bơm thảo dược và Túi ngâm mông thảo dược, và không còn Tiêu u – Thông kinh ngực. Tôi không có ảnh nào để kiểm các mục này.

### Câu hứa tác dụng nào mới xuất hiện, và bộ kiểm tra bản nháp hở ở đâu?

Câu nặng nhất trên ảnh là "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố", in trên hai ảnh Bio PDRN (`18.png`, `20.png`). Bộ kiểm tra bản nháp đã chặn chữ "điều trị", nên bản nháp chép nguyên câu này sẽ bị chặn. Ba câu khác chưa bị chặn. Câu quầng mắt in "gấp 10 lần", trong khi danh sách từ cấm ở dòng 12 chỉ có "gấp 20 lần". Ảnh `11.png` in "Lâm sàn trong 7 năm qua", và danh sách chưa có "lâm sàng"; bộ kiểm tra so chữ sau khi bỏ dấu, nên phải chặn cả cách viết thiếu chữ g. Ảnh `17.png` in "Inner fill hoạt chất theo chỉ định", và "chỉ định" là từ của ngành y.

Ở menu khỏe, 14 câu về bệnh hoặc cơ chế trong cơ thể chưa có trong danh sách câu cấm của catalog, ví dụ "Khi thận không được nuôi dưỡng đầy đủ, hàn tà dễ xâm nhập" và "đó không phải do vệ sinh, mà là dấu hiệu cơ thể đang ứ trệ". Ở menu tóc, ba câu đã chép nhưng chưa bị đánh dấu: "lành tính", "sợ gội đầu đêm ngấm lạnh sương ốm" và "Tóc yếu, thưa rụng". Các slide chưa chép còn nhiều câu hứa hơn, như "kích thích lưu thông máu", "cải thiện giấc ngủ", "Lành tính an toàn" và "Cho mọi loại da & tóc".

Khi đọc code, tôi thấy thêm một điểm. Danh sách từ cấm có chữ "thải độc", trong khi bước 7 của Ngừa đột quỵ là "Thải độc và phong tán hàn ra bàn chân". Nếu chatbot đọc nguyên văn các bước của dịch vụ này, bản nháp sẽ bị chặn. Tôi chỉ đọc code, chưa chạy bộ kiểm tra với các câu trên.

### File đề xuất sửa catalog gồm những gì?

File `data/services-corrections.json` chỉ chứa điểm lệch mà lượt kiểm lại đã xác nhận, cộng một câu cấm tôi tự đọc rõ trên vùng cắt của ảnh `9.png`. Mỗi điểm sửa ghi mã dịch vụ, trường, giá trị hiện tại, giá trị đề xuất, đường dẫn ảnh và ai đã kiểm. File có sáu phần:

- `corrections`: 22 điểm sửa. Năm điểm mức cao là ba thời lượng, quy trình Gói Mụn 5 in 1 và câu "gấp 10 lần". Mười bốn điểm còn lại gồm quy trình quầng mắt cho hai gói, hai tên dịch vụ khỏe, chữ "Xả", tám nhóm câu cấm bổ sung cho menu khỏe và menu tóc, và một câu cấm của gói quầng mắt cơ bản. Ba điểm chỉ lệch chữ hoa hoặc chữ "Gói" được đánh dấu là tùy chọn.
- `new_services`: 10 dịch vụ với 23 mức giá, 5 option và 3 mặt nạ, mỗi mục kèm các bước và câu cấm in trên ảnh.
- `confirmed_but_no_catalog_change`: 6 điểm mà catalog đã khớp ảnh, nhưng ảnh có lỗi hoặc đáng ngờ, như quy trình Giải mỏi đứng lâu.
- `catalog_services_without_any_menu_image`: 11 dịch vụ không có ảnh để đối chiếu.
- `checker_followups`: 5 việc trong code server, gồm ba điểm cần sửa trong bộ kiểm tra bản nháp, test dùng tên Diện chẩn ngừa đột quỵ và việc sinh lại file `seed-data.ts`.
- `business_facts_evidence`: 2 dữ kiện cho `data/business-facts.json`, là địa chỉ Tân Hưng và tên "facial studio".

Schema hiện tại của catalog chỉ có một số nguyên cho thời lượng và một số nguyên cho giá. Vì vậy, file đề xuất thêm hai cặp trường `duration_min`/`duration_max` và `price_min_vnd`/`price_max_vnd` cho các mục ghi khoảng. Trước khi áp dụng, cần sửa script dựng catalog hoặc code đọc catalog để hiểu các trường này; tôi chưa kiểm code server xử lý khoảng giá và thời lượng trống ra sao.

## (b) Không gian, thương hiệu và design system đang ở đâu?

thom house chưa có design system chính thức, ở dạng file hay artifact (trang web riêng tư trên claude.ai). Design system là bộ quy định chung về màu, font, logo, khoảng cách và giọng văn, để mọi ấn phẩm trông như của cùng một thương hiệu. Báo cáo `research/10` đã tìm trong danh sách artifact của tài khoản, trong `~/Projects/open-design` (154 design system), `darkbrain-studio`, `aura-coach-studio`, `truc-brain` và `thomhouse-analytics`, và không thấy design system nào của thom house.

Nguồn đầy đủ nhất là trang landing page. Dòng 12 của trang ghi toàn bộ màu, font, khoảng cách, bo góc và đường cong chuyển động thành biến CSS. Màu chính là nền tối `#13120e`, nền sáng `#f2ece4`, vàng kim `#cfae7b`, cùng năm màu cho năm menu: thư giãn `#7a6250`, khỏe `#6e7150`, phụ nữ `#8b5b5a`, da `#a8968a`, tóc `#a7844c`. Font tiêu đề là Cormorant Garamond, font chữ thường là Montserrat. Bộ công cụ video của dự án Thomhouse Academy đã chép lại các biến này, và file font đã có sẵn trong `~/Projects/thomhouse-academy-daily/assets/fonts/`.

Logo chỉ có một bản vẽ lại dạng SVG trong trang landing page: chữ thường "thom house", không chân, nét đậm. Ngoài đời, bảng hiệu, áo nhân viên, bảng wifi và tấm gỗ đều in hoa "THOM HOUSE". Tài liệu thương hiệu trên Drive quy định viết thường, nên tôi đề xuất chatbot viết "thom house". Màu cũng chưa thống nhất: menu da là `#a8968a` trên web, khoảng `#927c6c` trên menu in theo số đo của dự án Academy, còn tường thật đo được `#D2D1C8` và mảng tường màu nghệ `#BB7B3F`.

Mười hai ảnh không gian chỉ chụp tầng trệt: quầy lễ tân, sofa chờ, tủ khóa, cầu thang có chữ "Nail" và "Relax and Hair care", và mặt tiền kính. Không ảnh nào chụp phòng làm dịch vụ, giường, phòng tắm hay chỗ để xe. Vì vậy, chatbot được nói những gì thấy trong ảnh (có tủ khóa gửi đồ, có sofa chờ và nước uống, có wifi), và phải chuyển nhân viên khi khách hỏi phòng riêng, giường hay chỗ để xe. Chữ "Nail" trên tường là dữ kiện, nhưng catalog không có dịch vụ nail nào, nên chatbot không nên nói studio đang làm nail. Ảnh không có ngày chụp.

Bảng trên quầy và bàn chờ (`IMG_7518.jpg`) in mật khẩu wifi, tên chủ tài khoản, số tài khoản Techcombank và mã QR. Báo cáo không chép các giá trị này. Ảnh cho thấy studio nhận chuyển khoản, trong khi mục phương thức thanh toán trong `data/business-facts.json` vẫn trống.

File ghi âm giọng chị Thơm dài 31,04 giây chưa được chép lời, vì máy chưa có công cụ chuyển giọng nói thành chữ chạy local. Các script có sẵn trong dự án khác đều gửi âm thanh lên ElevenLabs, nên người viết báo cáo `research/10` không chạy các script đó. Giọng chị Thơm đã được nhân bản trên ElevenLabs trong dự án Academy, nhưng không file nào chép lại lời bản ghi.

Thư mục Drive tổng quan không đổi so với bản sao ngày 07/11: cả 32 file khớp ID, tên, dung lượng và ngày sửa. Hai file trên Drive chưa có trong bản sao là `.claude/settings.local.json` (293 byte) và `.DS_Store` (14.340 byte). Báo cáo `research/10` không tải hai file này, vì tải file cần anh đồng ý trong chat.

Trang landing page còn ghi những dữ kiện không rõ nguồn, như "Giờ đón khách: Từ 9h sáng", bốn hạng thẻ thành viên và menu phụ nữ mới. Không ai biết ai viết trang này, và artifact gốc không có trong danh sách artifact của tài khoản. Vì vậy, tôi đề xuất chỉ dùng trang landing page làm nguồn màu và font; dữ kiện kinh doanh trên trang chỉ dùng khi khớp một nguồn khác hoặc khi anh xác nhận.

## (c) Ba phiên video hằng ngày chạy thế nào, và thom house dùng lại được gì?

### Phiên darkbrain-daily làm gì, và chạy tốt tới đâu?

Phiên darkbrain-daily là một phiên Claude chạy lâu trong app Claude desktop, biến tin AI trong ngày thành video dọc tiếng Việt cho Dark Brain Studio. Phần việc nặng nằm trong Workflow script `.claude/workflows/darkbrain-daily-news.js`. Script chạy lần lượt các bước: chọn tin và thu giọng ElevenLabs, nghe lại bằng speech-to-text, vẽ hai storyboard, chấm storyboard, dựng bằng HyperFrames, kiểm từ ba góc độc lập (kỹ thuật, thương hiệu, nội dung), sửa, rồi xuất file. Theo code, script chạy tối đa ba vòng kiểm và hai lần sửa; video còn lỗi vẫn được xuất, tên file thêm đuôi `-chua-dat-kiem`.

Hai lịch tự chạy của app (scheduled task) bọc quanh script. Lịch thứ nhất làm 2 video lúc 06:00 và 21:00. Lịch thứ hai chạy mỗi 10 phút, mở một phiên Claude mới để xử lý nút Duyệt và nút Đã đăng mà anh bấm trên một artifact claude.ai.

Theo số đo trong báo cáo `research/11`, hai lịch này chạy kém. Lịch làm video chỉ tự ra đúng 1 video, ở lượt 06:00 ngày 07/11. Lượt 21:00 ngày 06/11 đứng chờ xin quyền, và lịch bị tắt lúc 16:57 ngày 07/11. Lịch xử lý nút chạy 213 lần; chỉ 16 lần có nút để xử lý, và 64 lần kết thúc bằng thông báo hết giới hạn tuần. Cả 213 lần tốn 80,81 USD giá quy đổi theo API, mỗi lần bình thường khoảng 0,54 USD. Nút Đã đăng chưa hoàn tất lần nào, vì máy chưa cài Google Drive for desktop. Khi app chuyển sang tài khoản claude.ai khác, artifact cũ và lịch cũ biến mất khỏi tài khoản mới, nên phiên phải tạo artifact mới ở link mới.

Phần lớn video của Dark Brain do chính phiên darkbrain-daily chạy Workflow script khi anh nhắn. Phiên darkbrain-daily ghi 772,09 USD giá quy đổi; 48 lần chạy Workflow gọi 650 agent con, cộng dồn 37,8 giờ.

### Phiên aura-coach-daily làm gì?

Phiên aura-coach-daily dựng video dọc ngắn dạy tiếng Anh cho app Aura Coach. Tên có chữ daily nhưng phiên không có lịch chạy; mỗi đợt bắt đầu từ tin nhắn của anh (41 tin) hoặc từ phiên soraflow. Phiên tự chọn chủ đề theo vòng luân phiên, viết kịch bản và thu giọng. Phần dựng, trộn âm, quét chữ chồng nhau và render do agent làm qua Workflow (20 lần gọi, 308 agent). Từ 05/11 đến 08/11, phiên xuất 33 video vào `~/Downloads/aura-coach-resources/daily/`.

Anh duyệt bằng nút trên một trang claude.ai có cơ sở dữ liệu riêng. Phiên chỉ đọc nút bấm khi đang mở và tự truy vấn. Từ 08/11, phiên chạy bằng tài khoản khác và không đọc hay ghi được trang đó nữa. Bước đưa video lên Drive chưa chạy lần nào.

Đến trưa 06/11, phiên chạy ba agent kiểm và tối đa ba vòng sửa trước khi gửi anh. Anh phản đối vì tốn thời gian và credit, nên phiên bỏ bước kiểm và gửi bản xem trước ngay khi render xong. Bản ghi chi phí cuối là 1.408,02 USD giá quy đổi; tổng credit ElevenLabs ghi trong 35 file là 8.002. Lúc 18:31 ngày 08/11, máy đo được load average khoảng 520, do nhiều trình duyệt headless và ffmpeg của Dark Brain chạy cùng lúc.

### Phiên thomhouse-academy-daily làm gì?

Phiên thomhouse-academy-daily làm sáu video kiến thức về da mặt cho học viên của thom house, mỗi video một kiểu hình. Kiến thức da lấy từ nguồn y khoa bên ngoài như AAD, NHS và DermNet, không lấy từ kho kiến thức của studio. Giọng đọc là giọng nhân bản của chị Thơm, tăng tốc 1,3 lần. Trước khi thu giọng, phiên chạy `kit/claims.mjs` để dò lời hứa y tế, từ bán hàng và giá trong lời thoại.

Video không nêu dịch vụ hay giá, nên không mâu thuẫn với catalog. Phiên chưa có lịch chạy. Lúc 19:12 ngày 08/11, phiên vẫn đang chạy: video 1 đã render, chưa video nào được xuất cho anh duyệt. Tin nhắn sửa bản giao việc mà phiên soraflow gửi lúc 16:02 không có trong transcript của phiên này.

Cả ba phiên được phiên soraflow mở theo cùng một khuôn. Phiên soraflow chạy một Workflow nghiên cứu, viết ba tài liệu (báo cáo tiếng Việt, danh mục kiểu hình, bản giao việc tiếng Anh) và cho một agent rà độc lập. Sau đó phiên soraflow mở phiên mới kèm danh sách file phải đọc theo thứ tự, rồi gửi tiếp các lỗi lượt rà tìm ra. Chỉ Dark Brain có lịch chạy.

### Chatbot thom house nên lấy gì, và không nên lấy gì?

Năm cách làm dùng lại được cho chatbot:

- Mỗi bản nháp câu trả lời có id cố định và trạng thái rõ (chờ duyệt, đã duyệt, đã gửi, gửi lỗi), ghi kèm số phiên bản để không đè lên thao tác mới hơn, và có nút hoàn tác trước khi gửi. Trạng thái nằm trong cơ sở dữ liệu của server và hiện trên console.
- Khi nhân viên bấm duyệt, code của server đưa tin vào hàng gửi ngay. Việc này không chờ một phiên Claude chạy theo lịch như Dark Brain, cũng không chờ một phiên đang mở tự truy vấn như Aura.
- Luật của chủ doanh nghiệp được ghi thành file, mỗi luật kèm ngày, lý do và cách áp dụng, theo mẫu file nhớ của Aura. Một test kiểm prompt của runner có nạp đủ các luật đó.
- Bản nháp chỉ qua một lượt kiểm tự động rồi tới người duyệt. Phần kiểm được bằng code (giá, tên dịch vụ, câu cấm) đặt trong server; phần cần đọc hiểu để nhân viên duyệt.
- Danh sách câu cấm được kiểm trong code trước khi gửi. Bộ biểu thức trong `~/Projects/thomhouse-academy-daily/kit/claims.mjs` dùng lại được, trừ nhóm chặn giá và từ đặt lịch, vì chatbot phải báo giá và nhận đặt lịch.

Bốn cơ chế không nên dùng cho chatbot. Thứ nhất là để một phiên Claude chạy mỗi 10 phút chỉ để xử lý nút bấm: khách chờ tới 10 phút, mỗi lần tốn giới hạn dùng, và lịch thất bại im lặng khi hết giới hạn. Thứ hai là đặt trạng thái hay lịch chạy của bot vào artifact hoặc scheduled task của claude.ai. Thứ ba là cho nhiều agent chạy trong đường trả lời khách. Thứ tư là nhận lệnh qua tin nhắn giữa các phiên, vì cách đó không để lại lịch sử duyệt mà người khác kiểm được.

Nếu sau này thom house làm video giới thiệu dịch vụ, bộ công cụ của Aura và Dark Brain dùng lại được: HyperFrames, giọng tiếng Việt ElevenLabs tăng tốc 1,3 lần, bước nghe lại bằng speech-to-text, và cách xuất bản nháp ra thư mục theo ngày để người duyệt trước khi đăng. Điểm yếu: mỗi video tốn từ 43 đến 528 credit ElevenLabs ở Aura, khoảng 1.500 đến 2.000 credit ở Dark Brain, và một đến ba giờ máy. Lời thoại về dịch vụ phải qua danh sách câu cấm trước khi thu giọng.

### Các phiên video tạo rủi ro gì cho chatbot?

Rủi ro thứ nhất là chung tài khoản Claude. Pool tài khoản của bot đăng ký tài khoản mặc định của máy ở ưu tiên 1, và báo cáo về Aura suy luận rằng tài khoản này có thể trùng tài khoản phiên Aura đang dùng. Nếu đúng, một đợt dựng video lớn có thể làm bot hết giới hạn tuần giữa lúc khách đang nhắn.

Rủi ro thứ hai là chung máy. Bot chạy local trên cùng chiếc Mac với các phiên video, và load average khoảng 520 ngày 08/11 cho thấy máy có thể quá tải. Tôi đề xuất các phiên video render ngoài giờ khách hay nhắn.

Rủi ro thứ ba là lịch chạy đứng chờ xin quyền mà không báo ai, như lượt 21:00 của Dark Brain. Chưa ai kiểm các cờ quyền mà runner truyền cho `claude -p`, nên chưa thể khẳng định runner sẽ không dừng lại chờ duyệt quyền.

Rủi ro thứ tư là khóa API trong transcript. Hai báo cáo cùng ghi rằng tối 05/11 anh dán một khóa API Anthropic vào chat. Tôi đo được cùng một chuỗi khóa (so bằng mã băm, dài 106 ký tự) xuất hiện 5 lần trong transcript Dark Brain và 5 lần trong transcript Aura. Hai phiên đều từ chối dùng khóa, nhưng khóa vẫn nằm trên đĩa.

## (d) Có repo GitHub nào nên thay stack hiện tại không?

Không repo nào nên thay stack hiện tại. Repo `aizaloapp/zalo-flow` mà anh gửi là một app chat và CRM hoàn chỉnh cho Zalo cá nhân, nhưng thiếu đúng các phần đã chốt cho chatbot thom house. Server của zalo-flow không có hàng chờ để nhân viên duyệt câu trả lời trước khi gửi, không gửi tin xin đồng ý, không gọi được `claude -p` và không kiểm câu trả lời theo bảng giá. zalo-flow có cơ chế nhân viên tiếp quản khi chủ tự gõ (dừng bot 15 phút), nhưng stack hiện tại cũng có cơ chế này.

Báo cáo `research/14` đọc mã zalo-flow ở commit `0a0e985` và thấy các vấn đề bảo mật sau; báo cáo chưa chạy thử để xác nhận. Hai đường webhook `/api/webhook/generic` và `/api/webhook/chatwoot` gửi tin ra Zalo mà không kiểm token, kể cả khi đã đặt `ADMIN_API_TOKEN`. Cấu hình mặc định cho server nghe ở `0.0.0.0` và để trống `ADMIN_API_TOKEN`; khi token trống, mọi request đều được cho qua. Với cấu hình đó, máy khác cùng mạng Wi-Fi đọc được hội thoại và gửi tin bằng tài khoản Zalo của anh. Repo còn có khóa mã hóa dự phòng viết cứng trong code, nút cập nhật chạy `git pull` rồi `npm install`, và lệnh lint chỉ in dòng báo đã qua.

zalo-flow mới hai tháng tuổi, 160 commit, một tác giả, 18 sao, dùng `zca-js` 2.1.2. Giấy phép MIT kèm Commons Clause cho phép dùng local phi thương mại.

Bốn repo khác đã được clone và đọc. `vuhai2002/zalo-agent` (MIT) có mã viết cẩn thận nhất, nhưng là trợ lý cá nhân trả lời thẳng, không qua duyệt. `cuongdev/hermes-zalo-plugin` (MIT) là cầu nối nhỏ giữ một phiên Zalo, mặc định chỉ nghe ở `127.0.0.1`. `monas-team/zaloclaw` phải chạy kèm gateway OpenClaw, và agent gọi được hành động tự cập nhật. `babyvibe/deplao-builder` là app desktop CRM rất lớn, bản build production gửi UID Zalo và mã máy về máy chủ của tác giả mỗi ngày.

Hai repo không được clone cũng đáng biết. `dennyducnguyen/penai` có nhiều tính năng giống chatbot thom house nhất, nhưng giấy phép riêng buộc phải có văn bản cho phép của tác giả khi dùng để chăm sóc khách trong kinh doanh. `zainkalkhan/zalo-personal` có dấu hiệu là repo mồi phát tán file zip; báo cáo không tải file đó.

Tôi đề xuất giữ stack hiện tại, lấy năm ý tưởng nhỏ và giữ `hermes-zalo-plugin` làm phương án dự phòng cho riêng phần engine. Năm ý tưởng là: lọc tin hệ thống về kết bạn, dặn nhân viên không mở Zalo Web khi bot chạy, chuyển Markdown sang định dạng chữ của Zalo, chia quyền theo nhóm hành động, và viết test kiểm địa chỉ server nghe. Điểm yếu của đề xuất: stack hiện tại chưa gửi tin nào qua Zalo thật, nên tôi đang so một hệ thống chưa thử thật với các repo cũng chưa ai chạy. Mọi lựa chọn, kể cả engine hiện tại, đều dựa vào `zca-js` không chính thức, nên rủi ro tài khoản Zalo bị khóa không đổi dù anh chọn repo nào.

Có hai việc nên kiểm trong lần thử đầu với Zalo thật. Việc đầu là xem listener có chuyển câu hệ thống như "đã trở thành bạn bè" thành tin nhắn không; nếu có, server sẽ gửi tin xin đồng ý cho người chưa nhắn gì. Việc sau là xem Zalo có coi việc mỗi lệnh `zalo-agent msg send` đăng nhập lại là bất thường không; nếu có, cần đổi sang engine giữ phiên liên tục.

## (e) Còn thiếu gì, và lượt nghiên cứu này chưa kiểm được gì?

### Những thông tin kinh doanh nào vẫn chưa có nguồn?

Sau lượt nghiên cứu này, các mục sau vẫn chưa có nguồn nào: số hotline, Zalo của studio, URL Fanpage, giờ đóng cửa, ngày nghỉ, chính sách hủy lịch, đổi lịch, đến trễ, đặt cọc, hoàn tiền, thẻ quà tặng, hóa đơn, nhân viên nam hay nữ, có phục vụ khách nam và trẻ em không, chỗ để xe, phòng riêng và giường. Phương thức thanh toán chỉ có dấu hiệu chuyển khoản Techcombank trên bảng ở quầy. Giờ mở cửa chỉ có câu "Từ 9h sáng" trên trang landing page. Bốn hạng thẻ thành viên trên trang landing page có khoảng mệnh giá trùng nhau ở mức 10.000.000đ và chưa có điều kiện chi tiết. Tên trợ lý và cách xưng hô của chatbot vẫn chờ anh quyết.

### Lượt nghiên cứu này chưa kiểm được những gì?

Tôi biết lượt nghiên cứu này chưa làm hoặc chưa kiểm được các việc sau.

- Theo phần tóm tắt gửi kèm từng báo cáo, sáu trong tám báo cáo nghiên cứu chưa qua lượt rà độc lập bằng subagent theo skill viết tiếng Việt, vì phiên viết không có công cụ tạo subagent; tóm tắt của hai báo cáo còn lại (menu khỏe và phiên Aura) không nói. Báo cáo này cũng chưa qua lượt rà đó, chỉ qua công cụ soát `lint_vi.py` và lượt tự đọc lại.
- Cả 57 ảnh menu đều được mở, và không chữ số nào phải đoán. Tuy vậy, mọi ảnh được đọc bằng mắt, không qua OCR; tôi tự mở lại 14 ảnh, các ảnh còn lại dựa vào ba báo cáo đối chiếu ảnh và lượt kiểm lại.
- Bộ ảnh in không có menu thư giãn và menu phụ nữ, nên 9 dịch vụ của catalog không đối chiếu được với ảnh. Bộ 5 ảnh da mà bản chép tháng 5 đã dùng chưa được tìm thấy.
- Không ảnh menu nào ghi ngày, và bản sao Drive không ghi ngày sửa của từng ảnh. Chưa ai lấy ngày sửa trên Drive, nên chưa biết phiên bản menu nào mới nhất.
- File ghi âm 31,04 giây của chị Thơm chưa được chép lời.
- Hai file trên Drive chưa tải: `.claude/settings.local.json` và `.DS_Store`. Chưa ai kiểm lại danh sách file của thư mục tài nguyên trên Drive ngoài bản sao đã có.
- Link Google Maps, beacons.ai và trang Fanpage chưa được mở, vì nhiệm vụ không cho truy cập mạng.
- Nguồn gốc trang landing page chưa rõ; artifact gốc và design system mà trang nhắc tới không có trong tài khoản. Mọi dữ kiện chỉ có trên trang này, như giá 250.000đ của Giải mỏi đứng lâu và menu phụ nữ mới, chưa được kiểm.
- Transcript chưa đọc hết. Các báo cáo không đọc transcript agent con của Aura (1,7 GB) và của Dark Brain (847 file, chỉ cộng token). Transcript soraflow chỉ được đọc từng phần. Phiên thomhouse-academy-daily vẫn đang chạy, và trạng thái ghi trong báo cáo là trạng thái lúc 19:12. Thư mục `~/Documents/ChatGPT/lulu-thomhouse` không được đọc lại.
- Hai artifact để anh bấm duyệt video của Dark Brain và Aura chưa được mở trong trình duyệt, và kho dữ liệu của các trang đó chưa được đọc. Các tài liệu dựng video `DESIGN-VIDEO.vi.md`, `SPEC.md` và kiểu dựng trong `kit/styles/` của Dark Brain chưa được đọc.
- Chưa chạy bộ kiểm tra bản nháp với các câu cấm mới, chưa chạy `gen-seed-data.mjs`, chưa chạy `claude_pool.py status` và chưa kiểm cờ quyền mà runner truyền cho `claude -p`.
- Các lỗ hổng của zalo-flow là suy luận từ đọc mã, chưa chạy thử. Chưa ai đọc mã OpenClaw để biết OpenClaw có chặn hành động tự cập nhật của zaloclaw không.
- Chưa ai tra quy định giấy phép cho máy IPL, mặt nạ Carboxy, Inner Fill và triệt lông. Việc từng câu hứa có vi phạm luật quảng cáo hay không là suy luận, luật sư cần xem.
- Chưa thử với Zalo thật: tin hệ thống về kết bạn và việc đăng nhập lại ở mỗi lần gửi.
- Font serif trên menu in chưa được nhận ra tên, và tỉ lệ tương phản màu chưa được tính lại.
- Chưa ai giải thích vì sao số credit ElevenLabs trên tài khoản lệch với số ghi trong `credits.json` của từng video.

## Nói ngắn gọn nhất

Catalog của chatbot đang theo menu chép tháng 5, còn bộ 57 ảnh menu in trên Drive là một bản khác; tôi suy luận bộ ảnh in là bản đang bán, vì trang landing page khớp bộ ảnh này. Giá của mọi dịch vụ có ở cả hai nơi đều khớp, nhưng catalog sai thời lượng ba dịch vụ da, sai quy trình Gói Mụn 5 in 1, sai tên hai dịch vụ khỏe, và thiếu 10 dịch vụ với 23 mức giá, trong đó có cả menu triệt lông; tôi đã ghi mọi điểm sửa đã xác nhận vào `data/services-corrections.json` và chưa sửa catalog. Trước khi áp dụng, anh cần xác nhận bộ ảnh in là menu đang bán, chốt thời lượng Gói Mụn 5 in 1, quyết có báo giá các dịch vụ có bước IPL và Inner Fill không, và cho chặn mọi con số "gấp N lần". Về phần còn lại, không repo GitHub nào nên thay stack hiện tại, thom house chưa có design system ngoài trang landing page, và bài học từ ba phiên video là giữ trạng thái duyệt trong server của mình, tách tài khoản Claude của bot khỏi các phiên video, và thu hồi khóa API đang nằm trong hai transcript.

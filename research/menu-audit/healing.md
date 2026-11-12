# Đối chiếu ảnh gốc menu khỏe với catalog chatbot

Ngày đối chiếu: 2026-11-08. Thư mục ảnh: `sources/drive-resources/thomhouse-menu/healing-giup-ban-khoe/`, tên gốc trên Drive là *Healing - Menu giúp bạn khỏe*, gồm 19 ảnh PNG cỡ 1536x2048. Tôi so ảnh với `data/services.json` (nhóm `health`, 6 dịch vụ) và với văn bản chép menu `sources/drive/raw-content/batch-02-health-menu.md`.

## Phần anh cần duyệt

Giá, thời lượng và khung giờ của cả 6 dịch vụ menu khỏe trong `data/services.json` khớp với ảnh gốc. Mỗi dịch vụ có đúng một mức giá trên ảnh, và không slide nào in khung giờ, nên giá trị `time_window` = `null` trong catalog là đúng. Không có dịch vụ nào có trên ảnh mà thiếu trong catalog, và cũng không có dịch vụ nhóm `health` nào trong catalog mà thiếu trên ảnh.

Hai tên dịch vụ trong catalog không phải tên in trên ảnh gốc:

- Slide bìa (17.png), slide giới thiệu (18.png) và slide quy trình (19.png) đều ghi *Ngừa đột quỵ*. Catalog ghi *Diện chẩn ngừa đột quỵ*. Không slide nào trong thư mục này có chữ *Diện chẩn* trong tên dịch vụ.
- Slide bìa (5.png), tiêu đề slide giới thiệu (6.png) và tiêu đề slide quy trình (7.png) ghi *Detox cơ thể*. Catalog ghi *Detox mùi cơ thể*. Cụm *Detox mùi cơ thể* chỉ xuất hiện hai lần, trong thân bài của slide giới thiệu 6.png.

Cả hai tên lệch đều có từ văn bản chép menu (`batch-02-health-menu.md` dòng 56–57 và 257–258); script dựng catalog chỉ chép lại văn bản đó.

Anh cần quyết hai việc.

1. Tên hiển thị của hai dịch vụ trên. Tôi đề xuất đổi `name_vi` theo đúng chữ in trên bìa (*Ngừa đột quỵ*, *Detox cơ thể*) và ghi tên cũ vào `notes_vi`, vì khách và tài liệu tổng hợp đang dùng tên cũ. Phương án này có ba điểm yếu. Thứ nhất, *Ngừa đột quỵ* vẫn là tên hứa ngăn một bệnh, nên đổi theo ảnh không làm tên an toàn hơn; giữ hay đổi hẳn tên vẫn là quyết định của chủ doanh nghiệp, như báo cáo `research/01-knowledge-audit.md` đã nêu. Thứ hai, catalog chưa có trường tên gọi khác, nên bot chỉ nhận ra tên cũ khi prompt hoặc code có đọc `notes_vi`. Thứ ba, sau khi sửa `data/services.json` phải sinh lại `apps/server/src/seed-data.ts` (file này sinh tự động từ `data/services.json`) và sửa test `apps/server/test/core-checker.test.ts` dòng 11, nơi đang dùng chuỗi *Diện chẩn ngừa đột quỵ*.
2. Quy trình của *Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch*. Slide quy trình 16.png có tiêu đề *chăm sóc chân*, nhưng 6 bước trên slide này giống từng chữ với slide quy trình *chăm sóc vai cổ chuyên sâu* (13.png) của dịch vụ Thiếu máu não, và chỉ bước đầu nói về chân. Tôi suy ra slide 16.png có thể đã chép nhầm danh sách bước của slide 13.png; căn cứ là slide giới thiệu 15.png mô tả liệu trình tập trung vào chân (vuốt dịch, làm ấm bàn chân). Catalog chép đúng ảnh, nên nếu có lỗi thì lỗi nằm trên ảnh. Tôi đề xuất bot chưa đọc 6 bước này khi khách hỏi về Giải mỏi đứng lâu, cho tới khi chủ tiệm xác nhận quy trình thật. Điểm yếu: trong thời gian chờ, bot trả lời thiếu phần quy trình của một dịch vụ.

Ngoài hai việc trên, tôi đếm được 14 câu về sức khỏe in trên ảnh mà `flagged_claims` trong catalog chưa ghi (bảng ở mục cuối). Phần lớn là câu giải thích nguyên nhân bệnh, ví dụ câu nói thận không được nuôi dưỡng nên sinh đau lưng, hoặc câu nói mùi cơ thể không phải do vệ sinh.

## Tôi đã đọc và chạy gì

- Mở cả 19 ảnh bằng công cụ Read và đọc bằng mắt; tôi không chạy OCR. Công cụ thu nhỏ ảnh khi hiển thị, nên tôi cắt và phóng to 6 vùng bằng `sips -c` để kiểm dấu: tiêu đề bìa của 2.png, 5.png, 11.png và 14.png, vùng giá của 2.png và bước 3 của 7.png.
- Đọc `data/services.json` bằng `python3 -I` và in đủ trường của 6 dịch vụ nhóm `health`. Đọc toàn bộ `batch-02-health-menu.md`, `sources/drive-resources/INDEX.md` và phần đầu cùng các dòng về menu khỏe của `research/01-knowledge-audit.md`.
- Tìm các chuỗi *Diện chẩn ngừa đột quỵ*, *Detox cơ thể* và *Detox mùi cơ thể* trong `sources/`, `research/`, `data/`, `apps/` và `scripts/` bằng `grep`. Ngoài báo cáo này, chuỗi *Detox cơ thể* không có trong file văn bản nào của dự án (lệnh `grep -rIl` trên năm thư mục trên, bỏ qua `node_modules`); chuỗi *Diện chẩn ngừa đột quỵ* có trong nhiều tài liệu tổng hợp, và các tài liệu này đều viết lại từ văn bản chép menu.
- So địa chỉ và năm thành lập in trên ảnh với `data/business-facts.json`.

Mọi giá và thời lượng trên ảnh đều đọc rõ; không có chữ số nào tôi phải đoán.

## File ảnh nào ứng với slide nào trong văn bản chép?

Thứ tự file trên Drive ngược với thứ tự trong văn bản chép: ảnh `N.png` ứng với *Slide (20 − N)* trong `batch-02-health-menu.md`. Ví dụ, 1.png là bìa nhóm (Slide 19 trong văn bản chép), còn 19.png là quy trình Ngừa đột quỵ (Slide 1). Trường `source.line` trong catalog trỏ vào văn bản chép, nên người kiểm lại bằng ảnh cần đổi số theo quy tắc này.

Trên Drive, mỗi dịch vụ có ba ảnh liền nhau theo thứ tự: bìa có giá, slide giới thiệu, slide quy trình.

## Mỗi nhóm slide in gì và catalog ghi gì?

Cột *Khớp* xét tên, thời lượng, giá và khung giờ. Trong tên và trong bước quy trình, ảnh dùng dấu gạch ngắn `-`, còn catalog dùng gạch `–`; tôi không tính khác biệt về dấu gạch là lệch.

### Bìa nhóm (1.png)

| Ảnh | Loại slide | Chữ in trên ảnh | Giá trị trong dự án | Khớp |
|---|---|---|---|---|
| 1.png | Bìa nhóm, không có dịch vụ và không có giá | "Menu giúp bạn khỏe"; "72 đường số 37 , phường Tân Hưng quận 7"; "thom house healing studio - Since 2019"; "Fanpage: Thơm House" | Catalog xếp 6 dịch vụ vào nhóm `health`; địa chỉ và năm 2019 khớp mục `address` và `founded_year` trong `data/business-facts.json` | Có |

Cả 19 ảnh đều in cùng địa chỉ *72 đường số 37, phường Tân Hưng quận 7* ở chân trang.

### Thải hàn giải cảm (2.png – 4.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`thai-han-giai-cam`) | Khớp |
|---|---|---|---|---|
| 2.png | Bìa | Tên in "Thải hàn giai cam", dòng hai thiếu dấu hỏi ở *giải* và *cảm*; "1,200,000 VNĐ"; "Thời gian: 90 phút"; không in khung giờ | *Thải hàn giải cảm*; 90 phút; 1.200.000 đ; `time_window` = `null` | Giá, thời lượng, khung giờ khớp; tên trên bìa sai dấu, catalog viết đúng |
| 3.png | Quy trình | Tiêu đề "Quy trình "thải hàn giải cảm" của chúng mình sẽ như sau:"; 6 bước | `process_steps_vi` có 6 bước giống ảnh | Có |
| 4.png | Giới thiệu | Tiêu đề "Thải hàn – giải cảm / Chăm sóc cơ thể từ gốc"; thân bài nhắc người sáng lập *Thơm* | Tên và mô tả ngắn khớp | Có |

### Detox cơ thể (5.png – 7.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`detox-mui-co-the`) | Khớp |
|---|---|---|---|---|
| 5.png | Bìa | Tên in "Detox cơ thê", chữ cuối thiếu dấu hỏi, tức *Detox cơ thể*; "1,190,000 VNĐ"; "Thời gian: 90 phút"; không in khung giờ | *Detox mùi cơ thể*; 90 phút; 1.190.000 đ; `time_window` = `null` | Giá, thời lượng, khung giờ khớp; tên không khớp |
| 6.png | Giới thiệu | Tiêu đề "Detox cơ thể / Chăm sóc từ bên trong"; thân bài viết "Liệu trình Detox mùi cơ thể…" và câu kết "Detox mùi cơ thể không phải là che mùi…" | Tên *Detox mùi cơ thể* | Tên ở tiêu đề không khớp |
| 7.png | Quy trình | Tiêu đề "Quy trình "detox cơ thể" của chúng mình sẽ như sau:"; 5 bước; bước 3 in "Vỗ hạch bạch huyết toàn thán" | 5 bước; bước 3 ghi "toàn thân" | Bước khớp; catalog đã sửa lỗi gõ mà không ghi chú |

### Đau thắt lưng mỏi gối (8.png – 10.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`dau-that-lung-moi-goi`) | Khớp |
|---|---|---|---|---|
| 8.png | Bìa | "Đau thắt lưng mỏi gối"; "599,000 VNĐ"; "Thời gian: 60 phút"; không in khung giờ | *Đau thắt lưng mỏi gối*; 60 phút; 599.000 đ; `time_window` = `null` | Có |
| 9.png | Giới thiệu | Tiêu đề "Đau thắt lưng, mỏi gối / Chăm sóc từ bên trong"; thân bài gợi ý khách tham khảo thêm liệu trình *Thải hàn* | Tên khớp | Có |
| 10.png | Quy trình | Tiêu đề "Quy trình "đau thắt lưng, mỏi gối" của chúng mình sẽ như sau:"; 5 bước; bước 3 in "Bấm những bộ nguyệt chăm sóc thận" | 5 bước giống ảnh; catalog giữ chữ *nguyệt* và ghi chú trong `conflicts` | Có |

### Thiếu máu não – tê tay, căng thẳng khó ngủ (11.png – 13.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`thieu-mau-nao`) | Khớp |
|---|---|---|---|---|
| 11.png | Bìa | "Thiếu máu não - tê tay, căng thẳng khó ngủ"; "599,000 VNĐ"; "Thời gian: 60 phút"; không in khung giờ | *Thiếu máu não – tê tay, căng thẳng khó ngủ*; 60 phút; 599.000 đ; `time_window` = `null` | Có |
| 12.png | Giới thiệu | Tiêu đề "Thiếu máu não – tê tay – căng thẳng, khó ngủ / Chăm sóc vai cổ chuyên sâu" | Mô tả ngắn có nhắc tên phụ *chăm sóc vai cổ chuyên sâu* | Có |
| 13.png | Quy trình | Tiêu đề "Quy trình "chăm sóc vai cổ chuyên sâu" của chúng mình sẽ như sau:"; 6 bước | 6 bước giống ảnh | Có |

### Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch (14.png – 16.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`giai-moi-dung-lau`) | Khớp |
|---|---|---|---|---|
| 14.png | Bìa | "Giải mỏi đứng lâu - chăm sóc chân giãn tinh mạch", chữ *tĩnh* thiếu dấu ngã; "599,000 VNĐ"; "Thời gian: 60 phút"; không in khung giờ | *Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch*; 60 phút; 599.000 đ; `time_window` = `null` | Giá, thời lượng, khung giờ khớp; tên trên bìa sai dấu, catalog viết đúng |
| 15.png | Giới thiệu | Tiêu đề "Giải mỏi đứng lâu / Chăm sóc chân giãn tĩnh mạch" | Tên khớp | Có |
| 16.png | Quy trình | Tiêu đề "Quy trình "chăm sóc chân" của chúng mình sẽ như sau:"; 6 bước giống từng chữ với 13.png | 6 bước giống ảnh | Catalog khớp ảnh; nội dung ảnh đáng ngờ, xem mục 3 phần sau |

### Ngừa đột quỵ (17.png – 19.png)

| Ảnh | Loại slide | Tên, thời lượng và giá in trên ảnh | Giá trị trong catalog (`dien-chan-ngua-dot-quy`) | Khớp |
|---|---|---|---|---|
| 17.png | Bìa | "Ngừa đột quỵ"; "2,990,000 VNĐ"; "Thời gian: 180 phút"; không in khung giờ | *Diện chẩn ngừa đột quỵ*; 180 phút; 2.990.000 đ; `time_window` = `null` | Giá, thời lượng, khung giờ khớp; tên không khớp |
| 18.png | Giới thiệu | Tiêu đề "Ngừa đột quỵ / Chăm sóc lưu thông và phòng ngừa từ sớm"; thân bài viết "Liệu trình Ngừa đột quỵ tại thom house…" | Tên *Diện chẩn ngừa đột quỵ* | Tên không khớp |
| 19.png | Quy trình | Tiêu đề "Quy trình "ngừa đột quỵ" của chúng mình sẽ như sau:"; 8 bước | 8 bước giống ảnh | Bước khớp; tên ở tiêu đề không khớp |

## Các bước quy trình in trên ảnh

Tôi chép nguyên văn từ ảnh, giữ cả lỗi gõ. Mọi danh sách giống `process_steps_vi` trong catalog, trừ bước 3 của Detox cơ thể (ghi trong ngoặc ở bước đó).

Ngừa đột quỵ, 8 bước (19.png):

1. Diện chẩn mặt - ấn huyệt xoá tắt nghẽn mạch máu.
2. Khai thông phần đầu, cổ, ngực, bụng.
3. Chải, day, hơ ngải bộ huyệt chống đột quỵ trước & sau .
4. Trục Hàn khí tích tụ ở các cơ, khớp, ổ bụng.
5. Massage cân bằng âm dương toàn thân.
6. Chải dịch bằng dụng cụ chuyên dụng cho toàn thân
7. Thải độc và phong tán hàn ra bàn chân
8. Vỗ hạch bạch huyết, hơ ngải dẫn lửa làm ấm cơ thể.

Chăm sóc vai cổ chuyên sâu (13.png, dịch vụ Thiếu máu não) và chăm sóc chân (16.png, dịch vụ Giải mỏi đứng lâu), cùng 6 bước:

1. Massage chân cơ bản, kiểm tra điểm đau
2. Massage lưng cơ bản. Đã thông cơ bó vai, cổ.
3. Bấm huyệt vai cổ
4. Chăm sóc từng bên tay-đầu-cổ
5. Lăn dụng cụ, hơ ngải cứu
6. Massage, diện chẩn mặt dụng cụ đồng ứng vai cổ.

Đau thắt lưng mỏi gối, 5 bước (10.png):

1. Ấn huyệt chân bổ khí thận, massage chân thải dịch phù nề.
2. Massage lưng cơ bản, giải các nhóm cơ thắt eo, cơ mông, cơ hông
3. Bấm những bộ nguyệt chăm sóc thận
4. Massage, diện chẩn mặt bộ bổ thận.
5. Khai thông đầu, ấn huyệt tay.

Detox cơ thể, 5 bước (7.png):

1. Ứng dụng massage cân bằng âm dương
2. Thải dịch bằng dụng cụ chuyên dụng cho toàn thân
3. Vỗ hạch bạch huyết toàn thán (catalog ghi *toàn thân*)
4. Massage mặt - Khai thông đầu, vai cổ
5. Hơ ngải huyệt đạo làm ấm lại cơ thể

Thải hàn giải cảm, 6 bước (3.png):

1. Giải cơ sâu vùng lưng, vai cổ, phong tán hàn vùng lưng
2. Giác hơi không nhiệt (theo nhu cầu khách hàng)
3. Thải dịch bụng
4. Diện chẩn mặt - Massage mặt - Khai thông đầu
5. Bày hàn qua lòng bàn chân
6. Hơ ngải dẫn lửa làm ấm lại cơ thể sau trục hàn

## Ảnh và catalog lệch nhau ở đâu?

### Cần sửa catalog hoặc cần chủ tiệm xác nhận

1. Tên dịch vụ Ngừa đột quỵ. Ảnh 17.png, 18.png và 19.png ghi *Ngừa đột quỵ*. Catalog (`dien-chan-ngua-dot-quy`) và văn bản chép (dòng 56–57, phần bìa) ghi *Diện chẩn ngừa đột quỵ*. Tôi không biết vì sao văn bản chép thêm chữ *Diện chẩn*. Có hai khả năng: người chép tự thêm, hoặc bộ ảnh nhận ngày 2026-05-16 khác bộ ảnh vừa sao từ Drive. Tôi không có dữ kiện để chọn giữa hai khả năng này; hai bộ cùng có 19 ảnh.
2. Tên dịch vụ Detox. Ảnh 5.png (bìa), 6.png (tiêu đề) và 7.png (tiêu đề quy trình) ghi *Detox cơ thể*. Catalog (`detox-mui-co-the`) và văn bản chép (dòng 257–258, phần bìa) ghi *Detox mùi cơ thể*. Thân bài 6.png dùng *Detox mùi cơ thể* hai lần, nên trên chính menu dịch vụ này có hai tên.
3. Quy trình Giải mỏi đứng lâu. Slide 16.png tên *chăm sóc chân* nhưng in đúng 6 bước của slide *chăm sóc vai cổ chuyên sâu* (13.png). Bước 2 đến bước 6 nói về lưng, vai, cổ, tay, đầu và mặt; slide giới thiệu 15.png lại nói liệu trình tập trung vào chân. Văn bản chép (dòng 127) coi việc trùng này là một quy trình dùng chung có chủ ý; đó là nhận định của người chép, ảnh không ghi như vậy. Catalog chép đúng ảnh. Chủ tiệm cần xác nhận quy trình thật của dịch vụ này.

### Không cần sửa catalog

4. Lỗi dấu trên ảnh bìa. Bìa 2.png in "Thải hàn giai cam", bìa 5.png in "Detox cơ thê", bìa 14.png in "giãn tinh mạch". Catalog viết đúng dấu. Tôi đoán phông chữ tiêu đề không vẽ được một số dấu, vì các slide giới thiệu và quy trình dùng phông khác và in đúng dấu cho cùng những chữ này. Phông tiêu đề còn vẽ nét đuôi trang trí có chấm dưới chữ *h* (2.png), *x* (5.png), *y* và *g* (11.png); tôi không coi các nét này là dấu. Nếu tiệm gửi lại các ảnh bìa này cho khách, nên sửa ảnh trước.
5. Lỗi gõ trong bước quy trình in trên ảnh. Bước 3 của 7.png in "toàn thán"; catalog đã đổi thành "toàn thân" mà không ghi chú. Bước 3 của 10.png in "bộ nguyệt"; ảnh gốc in đúng chữ này, nên đây là lỗi của menu chứ không phải lỗi chép, và catalog đang ghi chú đúng. Bước 2 của 13.png và 16.png in "Đã thông cơ bó vai, cổ", và bước 5 của 3.png in "Bày hàn qua lòng bàn chân". Tôi đoán *Đã thông* là lỗi gõ của *Đả thông*; với chữ *Bày* tôi không đoán được chữ đúng. Chủ tiệm cần xác nhận hai chữ này trước khi bot đọc nguyên văn hai bước đó.
6. Văn bản chép bỏ tên dịch vụ trong tiêu đề slide quy trình. Trên ảnh, mỗi slide quy trình có tên trong ngoặc kép, ví dụ "chăm sóc chân" hay "ngừa đột quỵ". Văn bản chép thay hết bằng câu chung "Quy trình của chúng mình sẽ như sau:". Tên trong tiêu đề xác nhận catalog đã gán mỗi danh sách bước cho đúng dịch vụ.

Ảnh không có dịch vụ nào ngoài 6 dịch vụ trên. Trong catalog, nhóm `health` cũng chỉ có 6 dịch vụ này. Các nhóm khác của catalog nằm ở thư mục ảnh khác, ngoài phạm vi báo cáo này.

## Câu trên ảnh bot không được nhắc lại

Các câu trong bảng in trên ảnh gốc và nói về bệnh, về cơ chế trong cơ thể hoặc về hiệu quả điều trị. Tôi đề xuất bot không đọc lại và không diễn giải lại các câu này. Cột cuối ghi câu đó đã có trong `flagged_claims` của catalog hay chưa. Tôi chưa hỏi người có chuyên môn y tế hay pháp lý; phần pháp lý nằm trong `research/07-vn-legal-compliance.md`.

| Ảnh | Dịch vụ | Câu in trên ảnh (trích ngắn) | Vì sao bot không nhắc lại | Đã có trong `flagged_claims` |
|---|---|---|---|---|
| 1.png | Cả nhóm | "Menu giúp bạn khỏe" | Tên nhóm hứa làm khách khỏe hơn; mức nhẹ, bot có thể gọi nhóm này là *menu khỏe* | Chưa (catalog không có trường ghi claim cho cả nhóm) |
| 17.png, 18.png, 19.png | Ngừa đột quỵ | tên "Ngừa đột quỵ" | Tên hứa ngăn một bệnh nguy hiểm | Có, ghi dưới tên *Diện chẩn ngừa đột quỵ* |
| 18.png | Ngừa đột quỵ | "phòng ngừa từ sớm" | Hứa phòng bệnh | Chưa |
| 18.png | Ngừa đột quỵ | "dấu hiệu cho thấy dòng lưu thông đang chậm lại" | Diễn giải đầu nặng, vai cổ căng, ngủ không sâu thành vấn đề tuần hoàn; đây là chẩn đoán | Chưa |
| 18.png | Ngừa đột quỵ | "ảnh hưởng trực tiếp đến tuần hoàn máu não" | Nói về sinh lý não mà menu không nêu căn cứ | Có |
| 19.png | Ngừa đột quỵ | "ấn huyệt xoá tắt nghẽn mạch máu" | Hứa tác động lên mạch máu | Có |
| 19.png | Ngừa đột quỵ | "bộ huyệt chống đột quỵ" | Hứa phòng bệnh | Có |
| 19.png | Ngừa đột quỵ | "Thải độc và phong tán hàn ra bàn chân" | Nói dịch vụ đẩy chất độc ra khỏi cơ thể mà không có căn cứ | Chưa |
| 14.png, 15.png | Giải mỏi đứng lâu | "chăm sóc chân giãn tĩnh mạch" | Gắn dịch vụ với bệnh tĩnh mạch; khách giãn tĩnh mạch cần được khuyên đi khám | Có |
| 15.png | Giải mỏi đứng lâu | "hỗ trợ lưu thông" | Nói về tuần hoàn máu; nhẹ hơn các câu khác nhưng vẫn là lời hứa về cơ thể | Chưa |
| 11.png, 12.png | Thiếu máu não | tên "Thiếu máu não – tê tay, căng thẳng khó ngủ" | Tên là một chẩn đoán bệnh; tê tay kéo dài cần đi khám | Có |
| 12.png | Thiếu máu não | "việc lưu thông lên đầu dễ bị ảnh hưởng" | Giải thích mệt mỏi bằng tuần hoàn lên não | Chưa |
| 12.png | Thiếu máu não | "liên quan trực tiếp đến tuần hoàn và thần kinh" | Nói về sinh lý mà menu không nêu căn cứ | Có |
| 9.png | Đau thắt lưng mỏi gối | "Khi thận không được nuôi dưỡng đầy đủ, hàn tà dễ xâm nhập" | Câu này quy đau thắt lưng, mỏi gối cho thận; đau lưng kéo dài có nhiều nguyên nhân cần khám | Chưa |
| 9.png | Đau thắt lưng mỏi gối | "chính khí của thận đang suy yếu" | Chẩn đoán bệnh của thận từ tóc khô, đầu nóng | Có |
| 9.png | Đau thắt lưng mỏi gối | "giảm đau mỏi rõ rệt" | Hứa hiệu quả | Có |
| 9.png | Đau thắt lưng mỏi gối | "duy trì hiệu quả lâu dài" | Hứa hiệu quả lâu dài khi khách mua thêm Thải hàn | Chưa |
| 10.png | Đau thắt lưng mỏi gối | "bổ khí thận", "thải dịch phù nề", "bộ bổ thận" | Bước quy trình hứa tác động lên thận và lên phù nề; nếu bot đọc các bước quy trình như báo cáo 01 đề xuất, cần bỏ hoặc viết lại ba cụm này | Chưa |
| 6.png | Detox cơ thể | "đó không phải do vệ sinh, mà là dấu hiệu cơ thể đang ứ trệ" | Gạt đi các nguyên nhân khác của mùi cơ thể kéo dài, kể cả nguyên nhân bệnh | Chưa |
| 6.png | Detox cơ thể | hệ bạch huyết là "đường ống thải độc" | Nói dịch vụ thải chất độc mà không có căn cứ | Chưa |
| 6.png | Detox cơ thể | "độc tố dễ tích tụ và thoát ra qua mồ hôi, từ đó gây mùi cơ thể" | Giải thích cơ chế không có căn cứ | Có |
| 6.png | Detox cơ thể | "làm sạch từ bên trong" | Hứa làm sạch bên trong cơ thể | Có |
| 2.png, 3.png, 4.png | Thải hàn giải cảm | chữ "giải cảm" trong tên | Hứa chữa cảm | Chưa |
| 4.png | Thải hàn giải cảm | "mệt kéo dài, dễ cảm gió, đau đầu âm ỉ" quy cho nhiễm hàn | Quy các triệu chứng cần đi khám cho một khái niệm Đông y | Chưa |
| 4.png | Thải hàn giải cảm | "từng nhiễm hàn suốt nhiều năm và đã chăm sóc dứt điểm" | Lời kể của người sáng lập dễ bị hiểu là lời hứa khỏi hẳn | Có |
| 4.png | Thải hàn giải cảm | "hiệu quả được duy trì lâu dài" | Hứa hiệu quả lâu dài | Chưa |

## Nói ngắn gọn nhất

Giá, thời lượng và khung giờ của menu khỏe trong catalog đúng với ảnh gốc, nên bot báo giá nhóm này được. Hai tên dịch vụ trong catalog lệch với ảnh: ảnh ghi *Ngừa đột quỵ* và *Detox cơ thể*, catalog ghi *Diện chẩn ngừa đột quỵ* và *Detox mùi cơ thể*, do văn bản chép menu ghi sai từ đầu. Slide quy trình của Giải mỏi đứng lâu in đúng danh sách bước của dịch vụ vai cổ, nên tôi nghi slide này chép nhầm và đề xuất bot chưa đọc các bước đó cho tới khi chủ tiệm xác nhận. Trên ảnh còn 14 câu về bệnh và hiệu quả điều trị mà catalog chưa đánh dấu; bot không được nhắc lại các câu này.

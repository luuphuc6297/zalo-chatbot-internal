# Đối chiếu ảnh menu chăm sóc da với catalog của chatbot

Ngày đối chiếu: 2026-11-08. Thư mục ảnh: `sources/drive-resources/thomhouse-menu/facial-cham-soc-da-co-ban/` (21 ảnh PNG, tên thư mục gốc trên Drive là "Facial - Menu chăm sóc da cơ bản").

Trong báo cáo này, *catalog* là file `data/services.json` mà chatbot dùng để trả lời giá và quy trình. *Bản chép* là file `sources/drive/raw-content/batch-04-skincare-menu.md`, văn bản người soạn chép lại từ ảnh menu da ngày 2026-05-16. Catalog được dựng từ bản chép này. *Câu hứa tác dụng* là câu trên menu nói dịch vụ làm da, cơ thể hay bệnh thay đổi ra sao.

## Phần anh cần duyệt

Bộ 21 ảnh trên Drive là một menu da khác với bộ 5 ảnh mà catalog đã chép, nên catalog đang thiếu phần lớn menu da và sai thời lượng ở cả ba dịch vụ có trên ảnh. Ảnh có 10 dịch vụ với 13 mức giá. Catalog có 5 dịch vụ da với 5 mức giá.

Ba dịch vụ có ở cả hai nơi là Gói mụn 5in1 và hai gói Xoá thâm quầng mắt. Giá của ba dịch vụ này khớp. Thời lượng của cả ba thì lệch: Gói mụn 5in1 in "60- 90 phút" trong khi catalog ghi 90 phút; gói cơ bản in 45 phút trong khi catalog ghi 60 phút; gói công nghệ điện xung trường in 60 phút trong khi catalog ghi 90 phút.

Câu hứa tác dụng của gói công nghệ điện xung trường trên ảnh in "gấp 10 lần điện di ion bình thường tại cơ sở". Catalog và bản chép ghi "gấp 20 lần". Bộ kiểm tra bản nháp trước khi gửi (`apps/server/src/checker/index.ts`, dòng 12) chỉ chặn cụm "gấp 20 lần", nên câu "gấp 10 lần" hiện chưa bị chặn.

Tám dịch vụ trên ảnh chưa có trong catalog, giá từ 289.000 đến 6.500.000 đồng. Hai dịch vụ trong catalog là Gói Mụn Chuyên Sâu và Chăm sóc da kích ứng không có trên ảnh nào trong thư mục này. Không ảnh nào in khung giờ giá (trước hay sau 20:30), và catalog cũng không ghi khung giờ cho nhóm da, nên phần khung giờ khớp.

Ảnh có thêm những câu hứa tác dụng mà bản chép không có, nặng nhất là "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố" trên hai ảnh Bio PDRN. Chatbot không được nói lại các câu này.

Anh cần quyết ba việc, ghi ở mục cuối: bộ menu nào là bản đang bán, có thêm tám dịch vụ mới vào catalog hay không, và có chặn mọi con số dạng "gấp N lần" hay không.

## Tôi đã đọc và chạy những gì?

Tôi mở cả 21 ảnh bằng công cụ đọc ảnh. Với các dòng giá, dòng thời lượng và câu "gấp 10 lần" ở ảnh 9, tôi cắt vùng ảnh bằng lệnh `sips -c ... --cropOffset ...` rồi đọc lại ở độ phóng lớn hơn. Mọi chữ số trong báo cáo đều đọc rõ, không có chữ số nào phải đoán.

Tôi đọc 5 mục nhóm `skin` trong `data/services.json` (dòng 1590 đến khoảng dòng 2010), toàn bộ bản chép `batch-04-skincare-menu.md`, phần địa chỉ và tên trong `data/business-facts.json`, các dòng về da trong `research/01-knowledge-audit.md`, mục về dịch vụ sức khỏe và mỹ phẩm trong `research/07-vn-legal-compliance.md`, và danh sách từ cấm trong `apps/server/src/checker/index.ts`.

Tôi không sửa `data/services.json` hay file nào khác ngoài báo cáo này. Tôi không mở ảnh ở các thư mục menu khác, nên chưa biết Gói Mụn Chuyên Sâu và Chăm sóc da kích ứng có nằm ở thư mục khác hay không.

## Bộ 21 ảnh có phải bộ ảnh catalog đã chép không?

Với các bằng chứng tôi có, bộ 21 ảnh không phải bộ ảnh mà bản chép đã chép. Bằng chứng nằm ngay trong bản chép; kết luận này là suy luận từ các bằng chứng đó.

Bản chép ghi nguồn là 5 ảnh (dòng 3). Bản chép ghi các slide da không có header và không có địa chỉ (dòng 13 và 14), và slide bìa in "CHĂM SÓC DA MỤN" (dòng 18). Cả 21 ảnh trên Drive đều có header "thom house facial studio -Since 2019" và dòng địa chỉ ở chân trang. Ảnh bìa (ảnh 1) in "Menu chăm sóc da".

Ảnh nền bản chép tả cũng không khớp ảnh nào trong 21 ảnh. Ví dụ, bản chép tả slide quầng mắt là người phụ nữ được lăn đá jade dưới mắt (dòng 120). Ảnh 8 thì chụp người phụ nữ cười, chấm kem dưới mắt và đặt tay lên má.

Tôi không biết bộ nào mới hơn. File `INDEX.md` của bản mirror chỉ ghi đường dẫn, dung lượng, Drive ID và loại file, không ghi ngày sửa trên Drive. Có hai dấu hiệu cho thấy một bộ đã được sửa từ bộ kia: câu "Khô còi mụn nhanh chóng với các hoạt chất treatment lành tính" giống hệt nhau ở hai bộ, còn câu quầng mắt chỉ khác ở con số (10 và 20) và cụm "tại cơ sở".

## Từng nhóm ảnh in gì và catalog ghi gì?

Mỗi dịch vụ chiếm hai ảnh liền nhau: ảnh đầu in tên, thời lượng và giá; ảnh sau in quy trình. Tên dịch vụ trong các bảng chép đúng chữ in trên ảnh, kể cả dấu. Giá trên ảnh chép đúng cách in (dấu phẩy ngăn hàng nghìn, chữ "VNĐ").

### Ảnh 1: bìa menu

| Ảnh | Nội dung in trên ảnh | Catalog | Khớp |
|---|---|---|---|
| `1.png` | Tiêu đề "Menu chăm sóc da", header "thom house facial studio -Since 2019", chữ "Made by thomhouse team", câu dọc "Beauty is the harmony of body and soul.", địa chỉ "72 đường số 37 , phường Tân Hưng quận 7" | Catalog không có mục cho ảnh bìa; `business-facts.json` ghi tên doanh nghiệp là "thom house healing studio" | Tên "facial studio" không có trong `business-facts.json` |

### Ảnh 2 và 3: Detox da

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `2.png` | Detox da (khách chọn một trong hai loại da: "Da mụn: Nặn mụn" hoặc "Da không mụn: Massage mặt") | "60- 75 phút", "389,000 VNĐ" | Catalog không có dịch vụ tên Detox da | Không: dịch vụ thiếu trong catalog |

Quy trình in trên ảnh 3, đúng thứ tự:

1. Thoa detox lam sạch bít tắc nan lông
2. Ủ bông làm mềm còi mụn
3. Sát khuẩn - nặn mụn trong 30 phút / massage mặt 20 phút
4. Điện tím sát khuẩn
5. Lăn búa lạnh tinh chất dịu da
6. Đấp nạ dẻo hàn quốc

Catalog có Gói Mụn Chuyên Sâu cùng giá 389.000 đồng và 75 phút, nằm trong khoảng 60 đến 75 phút của Detox da. Năm bước của Gói Mụn Chuyên Sâu trong catalog thì khác sáu bước trên ảnh 3. Tôi không đủ căn cứ để nói hai tên này là một dịch vụ.

### Ảnh 4 và 5: Gói mụn 5in1

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog (`goi-mun-5-in-1`) | Khớp |
|---|---|---|---|---|
| `4.png` | "MỤN SIGNATURE" và "Gói mụn 5in1"; ảnh 5 gọi quy trình là "Chăm da 5in1" | "60- 90 phút", "599,000 VNĐ" | Tên "Gói Mụn 5 in 1", 90 phút, 599.000 đồng, `is_signature: true` | Giá khớp. Thời lượng không khớp. Tên lệch nhẹ về khoảng trắng và chữ hoa |

Quy trình in trên ảnh 5 có 5 bước:

1. Làm sạch sừng chết và bã nhờn với whitetox
2. Massage kem mỡ làm mềm còi mụn
3. Lấy sạch nhân mụn
4. Thoa hoạt chất giảm viêm đỏ se còi mụn
5. Đắp mặt nạ chuyên dụng kháng viêm

Catalog ghi 6 bước. Ở catalog, bước "Đắp mặt nạ chuyên dụng kháng viêm" đứng thứ tư và bước "Thoa hoạt chất" đứng thứ năm, ngược với ảnh. Catalog còn có bước thứ sáu "Bắn ánh sáng xanh SHR phục hồi da nhanh chóng (theo thời gian khuyến mại)". Ảnh 5 không có bước SHR và không có chữ "khuyến mại".

### Ảnh 6 và 7: Massage mặt thư giãn

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `6.png` | Massage mặt thư giãn | "60 phút", "289,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Quy trình in trên ảnh 7:

1. Vệ sinh da
2. Massage mặt thư giãn
3. Massage cổ vai tay mặt ngửa
4. Lăn búa lạnh tinh chất dịu da
5. Đấp nạ dẻo hàn quốc

### Ảnh 8 và 9: Xoá thâm quầng mắt

Ảnh 8 in tiêu đề "Xoá thâm quầng mắt", còn ảnh 9 in "Xóa thâm quầng mắt". Hai cách đặt dấu này đều đúng chính tả.

| Ảnh | Gói in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `8.png` | Cơ bản | "45 phút", "329,000 VNĐ" | `xoa-tham-quang-mat-co-ban`: tên "Xóa thâm quầng mắt – Gói cơ bản", 60 phút, 329.000 đồng | Giá khớp. Thời lượng không khớp: ảnh 45 phút, catalog 60 phút |
| `8.png` | Công nghệ điện xung trường | "60 phút", "629,000 VNĐ" | `xoa-tham-quang-mat-dien-xung-truong`: tên "Xóa thâm quầng mắt – Gói công nghệ điện xung trường", 90 phút, 629.000 đồng | Giá khớp. Thời lượng không khớp: ảnh 60 phút, catalog 90 phút |

Ảnh 9 in câu mô tả của từng gói. Gói cơ bản: "Massage ấn huyệt dẫn lưu giúp khí huyết không còn tắt nghẽn, giảm ngay tình trạng thâm đen, ứ tụ bọng mắt". Gói công nghệ điện xung trường: "Massage ấn huyệt mắt kết hợp với plasma đưa tinh chất xuống da bằng công nghệ điện xung trường, hiệu quả gấp 10 lần điện di ion bình thường tại cơ sở, giảm thâm nhăn hiệu quả".

Ảnh 9 còn in một quy trình chung dưới tiêu đề "Quy trình Xóa thâm quầng mắt", không ghi quy trình này thuộc gói nào:

1. Vệ sinh da
2. Chải dụng cụ
3. Thải dịch ổ mắt
4. Lăn búa lạnh tinh chất phục hồi da mắt
5. Đấp nạ dẻo hàn quốc

Catalog chỉ ghi câu mô tả làm bước quy trình, cho cả hai gói. Năm bước trên ảnh 9 chưa có trong catalog.

### Ảnh 10 và 11: Cấp dinh dưỡng cơ bản

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `10.png` | Cấp dinh dưỡng cơ bản (khách chọn một trong hai mục: "Da nhạy cảm, kích ứng, cháy nắng" hoặc "Da thâm sạm, mụn, khô, lỗ chân lông to") | "60- 75 phút", "599,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Ảnh 11 mở bằng câu "Lâm sàn trong 7 năm qua, Thơm mang đến cho bạn quy trình nhẹ nhàng nhưng hiệu quả". Quy trình in trên ảnh 11:

1. Làm sạch da
2. Massage tinh chất cấp nước
3. Nặn mụn nếu có/ massage vai cổ
4. Xịt tế bào gốc
5. Lăn búa lạnh dinh dưỡng
6. Đấp nạ dịu da

Catalog có Chăm sóc da kích ứng cùng giá 599.000 đồng nhưng ghi 90 phút. Mục "Da nhạy cảm, kích ứng, cháy nắng" của ảnh 10 có thể đã thay cho dịch vụ Chăm sóc da kích ứng. Đây chỉ là suy luận từ mức giá giống nhau và từ chữ "kích ứng". Năm bước của Chăm sóc da kích ứng trong catalog khác sáu bước trên ảnh 11.

### Ảnh 12 và 13: Cấp dinh dưỡng bằng công nghệ Plasma fusion

| Ảnh | Mức giá in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `12.png` | Tinh chất | "60 phút" (in một lần cho cả dịch vụ), "999,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |
| `12.png` | Dịch chiết tế bào gốc | "60 phút" (in một lần cho cả dịch vụ), "1,500,000 VNĐ - 2,500,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog; giá in là một khoảng, ảnh không nói khi nào tính 1.500.000 và khi nào tính 2.500.000 đồng |

Ảnh 12 cho khách chọn một trong hai mục: "Chăm sóc da mụn, thu nhỏ lỗ chân lông, sáng màu" hoặc "Chăm sóc nếp nhăn, nâng cơ". Ảnh 13 mở bằng câu "Phục hồi liên kết collagen và elastine giúp cơ cổ/mặt săn chắc, đều màu, ấn huyệt dẫn lưu đào thải khí tắt nghẽn". Quy trình in trên ảnh 13:

1. Vệ sinh da
2. Sử dụng Cleanser Snow O₂ sạch sâu
3. Massage nâng cơ / nặn mụn
4. Ứng dụng năng lượng Plasma theo vấn đề da
5. Lăn búa lạnh dịu da
6. Đấp nạ chuyên phục hồi

### Ảnh 14 và 15: Lăn dưỡng

| Ảnh | Mức giá in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `14.png` | Da cần làm dày sừng | "60 phút", "1,500,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |
| `14.png` | Giảm mụn, sẹo / nám, nếp nhăn | "60 phút", "2,500,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Ảnh 15 mở bằng câu "Ứng dụng kĩ thuật tái tạo sừng giúp phục hồi cấu trúc da suy, tạo lớp bảo vệ hoàn hảo, đều màu, thu nhỏ lỗ chân lông, giảm sẹo nhẹ". Quy trình in trên ảnh 15:

1. Vệ sinh da
2. Sử dụng Cleanser Snow O₂ sạch sâu
3. Sát khuẩn
4. Lăn dưỡng
5. Lăn búa lạnh dịu da
6. Đấp nạ chuyên dụng phục hồi

### Ảnh 16 và 17: Inner Fill nâng cấp da

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `16.png` | Inner Fill nâng cấp da (khách chọn một trong hai mục: "Chăm sóc da mụn, thu nhỏ lỗ chân lông, sáng màu" hoặc "Chăm sóc đốm nâu, nếp nhăn, nâng cơ") | "60 - 75 phút", "6,500,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Quy trình in trên ảnh 17:

1. Vệ sinh da
2. Sử dụng Cleanser Snow O₂ sạch sâu
3. Sát khuẩn
4. Inner fill hoạt chất theo chỉ định
5. Lăn búa lạnh dịu da
6. Đấp nạ chuyên dụng phục hồi

Ảnh không nói Inner Fill đưa hoạt chất vào da bằng cách nào. Chatbot không được đoán cách làm.

### Ảnh 18 và 19: Bio PDRN Nuôi da căng bóng

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `18.png` | Bio PDRN Nuôi da căng bóng | "60 phút", "2,500,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Ảnh 18 in câu "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố. Cải thiện màu da, kết cấu da. Tăng cường độ đàn hồi cho da." Quy trình in trên ảnh 19:

1. Vệ sinh da
2. Sử dụng Cleanser Snow O₂ sạch sâu
3. Massage mặt tinh thể nước/ nặn mụn
4. Vỗ tinh chất Bio PDRN
5. Lăn búa lạnh dịu da
6. Nạ chuyên dụng phục hồi

### Ảnh 20 và 21: Bio PDRN Nuôi da căng bóng full

| Ảnh | Dịch vụ in trên ảnh | Thời lượng và giá in trên ảnh | Catalog | Khớp |
|---|---|---|---|---|
| `20.png` | Bio PDRN Nuôi da căng bóng full | "90 phút", "5,000,000 VNĐ" | Catalog không có dịch vụ này | Không: dịch vụ thiếu trong catalog |

Ảnh 20 in lại đúng câu "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố..." của ảnh 18. Quy trình in trên ảnh 21 có 9 bước:

1. Tẩy trang
2. Sử dụng Cleanser Snow O₂
3. Sử dụng kem massage nước
4. Sử dụng mặt nạ EZ CO₂ (Carboxy Therapy)
5. Sử dụng tinh chất Bio PDRN
6. Sử dụng mặt nạ chuyên dụng
7. Sử dụng kem phục hồi làm dịu
8. Xịt khoáng vi sinh
9. Bắn trẻ hoá IPL

## Catalog lệch với ảnh ở những điểm nào?

Mục này gom mọi điểm lệch. Mỗi điểm ghi giá trị trên ảnh trước, giá trị trong catalog sau.

1. Gói mụn 5in1, thời lượng: ảnh 4 in "60- 90 phút"; catalog ghi 90 phút (`services.json` dòng 1679); bản chép ghi 90 phút (dòng 70).
2. Gói mụn 5in1, quy trình: ảnh 5 in 5 bước, bước "Thoa hoạt chất" đứng trước bước "Đắp mặt nạ"; catalog ghi 6 bước, hai bước này đổi chỗ, và có thêm bước SHR "(theo thời gian khuyến mại)" (bản chép dòng 78 đến 80). Ảnh không có bước SHR.
3. Gói mụn 5in1, tên: ảnh in "Gói mụn 5in1" (viết liền "5in1"); catalog ghi "Gói Mụn 5 in 1".
4. Xoá thâm quầng mắt, gói cơ bản, thời lượng: ảnh 8 in 45 phút; catalog ghi 60 phút (dòng 1911).
5. Xoá thâm quầng mắt, gói công nghệ điện xung trường, thời lượng: ảnh 8 in 60 phút; catalog ghi 90 phút (dòng 1979).
6. Xoá thâm quầng mắt, gói công nghệ điện xung trường, câu hứa tác dụng: ảnh 9 in "gấp 10 lần điện di ion bình thường tại cơ sở"; catalog ghi "gấp 20 lần điện di ion bình thường" (dòng 1999), lấy từ bản chép dòng 142.
7. Xoá thâm quầng mắt, quy trình: ảnh 9 in 5 bước chung; catalog chỉ có câu mô tả làm bước cho cả hai gói.
8. Xoá thâm quầng mắt, tên gói: ảnh in "Cơ bản" và "Công nghệ điện xung trường"; catalog ghi "Gói cơ bản" và "Gói công nghệ điện xung trường". Điểm lệch này nhỏ, không đổi nghĩa.
9. Tám dịch vụ có trên ảnh nhưng chưa có trong catalog: Detox da (ảnh 2), Massage mặt thư giãn (ảnh 6), Cấp dinh dưỡng cơ bản (ảnh 10), Cấp dinh dưỡng bằng công nghệ Plasma fusion (ảnh 12, hai mức giá), Lăn dưỡng (ảnh 14, hai mức giá), Inner Fill nâng cấp da (ảnh 16), Bio PDRN Nuôi da căng bóng (ảnh 18) và Bio PDRN Nuôi da căng bóng full (ảnh 20). Tám dịch vụ này có tổng cộng 10 mức giá.
10. Gói Mụn Chuyên Sâu (`goi-mun-chuyen-sau`, 75 phút, 389.000 đồng) có trong catalog nhưng không có trên ảnh nào trong 21 ảnh.
11. Chăm sóc da kích ứng (`cham-soc-da-kich-ung`, 90 phút, 599.000 đồng) có trong catalog nhưng không có trên ảnh nào trong 21 ảnh.
12. Tên cơ sở: cả 21 ảnh in header "thom house facial studio -Since 2019"; `business-facts.json` ghi "thom house healing studio". Bản chép dòng 13 ghi slide da không có header.
13. Địa chỉ: 20 ảnh in "72 đường số 37 , phường Tân Hưng quận 7", ảnh 6 in "72 đường số 37 , phường Tân Hưng, quận 7". Cả 21 ảnh đều ghi phường Tân Hưng, không ảnh nào ghi Tân Kiểng. Mục `address` trong `business-facts.json` đang ở trạng thái `conflict` vì bản chép menu phụ nữ ghi Tân Kiểng.
14. Khung giờ giá: không ảnh nào in khung giờ. Catalog ghi `time_window: null` cho cả 5 dịch vụ da. Điểm này khớp, tôi ghi lại để anh biết là đã đối chiếu.

## Lỗi chính tả trên ảnh có liên quan tới "nan tóc" không?

Có một điểm liên quan. Ảnh 3 in "bít tắc nan lông". Tôi đoán từ đúng là "nang lông", vì câu đang nói về làm sạch phần bít tắc trong lỗ chân lông. Lỗi này cùng kiểu với "Chăm sóc nan tóc" ở menu tóc mà bản kiểm kê trước đã nghi là "nang tóc". Hai lỗi cùng kiểu ở hai menu là một dấu hiệu cho thấy người soạn menu viết "nan" cho "nang". Đây là suy luận, chủ menu cần xác nhận.

Các lỗi khác tôi thấy trên ảnh, kèm chữ tôi đoán là đúng:

- Ảnh 3: "lam sạch", tôi đoán là "làm sạch".
- Ảnh 3, 7, 9, 11, 13, 15 và 17: "Đấp nạ", tôi đoán là "Đắp nạ". Ảnh 5 in đúng "Đắp mặt nạ"; ảnh 19 in "Nạ chuyên dụng phục hồi".
- Ảnh 9 và 13: "tắt nghẽn", tôi đoán là "tắc nghẽn".
- Ảnh 11: "Lâm sàn", tôi đoán là "lâm sàng".
- Ảnh 13: "elastine", tôi đoán là "elastin"; "Đấp nạ chuyên phục hồi" thiếu chữ "dụng" so với ảnh 15 và 17.

Khi chatbot đọc tên bước quy trình cho khách, chatbot nên dùng chữ đã sửa sau khi chủ menu xác nhận, không chép lỗi từ ảnh.

## Câu nào trên ảnh chatbot không được nói lại?

Các câu dưới đây hứa tác dụng lên da hoặc cơ thể, hoặc dùng từ y khoa. Theo `research/07-vn-legal-compliance.md`, thom house không phải cơ sở khám bệnh, chữa bệnh. Báo cáo đó cũng dẫn Luật 19/2023, luật cấm thông tin sai lệch về công dụng dịch vụ. Việc từng câu có vi phạm hay không là suy luận của tôi, luật sư cần xem.

| Ảnh | Câu in trên ảnh | Vì sao chatbot không được nói lại |
|---|---|---|
| `18.png`, `20.png` | "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố. Cải thiện màu da, kết cấu da. Tăng cường độ đàn hồi cho da." | Câu nói dịch vụ "điều trị" mụn trứng cá, tức là nói tác dụng chữa bệnh |
| `9.png` | "hiệu quả gấp 10 lần điện di ion bình thường tại cơ sở, giảm thâm nhăn hiệu quả" | Con số "10 lần" không có nguồn đo; bộ kiểm tra bản nháp chưa chặn cụm này |
| `9.png` | "Massage ấn huyệt dẫn lưu giúp khí huyết không còn tắt nghẽn, giảm ngay tình trạng thâm đen, ứ tụ bọng mắt" | Câu hứa kết quả tức thì ("giảm ngay") và nói về khí huyết, một khái niệm y học cổ truyền |
| `11.png` | "Lâm sàn trong 7 năm qua, Thơm mang đến cho bạn quy trình nhẹ nhàng nhưng hiệu quả" | "Lâm sàng" là từ của ngành y; `business-facts.json` ghi chị Thơm không phải bác sĩ hay lương y |
| `13.png` | "Phục hồi liên kết collagen và elastine giúp cơ cổ/mặt săn chắc, đều màu, ấn huyệt dẫn lưu đào thải khí tắt nghẽn" | Câu khẳng định tác dụng lên cấu trúc da mà menu không nêu nguồn |
| `15.png` | "Ứng dụng kĩ thuật tái tạo sừng giúp phục hồi cấu trúc da suy, tạo lớp bảo vệ hoàn hảo, đều màu, thu nhỏ lỗ chân lông, giảm sẹo nhẹ" | Câu khẳng định tác dụng và dùng từ tuyệt đối "hoàn hảo" |
| `5.png` | "Khô còi mụn nhanh chóng với các hoạt chất treatment lành tính" | Câu hứa tốc độ ("nhanh chóng"); câu này đã nằm trong `flagged_claims` của catalog |
| `17.png` | "Inner fill hoạt chất theo chỉ định" | "Chỉ định" là từ y khoa, gợi ý có người kê đơn; ảnh không nói ai chỉ định |
| `11.png`, `12.png` | "Xịt tế bào gốc", "Dịch chiết tế bào gốc" | Chatbot không được giải thích là tế bào gốc người; catalog đã có quy tắc này cho "xịt tế bào gốc" |
| `21.png` | "Sử dụng mặt nạ EZ CO₂ (Carboxy Therapy)", "Bắn trẻ hoá IPL" | Đây là tên máy và sản phẩm; menu không nói loại máy và người vận hành. Tôi chưa tra quy định về việc spa dùng máy IPL |

Chatbot vẫn đọc được tên dịch vụ, thời lượng, giá và tên các bước quy trình. Chatbot không giải thích cơ chế, không nói độ an toàn và không hứa kết quả.

Trong bộ kiểm tra bản nháp, dòng 11 của `apps/server/src/checker/index.ts` đã có "điều trị" và "trị", nên câu ở ảnh 18 và ảnh 20 sẽ bị chặn nếu bản nháp chép nguyên câu. Dòng 12 có "gấp 20 lần" nhưng không có "gấp 10 lần". Danh sách từ cấm cũng chưa có "lâm sàng". Tôi chỉ đọc danh sách này, chưa chạy bộ kiểm tra với các câu trên.

## Anh cần quyết những gì?

**Bộ menu nào là bản đang bán?** Anh cần hỏi chị Thơm, vì chỉ chủ cơ sở biết bộ 21 ảnh trên Drive hay bộ 5 ảnh đã chép là bản hiện hành. Nếu bộ 21 ảnh là bản hiện hành, catalog phải sửa thời lượng của ba dịch vụ, bỏ bước SHR của Gói mụn 5in1 và gỡ hoặc đổi tên hai dịch vụ không có trên ảnh. Nếu cả hai bộ cùng đang dùng, catalog cần ghi rõ dịch vụ nào thuộc menu nào. Tôi đề xuất: trong lúc chờ chị Thơm trả lời, chatbot chỉ báo giá cho ba dịch vụ lệch, vì giá khớp ở cả hai nguồn, và chuyển nhân viên khi khách hỏi thời lượng. Điểm yếu của cách này là khách hỏi thời lượng sẽ phải chờ nhân viên.

**Có thêm tám dịch vụ mới vào catalog không?** Nếu thêm, chatbot trả lời được thêm 10 mức giá, trong đó có các mức cao như 5.000.000 và 6.500.000 đồng. Nếu không thêm, khách hỏi Bio PDRN hay Inner Fill sẽ được chuyển nhân viên. Tôi đề xuất thêm với trạng thái `draft_unapproved`, chỉ gồm tên, thời lượng, giá và bước quy trình, không kèm câu hứa tác dụng. Với mức "Dịch chiết tế bào gốc" của Plasma fusion, chatbot chỉ nói khoảng giá và để nhân viên báo giá cụ thể. Điểm yếu: ngày sửa của bộ ảnh chưa rõ, nên giá có thể đã cũ; báo sai một dịch vụ 6.500.000 đồng gây thiệt hại lớn hơn báo sai một dịch vụ 289.000 đồng. Sau khi sửa `data/services.json`, file `apps/server/src/seed-data.ts` cần sinh lại bằng `apps/server/scripts/gen-seed-data.mjs`, theo dòng chú thích đầu file seed-data; tôi chưa chạy script này.

**Có chặn mọi con số dạng "gấp N lần" không?** Hiện bộ kiểm tra chỉ chặn đúng cụm "gấp 20 lần". Tôi đề xuất chặn theo mẫu "gấp" kèm một con số kèm "lần", để cả "gấp 10 lần" lẫn các con số khác đều bị chặn. Điểm yếu: mẫu này có thể chặn nhầm câu bình thường như "giá gấp 2 lần gói cơ bản", và nhân viên sẽ phải duyệt tay các bản nháp đó.

## Nói ngắn gọn nhất

Catalog da hiện dựng từ một bộ 5 ảnh khác, trong khi Drive có một menu da 21 ảnh với 10 dịch vụ. Ba dịch vụ có ở cả hai nơi khớp giá nhưng lệch thời lượng. Catalog ghi "gấp 20 lần", còn ảnh in "gấp 10 lần ... tại cơ sở". Tám dịch vụ trên ảnh chưa có trong catalog, còn hai dịch vụ trong catalog không có trên ảnh. Trước khi chatbot báo thời lượng hay giới thiệu dịch vụ da mới, chị Thơm cần xác nhận bộ menu nào đang bán, và chatbot không được nói lại câu "điều trị mụn trứng cá" hay bất kỳ con số "gấp N lần" nào.

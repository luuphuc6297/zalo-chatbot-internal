# Đối chiếu ảnh menu gốc: chăm sóc tóc và triệt lông

Ngày đối chiếu: 2026-11-08. Người làm: trợ lý AI (Claude), chỉ đọc ảnh và file, không sửa catalog.

## Phần anh cần duyệt

Ba dịch vụ tóc đang có trong catalog khớp với ảnh menu gốc về tên, giá, thời lượng và khung giờ. Catalog ở đây là file `data/services.json`, nơi chatbot lấy tên dịch vụ, giá và các bước làm. Tuy vậy, ảnh gốc có nhiều hơn những gì catalog đang biết. Thư mục menu chăm sóc tóc trên Drive có 14 slide, còn bản chép chữ cũ (`sources/drive/raw-content/batch-05-hair-care-menu.md`) chỉ chép 9 slide đầu. Năm slide chưa ai chép gồm dịch vụ Peel peptide da đầu (299.000đ, 15 phút), bảng ba loại mặt nạ (50.000đ đến 90.000đ) và bảng năm option nâng cấp (50.000đ đến 199.000đ). Thư mục triệt lông có một bảng 12 mức giá, từ 100.000đ đến 18.000.000đ, và catalog chưa có dòng nào cho triệt lông.

Ảnh gốc cho thấy một lỗi chép. Bước thứ chín của Chăm sóc nan tóc in là "Xả phục hồi", trong khi bản chép và catalog ghi "Xã phục hồi". Tên "nan tóc" thì catalog ghi đúng như ảnh, và ảnh in chữ "nan" giống nhau trên ba slide.

Anh cần quyết năm việc, ghi chi tiết ở mục cuối. Thứ nhất là giữ tên "nan tóc" hay sửa thành "nang tóc". Thứ hai là có đưa Peel peptide da đầu, mặt nạ, option nâng cấp và triệt lông vào catalog không. Ba việc còn lại cần hỏi chủ studio:

- giá combo triệt lông vùng Nách;
- giá option Massage cổ, vai, gáy khi khách làm sau 20h30;
- slide phiếu thông tin khách trong thư mục triệt lông dùng cho dịch vụ nào.

## Tôi đã đọc và chạy những gì?

- Tôi mở cả 17 ảnh bằng công cụ đọc ảnh: 14 ảnh trong `sources/drive-resources/thomhouse-menu/thu-gian-cham-soc-toc/` và 3 ảnh trong `sources/drive-resources/thomhouse-menu/hair-removal-triet-long/`. Lệnh `sips -g pixelWidth -g pixelHeight` cho thấy 14 ảnh menu tóc có kích thước 1414 x 2000 px; 3 ảnh triệt lông có kích thước 1536 x 2048 px.
- Tôi cắt phóng to bằng `sips -c` những vùng chữ nhỏ để đọc chắc từng chữ số và từng dấu: giá và thời lượng Peel peptide, ba bước Peel, giá ba mặt nạ, dòng option Detox da đầu, ba dòng "phục hồi" ở slide 4, 7 và 9, hai cột giá triệt lông. Ảnh cắt chỉ nằm trong scratchpad của phiên, không lưu vào dự án.
- Mọi chữ số trên 17 ảnh đều đọc được. Tôi không phải đoán chữ số nào.
- Tôi đọc các dịch vụ nhóm `hair` và `relaxation` trong `data/services.json` bằng một đoạn `python3 -I`. Tôi đọc toàn bộ `batch-05-hair-care-menu.md` và `batch-01-relaxation-menu.md`.
- Tôi dùng `grep` tìm các chữ triệt lông, peel peptide, mặt nạ tóc, PDRN, điện tím, nửa chân trong `data/`, `apps/`, `sources/drive/` và `research/`. Không file nào nhắc tới các dịch vụ mới này.
- Tôi không mở ba thư mục ảnh còn lại (facial, healing, thomhouse-space), vì các thư mục đó thuộc phần đối chiếu khác.

Trong bảng, cột "Ảnh in" chép đúng cách viết trên ảnh (ví dụ "139,000 VNĐ"). Ở phần văn, tôi viết giá theo kiểu "139.000đ".

## Menu chăm sóc tóc: ảnh in gì, catalog ghi gì?

Thư mục trên Drive tên là "Thư giãn - Menu chăm sóc tóc", nhưng cả 14 slide đều thuộc menu chăm sóc tóc. Không slide nào trong thư mục này là menu massage thư giãn.

| Ảnh | Dịch vụ, tên như in trên ảnh | Ảnh in | Catalog ghi | Khớp |
|---|---|---|---|---|
| `thu-gian-cham-soc-toc/1.png` | Bìa "Menu chăm sóc tóc" | Bìa không có giá | Bìa không cần đối chiếu | Không áp dụng |
| `thu-gian-cham-soc-toc/2.png` | Detox da đầu | "9h - 20h30: 139,000 VNĐ", "Sau 20h30: 159,000 VNĐ", "Thời gian: 40 phút" | `detox-da-dau`: 40 phút, 139.000đ khung 09:00-20:30, 159.000đ khung after_20:30 | Có |
| `thu-gian-cham-soc-toc/3.png` | Detox da đầu, đoạn giới thiệu | Slide không có giá; có câu "sẽ rất dễ bệnh đấy" và chữ "lành tính" | Catalog gắn cờ câu "dễ bệnh", chưa gắn cờ chữ "lành tính" | Có về giá; thiếu một cờ |
| `thu-gian-cham-soc-toc/4.png` | Quy trình Detox da đầu, 7 bước | Bảy bước, bước thứ sáu in "Xã phục hồi" | Bảy bước giống hệt ảnh, kể cả "Xã phục hồi" | Có |
| `thu-gian-cham-soc-toc/5.png` | Gội đầu thư giãn | "9h - 20h30: 199,000 VNĐ", "Sau 20h30: 229,000 VNĐ", "Thời gian: 50 phút" | `goi-dau-thu-gian`: 50 phút, 199.000đ khung 09:00-20:30, 229.000đ khung after_20:30 | Có |
| `thu-gian-cham-soc-toc/6.png` | Gội đầu thư giãn, đoạn giới thiệu | Slide không có giá; có ba câu về ốm, bệnh và rụng tóc | Catalog chỉ gắn cờ câu "dễ nhiễm lạnh lại hay sinh bệnh" | Có về giá; thiếu hai cờ |
| `thu-gian-cham-soc-toc/7.png` | Quy trình Gội Đầu Thư Giãn, 8 bước | Tám bước, bước thứ sáu in "Xã phục hồi" | Tám bước giống hệt ảnh | Có |
| `thu-gian-cham-soc-toc/8.png` | Chăm sóc nan tóc | "349,000 VNĐ", "Thời gian: 70 phút", không in khung giờ | `cham-soc-nan-toc`: 70 phút, 349.000đ, `time_window` là null | Có |
| `thu-gian-cham-soc-toc/9.png` | Quy trình Chăm Sóc Nan Tóc, 10 bước | Mười bước, bước thứ chín in "Xả phục hồi" (chữ a có dấu hỏi) | Mười bước, bước thứ chín ghi "Xã phục hồi" (chữ a có dấu ngã) | Không, lệch một bước |
| `thu-gian-cham-soc-toc/10.png` | Peel peptide da đầu | "299,000 VNĐ", "Thời gian: 15 phút", không in khung giờ | Catalog không có dịch vụ này | Không |
| `thu-gian-cham-soc-toc/11.png` | Peel peptide da đầu, đoạn giới thiệu | Slide không có giá; có câu về tế bào, ngứa, mẩn đỏ | Catalog không có dịch vụ này | Không |
| `thu-gian-cham-soc-toc/12.png` | Quy trình "Peel da đầu", 3 bước | Ba bước, bước thứ ba in "Điện tim sát khuẩn" | Catalog không có dịch vụ này | Không |
| `thu-gian-cham-soc-toc/13.png` | Mặt nạ tóc Bồ kết (trong khung "Mask collection") | "60,000 VNĐ", không in thời lượng | Catalog không có sản phẩm này | Không |
| `thu-gian-cham-soc-toc/13.png` | Mặt nạ cho mặt Mask dẻo Hàn Quốc Collagen | "50,000 VNĐ", không in thời lượng | Catalog không có sản phẩm này | Không |
| `thu-gian-cham-soc-toc/13.png` | Mặt nạ Phục hồi PDRN | "90,000 VNĐ", không in thời lượng | Catalog không có sản phẩm này | Không |
| `thu-gian-cham-soc-toc/14.png` | Option "DETOX DA ĐẦU" | "50,000 VNĐ", không có dấu cộng, không in thời lượng | Catalog chỉ có Detox da đầu là dịch vụ riêng 40 phút, giá 139.000đ hoặc 159.000đ | Không |
| `thu-gian-cham-soc-toc/14.png` | Option "MASSAGE MẶT" | "10 phút: +50,000 VNĐ" | Catalog không có mục này | Không |
| `thu-gian-cham-soc-toc/14.png` | Option "MASSAGE TAY" | "10 phút: +50,000 VNĐ" | Catalog không có mục này | Không |
| `thu-gian-cham-soc-toc/14.png` | Option "MASSAGE CỔ, VAI, GÁY" | "30 phút: +199,000 VNĐ", không in khung giờ | `massage-co-vai-gay` 30 phút: 199.000đ trước 20h30, 239.000đ sau 20h30; catalog không ghi đây là option | Một phần |
| `thu-gian-cham-soc-toc/14.png` | Option "MASSAGE CHÂN" | "30 phút: +199,000 VNĐ" | `massage-chan` 30 phút: 199.000đ cho cả khung 9h-24h; catalog không ghi đây là option | Giá khớp; vai trò option chưa có |

Câu dẫn của slide 14 là "Có thể lựa chọn một hoặc nhiều option yêu thích để nâng cấp trải nghiệm của mình." Slide không nói option được cộng vào dịch vụ nào. Slide 13 cũng không nói mặt nạ là sản phẩm bán lẻ hay là bước thêm trong một dịch vụ.

### Các bước in trên ảnh

Bảy bước của Detox da đầu (slide 4) là: Chải đầu bằng dụng cụ; Ấn huyệt mặt; Detox da đầu với muối dược liệu, massage đầu; Gội sạch với hà thủ ô, bồ kết 2 lần; Massage 2 tay; Xã phục hồi; Sấy tóc, xịt bưởi.

Tám bước của Gội đầu thư giãn (slide 7) là: Chải đầu bằng dụng cụ; Ủ dược liệu khu vực tóc thưa mỏng; Ấn huyệt mặt; Giãn cơ vai cổ thư giãn; Gội sạch với hà thủ ô, bồ kết 2 lần; Xã phục hồi; Massage 2 tay; Sấy tóc, xịt bưởi.

Mười bước của Chăm sóc nan tóc (slide 9) là: Chải đầu bằng dụng cụ; Ủ dược liệu kích mọc tóc; Massage mặt, ấn huyệt mặt; Massage vai cổ; Sử dụng muối thảo dược giảm rụng; Gội nước thảo dược khu vực cần chăm sóc; Gội sạch với hà thủ ô, bồ kết; Massage tay thư giãn; Xả phục hồi; Sấy tóc - Xịt bưởi.

Ba bước của Peel da đầu (slide 12) là: Chải dụng cụ kích hoạt nan tóc; Peel hoạt chất vào vùng da đầu cần chăm sóc; Điện tim sát khuẩn.

## Menu triệt lông: ảnh in gì, catalog ghi gì?

Catalog và các bản chép chữ chưa có dòng nào về triệt lông. Vì vậy, mọi dòng trong bảng dưới đều không khớp.

| Ảnh | Vùng, tên như in trên ảnh | Ảnh in, mục "SUẤT LẺ" | Ảnh in, mục "COMBO - 20 Buổi" | Catalog ghi | Khớp |
|---|---|---|---|---|---|
| `hair-removal-triet-long/1.png` | Bìa "Triệt lông" | Bìa không có giá | Bìa không có giá | Catalog không có triệt lông | Không |
| `hair-removal-triet-long/2.png` | Nách | 150,000 VNĐ | 2,000,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/2.png` | Mép - Cằm - Trán | 100,000 VNĐ | 999,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/2.png` | Viền bi - Ngực | 180,000 VNĐ | 1,800,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/2.png` | Mặt - Tay - Cổ - Nữa Chân | 290,000 VNĐ | 2,900,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/2.png` | Bikini - Chân - Bụng - Lưng | 340,000 VNĐ | 3,400,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/2.png` | Full body | 1,800,000 VNĐ | 18,000,000 VNĐ | Catalog không có vùng này | Không |
| `hair-removal-triet-long/3.png` | Phiếu thông tin khách, tiêu đề "THOMHOUSE" | Phiếu không có giá và không có tên dịch vụ | Phiếu không có giá | Catalog không có mục tương ứng | Không áp dụng |

Slide 2 không in thời lượng, khung giờ, tên máy, các bước làm hay lưu ý trước và sau khi triệt. Slide 2 cũng không có dòng tên studio và địa chỉ như các slide khác. Bảng giá ghi mỗi dòng nhiều vùng nối bằng gạch ngang, và slide không nói giá đó tính cho từng vùng hay cho cả nhóm vùng.

Slide 3 là phiếu ghi thông tin khách, không phải menu. Phiếu có các ô: tên hoặc biệt danh khách muốn được nhớ, dị ứng, lực (yếu, vừa, mạnh), mang thai, tai nhạy cảm, lưu ý, vùng tập trung, vùng cần tránh, gói dịch vụ, kỹ thuật viên, "Today+++", cào nhiều, massage nhiều, gãi móng, gãi thịt, khách hàng phản hồi. Các ô "tai nhạy cảm", "gãi móng", "gãi thịt" không ăn khớp với triệt lông. Tôi không biết phiếu này dùng cho dịch vụ nào.

## Catalog và bản chép lệch với ảnh ở đâu?

Tôi xếp theo mức ảnh hưởng tới câu trả lời của chatbot, việc nặng nhất đứng đầu.

1. Catalog thiếu dịch vụ Peel peptide da đầu. Slide 10 in giá 299.000đ, thời lượng 15 phút, không chia khung giờ. Khách hỏi dịch vụ này thì chatbot hiện chỉ trả lời được là chưa có thông tin.
2. Catalog thiếu cả menu triệt lông với 12 mức giá (slide 2 của thư mục triệt lông). Đây là menu có mức giá cao nhất tôi thấy trong hai thư mục: Full body combo 20 buổi giá 18.000.000đ.
3. Catalog thiếu năm option nâng cấp trên slide 14. Trong số đó, option "DETOX DA ĐẦU" giá 50.000đ trùng tên với dịch vụ Detox da đầu 40 phút giá 139.000đ hoặc 159.000đ. Nếu chỉ thêm option vào catalog mà không đặt tên khác, chatbot có thể báo nhầm giá 50.000đ cho dịch vụ 40 phút.
4. Option "MASSAGE CỔ, VAI, GÁY" 30 phút in giá +199.000đ và không in khung giờ. Dịch vụ riêng cùng tên trong catalog có giá 199.000đ trước 20h30 và 239.000đ sau 20h30. Ảnh không cho biết option này sau 20h30 tính giá nào.
5. Catalog thiếu ba mặt nạ trên slide 13: Mặt nạ tóc Bồ kết 60.000đ, Mặt nạ cho mặt Mask dẻo Hàn Quốc Collagen 50.000đ, Mặt nạ Phục hồi PDRN 90.000đ. Ảnh không in thời lượng và không nói đây là hàng bán lẻ hay bước thêm trong dịch vụ.
6. Bước thứ chín của Chăm sóc nan tóc trên slide 9 in "Xả phục hồi". Bản chép ghi "Xã phục hồi" ở `batch-05-hair-care-menu.md` dòng 164, và catalog chép lại nguyên chữ đó trong `process_steps_vi`. Đây là lỗi chép, không phải lỗi trên ảnh. Ghi chú `conflicts` của `detox-da-dau` nói "Menu ghi 'Xã'" vẫn đúng cho slide 4 và slide 7, nhưng không đúng cho slide 9.
7. Bản chép `batch-05` ghi nguồn là 9 ảnh, trong khi thư mục Drive có 14 ảnh. Năm slide 10 đến 14 chưa từng được chép, nên catalog đếm nhóm `hair` có 3 dịch vụ (`counts.by_group.hair`).
8. Ảnh in tên dịch vụ là "nan tóc" trên ba slide: bìa slide 8, tiêu đề quy trình slide 9 ("Chăm Sóc Nan Tóc") và bước đầu của Peel trên slide 12 ("kích hoạt nan tóc"). Catalog ghi đúng như ảnh. Chữ "nang tóc" (bộ phận nuôi sợi tóc dưới da đầu) chỉ là đề xuất sửa trong bản chép, chủ studio chưa xác nhận.
9. Slide 4 và slide 7 in "Xã phục hồi", slide 9 in "Xả phục hồi". Như vậy chính ảnh dùng hai cách viết cho cùng một bước; catalog khớp ảnh ở từng slide trừ slide 9 (mục 6).
10. Dịch vụ Peel có hai tên trên ảnh: bìa slide 10 in "Peel peptide da đầu", còn tiêu đề quy trình slide 12 in "Peel da đầu".
11. Bước thứ ba của Peel trên slide 12 in "Điện tim sát khuẩn", chữ "tim" không có dấu sắc. Tôi đã phóng to để xác nhận. Tôi suy ra đây có thể là "điện tím", tên một loại máy dòng điện cao tần ánh tím mà các spa dùng, nhưng căn cứ duy nhất là chữ "sát khuẩn" đi kèm. Chủ studio cần xác nhận tên máy trước khi chatbot nhắc tới.
12. Bảng triệt lông in "Nữa Chân" ở cả hai mục. Cách viết thường gặp là "nửa chân". Bảng cũng dùng chữ "Viền bi", không có giải thích.
13. Giá combo Nách lệch khỏi quy luật của bảng. Năm dòng còn lại có giá combo 20 buổi bằng đúng 10 lần giá suất lẻ, hoặc gần đúng (Mép - Cằm - Trán: 999.000đ so với 10 x 100.000đ = 1.000.000đ). Dòng Nách có giá combo 2.000.000đ, bằng khoảng 13,3 lần giá suất lẻ 150.000đ; nếu theo quy luật, giá sẽ là 1.500.000đ. Đây là phép tính của tôi, chưa phải bằng chứng lỗi in, nên chatbot vẫn phải báo đúng số trên ảnh cho tới khi chủ studio xác nhận.
14. Bốn dịch vụ thư giãn trong catalog (`mo-vai-nang-mat`, `massage-chan`, `massage-co-vai-gay`, `massage-body-thu-gian`) không có slide nào trong hai thư mục tôi đọc, dù tên thư mục Drive có chữ "Thư giãn". Massage chân 30 phút và Massage cổ, vai, gáy 30 phút chỉ xuất hiện dưới dạng option trên slide 14. Massage chân 45 phút, Massage cổ, vai, gáy 60 phút, Mở Vai – Nâng Mặt và Massage body thư giãn không xuất hiện. Tôi không mở các thư mục khác, nên chưa biết bốn dịch vụ này có ảnh gốc ở đâu.
15. Catalog gắn cờ thiếu ba câu trên ảnh: "lành tính" (slide 3), "sợ gội đầu đêm ngấm lạnh sương ốm" và "Tóc yếu, thưa rụng vì guồng quay bận rộn bỏ bê chăm sóc" (slide 6). Mục tiếp theo liệt kê đủ.
16. Tài liệu `sources/drive/knowledge-base/03-pricing-structure.md` dòng 91 ghi Detox da đầu 139.000đ là "Giá vào đầu rẻ nhất toàn studio". Ảnh gốc có các mức thấp hơn: option Detox da đầu 50.000đ, mặt nạ collagen 50.000đ, triệt lông Mép - Cằm - Trán 100.000đ. Chatbot không được nhắc câu "rẻ nhất" từ tài liệu đó.
17. Thư mục triệt lông chứa slide 3 là phiếu thông tin khách (đã mô tả ở trên). Phiếu này không phải dịch vụ, nhưng có ô "Mang thai" và "Dị ứng", tức là studio có hỏi khách hai điều này ở ít nhất một dịch vụ.

## Những câu trên ảnh chatbot không được nhắc lại

Các câu dưới đây in trên chính menu, nhưng hứa tác dụng lên sức khỏe, dọa bệnh hoặc khẳng định sản phẩm an toàn. Chatbot nên chỉ đọc tên, giá, thời lượng và tên các bước; câu hỏi về tác dụng, độ an toàn hay tình trạng da đầu thì chuyển cho nhân viên.

- Slide 3 (Detox da đầu): "sẽ rất dễ bệnh đấy" là câu dọa bệnh, catalog đã gắn cờ. Chữ "lành tính" khẳng định độ an toàn, catalog chưa gắn cờ.
- Slide 6 (Gội đầu thư giãn): "dễ nhiễm lạnh lại hay sinh bệnh" (catalog đã gắn cờ) và "sợ gội đầu đêm ngấm lạnh sương ốm" (chưa gắn cờ) đều là câu dọa bệnh. Dòng "Tóc yếu, thưa rụng" mô tả người nên dùng dịch vụ; chatbot không được biến dòng này thành lời hứa giảm rụng tóc.
- Slide 9 (Chăm sóc nan tóc): hai bước "Ủ dược liệu kích mọc tóc" và "Sử dụng muối thảo dược giảm rụng" hứa mọc tóc và giảm rụng. Catalog đã gắn cờ. Nếu chatbot phải đọc tên bước, nên đọc kèm câu bên em không cam kết kết quả mọc tóc, như `research/01-knowledge-audit.md` dòng 181 đã đề xuất.
- Slide 11 (Peel peptide da đầu): "những tác nhân gây rụng ẩn sâu trong tế bào" là lời giải thích kiểu y học không có nguồn. Dòng "những cơn ngứa và tình trạng da đầu mẩn đỏ, nhạy cảm" nói về tình trạng da; khách kể triệu chứng này thì chatbot phải chuyển nhân viên, không gợi ý Peel.
- Slide 12 (Peel da đầu): "kích hoạt nan tóc" hứa tác dụng lên nang tóc. "Điện tim sát khuẩn" vừa hứa diệt khuẩn, vừa nêu một tên máy chưa rõ (mục 11 ở trên).
- Slide 13 (mặt nạ): "Dưỡng tóc chắc khỏe, giảm gãy rụng", "cấp ẩm sâu, tăng đàn hồi", "Phục hồi và tái tạo da, làm dịu tổn thương", và bốn nhãn "Lành tính an toàn", "Nguyên liệu chọn lọc", "Không chứa paraben", "Cho mọi loại da & tóc". Câu "Cho mọi loại da" và "an toàn" là khẳng định tuyệt đối; "Không chứa paraben" là thông tin thành phần mà dự án chưa có giấy tờ nào để đối chiếu.
- Slide 14 (option): "kích thích lưu thông máu" (Massage tay), "Giảm đau cổ vai gáy" và "cải thiện lưu thông máu" (Massage cổ, vai, gáy), "cải thiện giấc ngủ" (Massage chân), "giảm căng thẳng, tê mỏi tay". Các câu này hứa tác dụng lên cơ thể.
- Menu triệt lông không in câu hứa tác dụng nào. Tuy vậy, ảnh cũng không in tên máy, số buổi cần thiết hay đối tượng không nên làm. Chatbot không được tự nói triệt vĩnh viễn, không được nêu loại máy, và phải chuyển nhân viên khi khách hỏi về thai kỳ, da nhạy cảm hay độ đau.

## Anh cần quyết những gì?

### Việc 1: tên "nan tóc" và các chữ có thể in sai

Việc này cần anh quyết vì chatbot sẽ in nguyên tên dịch vụ cho khách. Nếu giữ "nan tóc", tên khớp với ảnh khách đang xem, nhưng chatbot in chữ "nan" trong khi tiếng Việt thường viết "nang tóc". Nếu sửa thành "nang tóc", chữ đúng chính tả, nhưng lệch với ảnh menu khách đã thấy. Tôi đề xuất hỏi chủ studio; trong lúc chờ, catalog giữ "nan tóc" và thêm "nang tóc" làm từ khóa tìm kiếm để khách gõ chữ nào cũng ra dịch vụ. Điểm yếu của cách này là chatbot vẫn hiển thị chữ có thể sai. Cùng cách xử lý áp cho "Xã/Xả phục hồi", "Nữa Chân" và "Điện tim": catalog chép đúng từng slide (riêng slide 9 sửa thành "Xả phục hồi" cho khớp ảnh) cho tới khi chủ studio xác nhận.

### Việc 2: có đưa các mục mới vào catalog không

Nếu thêm ngay Peel peptide, mặt nạ, option và triệt lông theo ảnh, chatbot báo được giá cho khách. Nếu chưa thêm, chatbot sẽ nói chưa có thông tin và chuyển nhân viên mọi câu hỏi về các mục này. Tôi đề xuất thêm ngay Peel peptide da đầu và 12 mức giá triệt lông với trạng thái `draft_unapproved`, vì ảnh đã in rõ tên và giá. Tôi đề xuất chờ chủ studio nói rõ cách tính rồi mới thêm mặt nạ và option, vì ảnh không cho biết option cộng vào dịch vụ nào và mặt nạ là hàng bán lẻ hay bước thêm. Điểm yếu: dữ liệu triệt lông không có thời lượng, nên trường `duration_min` sẽ trống; tôi chưa kiểm tra code báo giá trong `apps/server` xử lý trường trống ra sao. Sau khi sửa `data/services.json`, cần chạy lại `apps/server/scripts/gen-seed-data.mjs`, vì dòng đầu của `apps/server/src/seed-data.ts` ghi file này được sinh từ `data/services.json`; tôi chưa chạy lệnh đó.

### Việc 3: giá combo Nách

Anh hỏi chủ studio xem combo 20 buổi vùng Nách là 2.000.000đ hay 1.500.000đ. Cho tới khi có câu trả lời, chatbot báo 2.000.000đ như ảnh.

### Việc 4: option Massage cổ, vai, gáy sau 20h30

Anh hỏi chủ studio xem option 30 phút giá +199.000đ có tăng lên 239.000đ sau 20h30 như dịch vụ riêng không. Cho tới khi có câu trả lời, chatbot chỉ nên báo +199.000đ kèm câu nhân viên sẽ xác nhận giá nếu khách đặt sau 20h30.

### Việc 5: phiếu thông tin khách trong thư mục triệt lông

Anh hỏi chủ studio phiếu này dùng cho dịch vụ nào. Phiếu không ảnh hưởng tới bảng giá, nhưng các ô "tai nhạy cảm", "gãi móng", "gãi thịt" gợi ý studio có một dịch vụ mà catalog chưa có.

## Nói ngắn gọn nhất

Giá, thời lượng và khung giờ của ba dịch vụ tóc trong catalog đúng với ảnh gốc, nên chatbot báo giá ba dịch vụ này được. Trong chín slide đã chép, tôi chỉ thấy một chữ lệch với ảnh: bước thứ chín của Chăm sóc nan tóc in "Xả phục hồi", còn catalog ghi "Xã phục hồi". Vấn đề lớn hơn là phần chưa chép: Peel peptide da đầu, ba mặt nạ, năm option nâng cấp và 12 mức giá triệt lông đều có trên ảnh nhưng chưa có trong catalog. Nhiều câu mô tả trên chính các slide mới này hứa tác dụng lên tóc, da và tuần hoàn máu, nên khi thêm vào catalog, chatbot chỉ nên dùng tên, giá và thời lượng. Trước khi thêm, anh cần chủ studio xác nhận tên "nan tóc", giá combo Nách, giá option sau 20h30 và cách tính option, mặt nạ.

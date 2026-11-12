# Mẫu tin cảm ơn, hỏi thăm, khuyến mãi và xác nhận yêu cầu đặt lịch

Ngày viết: 2026-11-07. Trạng thái: bản nháp, chưa được chủ doanh nghiệp duyệt, chưa nộp mẫu nào cho Zalo. Tài liệu đi cùng `design/conversation-design.md`, mục "Hỏi thăm sau buổi làm".

## Phần anh cần duyệt

Tài liệu có năm mẫu: cảm ơn sau buổi làm, hỏi thăm sau 2–3 ngày, liên lạc lại sau 1 tháng, thông báo khuyến mãi và xác nhận đã nhận yêu cầu đặt lịch. Mỗi mẫu có hai bản. Bản chat dùng khi khách vừa nhắn OA trong khung gửi Tin Tư vấn và xưng *em – anh/chị* như đề xuất ở tài liệu thiết kế hội thoại. Bản ZBS dùng khi OA chủ động gửi qua mẫu tin được Zalo duyệt; bản này gọi khách là *bạn* và studio tự xưng *thom house*, vì quy định duyệt mẫu của Zalo cấm cụm *anh/chị* trong mẫu.

Mỗi mẫu là văn bản cố định có chỗ điền biến. Model không soạn tin chủ động theo từng khách; server điền biến vào mẫu đã duyệt. Cách này giữ được lời lẽ đã duyệt và khớp với cơ chế mẫu ZBS.

Anh cần quyết ba việc:

1. Có giữ câu hướng dẫn chăm sóc sau buổi làm trong tin cảm ơn hay không. Menu chỉ nói Thải hàn giải cảm có hướng dẫn giữ ấm tại nhà (batch-02:298) mà không ghi nội dung. Các hướng dẫn ở tài liệu 07 (không uống đồ lạnh 2–3 ngày, 48 giờ đầu tránh quan hệ sau Yoni Retreat) chưa được xác nhận là quy định của studio. Tôi để trống biến `<aftercare_note>` cho tới khi anh duyệt từng câu.
2. Câu từ chối nhận tin. Tôi đề xuất khách nhắn chữ "Ngừng". Bản ZBS không cho viết tắt và không cho ký tự đặc biệt, nên chữ này phải viết đủ, có dấu.
3. Tin liên lạc lại sau 1 tháng có được gửi hay không. Tin này có tính chất mời quay lại, nên theo nhánh pháp lý cần đồng ý nhận khuyến mãi, và theo Zalo phải dùng mẫu Tag 3.

## Ràng buộc chung cho mọi mẫu

Các ràng buộc dưới đây lấy từ quy định duyệt mẫu ZBS bản 10/2026 (`research/snapshots/zalo-2026-11-07/zalo-solutions-zbs-template-review-rules.txt`, đọc ngày 2026-11-07) và từ checklist của nhánh pháp lý.

| Ràng buộc | Áp cho | Nguồn |
|---|---|---|
| Không dùng cụm *anh/chị*; dùng *bạn* hoặc biến giới tính | Bản ZBS | dòng 113 |
| Không chèn link hay số điện thoại trong thân tin; link và hotline đặt ở nút thao tác | Bản ZBS | dòng 93, 117 |
| Không viết tắt, không dùng icon và ký tự đặc biệt | Bản ZBS | dòng 94, 95 |
| Tiếng Việt có dấu, một ngôn ngữ | Bản ZBS | dòng 89, 90 |
| Tham số đặt trong `<` và `>`, không dấu, các từ nối bằng dấu gạch dưới, có tiền tố giải thích tham số | Bản ZBS | dòng 110–112, 114 |
| Tag 1 và Tag 2 bắt buộc có tên khách hoặc một tham số cá nhân hóa, và ít nhất một tham số định danh giao dịch | Mẫu cảm ơn, hỏi thăm, xác nhận đặt lịch | dòng 182–183 (Tag 1), 220–221 (Tag 2) |
| Tag 3 không hứa kết quả điều trị, không dùng "nhất", "duy nhất", "tốt nhất", "số một" khi không có tài liệu chứng minh | Mẫu liên lạc lại, khuyến mãi | dòng 264–265 |
| Không nói dịch vụ chữa, ngừa, làm giảm bệnh; không nói triệu chứng sau buổi làm "là bình thường" | Mọi bản | `research/07-vn-legal-compliance.md`; tài liệu 07 dòng 203, 220 |
| Mỗi tin khuyến mãi có cách từ chối; chỉ gửi cho khách đã đồng ý; khung 7h–22h; tối đa 3 tin trong 24 giờ | Mẫu liên lạc lại, khuyến mãi | `research/07-vn-legal-compliance.md` (áp Nghị định 91/2020 cho Zalo là suy luận của nhánh pháp lý) |
| Không emoji | Mọi bản | Đề xuất trong `design/system-prompt-draft.md` |

Các biến dùng chung:

| Biến | Nghĩa | Lấy từ đâu |
|---|---|---|
| `<customer_name>` | Tên khách dùng khi đặt lịch | `booking_requests.customer_name` hoặc hồ sơ khách |
| `<service_name>` | Tên dịch vụ đã duyệt | `display_name_vi` của danh mục đang dùng |
| `<visit_date>` | Ngày làm dịch vụ, dạng 08/11/2026 | `visit.completed` |
| `<booking_code>` | Mã yêu cầu đặt lịch hoặc mã buổi làm | `booking_requests.id` rút gọn |
| `<requested_time>` | Ngày giờ khách mong muốn | `booking_requests` |
| `<aftercare_note>` | Một câu hướng dẫn sau buổi làm đã duyệt cho dịch vụ đó; để trống nếu chưa có | Bảng hướng dẫn sau buổi làm do chủ doanh nghiệp duyệt (chưa có) |
| `<promo_text>`, `<valid_until>`, `<promo_conditions>` | Nội dung, hạn dùng và điều kiện của chương trình đã duyệt | Bảng `promotions` ở trạng thái `approved` |

Bản chat dùng biến dạng `{customer_name}` vì do server điền trước khi gửi Tin Tư vấn; bản ZBS dùng dạng `<customer_name>` theo quy định của Zalo.

## Mẫu 1. Cảm ơn sau buổi làm

Mục đích: cảm ơn khách, hỏi cảm giác, nhắc khách báo lại khi có điều bất thường.

Thời điểm: 20–24 giờ sau khi nhân viên đánh dấu buổi làm đã xong, gửi trong khung 9h–20h. Nếu mốc 24 giờ rơi vào ban đêm, gửi lúc 9h sáng hôm sau.

Điều kiện: khách đã đồng ý nhận tin hỏi thăm; hội thoại không ở trạng thái nhân viên tiếp quản hay đã chuyển nhân viên; khách chưa báo vấn đề nào về buổi làm.

Loại tin Zalo (chờ nhánh nghiên cứu Zalo xác nhận): Đề xuất mẫu ZBS Tag 1 "Cảm ơn/Xác nhận sau một giao dịch cụ thể". Bản chat chỉ dùng khi khách đã tự nhắn OA trong 48 giờ trước đó và nhánh Zalo xác nhận việc này không bị coi là dùng sai mục đích Tin Tư vấn.

Bản chat:

```text
Dạ em chào {customer_name}, em là trợ lý AI của thom house. Cảm ơn anh/chị đã ghé làm {service_name} hôm {visit_date} ạ.
Sau buổi làm anh/chị thấy trong người thế nào ạ?
{aftercare_note}
Nếu anh/chị thấy khó chịu, đau tăng hoặc có biểu hiện lạ, anh/chị nhắn bên em ngay, và đi khám nếu thấy nặng ạ.
Anh/chị không muốn nhận tin hỏi thăm nữa thì nhắn "Ngừng" giúp em ạ.
```

Bản ZBS (Tag 1):

```text
thom house cảm ơn bạn <customer_name> đã sử dụng dịch vụ <service_name> ngày <visit_date>, mã buổi làm <booking_code>.
<aftercare_note>
Nếu bạn thấy khó chịu, đau tăng hoặc có biểu hiện lạ sau buổi làm, bạn hãy nhắn cho thom house qua Zalo này, và đi khám nếu thấy nặng.
Nếu không muốn nhận tin chăm sóc sau buổi làm, bạn nhắn "Ngừng" cho thom house.
```

Nút thao tác đề xuất cho bản ZBS: "Nhắn cho thom house" (mở cuộc trò chuyện với OA).

## Mẫu 2. Hỏi thăm sau 2–3 ngày

Mục đích: hỏi cảm giác sau vài ngày và mời khách cho ý kiến về buổi làm. Mẫu không kèm ưu đãi và không mời đặt lịch, để tin giữ tính chất chăm sóc, không thành tin quảng cáo (ranh giới này là suy luận của nhánh pháp lý).

Thời điểm: ngày thứ 2 hoặc thứ 3 sau buổi làm, trong khung 9h–20h.

Điều kiện: như mẫu 1, cộng thêm điều kiện khách chưa trả lời có vấn đề ở tin cảm ơn. Nếu khách đã trả lời tin cảm ơn rằng mọi thứ ổn, vẫn gửi được nhưng có thể bỏ qua theo lựa chọn của anh.

Loại tin Zalo (chờ nhánh nghiên cứu Zalo xác nhận): Đề xuất mẫu ZBS Tag 2, nhóm "Khảo sát nhu cầu/ý kiến đánh giá của khách hàng về dịch vụ (cần có phát sinh giao dịch rõ ràng)". Từ 15/10/2026, Tag 2 chỉ gửi trong khung 7h–22h.

Bản chat:

```text
Dạ em chào {customer_name}, em là trợ lý AI của thom house. Đã vài ngày từ buổi {service_name} hôm {visit_date}, em hỏi thăm anh/chị đã thấy ổn chưa ạ?
Anh/chị có góp ý gì về buổi làm, bên em rất muốn được nghe ạ.
Nếu có điều gì khó chịu, anh/chị nhắn em để nhân viên liên hệ ạ.
Anh/chị không muốn nhận tin hỏi thăm nữa thì nhắn "Ngừng" giúp em ạ.
```

Bản ZBS (Tag 2):

```text
Chào bạn <customer_name>, thom house xin hỏi thăm sau buổi <service_name> ngày <visit_date>, mã buổi làm <booking_code>.
Sau vài ngày, bạn cảm thấy thế nào? thom house mong nhận được góp ý của bạn về buổi làm.
Nếu có điều gì khó chịu, bạn hãy nhắn cho thom house qua Zalo này để nhân viên liên hệ.
Nếu không muốn nhận tin chăm sóc sau buổi làm, bạn nhắn "Ngừng" cho thom house.
```

Nút thao tác đề xuất: "Gửi góp ý" (mở cuộc trò chuyện với OA).

## Mẫu 3. Liên lạc lại sau 1 tháng

Mục đích: hỏi thăm nhẹ và cho khách biết studio sẵn sàng khi khách muốn quay lại. Mẫu không hỏi "khi nào quay lại" và không thúc đặt lịch (tài liệu 07 dòng 225–231).

Thời điểm: khoảng ngày thứ 30 sau buổi làm, trong khung 9h–20h, không gửi vào ngày khách đã nhận một tin khuyến mãi khác.

Điều kiện: khách đã đồng ý nhận tin khuyến mãi và chưa từ chối; khách chưa có buổi làm hay yêu cầu đặt lịch mới; không có khiếu nại đang mở. Khách không trả lời tin này thì không nhắn thêm.

Loại tin Zalo (chờ nhánh nghiên cứu Zalo xác nhận): Đề xuất mẫu ZBS Tag 3 (hậu mãi, mời quay lại); chịu trần 1 tin/ngày và 30 tin/tháng mỗi khách. Tin Tư vấn không gửi được vì quá 7 ngày kể từ tương tác cuối, trừ khi khách vừa nhắn OA.

Bản chat (chỉ dùng khi khách vừa tự nhắn OA):

```text
Dạ em chào {customer_name}, em là trợ lý AI của thom house. Đã khoảng một tháng từ buổi {service_name} của anh/chị, em hỏi thăm anh/chị dạo này vẫn khỏe chứ ạ?
Khi nào anh/chị muốn có một khoảng nghỉ, anh/chị cứ nhắn em ạ.
Anh/chị không muốn nhận tin từ thom house nữa thì nhắn "Ngừng" giúp em ạ.
```

Bản ZBS (Tag 3):

```text
Chào bạn <customer_name>, đã khoảng một tháng từ buổi <service_name> ngày <visit_date> của bạn tại thom house.
thom house gửi lời hỏi thăm và luôn sẵn sàng khi bạn muốn có một khoảng nghỉ.
Nếu không muốn nhận tin từ thom house, bạn nhắn "Ngừng" cho thom house.
```

Nút thao tác đề xuất: "Xem menu" (link tới trang menu đã duyệt, khi có).

## Mẫu 4. Thông báo khuyến mãi

Mục đích: báo một chương trình đã được chủ doanh nghiệp duyệt. Hiện `data/business-facts.json` ghi khuyến mãi là `missing`, nên mẫu này chỉ là khung.

Thời điểm: do người tạo chiến dịch chọn, trong khung 9h–20h; không gửi cho một khách quá 1 tin khuyến mãi trong 14 ngày (đề xuất của nhánh kiến trúc), và không vượt trần của Zalo.

Điều kiện: chương trình ở trạng thái `approved` và còn hạn; khách đã đồng ý nhận khuyến mãi và chưa từ chối; khách không có `minor_flag`; không dùng thông tin sức khỏe khách kể để chọn người nhận, trừ khi khách đã đồng ý riêng cho mục đích đó (`research/07-vn-legal-compliance.md`).

Nội dung chương trình không được: nói dịch vụ chữa hay ngừa bệnh; dùng "nhất", "duy nhất", "số một" khi không có chứng minh; dùng tên dịch vụ có nhắc bệnh mà chưa được duyệt cho mẫu Tag 3. Tài liệu 07 dòng 50 và 233 cũng dặn tránh "giảm 50%", "sale" và tránh nhắn khuyến mãi liên tục; nhánh pháp lý ghi mức giảm tối đa 50% theo Nghị định 128/2024, mới đọc qua bài viết thứ cấp.

Loại tin Zalo (chờ nhánh nghiên cứu Zalo xác nhận): Mẫu ZBS Tag 3 gửi qua API, hoặc Tin Broadcast gửi tay từ OA Manager cho người đang quan tâm OA (gói Tăng trưởng có 4 tin Broadcast miễn phí mỗi người mỗi tháng; Broadcast không gửi được qua API).

Bản chat (chỉ khi khách hỏi về ưu đãi; chatbot chép nguyên văn từ công cụ):

```text
Dạ hiện bên em có chương trình sau ạ:
{promo_text}
Áp dụng đến {valid_until}. Điều kiện: {promo_conditions}
Anh/chị muốn em ghi yêu cầu đặt lịch để nhân viên xác nhận không ạ?
```

Bản ZBS (Tag 3):

```text
Chào bạn <customer_name>, thom house gửi bạn thông tin chương trình <promo_name>.
Nội dung: <promo_text>
Thời hạn: đến hết ngày <valid_until>.
Điều kiện áp dụng: <promo_conditions>
Nếu không muốn nhận tin ưu đãi từ thom house, bạn nhắn "Ngừng" cho thom house.
```

## Mẫu 5. Xác nhận đã nhận yêu cầu đặt lịch

Mục đích: báo khách rằng yêu cầu đã được ghi và nhân viên sẽ xác nhận giờ. Mẫu không được nói lịch đã được giữ.

Thời điểm: ngay sau khi `create_booking_request` trả trạng thái `created` (bản chat). Bản ZBS chỉ dùng khi khách gửi yêu cầu qua kênh khác (điện thoại, Fanpage) và chưa nhắn OA.

Điều kiện: yêu cầu ở trạng thái `new`.

Loại tin Zalo: Tin Tư vấn cho bản chat. Bản ZBS (chờ nhánh nghiên cứu Zalo xác nhận): mẫu ZBS Tag 1 "Xác nhận đặt hàng/đặt lịch hẹn/đặt chỗ"; cần số điện thoại của khách hoặc UID.

Bản chat (do model soạn theo khung này, không phải mẫu cố định):

```text
Dạ em đã ghi nhận yêu cầu đặt lịch của anh/chị ạ:
- Dịch vụ: {service_name}
- Thời gian mong muốn: {requested_time}
- Số người: {party_size}
Nhân viên bên em sẽ nhắn xác nhận giờ trong cuộc trò chuyện này ạ. Lịch chỉ được giữ sau khi nhân viên xác nhận.
```

Bản ZBS (Tag 1):

```text
thom house đã nhận yêu cầu đặt lịch của bạn <customer_name>, mã yêu cầu <booking_code>.
Dịch vụ: <service_name>
Thời gian mong muốn: <requested_time>
Nhân viên thom house sẽ liên hệ để xác nhận giờ. Lịch chỉ được giữ sau khi nhân viên xác nhận.
```

Tin xác nhận đặt lịch là tin giao dịch, không phải tin quảng cáo, nên tôi không thêm câu từ chối nhận tin. Nếu anh muốn đồng nhất, có thể thêm câu "Nếu bạn không đặt lịch này, bạn nhắn cho thom house để hủy yêu cầu."

## Khi khách trả lời một mẫu tin, server làm gì?

| Khách trả lời | Server làm gì |
|---|---|
| "Ngừng", "ngung", "dừng", "stop", "đừng nhắn nữa" | Ghi từ chối cho loại tin vừa gửi (tin chăm sóc hoặc khuyến mãi), hủy các tin còn lại cùng loại, gửi một câu xác nhận. Không gọi model nếu chỉ có từ khóa này |
| Cảm thấy ổn, cảm ơn | Model trả lời ngắn theo ý định `followup_reply_positive` |
| Kể khó chịu, đau, phản ứng | Model gọi `handoff_to_staff` với mức `urgent`; server hủy tin hỏi thăm còn lại |
| Hỏi đặt lịch | Model theo luồng ghi nhận yêu cầu đặt lịch |
| Khiếu nại | Model gọi `handoff_to_staff` với mức `urgent`; server dừng mọi tin chủ động tới khách này cho tới khi nhân viên mở lại |

Khi khách trả lời, khách vừa tương tác với OA, nên các câu trả lời tiếp theo đi bằng Tin Tư vấn trong khung 48 giờ.

## Nói ngắn gọn nhất

Năm mẫu tin đều có hai bản: bản chat xưng *em – anh/chị* cho lúc khách vừa nhắn, và bản ZBS gọi khách là *bạn* vì Zalo cấm *anh/chị* trong mẫu. Không mẫu nào nói triệu chứng sau buổi làm là bình thường, không mẫu nào hứa tác dụng lên bệnh, và mọi tin chủ động trừ tin xác nhận đặt lịch đều có câu từ chối nhận tin. Tin cảm ơn đi theo Tag 1, hỏi thăm theo Tag 2, mời quay lại và khuyến mãi theo Tag 3, nhưng loại tin cụ thể còn chờ nhánh Zalo xác nhận. Anh cần duyệt câu hướng dẫn sau buổi làm cho từng dịch vụ, chữ từ chối "Ngừng" và việc có gửi tin sau 1 tháng hay không.

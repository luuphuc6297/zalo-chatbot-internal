# Zalo OA cho chatbot của thom house: nền tảng cho phép gì, tốn bao nhiêu, cần chuẩn bị gì

Ngày tra cứu: 2026-11-07. Mọi nguồn trong tài liệu này là trang chính thức của Zalo (docs.zaloplatforms.com, developers.zalo.me, oa.zalo.me, zalo.solutions) và được đọc vào ngày này. Bản chép văn bản của các trang đó nằm trong thư mục `research/snapshots/zalo-2026-11-07/`. Từ đây trở đi, tôi gọi thư mục này là `snap/` và trích dẫn theo dạng `snap/<tên file>:<dòng>`.

## Phần anh cần duyệt

Chatbot của thom house làm được qua kênh chính thức của Zalo, với ba điều kiện. OA phải được xác thực bằng giấy đăng ký kinh doanh. OA phải mua gói Tăng trưởng trở lên, giá 1.400.000đ cho 6 tháng hoặc 2.500.000đ cho 1 năm, đã gồm VAT. Máy chủ nhận tin phải chạy liên tục, có domain HTTPS và trả lời mỗi sự kiện Zalo gửi tới trong tối đa 2 giây.

Chatbot được trả lời khách miễn phí trong 48 giờ kể từ lần cuối khách tương tác với OA. Từ giờ thứ 48 đến ngày thứ 7, mỗi tin trả lời tốn 55đ sau khi dùng hết 500 tin có sẵn mỗi tháng của gói. Sau 7 ngày, API không cho gửi tin trả lời nữa.

Ba việc chủ động là cảm ơn, hỏi thăm sau buổi làm và nhắc lịch. Ba việc này phải đi qua ZBS Template Message, tức mẫu tin soạn trước và được Zalo duyệt. Giá công bố là 200đ một tin gửi qua số điện thoại, chưa gồm VAT. Gửi qua UID rẻ hơn, nhưng trang giá không ghi con số cụ thể. Tin khuyến mãi cũng phải dùng mẫu, và mỗi khách nhận tối đa 1 tin mỗi ngày, 30 tin mỗi tháng.

Anh cần quyết hai việc. Việc thứ nhất là chọn danh mục OA: "Mỹ phẩm và làm đẹp" hay "Y tế". Danh mục "Y tế" đòi giấy phép khám chữa bệnh. Việc thứ hai là quyết các tin khuyến mãi có nhắc đến hiệu quả chăm sóc sức khỏe hay không, vì Zalo chặn các mẫu tin hứa hẹn kết quả điều trị khi không có giấy tờ chứng minh.

Điểm yếu của hướng này: công thức ký webhook trong tài liệu Zalo chưa được thử trên một OA thật. Hai repo tham khảo cũng đang dùng một công thức khác với tài liệu. Ngoài ra, giá gửi qua UID không được công bố. Hai việc này cần thử trên OA thật trước khi chốt thiết kế.

## Các khái niệm dùng trong tài liệu

Tài liệu này dùng nhiều tên riêng của Zalo, và mỗi tên được định nghĩa một lần trong bảng sau. Sau bảng, mỗi tên chỉ có một nghĩa như trong bảng.

| Tên | Nghĩa trong tài liệu này |
|---|---|
| OA (Official Account) | Tài khoản chính thức của doanh nghiệp trên Zalo. Khách nhắn tin với OA giống như nhắn với một người. |
| OA xác thực | OA đã nộp giấy đăng ký kinh doanh và được Zalo duyệt. Chỉ OA xác thực mới nhắn tin, dùng chatbot và dùng API được. |
| OA Manager | Trang web và mini app do Zalo làm sẵn, để nhân viên chat với khách bằng tay. |
| OpenAPI | Bộ API để phần mềm của thom house đọc và gửi tin thay cho OA. Chatbot sẽ dùng bộ API này. |
| Zalo App | Một "ứng dụng" tạo trên developers.zalo.me. Zalo App đại diện cho phần mềm của thom house; OA cấp quyền cho Zalo App để Zalo App gọi OpenAPI. |
| ZBS Account | Tài khoản ví để trả tiền cho gói OA và tin có phí. Trước 01/01/2026, tài khoản này tên là Zalo Cloud Account (ZCA). |
| UID | Mã định danh của một khách, riêng cho từng OA. OA chỉ có UID của khách sau khi khách tương tác với OA. |
| Tương tác | Hành động khách chủ động làm với OA mà Zalo tính là cho phép OA nhắn lại, ví dụ nhắn tin, gọi điện, bấm menu, quan tâm OA. Một buổi khách đến spa không phải là tương tác theo nghĩa này. |
| Tin Tư vấn | Tin OA trả lời khách khi khách hỏi. Đây là loại tin chatbot dùng nhiều nhất. |
| Tin Broadcast | Tin gửi đồng loạt tới người đang quan tâm OA, chỉ gửi được từ OA Manager bản web. |
| ZBS Template Message | Tin theo mẫu soạn trước, Zalo duyệt từng mẫu. Gửi được qua UID hoặc qua số điện thoại. Mẫu chia ba nhãn mục đích: Tag 1 (giao dịch), Tag 2 (chăm sóc khách hàng), Tag 3 (hậu mãi, tức khuyến mãi và bán thêm). |
| ZNS | Tên cũ của tin mẫu gửi qua số điện thoại. Từ 01/01/2026, ZNS được gộp vào ZBS Template Message. |
| Webhook | Địa chỉ HTTPS trên máy chủ của thom house. Zalo gọi vào địa chỉ này mỗi khi có sự kiện, ví dụ khách gửi tin. |
| Access token, refresh token | Hai chuỗi bí mật Zalo App dùng để gọi API. Access token hết hạn nhanh; refresh token dùng để xin access token mới. |
| PKCE | Cách xin quyền OAuth có thêm một mã bí mật do máy chủ tự tạo, để người khác không dùng lại được mã cấp quyền bị lộ. |

## OA cần loại nào và gói nào thì chatbot mới gửi tin qua API được?

OA phải là OA xác thực. Hướng dẫn tạo OA chia hai loại tài khoản. "Hồ sơ quảng cáo" dành cho người chưa có giấy đăng ký kinh doanh và không nhắn tin, không dùng chatbot được (`snap/oa-zalo-me-guides_khoi-tao-zalo-official-account_61.txt:30`). "OA xác thực" dành cho doanh nghiệp hoặc hộ kinh doanh có giấy đăng ký kinh doanh. Khi OA chưa xác thực mà gọi API, Zalo trả mã lỗi -221 (`snap/zaloplatforms-OA-llms-full.txt:13188`).

OA xác thực còn phải mua gói Tăng trưởng hoặc Toàn diện. Trang bảng giá trả lời thẳng câu hỏi này: muốn liên kết ứng dụng với OA qua API thì cần gói Tăng trưởng hoặc Toàn diện (`snap/zalo-solutions-oa-pricing.txt:249`). Bảng so sánh gói cũng ghi hai gói Cơ bản và Tiêu chuẩn không có mục "Tích hợp Zalo Open API". Khi gói chưa đủ, API trả mã lỗi -224 (`snap/zaloplatforms-OA-llms-full.txt:13191`). Bộ gói mới áp dụng từ 01/06/2026. Các gói cũ Nâng cao và Premium dừng bán từ cùng ngày (`snap/zaloplatforms-OA-llms-full.txt:9165`).

Chatbot dựng sẵn của Zalo trong OA Manager (Zalo Chatbot, chạy theo kịch bản) cũng chỉ mở ở gói Tăng trưởng và Toàn diện (`snap/oa-zalo-me-guides_huong-dan-su-dung-zalo-chatbot.txt:30`). Chatbot của thom house chạy ngoài Zalo, nên không phụ thuộc tính năng này. Hai thứ dùng chung một điều kiện về gói.

## Zalo App được tạo và liên kết với OA thế nào, token sống bao lâu?

Quy trình gồm năm bước, theo tài liệu "Xác thực và ủy quyền cho Ứng dụng" (`snap/zaloplatforms-OA-llms-full.txt:151` trở đi).

1. Người quản trị đăng nhập developers.zalo.me bằng tài khoản Zalo cá nhân và tạo Zalo App.
2. Trong phần cài đặt của Zalo App, người quản trị khai báo callback URL, tạo code challenge theo PKCE và chọn nhóm quyền cần xin. Zalo App có thể xin chín nhóm quyền. Chatbot cần bốn nhóm: quyền gửi tin, quyền quản lý tin nhắn người dùng, quyền quản lý thông tin OA và quyền nhận sự kiện tin nhắn.
3. Người quản trị OA mở đường dẫn cấp quyền, chọn OA và bấm "Cho phép". Zalo chuyển trình duyệt về callback URL kèm `code` và `oa_id`.
4. Máy chủ gọi `POST https://oauth.zaloapp.com/v4/oa/access_token`, gửi `secret_key` của Zalo App trong header, gửi `code`, `app_id`, `grant_type=authorization_code` và `code_verifier` trong body.
5. Zalo trả về `access_token`, `refresh_token` và `expires_in` = 90000 giây.

Tài liệu cũng cho một cách lấy token bằng tay qua công cụ API Explorer. Cách này chỉ dành cho người quản trị OA hoặc người quản trị Zalo App, nên chỉ hợp để thử nghiệm.

Thời hạn và quy tắc dùng token như sau, tất cả trích từ cùng tài liệu:

| Loại mã | Hiệu lực | Quy tắc dùng | Nguồn |
|---|---|---|---|
| Authorization code | 10 phút | Dùng được 1 lần | `snap/zaloplatforms-OA-llms-full.txt:169` |
| Access token | 25 giờ | Hết hiệu lực ngay khi access token mới được tạo thành công | `:176`, `:186` |
| Refresh token | 3 tháng | Dùng được 1 lần. Sau khi dùng, refresh token cũ bị vô hiệu và Zalo trả refresh token mới | `:184`, `:185`, `:187` |

Hệ quả cho thiết kế: máy chủ phải lưu refresh token mới vào cơ sở dữ liệu ngay khi nhận được, trước khi làm việc khác. Nếu máy chủ dùng refresh token rồi mất bản mới do lỗi ghi, người quản trị OA phải cấp quyền lại từ đầu. Hai tiến trình cùng refresh một lúc cũng sẽ làm hỏng chuỗi token, nên việc refresh cần một khóa dùng chung.

Một OA chỉ được cấp quyền cho số Zalo App giới hạn theo gói. Gói Tăng trưởng cho 3 Zalo App, gói Toàn diện không giới hạn (`snap/zalo-solutions-oa-pricing.txt:126`). Zalo App còn có thể bật yêu cầu `appsecret_proof`, tức một chữ ký HMAC-SHA256 của access token dùng secret key của Zalo App làm khóa, gửi kèm mỗi lần gọi API (changelog v240409, developers.zalo.me). Đây là lớp bảo vệ thêm, không bắt buộc.

Từ 06/03/2026, các nhóm quyền ZBS được tách lại. Muốn gửi Tin Tư vấn hoặc gửi mẫu ZBS qua UID, Zalo App cần "quyền gửi tin nhắn" và "quyền nhận sự kiện quản lý tin nhắn". Muốn gửi mẫu qua số điện thoại, Zalo App cần thêm "quyền gửi tin qua SĐT". Muốn tạo và sửa mẫu, Zalo App cần "quyền quản lý Message Template" (changelog V260306, developers.zalo.me).

## Webhook nhận gì, được ký thế nào, phải trả lời trong bao lâu?

### Yêu cầu vận hành

Tài liệu webhook đặt bốn yêu cầu (`snap/zaloplatforms-OA-llms-full.txt:9240`–`9290`). Webhook nên dùng domain có HTTPS, không dùng dạng host:port. OA phải cấp access token cho Zalo App thì Zalo App mới nhận được sự kiện. Máy chủ phải trả HTTP 200 cho mọi sự kiện, và trả trong tối đa 2 giây (`:9275`). Nếu không đạt, người quản lý Zalo App nhận cảnh báo qua Zalo.

Zalo chỉ gửi lại sự kiện khi không mở được kết nối tới webhook. Các lần gửi lại cách lần đầu 30 giây, 5 phút, 15 phút, 30 phút và 1 giờ, kèm header `num_retry` (`:9285`). Nếu webhook vẫn hỏng sau các lần đó, Zalo hủy đăng ký nhận sự kiện của Zalo App, và người quản trị phải bật lại trong trang cài đặt. Tài liệu không nói Zalo có gửi lại khi máy chủ trả lỗi 500 hay trả chậm hơn 2 giây hay không.

Domain dùng cho các dịch vụ của Zalo Platform phải được xác thực trước bằng một trong ba cách: thêm bản ghi DNS TXT, tải tệp HTML lên website, hoặc thêm thẻ meta vào trang chủ (`snap/zaloplatforms-OA-llms-full.txt:12951`). Tài liệu không nói rõ webhook URL có bắt buộc nằm trong danh sách domain đã xác thực hay không. Tôi đề xuất xác thực domain từ đầu để tránh bị chặn khi cấu hình.

Hệ quả cho thiết kế: máy chủ nên ghi sự kiện vào cơ sở dữ liệu rồi trả 200 ngay, sau đó mới gọi model. Một lượt gọi Claude thường lâu hơn 2 giây, nên không thể gọi model trong lúc Zalo đang chờ phản hồi.

### Chữ ký sự kiện

Mọi trang mô tả sự kiện webhook đều ghi cùng một công thức. Header tên là `X-ZEvent-Signature`, giá trị là `mac = sha256(appId + data + timeStamp + OAsecretKey)`, trong đó `data` là chuỗi JSON của sự kiện (`snap/zaloplatforms-OA-llms-full.txt:9301`). Tôi đã đối chiếu thêm trang gốc trên developers.zalo.me (khung tài liệu ở stc-developers.zdn.vn) bằng trình duyệt; trang này ghi cùng công thức.

Công thức này là SHA-256 của một chuỗi ghép, không phải HMAC với khóa bí mật. Tài liệu để ngỏ bốn chi tiết. Thứ nhất, `timeStamp` là trường `timestamp` trong JSON hay một giá trị khác. Thứ hai, `data` là nguyên văn body nhận được hay JSON đã chuẩn hóa. Thứ ba, `OAsecretKey` là khóa nào; tài liệu chỉ có hướng dẫn lấy secret key của Zalo App (`snap/zaloplatforms-OA-llms-full.txt:12603`). Thứ tư, giá trị header có tiền tố `mac=` hay không. Bốn chi tiết này chỉ chốt được khi bắt một sự kiện thật từ một OA thật.

Hai repo tham khảo đều kiểm chữ ký bằng `createHmac("sha256", secretKey).update(body)`, tức HMAC của body, không ghép appId và timestamp (`sources/repos/zalo-agent-cli/src/commands/oa-listen.js:33`, `sources/repos/arden-zalo-agent-cli/src/commands/oa-listen.js:120`). Nếu tài liệu Zalo đúng, cách kiểm của hai repo sẽ từ chối sự kiện hợp lệ. Tôi chỉ đọc code, chưa chạy với OA thật.

### Các sự kiện liên quan

Mỗi sự kiện có `app_id`, `event_name` và `timestamp` tính bằng mili giây. Phần lớn sự kiện tin nhắn có `user_id_by_app`; trường này chỉ có khi Zalo App đang liên kết với OA nhận sự kiện (`snap/zaloplatforms-OA-llms-full.txt:9310`, `:9334`).

| Sự kiện (`event_name`) | Khi nào Zalo gửi | Trường cần lấy | Nguồn trong `snap/zaloplatforms-OA-llms-full.txt` |
|---|---|---|---|
| `user_send_text`, `user_send_image`, `user_send_link`, `user_send_audio`, `user_send_video`, `user_send_sticker`, `user_send_location`, `user_send_business_card`, `user_send_file` | Khách gửi tin tới OA | `sender.id` là UID của khách, `recipient.id` là OA, `message.msg_id`, `message.text`, `message.attachments`, `quote_msg_id` khi khách trả lời một tin cũ | `:9294`–`:9410` |
| `user_click_chatnow` | Khách bấm nút "Nhắn tin" trên trang OA lần đầu, chỉ 1 lần cho mỗi khách | `user_id`, `oa_id` | `:9433` |
| `follow`, `unfollow` | Khách quan tâm hoặc bỏ quan tâm OA | `follower.id`, `source` | `:10896` |
| `user_submit_info` | Khách điền và gửi mẫu yêu cầu thông tin | `info.name`, `info.phone`, `info.user_dob`, `info.gender`, `info.full_address` | `:10844` |
| `oa_send_text`, `oa_send_image`, `oa_send_gif`, `oa_send_list`, `oa_send_file`, `oa_send_sticker` | OA gửi tin, kể cả nhân viên gửi từ OA Manager | `sender.admin_id` chỉ có khi nhân viên gửi từ OA Manager | `:9583` |
| `user_received_message` | Tin của OA đã tới máy khách, chỉ khi khách dùng Zalo trên điện thoại | `message.msg_id` | `:9912` |
| `user_seen_message` | Khách đã xem tin, chỉ khi xem trên điện thoại, và chỉ gửi cho Zalo App đã gửi tin đó | `message.msg_ids` | `:9862` |
| `user_reacted_message` | Khách thả biểu tượng cảm xúc lên tin | `sender.id`, `message` | `:9475` |
| `widget_interaction_accepted` | Khách cấp quyền nhận tin qua widget trên website | `data.user_id`, `data.user_external_id` | `:11107` |
| `user_withdraw` | Khách yêu cầu rút đồng ý hoặc xóa dữ liệu; Zalo yêu cầu đối tác xóa dữ liệu tương ứng | `user_id`, `user_id_by_app` | `:11194` |

Sự kiện `oa_send_*` quan trọng cho chatbot. Khi nhân viên trả lời từ OA Manager, chatbot nhận được sự kiện này và biết nhân viên đã nhận cuộc trò chuyện, nhờ trường `admin_id`. Sự kiện `user_withdraw` liên quan nghĩa vụ xóa dữ liệu; phần pháp lý thuộc một track khác.

Trang cấu hình webhook có tùy chọn "Lọc cú pháp". Khi bật, webhook chỉ nhận tin văn bản bắt đầu bằng ký tự `#` (`snap/zaloplatforms-OA-llms-full.txt:9262`). Chatbot cần để tùy chọn này tắt.

## Mỗi loại tin được gửi khi nào và tốn bao nhiêu?

Từ 01/01/2026, Zalo chia tin của OA thành hai nhóm (`snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:25`). Nhóm "tin cơ bản" gồm Tin Tư vấn, tin gửi vào nhóm chat và Tin Broadcast. Nhóm "ZBS Template Message" gồm tin giao dịch và tin hậu mãi. Hai loại cũ là "Tin Giao dịch" (165đ một tin, không cần duyệt mẫu) và "Tin Truyền thông cá nhân" dừng từ 01/03/2026 (`snap/zaloplatforms-OA-llms-full.txt:2242`). Endpoint cũ `/v3.0/oa/message/transaction` và `/v3.0/oa/message/promotion` từ ngày đó chỉ nhận mẫu ZBS đã duyệt (changelog V251209).

| Loại tin | Dùng để làm gì | Điều kiện gửi | Công cụ | Giá | Giờ gửi | Mẫu cần duyệt |
|---|---|---|---|---|---|---|
| Tin Tư vấn | Trả lời và tư vấn khi khách hỏi | Khách có tương tác trong 7 ngày (qua OpenAPI) hoặc 365 ngày (qua OA Manager), và không chặn OA | OpenAPI, OA Manager | Miễn phí trong 48 giờ sau tương tác cuối; sau đó 55đ/tin, trừ vào hạn mức có sẵn của gói trước | 24/24 | Không |
| Lời chào | Chào khách vừa quan tâm OA hoặc vừa bấm "Nhắn tin" | Ngay sau hành động đó | OpenAPI (hạn mức `welcome_msg`), OA Manager | Không ghi giá riêng | 24/24 | Không |
| Tin Broadcast | Gửi đồng loạt nội dung chung, khuyến mãi | Khách đang quan tâm OA | Chỉ OA Manager bản web | Gói Tăng trưởng: mỗi người quan tâm nhận tối đa 4 tin miễn phí/tháng | 6h00–19h59 theo hướng dẫn OA; 6h00–21h59 theo tài liệu developer | Không, nhưng nội dung là bài viết OA |
| ZBS Template Tag 1, Giao dịch | Xác nhận lịch hẹn, cảm ơn sau giao dịch, nhắc hẹn | Khách đã phát sinh giao dịch với doanh nghiệp | OpenAPI (UID hoặc số điện thoại), công cụ chiến dịch | 200đ/tin qua số điện thoại, chưa VAT; qua UID thấp hơn | Mọi giờ | Có, 2–3 ngày làm việc |
| ZBS Template Tag 2, Chăm sóc khách hàng | Khảo sát, đánh giá dịch vụ, hướng dẫn sau khi dùng dịch vụ | Như Tag 1 | Như Tag 1 | Như Tag 1 | 7h–22h từ 15/10/2026 (dự kiến) | Có |
| ZBS Template Tag 3, Hậu mãi | Khuyến mãi, voucher, mời quay lại, mời quan tâm OA | Như Tag 1; mỗi khách nhận tối đa 1 tin/ngày và 30 tin/tháng từ một OA | Như Tag 1 | Như Tag 1; mẫu voucher 300đ | 7h–22h từ 15/10/2026 (dự kiến) | Có, thêm giấy tờ theo ngành |

Nguồn của từng ô:

- Tin Tư vấn: điều kiện 7 ngày và 365 ngày ở `snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:67`–`68`; giá ở `snap/zaloplatforms-OA-llms-full.txt:552` và `snap/zalo-solutions-oa-pricing.txt:184`; hạn mức 500 tin/tháng của gói Tăng trưởng và 2.000 tin/tháng của gói Toàn diện ở `snap/zalo-solutions-oa-pricing.txt:77` cùng các dòng ngay sau. Từ 01/01/2026, tin trong khung 48 giờ không còn giới hạn số lượng (`snap/zaloplatforms-OA-llms-full.txt:680`). Gửi ngoài 7 ngày bị lỗi -230 (`:13193`).
- Lời chào: `snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:65` và kiểu hạn mức `welcome_msg` ở `snap/zaloplatforms-OA-llms-full.txt:690`.
- Tin Broadcast: công cụ ở `snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:88`, giờ gửi ở `:91`; giờ gửi khác ở `snap/zaloplatforms-OA-llms-full.txt:2611`; hạn mức 4 tin ở `snap/oa-zalo-me-guides_cau-hoi-thuong-gap-tin-broadcast.txt:33`. Gói Cơ bản và Tiêu chuẩn không có Broadcast (`:32`).
- ZBS: định nghĩa ba Tag ở `snap/zalo-solutions-zbs-template-review-rules.txt:55`–`68`; điều kiện "đã phát sinh giao dịch" ở `:77`; giá ở `snap/zalo-solutions-zbs-pricing.txt:22` và `:57`, ghi chú chưa VAT ở `:80`, ghi chú UID rẻ hơn ở `:41`; thời gian duyệt mẫu ở `snap/oa-zalo-me-guides_cong-cu-gui-tin-theo-chien-dich_1154619161163221859.txt:84`; hạn mức Tag 3 ở `snap/zalo-solutions-zbs-quality-quota.txt:72`; giờ gửi theo changelog V261001 trên developers.zalo.me.

Ba quy tắc nằm ngoài bảng nhưng ảnh hưởng tới thiết kế. Thứ nhất, Zalo tính tin ZBS gửi qua UID ngay khi máy chủ Zalo xử lý thành công. Tin gửi qua số điện thoại chỉ bị tính khi tới máy khách trong thời hạn quy định, 7.200 giây với tin thường (`snap/zalo-solutions-zbs-billing-timeout.txt`). Thứ hai, khách không quan tâm OA vẫn nhận được tin Tag 3, nhưng tin rơi vào mục Business Box chứ không vào hộp thư chính (`snap/zalo-solutions-zbs-quality-quota.txt:79`). Thứ ba, mỗi OA mới bắt đầu với hạn mức 20.000 tin ZBS mỗi ngày. Hạn mức giảm khi tỉ lệ khách báo xấu cao; Zalo khuyên giữ tỉ lệ này dưới 0,1% mỗi ngày (`:59`, `:113`).

Tài liệu API có một ví dụ mẫu tin với `price_sdt` = 800 và `price_uid` = 560 (`snap/zaloplatforms-ZBS-llms-full.txt:753`). Đây chỉ là dữ liệu minh họa trong tài liệu, không phải bảng giá. Giá thật của từng mẫu đọc được qua API "Lấy thông tin chi tiết template" sau khi mẫu được duyệt.

Hai trang chính thức ghi giờ gửi Broadcast khác nhau: hướng dẫn OA ghi 6h00–19h59, còn tài liệu developer ghi 6h00–21h59. Hai con số hạn mức khác thì không mâu thuẫn. Chính sách tương tác đặt trần 30 tin/tháng cho mọi tin có mục đích truyền thông (`snap/oa-zalo-me-policy_tuong-tac-cua-oa-voi-nguoi-dung.txt:35`). Con số 4 tin/tháng chỉ là phần Broadcast miễn phí của gói. Trang câu hỏi thường gặp về Broadcast xác nhận cách hiểu này: tin Broadcast được tính chung vào trần tin truyền thông (`snap/oa-zalo-me-guides_cau-hoi-thuong-gap-tin-broadcast.txt:36`).

## Mỗi tình huống của thom house được gửi bằng loại tin nào?

Điểm quyết định nằm ở mốc thời gian tính từ lần cuối khách tương tác với OA, không tính từ buổi khách đến spa. Nếu khách đặt lịch qua điện thoại hoặc Facebook và không nhắn OA, OA không có UID của khách và không gửi được Tin Tư vấn.

Bảng dưới dùng bốn mức: "được" là gửi được và không tốn phí; "được, có phí" là gửi được và tốn tiền theo tin; "không được" là API sẽ từ chối; "chưa rõ" là tài liệu chưa đủ để kết luận.

| Tình huống | Loại tin nên dùng | Mức | Lý do và nguồn |
|---|---|---|---|
| Trả lời ngay khi khách nhắn | Tin Tư vấn | Được | Khách vừa tương tác, nên tin nằm trong khung 48 giờ miễn phí (`snap/zaloplatforms-OA-llms-full.txt:552`). |
| Nhân viên trả lời vào ngày hôm sau | Tin Tư vấn | Được nếu dưới 48 giờ; được, có phí nếu từ 48 giờ đến 7 ngày | Ngoài 48 giờ thì tốn 55đ/tin sau khi hết 500 tin có sẵn của gói Tăng trưởng (`snap/zalo-solutions-oa-pricing.txt:184`). Nếu nhân viên gửi từ OA Manager, khung là 365 ngày (`snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:67`). |
| Báo đã nhận yêu cầu đặt lịch | Tin Tư vấn khi khách đặt qua chat; ZBS Tag 1 "xác nhận đặt lịch hẹn" khi khách đặt qua kênh khác | Được (Tin Tư vấn); được, có phí (ZBS) | Tag 1 liệt kê đúng việc xác nhận đặt lịch hẹn (`snap/zalo-solutions-zbs-template-review-rules.txt:55`). |
| Cảm ơn 24 giờ sau buổi làm | ZBS Tag 1 "cảm ơn sau một giao dịch cụ thể" | Được, có phí | Mẫu này có trong Tag 1 (`snap/zalo-solutions-zbs-template-review-rules.txt:197`). Dùng Tin Tư vấn thì chưa rõ: Tin Tư vấn chỉ để trả lời khi khách yêu cầu, và chính sách cấm dùng sai mục đích loại tin (`snap/zaloplatforms-OA-llms-full.txt:549`; `snap/oa-zalo-me-policy_tuong-tac-cua-oa-voi-nguoi-dung.txt:34`). |
| Hỏi thăm sau 2–3 ngày | ZBS Tag 2 "khảo sát, đánh giá dịch vụ" hoặc "hướng dẫn dịch vụ đã dùng" | Được, có phí | Tag 2 cho phép khảo sát khi có giao dịch rõ ràng (`snap/zalo-solutions-zbs-template-review-rules.txt:246`). Tin Tư vấn thì chưa rõ, cùng lý do như trên. |
| Liên lạc lại sau 1 tháng | ZBS Tag 3 | Được, có phí, kèm điều kiện | Sau 7 ngày, Tin Tư vấn qua API bị lỗi -230. Mời khách quay lại là mục đích hậu mãi (`:68`), nên phải dùng Tag 3 và chịu trần 30 tin/tháng. |
| Báo chương trình khuyến mãi cho khách cũ | Tin Broadcast (người quan tâm OA, gửi tay từ OA Manager) hoặc ZBS Tag 3 (qua API hoặc công cụ chiến dịch) | Được (Broadcast, 4 tin/tháng); được, có phí (Tag 3) | Broadcast không gửi được qua API (`snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:88`). |
| Nhắc trước buổi hẹn | ZBS Tag 1 "nhắc hẹn"; Tin Tư vấn nếu khách vừa nhắn trong 48 giờ | Được, có phí (ZBS); được (Tin Tư vấn trong 48 giờ) | Nhắc hẹn nằm trong Tag 1 (`snap/zalo-solutions-zbs-template-review-rules.txt:202`). Tag 1 gửi được mọi giờ theo changelog V261001. |

## Các gói OA giá bao nhiêu và có gì?

Bảng giá dưới đây lấy từ trang zalo.solutions/oa/pricing, áp dụng từ 01/06/2026 (`snap/zalo-solutions-oa-pricing.txt:230`). Trang ghi mọi chi phí trên trang đã gồm VAT 10% (`:211`). Bảng giá ZBS Template Message là trang khác và ghi giá chưa gồm VAT (`snap/zalo-solutions-zbs-pricing.txt:80`).

| Hạng mục | Cơ bản | Tiêu chuẩn | Tăng trưởng | Toàn diện |
|---|---|---|---|---|
| Giá | Miễn phí | 1.000.000đ/năm | 1.400.000đ/6 tháng hoặc 2.500.000đ/năm | 3.400.000đ/6 tháng hoặc 6.000.000đ/năm |
| Tích hợp OpenAPI | Không | Không | Có | Có |
| Giới hạn gọi API của OA | Không áp dụng | Không áp dụng | 100 request/phút | 2.000 request/phút |
| Số Zalo App được cấp quyền | 1 | 1 | 3 | Không giới hạn |
| Tin Tư vấn ngoài 48 giờ có sẵn mỗi tháng | Không | Không | 500 | 2.000 |
| Broadcast miễn phí mỗi người quan tâm mỗi tháng | Không | Không | 4 | 4 |
| Zalo Chatbot dựng sẵn | Không | Không | Có, 10 kịch bản | Có, 50 kịch bản |
| Số nhân viên quản lý OA | 3 | 5 | 15 | 100 |

Nguồn của từng dòng trong `snap/zalo-solutions-oa-pricing.txt`: giá ở `:17`, `:27`, `:36`, `:45`, `:55`; giới hạn API ở `:121`–`124`; số Zalo App ở `:126`; Tin Tư vấn có sẵn ở `:77`; Broadcast ở `:145`. Tôi xác định cột của từng con số bằng cách đọc cấu trúc HTML của bảng. Ô nào ghi "---" là gói đó không có tính năng.

Ngoài giới hạn theo OA, mỗi Zalo App còn bị giới hạn 4.000 request/phút cho Official Account API. Vượt giới hạn thì API trả lỗi -32. Mỗi phản hồi có header `X-RateLimit-Limit` và `X-RateLimit-Remain` (`snap/zaloplatforms-OA-llms-full.txt:12714`, `:12731`). Giới hạn theo OA không tính API gửi ZBS Template Message.

Gói đã mua không được hoàn tiền và không chuyển sang OA khác. Khi gói hết hạn mà không gia hạn, OA quay về gói Cơ bản và mất quyền API (mục câu hỏi thường gặp trên cùng trang).

## OpenAPI còn có gì dùng được cho thom house?

Phần này liệt kê các API mà chatbot có thể cần, kèm giới hạn đã ghi trong tài liệu.

- Hồ sơ khách: `GET https://openapi.zalo.me/v3.0/oa/user/detail` trả tên hiển thị, ảnh đại diện, trạng thái quan tâm, ngày tương tác cuối, nhãn và ghi chú, thông tin khách đã chia sẻ. Trường `is_sensitive` = true nghĩa là tài khoản dưới 18 tuổi (`snap/zaloplatforms-OA-llms-full.txt:7792`, `:7876`). Chatbot nên kiểm trường này trước khi tư vấn dịch vụ cho phụ nữ hoặc gửi khuyến mãi.
- Xin số điện thoại và thông tin: Tin Tư vấn dạng `template_type` = `request_user_info` hiện một mẫu để khách tự điền. Khi khách gửi, webhook nhận `user_submit_info` (`:1482`, `:10844`). Đây là cách chính thống để có số điện thoại của khách với sự đồng ý của khách.
- Nhãn khách hàng: các API gắn nhãn, gỡ nhãn và lấy danh sách nhãn (`:7463` trở đi). Nhãn giúp lọc tập gửi Broadcast và chiến dịch ZBS.
- Trường thông tin tùy biến: lưu thuộc tính riêng của thom house cho từng khách, ví dụ dịch vụ đã dùng (`:8021` trở đi).
- Nút bấm: tối đa 5 nút mỗi tin. Kiểu `oa.query.show` và `oa.query.hide` gửi một chuỗi ngược về OA khi khách bấm, nên dùng được làm câu trả lời nhanh. Kiểu `oa.open.url` và `oa.open.phone` mở link và mở cuộc gọi (`:12751` trở đi).
- Ảnh và tệp: ảnh jpg hoặc png tối đa 1 MB; tệp PDF, DOC, DOCX hoặc CSV tối đa 5 MB (`:935`, `:3842`). Tin văn bản dài tối đa 2.000 ký tự (`:649`).
- Kiểm tra hạn mức trước khi gửi: `POST https://openapi.zalo.me/v3.0/oa/quota/message` với `user_id` trả thời điểm tương tác cuối và hạn mức tin truyền thông còn lại của khách đó (`:3459`). Chatbot nên gọi API này ngay trước khi gửi để biết tin còn miễn phí hay đã tốn phí.
- Lịch sử hội thoại: API lấy tin gần nhất và tin trong một hội thoại (`:3524`, `:3622`).

Các mã lỗi chatbot cần xử lý riêng: -216 và -220 (token hỏng hoặc hết hạn), -230 và -232 (ngoài khung tương tác), -227 (khách bị khóa hoặc không online quá 45 ngày), -234 (loại tin này không gửi được từ 22 giờ đến 7 giờ), -244 (khách đã chặn loại tin này), -248 (vi phạm tiêu chuẩn nền tảng), -320 và -321 (chưa nối ZBS Account hoặc hết tiền). Bảng mã lỗi nằm ở `snap/zaloplatforms-OA-llms-full.txt:13162`–`13214`.

## Những gì đã thay đổi trong 2025–2026?

Danh sách thay đổi lấy từ trang lịch sử cập nhật của developers.zalo.me, đọc bằng trình duyệt ngày 2026-11-07.

- V251115: từ 30/11/2025, quyền sở hữu mẫu tin chuyển về OA.
- V251209: từ 01/01/2026 ra mắt ZBS Template Message, gộp tin UID Giao dịch, tin UID Truyền thông và ZNS. Zalo Cloud Account đổi tên thành ZBS Account. Tin UID Giao dịch và UID Truyền thông theo mẫu cũ dừng từ 01/03/2026. Mẫu ZNS tạo trước 10/12/2025 không gửi được qua UID.
- 01/01/2026: Tin Tư vấn trong 48 giờ không còn giới hạn số lượng; API ngừng trả trường `remain` và `total` sau 01/03/2026 (`snap/zaloplatforms-OA-llms-full.txt:680`).
- V260306: tách nhóm quyền ZNS thành quyền gửi qua số điện thoại và quyền quản lý mẫu tin.
- 01/06/2026: bộ gói OA mới Cơ bản, Tiêu chuẩn, Tăng trưởng, Toàn diện; gói Nâng cao và Premium dừng bán.
- V260907: bổ sung domain mới cho ảnh đại diện. Tôi chỉ đọc tiêu đề của mục này, chưa đọc nội dung.
- V261001: ZBS Template Message dần hiển thị trên Zalo PC và Web từ tháng 10/2026; từ 15/10/2026, Tag 2 và Tag 3 chỉ gửi được từ 7 giờ đến 22 giờ.

API gửi tin V2 đã ngừng từ 20/06/2023; gọi API V2 trả lỗi -240 (`snap/zaloplatforms-OA-llms-full.txt:13200`, changelog v230418). Tôi không tìm thấy thông báo nào về việc đổi định dạng UID trong danh sách lịch sử cập nhật, và tìm kiếm web cũng không ra nguồn chính thức nào nói việc này.

## Zalo quy định gì về tin tự động, spam và nội dung sức khỏe?

### Tin tự động và spam

Chính sách tương tác của OA cấm gửi tin, "bằng cách thủ công hoặc tự động", có nội dung, tần suất hoặc ngữ cảnh không phù hợp (`snap/oa-zalo-me-policy_tuong-tac-cua-oa-voi-nguoi-dung.txt:28`). Chính sách cũng cấm nội dung sai lệch hoặc chưa kiểm chứng (`:32`) và cấm dùng sai mục đích các loại tin. Zalo tính số lần vi phạm trong 12 tuần gần nhất để chọn mức xử lý. Chính sách khóa OA có bốn mức, từ cảnh báo tới khóa vĩnh viễn và chặn các OA khác của cùng doanh nghiệp (`snap/oa-zalo-me-policy_khoa-tai-khoan.txt`). OA không hoạt động 180 ngày cũng có thể bị khóa (`:26`).

Tôi không tìm thấy quy định riêng về chatbot dùng AI hay nghĩa vụ báo cho khách biết họ đang nói chuyện với máy. Tôi đã tìm trong các trang chính sách và hướng dẫn đã tải, gồm chính sách tương tác, đăng ký và sử dụng, xác thực, khóa tài khoản và các trang về chatbot. Tôi chưa đọc điều khoản dịch vụ chung của Zalo.

### Nội dung sức khỏe

Quy định duyệt mẫu ZBS bản 10/2026 có ba điểm trực tiếp liên quan thom house.

Điểm thứ nhất: mẫu Tag 3 không được dùng từ tuyệt đối như "nhất", "duy nhất", "tốt nhất", "số một" khi không có tài liệu chứng minh. Mẫu Tag 3 cũng không được hứa chắc kết quả điều trị bệnh hay triệu chứng (`snap/zalo-solutions-zbs-template-review-rules.txt:265`).

Điểm thứ hai: Zalo xếp spa thành nhiều nhóm theo hoạt động (`:384`–`397`). Spa có massage kèm vật lý trị liệu phải nộp giấy phép kinh doanh và chứng chỉ hành nghề bác sĩ của người chịu trách nhiệm chuyên môn. Spa, tiệm cắt tóc, gội đầu, làm móng không có vật lý trị liệu thì chưa cần nộp thêm giấy tờ. Quảng bá dịch vụ khám chữa bệnh cần giấy xác nhận nội dung quảng cáo hoặc giấy phép khám chữa bệnh (`:423`).

Điểm thứ ba: mọi mẫu không được dùng "anh/chị" để xưng hô; mẫu phải dùng biến giới tính hoặc từ trung tính như "bạn", "quý khách" (`:113`). Mẫu cũng không được chèn link hay số điện thoại vào thân tin, và không được dùng icon hay ký tự đặc biệt (`:93`, `:95`).

Điểm thứ ba ảnh hưởng tới mâu thuẫn xưng hô trong tài liệu thương hiệu (nhận định K4 của báo cáo trước). Mẫu ZBS không dùng được "anh/chị", nên giọng của tin mẫu sẽ khác giọng chatbot trong Tin Tư vấn, bất kể chủ quán chọn cách xưng hô nào.

Tài liệu của thom house tự nhận là "healing studio", không phải cơ sở y tế, và người sáng lập không phải bác sĩ (`sources/drive/documentation/11-deep-knowledge-techniques-herbs.md:11`). Tài liệu này cũng có tên dịch vụ như "Tiêu u – Thông kinh ngực" và "Thiếu máu não – chăm sóc vai cổ" (`sources/drive/documentation/11-deep-knowledge-techniques-herbs.md:1432`, `sources/drive/documentation/07-customer-journey.md:265`). Đây là suy luận của tôi: người duyệt mẫu Tag 3 có thể coi các tên dịch vụ này là lời hứa điều trị, và mẫu có thể bị từ chối hoặc bị đòi giấy tờ y tế. Chưa có mẫu nào được nộp thử để kiểm chứng.

## Checklist đăng ký OA cho thom house

Các bước dưới đây theo thứ tự làm. Thời gian là con số Zalo công bố, chưa phải thời gian đo thực tế.

1. Chọn người quản trị OA. Người này cần tài khoản Zalo cá nhân đã xác thực bằng số điện thoại Việt Nam (+84) (`snap/oa-zalo-me-guides_khoi-tao-zalo-official-account_61.txt:37`).
2. Chuẩn bị giấy chứng nhận đăng ký kinh doanh, bản scan hoặc ảnh chụp bản gốc, đủ các trang, có dấu và chữ ký của cơ quan cấp. Hộ kinh doanh không dùng được "công văn xác thực" thay giấy đăng ký (`snap/oa-zalo-me-guides_huong-dan-xac-thuc_70.txt:35`, `:40`). Chuẩn bị thêm họ tên và số CCCD của người đại diện pháp luật.
3. Đặt tên OA theo dạng tiền tố, tên chính, hậu tố. Nếu tên "thom house" khác tên trên giấy đăng ký kinh doanh, cần nộp thêm một "yếu tố kinh doanh". Với nhóm thẩm mỹ, y tế, Zalo chấp nhận ảnh bảng hiệu, ảnh website, bài báo hoặc hồ sơ Google Business có tên trùng tên OA (`snap/oa-zalo-me-guides_y-te-duoc-pham_4364617168068169566.txt:47` trở đi).
4. Chọn danh mục. Danh mục "Mỹ phẩm và làm đẹp" ghi rõ spa, massage, làm đẹp không xâm lấn và không điều trị (`snap/oa-zalo-me-guides_lua-chon-danh-muc_5083845785359174113.txt:61`). Danh mục "Y tế" gồm y học cổ truyền, đông y, vật lý trị liệu và cần giấy phép khám chữa bệnh (`:110`; `snap/oa-zalo-me-guides_ho-so-xac-thuc_74.txt:47`). Nếu ngành của thom house là ngành kinh doanh có điều kiện, cần nộp thêm giấy phép ngành đó. Danh sách ngành có điều kiện của Zalo nằm trong một tệp Google Drive tôi chưa mở.
5. Nộp hồ sơ xác thực trong 14 ngày kể từ khi tạo OA. Zalo duyệt trong 2–3 ngày làm việc; một trang khác ghi 1–2 ngày (`snap/oa-zalo-me-guides_huong-dan-xac-thuc_70.txt:30`, `:55`; `snap/oa-zalo-me-guides_ho-so-xac-thuc_74.txt:29`). Nếu bị từ chối, phải nộp lại trong 14 ngày; quá hạn thì OA bị khóa vĩnh viễn (`snap/oa-zalo-me-policy_dang-ky-va-su-dung-tai-khoan-zalo-official-account-doanh-nghiep.txt:41`).
6. Tạo ZBS Account, nạp tiền, liên kết ZBS Account với OA. Người làm bước này phải là quản trị viên của cả OA và ZBS Account.
7. Mua gói Tăng trưởng.
8. Tạo Zalo App trên developers.zalo.me, chuyển Zalo App sang trạng thái "Đang hoạt động" (nếu không, API trả lỗi -209), liên kết Zalo App với ZBS Account, đăng ký Official Account API.
9. Xác thực domain của máy chủ, cấu hình callback URL và webhook URL dạng HTTPS, bật các sự kiện cần nhận, tắt "Lọc cú pháp".
10. Người quản trị OA cấp quyền cho Zalo App qua luồng OAuth v4 có PKCE. Máy chủ lưu access token và refresh token.
11. Soạn và nộp mẫu ZBS: Tag 1 cho xác nhận lịch, cảm ơn và nhắc hẹn; Tag 2 cho khảo sát; Tag 3 cho khuyến mãi. Mỗi mẫu được duyệt trong 2–3 ngày làm việc. Logo cần bản nền sáng và bản nền tối. Số hotline không có đầu 1800 hoặc 1900 thì cần bằng chứng công khai đó là số của doanh nghiệp (`snap/zalo-solutions-zbs-template-review-rules.txt:102`, `:118`).
12. Thiết lập tin chào mừng và menu trong OA Manager.

Một tùy chọn cho giai đoạn thử nghiệm là OA Test. Zalo chỉ tạo OA Test khi doanh nghiệp đã có một OA xác thực. OA Test tối đa 100 người quan tâm, không hiện khi tìm kiếm, và được duyệt trong tối đa 2 ngày làm việc sau khi gửi email cho oa@zalo.me. Sau khi được duyệt, doanh nghiệp có 7 ngày để liên kết Zalo App và thử nghiệm (`snap/oa-zalo-me-guides_tao-tai-khoan-oa-thu-nghiem-ky-thuat_4023591696049457534.txt:25`, `:51`). Tài liệu không nói OA Test có cần mua gói Tăng trưởng hay không.

Ước tính của tôi, chưa đo: nếu giấy tờ đủ ngay từ đầu, từ lúc tạo OA tới lúc gửi được Tin Tư vấn qua API mất khoảng 1 tuần, và tới lúc có mẫu ZBS đầu tiên được duyệt mất khoảng 1–2 tuần.

## Kiểm chứng các nhận định Z1–Z5, R6, R8 của báo cáo trước

| Mã | Nhận định | Kết luận | Bằng chứng |
|---|---|---|---|
| Z1 | Tin Tư vấn qua OpenAPI gửi được trong 7 ngày từ tương tác cuối, miễn phí 48 giờ đầu, tốn phí sau 48 giờ; OA Manager có khung khác | Đúng | Khung 07 ngày qua OpenAPI và 365 ngày qua OA Manager (`snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:67`–`68`); miễn phí trong 48 giờ (`snap/zaloplatforms-OA-llms-full.txt:552`). |
| Z2 | Chỉ quan tâm OA thì chưa đủ để gửi mọi Tin Tư vấn | Đúng | Khi khách quan tâm OA hoặc bấm "Nhắn tin", OA chỉ được gửi lời chào (`snap/oa-zalo-me-guides_tong-quan-cac-loai-tin-nhan.txt:65`); tin đó dùng hạn mức riêng `welcome_msg` (`snap/zaloplatforms-OA-llms-full.txt:690`). |
| Z3 | Nhắc lịch và khuyến mãi phải dùng đúng loại tin; ZBS Template là mẫu có tham số do Zalo duyệt; có mẫu chưa có nghĩa là khách nào cũng nhận được | Đúng | Mẫu được định nghĩa trước và được duyệt (`snap/zaloplatforms-ZBS-llms-full.txt:71`); chỉ gửi tới khách đã có giao dịch (`snap/zalo-solutions-zbs-template-review-rules.txt:77`); Tag 3 tối đa 30 tin/tháng mỗi khách (`snap/zalo-solutions-zbs-quality-quota.txt:72`). |
| Z4 | Access token sống 25 giờ; refresh token chỉ dùng 1 lần | Đúng | `snap/zaloplatforms-OA-llms-full.txt:176`, `:184`. Bổ sung: refresh token sống 3 tháng và được thay mới mỗi lần dùng (`:185`, `:187`). |
| Z5 | Gói Tăng trưởng 1.400.000đ/6 tháng hoặc 2.500.000đ/năm đã gồm VAT, có API; Tin Tư vấn ngoài 48 giờ tốn 55đ/tin khi hết hạn mức | Đúng | `snap/zalo-solutions-oa-pricing.txt:17`, `:45`, `:184`, `:211`, `:249`. Bổ sung: hạn mức có sẵn là 500 tin/tháng. |
| R6 (phần công thức) | Tài liệu Zalo ký webhook bằng SHA-256 của chuỗi appId + data + timestamp + OA secret key; hai repo dùng HMAC-SHA256 của body | Đúng | Công thức ở `snap/zaloplatforms-OA-llms-full.txt:9301`, khớp trang developers.zalo.me. Hai repo dùng HMAC của body (`sources/repos/zalo-agent-cli/src/commands/oa-listen.js:33`, `sources/repos/arden-zalo-agent-cli/src/commands/oa-listen.js:120`). Chưa thử trên OA thật. |
| R8 | Zalo dừng định dạng UID cũ và endpoint cũ từ 01/03/2026 | Đúng một phần | Ngày 01/03/2026 đúng, nhưng thứ dừng là tin UID Giao dịch và UID Truyền thông theo mẫu cũ (`snap/zaloplatforms-OA-llms-full.txt:2242`, changelog V251209). Không có nguồn nào nói định dạng UID thay đổi. |

## Còn gì chưa rõ, phải hỏi Zalo hoặc thử thật?

Năm câu hỏi dưới đây tài liệu chính thức chưa trả lời. Mỗi câu ảnh hưởng tới một phần thiết kế.

1. Bốn chi tiết của công thức chữ ký webhook đã nêu ở phần webhook. Cách trả lời: bắt một sự kiện thật trên OA Test hoặc OA chính thức và thử từng cách ghép.
2. Giá thật của mẫu ZBS gửi qua UID. Trang giá chỉ nói giá này thấp hơn giá gửi qua số điện thoại. Cách trả lời: đọc `price_uid` của mẫu sau khi được duyệt.
3. Zalo có coi việc dùng Tin Tư vấn để cảm ơn hoặc hỏi thăm trong 7 ngày là dùng sai mục đích hay không. Cách trả lời: hỏi oa@zalo.me, hoặc dùng mẫu ZBS cho mọi tin chủ động để tránh rủi ro.
4. Mẫu khuyến mãi nhắc tên dịch vụ như "Tiêu u" có bị từ chối hay bị đòi giấy tờ y tế không. Cách trả lời: nộp thử một mẫu Tag 3.
5. Giờ gửi Broadcast là đến 19h59 hay 21h59. Hai trang chính thức ghi khác nhau.

## Nguồn

Tất cả đọc ngày 2026-11-07.

- Tài liệu OA và ZBS toàn văn: https://docs.zaloplatforms.com/OA/llms-full.txt, https://docs.zaloplatforms.com/ZBS/llms-full.txt (bản chép: `snap/zaloplatforms-OA-llms-full.txt`, `snap/zaloplatforms-ZBS-llms-full.txt`).
- Trang gốc webhook trên developers.zalo.me: https://developers.zalo.me/docs/official-account/webhook/tin-nhan/su-kien-nguoi-dung-gui-tin-nhan (nội dung nằm trong khung https://stc-developers.zdn.vn/docs/v2/official-account/webhook/tin-nhan/su-kien-nguoi-dung-gui-tin-nhan).
- Lịch sử cập nhật developers.zalo.me: V251209 https://developers.zalo.me/changelog/thong-bao-ra-mat-zbs-template-message-va-lo-trinh-chuyen-doi-7814; V260306 https://developers.zalo.me/changelog/v260310-thong-bao-cap-nhat-xac-thuc-nhom-quyen-doi-voi-appid-7886; V261001 https://developers.zalo.me/changelog/v261001-thong-bao-cap-nhat-co-che-zbs-template-message-7924; v240409 https://developers.zalo.me/changelog/v240409-them-tinh-nang-kiem-tra-app-secret-proof-khi-goi-api-co-su-dung-access-token-7603; v230418 https://developers.zalo.me/changelog/thong-bao-cap-nhat-phan-loai-tin-nhan-cua-zalo-official-account-7241. Các trang này chỉ hiện nội dung khi chạy JavaScript; tôi đọc bằng trình duyệt và không lưu bản chép.
- Bảng giá gói OA: https://zalo.solutions/oa/pricing (`snap/zalo-solutions-oa-pricing.txt`).
- Bảng giá ZBS: https://zalo.solutions/business-message/pricing (`snap/zalo-solutions-zbs-pricing.txt`). Phần giá nút thao tác và giá hình ảnh trên trang này lấy từ một API không tải được, nên bản chép thiếu các con số đó.
- Quy định duyệt mẫu ZBS: https://zalo.solutions/business-message/guidelines/quy-dinh-chung-khi-kiem-duyet-mau-zbs-template-message (`snap/zalo-solutions-zbs-template-review-rules.txt`).
- Chất lượng và hạn mức ZBS: https://zalo.solutions/business-message/guidelines/co-che-danh-gia-chat-luong-va-quyen-loi-gui-zbs-template-message; cách tính phí theo thời hạn: https://zalo.solutions/business-message/guidelines/co-che-tinh-gia-cua-mau-tin-nhan-zbs.
- Hướng dẫn và chính sách OA: https://oa.zalo.me/home/documents/guides/ và https://oa.zalo.me/home/documents/policy/ (bản chép: các file `snap/oa-zalo-me-*.txt`).

## Nói ngắn gọn nhất

Zalo cho phép chatbot của thom house trả lời khách tự động qua OA, miễn là OA đã xác thực, có gói Tăng trưởng và có máy chủ trả lời webhook trong 2 giây. Trả lời trong 48 giờ thì miễn phí, đến 7 ngày thì tốn ít tiền, quá 7 ngày thì API không cho gửi. Mọi tin chủ động như cảm ơn, hỏi thăm, nhắc lịch hay khuyến mãi phải dùng mẫu được Zalo duyệt trước, tốn khoảng vài trăm đồng mỗi tin, và mẫu khuyến mãi không được hứa hẹn hiệu quả chữa bệnh. Hai việc cần làm sớm là thử chữ ký webhook trên một OA thật và nộp thử một mẫu khuyến mãi, vì cả hai đều chưa kiểm chứng được qua tài liệu.

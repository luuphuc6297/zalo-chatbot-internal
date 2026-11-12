# Đối chiếu chéo bảy nhánh nghiên cứu chatbot thom house

Ngày lập: 2026-11-07. Tài liệu này đọc lại toàn bộ file trong `research/`, `design/` và `data/` do bảy nhánh nghiên cứu viết ra, tìm các điểm mà hai nhánh nói ngược nhau, tự kiểm lại các dữ kiện quyết định trên nguồn gốc, và chốt kết luận cho mọi nhận định của báo cáo trước (danh sách ở `research/00-prior-report-claims.md`). Mọi trang web dẫn trong tài liệu được mở ngày 2026-11-07.

Bảy nhánh là: rà tài liệu doanh nghiệp (`research/01-knowledge-audit.md`), nền tảng Zalo OA (`research/03-zalo-oa-platform.md`), rà ba repo Zalo (`research/04-zalo-repos-audit.md`), gói Anthropic và chi phí (`research/05-anthropic-plan-model-cost.md`), kiến trúc (`research/06-architecture.md`), pháp lý Việt Nam (`research/07-vn-legal-compliance.md`) và thiết kế hội thoại (các file trong `design/`).

## Phần anh cần duyệt

Các nhánh thống nhất ở hướng chính, và tôi không thấy lý do đổi hướng đó. Chatbot gọi Opus 5.5 bằng API key của một tổ chức Claude Console, dùng 200 USD tín dụng mỗi tháng của gói Ultra; phần nhận tin và gửi tin chạy trên cloud; ứng dụng macOS là màn hình làm việc của nhân viên. Tôi đã tự kiểm lại các dữ kiện này trên trang chính thức của Anthropic hôm nay.

Tôi tìm thấy sáu điểm mà các nhánh nói ngược nhau hoặc thiết kế chưa khớp với nền tảng. Ba điểm quan trọng nhất như sau.

Thứ nhất, nhánh kiến trúc gửi tin cảm ơn và tin hỏi thăm sau buổi làm bằng Tin Tư vấn (loại tin OA trả lời khách). Tài liệu Zalo ghi Tin Tư vấn chỉ để trả lời khi khách yêu cầu, và chính sách Zalo cấm dùng sai mục đích loại tin. Vì vậy, tin chủ động phải dùng mẫu ZBS (mẫu tin Zalo duyệt trước), như nhánh Zalo và nhánh hội thoại đã đề xuất.

Thứ hai, bước xin đồng ý trước khi gửi tin sang Anthropic chưa đủ. Tin đầu tiên của khách tới máy chủ Cloudflare đặt ở nước ngoài trước khi khách bấm đồng ý. Luật Bảo vệ dữ liệu cá nhân tính cả việc "sử dụng nền tảng ở ngoài lãnh thổ" là chuyển dữ liệu xuyên biên giới, nên lời xin đồng ý phải nêu cả nơi lưu, và luật sư phải xác nhận căn cứ để lưu tin trước lúc khách đồng ý.

Thứ ba, con số chi phí 105 USD mỗi tháng của nhánh Anthropic tính cho một kiến trúc khác với bản thiết kế hội thoại. Bản thiết kế chỉ dùng Opus và không soạn tin hỏi thăm bằng model. Với bản thiết kế hiện tại, ước tính gần nhất là khoảng 120 đến 130 USD cho 1.000 cuộc hội thoại mỗi tháng, vẫn nằm trong 200 USD tín dụng, chưa gồm phí tin Zalo.

Tôi cũng gom chi phí và thời gian triển khai, hai câu mà chưa file nào trả lời gọn. Chi phí cố định ngoài tiền Claude là khoảng 680.000đ mỗi tháng (ước tính, chi tiết ở phần sau). Từ lúc bắt đầu tới lúc bot trả lời khách thật có người duyệt từng tin, tôi ước tính 6 đến 9 tuần, với điều kiện giấy đăng ký kinh doanh có sẵn và luật sư trả lời kịp.

Anh cần quyết các việc ở mục "Những gì chỉ anh, luật sư hoặc Zalo trả lời được". Điểm yếu của tài liệu này: tôi chưa chạy model, chưa có OA thật và chưa hỏi luật sư, nên mọi con số chi phí, thời gian và mọi suy luận pháp lý vẫn là ước tính hoặc suy luận.

## Các thuật ngữ dùng trong tài liệu

| Thuật ngữ | Nghĩa trong tài liệu này |
|---|---|
| OA | Zalo Official Account, tài khoản doanh nghiệp của thom house trên Zalo |
| Tin Tư vấn | Loại tin OA gửi qua API `v3.0/oa/message/cs` để trả lời khách; chỉ gửi được trong 7 ngày kể từ lần cuối khách tương tác với OA |
| mẫu ZBS | ZBS Template Message: mẫu tin soạn trước, Zalo duyệt từng mẫu, dùng cho tin OA chủ động gửi. Tag 1 là giao dịch, Tag 2 là chăm sóc khách hàng, Tag 3 là hậu mãi (khuyến mãi, mời quay lại) |
| UID | Mã định danh của một khách, riêng cho từng OA; OA chỉ có UID sau khi khách tương tác với OA |
| tham số mẫu | Chỗ trống trong mẫu ZBS mà server điền khi gửi, viết dạng `<customer_name>` |
| chuyển dữ liệu xuyên biên giới | Cách Luật 91/2025/QH15 gọi việc đưa dữ liệu cá nhân thu ở Việt Nam ra hệ thống hoặc nền tảng ở nước ngoài |
| tổ chức Console | Tài khoản doanh nghiệp trên Claude Console (platform.claude.com), nơi tạo API key và nhận tín dụng API |
| kill switch | Cờ cấu hình cho phép dừng ngay một loại hành động tự động, ví dụ `scheduled_sends_enabled` |

## Các nhánh nói ngược nhau ở đâu, và nên theo bên nào?

### Tin cảm ơn và hỏi thăm sau buổi làm đi bằng loại tin nào?

Nhánh kiến trúc vẽ luồng chăm sóc sau buổi làm gửi qua `POST v3.0/oa/message/cs`, tức Tin Tư vấn, với tin cảm ơn ở mốc 4 giờ sau buổi làm (`research/06-architecture.md:279`). Nhánh Zalo, `design/conversation-design.md` và `design/followup-templates.md` dùng mẫu ZBS Tag 1 cho tin cảm ơn, Tag 2 cho tin hỏi thăm và Tag 3 cho tin liên lạc lại sau một tháng, với tin cảm ơn ở mốc 20 đến 24 giờ.

Tôi chọn theo nhánh Zalo. Bảng mục đích các loại tin trong tài liệu Zalo ghi Tin Tư vấn dùng để "Phản hồi khách hàng và hỗ trợ giải đáp" khi khách yêu cầu (`research/snapshots/zalo-2026-11-07/zaloplatforms-OA-llms-full.txt:549`). Chính sách tương tác của OA cấm "Sử dụng sai mục đích các loại tin" (`research/snapshots/zalo-2026-11-07/oa-zalo-me-policy_tuong-tac-cua-oa-voi-nguoi-dung.txt:34`). Mốc 4 giờ cũng không khớp tài liệu hành trình khách của studio, vốn ghi cảm ơn trong vòng 24 giờ (`sources/drive/documentation/07-customer-journey.md:180`). Phần còn lại của luồng kiến trúc giữ nguyên: job hẹn giờ, kiểm kill switch, kiểm trạng thái hội thoại và kiểm đồng ý trước khi gửi. Chỉ bước gửi đổi sang API mẫu ZBS (`POST https://openapi.zalo.me/v3.0/oa/message/template` khi gửi qua UID).

Thay đổi này kéo theo một điều kiện mà chưa nhánh nào nêu rõ. Mẫu ZBS gửi qua UID cần `user_id` mà OA nhận được qua các sự kiện của khách (`research/snapshots/zalo-2026-11-07/zaloplatforms-ZBS-llms-full.txt:2959`). Khách đặt lịch qua điện thoại hay Facebook và chưa từng nhắn OA thì OA không có UID. Với những khách này, studio chỉ gửi được mẫu ZBS qua số điện thoại, và phải có số điện thoại cùng sự đồng ý của khách cho việc nhận tin.

### Con số chi phí nào khớp với bản thiết kế?

Mô hình chi phí của nhánh Anthropic giả định mỗi lượt khách nhắn có hai lần gọi model: Haiku 5.5 lọc ý định, rồi Opus 5.5 viết câu trả lời. Mô hình cũng cho Opus soạn một tin hỏi thăm cho mỗi cuộc hội thoại qua Message Batches (`research/05-anthropic-plan-model-cost.md`, mục "Mô hình giả định những gì?"). Bản thiết kế hội thoại không có bước lọc bằng Haiku; prompt chỉ gọi `claude-opus-5-5` (`design/system-prompt-draft.md:35`). Tin hỏi thăm là mẫu cố định do server điền tham số, không do model soạn (`design/followup-templates.md:9`). Bản thiết kế còn bắt mọi câu hỏi giá đi qua công cụ `quote_price`, nên một lượt hỏi giá cần hai lần gọi Opus: lần đầu model gọi công cụ, lần sau model viết câu trả lời.

Kịch bản trong mô hình gần nhất với bản thiết kế là "chỉ Opus, có cache", vì kịch bản này cũng tính hai lần gọi Opus cho mỗi lượt. Với 1.000 cuộc hội thoại và 6 lần gọi, kịch bản này ra 130,50 USD mỗi tháng. Trừ khoảng 10,5 USD tiền soạn tin hỏi thăm bằng Batches (0,0105 USD mỗi hội thoại theo cùng mô hình), tôi ước tính khoảng 120 USD. Đây là suy luận từ mô hình, chưa đo token thật. Con số 105 USD chỉ đúng nếu anh làm thêm bước lọc bằng Haiku, một bước mà bản thiết kế hiện chưa có.

Mô hình chi phí cũng bỏ ngoài tiền gửi mẫu ZBS. Phần gom chi phí ở dưới cộng khoản này bằng tiền đồng.

### Bước xin đồng ý có che hết việc chuyển dữ liệu ra nước ngoài không?

Bản thiết kế hội thoại chặn tin đầu tiên của khách: server gửi lời giới thiệu AI kèm nút đồng ý, và model chỉ nhận tin sau khi khách bấm nút (`design/conversation-design.md`, mục "Lần nhắn đầu tiên và lời giới thiệu AI"). Lời giới thiệu chỉ nói tin được xử lý trên máy chủ của Anthropic tại Mỹ. Trong khi đó, kiến trúc ghi mọi sự kiện webhook, kể cả tin đầu tiên, vào D1 trên Cloudflare trước khi trả HTTP 200 cho Zalo. Nhánh kiến trúc tự ghi điểm yếu này: dữ liệu khách nằm trên hạ tầng Cloudflare ở nước ngoài.

Tôi đọc lại Luật 91/2025/QH15 trên Công báo. Điểm c khoản 1 Điều 20 tính cả trường hợp tổ chức ở Việt Nam "sử dụng nền tảng ở ngoài lãnh thổ" để xử lý dữ liệu thu tại Việt Nam. Khoản 1 Điều 11 đòi đồng ý trước khi thu thập, trừ khi luật quy định khác. Vì vậy, bước chặn hiện tại chỉ che chặng gửi sang Anthropic, không che chặng lưu trên Cloudflare.

Tôi đề xuất hai sửa đổi, kèm một câu hỏi cho luật sư. Lời giới thiệu đầu tiên phải nêu cả nơi lưu trữ (Cloudflare) bên cạnh nơi xử lý (Anthropic). Bảng `consents` của kiến trúc cần thêm mục đích `ai_chat` cho việc trò chuyện với trợ lý AI, vì hiện bảng chỉ có `service_messages`, `marketing` và `health_data`. Câu hỏi cho luật sư: việc lưu tin đầu tiên để nhân viên trả lời có dựa được vào điểm d khoản 1 Điều 19 (thực hiện thỏa thuận của chủ thể dữ liệu) hay không. Nếu luật sư trả lời không, phương án thay thế là đặt phần lưu trữ trên máy chủ ở Việt Nam. Điểm yếu của phương án thay thế là studio phải thuê người vận hành máy chủ, đúng việc nhánh kiến trúc muốn tránh.

### Tài liệu xưng hô nào mới hơn?

Nhánh hội thoại chọn cách xưng *em*, gọi khách *anh/chị*, một phần vì cho rằng tài liệu 13 là tài liệu mới nhất (`design/conversation-design.md:345`). Thông tin của Google Drive nói ngược lại. Tôi đọc thông tin file qua kết nối Drive: `13-critical-chatbot-fixes.md` sửa lần cuối ngày 2026-05-16, còn `06-brand-voice-identity.md`, tài liệu quy định *mình/bạn*, sửa lần cuối ngày 2026-11-03 lúc 09:12 UTC. Nhánh tài liệu doanh nghiệp đã đo nội dung tài liệu 06 trùng với phần tương ứng trong file gom, nên lần sửa ngày 2026-11-03 có thể không đổi nội dung chính. Lý do "tài liệu mới nhất" vì vậy không đứng được. Lý do còn lại của nhánh hội thoại vẫn đứng: tài liệu 13 viết từ lỗi chat thật. Việc chọn cách xưng hô là việc của anh.

Tôi tìm thêm một dữ kiện làm nhẹ điểm yếu "hai giọng" của phương án A. Quy định duyệt mẫu ZBS cấm cụm *anh/chị* nhưng yêu cầu dùng "biến giới tính" hoặc từ trung tính (`research/snapshots/zalo-2026-11-07/zalo-solutions-zbs-template-review-rules.txt:113`). Danh sách kiểu tham số của ZBS có kiểu "Giới tính / Danh xưng" dài tối đa 5 ký tự (`research/snapshots/zalo-2026-11-07/zaloplatforms-ZBS-llms-full.txt:1186`). Theo cách hiểu của tôi, mẫu ZBS gọi được khách là *anh* hay *chị* qua một tham số, nếu server biết danh xưng của từng khách. Chưa có mẫu nào được nộp để kiểm cách hiểu này.

### Mẫu tin hỏi thăm và khuyến mãi có hợp với giới hạn tham số của ZBS không?

`design/followup-templates.md` dùng các tham số chứa cả câu, như `<aftercare_note>` (một câu hướng dẫn sau buổi làm), `<promo_text>` và `<promo_conditions>`. Tài liệu ZBS chỉ cho 15 kiểu tham số. Phần lớn kiểu dài tối đa 30 ký tự; hai kiểu dài nhất là "Địa chỉ" và "Tên sản phẩm / Thương hiệu", tối đa 200 ký tự (`research/snapshots/zalo-2026-11-07/zaloplatforms-ZBS-llms-full.txt:1186`). Thành phần voucher còn giới hạn tên 30 ký tự và điều kiện 40 ký tự (`:426`, `:427`).

Hệ quả, theo suy luận của tôi: một câu hướng dẫn sau buổi làm không nhét vừa tham số 30 ký tự, và dùng kiểu "Tên sản phẩm" để chứa nội dung khuyến mãi có rủi ro bị từ chối khi duyệt. Hướng sửa là viết hướng dẫn sau buổi làm thành chữ cố định trong một mẫu riêng cho từng dịch vụ, và nộp một mẫu Tag 3 mới cho mỗi chương trình khuyến mãi. Cách sửa này tốn thêm 2 đến 3 ngày làm việc chờ Zalo duyệt cho mỗi chương trình, nên chủ studio phải soạn khuyến mãi sớm hơn ngày định gửi.

### Câu giới thiệu AI phải nói lại khi nào?

Usage Policy của Anthropic, bản có hiệu lực từ 2026-11-12, đòi lời báo AI "at a minimum at the beginning of each chat session". Bản thiết kế hội thoại chỉ nói lại mình là AI ở lần trả lời đầu sau khi khách đồng ý, khi khách hỏi và khi hội thoại quay lại tay bot sau lúc nhân viên tiếp quản. Trên Zalo, khách và OA chỉ có một luồng chat kéo dài nhiều tháng, nên "mỗi phiên" cần được định nghĩa. Tôi đề xuất coi một phiên mới bắt đầu khi khách nhắn lại sau 24 giờ im lặng, và lúc đó model mở câu trả lời bằng một câu ngắn nói mình là trợ lý AI. Mốc 24 giờ là đề xuất của tôi, chưa dựa trên văn bản nào.

### Các điểm lệch nhỏ hơn

Các điểm dưới đây không đổi hướng thiết kế, nhưng cần sửa trong file tương ứng.

| Điểm lệch | Bên A | Bên B | Cách xử lý |
|---|---|---|---|
| Drive có ghi ngày sửa file không | Nhánh tài liệu doanh nghiệp ghi `sources/drive-index.md` không có và ngày sửa trên Drive không kiểm được | File `sources/drive-index.md` có trong dự án; kết nối Drive trả `modifiedTime` của file gom là 2026-10-25T14:50:41Z và cỡ 578.085 byte | Nhận định K1 và K2 chuyển sang Đúng |
| Ví dụ ý định được tự trả lời | Kiến trúc lấy `opening_hours` làm ví dụ cho `auto_reply_intents` | Giờ mở cửa chưa được xác nhận (nhận định K8) và bản thiết kế chỉ trả lời mục đã duyệt | Bỏ `opening_hours` khỏi ví dụ cho tới khi anh xác nhận giờ |
| Tái dùng code repo | Nhánh repo đề xuất dùng lại `oa-client.js` của repo PhucMPham (giấy phép MIT) | Kiến trúc chạy trên Cloudflare Workers; file này dùng `node:fs`, `node:os` và `node-fetch` (`sources/repos/zalo-agent-cli/src/core/oa-client.js:7`–`10`) | Dùng lại kiến thức về endpoint và tham số, viết lại phần gọi HTTP và lưu token cho Workers |
| Nhịp gửi khuyến mãi | Kiến trúc: mỗi khách cách nhau 14 ngày | Pháp lý: 7h–22h, tối đa 3 tin trong 24 giờ; Zalo: Tag 3 tối đa 1 tin mỗi ngày và 30 tin mỗi tháng, Tag 2 và Tag 3 chỉ gửi 7h–22h | Không mâu thuẫn; áp quy tắc chặt nhất: gửi 9h–20h, cách nhau ít nhất 14 ngày |
| Thời hạn Anthropic lưu dữ liệu | privacy.claude.com: xóa "within 30 days" | Tài liệu API: nội dung hội thoại "not retained by default", trừ Covered Models | Tôi mở lại cả hai trang hôm nay; hai trang vẫn nói khác nhau. Giữ mốc 30 ngày làm mức trần trong chính sách dữ liệu của studio |
| Giá đọc cache của Sonnet 5.5 | Tài liệu skill claude-api: 0,20 USD | Trang giá chính thức: 0,10 USD mỗi triệu token | Theo trang giá chính thức |
| Giờ mở cửa trong mô hình chi phí | Mô hình giả định 15 giờ mở cửa (9h–24h) | Giờ mở cửa chưa chốt | Chỉ ảnh hưởng tỉ lệ cache nguội; chạy lại mô hình khi có giờ thật |

## Tôi đã tự kiểm lại những dữ kiện nào?

Tôi chọn các dữ kiện mà một quyết định lớn phụ thuộc vào, hoặc các dữ kiện mà các nhánh chỉ đọc qua trang đăng lại. Mỗi dòng trong bảng là kết quả tôi đọc trực tiếp hôm nay.

| Dữ kiện | Kết quả | Nguồn |
|---|---|---|
| Gói Ultra cho tín dụng API | Đúng: 200 USD mỗi tháng; phải dùng gói đủ 7 ngày; mỗi gói liên kết một tổ chức Console và người dùng không tự đổi được; tín dụng hết hạn cuối chu kỳ; không trả cho Claude Code; hết tín dụng thì API dừng nếu không có tín dụng mua thêm; tổ chức liên kết lên ít nhất bậc Start | https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers |
| Có dùng đăng nhập gói Ultra cho chatbot được không | Không: Anthropic không cho "route requests through Free, Pro, Max, or Ultra plan credentials" thay cho người dùng của mình; sản phẩm phải dùng API key từ Console | https://code.claude.com/docs/en/legal-and-compliance |
| Giá Opus 5.5 | Đúng: 4 USD đầu vào, 5 USD ghi cache 5 phút, 8 USD ghi cache 1 giờ, 0,20 USD đọc cache, 20 USD đầu ra mỗi triệu token; Batches 2 và 10 USD; `inference_geo: "us"` nhân giá với 1,1 | https://platform.claude.com/docs/en/about-claude/pricing |
| Opus 5.5 có ép gọi công cụ được không | Không: `tool_choice` loại `any` hoặc `tool` trả lỗi 400 trên Opus 5.5; dùng `auto` | https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools |
| Usage Policy | Trang ghi hiệu lực Nov 12, 2026; chatbot phải báo là AI ít nhất ở đầu mỗi phiên; lời khuyên y khoa cho một người cụ thể phải được người có chuyên môn xem và có quyền sửa; nội dung sức khỏe chung về giấc ngủ, căng thẳng, dinh dưỡng, vận động được loại trừ | https://www.anthropic.com/legal/aup |
| Luật 91/2025/QH15 | Đúng như nhánh pháp lý ghi: hiệu lực 01/01/2026 (khoản 1 Điều 38); im lặng không phải đồng ý (điểm d khoản 4 Điều 9); đồng ý trước khi thu thập (khoản 1 Điều 11); dùng nền tảng ở nước ngoài là chuyển dữ liệu xuyên biên giới, hồ sơ nộp trong 60 ngày (khoản 1, 2 Điều 20); miễn trừ cho hộ kinh doanh không áp cho bên trực tiếp xử lý dữ liệu nhạy cảm và không nhắc Điều 20 (khoản 2, 3 Điều 38) | Công báo số 971+972 ngày 24/7/2025, https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2025/6/45578/57730-1-2025971-97291-2025-qh15.pdf |
| Nghị định 356/2025/NĐ-CP | Đúng: hiệu lực 01/01/2026 và thay Nghị định 13/2023 (Điều 42); tình trạng sức khỏe là dữ liệu nhạy cảm (điểm d khoản 1 Điều 4); miễn trừ có ngoại lệ cho bên trực tiếp xử lý dữ liệu nhạy cảm (Điều 41) | Công báo số 18 ngày 18/01/2026, https://congbaocdn.chinhphu.vn/180507251028987904/2026/1/17/356signed-1768638052103952849513.pdf |
| Luật Trí tuệ nhân tạo 134/2025/QH15 | Đúng: hiệu lực 01/3/2026 (Điều 34); nhà cung cấp là bên đưa hệ thống vào dùng dưới thương hiệu của mình (khoản 4 Điều 3); rủi ro trung bình là hệ thống có thể gây nhầm lẫn khi người dùng không biết đang nói với AI (điểm b khoản 1 Điều 9); hệ thống rủi ro trung bình phải thông báo Bộ Khoa học và Công nghệ trước khi dùng (khoản 3 Điều 10); người dùng phải nhận biết khi đang tương tác với AI (khoản 1 Điều 11) | Công báo số 40 ngày 22/01/2026, tải từ https://congbao.chinhphu.vn/van-ban/luat-so-134-2025-qh15-468694.htm |
| Mục đích của Tin Tư vấn | Trả lời khách khi khách yêu cầu; chính sách cấm dùng sai mục đích loại tin | Bản chép tài liệu Zalo, dòng đã dẫn ở trên |
| Điều kiện gửi mẫu ZBS qua UID | Cần `user_id` có được từ sự kiện của khách; Tag 1 và Tag 2 là tin giao dịch, Tag 3 là tin hậu mãi | `research/snapshots/zalo-2026-11-07/zaloplatforms-ZBS-llms-full.txt:2872`–`2889`, `:2959` |
| Ngày sửa file trên Drive | File gom: 2026-10-25T14:50:41Z, 578.085 byte; tài liệu 06: 2026-11-03T09:12:22Z, 13.359 byte; cả hai khớp cỡ file bản sao trong `sources/drive/` | Kết nối Google Drive, đọc thông tin file `1s31HVFS7p3lgx3B8T_9fwjNkXfKRu2TO` và `125aPiipGVPO98GoWnYJ6rGFajt7wo5lr` |

Nhờ có bản Công báo, ba văn bản luật chính của nhánh pháp lý giờ đã được đối chiếu với văn bản chính thức. Nhánh pháp lý trước đó chỉ đọc qua trang đăng lại. Các nghị định xử phạt (330/2026), Nghị định 392/2026, Nghị định 142/2026 và các văn bản về quảng cáo tôi chưa đối chiếu lại; trang tìm kiếm có trả về bản Công báo của Nghị định 330/2026, nhưng tôi chưa đọc nội dung.

Tôi cũng chạy kiểm tra định dạng các file dữ liệu bằng `python3 -I`: `design/eval-set.jsonl` có 135 dòng JSON hợp lệ; `design/tools-schema.json`, `data/services.json` và `data/business-facts.json` đọc được bằng `json.load`. Tôi không chạy prompt với API và không chấm bộ câu thử.

## Chủ studio còn câu hỏi nào mà chưa file nào trả lời?

### Mỗi tháng tốn bao nhiêu, tính hết các khoản?

Mỗi nhánh chỉ tính phần của mình. Bảng dưới gom lại theo tỷ giá 25.780đ cho 1 USD (Vietcombank, bán ra, ngày 2026-11-07, theo nhánh Anthropic). Mọi dòng là ước tính.

| Khoản | Mức | Quy ra mỗi tháng | Căn cứ |
|---|---|---|---|
| Gói OA Tăng trưởng, 12 tháng | 2.500.000đ mỗi năm, đã gồm VAT | Khoảng 208.000đ | `research/03-zalo-oa-platform.md` |
| Cloudflare Workers Paid | 5 USD mỗi tháng | Khoảng 129.000đ | `research/06-architecture.md` |
| Apple Developer Program | 99 USD mỗi năm | Khoảng 213.000đ | `research/06-architecture.md` |
| Mẫu ZBS cảm ơn và hỏi thăm | Giả định 300 buổi làm mỗi tháng, 2 tin mỗi buổi, gửi qua số điện thoại 200đ mỗi tin, cộng VAT 10% | Khoảng 132.000đ; gửi qua UID rẻ hơn nhưng Zalo chưa công bố giá | Giả định số buổi làm là của tôi, chưa có số thật |
| Tin Tư vấn ngoài 48 giờ | 55đ mỗi tin sau 500 tin có sẵn của gói | Gần như 0đ ở quy mô studio (ước tính) | `research/03-zalo-oa-platform.md` |
| Tiền gọi Claude | Khoảng 120 USD cho 1.000 cuộc hội thoại, theo phần đối chiếu ở trên | Nằm trong 200 USD tín dụng của gói Ultra; nếu Anthropic thu VAT 10% thì cộng thêm, chưa xác minh | `scripts/cost_model.py` và suy luận của tôi |
| Tên miền | Chưa xác minh giá | Chưa tính | |

Cộng các dòng có số, chi phí cố định ngoài tiền Claude là khoảng 680.000đ mỗi tháng. Bảng chưa gồm ba khoản lớn hơn nhiều: tiền thuê lập trình viên cho 4 đến 6 tuần-người (nhánh kiến trúc ước tính công sức, không ước tính tiền), tiền luật sư và tiền thuê dịch vụ bảo vệ dữ liệu nếu studio không có người đủ điều kiện làm người phụ trách bảo vệ dữ liệu.

Một điểm cần nói thẳng về gói Ultra. Gói Ultra giá 200 USD mỗi tháng và cho đúng 200 USD tín dụng API. Nếu anh không dùng app Claude cho việc khác, giữ gói Ultra chỉ để lấy tín dụng không rẻ hơn tự nạp 200 USD vào tổ chức Console. Khi đó, khác biệt chính là tín dụng Ultra hết hạn cuối mỗi chu kỳ, còn tín dụng mua thêm thì không có ghi chú hết hạn trên trang tôi đọc.

### Mất bao lâu từ hôm nay tới lúc bot trả lời khách thật?

Tôi ghép thời gian Zalo công bố, ước tính công sức của nhánh kiến trúc và thời hạn luật định. Các việc dưới đây chạy song song khi có thể; thời gian là ước tính, chưa đo.

1. Tuần 1 đến 2: tạo và xác thực OA (Zalo duyệt 2 đến 3 ngày làm việc), mua gói Tăng trưởng, tạo tổ chức Console và liên kết gói Ultra (cần gói Ultra đã chạy đủ 7 ngày), gửi câu hỏi cho luật sư.
2. Tuần 2 đến 3: thử nền tảng Zalo trên OA thật bằng tài khoản Zalo của nhân viên, chưa nhận khách thật: đo công thức chữ ký webhook, làm mới token, gửi một Tin Tư vấn, nộp thử một mẫu ZBS. Nhánh kiến trúc ước tính 1 đến 1,5 tuần-người.
3. Tuần 3 đến 7: làm bản MVP ở chế độ nhân viên duyệt từng tin (`auto_reply_mode = approve_each`), 3 đến 4,5 tuần-người theo nhánh kiến trúc. Song song, anh duyệt bảng giá, giờ mở cửa, chính sách và danh sách trường hợp chuyển nhân viên; luật sư duyệt lời xin đồng ý và chính sách dữ liệu.
4. Trước ngày mở cho khách thật: lập hồ sơ phân loại rủi ro và thông báo Bộ Khoa học và Công nghệ nếu luật sư xác nhận chatbot thuộc nhóm rủi ro trung bình (khoản 3 Điều 10 Luật 134/2025).
5. Trong 60 ngày sau lần đầu gửi dữ liệu khách sang Anthropic và Cloudflare: nộp hồ sơ chuyển dữ liệu xuyên biên giới (khoản 2 Điều 20 Luật 91/2025), và theo suy luận của nhánh pháp lý, nộp cả hồ sơ đánh giá tác động xử lý.

Tổng cộng khoảng 6 đến 9 tuần tới lúc bot soạn nháp cho khách thật và nhân viên duyệt từng tin. Ngày bắt đầu đếm 60 ngày là lần đầu dữ liệu khách thật đi ra nước ngoài, nên bước thử nền tảng ở mục 2 chỉ nên dùng tài khoản của nhân viên đã đồng ý. Điểm yếu của lịch này: tôi không biết luật sư cần bao lâu, và nếu giấy đăng ký kinh doanh có tên khác "thom house", Zalo đòi thêm giấy tờ chứng minh tên.

### Khách gửi ảnh, tin thoại hay sticker thì sao?

Chưa file nào trả lời. Zalo có sự kiện `user_send_image`, `user_send_audio`, `user_send_sticker` (`research/03-zalo-oa-platform.md`, bảng sự kiện), nhưng bản thiết kế hội thoại và prompt không nói bot làm gì với ảnh hay tin thoại, và mô hình chi phí không tính token ảnh. Ở một spa, khách hay gửi ảnh da, ảnh vùng cơ thể hoặc ảnh chụp đơn thuốc, và các ảnh này là dữ liệu sức khỏe. Tôi đề xuất bản MVP không gửi ảnh và tin thoại sang Claude: server lưu tin, báo nhân viên và gửi một câu cố định rằng nhân viên sẽ xem. Điểm yếu: khách gửi ảnh menu hay ảnh chụp màn hình khuyến mãi cũng phải chờ người.

### Studio có cần thêm văn bản nào cho khách đọc không?

Có. Lời giới thiệu đầu tiên trong bản thiết kế trỏ tới một "chính sách dữ liệu đã duyệt", nhưng chưa nhánh nào soạn văn bản này. Theo nhánh pháp lý, văn bản cần nêu loại dữ liệu, mục đích, nơi xử lý và lưu trữ (Anthropic ở Mỹ, Cloudflare), thời hạn lưu, quyền của khách, cách rút đồng ý và cách xử lý tự động. Bản nháp văn bản này nên do luật sư duyệt cùng lời xin đồng ý.

### Bảy việc anh đặt ra đã được phủ tới đâu?

| Việc | Đã có | Còn thiếu |
|---|---|---|
| Tư vấn | Ý định `consult_needs`, danh sách 14 trường hợp chuyển nhân viên | Ở giai đoạn đầu không tự gửi; cần người có chuyên môn duyệt danh sách chuyển nhân viên |
| Menu và giá | 23 dịch vụ, 33 mức giá, công cụ `quote_price` | Quy tắc giá đúng 20h30 và buổi làm vắt qua 20h30 |
| Quy trình dịch vụ | Quy trình của 17 dịch vụ trên menu | 6 dịch vụ chưa có quy trình |
| Câu hỏi chuyên môn | Luồng chuyển nhân viên, giới hạn của Usage Policy và luật quảng cáo | Chưa có mục kiến thức nào được duyệt để tự trả lời |
| Ghi nhận yêu cầu đặt lịch | Công cụ `create_booking_request`, hợp đồng sự kiện với app đặt lịch sau này | Chính sách đổi, hủy, đến trễ, đặt cọc |
| Khuyến mãi | Luồng chiến dịch, mẫu Tag 3, Broadcast gửi tay | Chưa có chương trình nào; mỗi chương trình cần một mẫu mới chờ duyệt 2 đến 3 ngày làm việc |
| Hỏi thăm sau buổi làm | Lịch 24 giờ, 2 đến 3 ngày, 1 tháng; điều kiện dừng | Ai đánh dấu buổi làm đã xong; khách chưa nhắn OA thì cần số điện thoại và đồng ý |

## Kết luận cho mọi nhận định của báo cáo trước

Cột "Kết luận" dùng năm mức: Đúng, Sai, Đúng một phần, Không kiểm được, Đã cũ. Khi hai nhánh cùng xét một nhận định, tôi ghi lại nếu kết luận khác nhau; lần này không có nhận định nào bị hai nhánh kết luận khác nhau.

| Mã | Kết luận | Ghi chú |
|---|---|---|
| K1 | Đúng | 578.085 byte, file tự ghi ngày 2026-05-16, gom 30 tài liệu (nhánh tài liệu doanh nghiệp); Drive ghi sửa lần cuối 2026-10-25T14:50:41Z (tôi đọc qua kết nối Drive). Nhánh tài liệu doanh nghiệp ghi Đúng một phần vì chưa thấy `sources/drive-index.md` |
| K2 | Đúng | Tài liệu 06 dòng 18 quy định viết `thom house`; Drive ghi sửa 2026-11-03T09:12:22Z, mới hơn file gom. Nội dung trùng phần tương ứng trong file gom, nên "mới hơn" chỉ đúng về ngày sửa |
| K3 | Đúng | `scripts/build_services.py` đếm 23 dịch vụ và 33 mức giá, mọi mức truy về dòng menu gốc |
| K4 | Đúng | Tài liệu 13 dòng 23 so với tài liệu 06 dòng 53–54 và 250. Thêm: mẫu ZBS cấm cụm *anh/chị* nhưng cho tham số danh xưng |
| K5 | Đúng | `raw-content/batch-05-hair-care-menu.md` dòng 93–96 |
| K6 | Đúng | Massage chân chia giá theo thời lượng (batch-01 dòng 80–81); chăm sóc nan tóc 349.000đ không chia khung giờ (batch-05 dòng 141) |
| K7 | Đúng | Tài liệu 07 dòng 180, 182, 226; không có bản duyệt |
| K8 | Đúng | File gom dòng 57 ghi 9h–24h; dòng 590 và 931 ghi chờ xác nhận |
| K9 | Đúng | Tài liệu 13 dòng 65 |
| K10 | Đúng | Menu có "ngừa đột quỵ", "Giảm u hạch, tuyến giáp", "hỗ trợ chữa sa tử cung" trong khi tài liệu 13 cấm hứa chữa |
| K11 | Đúng | File gom dòng 4222 và 4224 |
| K12 | Đúng | SHR được định nghĩa bốn kiểu khác nhau; thông tin Whitetox còn chờ xác nhận |
| K13 | Đúng | File gom dòng 9044 gọi Yoni Retreat là đắt thứ 2, trong khi giá 3.500.000đ là cao nhất |
| K14 | Đúng một phần | Câu "mệt nhẹ 1-2 ngày là bình thường (đẩy độc tố)" đúng; câu thứ hai nói căng nhẹ vùng bụng dưới sau Yoni Retreat, không phải đầy bụng |
| R1 | Đúng | Lockfile ghi engine 2.5.9; gitHead trên npm khớp hai commit. `package.json` chỉ khai `^2.5.0` |
| R2 | Đúng | Không file nào trong `src/mcp` gọi `oa-client` |
| R3 | Đúng | NOTICE dòng 16–19 của repo Arden. Phần gốc MIT và các bản cũ vẫn là MIT |
| R4 | Đúng | Bản 1.7.0, MIT, có `oa-client` riêng; 8 công cụ MCP dùng tài khoản cá nhân. Bản 1.7.0 chưa có trên npm |
| R5 | Đúng | Lệnh nhắc lịch và tự trả lời gọi API tài khoản cá nhân qua zca-js |
| R6 | Đúng | Ba nhánh cùng đối chiếu: tài liệu Zalo ghi `sha256(appId + data + timeStamp + OAsecretKey)`, hai repo dùng HMAC-SHA256 của body. Chưa thử trên OA thật |
| R7 | Đúng một phần | Thiếu lưu sự kiện, lọc trùng, tự làm mới token và kiểm điều kiện gửi là đúng. Nhưng repo Arden có outbox SQLite cho tài khoản cá nhân, và cả hai repo, không chỉ PhucMPham, còn dùng loại tin `transaction` và `promotion` cũ |
| R8 | Đúng một phần | Ngày 01/03/2026 đúng, nhưng thứ dừng là tin UID Giao dịch và UID Truyền thông theo mẫu cũ. Không nguồn nào nói định dạng UID đổi (nhánh Zalo và nhánh repo kết luận giống nhau) |
| A1 | Đúng | Tôi kiểm lại hôm nay trên trang api-credits-for-subscribers |
| A2 | Đúng | Tôi kiểm lại hôm nay trên trang legal-and-compliance |
| A3 | Đúng | Tôi kiểm lại hôm nay trên trang pricing |
| A4 | Đúng | Tín dụng không đổi hạn mức dùng app Claude; hết tín dụng thì API dừng nếu không có tín dụng mua thêm hay auto-reload. Câu "không bật auto-reload mặc định" là đề xuất |
| A5 | Đúng một phần | Là nhận định thiết kế hợp lý, không phải quy định trong tài liệu; cả Messages API và Agent SDK đều cần API key và đều được trả bằng tín dụng Ultra |
| A6 | Đúng | Commercial Terms mục B cấm huấn luyện trên dữ liệu khách hàng; thời hạn lưu là chuyện riêng. Hai trang Anthropic vẫn nói khác nhau về thời hạn lưu mặc định |
| A7 | Đúng | Trang ghi "Effective Nov 12, 2026"; tới ngày đó, bản 2025-09-15 vẫn có hiệu lực. Cả hai bản đều bắt báo là AI |
| Z1 | Đúng | 7 ngày qua OpenAPI, 365 ngày qua OA Manager, miễn phí trong 48 giờ |
| Z2 | Đúng | Quan tâm OA chỉ cho gửi lời chào, hạn mức `welcome_msg` |
| Z3 | Đúng | Mẫu ZBS được duyệt trước, chỉ gửi cho khách đã có giao dịch; Tag 3 tối đa 30 tin mỗi tháng |
| Z4 | Đúng | Access token 25 giờ, refresh token dùng một lần và sống 3 tháng; nhánh Zalo và nhánh kiến trúc kết luận giống nhau |
| Z5 | Đúng | Giá gói đã gồm VAT 10%; 55đ mỗi tin; gói có sẵn 500 Tin Tư vấn ngoài 48 giờ mỗi tháng |
| C1 | Đúng một phần | Hướng chính đúng: Mac chỉ hợp để thử nội bộ vì Zalo tắt webhook sau các lần gửi lại thất bại. PostgreSQL trên máy chủ riêng là lựa chọn thiết kế; nhánh kiến trúc đề xuất Cloudflare Workers với D1 |
| C2 | Đúng một phần | Phép tính 96 và 240 USD đúng, nhưng bỏ qua khối menu, thinking và cache. Với bản thiết kế hiện tại, ước tính khoảng 120 USD cho 1.000 cuộc hội thoại mỗi tháng |
| C3 | Đúng một phần | Ba chế độ làm được với cờ `auto_reply_mode`, không phải `auto_reply_enabled`. Kiểm cờ ngay trước khi gửi là cần nhưng chưa đủ; cần thêm trạng thái từng hội thoại, cờ dừng gọi Claude, cờ dừng mọi tin gửi đi và bước kiểm bản nháp ở server (nhánh kiến trúc và nhánh hội thoại kết luận giống nhau) |

## Những gì chỉ anh, luật sư hoặc Zalo trả lời được

Các câu dưới đây tôi đã tìm trong tài liệu và trên trang chính thức mà không có câu trả lời. Mỗi câu ghi ai trả lời được.

Anh cần trả lời:

1. Studio là hộ kinh doanh, doanh nghiệp siêu nhỏ hay công ty, và tên trên giấy đăng ký kinh doanh là gì. Câu trả lời quyết định giấy tờ xác thực OA và mức phạt áp theo cá nhân hay tổ chức.
2. Studio đã có OA chưa, và người quản trị OA là ai.
3. Giờ mở cửa, giờ nhận khách cuối, hotline, chính sách hủy, đến trễ, đặt cọc, hoàn tiền, thẻ quà tặng, hội viên, nơi gửi xe, giới tính kỹ thuật viên, nhận khách nam và trẻ em hay không.
4. Giá đêm tính theo giờ bắt đầu hay giờ kết thúc, và đặt đúng 20h30 thì tính giá nào.
5. Cách xưng hô trong chat và trong mẫu ZBS.
6. Ai nhận hội thoại được chuyển, trả lời trong bao lâu, và ngoài giờ thì khách nhận câu gì.
7. Ai ở studio đủ chuyên môn để duyệt câu trả lời sức khỏe cho một khách cụ thể, như Usage Policy đòi.
8. Có đổi tên các dịch vụ mang tên bệnh ("Diện chẩn ngừa đột quỵ", "Tiêu u", "Thiếu máu não") hay không.
9. Ai trong studio làm và duy trì phần mềm, hoặc thuê ai.

Luật sư cần trả lời:

1. Việc lưu tin đầu tiên của khách trên Cloudflare trước lúc khách bấm đồng ý có căn cứ nào không, và tin trước lúc đồng ý có được gửi sang Anthropic sau khi khách đồng ý không.
2. Chatbot thu tin sức khỏe khách tự kể có làm studio thành bên "trực tiếp xử lý dữ liệu cá nhân nhạy cảm" hay không; câu trả lời quyết định nghĩa vụ hồ sơ đánh giá tác động xử lý và người phụ trách bảo vệ dữ liệu.
3. Chatbot thuộc nhóm rủi ro trung bình hay thấp theo Luật 134/2025 khi đã báo rõ là AI.
4. Điều khoản thương mại và thỏa thuận xử lý dữ liệu của Anthropic, và điều khoản của Cloudflare, có đáp ứng khoản 2 Điều 12 Nghị định 356/2025 hay không.
5. Nghị định 91/2020 về tin nhắn rác có áp cho tin Zalo hay không, và nghị định thay thế đã ký chưa.
6. Ranh giới giữa massage thư giãn, diện chẩn, ấn huyệt với "chữa bệnh" theo Luật Khám bệnh, chữa bệnh.

Chỉ OA thật hoặc Zalo trả lời được:

1. Công thức chữ ký webhook thật: `timeStamp` là gì, `data` là body nguyên văn hay JSON đã chuẩn hóa, khóa nào, có tiền tố `mac=` hay không.
2. Tin gửi qua API có luôn sinh sự kiện `oa_send_text` hay không.
3. Giá thật của mẫu ZBS gửi qua UID (đọc được qua `price_uid` sau khi mẫu được duyệt).
4. Zalo có coi tin cảm ơn qua Tin Tư vấn là dùng sai mục đích hay không (hỏi oa@zalo.me).
5. Mẫu Tag 3 có tên dịch vụ như "Tiêu u" có bị từ chối hay không, và mẫu dùng tham số danh xưng cho *anh/chị* có được duyệt hay không.
6. Zalo có hiển thị in đậm dạng markdown trong Tin Tư vấn hay không.

Chỉ chạy thật mới trả lời được: số token thật của prompt tiếng Việt (endpoint `count_tokens`), chất lượng trả lời tiếng Việt của Opus 5.5 trên 135 câu thử, và Anthropic có thu VAT 10% với giao dịch từ Việt Nam hay không.

## Nói ngắn gọn nhất

Hướng làm vẫn đứng: Opus 5.5 gọi bằng API key của tổ chức Console nhận 200 USD tín dụng Ultra, phần nhận và gửi tin chạy trên Cloudflare, app macOS cho nhân viên duyệt. Ba điểm phải sửa trước khi làm là: tin cảm ơn và hỏi thăm phải đi bằng mẫu ZBS chứ không bằng Tin Tư vấn; lời xin đồng ý phải nói cả việc lưu trên Cloudflare, và luật sư phải xác nhận việc lưu tin đầu tiên trước lúc khách đồng ý; chi phí Claude nên tính khoảng 120 USD mỗi tháng cho 1.000 cuộc hội thoại theo bản thiết kế chỉ dùng Opus. Chi phí cố định ngoài Claude khoảng 680.000đ mỗi tháng, chưa gồm tiền lập trình viên và luật sư, và bot có thể trả lời khách thật với nhân viên duyệt từng tin sau khoảng 6 đến 9 tuần. Mọi con số này là ước tính, vì chưa có OA thật, chưa chạy model và chưa có ý kiến luật sư.

# Gói Anthropic, model, chi phí và chính sách cho chatbot Zalo OA của thom house

Ngày nghiên cứu: 2026-11-07. Mọi trang web dẫn trong tài liệu này được mở vào ngày 2026-11-07. Lời trích tiếng Anh được giữ dưới 15 từ.

## Phần anh cần duyệt

Gói Ultra của anh không tự chạy được chatbot. Gói Ultra cho 200 USD tín dụng API mỗi tháng (API là cách để phần mềm gọi model Claude bằng code). Để nhận khoản tín dụng này, anh phải liên kết gói với một tổ chức trên Claude Console, trang quản trị API của Anthropic. Chatbot phải gọi model bằng API key của tổ chức đó, theo Commercial Terms (điều khoản dành cho doanh nghiệp). Tài liệu pháp lý của Claude Code ghi rõ: Anthropic không cho route yêu cầu của người dùng khác qua thông tin đăng nhập gói Free, Pro, Max hay Ultra. Vì vậy, cách lấy phiên đăng nhập Ultra trên máy Mac để trả lời khách Zalo là sai điều khoản.

Model Opus 5.5 có mã `claude-opus-5-5`, giá 4 USD cho mỗi triệu token đầu vào và 20 USD cho mỗi triệu token đầu ra. Theo mô hình chi phí trong `scripts/cost_model.py`, 1.000 cuộc hội thoại mỗi tháng tốn khoảng 105 USD khi bật prompt caching và dùng Haiku 5.5 cho bước lọc. Khoản này nằm trong 200 USD tín dụng của gói Ultra. Nếu không bật caching và gọi Opus cho mọi bước, cùng khối lượng tốn khoảng 619 USD. Các con số này là ước tính, vì tôi chưa đo token thật.

Usage Policy bắt chatbot nói rõ với khách rằng khách đang nói chuyện với AI. Khi chatbot đưa lời khuyên y khoa cho một khách cụ thể (giải thích triệu chứng, gợi ý điều trị), một người có chuyên môn phải duyệt lời khuyên đó trước khi gửi. Anh cần quyết định ai ở thom house đóng vai người duyệt này, hoặc chặn chatbot khỏi loại câu trả lời đó.

Những việc anh cần quyết nằm ở phần cuối, mục "Anh cần quyết gì".

## Gói Ultra cho gì về API?

Gói Ultra giá 200 USD mỗi tháng và kèm 200 USD tín dụng API mỗi tháng ([claude.com/pricing](https://claude.com/pricing)). Trang tài liệu chính thức về tín dụng cho người đăng ký ([platform.claude.com/docs/en/about-claude/api-credits-for-subscribers](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers)) và bài trợ giúp ([support.claude.com/en/articles/17154008](https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans)) nói giống nhau ở các điểm sau.

Số tiền: Max được 100 USD, Ultra được 200 USD, Team được 20 USD cho mỗi ghế Standard và 100 USD cho mỗi ghế Premium, gộp lại tối đa 500 USD.

Điều kiện nhận: gói phải đang hoạt động và không bị khóa. Người mới đăng ký phải dùng gói đủ 7 ngày mới nhận được. Người nhận phải là chủ gói Ultra, và phải có vai trò Owner, Admin hoặc Billing trong tổ chức Console. Hai trang trên không nêu giới hạn theo quốc gia. Gói Free, Pro và Enterprise không được nhận.

Cách nhận: trên claude.ai, anh vào Settings, rồi Billing, rồi phần API credits, chọn tổ chức Console để liên kết và chấp nhận điều khoản tín dụng. Mỗi gói chỉ liên kết được một tổ chức. Anh không tự đổi tổ chức đã liên kết được, muốn đổi phải nhờ bộ phận hỗ trợ. Vì vậy, anh nên tạo một tổ chức Console riêng cho thom house trước khi liên kết.

Thời hạn: tín dụng về mỗi chu kỳ thanh toán, ngay sau khi tiền gói được trừ. Tín dụng chưa dùng hết sẽ hết hạn cuối chu kỳ và không cộng dồn sang tháng sau.

Phạm vi dùng: tín dụng trả cho Claude API (Messages và Message Batches), Claude Managed Agents, Claude Agent SDK và Playground trong Console. Tín dụng không trả cho Claude Code dùng tương tác, cho phần dùng thêm trong app Claude, và cho Claude trên Bedrock, Google Cloud hay Microsoft Foundry. Mọi API key trong tổ chức đã liên kết cùng dùng chung một số dư.

Khi tín dụng hết: nếu tổ chức có tín dụng mua thêm hoặc bật auto-reload (tự nạp tiền khi số dư xuống dưới ngưỡng), yêu cầu API tiếp tục chạy bằng tiền đó. Nếu không có, API trả lỗi "credit balance is too low" cho tới khi tín dụng tháng sau về. Anthropic không trừ tiền vượt mức vào gói Ultra. Tín dụng tặng kèm được dùng trước, tín dụng mua thêm dùng sau.

Ảnh hưởng tới giới hạn: tín dụng không đổi hạn mức dùng của anh trong app Claude hay Claude Code. Tổ chức được liên kết lên ít nhất bậc Start. Chỉ gói có tín dụng trên 200 USD mới được lên bậc Build, nên tổ chức liên kết với Ultra dừng ở bậc Start. Phần chi bằng tín dụng vẫn tính vào trần chi tiêu tháng của tổ chức.

Điều khoản tín dụng ([anthropic.com/legal/credit-terms](https://www.anthropic.com/legal/credit-terms), hiệu lực từ 2024-03-04) không cấm dùng tín dụng cho sản phẩm phục vụ khách hàng. Điều khoản này cấm chuyển nhượng hoặc bán lại tín dụng, và ghi rõ tín dụng không có giá trị quy đổi thành tiền.

## Có được dùng đăng nhập gói Ultra để chạy chatbot cho khách không?

Không được. Lý do nằm ở ba văn bản.

Trang pháp lý của Claude Code ([code.claude.com/docs/en/legal-and-compliance](https://code.claude.com/docs/en/legal-and-compliance)), mục Authentication and credential use, viết rằng đăng nhập OAuth chỉ dành cho người mua gói và cho việc dùng thông thường. OAuth là cách app Claude, Claude Code và Agent SDK đăng nhập bằng tài khoản claude.ai thay cho API key. Cùng mục đó yêu cầu người xây sản phẩm, kể cả sản phẩm dùng Agent SDK, phải dùng API key từ Console. Câu cấm nguyên văn là: "route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users". Trang cũng ghi Anthropic có thể thực thi hạn chế này mà không báo trước.

Trang tổng quan Agent SDK ([code.claude.com/docs/en/agent-sdk/overview](https://code.claude.com/docs/en/agent-sdk/overview)) nhắc lại rằng bên thứ ba không được dùng claude.ai login hay hạn mức gói cho sản phẩm của mình. Trang này cũng ghi Agent SDK chịu Commercial Terms, kể cả khi dùng cho khách hàng của anh.

Consumer Terms ([anthropic.com/legal/consumer-terms](https://www.anthropic.com/legal/consumer-terms), hiệu lực 2025-10-08) là điều khoản của gói Ultra. Mục 3 cấm truy cập dịch vụ bằng bot hay script, trừ khi dùng "an Anthropic API Key". Mục 2 cấm cho người khác dùng tài khoản: "You also may not make your Account available to anyone else."

Đường hợp lệ là: tạo tổ chức Console cho thom house, chấp nhận Commercial Terms, liên kết gói Ultra với tổ chức này để nhận tín dụng, tạo API key và để chatbot gọi Messages API bằng key đó. Commercial Terms ([anthropic.com/legal/commercial-terms](https://www.anthropic.com/legal/commercial-terms), hiệu lực 2025-06-17) mục A.1 cho phép dùng dịch vụ "to power products and services Customer makes available to its own customers". Mục B ghi Anthropic không huấn luyện model trên dữ liệu của khách hàng doanh nghiệp.

Điểm yếu của đường này: API key là bí mật. Nếu chatbot chạy trên máy Mac ở tiệm, key nằm trên máy đó. Ai lấy được máy hoặc file cấu hình sẽ tiêu tín dụng của anh. Tôi đề xuất đặt key ở máy chủ, hoặc ít nhất trong Keychain của macOS, và đặt spend limit (hạn mức chi do anh tự đặt) cho workspace của chatbot.

## Opus 5.5 và các model rẻ hơn khác nhau thế nào?

Một token là một mẩu chữ mà model đọc hoặc viết. Model tính tiền theo số token. Giá dưới đây tính bằng USD cho mỗi triệu token, lấy từ trang giá chính thức ([platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing)) và trang tổng quan model ([platform.claude.com/docs/en/about-claude/models/overview](https://platform.claude.com/docs/en/about-claude/models/overview)).

Prompt caching là tính năng cho phép API giữ lại phần đầu của prompt (ví dụ quy tắc trả lời và bảng giá dịch vụ) để các lần gọi sau đọc lại với giá rẻ hơn. Lần đầu ghi vào cache tốn hơn giá đầu vào thường. Cache có hai thời hạn: 5 phút hoặc 1 giờ. Mỗi lần đọc trúng cache thì thời hạn được tính lại từ đầu.

| Model | Mã model | Đầu vào | Ghi cache 5 phút | Ghi cache 1 giờ | Đọc cache | Đầu ra |
|---|---|---|---|---|---|---|
| Opus 5.5 | `claude-opus-5-5` | 4,00 | 5,00 | 8,00 | 0,20 | 20,00 |
| Sonnet 5.5 | `claude-sonnet-5-5` | 2,00 | 2,50 | 4,00 | 0,10 | 10,00 |
| Haiku 5.5, prompt đến 100.000 token | `claude-haiku-5-5` | 0,10 | 0,125 | 0,20 | 0,01 | 0,50 |
| Haiku 5.5, prompt trên 100.000 token | `claude-haiku-5-5` | 0,50 | 0,625 | 1,00 | 0,05 | 2,50 |

Cả ba model đều có cửa sổ ngữ cảnh 1 triệu token (lượng chữ tối đa model đọc trong một lần gọi) và trả lời tối đa 128.000 token mỗi lần. Opus 5.5 và Sonnet 5.5 tính giá đọc cache bằng 5% giá đầu vào; các model khác tính 10%. Opus 5.5 và Sonnet 5.5 không thu thêm tiền cho prompt dài. Haiku 5.5 thu giá cao hơn khi prompt vượt 100.000 token.

Message Batches API là cách gửi một loạt yêu cầu không cần trả lời ngay, chạy bất đồng bộ và được giảm 50% cả đầu vào lẫn đầu ra. Opus 5.5 qua Batches còn 2 USD đầu vào và 10 USD đầu ra. Cách này hợp với việc soạn tin hỏi thăm khách sau dịch vụ.

Thinking là phần model tự suy luận trước khi trả lời. Trang Thinking ([platform.claude.com/docs/en/build-with-claude/thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)) ghi rằng token thinking được tính như token đầu ra, kể cả khi API không trả nội dung thinking về. Trên Opus 5.5, thinking không tắt được. Anh chỉ điều chỉnh độ sâu qua tham số `effort`; mặc định của Opus 5.5 là `medium`. Opus 5.5 giữ thinking của các lượt trước trong ngữ cảnh, nên lịch sử hội thoại dài thêm cả phần thinking.

Về tốc độ, trang tổng quan chỉ xếp hạng tương đối: Opus 5.5 ở mức "Moderate", Sonnet 5.5 "Fast", Haiku 5.5 "Fastest". Anthropic không công bố số mili giây; tôi chưa đo. Opus 5.5 có chế độ fast mode giá 8 USD đầu vào và 40 USD đầu ra, tức gấp đôi giá thường.

Nếu chọn `inference_geo: "us"` để bắt xử lý tại Mỹ, mọi loại giá nhân 1,1. Mặc định là `global`, giá thường.

Chiến lược chia model mà tôi mô hình hóa: Haiku 5.5 làm bước lọc và phân loại ý định (khách hỏi giá, hỏi quy trình, xin đặt lịch, hay hỏi chuyện sức khỏe cần người duyệt), còn Opus 5.5 viết câu trả lời tư vấn. Điểm yếu: cache gắn với từng model, nên phần prompt Haiku dùng không chia sẻ cache với Opus. Thêm một bước gọi cũng thêm độ trễ. Tài liệu kỹ năng claude-api của Anthropic khuyên đo trước phương án đơn giản hơn: chỉ dùng Opus 5.5 với `effort` thấp.

## Tổ chức mới bắt đầu ở bậc giới hạn nào?

Trang Rate limits ([platform.claude.com/docs/en/api/rate-limits](https://platform.claude.com/docs/en/api/rate-limits)) xếp mỗi tổ chức vào một usage tier, tức bậc giới hạn tính theo lịch sử dùng API. Tổ chức mới có thể bắt đầu ở bậc Evaluation, với giới hạn thấp hơn bảng chuẩn; trang không công bố số cụ thể của bậc này. Tổ chức liên kết với gói Ultra được nâng lên ít nhất bậc Start.

| Bậc | Trần chi tiêu tháng | Opus 5.5: yêu cầu/phút | Opus 5.5: token đầu vào/phút | Opus 5.5: token đầu ra/phút |
|---|---|---|---|---|
| Start | 500 USD | 4.000 | 2.000.000 | 400.000 |
| Build | 1.000 USD | 10.000 | 5.000.000 | 1.000.000 |
| Scale | 200.000 USD | 13.000 | 10.000.000 | 2.000.000 |

Sonnet 5.5 và Haiku 5.5 có cùng mức giới hạn như Opus 5.5 ở mỗi bậc, và mỗi model có giới hạn riêng. Token đọc từ cache không tính vào giới hạn token đầu vào mỗi phút. Khi chạm trần chi tiêu, API trả lỗi 429 với mã `enforced_spend_limit_reached` cho tới 00:00 UTC ngày đầu tháng sau. Với 3.000 cuộc hội thoại mỗi tháng, chatbot dùng chưa tới 1% giới hạn bậc Start; tôi suy ra con số này từ khối lượng ước tính, chưa đo.

## Usage Policy bắt chatbot của spa làm gì?

Trang Usage Policy ([anthropic.com/legal/aup](https://www.anthropic.com/legal/aup)) đang hiển thị bản có hiệu lực từ 2026-11-12, tức năm ngày sau hôm nay. Mã nguồn trang ghi bản trước đó có hiệu lực từ 2025-09-15; bản cũ được lưu tại [anthropic.com/legal/archive/22742366-2ef0-4c7a-a833-6523f10d3944](https://www.anthropic.com/legal/archive/22742366-2ef0-4c7a-a833-6523f10d3944). Chatbot sẽ chạy sau ngày 2026-11-12, nên tôi lấy bản mới làm chuẩn.

Nghĩa vụ thứ nhất là nói rõ khách đang nói chuyện với AI. Cả bản 2025 và bản 2026 đều yêu cầu chatbot giao tiếp với khách bên ngoài phải "disclose to users that they are interacting with AI". Lời báo phải có ít nhất ở đầu mỗi phiên chat hoặc trong giao diện. Lời báo không cần nhắc tên Anthropic hay Claude. Với Zalo OA, tôi đề xuất câu chào đầu mỗi phiên nói rõ đây là trợ lý AI của thom house và cách gặp nhân viên.

Nghĩa vụ thứ hai áp cho High-risk AI Recommendation, tức khuyến nghị AI đưa ra trong một lĩnh vực rủi ro cao. Bản 2026 xếp mục Medical vào nhóm này: chẩn đoán bệnh; gợi ý bắt đầu, dừng hay đổi một cách điều trị; diễn giải triệu chứng của một người để phân loại, chẩn đoán hay lập kế hoạch điều trị. Với khuyến nghị loại này, chatbot phải có hai lớp kiểm soát. Lớp một: một người có chuyên môn phải xem lại và có quyền sửa trước khi lời khuyên tới khách, kèm giấy phép hành nghề nếu luật yêu cầu. Lớp hai: khách phải được báo rõ rằng AI đã tạo ra lời khuyên đó.

Bản 2026 cũng loại trừ một số trường hợp khỏi yêu cầu này. Thông tin chung giải thích một liệu trình hoạt động thế nào, khi không áp vào tình trạng riêng của khách, không phải khuyến nghị rủi ro cao. Nội dung chăm sóc sức khỏe chung về giấc ngủ, căng thẳng, dinh dưỡng và vận động cũng được loại trừ.

Áp vào thom house, tôi suy luận như sau. Câu hỏi về menu, giá, quy trình gội đầu dưỡng sinh hay massage thư giãn nằm ngoài nhóm rủi ro cao. Câu hỏi kiểu "em bị đau bụng kinh, sa tử cung thì nên làm gói nào" nằm sát ranh giới, vì chatbot phải diễn giải triệu chứng của một khách cụ thể và gợi ý cách xử lý. Chatbot nên chuyển loại câu hỏi này cho nhân viên duyệt, hoặc chỉ trả lời thông tin chung và khuyên khách gặp bác sĩ. Tài liệu của thom house cũng đã có quy tắc khuyên khách khám bác sĩ chuyên khoa (`sources/drive/thomhouse-knowledge-bundle.txt`, dòng 59–61).

Usage Policy còn cấm tạo thông tin sai lệch về y tế và sức khỏe, và cấm phát tán spam. Hai điều này liên quan tới các tuyên bố chữa bệnh trong tài liệu (claim K10, K11) và tới tin khuyến mãi gửi hàng loạt.

## Dữ liệu khách gửi qua API được lưu bao lâu?

Hai nguồn chính thức nói khác nhau về thời hạn lưu mặc định. Trang quyền riêng tư ([privacy.claude.com/en/articles/7996866](https://privacy.claude.com/en/articles/7996866), cập nhật 2026-07-01) ghi Anthropic tự xóa đầu vào và đầu ra "within 30 days of receipt or generation". Trang tài liệu API ([platform.claude.com/docs/en/build-with-claude/api-and-data-retention](https://platform.claude.com/docs/en/build-with-claude/api-and-data-retention)) ghi nội dung hội thoại "is not retained by default", trừ các Covered Models phải lưu 30 ngày. Covered Models hiện gồm Fable 5.1, Mythos 5.1, Fable 5 và Mythos 5; Opus 5.5 không nằm trong danh sách. Tôi coi giới hạn 30 ngày là mức trần an toàn để viết vào chính sách quyền riêng tư của thom house.

Có bốn ngoại lệ đáng chú ý. Thứ nhất, nếu hệ thống an toàn tự động gắn cờ một cuộc chat, Anthropic có thể giữ đầu vào và đầu ra tới 2 năm, và điểm phân loại an toàn tới 7 năm. Thứ hai, Message Batches lưu kết quả 29 ngày. Thứ ba, Files API lưu file cho tới khi anh xóa. Thứ tư, mọi thao tác trong Console và Playground không thuộc phạm vi ZDR.

ZDR (zero data retention) là thỏa thuận theo đó Anthropic không lưu prompt và câu trả lời sau khi trả kết quả. ZDR phải xin qua đội bán hàng và bật riêng cho từng tổ chức. Prompt caching vẫn dùng được dưới ZDR, vì cache chỉ giữ trong bộ nhớ trong thời hạn cache.

Về huấn luyện model, Commercial Terms mục B ghi "Anthropic may not train models on Customer Content from Services." Vì vậy, nhận định A6 đúng: không dùng để huấn luyện là một chuyện, không lưu là chuyện khác.

Về nơi xử lý, tham số `inference_geo` chỉ có hai giá trị: `global` (mặc định, chạy ở bất kỳ vùng nào) và `us` (chỉ tại Mỹ). Nơi lưu dữ liệu của workspace hiện chỉ có `us` ([platform.claude.com/docs/en/manage-claude/data-residency](https://platform.claude.com/docs/en/manage-claude/data-residency)). Không có lựa chọn xử lý tại châu Á hay Việt Nam. Hệ quả là dữ liệu khách Việt Nam, kể cả thông tin sức khỏe, sẽ đi ra nước ngoài. Việc này cần đối chiếu với luật bảo vệ dữ liệu cá nhân của Việt Nam; tôi chưa kiểm tra phần luật này.

## Thanh toán từ Việt Nam có được không?

Việt Nam có trong danh sách quốc gia được hỗ trợ ([anthropic.com/supported-countries](https://www.anthropic.com/supported-countries)), áp cho cả claude.ai và API. Trang này cũng ghi ngày hiệu lực 2026-11-12.

API trả trước bằng tín dụng mua trên trang Billing của Console; tổ chức có hợp đồng qua đội bán hàng thì được xuất hóa đơn hằng tháng ([support.claude.com/en/articles/8977456](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-api-usage)). Bài trợ giúp nói người dùng nhập thẻ, nhưng không liệt kê loại thẻ được nhận và không nêu mức mua tối thiểu. Auto-reload cộng thêm "applicable taxes" vào số tiền nạp.

Về VAT, bài trợ giúp "How are taxes calculated for my API credit payments" trả lỗi 404 khi tôi mở, nên tôi chưa có nguồn chính thức. Có một dấu hiệu gián tiếp. Trên trang hỏi đáp chính sách của Bộ Tài chính ([portal.mof.gov.vn/hoidapcstc/home/cthoidap/166120](https://portal.mof.gov.vn/hoidapcstc/home/cthoidap/166120), đăng 2026-10-01), một doanh nghiệp kể rằng hóa đơn của Anthropic, PBC ghi mã số thuế Việt Nam 9000020034 và thu 10% thuế GTGT. Phần trả lời của Bộ nằm trong ảnh nên tôi không đọc được. Vì vậy, việc Anthropic thu VAT 10% cho giao dịch từ Việt Nam chỉ là suy luận. Mô hình chi phí hiển thị VAT 10% như một cột riêng.

Tỷ giá dùng trong mô hình là 25.780 VND cho 1 USD, giá bán của Vietcombank trong bảng ngày 2026-11-07 ([portal.vietcombank.com.vn](https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx)). Ngân hàng phát hành thẻ thường thu thêm phí giao dịch ngoại tệ; tôi chưa tính phí này vì mức phí tùy ngân hàng.

## Chatbot tốn bao nhiêu mỗi tháng?

Tôi viết `scripts/cost_model.py` bằng Python thuần, không cần thư viện ngoài, và đã chạy bằng lệnh `python3 -I scripts/cost_model.py`. Bản `--json` in toàn bộ 144 kịch bản.

### Mô hình giả định những gì?

Dự án chưa có `data/services.json`. Tôi đo các file menu và bảng giá trong `sources/drive/knowledge-base/02-services/` cùng `03-pricing-structure.md`, được 75.553 ký tự. Với giả định tiếng Việt có dấu tốn 2,5 đến 3,5 ký tự cho mỗi token, khối này ước tính 21.586 đến 30.221 token. Tỷ lệ ký tự trên token là giả định, chưa đo; cách đo đúng là gọi endpoint `count_tokens` của API, mà nghiên cứu này không được gọi. Mô hình chạy hai cỡ khối kiến thức: 15.000 token (menu nén thành JSON gọn) và 30.221 token (toàn bộ markdown hiện có). Mỗi lần gọi Opus còn có 5.000 token quy tắc trả lời và 1.500 token mô tả công cụ.

Mỗi lượt khách nhắn sinh hai lần gọi model: một lần lọc và phân loại, một lần viết câu trả lời. Vì vậy, 4, 6 hay 8 lần gọi tương ứng 2, 3 hay 4 lượt khách nhắn. Ở phương án chỉ dùng Opus, cả hai lần gọi đều chạy Opus với đủ ngữ cảnh. Ở phương án chia model, bước lọc chạy Haiku 5.5 với prompt 2.000 token và 1.000 token lịch sử gần nhất.

Hồ sơ đầu ra cơ bản: câu trả lời 350 token cộng 400 token thinking; bước lọc 60 token cộng 150 token thinking. Hồ sơ đầu ra cao: câu trả lời 600 token cộng 1.200 token thinking; bước lọc 80 token cộng 300 token thinking. Sau mỗi lượt, lịch sử dài thêm phần trả lời, phần thinking, 380 token công cụ và 60 token tin nhắn khách.

Khi bật caching, phần quy tắc cộng menu được cache 1 giờ và dùng chung cho mọi khách. Điều kiện là phần đầu prompt phải giống hệt nhau từng byte, không chứa tên khách hay giờ hiện tại. Mô hình coi lúc mở đầu cuộc hội thoại là ngẫu nhiên, rải đều trong 15 giờ mở cửa (9h đến 24h, giờ mở cửa vẫn chưa chốt theo claim K8). Lịch sử hội thoại được cache 5 phút; tôi giả định 70% lượt khách trả lời trong 5 phút. Mỗi cuộc hội thoại còn có một tin hỏi thăm do Opus soạn qua Batches, đầu vào 2.500 token, đầu ra 550 token, tốn khoảng 0,0105 USD.

### Kết quả với khối kiến thức 15.000 token, hồ sơ đầu ra cơ bản

Đơn vị là USD mỗi tháng, đã gồm tin hỏi thăm qua Batches, chưa gồm VAT. Cột cuối quy đổi phương án rẻ nhất sang VND.

| Hội thoại/tháng | Lần gọi/hội thoại | Chỉ Opus, không cache | Chỉ Opus, có cache | Chia model, không cache | Chia model, có cache | Chia model có cache, VND |
|---|---|---|---|---|---|---|
| 300 | 4 | 122,02 | 48,44 | 66,50 | 43,48 | 1.120.830 |
| 300 | 6 | 185,74 | 59,53 | 100,33 | 51,99 | 1.340.174 |
| 300 | 8 | 252,32 | 71,27 | 135,58 | 61,08 | 1.574.612 |
| 1.000 | 4 | 406,74 | 93,55 | 221,66 | 77,00 | 1.984.950 |
| 1.000 | 6 | 619,14 | 130,50 | 334,42 | 105,36 | 2.716.096 |
| 1.000 | 8 | 841,06 | 169,63 | 451,95 | 135,67 | 3.497.555 |
| 3.000 | 4 | 1.220,22 | 226,76 | 664,97 | 177,11 | 4.565.830 |
| 3.000 | 6 | 1.857,42 | 337,61 | 1.003,27 | 262,19 | 6.759.270 |
| 3.000 | 8 | 2.523,18 | 455,02 | 1.355,84 | 353,13 | 9.103.647 |

### Kết quả thay đổi thế nào khi giả định đổi?

Với 1.000 hội thoại và 6 lần gọi, phương án chia model có cache tốn 105,36 USD ở trường hợp cơ bản. Con số lên 127,36 USD khi khối kiến thức là 30.221 token, 180,83 USD khi đầu ra theo hồ sơ cao, và 202,83 USD khi cả hai cùng xảy ra. Trường hợp xấu nhất này vừa vượt 200 USD tín dụng của gói Ultra.

Thời hạn cache cho phần dùng chung ảnh hưởng nhiều. Với 1.000 hội thoại và 6 lần gọi, phần chat tốn 162,44 USD khi cache 5 phút và 94,86 USD khi cache 1 giờ. Lý do: khoảng 33 cuộc hội thoại mỗi ngày rải trên 15 giờ, nên khoảng cách giữa hai khách thường dài hơn 5 phút. Với cache 5 phút, 83% cuộc hội thoại gặp cache nguội; với cache 1 giờ, tỷ lệ này còn 11%.

Khi đã bật cache, phần lớn chi phí nằm ở token đầu ra, gồm cả thinking. Ở trường hợp 1.000 hội thoại, 6 lần gọi, chỉ dùng Opus có cache, mỗi cuộc hội thoại tốn khoảng 0,12 USD, trong đó khoảng 0,058 USD là đầu ra. Vì vậy, giảm `effort` cho các bước đơn giản tiết kiệm nhiều hơn là cắt bớt menu.

### So với tín dụng 200 USD của gói Ultra

Ở trường hợp cơ bản, phương án chia model có cache nằm trong 200 USD với 300 và 1.000 hội thoại mỗi tháng. Với 3.000 hội thoại, phương án này tốn 177 đến 353 USD, nên anh phải mua thêm tín dụng. Mọi phương án không cache đều vượt 200 USD từ mức 1.000 hội thoại trở lên. Mô hình chưa tính: yêu cầu bị lỗi phải gửi lại, câu trả lời bị bộ lọc an toàn từ chối rồi chạy lại, ảnh khách gửi (ảnh tốn thêm token), web search (10 USD cho 1.000 lượt tìm), phí Zalo, phí máy chủ, phí ngoại tệ của thẻ và VAT.

### Nhận định C2 của báo cáo trước sai ở đâu?

Phép tính của báo cáo trước đúng: 6.000 lần gọi với 2.000 token vào và 400 token ra cho 96 USD, với 6.000 token vào và 800 token ra cho 240 USD. Mô hình tái tạo đúng hai con số này. Tuy vậy, giả định 2.000 đến 6.000 token đầu vào mỗi lần gọi thấp hơn nhiều so với một prompt chứa menu. Riêng menu hiện tại đã ước tính 21.586 đến 30.221 token. Báo cáo trước cũng không tính thinking và không tính caching. Với cùng 1.000 hội thoại và 6 lần gọi, khoảng hợp lý theo mô hình này là 105 đến 619 USD, tùy có cache và có chia model hay không.

## Đối chiếu các nhận định của báo cáo trước

| Mã | Kết luận | Căn cứ |
|---|---|---|
| A1 | Đúng | Trang api-credits-for-subscribers ghi "$200 USD (Ultra)"; phải liên kết tổ chức Console, sau 7 ngày dùng gói, người nhận có vai trò Owner, Admin hoặc Billing. |
| A2 | Đúng | Trang legal-and-compliance cấm "route requests through Free, Pro, Max, or Ultra plan credentials"; người xây sản phẩm phải dùng API key từ Console. |
| A3 | Đúng | Trang models overview và trang pricing: mã `claude-opus-5-5`, "$4 / input MTok, $20 / output MTok". |
| A4 | Đúng | Tín dụng "don't change your usage limits in Claude"; khi hết, yêu cầu dừng nếu tổ chức không có tín dụng mua thêm hay auto-reload. Câu "không bật auto-reload mặc định" là đề xuất, không phải dữ kiện. |
| A5 | Đúng một phần | Tài liệu Agent SDK mô tả SDK là bộ công cụ của Claude Code, gồm đọc ghi file và chạy lệnh; muốn gọi API trực tiếp thì dùng Client SDK. Chọn Messages API cho bản đầu là nhận định thiết kế, tài liệu không bắt buộc. |
| A6 | Đúng | Commercial Terms mục B cấm huấn luyện trên dữ liệu khách hàng; trang privacy ghi xóa "within 30 days"; cuộc chat bị gắn cờ có thể giữ tới 2 năm. |
| A7 | Đúng, cần nói rõ thêm | Trang aup hiển thị "Effective Nov 12, 2026". Hôm nay 2026-11-07 bản đang có hiệu lực là bản 2025-09-15; cả hai bản đều bắt chatbot báo là AI. |
| C2 | Đúng một phần | Phép tính 96 và 240 USD đúng; giả định 2.000 đến 6.000 token đầu vào bỏ qua khối menu ước tính 21.586 đến 30.221 token, thinking và caching. |

## Anh cần quyết gì?

Quyết định thứ nhất là tổ chức Console nào nhận tín dụng Ultra. Anh chỉ liên kết được một tổ chức và không tự đổi được. Tôi đề xuất tạo một tổ chức mới mang tên thom house, đặt spend limit thấp hơn 200 USD cho workspace của chatbot, và không bật auto-reload trong giai đoạn thử. Điểm yếu: khi tín dụng hết giữa tháng, chatbot ngừng trả lời cho tới chu kỳ sau, trừ khi anh mua thêm.

Quyết định thứ hai là cách xử lý câu hỏi sức khỏe cá nhân. Lựa chọn một: chatbot chỉ trả lời thông tin chung, còn câu hỏi về triệu chứng của khách thì soạn nháp cho một nhân viên có chuyên môn duyệt trước khi gửi. Lựa chọn này đáp ứng yêu cầu người duyệt của Usage Policy nhưng khách phải chờ. Lựa chọn hai: chatbot từ chối loại câu hỏi đó và mời khách gọi điện hoặc tới tiệm. Lựa chọn này đơn giản hơn nhưng mất một phần nhu cầu tư vấn. Tôi đề xuất lựa chọn một. Anh cần cho biết ai ở thom house đủ chuyên môn, và có chứng chỉ hành nghề nào không, để làm người duyệt.

Quyết định thứ ba là chia model hay chỉ dùng Opus. Tôi đề xuất bắt đầu bằng Opus 5.5 cho câu trả lời và Haiku 5.5 cho bước lọc, rồi đo chi phí và chất lượng thật trong hai tuần đầu. Điểm yếu: hai model làm hệ thống phức tạp hơn và mất phần cache dùng chung giữa hai bước.

## Câu hỏi còn mở

Tôi chưa đo số token thật của menu tiếng Việt, nên mọi con số chi phí là ước tính. Tôi chưa có nguồn chính thức về cách Anthropic tính VAT cho giao dịch từ Việt Nam. Tôi chưa kiểm tra luật Việt Nam về việc chuyển dữ liệu sức khỏe của khách ra nước ngoài. Tôi chưa xác định nhân viên thom house nào đủ điều kiện làm người duyệt theo Usage Policy. Mức giới hạn của bậc Evaluation không được công bố.

## Nói ngắn gọn nhất

Gói Ultra không được dùng làm tài khoản cho chatbot, nhưng gói này cho 200 USD tín dụng API mỗi tháng. Anh nhận khoản này bằng cách liên kết gói với một tổ chức Console của thom house, rồi cho chatbot gọi Opus 5.5 bằng API key của tổ chức đó. Nếu bật prompt caching với thời hạn 1 giờ và để Haiku làm bước lọc, khoảng 1.000 cuộc hội thoại mỗi tháng tốn chừng 105 USD theo ước tính, nằm trong khoản tín dụng; không bật caching thì gấp khoảng sáu lần. Chatbot phải báo khách rằng đây là AI, và mọi lời khuyên sức khỏe dành riêng cho một khách phải qua người có chuyên môn duyệt trước khi gửi.

## Nguồn

Tất cả truy cập ngày 2026-11-07.

- Claude pricing (gói): https://claude.com/pricing
- API credits for Max, Ultra, and Team plans: https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers
- Bài trợ giúp 17154008: https://support.claude.com/en/articles/17154008-monthly-api-credits-for-max-ultra-and-team-plans
- Credit Terms: https://www.anthropic.com/legal/credit-terms
- Claude Code legal and compliance: https://code.claude.com/docs/en/legal-and-compliance
- Agent SDK overview: https://code.claude.com/docs/en/agent-sdk/overview
- Consumer Terms (hiệu lực 2025-10-08): https://www.anthropic.com/legal/consumer-terms
- Commercial Terms (hiệu lực 2025-06-17): https://www.anthropic.com/legal/commercial-terms
- Usage Policy (hiệu lực 2026-11-12): https://www.anthropic.com/legal/aup
- Usage Policy bản 2025-09-15: https://www.anthropic.com/legal/archive/22742366-2ef0-4c7a-a833-6523f10d3944
- Pricing (API): https://platform.claude.com/docs/en/about-claude/pricing
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Thinking: https://platform.claude.com/docs/en/build-with-claude/thinking
- Rate limits: https://platform.claude.com/docs/en/api/rate-limits
- API and data retention: https://platform.claude.com/docs/en/build-with-claude/api-and-data-retention
- Data residency: https://platform.claude.com/docs/en/manage-claude/data-residency
- Privacy, commercial retention: https://privacy.claude.com/en/articles/7996866
- Supported countries: https://www.anthropic.com/supported-countries
- Purchasing API credits: https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-api-usage
- Bài thuế API 9001209: https://support.claude.com/en/articles/9001209-how-are-taxes-calculated-for-my-api-credit-payments (trả lỗi 404)
- Hỏi đáp Bộ Tài chính về hóa đơn Anthropic: https://portal.mof.gov.vn/hoidapcstc/home/cthoidap/166120
- Tỷ giá Vietcombank: https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx

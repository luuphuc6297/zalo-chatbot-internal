# Ràng buộc pháp lý Việt Nam cho chatbot thom house

Ngày lập: 2026-11-07. Người lập: Claude (nhánh nghiên cứu pháp lý). Tài liệu này không phải ý kiến tư vấn pháp lý. Mỗi kết luận có ghi mức chắc chắn; các điểm ghi "luật sư cần xác nhận" phải được một luật sư Việt Nam xem trước khi chatbot chạy thật.

## Phần anh cần duyệt

Chatbot của thom house sẽ đọc tin nhắn của khách trên Zalo, gửi nội dung đó sang máy chủ của Anthropic ở Mỹ để mô hình Claude soạn câu trả lời, rồi gửi câu trả lời về Zalo. Khi khách kể triệu chứng, chuyện sau sinh hay chuyện sức khỏe phụ nữ, nội dung đó là dữ liệu cá nhân nhạy cảm theo luật Việt Nam. Vì vậy chatbot chịu bốn nhóm quy định cùng lúc: bảo vệ dữ liệu cá nhân, chống tin nhắn rác, quảng cáo dịch vụ sức khỏe, và luật trí tuệ nhân tạo mới.

Tôi đã đọc văn bản gốc (bản đăng trên các trang tra cứu luật) và rút ra năm việc anh cần biết trước khi quyết định.

Thứ nhất, chatbot phải xin khách đồng ý trước khi chuyển tin nhắn sang Anthropic. Sự đồng ý phải tách theo từng mục đích, phải báo rõ có dữ liệu sức khỏe, và phải lưu lại được. Im lặng không được tính là đồng ý. Căn cứ là Điều 9 Luật Bảo vệ dữ liệu cá nhân 2025 và Điều 6 Nghị định 356/2025/NĐ-CP.

Thứ hai, việc dùng máy chủ của Anthropic ở Mỹ là chuyển dữ liệu cá nhân ra nước ngoài. thom house phải lập hồ sơ đánh giá tác động của việc chuyển dữ liệu này và nộp cho Bộ Công an trong 60 ngày kể từ lần chuyển đầu tiên (Điều 20 Luật Bảo vệ dữ liệu cá nhân). Luật miễn một số thủ tục cho hộ kinh doanh và doanh nghiệp siêu nhỏ, nhưng không miễn hồ sơ chuyển dữ liệu ra nước ngoài. Miễn trừ về hồ sơ đánh giá tác động xử lý và người phụ trách bảo vệ dữ liệu cũng không áp dụng cho bên trực tiếp xử lý dữ liệu nhạy cảm.

Thứ ba, chatbot không được nói rằng dịch vụ chữa, ngừa hay làm giảm bệnh. Tài liệu hiện có của thom house có những tên dịch vụ và câu mô tả dễ vi phạm, ví dụ *Diện chẩn ngừa đột quỵ* và *Tiêu u – Thông kinh ngực* với mô tả "hỗ trợ giảm u hạch, tuyến giáp". thom house không có giấy phép khám bệnh, chữa bệnh, nên các câu này có nguy cơ bị coi là quảng cáo dịch vụ chữa bệnh khi chưa có giấy phép.

Thứ tư, chatbot phải cho khách biết họ đang nói chuyện với hệ thống trí tuệ nhân tạo (Điều 11 Luật Trí tuệ nhân tạo, có hiệu lực từ 01/3/2026). Theo cách hiểu của tôi, chatbot này nhiều khả năng thuộc nhóm "rủi ro trung bình" và phải được khai báo với Bộ Khoa học và Công nghệ trước khi chạy. Đây là suy luận, luật sư cần xác nhận.

Thứ năm, tin nhắn khuyến mãi chỉ gửi cho khách đã đăng ký nhận, trong khung 7 giờ đến 22 giờ, tối đa 3 tin trong 24 giờ, và phải có cách từ chối dễ dùng. Nghị định chống tin nhắn rác hiện hành (91/2020) chỉ nói tới SMS, email và cuộc gọi. Tuy vậy, dự thảo nghị định thay thế của Bộ Công an (tháng 9/2026) đã mở phạm vi sang các ứng dụng như Zalo. Luật Bảo vệ dữ liệu cá nhân cũng đòi hỏi quyền từ chối nhận quảng cáo.

Anh cần quyết sáu việc, liệt kê ở mục cuối "Những việc anh cần quyết". Việc quan trọng nhất là có giữ các câu về bệnh trong kho kiến thức của chatbot hay không.

## Bảng thuật ngữ dùng trong tài liệu

Các khái niệm dưới đây lấy đúng tên trong luật. Tôi giữ một cách gọi cho mỗi khái niệm trong toàn bộ tài liệu.

| Cách gọi trong tài liệu | Nghĩa | Căn cứ |
|---|---|---|
| Dữ liệu cá nhân nhạy cảm | Dữ liệu gắn với quyền riêng tư, trong đó có tình trạng sức khỏe và đời sống tình dục. Khi bị lộ, loại dữ liệu này gây hại trực tiếp cho người đó. | Khoản 3 Điều 2 Luật 91/2025/QH15; Điều 4 Nghị định 356/2025/NĐ-CP |
| Bên kiểm soát và xử lý dữ liệu | Bên tự quyết định mục đích, cách thức và tự xử lý dữ liệu. thom house đứng ở vị trí này khi vận hành chatbot. | Khoản 9 Điều 2 Luật 91/2025/QH15 |
| Bên xử lý dữ liệu | Bên xử lý dữ liệu theo hợp đồng với bên kiểm soát. Anthropic có thể đứng ở vị trí này nếu hợp đồng quy định như vậy. | Khoản 8 Điều 2 Luật 91/2025/QH15 |
| Hồ sơ đánh giá tác động xử lý | Bộ tài liệu phân tích rủi ro khi xử lý dữ liệu cá nhân, nộp bản chính cho Bộ Công an trong 60 ngày kể từ ngày bắt đầu xử lý. | Điều 21 Luật 91/2025/QH15; Điều 19 Nghị định 356/2025/NĐ-CP |
| Hồ sơ chuyển dữ liệu ra nước ngoài | Bộ tài liệu đánh giá tác động khi chuyển dữ liệu cá nhân ra khỏi Việt Nam, nộp trong 60 ngày kể từ lần chuyển đầu tiên. | Điều 20 Luật 91/2025/QH15; Điều 18 Nghị định 356/2025/NĐ-CP |
| Người phụ trách bảo vệ dữ liệu | Nhân sự hoặc bộ phận được chỉ định bằng văn bản để lo việc bảo vệ dữ liệu, hoặc một dịch vụ thuê ngoài. | Khoản 2 Điều 33 Luật 91/2025/QH15; Điều 13 Nghị định 356/2025/NĐ-CP |
| Cơ quan chuyên trách | Cơ quan chuyên trách bảo vệ dữ liệu cá nhân thuộc Bộ Công an. Nghị định 330/2026 gọi tên là Cục An ninh mạng và phòng, chống tội phạm sử dụng công nghệ cao. | Điểm a khoản 1 Điều 33 Luật 91/2025/QH15; Điều 55 Nghị định 330/2026/NĐ-CP |
| Nhà cung cấp hệ thống trí tuệ nhân tạo | Bên đưa hệ thống trí tuệ nhân tạo vào sử dụng dưới tên hoặc thương hiệu của mình, kể cả khi hệ thống do bên khác phát triển. thom house là nhà cung cấp của chatbot mang tên thom house. | Khoản 4 Điều 3 Luật 134/2025/QH15 |
| Zalo OA | Tài khoản chính thức của doanh nghiệp trên Zalo, nơi khách nhắn tin với thom house. | Thuật ngữ nền tảng, không phải thuật ngữ luật |
| ZNS | Dịch vụ Zalo Notification Service: gửi tin theo mẫu đã duyệt tới số điện thoại của khách qua Zalo. | Thuật ngữ nền tảng, không phải thuật ngữ luật |

Tôi dùng ba mức chắc chắn. "Đã đọc văn bản" nghĩa là tôi đọc trực tiếp điều khoản. "Suy luận" nghĩa là tôi áp điều khoản vào tình huống của thom house, có nêu căn cứ. "Chưa xác minh" nghĩa là tôi chỉ thấy thông tin qua trang tin hoặc kết quả tìm kiếm.

## Tài liệu này dựa vào văn bản nào, và văn bản nào có hiệu lực vào ngày 07/11/2026?

Tôi đọc văn bản qua các trang đăng lại văn bản luật (luatvietnam.vn, hethongphapluat.com, bản PDF của Nghị định 91/2020 trên qtsc.com.vn, bản dự thảo trên bocongan.gov.vn). Trang vbpl.moj.gov.vn không phân giải được tên miền từ máy tôi, và thuvienphapluat.vn trả lỗi 403, nên tôi chưa đối chiếu được với Công báo. Luật sư nên đối chiếu số hiệu và ngày hiệu lực với Công báo trước khi dùng.

| Văn bản | Nội dung | Ngày ban hành | Hiệu lực | Tình trạng ngày 07/11/2026 | Mức chắc chắn |
|---|---|---|---|---|---|
| Luật Bảo vệ dữ liệu cá nhân, số 91/2025/QH15 | Luật gốc về dữ liệu cá nhân | Thông qua 26/6/2025 | 01/01/2026 (Điều 38) | Đang có hiệu lực | Đã đọc văn bản |
| Nghị định 356/2025/NĐ-CP | Hướng dẫn Luật 91/2025; thay Nghị định 13/2023 | 31/12/2025 | 01/01/2026 (Điều 42) | Đang có hiệu lực; Nghị định 392/2026 sửa một số điều về thủ tục | Đã đọc văn bản |
| Nghị định 13/2023/NĐ-CP | Nghị định cũ về bảo vệ dữ liệu cá nhân | 17/4/2023 | | Hết hiệu lực từ 01/01/2026 (khoản 2 Điều 42 Nghị định 356/2025). Sự đồng ý đã xin theo nghị định này vẫn dùng tiếp được (khoản 1 Điều 39 Luật 91/2025) | Đã đọc văn bản |
| Nghị định 330/2026/NĐ-CP | Xử phạt vi phạm hành chính về an ninh mạng và bảo vệ dữ liệu cá nhân | 19/8/2026 | 19/8/2026 (Điều 80) | Đang có hiệu lực | Đã đọc văn bản |
| Nghị định 392/2026/NĐ-CP | Sửa thủ tục nộp hồ sơ đánh giá tác động trong Nghị định 356 (Điều 42 đến 47) | 20/10/2026 | 15/11/2026 (Điều 48) | Chưa có hiệu lực, còn 8 ngày | Đã đọc văn bản |
| Nghị định 91/2020/NĐ-CP | Chống tin nhắn rác, thư điện tử rác, cuộc gọi rác | 14/8/2020 | 01/10/2020 | Tôi chưa thấy văn bản thay thế đã ban hành. Bộ Công an đăng dự thảo thay thế vào tháng 9/2026 | Đã đọc văn bản; tình trạng hiệu lực là suy luận |
| Luật Trí tuệ nhân tạo, số 134/2025/QH15 | Luật gốc về trí tuệ nhân tạo | Thông qua 10/12/2025 | 01/3/2026 (Điều 34) | Đang có hiệu lực. Luật này bãi bỏ Chương IV (chương về trí tuệ nhân tạo) của Luật Công nghiệp công nghệ số 71/2025/QH15 (Điều 33) | Đã đọc văn bản |
| Nghị định 142/2026/NĐ-CP | Hướng dẫn Luật Trí tuệ nhân tạo | 30/4/2026 | 01/5/2026 (Điều 45) | Đang có hiệu lực | Đã đọc văn bản |
| Quyết định 33/2026/QĐ-TTg | Danh mục hệ thống trí tuệ nhân tạo rủi ro cao | Tin đăng 02/7/2026 | | Theo báo VietnamPlus, mục y tế chỉ có hệ thống hỗ trợ phẫu thuật và rô-bốt phẫu thuật | Chưa xác minh (chỉ đọc bài báo) |
| Luật Quảng cáo sửa đổi, số 75/2025/QH15 | Sửa Luật Quảng cáo 2012 | Thông qua 16/6/2025 | 01/01/2026 (Điều 3) | Đang có hiệu lực | Đã đọc văn bản |
| Nghị định 342/2025/NĐ-CP | Hướng dẫn Luật Quảng cáo; thay Nghị định 181/2013 | 26/12/2025 | 15/02/2026 (Điều 32) | Đang có hiệu lực | Đã đọc văn bản |
| Nghị định 87/2026/NĐ-CP | Xử phạt vi phạm hành chính về văn hóa và quảng cáo | 27/3/2026 | 15/5/2026 | Đang có hiệu lực | Đã đọc văn bản |
| Luật Khám bệnh, chữa bệnh, số 15/2023/QH15 | Hoạt động khám bệnh, chữa bệnh | Thông qua 09/01/2023 | 01/01/2024 | Đang có hiệu lực; Luật 113/2025/QH15 đã sửa một phần | Đã đọc văn bản (các điều trích) |
| Luật Bảo vệ quyền lợi người tiêu dùng, số 19/2023/QH15 | Nghĩa vụ thông tin, giao dịch từ xa | Thông qua 20/6/2023 | 01/7/2024 | Đang có hiệu lực | Đã đọc văn bản (các điều trích) |
| Nghị định 81/2018/NĐ-CP, sửa bởi Nghị định 128/2024/NĐ-CP | Khuyến mại, trần giảm giá 50% | | Nghị định 128/2024 có hiệu lực 01/12/2024 | Tôi chưa xác minh tình trạng năm 2026 | Chưa xác minh |
| Luật Thương mại điện tử, số 122/2025/QH15 và Nghị định 248/2026/NĐ-CP | Thương mại điện tử | | Theo kết quả tìm kiếm: 01/7/2026 | Tôi chưa đọc văn bản | Chưa xác minh |

## Chatbot sẽ chạm tới những dữ liệu nào, và luật xếp chúng vào loại nào?

Luật chia dữ liệu cá nhân thành hai loại: dữ liệu cơ bản và dữ liệu nhạy cảm (khoản 1 Điều 2 Luật 91/2025). Danh mục dữ liệu nhạy cảm nằm ở khoản 1 Điều 4 Nghị định 356/2025. Danh mục này gồm "tình trạng sức khỏe" (điểm d), dữ liệu về đời sống tình dục (điểm e), và dữ liệu theo dõi hành vi sử dụng mạng xã hội (điểm l).

Với chatbot thom house, tôi phân loại như sau. Phần phân loại là suy luận dựa trên danh mục trên.

| Dữ liệu chatbot nhận hoặc tạo ra | Loại | Ví dụ từ tài liệu thom house |
|---|---|---|
| Tên hiển thị Zalo, mã người dùng Zalo, số điện thoại, lịch hẹn | Dữ liệu cơ bản | Thông tin đặt lịch |
| Triệu chứng, bệnh nền, tình trạng sau sinh, chuyện sảy thai hay hiếm muộn khách kể trong chat | Nhạy cảm (tình trạng sức khỏe, điểm d khoản 1 Điều 4 Nghị định 356) | `knowledge-base/01-tone-voice.md:249` dặn chatbot cách xử lý khi khách kể chuyện sảy thai, hiếm muộn |
| Nội dung trao đổi về dịch vụ vùng kín, se khít, Yoni | Có thể nhạy cảm (đời sống tình dục, điểm e) | `knowledge-base/02-services/women-health-menu.md:20` |
| Lịch sử chat dùng để chọn khuyến mãi cho từng người | Có thể nhạy cảm (dữ liệu theo dõi hành vi, điểm l) | Tính năng gửi khuyến mãi và hẹn hỏi thăm |
| Ảnh khách gửi (da, tóc, vùng cơ thể) | Thường là nhạy cảm (tình trạng sức khỏe) | Tư vấn da và tóc |

Kết luận của phần này: chatbot sẽ xử lý dữ liệu nhạy cảm trong vận hành bình thường, vì kho kiến thức của thom house dạy chatbot hỏi và trả lời về triệu chứng. Hệ quả là các quy định riêng cho dữ liệu nhạy cảm và cho thông tin sức khỏe đều áp dụng. Khoản 1 Điều 26 Luật 91/2025 yêu cầu phải có sự đồng ý khi thu thập và xử lý thông tin sức khỏe. Khoản 2 Điều 4 Nghị định 356/2025 yêu cầu phân quyền truy cập và có quy trình bảo mật riêng cho dữ liệu nhạy cảm.

## Khách phải đồng ý thế nào thì hợp lệ?

Luật đặt bốn điều kiện cho sự đồng ý. Phần này là đã đọc văn bản.

Điều kiện thứ nhất là khách phải tự nguyện và biết rõ ba thông tin: loại dữ liệu và mục đích xử lý, ai là bên kiểm soát dữ liệu, và khách có quyền gì (khoản 2 Điều 9 Luật 91/2025).

Điều kiện thứ hai là hình thức. Sự đồng ý phải rõ ràng, cụ thể, in hoặc sao chép được, kể cả ở dạng điện tử (khoản 3 Điều 9). Khoản 1 Điều 6 Nghị định 356/2025 cho phép xin đồng ý trên "nền tảng, ứng dụng có thiết lập kỹ thuật xin sự đồng ý". Cách xin phải kiểm chứng được ba thứ: ai đồng ý, đồng ý lúc nào và đồng ý với nội dung gì.

Điều kiện thứ ba là cách tách mục đích. Khách đồng ý riêng cho từng mục đích. thom house không được bắt khách đồng ý mục đích khác làm điều kiện. Im lặng hoặc không trả lời không phải là đồng ý (khoản 4 Điều 9 Luật 91/2025). thom house không được đặt sẵn lựa chọn đồng ý hay viết hướng dẫn mập mờ (khoản 3 Điều 6 Nghị định 356/2025).

Điều kiện thứ tư áp dụng cho dữ liệu nhạy cảm. Khi xin đồng ý, thom house phải nói cho khách biết dữ liệu đó là dữ liệu nhạy cảm (khoản 4 Điều 6 Nghị định 356/2025). thom house phải lưu bằng chứng đồng ý và chịu trách nhiệm chứng minh khi có tranh chấp (khoản 2 Điều 6).

Thời điểm cũng quan trọng. Khoản 1 Điều 11 Luật 91/2025 yêu cầu có sự đồng ý trước khi thu thập. Vì vậy, theo suy luận của tôi, tin nhắn đầu tiên của khách chưa nên được gửi sang Anthropic. Chatbot nên trả lời tin đầu bằng một mẫu cố định, không qua mô hình, gồm lời giới thiệu, thông báo về dữ liệu và các nút đồng ý. Chỉ khi khách bấm đồng ý, tin nhắn mới được chuyển sang Anthropic.

Điều 19 Luật 91/2025 liệt kê các trường hợp không cần đồng ý, trong đó có trường hợp "thực hiện thỏa thuận" với chủ thể dữ liệu (điểm d khoản 1). Trường hợp này có thể bao phần đặt lịch cơ bản. Tuy nhiên, Điều 26 đòi sự đồng ý riêng cho thông tin sức khỏe. Do đó tôi không khuyên dựa vào Điều 19 cho phần tư vấn. Luật sư cần xác nhận phạm vi của điểm d.

Tôi đề xuất bốn mục đồng ý tách riêng, mỗi mục một nút. Phương án này có điểm yếu: thêm một bước trước khi khách được tư vấn, nên một phần khách có thể bỏ đi. Phần khách không đồng ý chuyển sang nhân viên trả lời tay, không qua Anthropic. Cách này tránh việc ép khách đồng ý để được phục vụ (điểm b khoản 4 Điều 9 Luật 91/2025).

| Mục đồng ý | Dữ liệu liên quan | Bắt buộc để dùng chatbot? |
|---|---|---|
| Tư vấn và đặt lịch qua trợ lý trí tuệ nhân tạo, kể cả việc tin nhắn được xử lý trên máy chủ Anthropic tại Mỹ | Nội dung chat, kể cả thông tin sức khỏe khách tự kể | Có, nếu khách muốn dùng chatbot. Khách từ chối thì được chuyển sang nhân viên |
| Lưu lịch sử chăm sóc để lần sau tư vấn phù hợp hơn | Lịch sử dịch vụ, ghi chú sức khỏe | Không |
| Nhận tin hỏi thăm sau dịch vụ | Số điện thoại hoặc mã Zalo, ngày dùng dịch vụ | Không |
| Nhận tin khuyến mãi | Số điện thoại hoặc mã Zalo, sở thích dịch vụ | Không |

Khách có quyền rút lại sự đồng ý bất cứ lúc nào. Yêu cầu rút phải ở dạng văn bản, kể cả dạng điện tử kiểm chứng được (khoản 2 Điều 10 Luật 91/2025). Một tin nhắn Zalo của chính khách nhiều khả năng đáp ứng điều kiện này; đây là suy luận. Khi nhận yêu cầu, thom house phản hồi trong 2 ngày làm việc và thực hiện trong 15 ngày (khoản 2 Điều 5 Nghị định 356/2025). Việc rút đồng ý không làm mất hiệu lực các xử lý đã làm trước đó (khoản 4 Điều 10 Luật 91/2025).

## thom house phải báo cho khách những gì?

Luật không có một điều riêng tên là "thông báo quyền riêng tư". Nội dung bắt buộc nằm rải ở nhiều điều. Tôi gom lại thành tám mục; cách gom là suy luận từ các điều được dẫn.

- Loại dữ liệu chatbot xử lý và mục đích, kèm câu báo rằng thông tin sức khỏe là dữ liệu nhạy cảm (khoản 2 Điều 9 Luật 91/2025; khoản 4 Điều 6 Nghị định 356/2025).
- Tên, địa chỉ, cách liên hệ của thom house với tư cách bên kiểm soát dữ liệu (điểm b khoản 2 Điều 9).
- Các quyền của khách và cách thực hiện quyền: xem, sửa, xóa, rút đồng ý, phản đối, khiếu nại (Điều 4 Luật 91/2025; khoản 1 Điều 5 Nghị định 356/2025).
- Việc tin nhắn được chuyển sang Anthropic tại Mỹ, tên bên nhận và mục đích. Nghị định 330/2026 phạt riêng hành vi không thông báo việc chuyển dữ liệu ra nước ngoài, tổ chức nhận và mục đích xử lý (điểm b khoản 2 Điều 56).
- Việc chatbot là hệ thống xử lý tự động, nguyên tắc hoạt động ở mức mô tả, ảnh hưởng tới khách và lựa chọn để khách không tham gia (khoản 3 Điều 10 Nghị định 356/2025).
- Việc khách đang trò chuyện với hệ thống trí tuệ nhân tạo (khoản 1 Điều 11 Luật 134/2025).
- Thời gian lưu dữ liệu (khoản 3 Điều 3 Luật 91/2025 về nguyên tắc lưu đúng thời gian cần thiết).
- Với giao dịch qua mạng, tên, địa chỉ, số điện thoại, số đăng ký kinh doanh hoặc mã số thuế của thom house (điểm a và b khoản 1 Điều 37 Luật 19/2023/QH15).

## Khách có những quyền gì, và thom house phải trả lời trong bao lâu?

Điều 4 Luật 91/2025 liệt kê các quyền: được biết; đồng ý, không đồng ý, rút đồng ý; xem, sửa; yêu cầu cung cấp, xóa, hạn chế xử lý; phản đối xử lý; khiếu nại, khởi kiện, đòi bồi thường. Thời hạn trả lời nằm ở Điều 5 Nghị định 356/2025. Phần này là đã đọc văn bản.

| Yêu cầu của khách | Phản hồi đầu tiên | Thực hiện xong | Gia hạn tối đa | Mức phạt nếu trễ (tổ chức) |
|---|---|---|---|---|
| Rút đồng ý, hạn chế hoặc phản đối xử lý | 2 ngày làm việc | 15 ngày | Thêm 1 lần, không quá 15 ngày | 30 đến 40 triệu đồng (điểm a khoản 3 Điều 44 Nghị định 330/2026) |
| Xem, sửa, cung cấp dữ liệu | 2 ngày làm việc | 10 ngày; 15 ngày nếu cần bên xử lý làm | Thêm 1 lần, không quá 10 ngày | 30 đến 40 triệu đồng (điểm b khoản 3 Điều 44) |
| Xóa dữ liệu | 2 ngày làm việc | 20 ngày; 30 ngày nếu cần bên xử lý làm | Thêm 1 lần, không quá 20 ngày | 30 đến 40 triệu đồng (điểm c khoản 3 Điều 44) |

thom house phải có quy trình và biểu mẫu rõ ràng để khách thực hiện các quyền này (khoản 1 Điều 5 Nghị định 356/2025). Không có quy trình bị phạt 10 đến 20 triệu đồng (khoản 1 Điều 44 Nghị định 330/2026). Khi khách rút đồng ý, thom house còn phải yêu cầu Anthropic ngừng xử lý (điểm c khoản 1 Điều 45 Nghị định 330/2026).

## Giữ dữ liệu bao lâu, và khi nào phải xóa?

Luật không đặt một con số cố định cho dữ liệu chat. Khoản 3 Điều 3 Luật 91/2025 chỉ yêu cầu lưu "trong khoảng thời gian phù hợp với mục đích xử lý". Điểm b khoản 1 Điều 14 yêu cầu xóa khi đã hoàn thành mục đích. Thời hạn lưu phải được mô tả và giải thích trong hồ sơ đánh giá tác động xử lý (điểm d khoản 3 Điều 19 Nghị định 356/2025). Phần này là đã đọc văn bản.

Có hai con số tối thiểu tôi tìm được. Thứ nhất, bằng chứng đồng ý phải được lưu (khoản 2 Điều 6 Nghị định 356/2025), nhưng luật không ghi số năm. Thứ hai, người gửi quảng cáo phải lưu thông tin đăng ký nhận quảng cáo và yêu cầu từ chối tối thiểu 1 năm (khoản 7 Điều 11 Nghị định 91/2020). Không lưu đủ 1 năm bị phạt 20 đến 30 triệu đồng với cá nhân (điểm b khoản 2 Điều 37 Nghị định 330/2026).

Nếu dữ liệu nằm trên dịch vụ đám mây, dữ liệu phải được mã hóa khi lưu và khi truyền, với phân quyền truy cập chặt (khoản 4 Điều 12 Nghị định 356/2025). Hợp đồng với nhà cung cấp đám mây phải ghi rõ thời hạn xử lý và yêu cầu xóa (điểm đ khoản 2 Điều 12).

Con số cụ thể là việc anh quyết. Ví dụ, nội dung chat có thể giữ 12 tháng kể từ lần liên hệ cuối, còn bằng chứng đồng ý giữ suốt thời gian còn dùng dữ liệu cộng thêm 1 năm. Các con số trong câu trước chỉ là ví dụ để anh dễ hình dung, không phải yêu cầu của luật.

## thom house có được miễn hồ sơ đánh giá tác động và người phụ trách bảo vệ dữ liệu không?

Câu trả lời ngắn: nhiều khả năng không được miễn, vì chatbot trực tiếp xử lý dữ liệu sức khỏe. Hồ sơ chuyển dữ liệu ra nước ngoài thì luật không miễn cho ai theo quy mô.

Điều 38 Luật 91/2025 và Điều 41 Nghị định 356/2025 có hai mức miễn. Hộ kinh doanh và doanh nghiệp siêu nhỏ không phải lập hồ sơ đánh giá tác động xử lý (Điều 21, Điều 22) và không phải chỉ định người phụ trách bảo vệ dữ liệu (khoản 2 Điều 33). Doanh nghiệp nhỏ và doanh nghiệp khởi nghiệp được chọn làm hay không làm các việc đó trong 5 năm kể từ 01/01/2026. Cả hai mức miễn đều có ngoại lệ: không áp dụng cho bên "trực tiếp xử lý dữ liệu cá nhân nhạy cảm", bên kinh doanh dịch vụ xử lý dữ liệu, hoặc bên xử lý dữ liệu của từ 100 nghìn người trở lên (khoản 2 Điều 41 Nghị định 356/2025). Phần này là đã đọc văn bản.

Áp vào thom house, tôi suy luận rằng chatbot đưa thom house vào nhóm "trực tiếp xử lý dữ liệu cá nhân nhạy cảm". Căn cứ là kho kiến thức dạy chatbot hỏi về triệu chứng và sức khỏe sinh sản. Do đó thom house nhiều khả năng phải lập hồ sơ đánh giá tác động xử lý và chỉ định người phụ trách bảo vệ dữ liệu, dù là hộ kinh doanh hay doanh nghiệp siêu nhỏ. Luật sư cần xác nhận cách hiểu cụm "trực tiếp xử lý".

Miễn trừ ở Điều 38 không nhắc tới Điều 20 (chuyển dữ liệu ra nước ngoài). Vì vậy hồ sơ chuyển dữ liệu ra nước ngoài là bắt buộc với mọi quy mô, trừ các trường hợp ở khoản 6 Điều 20 Luật 91/2025 và khoản 3 Điều 17 Nghị định 356/2025. Không trường hợp nào trong hai danh sách đó khớp với việc gửi tin nhắn khách sang Anthropic để soạn câu trả lời. Đây là suy luận; luật sư cần xác nhận.

Người phụ trách bảo vệ dữ liệu phải có trình độ cao đẳng trở lên, ít nhất 2 năm kinh nghiệm ở một trong các lĩnh vực như pháp chế, công nghệ thông tin hay quản trị rủi ro, và đã được đào tạo về bảo vệ dữ liệu (khoản 2 Điều 13 Nghị định 356/2025). Nếu thom house không có người đủ điều kiện, khoản 2 Điều 33 Luật 91/2025 cho phép thuê tổ chức hoặc cá nhân cung cấp dịch vụ bảo vệ dữ liệu.

## Gửi tin nhắn của khách sang Anthropic ở Mỹ và qua Zalo thì phải làm gì?

Việc dùng máy chủ Anthropic là chuyển dữ liệu ra nước ngoài. Điểm c khoản 1 Điều 20 Luật 91/2025 tính cả trường hợp "sử dụng nền tảng ở ngoài lãnh thổ" để xử lý dữ liệu thu thập tại Việt Nam. Điểm c khoản 1 Điều 17 Nghị định 356/2025 nói tương tự. Phần này là đã đọc văn bản.

Hồ sơ chuyển dữ liệu ra nước ngoài gồm ba phần (khoản 2 Điều 18 Nghị định 356/2025). Phần một là báo cáo đánh giá theo Mẫu số 09. Phần hai là bản sao hợp đồng hoặc văn bản chuyển giao dữ liệu giữa thom house và bên nhận. Phần ba là chính sách, quy trình và biểu mẫu bảo vệ dữ liệu của thom house. Báo cáo phải có các nội dung ở khoản 3 Điều 18, trong đó có sơ đồ luồng dữ liệu, cách xin đồng ý, chính sách lưu và xóa, biện pháp bảo vệ sau khi chuyển, và đánh giá mức bảo vệ của bên nhận.

Thời hạn nộp là 60 ngày kể từ lần chuyển đầu tiên (khoản 2 Điều 20 Luật 91/2025). Hồ sơ cập nhật định kỳ 6 tháng khi có thay đổi, và cập nhật trong 10 ngày khi có thay đổi lớn, ví dụ đổi bên xử lý (Điều 20 Nghị định 356/2025). Từ 15/11/2026, Nghị định 392/2026 quy định nộp về cơ quan chuyên trách thuộc Bộ Công an. Hồ sơ được trả kết quả "đạt", "đạt cần bổ sung" hoặc "không đạt" trong 11 ngày làm việc (Điều 43 Nghị định 392/2026).

Hợp đồng với Anthropic phải đáp ứng hai nhóm yêu cầu. Thứ nhất, bên xử lý chỉ được nhận dữ liệu sau khi có hợp đồng xử lý dữ liệu (điểm a khoản 2 Điều 37 Luật 91/2025). Thứ hai, hợp đồng với nhà cung cấp đám mây phải ghi việc tuân thủ luật Việt Nam, luồng dữ liệu, vai trò các bên, biện pháp bảo mật, nghĩa vụ báo thay đổi, thời hạn xóa và việc bảo đảm quyền của khách (khoản 2 Điều 12 Nghị định 356/2025). Tôi chưa đối chiếu điều khoản thương mại hay thỏa thuận xử lý dữ liệu của Anthropic với danh sách này; việc đó thuộc nhánh nghiên cứu về Anthropic và cần luật sư. Không có hợp đồng ràng buộc trách nhiệm với bên nhận bị phạt 50 đến 100 triệu đồng (điểm a khoản 2 Điều 56 Nghị định 330/2026).

Zalo là nền tảng nơi tin nhắn đi qua. Tôi chưa xác minh máy chủ Zalo đặt ở đâu và Zalo đứng vai trò pháp lý nào với dữ liệu của OA. Khi lập hồ sơ, thom house cần ghi Zalo vào sơ đồ luồng dữ liệu. Nếu dữ liệu lưu trong máy của thom house (ứng dụng chạy trên macOS), máy đó cũng thuộc hệ thống phải được bảo vệ theo khoản 2 Điều 4 Nghị định 356/2025.

## Vi phạm thì bị phạt bao nhiêu?

Mức trần nằm ở Điều 8 Luật 91/2025 và khoản 4 Điều 7 Nghị định 330/2026. Vi phạm chung tối đa 3 tỷ đồng. Vi phạm về chuyển dữ liệu ra nước ngoài tối đa 5% doanh thu năm trước. Mua bán dữ liệu tối đa 10 lần khoản thu. Các mức này là mức cho tổ chức. Cá nhân bị phạt một nửa. Hộ kinh doanh bị phạt theo mức của cá nhân (khoản 3 Điều 2 Nghị định 330/2026). Phần này là đã đọc văn bản.

Bảng dưới liệt kê các hành vi sát với chatbot. Mức trong bảng là mức cho tổ chức.

| Hành vi | Mức phạt cho tổ chức | Căn cứ trong Nghị định 330/2026 |
|---|---|---|
| Xử lý dữ liệu khi chưa có đồng ý, đặt sẵn lựa chọn đồng ý, không cho đồng ý theo từng mục đích, không lưu nhật ký đồng ý, không báo khách rằng dữ liệu nhạy cảm đang được xử lý | 30 đến 50 triệu đồng | Khoản 1 Điều 43 |
| Coi im lặng là đồng ý; cố ý xử lý tiếp sau khi khách yêu cầu ngừng | 50 đến 70 triệu đồng | Khoản 2 Điều 43 |
| Không có quy trình cho khách thực hiện quyền; trả lời quá 2 ngày làm việc | 10 đến 20 triệu đồng | Khoản 1 Điều 44 |
| Không lập hoặc không nộp hồ sơ đánh giá tác động xử lý | 20 đến 30 triệu đồng; có thể bị buộc dừng xử lý | Khoản 1 và điểm b khoản 3 Điều 55 |
| Không lập hoặc không nộp hồ sơ chuyển dữ liệu ra nước ngoài | 30 đến 50 triệu đồng; có thể bị buộc ngừng chuyển | Khoản 1 và điểm b khoản 6 Điều 56 |
| Không có hợp đồng với bên nhận; không xin đồng ý hoặc không báo khách về việc chuyển ra nước ngoài | 50 đến 100 triệu đồng | Khoản 2 Điều 56 |
| Không chỉ định người phụ trách bảo vệ dữ liệu bằng văn bản; người được chỉ định không đủ điều kiện | 20 đến 30 triệu đồng | Khoản 2 Điều 57 |
| Không thông báo hoặc không giải thích việc xử lý tự động; không cho khách từ chối xử lý tự động | 50 đến 70 triệu đồng | Điểm a và b khoản 2 Điều 67 |
| Không tự đánh giá tuân thủ hằng năm với hệ thống trí tuệ nhân tạo xử lý dữ liệu cá nhân | 20 đến 50 triệu đồng | Khoản 1 Điều 67 |

Ngoài tiền phạt, cơ quan có thẩm quyền có thể buộc xóa dữ liệu đã thu thập trái phép (điểm a khoản 4 Điều 43). Vi phạm làm lộ dữ liệu còn có thể bị truy cứu trách nhiệm hình sự (khoản 1 Điều 8 Luật 91/2025). Khi phát hiện vi phạm có thể gây hại cho sức khỏe, danh dự hay tài sản của khách, thom house phải báo cơ quan chuyên trách chậm nhất 72 giờ (khoản 1 Điều 23 Luật 91/2025), theo Mẫu số 08 của Nghị định 356/2025 (Điều 28).

## Gửi khuyến mãi qua Zalo OA và ZNS phải theo quy định nào?

Văn bản chuyên về tin nhắn quảng cáo hiện hành là Nghị định 91/2020. Phạm vi của nghị định này là quảng cáo bằng tin nhắn SMS, MMS, USSD, thư điện tử và gọi điện thoại (Điều 1). Tin nhắn qua Zalo OA và ZNS không được nêu tên. Vì vậy, theo câu chữ, các quy tắc số lượng và khung giờ của Nghị định 91/2020 chưa chắc áp dụng trực tiếp cho tin nhắn Zalo. Đây là suy luận; luật sư cần xác nhận.

Tôi vẫn khuyên áp các quy tắc đó cho Zalo, vì ba lý do. Lý do thứ nhất: dự thảo nghị định thay thế do Bộ Công an đăng tháng 9/2026 mở phạm vi sang tin nhắn "thông qua" dịch vụ viễn thông trên Internet, có chương riêng về ứng dụng OTT (Điều 1, Điều 36 và 37 của dự thảo). OTT là ứng dụng nhắn tin chạy trên Internet, như Zalo. Dự thảo giữ khung 7 giờ đến 22 giờ và giới hạn 3 tin trong 24 giờ. Lý do thứ hai: Luật 91/2025 đã đòi phải có đồng ý và cách từ chối khi dùng dữ liệu cá nhân để quảng cáo. Khoản 3 Điều 28 yêu cầu khách biết rõ nội dung, phương thức, hình thức và tần suất giới thiệu sản phẩm. Khoản 4 Điều 28 dẫn sang luật chống tin nhắn rác. Khoản 5 Điều 28 cho khách quyền yêu cầu ngừng nhận quảng cáo. Lý do thứ ba: Luật 19/2023 cấm quấy rối người tiêu dùng bằng việc tiếp xúc trái ý muốn để giới thiệu dịch vụ (điểm b khoản 1 Điều 10).

Các quy tắc cụ thể của Nghị định 91/2020 như sau. Phần này là đã đọc văn bản.

- Chỉ gửi quảng cáo khi người nhận đã đồng ý trước, qua một trong các cách ở khoản 2 Điều 11. Một cách được nêu là khai báo và xác nhận trên ứng dụng trực tuyến hoặc mạng xã hội của người quảng cáo (điểm b).
- Ngừng gửi ngay sau khi người nhận từ chối (khoản 4 Điều 13).
- Không quá 3 tin quảng cáo tới một người trong 24 giờ, trừ khi đã thỏa thuận khác (khoản 5 Điều 13).
- Chỉ gửi trong khung 7 giờ đến 22 giờ, trừ khi đã thỏa thuận khác (khoản 6 Điều 13).
- Lưu thông tin đăng ký, yêu cầu từ chối và xác nhận từ chối tối thiểu 1 năm (khoản 7 Điều 11).
- Không gửi tới số điện thoại trong Danh sách không quảng cáo (khoản 1 Điều 11). Quy tắc này đáng chú ý khi gửi ZNS theo số điện thoại.

Mức phạt cho các hành vi này nằm ở Điều 37 Nghị định 330/2026, mức áp cho cá nhân; tổ chức bị phạt gấp đôi (khoản 1 Điều 7). Gửi tin quảng cáo chưa được đồng ý bị phạt 10 đến 20 triệu đồng (điểm a khoản 1). Gửi quá 3 tin trong 24 giờ hoặc ngoài khung 7 giờ đến 22 giờ bị phạt 30 đến 50 triệu đồng (điểm n và o khoản 3). Không có đủ hình thức từ chối bị phạt 70 đến 80 triệu đồng (điểm a khoản 5).

Tin hỏi thăm sau dịch vụ không phải tin quảng cáo nếu chỉ hỏi về trải nghiệm và sức khỏe sau buổi làm. Nếu tin hỏi thăm kèm ưu đãi hoặc mời đặt lịch mới, tin đó có tính quảng cáo. Ranh giới này là suy luận từ định nghĩa ở khoản 1 Điều 3 Nghị định 91/2020: tin nhắn quảng cáo là tin giới thiệu sản phẩm, dịch vụ có mục đích sinh lợi. Tôi đề xuất xin đồng ý riêng cho tin hỏi thăm và giữ tin hỏi thăm không kèm khuyến mãi.

Zalo có quy định riêng về loại nội dung được gửi qua OA và ZNS. Quy định đó là điều kiện hợp đồng với Zalo chứ không phải luật. Nhánh nghiên cứu về Zalo xem phần này.

## Chatbot được nói gì về dịch vụ sức khỏe, y học cổ truyền và mỹ phẩm?

thom house không phải cơ sở khám bệnh, chữa bệnh. Chính tài liệu của thom house ghi rõ chị Thơm không phải bác sĩ hay lương y, và thom house không phải cơ sở y tế (`knowledge-base/00-brand-essence.md:11-12`). Theo luật, chỉ cơ sở có giấy phép hoạt động mới được cung cấp dịch vụ khám bệnh, chữa bệnh (khoản 6 Điều 2 và điểm a khoản 15 Điều 7 Luật 15/2023/QH15). "Chữa bệnh" trong luật là việc người có giấy phép hành nghề dùng kỹ thuật chuyên môn để giải quyết tình trạng bệnh hoặc ngăn bệnh xuất hiện, tiến triển (khoản 2 Điều 2). Phần này là đã đọc văn bản.

Về quảng cáo, khoản 4 Điều 20 Luật Quảng cáo (sửa bởi Luật 75/2025) yêu cầu quảng cáo dịch vụ khám bệnh, chữa bệnh phải có giấy phép. Nghị định 342/2025 xếp dịch vụ khám bệnh, chữa bệnh vào danh mục dịch vụ đặc biệt (khoản 6 Điều 3). Quảng cáo dịch vụ này phải ghi số giấy phép và phạm vi chuyên môn (Điều 9). Nghị định 87/2026 phạt quảng cáo dịch vụ khám bệnh, chữa bệnh khi chưa có giấy phép từ 30 đến 40 triệu đồng với cá nhân (khoản 3 Điều 75), gấp đôi với tổ chức (khoản 3 Điều 6). Quảng cáo gây hiểu nhầm về công dụng bị phạt 20 đến 40 triệu đồng với cá nhân (khoản 2 Điều 53). Luật 19/2023 cấm cung cấp thông tin sai lệch về công dụng dịch vụ (điểm a khoản 1 Điều 10).

Tài liệu hiện có của thom house chứa các câu tôi cho là rủi ro cao. Đánh giá này là suy luận và luật sư cần xem từng câu.

| Câu hoặc tên trong tài liệu | Vị trí | Vì sao rủi ro |
|---|---|---|
| Tên dịch vụ *Diện chẩn ngừa đột quỵ*, giá 2.990.000 đồng | `knowledge-base/03-pricing-structure.md:35` | "Ngừa đột quỵ" là nói ngăn một bệnh cụ thể, khớp định nghĩa chữa bệnh ở khoản 2 Điều 2 Luật 15/2023 |
| Tên *Tiêu u – Thông kinh ngực*, ghi đối tượng "U hạch, tuyến giáp, đau ngực" | `knowledge-base/02-services/women-health-menu.md:15` | "Tiêu u" và nhắm vào u hạch, tuyến giáp là công dụng trị bệnh |
| Câu mẫu gợi ý chatbot nói liệu trình "hỗ trợ giảm u hạch, tuyến giáp ở cổ ngực" | `knowledge-base/01-tone-voice.md:511` | Thêm chữ "hỗ trợ" vẫn là nói về tác dụng lên bệnh. Tài liệu của thom house coi câu này là cách nói an toàn, tôi không đồng ý |
| Bước "giải các tắt nghẽn có nguy cơ gây tức, lối ngực và ung thư vú" | `knowledge-base/02-services/women-health-menu.md:190` | Gắn dịch vụ với nguy cơ ung thư vú dễ bị hiểu là phòng ngừa ung thư |

Kho kiến thức đã có một số chỉ dẫn tốt, ví dụ cấm nói "chữa khỏi sa tử cung", "phòng ngừa ung thư vú" (`knowledge-base/01-tone-voice.md:240`). Các chỉ dẫn này nên giữ. Vấn đề là các tên dịch vụ ở bảng trên vẫn có thể đi vào câu trả lời của chatbot.

Về y học cổ truyền, diện chẩn và bấm huyệt, Luật 15/2023 không cấm spa nhắc tới các phương pháp này như kỹ thuật thư giãn, chăm sóc. Luật cấm việc dùng chúng để khám bệnh, chữa bệnh khi không có giấy phép, và cấm lợi dụng kiến thức y học để quảng cáo gian dối (khoản 20 Điều 7). Danh sách hình thức cơ sở khám bệnh, chữa bệnh có "phòng chẩn trị y học cổ truyền" (điểm đ khoản 1 Điều 48 Luật 15/2023; Điều 39 Nghị định 96/2023). Danh sách đó không có loại hình spa. Tôi chưa tìm được văn bản riêng quy định ranh giới giữa xoa bóp chăm sóc và xoa bóp trị liệu. Luật sư hoặc Sở Y tế cần xác nhận. Ngoài ra, cơ sở xoa bóp là ngành kinh doanh có điều kiện về an ninh trật tự. Tôi chỉ thấy điều này qua bài viết thứ cấp, chưa đọc văn bản.

Về mỹ phẩm, nếu chatbot giới thiệu sản phẩm bán kèm, quảng cáo mỹ phẩm phải có phiếu công bố (điểm b khoản 4 Điều 20 Luật Quảng cáo sửa đổi). Nội dung không được gây hiểu nhầm sản phẩm là thuốc. Nội dung không được dùng hình ảnh hay danh nghĩa bác sĩ, cơ sở y tế (khoản 2 và 4 Điều 4 Nghị định 342/2025). Phạt 30 đến 40 triệu đồng với cá nhân khi gây hiểu nhầm mỹ phẩm là thuốc (điểm b khoản 4 Điều 70 Nghị định 87/2026). Quảng cáo dùng từ "nhất", "duy nhất", "số một" mà không có tài liệu chứng minh bị phạt 10 đến 20 triệu đồng (điểm a khoản 2 Điều 50 Nghị định 87/2026).

Còn một câu hỏi chưa có đáp án rõ: một câu trả lời riêng cho một khách trong chat có phải là "quảng cáo" không. Định nghĩa quảng cáo nói tới việc giới thiệu "đến công chúng", và Điều 19 Luật Quảng cáo sửa đổi loại trừ một số thông tin mô tả dịch vụ. Tin khuyến mãi gửi hàng loạt thì rõ ràng là quảng cáo. Câu trả lời một-một thì chưa chắc. Dù ở trường hợp nào, Luật 19/2023 vẫn cấm thông tin sai lệch về công dụng. Vì vậy tôi đề xuất cùng một bộ lọc cho cả hai loại tin.

## Luật Trí tuệ nhân tạo đòi hỏi gì ở chatbot này?

Luật Trí tuệ nhân tạo 134/2025/QH15 có hiệu lực từ 01/3/2026. Chatbot mới chạy sau ngày này nên không hưởng thời gian chuyển tiếp 12 đến 18 tháng; thời gian đó chỉ dành cho hệ thống đã hoạt động trước 01/3/2026 (khoản 1 Điều 35). Phần này là đã đọc văn bản.

thom house đưa chatbot vào dùng dưới thương hiệu của mình, nên là nhà cung cấp theo khoản 4 Điều 3. Định nghĩa này áp dụng kể cả khi mô hình do Anthropic phát triển. Nhà cung cấp phải tự phân loại mức rủi ro trước khi đưa hệ thống vào dùng (khoản 1 Điều 10 Luật 134/2025; Điều 6 Nghị định 142/2026). Luật có ba mức rủi ro: cao, trung bình, thấp.

Tôi suy luận chatbot không thuộc nhóm rủi ro cao. Căn cứ là bài báo VietnamPlus về Quyết định 33/2026/QĐ-TTg: mục y tế của danh mục chỉ có hệ thống hỗ trợ phẫu thuật. Tôi chưa đọc văn bản quyết định này.

Tôi suy luận chatbot nhiều khả năng thuộc nhóm rủi ro trung bình. Hệ thống thuộc nhóm này khi có khả năng gây nhầm lẫn vì người dùng không nhận ra mình đang tương tác với trí tuệ nhân tạo (điểm b khoản 1 Điều 9 Luật 134/2025; khoản 1 Điều 9 Nghị định 142/2026). Chatbot nhắn tin bằng giọng nhân viên trên Zalo khớp mô tả này. Các trường hợp loại trừ ở khoản 3 Điều 9 Nghị định 142/2026 không khớp. Ví dụ, điểm c chỉ loại trừ hệ thống không tương tác với công chúng.

Nếu chatbot thuộc nhóm rủi ro trung bình, thom house phải làm hai việc trước khi chạy. Thứ nhất, lập hồ sơ phân loại rủi ro gồm thông tin nhận diện hệ thống, mô tả mục đích và bối cảnh, dữ liệu đầu vào chính, và biện pháp quản lý rủi ro (Điều 12 Nghị định 142/2026). Hồ sơ đánh giá tác động xử lý dữ liệu cá nhân được dùng thay hoặc ghép vào hồ sơ này (khoản 7 Điều 12). Thứ hai, khai báo kết quả phân loại cho Bộ Khoa học và Công nghệ qua cổng thông tin một cửa về trí tuệ nhân tạo (Điều 14 Nghị định 142/2026). Cổng tự cấp mã định danh ngay khi khai báo xong và không đòi thêm giấy tờ. Điểm yếu của cách hiểu này: nếu chatbot đã nói rõ ngay từ đầu rằng mình là trí tuệ nhân tạo, có thể lập luận rằng hệ thống không còn "khả năng gây nhầm lẫn" và chỉ là rủi ro thấp. Luật sư cần chọn một trong hai cách hiểu. Khai báo nhóm trung bình tốn ít công và an toàn hơn.

Nghĩa vụ minh bạch áp dụng cho mọi mức rủi ro có tương tác trực tiếp với người. Khoản 1 Điều 11 Luật 134/2025 yêu cầu hệ thống được thiết kế để người dùng biết mình đang tương tác với hệ thống trí tuệ nhân tạo. Thông báo phải rõ, dễ hiểu, xuất hiện trước hoặc ngay lúc người dùng tiếp cận, và không được thiết kế để che giấu (khoản 3 Điều 18 Nghị định 142/2026). Văn bản do chatbot viết không bắt buộc phải gắn dấu máy đọc (khoản 1 Điều 17 Nghị định 142/2026). Nhãn hiển thị bắt buộc với âm thanh, hình ảnh, video mô phỏng người thật (khoản 4 Điều 11 Luật 134/2025). Nếu sau này chatbot tạo ảnh hay giọng nói, quy định này sẽ áp dụng.

Nghị định 356/2025 còn thêm nghĩa vụ cho mọi hệ thống trí tuệ nhân tạo xử lý dữ liệu cá nhân (Điều 10). thom house phải báo khách về việc xử lý tự động, giải thích nguyên tắc hoạt động ở mức mô tả, và cho khách lựa chọn không tham gia (khoản 3). thom house phải tự đánh giá tuân thủ một lần mỗi năm (điểm đ khoản 5). Khoản 4 Điều 30 Luật 91/2025 yêu cầu phân loại việc xử lý dữ liệu bằng trí tuệ nhân tạo theo mức rủi ro.

Khi tích hợp mô hình của bên khác, nhà cung cấp phải thỏa thuận với bên cung cấp mô hình để phối hợp cung cấp thông tin kỹ thuật phục vụ minh bạch và giải trình (khoản 6 Điều 16 Nghị định 142/2026). Tôi chưa kiểm tra điều khoản của Anthropic về điểm này.

Tôi chưa đọc được văn bản của nghị định xử phạt riêng nào cho Luật Trí tuệ nhân tạo. Khoản 5 Điều 29 Luật 134/2025 giao Chính phủ quy định. Một tiêu đề trên LuatVietnam nói tới "Nghị định 401/2026/NĐ-CP" về xử phạt trong công nghiệp công nghệ số, có hiệu lực 22/12/2026. Tôi chưa đọc văn bản này và chưa biết văn bản có điều nào về trí tuệ nhân tạo hay không.

## Báo giá và khuyến mãi trong chat cần đúng những gì?

Đặt lịch qua chat là "giao dịch từ xa" theo khoản 5 Điều 3 Luật 19/2023/QH15, vì khách không trực tiếp kiểm tra dịch vụ trước khi giao dịch. Phần này là đã đọc văn bản.

Khi giao dịch từ xa, thom house phải cung cấp đủ và đúng: tên, địa chỉ, số điện thoại; số đăng ký kinh doanh hoặc mã số thuế; công dụng và giá dịch vụ; phí phát sinh; thời gian, địa điểm cung cấp; điều kiện đổi, hủy; và quy trình khiếu nại (khoản 1 Điều 37). Nếu thông tin thiếu hoặc sai, khách được đơn phương chấm dứt hợp đồng trong 30 ngày mà không chịu phí cho phần chưa dùng (điểm b khoản 3 Điều 38). Giá phải đúng với giá niêm yết (khoản 3 Điều 21). Thông tin sai lệch về giá hay công dụng là hành vi bị cấm (điểm a khoản 1 Điều 10).

Với chatbot, rủi ro thực tế là mô hình trả lời một giá cũ hoặc tự bịa giá. Tài liệu của thom house đã ghi một số thông tin chưa thống nhất, ví dụ địa chỉ Tân Hưng hay Tân Kiểng (`knowledge-base/00-brand-essence.md:263-267`). Tôi đề xuất chatbot chỉ báo giá lấy từ một bảng giá có ngày cập nhật, không để mô hình tự nhớ giá.

Về khuyến mại, Nghị định 128/2024 sửa Nghị định 81/2018. Theo bài viết thứ cấp, mức giảm giá không vượt quá 50% giá ngay trước thời gian khuyến mại. Một số hình thức khuyến mại phải thông báo Sở Công Thương. Tôi chưa đọc văn bản gốc và chưa xác minh tình trạng năm 2026. Luật sư hoặc kế toán của thom house cần xác nhận trước khi chatbot gửi chương trình giảm giá lớn.

## Checklist: chatbot phải làm và không được làm

Bảng dưới gom các nghĩa vụ theo tính năng. Cột "Mức chắc chắn" cho biết căn cứ đã đọc văn bản hay là suy luận.

| Tính năng | Chatbot phải làm hoặc không được làm | Căn cứ | Mức chắc chắn |
|---|---|---|---|
| Xin đồng ý | Phải trả lời tin đầu tiên của khách bằng mẫu cố định (không qua Anthropic), gồm thông báo dữ liệu và nút đồng ý riêng cho từng mục đích | Khoản 1 Điều 11, khoản 2 và 4 Điều 9 Luật 91/2025 | Nghĩa vụ: đã đọc văn bản. Cách làm bằng mẫu cố định: suy luận |
| Xin đồng ý | Phải ghi rõ rằng thông tin sức khỏe khách chia sẻ là dữ liệu nhạy cảm | Khoản 4 Điều 6 Nghị định 356/2025; điểm h khoản 1 Điều 43 Nghị định 330/2026 | Đã đọc văn bản |
| Xin đồng ý | Phải lưu bằng chứng đồng ý gồm mã khách, thời điểm, nội dung và phiên bản thông báo | Khoản 1 và 2 Điều 6 Nghị định 356/2025 | Đã đọc văn bản |
| Xin đồng ý | Không được coi việc khách tiếp tục nhắn tin là đồng ý; không được đặt sẵn lựa chọn đồng ý | Điểm d khoản 4 Điều 9 Luật 91/2025; khoản 3 Điều 6 Nghị định 356/2025 | Đã đọc văn bản |
| Xin đồng ý | Không được từ chối phục vụ khách không đồng ý nhận khuyến mãi; khách không đồng ý dùng trợ lý tự động được chuyển sang nhân viên | Điểm b khoản 4 Điều 9 Luật 91/2025; khoản 3 Điều 10 Nghị định 356/2025 | Đã đọc văn bản; cách chuyển sang nhân viên là suy luận |
| Chuyển dữ liệu ra nước ngoài | Thông báo phải nêu việc tin nhắn được xử lý tại Mỹ, tên bên nhận và mục đích | Điểm b khoản 2 Điều 56 Nghị định 330/2026 | Đã đọc văn bản |
| Chuyển dữ liệu ra nước ngoài | Phải nộp hồ sơ chuyển dữ liệu ra nước ngoài trong 60 ngày kể từ lần gửi đầu tiên sang Anthropic, kể cả giai đoạn chạy thử với khách thật | Khoản 2 Điều 20 Luật 91/2025; Điều 18 Nghị định 356/2025 | Nghĩa vụ: đã đọc văn bản. Việc áp vào giai đoạn chạy thử: suy luận |
| Chuyển dữ liệu ra nước ngoài | Phải có hợp đồng xử lý dữ liệu với Anthropic có đủ nội dung luật yêu cầu trước khi gửi dữ liệu thật | Điểm a khoản 2 Điều 37 Luật 91/2025; khoản 2 Điều 12 Nghị định 356/2025 | Đã đọc văn bản |
| Công khai là trí tuệ nhân tạo | Tin đầu tiên và phần giới thiệu OA phải nói rõ khách đang trò chuyện với trợ lý trí tuệ nhân tạo của thom house | Khoản 1 Điều 11 Luật 134/2025; khoản 3 Điều 18 Nghị định 142/2026 | Đã đọc văn bản |
| Công khai là trí tuệ nhân tạo | Không được xưng là nhân viên thật hay dùng tên người thật mà không nói là trí tuệ nhân tạo | Khoản 1 Điều 11 Luật 134/2025 | Suy luận |
| Công khai là trí tuệ nhân tạo | Phải có lệnh để khách gặp nhân viên thật bất cứ lúc nào | Khoản 3 Điều 10 Nghị định 356/2025 | Đã đọc văn bản; hình thức lệnh là suy luận |
| Khai báo hệ thống | Phải lập hồ sơ phân loại rủi ro và khai báo với Bộ Khoa học và Công nghệ trước khi chạy, nếu chatbot được xếp nhóm trung bình | Điều 10 Luật 134/2025; Điều 12 và 14 Nghị định 142/2026 | Nghĩa vụ: đã đọc văn bản. Việc xếp nhóm trung bình: suy luận, luật sư cần xác nhận |
| Từ chối nhận tin | Phải nhận diện các câu như "không nhận tin nữa", "hủy đăng ký" và ngừng gửi khuyến mãi ngay | Khoản 4 Điều 13 Nghị định 91/2020; khoản 5 Điều 28 Luật 91/2025 | Đã đọc văn bản; việc áp cho Zalo là suy luận |
| Từ chối nhận tin | Mỗi tin khuyến mãi phải kèm cách từ chối | Điểm a khoản 5 Điều 37 Nghị định 330/2026; khoản 3 Điều 28 Luật 91/2025 | Đã đọc văn bản; việc áp cho Zalo là suy luận |
| Rút đồng ý và xóa dữ liệu | Phải nhận yêu cầu rút đồng ý hoặc xóa dữ liệu qua chat, phản hồi trong 2 ngày làm việc, xóa trong 20 ngày và yêu cầu Anthropic xóa phần của Anthropic | Điều 10 Luật 91/2025; khoản 2 và 4 Điều 5 Nghị định 356/2025; điểm c khoản 1 Điều 45 Nghị định 330/2026 | Đã đọc văn bản |
| Lưu dữ liệu | Phải có thời hạn lưu cụ thể cho từng loại dữ liệu và tự xóa khi hết hạn | Khoản 3 Điều 3, điểm b khoản 1 Điều 14 Luật 91/2025 | Nguyên tắc: đã đọc văn bản. Con số: anh quyết |
| Lưu dữ liệu | Phải giữ nhật ký đăng ký và từ chối nhận khuyến mãi ít nhất 1 năm | Khoản 7 Điều 11 Nghị định 91/2020; điểm b khoản 2 Điều 37 Nghị định 330/2026 | Đã đọc văn bản |
| Lưu dữ liệu | Phải mã hóa dữ liệu khi lưu và khi truyền nếu dùng dịch vụ đám mây; phải phân quyền người xem dữ liệu sức khỏe | Khoản 4 Điều 12, khoản 2 Điều 4 Nghị định 356/2025 | Đã đọc văn bản |
| Lọc nội dung y khoa | Không được nói dịch vụ chữa, trị, ngừa, tiêu, làm giảm một bệnh cụ thể (đột quỵ, u, tuyến giáp, ung thư, viêm nhiễm, sa tử cung, vô sinh) | Khoản 2 Điều 2, khoản 15 và 20 Điều 7 Luật 15/2023; khoản 3 Điều 75 Nghị định 87/2026; điểm a khoản 1 Điều 10 Luật 19/2023 | Điều luật: đã đọc văn bản. Danh sách từ: suy luận |
| Lọc nội dung y khoa | Không được chẩn đoán, gọi tên bệnh của khách, hay khuyên bỏ hoặc thay thuốc | Khoản 1 và 2 Điều 2, điểm a khoản 15 Điều 7 Luật 15/2023 | Suy luận |
| Lọc nội dung y khoa | Không được gọi chị Thơm hay kỹ thuật viên là bác sĩ, lương y; không dùng danh nghĩa bác sĩ để giới thiệu mỹ phẩm | Khoản 17 Điều 7 Luật 15/2023; khoản 4 Điều 4 Nghị định 342/2025 | Đã đọc văn bản |
| Lọc nội dung y khoa | Phải khuyên khách gặp bác sĩ khi khách kể triệu chứng nặng hoặc dấu hiệu cấp cứu | Điểm a khoản 1 Điều 19 Luật 91/2025 cho phép xử lý dữ liệu để bảo vệ tính mạng, sức khỏe trong trường hợp cấp bách | Suy luận (thực hành an toàn, không phải nghĩa vụ trực tiếp) |
| Lọc nội dung y khoa | Không được dùng từ "nhất", "duy nhất", "số một" khi không có tài liệu chứng minh | Điểm a khoản 2 Điều 50 Nghị định 87/2026 | Đã đọc văn bản |
| Đồng ý nhận khuyến mãi | Chỉ gửi khuyến mãi cho khách đã bấm đồng ý mục khuyến mãi; khung 7 giờ đến 22 giờ; tối đa 3 tin trong 24 giờ | Khoản 2 Điều 11, khoản 5 và 6 Điều 13 Nghị định 91/2020; Điều 28 Luật 91/2025 | Đã đọc văn bản; việc áp cho Zalo là suy luận |
| Đồng ý nhận khuyến mãi | Không được dùng thông tin sức khỏe khách kể để chọn khuyến mãi, trừ khi khách đã đồng ý riêng cho mục đích đó | Khoản 4 Điều 9 Luật 91/2025; khoản 2 Điều 63 Nghị định 330/2026 | Đã đọc văn bản; việc áp Điều 63 cho thom house là suy luận |
| Hẹn hỏi thăm | Tin hỏi thăm sau dịch vụ cần đồng ý riêng và không kèm ưu đãi | Khoản 1 Điều 3 Nghị định 91/2020; khoản 4 Điều 9 Luật 91/2025 | Suy luận |
| Báo giá | Chỉ báo giá lấy từ bảng giá có ngày cập nhật; phải nêu đủ thời lượng, phí phát sinh, điều kiện hủy | Khoản 1 Điều 37, khoản 3 Điều 21 Luật 19/2023 | Đã đọc văn bản |
| Báo giá | Phải nói tên, địa chỉ, số đăng ký kinh doanh của thom house khi khách hỏi hoặc trong phần giới thiệu OA | Điểm a và b khoản 1 Điều 37 Luật 19/2023 | Đã đọc văn bản |
| Khách là trẻ em | Nếu khách cho biết mình dưới tuổi thành niên, chatbot dừng tư vấn sức khỏe và chuyển sang nhân viên | Khoản 2 Điều 24 Luật 91/2025 | Suy luận về cách làm; điều luật đã đọc |
| Sự cố dữ liệu | Khi lộ dữ liệu, thom house báo cơ quan chuyên trách trong 72 giờ | Khoản 1 Điều 23 Luật 91/2025; Điều 28 Nghị định 356/2025 | Đã đọc văn bản |

## Những điểm luật sư cần xác nhận

1. thom house đang đăng ký là hộ kinh doanh, doanh nghiệp siêu nhỏ hay doanh nghiệp nhỏ? Tài liệu tôi đọc không ghi loại hình. Câu trả lời đổi mức phạt và cách áp miễn trừ.
2. Việc chatbot nhận thông tin sức khỏe khách tự kể có làm thom house thành bên "trực tiếp xử lý dữ liệu cá nhân nhạy cảm" theo khoản 2 Điều 41 Nghị định 356/2025 không?
3. Việc gửi tin nhắn sang Anthropic có thuộc trường hợp nào được miễn hồ sơ chuyển dữ liệu ra nước ngoài không? Tôi không thấy trường hợp nào khớp.
4. Điều khoản và thỏa thuận xử lý dữ liệu của Anthropic có đáp ứng khoản 2 Điều 12 Nghị định 356/2025 không? Anthropic là bên xử lý hay bên thứ ba?
5. Chatbot thuộc nhóm rủi ro trung bình hay thấp theo Luật Trí tuệ nhân tạo khi đã công khai là trí tuệ nhân tạo?
6. Nghị định 91/2020 có áp dụng cho tin nhắn Zalo OA và ZNS không, và nghị định thay thế đã ban hành chưa?
7. Các tên dịch vụ *Diện chẩn ngừa đột quỵ*, *Tiêu u – Thông kinh ngực* và mô tả liên quan có bị coi là quảng cáo dịch vụ khám bệnh, chữa bệnh không? Nên đổi tên ra sao?
8. Ranh giới pháp lý giữa xoa bóp, bấm huyệt, diện chẩn để chăm sóc và để trị liệu; điều kiện an ninh trật tự cho cơ sở xoa bóp.
9. Nghị định 81/2018 và 128/2024 về khuyến mại còn nguyên hiệu lực năm 2026 không, và Luật Thương mại điện tử 122/2025 có thêm nghĩa vụ nào cho bán hàng qua chat không?

## Những việc anh cần quyết

Việc thứ nhất là giữ hay bỏ các câu về bệnh trong kho kiến thức của chatbot. Nếu giữ nguyên, chatbot có thể lặp lại "ngừa đột quỵ" hay "giảm u hạch, tuyến giáp" với khách, và thom house chịu rủi ro bị phạt theo Điều 75 Nghị định 87/2026. Nếu bỏ hoặc đổi tên, chatbot an toàn hơn, nhưng phải sửa menu, tài liệu và có thể ảnh hưởng tới cách khách nhận ra dịch vụ quen. Tôi đề xuất chatbot không nhắc tên bệnh trong bất kỳ câu trả lời nào, kể cả khi đọc nguyên văn menu; việc đổi tên menu thì chờ luật sư.

Việc thứ hai là có chặn tin đầu tiên bằng màn hình đồng ý hay không. Nếu chặn, mọi tin gửi sang Anthropic đều có đồng ý trước; điểm yếu là thêm một bước và một số khách bỏ đi. Nếu không chặn, trải nghiệm mượt hơn, nhưng tin đầu tiên của khách (có thể chứa thông tin sức khỏe) đã sang Mỹ trước khi khách đồng ý, trái khoản 1 Điều 11 Luật 91/2025. Tôi đề xuất chặn.

Việc thứ ba là lập hồ sơ đánh giá tác động xử lý và chỉ định người phụ trách bảo vệ dữ liệu ngay, hay chờ luật sư trả lời câu hỏi về miễn trừ. Tôi đề xuất làm ngay. Hồ sơ chuyển dữ liệu ra nước ngoài thì bắt buộc dù thế nào, và hai hồ sơ có phần lớn nội dung giống nhau. Điểm yếu là tốn công và có thể phải thuê dịch vụ bảo vệ dữ liệu.

Việc thứ tư là có áp quy tắc chống tin nhắn rác cho tin Zalo không. Tôi đề xuất áp, vì chi phí thấp và dự thảo mới đã nhắm tới ứng dụng như Zalo. Điểm yếu là ít tin khuyến mãi được gửi đi hơn.

Việc thứ năm là khai báo chatbot với Bộ Khoa học và Công nghệ theo nhóm rủi ro trung bình hay coi là rủi ro thấp. Tôi đề xuất khai báo nhóm trung bình. Khai báo làm trên cổng điện tử và được cấp mã ngay. Điểm yếu là thom house có thêm một hồ sơ phải cập nhật khi đổi chức năng.

Việc thứ sáu là thời hạn lưu cho nội dung chat, ghi chú sức khỏe và bằng chứng đồng ý. Luật chỉ yêu cầu "phù hợp với mục đích". Tôi đề xuất anh chọn con số ngắn nhất mà việc chăm sóc khách vẫn chạy được, và ghi con số đó vào thông báo cho khách.

## Nguồn đã dùng

Tất cả truy cập ngày 2026-11-07.

- Luật 91/2025/QH15 (Bảo vệ dữ liệu cá nhân): https://luatvietnam.vn/dan-su/luat-bao-ve-du-lieu-ca-nhan-2025-so-91-2025-qh15-405135-d1.html
- Nghị định 356/2025/NĐ-CP: https://luatvietnam.vn/dan-su/nghi-dinh-356-2025-nd-cp-quy-dinh-chi-tiet-luat-bao-ve-du-lieu-ca-nhan-422896-d1.html
- Nghị định 330/2026/NĐ-CP: https://luatvietnam.vn/vi-pham-hanh-chinh/nghi-dinh-330-2026-nd-cp-xu-phat-vi-pham-hanh-chinh-trong-an-ninh-mang-va-bao-ve-du-lieu-445214-d1.html
- Nghị định 392/2026/NĐ-CP: https://luatvietnam.vn/dau-tu/nghi-dinh-392-2026-nd-cp-sua-doi-thu-tuc-hanh-chinh-dieu-kien-dau-tu-kinh-doanh-an-ninh-trat-tu-451905-d1.html
- Nghị định 91/2020/NĐ-CP (bản PDF): https://www.qtsc.com.vn/uploads/files/2020/09/07/91_2020_ND-CP.pdf
- Dự thảo nghị định thay thế Nghị định 91/2020 (Bộ Công an, tháng 9/2026): https://bocongan.gov.vn/media/bca-media/library-20260909084715-f7e1171f-eb0c-4ae2-97ed-7017b136dc65-1-nghi-inh-thay-the-n-91.doc
- Luật 134/2025/QH15 (Trí tuệ nhân tạo): https://static3.luatvietnam.vn/uploaded/others/2025/12/25/luat-134-2025-qh15_2512152052.docx
- Nghị định 142/2026/NĐ-CP: https://hethongphapluat.com/nghi-dinh-142-2026-nd-cp-huong-dan-luat-tri-tue-nhan-tao.html
- Bài báo về Quyết định 33/2026/QĐ-TTg (nguồn thứ cấp): https://www.vietnamplus.vn/ban-hanh-danh-muc-he-thong-tri-tue-nhan-tao-co-rui-ro-cao-post1121909.vnp
- Luật 75/2025/QH15 (Quảng cáo sửa đổi): https://luatvietnam.vn/thuong-mai/luat-quang-cao-sua-doi-2025-so-75-2025-qh15-404208-d1.html
- Nghị định 342/2025/NĐ-CP: https://luatvietnam.vn/van-hoa/nghi-dinh-342-2025-nd-cp-quy-dinh-chi-tiet-luat-quang-cao-co-hieu-luc-2026-422938-d1.html
- Nghị định 87/2026/NĐ-CP: https://luatvietnam.vn/vi-pham-hanh-chinh/nghi-dinh-87-2026-nd-cp-xu-phat-vi-pham-hanh-chinh-trong-van-hoa-va-quang-cao-431418-d1.html
- Luật 15/2023/QH15 (Khám bệnh, chữa bệnh): https://luatvietnam.vn/y-te/luat-15-2023-qh15-242305-d1.html
- Điều 39 Nghị định 96/2023/NĐ-CP: https://hethongphapluat.com/nghi-dinh-96-2023-nd-cp-huong-dan-luat-kham-benh-chua-benh/dieu-39
- Luật 19/2023/QH15 (Bảo vệ quyền lợi người tiêu dùng): https://luatvietnam.vn/thuong-mai/luat-bao-ve-quyen-loi-nguoi-tieu-dung-2023-so-19-2023-qh15-259732-d1.html
- Bài viết về trần giảm giá 50% theo Nghị định 128/2024 (nguồn thứ cấp): https://tapchicongthuong.vn/sua-quy-dinh-han-muc-toi-da-ve-gia-tri-hang-hoa--dich-vu-dung-de-khuyen-mai-128043.htm

Các trang không tải được: vbpl.moj.gov.vn (không phân giải tên miền), thuvienphapluat.vn (lỗi 403), hoatieu.vn (trang chặn truy cập tự động).

## Nói ngắn gọn nhất

Chatbot của thom house sẽ nhận thông tin sức khỏe của khách và gửi sang Mỹ, nên luật coi việc này là xử lý dữ liệu nhạy cảm và chuyển dữ liệu ra nước ngoài. thom house cần xin khách đồng ý từng mục đích trước khi gửi tin sang Anthropic, nộp hồ sơ cho Bộ Công an trong 60 ngày, nói rõ khách đang trò chuyện với trí tuệ nhân tạo, và chỉ gửi khuyến mãi cho người đã đăng ký. Rủi ro lớn nhất không nằm ở kỹ thuật mà ở câu chữ: thom house không có giấy phép chữa bệnh, nên chatbot không được lặp lại những câu như "ngừa đột quỵ" hay "giảm u hạch, tuyến giáp", dù các câu đó đang có trong menu.

# Hai bot trong phòng chat, công tắc tự động trả lời và hồ sơ khách

Tài liệu này viết cho anh và cho lễ tân. Trong tài liệu, lễ tân là người dùng console để duyệt tin trả lời khách. Phần kỹ thuật cho người lập trình nằm ở mục 14 và mục 15 của `docs/contracts.md`; cách bật, tắt và chạy lệnh nằm ở `docs/run-local.md`.

## Phần anh cần đọc trước

Đây là phần anh cần duyệt. Các phần sau giải thích chi tiết.

Từ ngày 12/11/2026, chatbot có thêm một cách soạn câu trả lời: hai bot cùng làm việc trong một phòng chat nội bộ trên máy Mac. Bot dịch vụ biết dịch vụ, giá và quy tắc trả lời của studio. Bot khách hàng biết những gì studio đã ghi về từng khách. Cách soạn này mặc định tắt. Khi chưa bật, runner (chương trình trên máy Mac gọi Claude để soạn bản nháp) vẫn soạn mỗi bản nháp bằng một lần gọi `claude -p` như trước.

Cùng ngày, hệ thống có thêm bốn thứ dùng được ngay, kể cả khi chưa bật hai bot:

- Công tắc Tự động trả lời cho từng hội thoại trên console. Mặc định, công tắc tắt ở mọi hội thoại cho tới khi lễ tân bật; khi đó, với chế độ trả lời chung mặc định, mọi câu trả lời vẫn chờ lễ tân duyệt.
- Ba nhãn Zalo Khách hàng, Quản lý và Nhân viên, để báo cho hệ thống ai là khách và ai làm ở studio.
- Khối Tóm tắt khách hàng trên console. Khối này tính trạng thái của khách từ các lần khách đến studio.
- Script `scripts/analyze_visits.py` đọc tin nhắn Zalo cũ và đoán các lần khách đến, số tiền khách đã trả, kỹ thuật viên, số điện thoại và gói nhiều buổi của khách. Console hiện các kết quả này trong mục Suy ra từ tin nhắn cũ, và lễ tân xác nhận hoặc bỏ từng kết quả.

Chiều 12/11, hệ thống đã được chạy thử trên máy Mac này với một khách giả và một bản giả của zalo-agent, công cụ dòng lệnh mà hệ thống dùng để gửi và nhận tin Zalo cá nhân; vì vậy không tin nào đi qua Zalo thật. Trong lượt chạy thử, hai bot soạn được câu trả lời trong phòng, công tắc Tự động trả lời gửi được câu trả lời của bot khi bật, nhãn Nhân viên làm bot im lặng với người mang nhãn, và khối Tóm tắt khách hàng đếm cả buổi làm do lễ tân ghi lẫn lần đến suy ra từ tin nhắn. Lượt chạy thử cũng tìm ra một lỗi làm hai bot không dùng được bộ quy tắc trả lời; lỗi này đã được sửa trong code của runner nhưng bản sửa chưa chạy lại với OpenMausBot thật (mục "Điểm yếu đã biết"). Lượt chạy thử chưa gửi tin nào qua tài khoản Zalo thật và chưa mở console trên trình duyệt.

Trạng thái và hồ sơ của khách chỉ có số liệu khi hệ thống biết khách đã đến. Hệ thống biết điều đó từ ba nguồn: buổi làm lễ tân ghi trên console, lịch sử anh nhập từ file, và lần đến mà `scripts/analyze_visits.py` suy ra từ tin nhắn cũ ở mức chắc hoặc khá chắc. Khách không có lần đến nào từ ba nguồn này hiện là "mới hỏi, chưa đến lần nào", và Bot khách hàng không có gì để kể về khách đó.

Có hai việc anh cần quyết trước khi bật hai bot:

1. Phòng của mỗi khách giữ bản chép tin nhắn của khách. Lệnh xóa dữ liệu của runner chưa xóa phòng, và phòng cũ không tự mất. Anh cần chọn người xóa phòng khi một khách yêu cầu xóa dữ liệu.
2. Bot khách hàng nói mức chi tiêu của khách bằng lời, theo hai ngưỡng do người viết code tự chọn: trung bình dưới 300.000đ một lần đến là thấp, trên 700.000đ là cao. Anh duyệt hai ngưỡng này hoặc đưa ngưỡng khác.

Trên OpenMausBot từng có hai bot tên Bot dịch vụ và Bot khách hàng trong nhóm "thom house thu". Hai bot đó là bot thử với dữ liệu giả do người viết code tạo trong lúc làm. Lần cài đặt thật đầu tiên đã nhận lại hai tên bot đó cho hệ thống, nên anh không cần quyết gì về hai bot này.

## Hai bot là ai, và mỗi bot biết gì?

Hai bot làm việc trên OpenMausBot. OpenMausBot là một chương trình chạy trên máy Mac, cho nhiều bot cùng làm việc trong các phòng chat. Hệ thống dùng OpenMausBot để mỗi hội thoại Zalo cá nhân của một khách có một phòng riêng, tên là `zalo-` cộng mã hội thoại. Khách không thấy phòng. OpenMausBot chỉ mở trên máy Mac, ở địa chỉ `127.0.0.1:8799`, và không nối với Zalo.

Bot dịch vụ là bot chính và là bot viết câu trả lời cuối cùng. Bot này nhận đúng bộ quy tắc trả lời mà `claude -p` đang dùng: giọng văn, bảy mẫu trả lời, danh mục dịch vụ và các thông tin đã duyệt của studio. Bot dịch vụ dùng tám công cụ như trước: tra dịch vụ, xem chi tiết dịch vụ, báo giá, xem khuyến mãi, ghi yêu cầu đặt lịch, chuyển hội thoại cho lễ tân, ghi lựa chọn nhận tin của khách và đính kèm ảnh menu. Bot dịch vụ được dặn không nói với khách số tiền khách đã chi hay mức chi tiêu của khách.

Bot khách hàng chỉ có một công cụ: đọc hồ sơ của khách đang nhắn. Hồ sơ gồm cách gọi khách, trạng thái khách, lần đến gần nhất (ngày, dịch vụ, kỹ thuật viên), nhịp quay lại, dịch vụ hay dùng, số tiền khách đã chi và các quyền lợi chưa dùng. Với khách có kết quả suy ra từ tin nhắn cũ, hồ sơ còn ghi bao nhiêu lần đến là suy ra từ tin nhắn, lịch hẹn sắp tới suy ra từ tin nhắn, và số buổi còn lại của gói suy ra từ tin nhắn (không có tên gói). Bot khách hàng tóm tắt hồ sơ cho Bot dịch vụ trong tối đa 9 dòng. Bot này nói mức chi tiêu bằng một trong ba chữ thấp, vừa, cao, theo số tiền trung bình mỗi lần đến trong 183 ngày gần nhất, và không ghi con số.

Có những thứ cả hai bot đều không thấy:

- Số điện thoại của khách, kể cả số điện thoại suy ra từ tin nhắn cũ. Bot chỉ biết khách đã để lại số hay chưa.
- Tên dịch vụ thuộc nhóm sức khỏe và nhóm chăm sóc phụ nữ, và tên dịch vụ ngoài danh mục của studio. Hồ sơ chỉ đếm số dịch vụ loại này.
- Tên gói hoặc voucher có nhắc dịch vụ thuộc hai nhóm trên, hoặc có các từ như diện chẩn, ấn huyệt, giác hơi, hơ ngải, vùng kín. Hồ sơ thay tên đó bằng "Gói dịch vụ" hoặc "Voucher".
- Tên kỹ thuật viên suy ra từ tin nhắn cũ mà có từ ba chữ số liền nhau trở lên, vì chuỗi số như vậy có thể là số điện thoại hay số tài khoản.
- Hội thoại của khách chưa đồng ý trò chuyện với trợ lý AI, của khách được đánh dấu dưới 18 tuổi, và của người có nhãn Quản lý hoặc Nhân viên. Các hội thoại này không có phòng.

Phòng chỉ nhận tin khách nhắn sau khi đồng ý và tin mà bot, lễ tân hoặc hệ thống đã gửi tới khách, trong 14 ngày gần nhất. Một phòng mới nhận 20 tin gần nhất của hội thoại để bot có bối cảnh.

Số tiền trong hồ sơ chỉ để bot chọn cách tư vấn. Bước kiểm tra trước khi gửi là bước server tự kiểm từng bản nháp, đã có từ trước. Nếu bot vẫn viết cho khách một số tiền không trùng giá nào mà công cụ đã trả về trong hội thoại, bước này đánh lỗi câu trả lời, và câu trả lời phải chờ lễ tân duyệt.

## Một lượt trả lời trong phòng diễn ra thế nào?

Một lượt trả lời đi qua sáu bước:

1. Khách nhắn. Server chờ 10 giây sau tin cuối của khách, rồi giao việc soạn nháp cho runner như trước.
2. Runner tạo một mã dùng một lần cho mỗi lượt trả lời, đưa tin mới của khách vào phòng và gọi Bot dịch vụ. Tin đưa vào phòng có thêm một dòng cho Bot dịch vụ biết bot đã từng gửi tin tới khách này hay chưa; nếu đã gửi, Bot dịch vụ được dặn không tự giới thiệu lại là trợ lý AI.
3. Bot dịch vụ hỏi Bot khách hàng về khách. Bot khách hàng đọc hồ sơ bằng mã của lượt đó rồi trả lời.
4. Bot dịch vụ tra dịch vụ và giá bằng công cụ, cũng kèm mã của lượt đó, rồi viết đúng một câu trả lời.
5. Runner kiểm câu trả lời. Câu trả lời phải do Bot dịch vụ viết, không chứa mã và không chứa tên bot. Bot khách hàng cũng phải đã đọc hồ sơ trong lượt đó. Nếu đạt, runner gửi câu trả lời về server như một bản nháp bình thường.
6. Server làm như trước: chạy bước kiểm tra trước khi gửi, rồi chờ lễ tân duyệt, hoặc tự gửi khi công tắc Tự động trả lời của hội thoại đang bật.

Mã dùng một lần cho mỗi lượt trả lời có dạng `tk_` và 32 ký tự. Runner gắn mã với đúng việc soạn nháp đang chạy. Mỗi khi một bot gọi công cụ, chương trình cấp công cụ kiểm mã trước. Nếu mã sai, đã hết hạn hoặc bị thiếu, công cụ từ chối và không gọi server. Mã hết hạn sau 240 giây (thời gian tối đa của một lượt) cộng 60 giây, và runner xóa mã khi lượt kết thúc. Nhờ vậy, bot chỉ đọc và ghi được dữ liệu của đúng khách đang được trả lời, kể cả khi một tin nhắn của khách cố dụ bot làm việc khác.

Khi một bước lỗi, ví dụ OpenMausBot không chạy, lượt kéo dài quá 240 giây hoặc câu trả lời bị runner loại, runner soạn lại bằng `claude -p` như cách cũ (đây là cài đặt mặc định, biến `ROOM_FALLBACK`). Lễ tân vẫn nhận bản nháp như thường, chỉ chậm hơn. Một lượt trong phòng gọi Claude ít nhất ba lần, nên chậm hơn và tốn hạn mức gói Claude hơn cách cũ. Chưa ai đo chậm hơn bao nhiêu.

## Bật và tắt hai bot thế nào?

Hai bot chỉ chạy khi đủ cả hai điều kiện:

1. File `apps/runner/.env` có dòng `THOMHOUSE_DRAFT_ENGINE=rooms`, và runner đã được khởi động lại bằng `scripts/stop_local.sh` rồi `scripts/start_local.sh`.
2. Trên console, ở tab Cài đặt, mục Phòng hai bot (`rooms_enabled`) đang là `true`.

Ngoài ra, máy phải có OpenMausBot trong thư mục `tools/openmausbot` của dự án và có Node.js 24 trở lên. Khi đủ hai thứ này, `scripts/start_local.sh` tự bật OpenMausBot.

Muốn tắt hai bot, anh làm một trong hai cách. Cách nhanh là chọn `false` ở mục Phòng hai bot trên console; runner soạn bằng `claude -p` từ lượt tiếp theo, không cần khởi động lại. Cách thứ hai là đổi dòng trong `apps/runner/.env` thành `THOMHOUSE_DRAFT_ENGINE=claude` rồi khởi động lại. Các lệnh, địa chỉ của OpenMausBot, thư mục dữ liệu và file log nằm ở `docs/run-local.md`.

## Công tắc Tự động trả lời làm gì?

Lễ tân thấy công tắc Tự động trả lời ở trang chi tiết của mỗi hội thoại. Công tắc dùng được với cả hai cách soạn, có phòng hay không có phòng.

Khi công tắc hiện Tắt, bot không tự gửi tin nào trong hội thoại đó. Bot vẫn soạn bản nháp, và mỗi bản nháp chờ lễ tân duyệt, sửa hoặc tự trả lời. Với chế độ trả lời chung mặc định là Duyệt từng tin, đây là trạng thái của mọi hội thoại cho tới khi lễ tân bật. Khi lễ tân tắt công tắc, chế độ riêng của hội thoại (Tắt bot, Chỉ soạn nháp, Duyệt từng tin) vẫn áp dụng; chế độ Cho bot tự gửi thì bị hạ xuống Duyệt từng tin.

Khi công tắc hiện Bật, câu trả lời của bot tới khách ngay, không ai đọc trước, với điều kiện câu trả lời không rơi vào các trường hợp ở dưới. Console hỏi xác nhận trước khi bật. Bật công tắc cũng bỏ chế độ riêng của hội thoại.

Dù công tắc đang bật, câu trả lời vẫn chờ lễ tân duyệt trong năm trường hợp:

- Bản nháp có ảnh menu.
- Bước kiểm tra trước khi gửi báo lỗi. Ví dụ: giá không lấy từ công cụ báo giá, số tiền viết kiểu "450k", câu có từ bị cấm, thông tin liên hệ chưa được duyệt, hoặc câu hứa giữ lịch.
- Trong lượt đó, bot chuyển hội thoại cho lễ tân, hoặc khách từ chối trò chuyện với trợ lý AI.
- Hội thoại không còn ở trạng thái bot đang trả lời, ví dụ lễ tân vừa tiếp quản.
- Tin gần nhất của khách đã cũ hơn 7 ngày.

Có ba trường hợp khác mà bot không gửi gì:

- Khách nhắn thêm trong lúc bot đang soạn. Server bỏ bản nháp cũ và cho bot soạn bản mới có cả tin mới.
- Mục Gửi tin qua Zalo (`outbound_enabled`) ở tab Cài đặt đang là `false`. Khi đó không tin nào được gửi.
- Chế độ trả lời chung (`auto_reply_mode`) đang là Tắt bot. Khi đó công tắc không có tác dụng; console khóa công tắc và ghi lý do.

Một câu trả lời được tự gửi vẫn đi qua hàng chờ gửi của tài khoản Zalo cá nhân như mọi tin khác. Hàng chờ gửi tối đa 30 tin mỗi giờ, hai tin cho cùng một người cách nhau ít nhất 5 giây, và tin tự động nằm trong hàng chờ quá 30 phút thì không được gửi nữa.

Ba điều nữa lễ tân cần biết:

- Khi lễ tân chọn Tắt bot, Chỉ soạn nháp hoặc Duyệt từng tin cho một hội thoại đang bật công tắc, công tắc tự tắt.
- Server không cho bật công tắc cho người có vai trò quản lý hoặc nhân viên, dù vai trò đến từ nhãn Zalo hay do lễ tân đặt. Console khóa công tắc và ghi lý do.
- Ở danh sách hội thoại, nhãn "tự động trả lời" hiện ở mọi hội thoại mà bot được phép tự gửi, kể cả khi lý do là chế độ trả lời chung đang là Cho bot tự gửi.

## Gắn nhãn Zalo thế nào, và mỗi nhãn đổi điều gì?

Trong app Zalo trên điện thoại của tài khoản studio, anh tạo ba nhãn tên là Khách hàng, Quản lý và Nhân viên, rồi gắn nhãn cho cuộc trò chuyện riêng của từng người. Hệ thống so cả tên nhãn sau khi bỏ dấu và bỏ chữ hoa, nên nhãn "khach hang" cũng được tính. Một nhãn có thêm chữ, ví dụ "Khách hàng VIP", thì không được tính. Nhãn gắn cho nhóm chat bị bỏ qua.

Bridge, tức chương trình gửi tin qua Zalo cá nhân, đọc nhãn mỗi khi bật và sau đó cứ 15 phút một lần, rồi gửi danh sách vai trò lên server. Lễ tân không cần làm gì thêm. Muốn cập nhật ngay, anh chạy lệnh `python3 -m bridge.main sync-labels` trong thư mục `apps/zalo-bridge`. Lệnh chỉ in số đếm, không in tên hay mã của ai.

Nhãn Khách hàng làm hệ thống coi người đó là khách, kể cả khi hồ sơ liên hệ đoán là người nhà, bạn bè hay nhân viên. Hồ sơ liên hệ là kết quả của script đọc tin nhắn cũ `scripts/analyze_contacts.py`. Với người có nhãn Khách hàng, quy tắc bot im lặng với người nhà và bạn bè không áp dụng nữa. Người đó vẫn phải đồng ý trò chuyện với trợ lý AI như mọi khách.

Người có nhãn Quản lý hoặc Nhân viên được gọi chung là người của studio. Khi người của studio nhắn tới, server chỉ lưu tin và không làm gì thêm:

- Không gửi tin xin đồng ý và không gửi tin cố định nào.
- Không soạn bản nháp, không tự gửi, không tạo yêu cầu chuyển lễ tân và không đánh dấu hội thoại cần chú ý.
- Không gửi tin cảm ơn hay tin hỏi thăm sau buổi làm.
- Không đưa hội thoại vào phòng của hai bot.
- Hủy các tin tự động còn nằm trong hàng chờ gửi, như câu trả lời của bot, tin xin đồng ý và tin hẹn giờ.
- Xóa các kết quả suy ra từ tin nhắn cũ mà lễ tân chưa xác nhận hay bỏ, và xóa số điện thoại gợi ý của người đó.

Lễ tân và anh vẫn tự nhắn được cho người của studio, từ console hoặc từ điện thoại. Khi bỏ nhãn, lần đồng bộ sau xóa vai trò (trừ vai trò do lễ tân đặt trên console), và tin tiếp theo của người đó được xử lý như bình thường. Người không có nhãn nào được xử lý như trước ngày 12/11. Một người mang nhiều nhãn được tính theo nhãn đứng trước trong thứ tự Quản lý, Nhân viên, Khách hàng.

Trên console, dòng Vai trò ở trang chi tiết hội thoại cho biết vai trò và nguồn của vai trò: nhãn Zalo, lễ tân đặt, hoặc suy từ hồ sơ. Lễ tân chọn vai trò ở ô Lễ tân đặt khi cần sửa nhanh. Vai trò lễ tân đặt thắng nhãn Zalo; nếu muốn hệ thống theo nhãn Zalo trở lại, lễ tân chọn Không đặt. Vai trò có nguồn suy từ hồ sơ không làm server chặn bot như nhãn Quản lý hay Nhân viên; với người đó, các quy tắc của hồ sơ liên hệ vẫn áp dụng như trước.

## Mỗi trạng thái khách nghĩa là gì?

Khối Tóm tắt khách hàng ghi một trong bốn trạng thái:

| Trạng thái trên console | Khi nào |
|---|---|
| mới hỏi, chưa đến lần nào | Hệ thống chưa biết lần đến nào của khách |
| đã đến lần đầu | Khách có đúng một ngày đến, và chưa quá mốc lâu chưa quay lại |
| khách quay lại | Khách có từ hai ngày đến trở lên, và chưa quá mốc lâu chưa quay lại |
| lâu chưa quay lại | Số ngày từ lần đến gần nhất tới hôm nay lớn hơn mốc lâu chưa quay lại |

Server tính trạng thái theo bốn quy tắc. Mọi ngày đều tính theo giờ Việt Nam.

1. Một ngày đến là một ngày có ít nhất một buổi làm được ghi, hoặc một lần đến suy ra từ tin nhắn ở mức chắc hoặc khá chắc. Khách làm ba dịch vụ trong một ngày vẫn tính là một lần đến.
2. Nhịp quay lại là số ngày khách thường để giữa hai lần đến. Server lấy khoảng cách giữa từng cặp ngày đến liền nhau, xếp từ nhỏ tới lớn rồi lấy số ở giữa (khi số khoảng cách là số chẵn, server lấy trung bình của hai số ở giữa).
3. Khách mới đến một lần thì chưa có nhịp riêng. Khi đó server xét những khách khác từng dùng cùng dịch vụ và đã đến từ hai lần trở lên. Nếu có ít nhất ba khách như vậy, server lấy số ở giữa trong nhịp quay lại của họ. Nếu không đủ ba khách, server dùng 45 ngày.
4. Mốc lâu chưa quay lại bằng hai lần nhịp quay lại, làm tròn tới số ngày gần nhất. Mốc không nhỏ hơn 14 ngày. Vì mốc theo nhịp riêng của từng khách, khách tháng nào cũng đến bị coi là lâu chưa quay lại sau khoảng hai tháng, còn khách tuần nào cũng đến thì sau khoảng hai tuần.

Ví dụ. Chị Lan có năm buổi làm được ghi: 01/08, 22/08 (hai dịch vụ trong ngày), 19/09 và 10/10/2026. Chị có bốn ngày đến. Khoảng cách giữa các ngày đến là 21, 28 và 21 ngày. Xếp lại thành 21, 21, 28 thì số ở giữa là 21, nên nhịp quay lại của chị là 21 ngày. Mốc lâu chưa quay lại là 2 nhân 21, bằng 42 ngày. Hôm nay, 12/11, đã 33 ngày từ lần đến 10/10. Vì 33 không lớn hơn 42, chị Lan là khách quay lại. Nếu tới 21/11 chị chưa đến, số ngày là 42, chị vẫn là khách quay lại. Từ 22/11, số ngày là 43, lớn hơn 42, nên chị chuyển sang lâu chưa quay lại. Ngày 12/11, tôi chạy đúng ví dụ này qua hàm tính trạng thái của server (`computeCustomerStatus`), và ba ngày 12/11, 21/11, 22/11 cho ra đúng ba kết quả vừa nêu.

Trong ví dụ đó, buổi 19/09 chưa ghi số tiền, ba buổi còn lại ghi tổng 1.549.000đ. Server chỉ chia cho các ngày đến có ghi số tiền, nên trung bình mỗi lần đến là 516.333đ, và Bot khách hàng nói mức chi là "vừa". Buổi chưa ghi số tiền không bị tính là 0đ.

Các con số 2 lần, 14 ngày, 45 ngày và 183 ngày đổi được bằng bốn biến `CUSTOMER_ABSENT_FACTOR_PCT` (200, nghĩa là 2 lần), `CUSTOMER_MIN_ABSENT_DAYS`, `CUSTOMER_DEFAULT_GAP_DAYS` và `CUSTOMER_WINDOW_DAYS`. Anh ghi các biến này vào `apps/server/.dev.vars` rồi khởi động lại server.

## Buổi làm, số tiền, kỹ thuật viên và quyền lợi vào hệ thống bằng cách nào?

Hệ thống biết lần đến của khách từ ba nguồn: buổi làm lễ tân ghi trên console, lịch sử anh nhập từ file, và kết quả `scripts/analyze_visits.py` suy ra từ tin nhắn cũ. Mục này nói về hai nguồn đầu; mục sau nói về nguồn thứ ba. Yêu cầu đặt lịch của bot không tự thành buổi làm. Khi cả ba nguồn đều chưa có gì về một khách, khách đó là "mới hỏi, chưa đến lần nào", và khối Tóm tắt khách hàng ghi rõ là chưa có buổi làm nào được ghi.

Trên console, khối Tóm tắt khách hàng có ba nút:

- Ghi buổi làm cho khách này: lễ tân chọn dịch vụ trong danh mục, giờ làm, số tiền, kỹ thuật viên và thời lượng. Nếu buổi đó dùng gói hoặc voucher, lễ tân chọn thêm quyền lợi. Khi chọn quyền lợi, server trừ một lượt của quyền lợi đó cùng lúc với việc ghi buổi làm. Ô dịch vụ chỉ nhận mã dịch vụ có trong danh mục của studio.
- Thêm hoặc dùng quyền lợi: lễ tân thêm gói nhiều buổi hoặc voucher (tên, số lần, số lần đã dùng, hạn dùng). Nút Dùng 1 lần trừ một lượt khi khách dùng quyền lợi mà không ghi buổi làm. Nút Hủy quyền lợi và Khôi phục quyền lợi đổi trạng thái của quyền lợi. Một quyền lợi dùng được tới hết ngày hết hạn.
- Xem các buổi làm đã ghi: danh sách tối đa 200 buổi gần nhất.

Khối Tóm tắt khách hàng cũng có ô số điện thoại để lễ tân sửa hoặc xóa. Tab Ghi nhận buổi làm có sẵn từ trước cũng có thêm các ô số tiền, kỹ thuật viên, thời lượng và quyền lợi.

Mỗi buổi làm ghi trên console tạo tin cảm ơn và tin hỏi thăm như trước. Các tin này chỉ được gửi khi mục Tin hẹn giờ sau buổi làm (`scheduled_sends_enabled`) là `true` và khách đã đồng ý nhận tin chăm sóc sau buổi làm. Khi lễ tân ghi một buổi làm đã qua lâu, ví dụ hôm nay mới ghi buổi làm cách đây ba tuần, server vẫn tạo hai tin đó nhưng không gửi trễ: tin nào đã quá giờ gửi dự kiến hơn 6 giờ thì chuyển sang hết hạn, và server không gửi tin đó nữa. Lượt chạy thử ngày 12/11 tạo đúng trường hợp này cho một buổi làm cách 23 ngày; sau đó một test tự động khóa lại quy tắc 6 giờ.

Lịch sử cũ thì anh nhập từ một file CSV, ví dụ file xuất từ Google Sheets hoặc từ phần mềm bán hàng. Anh chạy lệnh ở thư mục dự án:

```bash
python3 -I scripts/import_visits.py lich-su.csv            # chạy thử: chỉ in số đếm và các dòng không nhập được
python3 -I scripts/import_visits.py lich-su.csv --apply    # chạy thử, rồi ghi thật
```

Script đọc tên cột tiếng Việt hoặc tiếng Anh, không phân biệt dấu và chữ hoa. Mỗi dòng cần một cột để tìm khách (mã khách `cus_`, Zalo ID hoặc số điện thoại), một cột ngày và một cột dịch vụ; các cột giờ, số tiền, kỹ thuật viên, thời lượng và mã hóa đơn có thể có hoặc không. Ngày viết kiểu 09/10/2026; dòng không có giờ được ghi lúc 12:00. Số tiền viết 450000, 450.000 hoặc 450.000đ đều được, còn 450k thì bị từ chối. Dịch vụ có tên trùng tên trong danh mục được ghi theo dịch vụ đó; tên khác được giữ nguyên như trong file. Một Zalo ID mà server chưa biết tạo ra một khách mới chưa có tên, và lần chạy thử in số khách mới này để anh kiểm trước khi ghi.

Script luôn chạy thử trước và in số đếm cùng số dòng của các dòng không nhập được, không in tên, số điện thoại hay số tiền nào. Buổi làm nhập từ file không tạo tin cảm ơn hay tin hỏi thăm. Chạy lại cùng một file không ghi trùng, vì server bỏ qua buổi làm đã có. Script chỉ gửi tới server trên máy này và không đọc file Excel; anh xuất file sang CSV trước.

## Kết quả suy ra từ tin nhắn cũ hiện thế nào, và lễ tân làm gì với chúng?

Script `scripts/analyze_visits.py` đọc tin nhắn Zalo cũ mà zalo-agent lưu trên máy Mac và đoán, cho từng khách: các lần khách đến studio, ngày giờ và dịch vụ của mỗi lần, số tiền, kỹ thuật viên, số điện thoại và gói nhiều buổi hoặc voucher khách đang có. Mỗi kết quả chỉ là phỏng đoán. Server lưu các kết quả này riêng, không trộn với buổi làm và quyền lợi do lễ tân ghi. Trên console, các kết quả nằm trong mục Suy ra từ tin nhắn cũ của khối Tóm tắt khách hàng. Lệnh chạy script nằm ở `docs/chay-local-zalo-ca-nhan.md`.

Script bỏ qua cuộc trò chuyện của người mà script hồ sơ liên hệ đoán là người nhà, nhân viên hay bạn bè, và bỏ qua nhóm chat. Script đọc tin bằng các quy tắc chữ viết sẵn, chạy trên máy Mac và không gọi mạng. Script có thêm một lượt nhờ Claude đọc lại tin nhắn, nhưng lượt này mặc định tắt (biến `PROFILE_LLM_ENABLED`). Khi anh bật, script chỉ gửi những đoạn tin quanh các lần hẹn của khách đã đồng ý trò chuyện với trợ lý AI. Trước khi gửi, script che số điện thoại, tên Zalo của khách và đường link, và bỏ hẳn những tin nói về sức khỏe. Lượt đọc bằng Claude chưa được chạy với Claude thật lần nào.

### Mỗi lần đến suy ra từ tin nhắn chắc tới mức nào?

Console ghi mỗi lần đến suy ra từ tin nhắn ở một trong ba mức:

- Mức chắc: khách đặt lịch cho một ngày, và cùng ngày đó có tin cho thấy khách đã tới, ví dụ khách báo đang tới hay đã tới, studio cảm ơn khách đã ghé, hoặc khách chuyển khoản cho buổi làm. Một tin chuyển khoản đi cùng tin đã tới hoặc tin cảm ơn trong ngày cũng đủ mức chắc.
- Mức khá chắc: studio đã xác nhận lịch của một ngày đã qua và trong 72 giờ sau giờ hẹn khách còn nhắn một tin không phải câu hỏi địa chỉ, giờ mở cửa hay giá. Mức này cũng dùng khi chỉ có tin đã tới, tin cảm ơn hoặc tin chuyển khoản mà không có tin đặt lịch, hoặc khi khách nhắc lại một lần đến có ngày rõ, như "hôm qua chị làm gội đầu".
- Mức chưa chắc: khách xin lịch mà studio chưa xác nhận, hoặc studio xác nhận lịch mà sau giờ hẹn không còn tin nào.

Lịch đã hủy và lịch khách không đến không thành lần đến. Lịch hẹn của ngày sau hôm chạy script hiện ở nhóm Lịch hẹn sắp tới.

### Kết quả suy ra từ tin nhắn được tính vào số liệu thế nào?

Lần đến ở mức chắc và khá chắc được tính vào số lần đến, lần đến gần nhất, nhịp quay lại, trạng thái và số tiền của khách, như buổi làm do lễ tân ghi. Ngày đã có buổi làm do lễ tân ghi hoặc nhập từ file thì lần đến suy ra từ tin nhắn của ngày đó không được tính nữa. Lần đến ở mức chưa chắc và lịch hẹn sắp tới không được tính.

Số tiền chỉ được tính khi tin nhắn cho thấy khách đã trả: tin chuyển khoản, hóa đơn, hoặc tổng tiền studio báo sau buổi làm. Console ghi nguồn của mỗi số tiền là đã trả, báo giá hoặc giá niêm yết. Báo giá và giá niêm yết không được tính là tiền khách đã chi.

Mỗi con số trên khối Tóm tắt khách hàng có lần đến suy ra từ tin nhắn đều ghi kèm "gồm N lần suy ra từ tin nhắn". Lần đến gần nhất mà là phỏng đoán thì ghi "suy ra từ tin nhắn". Gói suy ra từ tin nhắn mà trùng tên với một quyền lợi lễ tân đã ghi thì không được đếm thêm lần nữa.

### Lễ tân xác nhận hoặc bỏ một kết quả thế nào?

Với mỗi lần đến suy ra từ tin nhắn, lễ tân bấm một trong hai nút:

- Xác nhận: console mở một form đã điền sẵn dịch vụ, ngày giờ và kỹ thuật viên. Số tiền chỉ được điền sẵn khi tin nhắn cho thấy khách đã trả; báo giá hay giá niêm yết chỉ hiện làm gợi ý, và lễ tân tự gõ số tiền nếu biết khách đã trả. Khi lưu, server ghi một buổi làm như lễ tân tự ghi, nhưng không tạo tin cảm ơn và tin hỏi thăm, vì buổi làm đó đã qua. Server không cho xác nhận một lần đến vào ngày đã có buổi làm được ghi, và console ẩn nút Xác nhận ở ngày đó.
- Bỏ: console hỏi lại một câu rồi đánh dấu kết quả là đã bỏ. Những lần chạy script sau không đưa kết quả đó trở lại. Khi lễ tân bỏ một lịch hẹn, ngày của lịch đó cũng không thành lần đến về sau.

Với gói hoặc voucher suy ra từ tin nhắn, nút Xác nhận tạo một quyền lợi như khi lễ tân thêm tay. Lễ tân nhập tổng số buổi khi tin nhắn không nói rõ. Khi tin nhắn có số buổi còn lại, form tính sẵn số buổi đã dùng. Server không cho xác nhận một gói khi khách đã có quyền lợi cùng tên.

Với số điện thoại, script làm theo hai mức. Khi khách tự gửi số kèm chữ như "sđt" hay "số chị", hoặc gửi một tin chỉ có số, script coi là số của khách; server tự ghi số đó vào hồ sơ nếu khách chưa có số và chưa khách nào khác có số đó. Các số còn lại chỉ thành số điện thoại gợi ý. Console che số gợi ý, chỉ hiện ba số cuối cho tới khi lễ tân bấm Hiện số. Nút Dùng số này ghi số vào hồ sơ khách. Sau khi lễ tân bấm nút Bỏ, script không gợi ý lại số đó cho khách này. Một số mà lễ tân đã xóa khỏi hồ sơ khách cũng không được script ghi lại. Khi khách đã có số điện thoại, console không hiện số gợi ý nào.

Các kết quả lễ tân đã xác nhận hoặc đã bỏ được gom vào dòng Đã xử lý, mặc định thu gọn.

## Phần nào chưa làm?

- Lệnh dành cho người có nhãn Nhân viên, như `/tour`, `/tip` và `/lich-off`, chưa có. Tin bắt đầu bằng dấu `/` của người có nhãn Nhân viên được lưu như mọi tin khác.
- Nhóm chat chưa được hỗ trợ. Server vẫn bỏ qua tin trong nhóm, nên chỉ hội thoại riêng một-một mới có phòng.
- Hai bot chưa ghi lại điều mới biết về khách vào hồ sơ. Hồ sơ chỉ đổi khi lễ tân sửa, khi có buổi làm mới, hoặc khi anh chạy lại các script phân tích tin nhắn cũ.
- Console chưa có màn hình liệt kê vai trò của mọi người. Vai trò hiện ở trang chi tiết của từng hội thoại.
- Chưa có lệnh xóa dữ liệu của một khách trên server. Khi lệnh đó được làm, lệnh phải xóa cả các kết quả suy ra từ tin nhắn của khách.

## Điểm yếu đã biết

- Lượt chạy thử chiều 12/11 tìm ra một lỗi làm hai bot không dùng được: Bot dịch vụ không đọc được bộ quy tắc trả lời. Bộ quy tắc dài khoảng 39 đến 43 KB, hơn giới hạn 24.000 byte mà OpenMausBot cho phần chỉ dẫn của một bot, nên runner đặt bộ quy tắc vào file `CLAUDE.md` trong thư mục làm việc của Bot dịch vụ. Nhưng OpenMausBot chạy lượt trả lời trong phòng ở một thư mục khác, nên Bot dịch vụ không thấy file đó, và mỗi lượt đều quay về soạn bằng `claude -p`. Khi chép tay file quy tắc sang thư mục OpenMausBot dùng, hai bot soạn được câu trả lời. Runner đã được sửa để tự ghi file quy tắc vào cả hai thư mục. Bản sửa mới chạy với OpenMausBot giả trong test; runner trên máy Mac chưa được khởi động lại để chạy bản sửa với OpenMausBot thật.
- Trong lượt chạy thử, Bot dịch vụ mở đầu mọi câu trả lời bằng câu tự giới thiệu là trợ lý AI của thom house, kể cả giữa cuộc trò chuyện. Runner giờ báo cho Bot dịch vụ biết bot đã từng gửi tin tới khách hay chưa. Chưa thử với Claude thật xem Bot dịch vụ có thôi tự giới thiệu lại hay không. Câu mở "Dạ em chào chị ..." đến từ các mẫu trả lời, nên vẫn còn ở cả hai cách soạn.
- Khi tài khoản Claude hết hạn mức giữa một lượt trong phòng, runner không nhận ra lý do này. Lượt đó chuyển sang soạn bằng `claude -p`, và tài khoản đó chưa bị đánh dấu hết hạn mức cho tới khi cách soạn cũ gặp lỗi hạn mức.
- Khi runner đổi sang tài khoản Claude khác, hai bot chạy trên tài khoản mới. Chưa thử xem bot có còn nhớ những gì đã làm trong phòng hay không; tin nhắn trong phòng thì vẫn còn.
- Sau mỗi lần thêm hoặc đổi tài khoản Claude của runner, anh cần chạy `scripts/stop_local.sh` rồi `scripts/start_local.sh`, để runner ghi lại cấu hình cho OpenMausBot và OpenMausBot đọc lại cấu hình đó. Chưa biết OpenMausBot có tự đọc lại cấu hình khi đang chạy hay không.
- File log `~/.thomhouse-bot/logs/openmausbot.log` có mã ghép nối của OpenMausBot. Theo README của OpenMausBot, mã ghép nối dùng để nối một điện thoại vào OpenMausBot. Anh không gửi file log này cho ai.
- Lượt chạy thử đọc nhãn từ dữ liệu nhãn giả. Chưa thử đọc nhãn khi listener (tiến trình nhận tin Zalo) đang chạy với tài khoản Zalo thật. Nếu Zalo không cho đọc nhãn lúc đó, vai trò chỉ cập nhật khi anh chạy lệnh đồng bộ nhãn trong lúc listener đã dừng. Một tài khoản có hơn 5.000 người được gắn nhãn chưa đồng bộ được.
- Script hồ sơ liên hệ có thể đoán một người là nhân viên trong khi người đó chưa có nhãn. Nếu người đó đã đồng ý trò chuyện với trợ lý AI, server vẫn để bot trả lời như với khách, còn Bot khách hàng báo đây là người nội bộ và không đưa hồ sơ. Cách tránh: gắn nhãn Nhân viên cho người thật sự làm ở studio, hoặc nhãn Khách hàng cho khách.
- Tên kỹ thuật viên và tên gói do lễ tân gõ được đưa nguyên văn cho bot, trừ tên gói nhắc dịch vụ nhóm sức khỏe hoặc chăm sóc phụ nữ. Lễ tân không gõ số điện thoại hay thông tin riêng của khách vào các ô này.
- Nút Dùng 1 lần tính số lần đã dùng trên trình duyệt. Nếu hai lễ tân bấm cùng lúc cho cùng một quyền lợi, quyền lợi có thể chỉ bị trừ một lượt.
- Nếu bridge đang gửi dở một câu trả lời của bot đúng lúc người nhận được gắn nhãn Quản lý hoặc Nhân viên, câu trả lời đó không bị thu hồi.
- Một tin cảm ơn hay tin hỏi thăm đã vào hàng chờ gửi đúng giờ, trong lúc bridge hoặc máy Mac đang tắt, vẫn được gửi khi bridge chạy lại, dù trễ nhiều ngày. Quy tắc 6 giờ chỉ áp cho tin chưa được xếp vào hàng chờ gửi. Người viết code tìm ra điểm này khi đọc code ngày 12/11, chưa sửa.
- Script `scripts/analyze_visits.py` mới được đo độ đúng trên tin nhắn giả. Trên 90 cuộc trò chuyện giả, trước các bản sửa ngày 12/11, 25 trên 28 lần đến mức chắc là đúng, 11 trên 23 lần đến mức khá chắc là đúng, và script tìm ra 36 trên 39 lần đến thật ở hai mức đó. Chưa ai đo trên tin nhắn thật. Vì lần đến mức khá chắc cũng được tính vào số liệu, lễ tân nên xem lại các lần đến suy ra từ tin nhắn trước khi dựa vào trạng thái của khách.
- Một trường hợp script có thể đoán sai ở mức chắc: khách chuyển khoản cho việc khác trong ngày, rồi studio trả lời câu hỏi giá bằng câu "cảm ơn chị đã ghé". Khi đó script ghi một lần đến kèm số tiền chuyển khoản đó.
- Ngày 12/11, script chạy thử trên tin nhắn thật chỉ tìm thấy 2 cuộc trò chuyện của khách, vì kho tin của zalo-agent trên máy chỉ có 18 trong số 420 cuộc trò chuyện riêng của tài khoản. Chưa ai tìm hiểu vì sao lệnh đồng bộ tin cũ lấy về ít như vậy.
- Bot khách hàng nhận được số lần đến suy ra từ tin nhắn trong hồ sơ, nhưng chỉ dẫn của bot chưa dặn bot nói rõ với Bot dịch vụ phần nào là phỏng đoán. Khi soạn bằng `claude -p`, bot không nhận các kết quả suy ra từ tin nhắn.
- Lệnh đồng bộ nhãn mới chạy với dữ liệu nhãn giả, và script nhập buổi làm từ file CSV mới chạy với server giả trong test. `scripts/stop_local.sh` chưa được chạy thật với OpenMausBot. Console chưa được mở trên trình duyệt với server đang chạy.

## Nói ngắn gọn nhất

Hai bot trong phòng chat là một cách soạn nháp mới, mặc định tắt. Cách này đã chạy thử với zalo-agent giả chiều 12/11 và tìm ra một lỗi làm Bot dịch vụ không đọc được quy tắc trả lời; lỗi đã được sửa trong code của runner nhưng bản sửa chưa chạy với OpenMausBot thật. Muốn bật, anh cần cả dòng `THOMHOUSE_DRAFT_ENGINE=rooms` của runner lẫn mục Phòng hai bot trên console; khi phòng gặp lỗi, runner quay về cách soạn cũ. Trước khi bật, anh cần chọn người xóa phòng khi khách xin xóa dữ liệu và duyệt hai ngưỡng mức chi tiêu. Công tắc Tự động trả lời mặc định tắt ở mọi hội thoại; khi công tắc bật, tin có ảnh menu, tin bị bước kiểm tra trước khi gửi báo lỗi và tin bot chuyển cho lễ tân vẫn chờ duyệt. Nhãn Khách hàng, Quản lý, Nhân viên trong Zalo cho hệ thống biết ai là khách và ai là người của studio. Trạng thái khách có số liệu khi lễ tân ghi buổi làm, khi anh nhập file CSV, hoặc khi `scripts/analyze_visits.py` đoán được lần đến từ tin nhắn cũ ở mức chắc hoặc khá chắc. Các phỏng đoán đó được tính ngay vào số liệu và ghi rõ là suy ra từ tin nhắn, nên lễ tân cần xác nhận hoặc bỏ từng phỏng đoán trong mục Suy ra từ tin nhắn cũ.

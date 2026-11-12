# Thông tin thom house nằm ngoài dự án chatbot

Ngày rà: 2026-11-08. Phạm vi: repo `~/Projects/thomhouse-academy-daily` và transcript của phiên dựng video trong repo đó, repo `~/Projects/thomhouse-analytics` cùng hai transcript cũ của thư mục analytics, transcript của phiên Claude Code trong `~/Projects/soraflow`, rồi đối chiếu với `data/services.json` và `data/business-facts.json` của dự án này. Tôi chỉ đọc, không sửa file nào ngoài báo cáo này.

## Phần anh cần duyệt

Bên ngoài dự án có hai nguồn menu mới hơn nguồn mà chatbot đang dùng, và hai nguồn này cho thấy `data/services.json` đã thiếu nhiều dịch vụ. Nguồn thứ nhất là bộ ảnh menu in trên Google Drive của thom house. Nguồn thứ hai là trang landing page anh gửi cho phiên Claude Code trong `~/Projects/soraflow` chiều 08/11. Hai nguồn này cùng ghi menu da 9 liệu trình, trong khi `services.json` chỉ có 5. Hai nguồn cũng có thêm nhóm triệt lông, 5 dịch vụ cộng thêm 50.000–199.000đ, một liệu trình da đầu mới và mặt nạ bán lẻ. Riêng trang landing page còn có 4 hạng thẻ thành viên, và đây là chính sách đầu tiên về thẻ mà tôi thấy trong mọi tài liệu của thom house.

Repo `thomhouse-analytics` không có dữ liệu gì. Repo chỉ có một file `AGENTS.md` dài một dòng tiêu đề. Repo không có số khách, doanh thu hay kênh bán. Repo học viện thì làm video kiến thức về da cho học viên. Video không nhắc dịch vụ hay giá, nên phần có ích cho chatbot nằm ở tài liệu nghiên cứu và nguồn gốc mà repo đó gom về.

Anh cần quyết năm việc trước khi tôi hay một phiên khác sửa `services.json`:

1. Mỗi nhóm menu lấy theo nguồn nào. Tôi đề xuất lấy bộ ảnh menu in làm nguồn chính cho nhóm da, tóc, triệt lông, dịch vụ cộng thêm và nhóm khỏe. Nhóm thư giãn và nhóm phụ nữ tạm giữ theo kho kiến thức, vì bộ ảnh không có trang của hai nhóm này. Trang landing page chỉ được dùng cho những mục khớp với bộ ảnh. Điểm yếu: không ảnh nào và cả trang landing page đều không ghi ngày, nên tôi chỉ dựa vào việc các nguồn khớp nhau để đoán bản nào đang dùng.
2. Giá của "Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch". Kho kiến thức và ảnh menu in cùng ghi 60 phút, 599.000đ. Trang landing page ghi 45 phút, 250.000đ. Tôi đề xuất giữ 599.000đ cho tới khi anh hỏi chủ doanh nghiệp, vì kho kiến thức và ảnh menu in khớp nhau. Điểm yếu: nếu trang landing page là bản sửa giá mới, chatbot sẽ báo giá cao hơn giá thật.
3. Menu sức khỏe phụ nữ. Trang landing page thêm Chăm sóc vòi trứng, Khai thông tam giác vàng, Bơm thảo dược và Túi ngâm mông thảo dược, đồng thời không còn Tiêu u – Thông kinh ngực. Bộ ảnh menu in không có trang menu phụ nữ để đối chiếu. Tôi đề xuất chatbot chưa báo các dịch vụ mới này cho tới khi chủ doanh nghiệp xác nhận. Điểm yếu: khách hỏi đúng tên dịch vụ mới sẽ phải chờ nhân viên trả lời.
4. Chatbot có báo giá Lăn dưỡng, Inner Fill, Bio PDRN và gói Bio PDRN full có bước IPL hay không. Phiên dựng video đã cấm nhắc ba dịch vụ này trong video, vì nghi một số bước có thể cần giấy phép y tế. Nghi ngờ này là suy luận và chưa ai kiểm quy định. Tôi đề xuất chatbot chỉ đọc tên, thời lượng và giá khi khách hỏi đúng tên, không đọc câu mô tả, rồi chuyển câu hỏi về quy trình cho nhân viên. Điểm yếu: nếu các bước này thật sự cần giấy phép, chatbot vẫn đang quảng bá chúng.
5. Mốc sau sinh. Trang landing page dặn khách mới sinh dưới 2–3 tháng nhắn trước. Phiếu sức khỏe giấy mà anh gửi ảnh cho Claude ngày 09/09 chia mốc ở 6 tháng; việc phiếu này thuộc thom house là suy luận của tôi (mục B). Chatbot cần một mốc duy nhất để biết khi nào chuyển cho nhân viên. Tôi đề xuất dùng mốc 6 tháng, vì mốc này rộng hơn nên an toàn hơn. Điểm yếu: khách sinh được 3–6 tháng sẽ bị chuyển cho nhân viên dù trang landing page coi là làm được.

Phần còn thiếu thì vẫn thiếu sau lượt rà này: số hotline, Zalo, giờ đóng cửa, ngày nghỉ, chính sách hủy và đổi lịch, đặt cọc, thanh toán, hoàn tiền, thẻ quà tặng, nhân viên nam hay nữ, nơi gửi xe và hóa đơn.

## Thuật ngữ dùng trong báo cáo

| Thuật ngữ | Nghĩa trong báo cáo này |
|---|---|
| kho kiến thức | thư mục `#1-thomhouse-overview` trên Drive của chủ doanh nghiệp; dự án này chép thư mục đó vào `sources/drive/`, và `services.json` được dựng từ thư mục này |
| bộ ảnh menu in | 57 ảnh PNG trong thư mục `#2-thomhouse-resources/thomhouse-menu` trên Drive, chia bốn thư mục: da (21 ảnh), triệt lông (3), khỏe (19), thư giãn và tóc (14) |
| trang landing page | file `source/landing-page.html` trong repo học viện; đây là bản lưu của một artifact trên claude.ai mà anh gửi lúc 15:08 ngày 08/11 kèm lời "Đây là landing page của thomhouse"; chân trang ghi "Made by thomhouse team" |
| phiên dựng video học viện | phiên Claude Code tên "thomhouse-academy-daily: 6 video kiến thức facial", chạy trong `~/Projects/thomhouse-academy-daily` |
| phiên soraflow | phiên Claude Code chạy trong `~/Projects/soraflow`, phiên đã mở phiên dựng video học viện và các phiên video hằng ngày khác |
| giá ngày, giá tối | giá khung 9h–20h30 và giá sau 20h30, theo cách menu chia |

Giờ trong báo cáo là giờ Việt Nam. Transcript ghi giờ UTC; tôi đã cộng 7 giờ.

## A. Repo thomhouse-academy-daily làm gì, và dùng những dữ kiện nào về thom house?

### Quy trình đi từ đâu đến đâu?

Repo làm sáu video giảng giải về da mặt cho học viên của thom house, mỗi video một kiểu hình ảnh. Sáu chủ đề là cấu tạo da, sai lầm khi chăm sóc da, phân loại da, hàng rào bảo vệ da, mụn hình thành ra sao và quầng thâm mắt. Anh yêu cầu việc này lúc 14:29 ngày 08/11 trong phiên soraflow. Phiên soraflow mở phiên dựng video học viện lúc 15:44 cùng ngày.

Đầu vào nằm trong thư mục `source/` của repo. Thư mục `source/#1-thomhouse-overview/` là bản tải về của kho kiến thức. Tôi chạy `diff -rq` giữa thư mục này và `sources/drive/` của dự án chatbot: hai thư mục giống nhau, chỉ khác file `.DS_Store` và thư mục `.claude`. Thư mục `source/thomhouse-resources/` chứa bộ ảnh menu in, 12 ảnh chụp không gian studio và file ghi âm giọng chị Thơm. File `source/landing-page.html` là trang landing page.

Một video đi qua các bước sau, theo `docs/thomhouse-academy-daily-brief.md` mục 6 và các file trong `kit/`:

1. Một agent nghiên cứu mỗi chủ đề từ nguồn y khoa bên ngoài (AAD, BAD, DermNet NZ, StatPearls, NHS, Mayo Clinic, Bệnh viện Da liễu Trung ương) và ghi vào `research/raw/` và `formats/<slug>/research.md`. Kho kiến thức không được dùng làm nguồn cho kiến thức da.
2. Phiên viết `script.json` rồi chạy `kit/claims.mjs` để dò lời hứa y tế, từ bán hàng và giá trong lời thoại.
3. ElevenLabs đọc lời thoại bằng giọng nhân bản của chị Thơm, sau đó ffmpeg tăng tốc lên 1,3 lần. ElevenLabs nghe lại và chép ra chữ để bắt chữ đọc sai.
4. Phiên dựng hình bằng HyperFrames (công cụ dựng video từ HTML), trộn tiếng ở mức −16 LUFS, quét chữ chồng hình rồi render ra MP4 1920×1080, 30 hình/giây.
5. Ba agent kiểm độc lập: kỹ thuật, hình và thương hiệu, nội dung. Video lỗi được sửa và kiểm lại tối đa ba vòng.
6. Video được chép vào `~/Downloads/thomhouse-academy-resources/daily/08-11-2026/` và ghi một dòng vào `cho-duyet.txt`.

Anh là người duyệt từng video trong chat. Phiên không được upload, commit hay đăng video khi anh chưa đồng ý, và mọi lệnh tạo hình hay video tốn tiền phải báo giá trước (`docs/owner-decisions-2026-11-08.md`, mục Output; brief mục 10).

Repo có chữ "daily" trong tên nhưng chưa có lịch chạy. Thư mục `~/.claude/scheduled-tasks/` chỉ có tác vụ định kỳ của Dark Brain và của một dự án khác. Không tác vụ nào nhắc thom house.

Trạng thái lúc 19:12, khi tôi đọc lần cuối: phiên dựng video vẫn đang chạy, bản ghi mới nhất của transcript lúc 19:09. Video 1 đã render (`out/2026-11-08-01-cau-tao-da/2026-11-08-01-cau-tao-da.mp4`, dài 68,6 giây, −16 LUFS, đỉnh thật −2,6 dBTP theo `render.json`). Video 2, 3 và 4 mới có ảnh bìa trong `out/`. Thư mục xuất trong `~/Downloads` chưa tồn tại, nên chưa video nào được xuất cho anh duyệt. Tin nhắn sửa brief mà phiên soraflow gửi lúc 16:02 không xuất hiện trong transcript của phiên dựng video; tôi grep câu mở đầu của tin nhắn đó và được 0 kết quả.

Trong phiên dựng video, anh gửi năm tin nhắn góp ý từ 17:45 đến 18:57. Anh muốn chỉ còn một dòng chữ thương hiệu là `thomhouse - academy`, với khoảng cách chữ hẹp lại. Anh muốn video dùng ảnh thật từ Pexels và Unsplash, không lặp lại lỗi của Dark Brain, và tiêu đề video viết đầy đủ hơn. Anh muốn giọng văn chuẩn nhưng dịu dàng, vui tươi, không cứng nhắc. Hai tin cuối cho phép dùng Codex, Gemini, Antigravity và GPT để tạo ảnh minh họa hợp với hệ thiết kế của thom house.

### Video nói gì về thom house?

Video gần như không nói gì về dịch vụ. Tôi tìm tên dịch vụ, giá, địa chỉ và tên chị Thơm trong `script.json`, `storyboard.md` và `src/story.js` của cả sáu video: không có kết quả nào. Thẻ cuối video chỉ có câu tóm ý, dòng `thomhouse - academy`, câu khẩu hiệu và câu khuyên đi khám bác sĩ da liễu. Vì vậy, video không mâu thuẫn với dữ liệu của chatbot.

### Những dữ kiện về thom house mà repo dùng

Bảng dưới gom các dữ kiện về thom house mà tài liệu của repo ghi, kèm file nguồn. Phần lớn các dữ kiện này cũng có trong kho kiến thức. Cột cuối ghi dữ kiện đó có mới so với `business-facts.json` hay không.

| Dữ kiện | Nội dung | File | So với business-facts.json |
|---|---|---|---|
| Tên và năm mở | thom house healing studio, mở năm 2019 | `docs/thomhouse-academy-daily-brief.md` mục 3.1 | Đã có |
| Địa chỉ | 72 đường số 37, phường Tân Hưng, quận 7; một slide menu phụ nữ ghi Tân Kiểng, nên video không ghi phường | brief mục 3.1 | Đã có, đã ghi xung đột phường |
| Địa chỉ trên ảnh menu in | mọi ảnh menu in có in địa chỉ ở chân trang đều ghi "72 đường số 37, phường Tân Hưng quận 7"; tôi không thấy ảnh nào ghi Tân Kiểng | bộ ảnh menu in | Mới: thêm nguồn ủng hộ Tân Hưng |
| Cách viết tên | trên màn hình luôn viết `thom house` chữ thường; "Thơm House" chỉ dùng cho Fanpage; video học viện dùng một dòng `thomhouse - academy` theo yêu cầu của anh | brief mục 3.1; memory của repo học viện | Kho kiến thức vẫn còn xung đột cách viết; ảnh menu tóc in chữ "Thom House" trong thân bài |
| Thương hiệu con cho menu da | ảnh menu da và trang landing page ghi "thom house facial studio" | bộ ảnh menu in; trang landing page | Mới |
| Người sáng lập | chị Thơm; không phải bác sĩ, lương y hay chuyên gia y tế; nhân viên gọi là team thom house hoặc đội ngũ kỹ thuật viên | brief mục 3.1 | Đã có |
| Quan hệ giữa anh và chị Thơm | ngày 08/11, anh nói anh là người quyết thay chị Thơm, và yêu cầu mọi tài liệu vẫn gọi chị Thơm là người sáng lập | `~/.claude/projects/-Users-luuphuc-Projects-soraflow/memory/thomhouse-founder-no-consent-asks.md` | Mới; chatbot vẫn gọi chị Thơm là người sáng lập |
| Thông tin liên hệ | video không được hiện hotline, website, Zalo hay giờ mở cửa, vì kho kiến thức ghi các mục này là chưa xác nhận | brief mục 3.1 | Khớp: các mục này vẫn thiếu |
| Giọng văn | nội dung quảng bá gọi khách là *bạn* và tự xưng *mình*; chat 1:1 xưng *em*, gọi *anh/chị*; tách hai cách này là suy luận của tài liệu học viện từ tài liệu 13 | brief mục 3.2 | Khớp với đề xuất trong báo cáo rà kho kiến thức |
| Từ cần tránh | ngay, gấp, chỉ còn, nhanh tay, sale, ưu đãi, khuyến mại; trị liệu, điều trị, chữa khỏi, đảm bảo 100%; quý khách, thượng đế, VIP | brief mục 3.2 | Có thể đưa vào bộ kiểm câu trả lời của chatbot |
| Danh sách từ y tế bị cấm và từ thay thế | bảng "Never / Use instead": điều trị → chăm sóc; chữa khỏi → hỗ trợ giảm; châm cứu → ấn huyệt, diện chẩn, hơ ngải | brief mục 3.3; `kit/claims.mjs` | Có sẵn dạng biểu thức chính quy trong `kit/claims.mjs` |
| Câu vượt quy định trên ảnh menu da | "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố" (trang 18, 20), "Lâm sàn trong 7 năm qua" (trang 11), "tạo lớp bảo vệ hoàn hảo" (trang 15), "theo chỉ định" (trang 17), "Bắn trẻ hoá IPL" và "Carboxy Therapy" (trang 21) | brief mục 3.4 | Mới |
| Sai sót trong kho kiến thức | SHR bị giải thích theo nhiều cách; tên vi khuẩn P. acnes đã đổi thành Cutibacterium acnes; plasma được gọi là an toàn khi chưa rõ máy | brief mục 3.6 | Khớp với báo cáo rà kho kiến thức |
| Giới hạn khi nặn mụn | trang AAD mà agent nghiên cứu đọc ghi rằng nặn mụn là việc của bác sĩ da liễu; tài liệu dặn video không gợi ý học viên hay nhân viên tự nặn mụn | `research/raw/02-sai-lam-cham-soc-da.md` dòng 97 | Mới; liên quan dịch vụ Detox da có bước nặn mụn 30 phút |
| Tài sản khác | giọng nhân bản của chị Thơm trên ElevenLabs tên "Thơm - Thomhouse"; 12 ảnh không gian studio, không thấy mặt người theo lượt xem của tài liệu học viện | brief mục 5; `docs/thomhouse-deep-dive.md` | Không liên quan trực tiếp tới chatbot |

## B. Repo thomhouse-analytics đo những gì?

Repo không đo gì. Tôi liệt kê thư mục `~/Projects/thomhouse-analytics`: repo chỉ có `AGENTS.md`, 47 byte, nội dung là dòng tiêu đề "## Imported Claude Cowork project instructions". Tôi chạy `cmp` và thấy file này giống hệt `AGENTS.md` trong kho kiến thức. Repo không có dữ liệu khách, doanh thu, dịch vụ hay kênh. Phiên soraflow cũng ghi nhận repo "gần như trống" lúc 14:31 ngày 08/11, rồi chuyển sang lấy tài liệu từ Drive.

Trên máy còn hai transcript của một thư mục cũ tên `~/thomhouse-analytics`. Thư mục này nay không còn. Hai transcript nằm trong `~/.claude/projects/-Users-luuphuc-thomhouse-analytics/`:

1. Phiên ngày 19/07/2026 chỉ cài hai bộ skill từ GitHub. Phiên không đọc dữ liệu nào.
2. Phiên ngày 09/09/2026 sắp xếp lại phiếu sức khỏe khách hàng. Anh gửi ảnh phiếu giấy đang dùng và viết rằng cơ sở là spa chăm sóc sức khỏe có dùng kỹ thuật Đông y, không phải cơ sở chữa bệnh. Phiên đó làm một workflow năm góc nhìn và trả về bản thiết kế A4 hai mặt.

Phiếu giấy gốc là thông tin thật về cách tiệm đang làm. Theo bản chép trong workflow của phiên 09/09, phiếu có tiêu đề "THÔNG TIN THEO DÕI SỨC KHỎE KHÁCH HÀNG" và hỏi tên, số điện thoại, địa chỉ. Phiếu có 9 câu tick: tiền sử gia đình, tiền sử bệnh của khách, sức khỏe hiện tại, thói quen ăn uống đồ lạnh hay nóng, thực phẩm chức năng, đầy bụng hay đau nhức, giấc ngủ, mức căng thẳng và thai sản. Câu thai sản chia ba ô: không mang thai, đang mang thai hoặc sau sinh dưới 6 tháng, sau sinh trên 6 tháng. Cuối phiếu có mục "Đánh giá chỉ số sức khỏe" gồm thể trạng, nhu cầu, độ tin cậy và lưu ý.

Bản thiết kế mới do Claude đề xuất, và transcript không cho biết tiệm đã dùng bản này chưa. Bản mới thay các câu hỏi bệnh bằng danh sách 14 tình trạng cần báo, ví dụ huyết áp, thuốc chống đông, tiểu đường và mới tiêm filler hay laser trong 2 tuần. Bản mới thêm ba ô chỉ đúng cho riêng hôm đó: vừa uống rượu bia, vừa ăn no trong 1 giờ, đang sốt hay mệt khác thường. Bản mới cũng đổi mốc sau sinh thành "mới sinh trong vòng 6 tháng".

Ảnh menu triệt lông trang 3 cho thấy tiệm còn một thẻ ghi chú thứ hai, dùng trong phòng. Thẻ ghi tên hoặc biệt danh khách muốn được nhớ, dị ứng, lực tay (yếu, vừa, mạnh), mang thai, tai nhạy cảm, vùng tập trung, vùng cần tránh, gói dịch vụ, kỹ thuật viên và ô "Today+++" (cào nhiều, massage nhiều, gãi móng, gãi thịt).

Ba điều anh nên biết về nguồn này. Phiếu và bản thiết kế không ghi tên thom house, vì bản thiết kế để trống ô `[TÊN SPA]`. Việc phiếu thuộc thom house là suy luận của tôi từ tên thư mục. Câu "khách nữ 25–60 tuổi là chính" trong workflow ngày 09/09 do Claude tự viết làm bối cảnh, không phải số liệu đo được, nên tôi không coi đó là dữ kiện về khách. Báo cáo này không chép dữ liệu cá nhân nào của khách, vì hai nguồn trên chỉ là mẫu phiếu trống.

## C. Phiên soraflow dựng các phiên video hằng ngày như thế nào?

Phiên soraflow đã mở cả ba phiên làm video hằng ngày. Transcript chính của phiên soraflow là `~/.claude/projects/-Users-luuphuc-Projects-soraflow/af322bac-c1e7-4607-a328-cd820ffd3fb1.jsonl` (93 MB, từ 25/10 đến 08/11). Phiên này mở từng phiên mới bằng công cụ mở phiên của app Claude, mỗi phiên làm video cho một thương hiệu:

| Phiên được mở | Lúc mở | Thư mục | Tên hiện trên app |
|---|---|---|---|
| Dark Brain, video tin AI | 23:00 ngày 04/11 | `~/Projects/darkbrain-studio` | `darkbrain-studio`, tiêu đề "Dark Brain Studio: 6 video tin AI theo design system" |
| Aura Coach, video học tiếng Anh | 14:16–14:17 ngày 05/11 (ba lần gọi, lần cuối có thêm bước đọc quy trình Dark Brain) | `~/Projects/aura-coach-studio` | đổi tên thành `aura-coach-daily` |
| Thom house Academy, video kiến thức da | 15:44 ngày 08/11 | `~/Projects/thomhouse-academy-daily` | `thomhouse-academy-daily`, tiêu đề "thomhouse-academy-daily: 6 video kiến thức facial" |

Anh gọi phiên Dark Brain là darkbrain-daily, còn app lưu tên phiên là `darkbrain-studio`.

Ba phiên dùng chung một khuôn. Trước tiên, phiên soraflow chạy một workflow nghiên cứu và ghi tài liệu vào repo mới. Với thom house, workflow `thomhouse-deep-dive-and-style-catalog` cho năm agent đọc song song: kho kiến thức, nhận diện hình ảnh từ trang landing page và ảnh, quy trình Dark Brain, quy trình Aura và danh mục kiểu hình. Sau đó một agent tổng hợp viết ba file: báo cáo tiếng Việt cho anh (`docs/thomhouse-deep-dive.md`), danh mục kiểu hình (`docs/style-catalog.md`) và bản giao việc tiếng Anh (`docs/thomhouse-academy-daily-brief.md`). Cuối cùng một agent rà độc lập. Aura cũng có bộ ba tài liệu tương tự, thêm file ghi 24 lỗi do lượt rà độc lập tìm ra.

Lời giao việc gửi cho mỗi phiên mới có cùng thứ tự: một câu nêu nhiệm vụ; danh sách file phải đọc theo thứ tự, trong đó file quyết định của anh thắng mọi tài liệu cũ; danh sách video và kiểu hình; cách làm (dùng lại bộ công cụ Dark Brain ở chế độ chỉ đọc, viết nguồn cho mọi dữ kiện, dò lời hứa trước khi lồng tiếng, kiểm −16 LUFS, phụ đề và dấu tiếng Việt); giọng đọc và số credit ElevenLabs còn lại; luật báo giá trước lệnh tốn tiền; cấm commit, upload, đăng khi anh chưa đồng ý; và điều kiện hoàn thành gồm thư mục xuất `~/Downloads/<studio>-resources/daily/<ngày>/`, gửi từng video cho anh và báo cáo tiếng Việt. Sau khi mở phiên mới, phiên soraflow gửi tiếp các lỗi mà lượt rà độc lập tìm ra bằng tin nhắn kết thúc bằng "No reply needed". Với thom house, tin nhắn lúc 16:02 dặn phiên dựng video học viện lấy tên dịch vụ da theo trang landing page và ảnh menu, và vẫn bỏ Lăn dưỡng, Inner Fill, Bio PDRN.

Cách đặt tên: tên phiên viết thường nối gạch ngang; tên video dạng `YYYY-MM-DD-NN-chủ-đề`, ví dụ `2026-11-08-01-cau-tao-da`; file xuất dạng `<NN>-<kiểu hình>-<chủ đề>.mp4`, thêm đuôi `-chua-dat-kiem` khi chưa qua đủ ba lượt kiểm.

Lịch chạy chỉ có ở Dark Brain. Tác vụ `darkbrain-daily-news` trong `~/.claude/scheduled-tasks/` chạy lúc 21:00 và 06:00, mỗi lần hai video, do anh lập ngày 06/11. Tác vụ `darkbrain-review-actions` chạy mỗi 10 phút để xử lý nút Duyệt và Đã đăng mà anh bấm trên trang web duyệt video của Dark Brain. Tôi không thấy tác vụ định kỳ nào cho Aura hay thom house; hai phiên này làm từng đợt video trong phiên.

## D. Dữ liệu của chatbot lệch với các nguồn ngoài ở đâu?

### D1. Cùng một dịch vụ, các nguồn ghi khác nhau

Tôi so `services.json` với ảnh menu in (xem bằng mắt, xem mục "Tôi đã đọc và chạy gì") và với trang landing page. Cột cuối là đề xuất của tôi, chưa có ý kiến chủ doanh nghiệp.

| Dịch vụ | services.json (từ kho kiến thức) | Ảnh menu in | Trang landing page | Đề xuất |
|---|---|---|---|---|
| Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch | 60 phút, 599.000đ | trang 14 menu khỏe: 60 phút, 599.000đ | 45 phút, 250.000đ | Giữ 599.000đ, hỏi chủ doanh nghiệp |
| Quy trình của Giải mỏi đứng lâu | 6 bước trùng nguyên văn quy trình Thiếu máu não (services.json đã ghi chú điểm này) | trang 16 cũng in quy trình vai cổ | 6 bước riêng cho chân: đả thông cơ bó chân, bấm huyệt chân, chăm sóc từng bên chân | Trang landing page có vẻ đã sửa lỗi in; hỏi chủ doanh nghiệp trước khi dùng |
| Gói Mụn 5 in 1 (Signature) | 90 phút, 599.000đ, 6 bước, bước cuối là ánh sáng xanh SHR | trang 4–5: 60–90 phút, 599.000đ, 5 bước, không có SHR | 60–90 phút, 599.000đ, 5 bước, không có SHR | Theo ảnh menu in |
| Xóa thâm quầng mắt, gói cơ bản | 60 phút, 329.000đ | trang 8: 45 phút, 329.000đ | 45 phút, 329.000đ | Theo ảnh menu in |
| Xóa thâm quầng mắt, gói điện xung trường | 90 phút, 629.000đ; câu "gấp 20 lần điện di ion" | trang 8–9: 60 phút, 629.000đ; câu "gấp 10 lần ... tại cơ sở" | 60 phút, 629.000đ; câu "gấp 10 lần" | Theo ảnh menu in về thời lượng; không đọc con số 10 hay 20 |
| Chăm sóc da kích ứng | 90 phút, 599.000đ | không có trang riêng; da kích ứng là một lựa chọn của Cấp dinh dưỡng cơ bản | như ảnh menu in | Thay bằng Cấp dinh dưỡng cơ bản sau khi chủ doanh nghiệp xác nhận |
| Gói Mụn Chuyên Sâu | 75 phút, 389.000đ, 5 bước | không có; trang 2–3 có Detox da 60–75 phút, 389.000đ, quy trình khác | Detox da như ảnh menu in | Theo suy luận của tôi, Detox da đã thay gói này vì cùng giá; cần hỏi |
| Detox mùi cơ thể | 90 phút, 1.190.000đ | bìa trang 5 ghi "Detox cơ thể", trang 6 vẫn viết "Detox mùi cơ thể"; cùng giá | "Detox cơ thể" | Thêm "Detox cơ thể" làm tên gọi khác |
| Tiêu u – Thông kinh ngực | 60 phút, 650.000đ | bộ ảnh không có menu phụ nữ | không có | Hỏi dịch vụ còn bán không |

Các dịch vụ còn lại trong `services.json` khớp với hai nguồn ngoài ở giá và thời lượng. Bốn dịch vụ thư giãn khớp trang landing page. Ba dịch vụ tóc khớp cả ảnh menu in và trang landing page. Năm dịch vụ khỏe còn lại khớp ảnh menu in.

### D2. Dịch vụ và sản phẩm mà services.json chưa có

| Mục | Thời lượng và giá | Có trên ảnh menu in | Có trên trang landing page |
|---|---|---|---|
| Massage mặt thư giãn | 60 phút, 289.000đ | Có, trang 6–7 | Có |
| Cấp dinh dưỡng cơ bản (chọn da nhạy cảm, kích ứng, cháy nắng, hoặc da thâm sạm, mụn, khô, lỗ chân lông to) | 60–75 phút, 599.000đ | Có, trang 10–11 | Có |
| Cấp dinh dưỡng bằng công nghệ Plasma fusion | 60 phút; tinh chất 999.000đ; dịch chiết tế bào gốc 1.500.000–2.500.000đ | Có, trang 12–13 | Có |
| Lăn dưỡng | 60 phút; da cần làm dày sừng 1.500.000đ; mụn, sẹo, nám, nếp nhăn 2.500.000đ | Có, trang 14–15 | Có |
| Inner Fill nâng cấp da | 60–75 phút, 6.500.000đ | Có, trang 16–17 | Có |
| Bio PDRN nuôi da căng bóng | 60 phút 2.500.000đ; bản full 90 phút 5.000.000đ, có mặt nạ EZ CO₂ và bắn trẻ hóa IPL | Có, trang 18–21 | Có |
| Peel peptide da đầu | 15 phút, 299.000đ | Có, menu tóc trang 10–12 | Có |
| Triệt lông, suất lẻ | nách 150.000đ; mép, cằm, trán 100.000đ; viền bi, ngực 180.000đ; mặt, tay, cổ, nửa chân 290.000đ; bikini, chân, bụng, lưng 340.000đ; full body 1.800.000đ | Có, trang 2 | Có |
| Triệt lông, combo 20 buổi | nách 2.000.000đ; mép, cằm, trán 999.000đ; viền bi, ngực 1.800.000đ; mặt, tay, cổ, nửa chân 2.900.000đ; bikini, chân, bụng, lưng 3.400.000đ; full body 18.000.000đ | Có, trang 2 | Không |
| Dịch vụ cộng thêm vào buổi massage | detox da đầu +50.000đ; massage mặt 10 phút +50.000đ; massage tay 10 phút +50.000đ; massage cổ vai gáy 30 phút +199.000đ; massage chân 30 phút +199.000đ | Có, menu tóc trang 14 | Có |
| Mặt nạ bán lẻ | mặt nạ tóc bồ kết 60.000đ; mask dẻo Hàn Quốc collagen 50.000đ; mặt nạ phục hồi PDRN 90.000đ | Có, menu tóc trang 13 | Có |
| Cải thiện tiêu hóa, giảm bụng to | 45 phút, 599.000đ | Không; menu khỏe in chỉ có 6 dịch vụ | Có |
| Chăm sóc vòi trứng | 45 phút, 599.000đ | Không có menu phụ nữ để đối chiếu | Có |
| Khai thông tam giác vàng – hơ ngải cứu vùng kín | một buổi, 1.000.000đ | Không có menu phụ nữ để đối chiếu | Có |
| Bơm thảo dược (trinh nữ hoàng cung, ích mẫu, hoàng bá, lá trầu và 6 vị khác) | một buổi, 1.000.000đ | Không có menu phụ nữ để đối chiếu | Có |
| Túi ngâm mông thảo dược, dùng tại nhà | 35.000đ | Không có menu phụ nữ để đối chiếu | Có |

Sau các mục mới này, giá cao nhất của một buổi lẻ không còn là Yoni Retreat 3.500.000đ mà là Inner Fill 6.500.000đ. Gói đắt nhất là combo triệt lông full body 20 buổi, 18.000.000đ. Câu nào trong tài liệu nói giá cao nhất là 3.500.000đ sẽ sai nếu menu mới được xác nhận.

Trang landing page ghi tổng 31 liệu trình: thư giãn 4, khỏe 7, phụ nữ 7, da 9, tóc 4. Con số này chưa tính nhóm triệt lông.

### D3. Thông tin doanh nghiệp: cái gì mới, cái gì vẫn thiếu

| Mục trong business-facts.json | Trạng thái hiện tại | Nguồn ngoài nói gì | Đề xuất |
|---|---|---|---|
| `opening_hours` | conflict, value null | Trang landing page: "Giờ đón khách: Từ 9h sáng", giá tối áp dụng sau 20h30, massage chân phục vụ đến 24h. Không ghi giờ đóng cửa và ngày nghỉ | Ghi giờ mở 9h là có nguồn; giờ đóng cửa vẫn thiếu |
| `address` | conflict giữa Tân Hưng và Tân Kiểng | Trang landing page và mọi ảnh menu in có in địa chỉ đều ghi phường Tân Hưng | Nghiêng về Tân Hưng; vẫn cần chủ doanh nghiệp chốt dòng địa chỉ |
| `google_maps_link` | documented, chưa mở link | Trang landing page dùng cùng link `maps.app.goo.gl/Xo43VT6JYEtxxCNf9` | Tôi cũng chưa mở link, vì nhiệm vụ cấm truy cập mạng |
| `beacons_link` | documented, chưa kiểm | Trang landing page ghi "Mọi kênh liên hệ: beacons.ai/thomhouseq7", nút "Giữ chỗ" cũng trỏ tới link này | Khớp; chưa kiểm nội dung trang |
| `facebook_fanpage` | chỉ có tên | Ảnh menu in và trang landing page ghi "Fanpage Thơm House", không có URL | Vẫn thiếu URL |
| `hotline_phone`, `zalo_oa`, `website_email` | missing | Không nguồn ngoài nào có số hotline hay Zalo. Trang landing page là artifact riêng tư trên claude.ai, không phải website công khai. Thư mục Drive thuộc tài khoản Google `thomhouseq7@gmail.com` (`sources/drive-index.md`) | Vẫn thiếu; không đưa email cho khách khi chưa hỏi chủ doanh nghiệp |
| `membership` | missing | Trang landing page có 4 hạng thẻ: Khách mới 2.000.000–5.000.000đ tặng thêm 5% trên hóa đơn; Khách quen 6.000.000–10.000.000đ tặng 10%; Khách gắn bó 10.000.000–14.000.000đ tặng 15%; Khách ruột từ 15.000.000đ tặng 20%. Hạng đầu tặng bắn trẻ hóa hằng tuần trong 1 tháng, ba hạng sau trong 1,5 tháng, khi dùng dịch vụ trên 200.000đ. Điều kiện chi tiết: nhắn Fanpage | Mới. Khoảng mệnh giá trùng nhau ở mức 10.000.000đ và hở ở 5–6 triệu, 14–15 triệu; cần hỏi trước khi chatbot báo |
| `multi_session_packages` | missing | Ảnh menu triệt lông có combo 20 buổi | Mới |
| `combos` | chỉ có Yoni Retreat tặng nắn chỉnh sàn chậu | Trang landing page ghi Yoni Retreat "Tặng nắn chỉnh sàn chậu (500,000đ)"; có thêm 5 dịch vụ cộng thêm | Thêm dịch vụ cộng thêm |
| `promotions` | missing | Ngoài quà bắn trẻ hóa của thẻ thành viên, không nguồn nào có khuyến mại đang chạy. Bước SHR "theo thời gian khuyến mại" không còn trên ảnh menu in | Vẫn thiếu |
| `follow_up_guidance` | derived_unapproved | Trang landing page: "Trong 24 giờ, team nhắn hỏi thăm và gửi vài lưu ý tự chăm sóc tại nhà" | Bước 24 giờ nay có trên trang anh gửi; các mốc 2–3 ngày và 1 tháng vẫn chưa ai duyệt |
| `pregnancy_policy`, `postpartum_policy` | derived_unapproved | Trang landing page: đang mang thai hoặc mới sinh dưới 2–3 tháng thì nhắn team trước, tránh tác động mạnh vùng bụng. Phiếu giấy gốc chia mốc sau sinh ở 6 tháng | Xung đột 2–3 tháng với 6 tháng (quyết định số 5 ở đầu báo cáo) |
| Lưu ý trước khi đến (chưa có mục) | chưa có | Trang landing page: báo dị ứng bưởi, ngải cứu, tinh dầu; vừa peel da hoặc làm laser nơi khác thì da cần nghỉ; có bệnh cần điều trị thì khám bác sĩ chuyên khoa trước; mụn nang, viêm da, da kích ứng nặng thì gặp bác sĩ da liễu trước; rụng tóc kèm dấu hiệu bất thường thì đi khám song song | Thêm thành mục mới, ghi nguồn là trang landing page |
| Một buổi ở tiệm (chưa có mục) | chưa có | Trang landing page mô tả 5 bước: mời trà, hỏi trước rồi gợi ý một đến hai lựa chọn, thay đồ riêng, giữ yên lặng khi khách ngủ, "không vội tính tiền" | Có thể dùng để trả lời khách hỏi "đến tiệm thì thế nào" |
| `staff_gender`, `male_customers_served`, `children_served`, `parking`, `invoice_vat`, các chính sách hủy, đổi lịch, đến trễ, đặt cọc, thanh toán, hoàn tiền, thẻ quà tặng | missing | Không nguồn ngoài nào có | Vẫn thiếu |
| `assistant_persona_name`, `assistant_pronouns` | conflict | Không nguồn ngoài nào quyết. Tài liệu học viện chỉ suy luận rằng chat dùng *em – anh/chị* | Vẫn chờ anh quyết |

### D4. Lời hứa y tế mới cần thêm vào danh sách câu chatbot không được nói

Ngoài các câu đã ghi trong báo cáo rà kho kiến thức, ảnh menu in và trang landing page có thêm các câu sau. Chatbot không nên đọc lại các câu này:

- "Có hiệu quả trong việc điều trị mụn trứng cá và sắc tố" (ảnh menu da trang 18 và 20).
- "Lâm sàn trong 7 năm qua" (trang 11) và câu "được chị Thơm đồng hành cùng khách suốt 7 năm" trên trang landing page.
- "tạo lớp bảo vệ hoàn hảo" và "giảm sẹo nhẹ" của Lăn dưỡng (trang 15, trang landing page).
- "Inner Fill hoạt chất theo chỉ định" (trang 17, trang landing page).
- "Hỗ trợ phục hồi liên kết collagen và elastin" của Plasma fusion (trang 13, trang landing page).
- "hiệu quả gấp 10 lần điện di ion" của gói điện xung trường. Kho kiến thức ghi 20 lần, nên con số này đã có hai bản khác nhau.
- Câu của menu phụ nữ trên trang landing page: "hỗ trợ đẩy khí hư ra bên ngoài và làm ấm tử cung" (tam giác vàng), "hỗ trợ các vấn đề nấm, viêm nhiễm, khí hư" (túi ngâm mông), "Giải tắc khí huyết vòi trứng" (chăm sóc vòi trứng).

Bộ biểu thức chính quy trong `~/Projects/thomhouse-academy-daily/kit/claims.mjs` chặn sẵn nhiều nhóm từ trên. Chatbot dùng lại được phần lớn danh sách đó, trừ nhóm chặn giá và từ đặt lịch, vì chatbot phải báo giá và nhận đặt lịch.

## Những phát hiện này ảnh hưởng gì tới chatbot?

Ảnh hưởng lớn nhất là chatbot đang trả lời theo menu cũ. Khách hỏi Massage mặt thư giãn, Plasma, Bio PDRN, triệt lông hay peel da đầu sẽ nhận câu trả lời rằng tiệm không có dịch vụ đó, trong khi menu in đang bán. Khách hỏi gói quầng mắt điện xung trường sẽ nghe 90 phút thay cho 60 phút. Vì vậy, `services.json` cần một bản mới dựng từ bộ ảnh menu in. Dự án này đã có bản sao bộ ảnh trong `sources/drive-resources/` (các file mang giờ sửa 18:47 ngày 08/11, `INDEX.md` ghi Drive ID từng ảnh), nên bản mới có thể ghi nguồn tới từng trang ảnh.

Ảnh hưởng thứ hai là phần câu hỏi về sức khỏe. Tiệm đang ghi thông tin của khách trên thẻ ghi chú trong phòng (ảnh menu triệt lông trang 3), và theo suy luận ở mục B còn dùng một phiếu sức khỏe giấy. Theo tôi, chatbot không cần hỏi lại các câu bệnh trong chat; khi khách tự kể bệnh, thai kỳ hay sau sinh, chatbot chuyển cho nhân viên như báo cáo rà kho kiến thức đã đề xuất. Danh sách 14 tình trạng của bản thiết kế phiếu ngày 09/09 có thể làm danh sách từ khóa để chatbot nhận ra lúc cần chuyển người. Điểm yếu: danh sách đó do Claude viết, chưa có người có chuyên môn y tế duyệt.

Ảnh hưởng thứ ba là quy tắc thương hiệu. Các quy tắc của repo học viện khớp với quy tắc chatbot đang theo: không gọi chị Thơm là bác sĩ, không hứa chữa bệnh, không dùng từ thúc giục. Repo học viện không có quyết định nào mới về cách chatbot xưng hô.

## Tôi đã đọc và chạy gì?

Tôi đọc toàn bộ ba tài liệu chính của repo học viện: `docs/thomhouse-academy-daily-brief.md`, `docs/owner-decisions-2026-11-08.md` và `docs/thomhouse-deep-dive.md`. Tôi đọc `kit/claims.mjs`, `data/voices.json`, `data/say.json`, phần cuối `script.json` của sáu video và `render.json` của video 1. Tôi grep `research/raw/*.md`, `docs/style-catalog.md` và các file video để tìm tên dịch vụ, giá và địa chỉ.

Tôi trích chữ của trang landing page bằng một script Python dùng `html.parser`, bỏ phần script, style và svg, được 874 dòng chữ, rồi đọc hết. Tôi xem bộ ảnh menu in bằng mắt qua ảnh ghép dựng bằng ffmpeg. Trong ảnh ghép, mỗi trang còn khoảng 320 px chiều ngang; riêng ba trang triệt lông còn 700 px. Tôi xem cả 57 trang. Với trang 14 menu khỏe và trang 3 menu triệt lông, tôi cắt vùng chữ ở độ phân giải gốc để đọc lại. Giá ghi trong báo cáo là giá tôi đọc bằng mắt; tôi chưa chạy công cụ nhận dạng chữ.

Tôi đọc transcript bằng script `python3 -I`, mỗi dòng là một bản ghi JSON, không mở cả file. Transcript của phiên dựng video học viện là `~/.claude/projects/-Users-luuphuc-Projects-thomhouse-academy-daily/c6b74335-d810-4ccc-add6-fbdbdc9c87fa.jsonl`. Lúc 19:12, file dài 24.401.969 byte và 1.924 dòng, có một session id duy nhất và mang đúng tiêu đề của phiên dựng video học viện. Transcript có 165 lệnh Bash, 23 lệnh Read, 9 agent, 6 lệnh Write, 3 lệnh trình duyệt và 5 tin nhắn của anh. Vì phiên vẫn chạy, các con số này sẽ còn tăng. Phiên mở phiên này trong app có mã `local_0fa1d364`; tôi xác nhận mã đó thuộc transcript `af322bac-...` của soraflow, vì mã xuất hiện trong kết quả mở trình duyệt của transcript này. Với soraflow, tôi chỉ trích lời anh từ 07/11, các lệnh mở phiên, đổi tên phiên và gửi tin cho phiên khác, rồi grep script workflow `thomhouse-deep-dive-and-style-catalog-wf_7efb82f1-74c.js`. Tôi đọc hai transcript của thư mục analytics cũ và tách bản HTML cuối của phiếu thiết kế ngày 09/09 ra thư mục nháp để đọc chữ.

Tôi chạy `diff -rq` giữa `sources/drive/` của dự án và `source/#1-thomhouse-overview/` của repo học viện, và `cmp` giữa hai file `AGENTS.md`. Tôi liệt kê `~/.claude/scheduled-tasks/` và grep chữ "thom" và "aura" trong đó. Tôi đọc `services.json` và `business-facts.json` bằng script để lập bảng so sánh.

Tôi không mở link Google Maps, link beacons hay artifact trên claude.ai, vì nhiệm vụ cấm truy cập mạng. Tôi không nghe file ghi âm và không xem 12 ảnh không gian studio. Thư mục `~/Documents/ChatGPT/lulu-thomhouse` cũng chứa tài liệu thom house, nhưng đó là đợt nghiên cứu chatbot trước đã được tóm trong `research/00-prior-report-claims.md`, nên tôi chỉ liệt kê file mà không đọc lại.

## Còn những câu hỏi nào phải hỏi chủ doanh nghiệp?

1. Menu đang bán là bản nào, theo từng nhóm: ảnh menu in, trang landing page hay kho kiến thức tháng 5.
2. Giải mỏi đứng lâu giá 599.000đ hay 250.000đ, 60 hay 45 phút; quy trình đúng là quy trình vai cổ hay quy trình chân.
3. Menu phụ nữ hiện có những dịch vụ nào; Tiêu u – Thông kinh ngực còn bán không.
4. Combo triệt lông 20 buổi còn bán không, vì trang landing page không ghi.
5. Điều kiện của 4 hạng thẻ thành viên, và mức 10.000.000đ thuộc hạng nào.
6. Giờ đóng cửa, ngày nghỉ, số hotline, Zalo và URL Fanpage.
7. Mốc sau sinh là 2–3 tháng hay 6 tháng.
8. Chatbot có được báo giá Lăn dưỡng, Inner Fill, Bio PDRN và triệt lông không.

## Nói ngắn gọn nhất

Ngoài dự án này, chỉ repo học viện và các nguồn mà repo đó gom về là có ích cho chatbot. Repo analytics trống. Ở thư mục analytics cũ, thứ duy nhất liên quan tới khách là mẫu phiếu sức khỏe chưa điền. Ảnh menu in và trang landing page cho thấy `services.json` đang theo menu da cũ 5 dịch vụ trong khi tiệm bán 9, và thiếu cả nhóm triệt lông, dịch vụ cộng thêm, peel da đầu, mặt nạ và thẻ thành viên. Hai nguồn mới cũng không khớp nhau hoàn toàn: trang landing page ghi Giải mỏi đứng lâu 250.000đ, còn ảnh menu in và kho kiến thức ghi 599.000đ; menu phụ nữ thì chỉ trang landing page có. Vì vậy, bước tiếp theo nên là dựng lại `services.json` từ ảnh menu in, đánh dấu các mục chỉ có trên trang landing page là chưa xác nhận, rồi mang tám câu hỏi ở trên tới chủ doanh nghiệp trước khi chatbot báo các giá mới.

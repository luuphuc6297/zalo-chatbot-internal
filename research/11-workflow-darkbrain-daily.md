# Quy trình của phiên darkbrain-daily: Dark Brain làm video tin AI mỗi ngày như thế nào

Ngày viết: 2026-11-08. Người đọc chính: anh, trước khi chọn phần nào của cách làm Dark Brain đem sang thom house.

## Phần anh cần duyệt

Phiên darkbrain-daily là một phiên Claude chạy lâu trong app Claude desktop. Phiên này biến tin AI trong ngày thành video dọc tiếng Việt cho thương hiệu Dark Brain Studio. Phần việc nặng nằm trong một Workflow script, tức một file script mà tool Workflow của Claude Code chạy để gọi nhiều agent con (mỗi agent con là một tiến trình Claude riêng làm một việc): một agent chọn tin và thu giọng, hai agent vẽ storyboard, một agent chấm, một agent dựng, ba agent kiểm độc lập, rồi agent sửa và agent xuất file. Hai lịch tự chạy của app (scheduled task) bọc quanh Workflow script đó. Lịch thứ nhất làm 2 video vào mỗi lượt 06:00 và 21:00. Lịch thứ hai chạy mỗi 10 phút để xử lý nút anh bấm trên trang artifact `Dark Brain duyệt video` (artifact là một trang web riêng tư trên claude.ai).

Nút Duyệt và nút Đã đăng nằm trên trang artifact đó. Khi anh bấm, trang ghi một yêu cầu có trạng thái `pending` vào kho dữ liệu của artifact. Trong vòng 10 phút, lịch xử lý nút mở một phiên Claude mới, chạy script chép file, ghi trạng thái mới về kho và đăng lại trang. Các phiên ngắn tên "Dark Brain: xử lý nút Duyệt / Đã đăng" chính là các lần chạy của lịch này. Tôi đếm được 213 phiên như vậy từ 06/11 đến 08/11, nhiều hơn con số khoảng 50 nêu trong yêu cầu.

Tôi đo được bốn điểm anh nên biết trước khi dùng lại cách làm này. Thứ nhất, lịch 06:00/21:00 chỉ tự làm ra đúng 1 video trước khi bị tắt ngày 07/11; phần lớn video còn lại do phiên darkbrain-daily chạy cùng Workflow script khi anh nhắn. Thứ hai, trong 213 lần chạy của lịch xử lý nút, chỉ 16 lần có nút để xử lý, và 64 lần kết thúc bằng thông báo hết hạn mức tuần. Thứ ba, nút Đã đăng chưa lần nào tải được video lên Google Drive, vì máy chưa cài Google Drive for desktop. Thứ tư, khi app chuyển sang tài khoản claude.ai khác, trang artifact cũ và hai lịch cũ biến mất khỏi tài khoản mới, nên phiên phải tạo trang mới ở link mới.

Tôi đề xuất đem sang thom house bốn cách làm của Dark Brain: xuất bản nháp ra máy trước rồi người duyệt sau, một bộ luật viết thành file kèm ba lượt kiểm độc lập, một file lưu vòng luân phiên, và luật "mọi dữ kiện trên màn hình chỉ lấy từ file nguồn". Tôi không đề xuất chép hai cơ chế chạy của Dark Brain cho chatbot chăm sóc khách: dùng một phiên Claude mỗi 10 phút để xử lý nút bấm, và đặt trang bấm duyệt hay lịch chạy vào những thứ gắn với một tài khoản claude.ai (artifact, scheduled task). Không có quyết định nào anh phải đưa ra ngay; mục "Phần nào dùng lại được cho thom house" ghi đề xuất kèm điểm yếu.

## Tôi đã đọc và chạy những gì?

Tôi chỉ đọc. Trong repo Dark Brain tôi chạy các lệnh xem như `ls`, `cat`, `git log`, `git status`; tôi không chạy script nào của Dark Brain, không sửa file và không gửi tin cho phiên nào.

- Transcript phiên darkbrain-daily `~/.claude/projects/-Users-luuphuc-Projects-darkbrain-studio/e806b10d-8f29-4807-9268-8c33879988d9.jsonl` (51,6 MB, 9.359 dòng). Tôi không mở cả file. Tôi chạy các script `python3 -I` ngắn để đếm tool, lấy tin của người dùng, tin giữa các phiên, lời tóm tắt cuối mỗi lượt và các lời gọi tool lịch, Artifact, ArtifactData, SendMessage. Tiêu đề phiên ghi trong transcript là `darkbrain-daily`, trước đó là "Dark Brain Studio: 6 video tin AI theo design system", nên tôi xác nhận đây đúng là phiên được hỏi.
- 216 transcript còn lại trong cùng thư mục: tôi phân loại theo dòng `<scheduled-task name=...>` ở tin đầu, đếm chi phí, thời lượng, số lần chạy script xử lý nút và lời cuối. Tôi đọc chi tiết ba phiên: một lần xử lý nút Duyệt (`155afdb1`), lần chạy 21:00 bị kẹt (`859213cd`) và lần chạy 06:00 ngày 07/11 (`86380a99`).
- 48 file kết quả Workflow trong `e806b10d-.../workflows/` và tổng token của 847 transcript agent con.
- Bốn file `SKILL.md` trong `~/.claude/scheduled-tasks/darkbrain-*`.
- Trong repo `~/Projects/darkbrain-studio`: `README.md`, `package.json`, `.gitignore`, `.claude/workflows/darkbrain-daily-news.js`, `news-video/CLAUDE.md`, `news-video/README.md`, `news-video/formats/README.md`, và trong `news-video/formats/kit/`: `BRIEF.md`, `CHECK-LENSES.md`, `VERIFY.md`, `rotation.json`, `review-artifact.json`, `review-page.mjs`, `review-apply.mjs`, `credits.mjs`, một phần `voice.mjs` và `eleven.mjs`. Tôi chỉ liệt kê tên thư mục của `~/Downloads/darkbrain-studio-resources/daily/`, của thư mục video đã duyệt và đọc `cho-duyet.txt` ngày 08/11.
- Ghi chú bàn giao `darkbrain-news-videos-2026-11-04.md` trong thư mục ghi chú chung của nhóm phiên, và mục lục memory của dự án Dark Brain.

Thư mục `~/Projects/darkbrain-daily-news*` và `~/Projects/darkbrain-review-actions*` không tồn tại. Hai tên đó là tên thư mục lịch trong `~/.claude/scheduled-tasks/`.

## Thuật ngữ dùng trong báo cáo

| Thuật ngữ | Nghĩa trong báo cáo này |
|---|---|
| phiên darkbrain-daily | Phiên Claude có tiêu đề `darkbrain-daily`, transcript `e806b10d`, mở lúc 23:00 ngày 04/11 giờ Việt Nam, còn chạy lúc 18:53 ngày 08/11 |
| Workflow script | File `.claude/workflows/darkbrain-daily-news.js`. Tool Workflow của Claude Code chạy file này; script gọi nhiều agent con theo từng giai đoạn và chờ kết quả của chúng |
| agent con | Một tiến trình Claude riêng do Workflow script hoặc tool Agent khởi động để làm một việc rồi trả kết quả |
| lịch làm video | Scheduled task `darkbrain-daily-news` (sau là `darkbrain-daily-news-2`), cron `0 6,21 * * *` |
| lịch xử lý nút | Scheduled task `darkbrain-review-actions` (sau là `darkbrain-review-actions-2`), cron `*/10 6-23 * * *`, tức mỗi 10 phút từ 06:00 đến 23:50 |
| trang Dark Brain duyệt video | Trang artifact trên claude.ai có tiêu đề "Dark Brain duyệt video", do `kit/review-page.mjs` sinh ra. Link đầu là `JCzni21yygTnNx5w5aCMxE`, link hiện tại là `Lsc2J1prjz1qpb2X6uGHhA` |
| kho `actions` | Collection `actions` trong kho dữ liệu của trang artifact (capability `db`). Mỗi lần bấm nút tạo hoặc ghi đè một document |
| thư mục xuất | `~/Downloads/darkbrain-studio-resources/daily/<DD-MM-YYYY>/`, nơi video mới được chép ra để anh xem |
| thư mục video đã duyệt | `~/Projects/darkbrain-studio/drive/darkbrain-studio/daily/<DD-MM-YYYY>/`, thư mục trong repo (bị `.gitignore` bỏ qua) chứa bản chép của video đã bấm Duyệt |
| ba lượt kiểm | Ba agent con kiểm cùng một video theo ba góc: kỹ thuật (âm lượng, khớp file), thương hiệu (màu, chữ, khung an toàn), nội dung (dữ kiện, ghi nguồn, phụ đề). Mỗi agent trả PASS hoặc FAIL |
| HyperFrames | Bộ công cụ dựng video từ HTML và GSAP rồi render ra MP4 trên máy, bản 0.8.208 |
| ElevenLabs | Dịch vụ tạo giọng đọc và hiệu ứng âm thanh, tính phí theo credit; kit đọc key từ `~/.config/cartoon-studio/elevenlabs_api_key` |

Giờ trong báo cáo là giờ Việt Nam (UTC+7). Transcript ghi giờ UTC; tôi đã cộng 7 giờ.

## Dark Brain là gì, và phiên darkbrain-daily làm việc gì?

Dark Brain Studio là một studio nhỏ của anh. Repo `~/Projects/darkbrain-studio` chứa design system, landing page, một video thương hiệu và hai đường làm video tin. Đường cũ trong `news/` và `news-video/` dùng Gemini để dịch bài và vẽ minh hoạ, mỗi bài một video theo một khuôn cố định. Đường mới trong `news-video/formats/` là đường phiên darkbrain-daily xây và dùng hằng ngày: mỗi tin AI thành một video dọc 1080x1920 có một kiểu dựng riêng, lời đọc tiếng Việt bằng ElevenLabs, nhưng màu và font giữ đúng design system.

Phiên darkbrain-daily được phiên soraflow `local_0fa1d364` khởi động lúc 23:00 ngày 04/11. Việc ban đầu là làm 6 video tin AI. Sau bốn ngày, phiên đã chuyển thành dây chuyền làm video hằng ngày: phiên viết bộ luật dựng (`kit/BRIEF.md`), bộ luật kiểm (`kit/VERIFY.md`, `kit/CHECK-LENSES.md`), Workflow script, hai lịch tự chạy và trang Dark Brain duyệt video. Thư mục `news-video/out/` có 42 thư mục video đề ngày 02/11 đến 08/11. Thư mục xuất có 32 file MP4 (6 của 04/11, 5 của 05/11, 8 của 06/11, 8 của 07/11 và 5 của 08/11).

Anh điều khiển phiên darkbrain-daily qua ba đường. Đường thứ nhất là gõ tin thẳng vào phiên; sau khi bỏ tin trùng, tôi đếm được 78 tin anh gõ, phần lớn ngắn như "status", "Duyệt cả 3", "6 video ngay". Đường thứ hai là phiên soraflow chuyển lời anh sang bằng tin giữa các phiên. Đường thứ ba là bấm nút trên trang Dark Brain duyệt video. Phiên darkbrain-daily gửi bản xem trước cho anh bằng `SendUserFile` 26 lần.

## Một ngày của Dark Brain diễn ra thế nào khi mọi thứ chạy đúng thiết kế?

Theo các file `SKILL.md` và `review-artifact.json`, một ngày theo thiết kế gồm các mốc sau.

| Giờ | Ai làm | Việc |
|---|---|---|
| 06:00 | Lịch làm video mở một phiên Claude mới | Chạy Workflow script với `count: 2`, chép 2 video ra thư mục xuất, đăng lại trang Dark Brain duyệt video, báo anh |
| 06:00 đến 23:50, mỗi 10 phút | Lịch xử lý nút mở một phiên Claude mới | Đọc yêu cầu `pending` trong kho `actions`, chạy `kit/review-apply.mjs`, ghi kết quả, dựng lại trang và đăng lại nếu trang đổi |
| Bất kỳ lúc nào | Anh | Xem video ngay trong trang (bản nhẹ 540x960), bấm Duyệt hoặc Đã đăng |
| 21:00 | Lịch làm video mở một phiên Claude mới | Chạy Workflow script với `count: 2`, xuất 2 video, đăng lại trang và báo anh, giống lượt 06:00 |

Một lượt làm 2 video mất khoảng 78 phút và gọi 29 agent con. Tôi đo con số này ở lượt 21:00 ngày 06/11 được chạy bù (file kết quả Workflow `wf_7520f2f2`). Một lượt 1 video theo clip mẫu của anh mất 96 phút với 17 agent con.

Trên thực tế, lịch làm video gần như không chạy theo thiết kế. Lượt 21:00 đầu tiên ngày 06/11 đứng ngay lệnh đầu vì chờ xin quyền. Lượt 06:00 ngày 07/11 chạy được nhưng chỉ ra 1 video vì ổ đĩa đầy. Chiều 07/11 anh bảo dừng cả lịch, và phiên darkbrain-daily tắt lịch làm video lúc 16:57. Từ đó tới lúc tôi đọc, mọi video đều do phiên darkbrain-daily chạy Workflow script theo tin nhắn của anh.

## Mỗi lượt làm video đi qua những bước nào?

Workflow script chia một lượt thành sáu giai đoạn. Các video trong một lượt chạy song song qua các giai đoạn (hàm `pipeline`), nên video thứ nhất có thể đang được kiểm trong khi video thứ hai còn đang dựng.

| Giai đoạn | Ai làm | Đầu vào | Đầu ra |
|---|---|---|---|
| Chọn tin và thu giọng | 1 agent con | RSS và trang bài của The Verge, TechCrunch, Ars Technica, Wired, Engadget, ZDNET, VentureBeat, Reuters; `kit/rotation.json`; `kit/BRIEF.md`; số credit ElevenLabs | Mỗi tin một thư mục `formats/<slug>/` có `script.json` (7 đến 10 câu, hook, tiêu đề, dòng nguồn), file giọng đọc, kết quả đọc lại bằng speech-to-text; `rotation.json` được đẩy sang giọng và màu nền kế tiếp |
| Vẽ storyboard | 2 agent con cho mỗi video, mỗi agent một hướng (chắc tay nhất, vui nhất) | `script.json`, luật dựng | Hai storyboard dạng JSON |
| Chấm storyboard | 1 agent con cho mỗi video | Hai storyboard | `storyboard.md` gộp từ bản thắng và phần hay của bản kia |
| Dựng | 1 agent con cho mỗi video | `storyboard.md` | Logo, hiệu ứng âm thanh, bản trộn tiếng ở −16 LUFS, `index.html`, bản render MP4, `thumbnail.png` riêng, hai file mô tả |
| Kiểm và sửa | 3 agent con mỗi vòng kiểm; 1 agent con sửa khi có FAIL | MP4, thư mục truyện, `CHECK-LENSES.md` | PASS hoặc danh sách lỗi có thời điểm và vị trí |
| Xuất | 1 agent con cho mỗi video | MP4 và thumbnail trong `out/<slug>/` | File `NN-<kiểu dựng>-<slug>.mp4` trong thư mục xuất, một dòng mới trong `cho-duyet.txt` ghi "Chờ anh duyệt; chưa lên Drive." |

Bước chọn tin có ba luật cứng. Tin phải đăng đúng ngày Việt Nam của lượt chạy; luật này được siết lại ngày 08/11 sau khi agent lấy tin tối 07/11 cho lượt ngày 08/11. Tin không được trùng với thư mục nào đã có trong `formats/`, `out/` hoặc `news/`. Nếu không đủ tin tốt hoặc credit dưới khoảng 2.500 cho mỗi video, lượt chạy làm ít video hơn và ghi lý do.

Giọng đọc dùng model `eleven_v4` của ElevenLabs. Model này bỏ qua tham số tốc độ, nên `kit/voice.mjs` tăng tốc bản thu lên 1,3 lần bằng ffmpeg `atempo` và chia mốc thời gian của từng chữ cho 1,3 để phụ đề vẫn khớp. Sau khi thu, `kit/verify.mjs` cho speech-to-text nghe lại; nếu máy nghe sai tên hoặc số, agent thêm cách đọc hoặc viết lại câu, tối đa hai lần mỗi câu. Vòng luân phiên hiện có hai giọng: Lam Vy (cũng là giọng "Trúc" trong dự án Kai) và Nhật Phong. Màu nền luân phiên qua 11 màu của design system và một ô `new`; khi tới ô `new`, agent tự tạo một màu cùng họ theo luật OKLCH ghi trong `rotation.json`.

Vòng kiểm và sửa theo code chạy tối đa ba vòng kiểm và hai lần sửa. Sau vòng kiểm thứ ba, video vẫn được xuất dù còn FAIL, và tên file mang đuôi `-chua-dat-kiem`. File `SKILL.md` của lịch ghi "up to three fix rounds", nhưng vòng lặp trong Workflow script chỉ gọi agent sửa sau vòng kiểm 1 và vòng kiểm 2. Tỉ lệ trượt ở vòng đầu cao: ở lượt 21:00 ngày 06/11, cả hai video đều trượt vòng 1; trong lượt thử 6 kiểu dựng mới ngày 07/11, 2 trên 6 video vẫn trượt sau ba vòng; ngày 08/11, 2 trên 5 file đã xuất mang đuôi `-chua-dat-kiem`.

Sau khi Workflow script trả kết quả, chính phiên chạy lịch làm thêm ba việc: so từng file đã xuất với bản gốc bằng `cmp`, chạy `node kit/review-page.mjs` để dựng lại trang, và đăng trang lên đúng URL cũ bằng tool Artifact (đọc trang trước, rồi publish kèm danh sách file video nhẹ). Cuối cùng phiên báo anh nguồn tin, giọng, màu nền, kiểu dựng, kết quả kiểm và số credit còn lại.

## Nút Duyệt và nút Đã đăng nằm ở đâu, và trạng thái chạy ra sao?

Hai nút nằm trên từng thẻ video của trang Dark Brain duyệt video. Trang xếp thẻ theo bốn trạng thái: Chờ duyệt, Đang làm, Đã duyệt, Đã đăng. Script `kit/review-page.mjs` tính trạng thái từ file trên đĩa, không từ kho `actions`. Thẻ ở trạng thái Chờ duyệt khi video chỉ có trong thư mục xuất. Thẻ ở trạng thái Đã duyệt khi video đã có trong thư mục video đã duyệt. Thẻ ở trạng thái Đang làm khi `rotation.json` có lượt chạy cho truyện đó mà chưa có file xuất. Thẻ ở trạng thái Đã đăng khi video có trong `news-video/review/posted.json`.

Một lần bấm Duyệt đi qua các bước sau:

1. Anh bấm Duyệt trên thẻ Chờ duyệt. Code JavaScript trong trang ghi document `<ngày>_<tên file>` vào kho `actions` với `action: "approve"`, `status: "pending"`, ngày, tên file và giờ bấm. Nút bị khoá và dòng trạng thái hiện "Đã gửi lệnh duyệt, chờ máy xử lý".
2. Trong vòng 10 phút, lịch xử lý nút mở một phiên Claude mới. Phiên này gọi `ArtifactData` để lấy các document có `status == "pending"`.
3. Phiên chạy `node kit/review-apply.mjs '<danh sách yêu cầu>'`. Với Duyệt, script chép video và thumbnail từ thư mục xuất sang thư mục video đã duyệt, rồi so bằng `cmp`.
4. Phiên ghi kết quả về kho bằng một lệnh `batch`: `status` là `done`, `failed` hoặc `waiting-drive`, kèm ghi chú tiếng Việt và giờ xong. Lệnh ghi có `if_version` để không đè lên một lần bấm mới hơn.
5. Phiên chạy `kit/review-page.mjs`. Nếu nội dung trang đổi (so mã băm với `published-hash.txt`), phiên đọc lại trang rồi đăng bản mới, sau đó chép `current-hash.txt` sang `published-hash.txt`.
6. Trang đang mở trên máy anh nghe thay đổi của kho `actions` (`onSnapshot`) và hiện "Đã duyệt"; lần đăng lại sau đó chuyển thẻ sang mục Đã duyệt.

Nút Đã đăng chỉ có trên thẻ Đã duyệt và cần bấm hai lần trong 6 giây, vì lần bấm này xoá bản local. Theo code `review-apply.mjs`, script chép video vào thư mục `darkbrain-studio` trong Google Drive for desktop, so kích thước, rồi chuyển bản ở thư mục xuất và thư mục video đã duyệt vào Thùng rác của macOS. Script không dùng `rm`. Nếu máy không có Google Drive for desktop, script trả `waiting-drive` và giữ nguyên mọi file. Trên máy này, `~/Library/CloudStorage` không có thư mục Google Drive, `posted.json` có 0 mục, và mọi lần bấm Đã đăng tôi thấy trong transcript đều kết thúc ở `waiting-drive` (1 video ngày 06/11, rồi 13, 9 và 5 video trong các lần chạy ngày 07 và 08/11). Lịch xử lý nút chỉ đọc document `pending`, nên yêu cầu `waiting-drive` không tự chạy lại; anh phải bấm lại sau khi cài Google Drive for desktop.

Trước khi có trang này, phiên darkbrain-daily đưa video lên Drive bằng cách điều khiển Chrome. Ngày 04 và 05/11, phiên tải được 8 video lên thư mục Drive qua ô chọn file của trang drive.google.com. Hai connector Google Drive trong app không dùng được: một connector cần cấp thêm quyền, connector kia báo lỗi xác thực. Công cụ tải file qua Chrome giới hạn 10 MB, nên video lớn hơn phải chờ anh tự kéo vào. Ngày 06/11, Chrome đăng nhập một tài khoản Google khác không có thư mục này, nên anh chuyển sang cách "xuất ra máy trước, duyệt trên trang sau".

## 213 phiên ngắn "Dark Brain: xử lý nút Duyệt / Đã đăng" là gì?

Các phiên này là các lần chạy của lịch xử lý nút. Mỗi phiên mở đầu bằng thẻ `<scheduled-task name="darkbrain-review-actions">` hoặc `darkbrain-review-actions-2`, theo sau là nội dung `SKILL.md` của lịch. Tôi đếm theo thẻ đó trên toàn bộ thư mục transcript.

| Chỉ số | Số đo |
|---|---|
| Tổng số lần chạy | 213 (184 của lịch đầu từ 17:44 ngày 06/11 đến 16:34 ngày 08/11; 29 của lịch thứ hai từ 14:12 đến 18:52 ngày 08/11) |
| Lần chạy có nút để xử lý (có chạy `review-apply.mjs`) | 16 |
| Lần chạy có đăng lại trang | 49 |
| Lần chạy kết thúc bằng "You've hit your weekly limit · resets Nov 13 at 9am" | 64, từ 19:34 ngày 07/11 đến 16:34 ngày 08/11 |
| Chi phí quy đổi theo giá API mà app ghi cho cả 213 lần | 80,81 USD |
| Chi phí trung bình của 149 lần chạy bình thường | 0,54 USD mỗi lần |
| Thời gian chạy của 149 lần bình thường | trung vị 36 giây, 90% dưới khoảng 4,8 phút, lâu nhất khoảng 14 phút |

Số USD trên là chi phí quy đổi theo bảng giá API mà app ghi trong `cost-state`; trên gói thuê bao, con số này không bị tính tiền mà trừ vào hạn mức tuần. Các lần chạy bình thường dùng Bash, ToolSearch, ArtifactData và Artifact. Ngoài 64 lần hết hạn mức, lời cuối của phần lớn các lần chạy chỉ là một câu như "Không có yêu cầu nào đang chờ trên trang duyệt video".

## Phiên darkbrain-daily nói chuyện với những phiên nào?

Phiên darkbrain-daily trao đổi với bốn nhóm phiên khác. Tôi lấy danh sách từ các tin `cross-session-message`, tin nền lúc khởi động và các lời gọi `SendMessage`.

| Phiên | Hướng | Nội dung |
|---|---|---|
| Phiên soraflow `local_0fa1d364` | Gửi tới phiên darkbrain-daily lúc 23:00 ngày 04/11 | Tin nền khởi động: làm 6 video tin AI đúng design system, đọc pipeline cũ, dùng ElevenLabs, kiểm mỗi video bằng một agent con độc lập, không đọc `.env`, phải lấy báo giá trước khi dùng Google Flow |
| Phiên soraflow `local_3a3d3dce` | Gửi tới phiên darkbrain-daily 5 tin từ 08:58 đến 09:55 ngày 06/11; phiên darkbrain-daily trả lời 1 tin | Chuyển lời anh: chạy lại các việc còn dở sau khi tài khoản cũ chạm hạn mức tuần; thêm luật thumbnail, hook và headline; đổi thứ tự làm lại video cũ; chạy tiếp các agent bị dừng khi app tắt |
| Phiên "Kiểm tra giải phóng bộ nhớ" `local_b96c65ee` | Gửi tới phiên darkbrain-daily lúc 11:22 ngày 05/11; phiên darkbrain-daily trả lời lúc 11:23 | Ổ còn 7,8 GB; các thư mục kiểm của phiên darkbrain-daily chiếm khoảng 17 GB. Phiên darkbrain-daily dọn và báo đã lấy lại 13,96 GB |
| Agent con của chính phiên darkbrain-daily | Phiên darkbrain-daily gửi 14 tin | Giao lỗi cần sửa, nhắc chạy tiếp sau khi app tắt, làm rõ luật hook phải bắt đầu ở khoảng 0,3 giây |

Phiên darkbrain-daily không gửi và không nhận tin nào từ aura-coach-daily hay thomhouse-academy-daily. Hai phiên này chỉ xuất hiện trong dòng trạng thái "Linked sessions now" mà app chèn vào phiên darkbrain-daily. aura-coach-daily có mặt từ 17:18 ngày 05/11 và mang ba id khác nhau theo thời gian; thomhouse-academy-daily có mặt từ 15:50 ngày 08/11 với trạng thái "working". Có hai liên hệ gián tiếp với Aura Coach. Anh dặn đặt thư mục xuất theo kiểu `aura-coach-resources` có sẵn trong Downloads. Ngày 07/11, phiên darkbrain-daily thấy máy đang render một video của Aura Coach cùng lúc với video Dark Brain và để nguyên.

Thư mục `~/Projects/thomhouse-academy-daily` có các thư mục `kit/`, `formats/`, `styles/`, `voice/`, `out/` giống cách tổ chức của Dark Brain. Tôi chỉ xem tên thư mục, chưa đọc nội dung. Vì vậy, nhận định "dự án này đang chép cách làm của Dark Brain" chỉ là suy luận từ tên thư mục.

## Bốn ngày của phiên darkbrain-daily diễn ra theo những giai đoạn nào?

| Thời điểm | Việc chính |
|---|---|
| 04/11, 23:00 đến 03:35 sáng 05/11 | Làm 8 video đầu (6 video theo đề bài, thêm video Vox cắt dán và video tranh giấy Dreambeans). Viết `BRIEF.md`, `VERIFY.md`, bộ kit dựng. Tải 5 video lên Drive qua Chrome |
| 05/11 | Anh đòi tin mới đúng ngày, mỗi video một tin, luân phiên giọng và màu nền, thêm logo công ty. Phiên làm thêm các video ngày 05/11, thử nhạc khớp hình của ElevenLabs sau khi anh duyệt báo giá. 21:55: tài khoản cũ chạm hạn mức tuần |
| 06/11 sáng | Phiên chạy tiếp ở tài khoản khác theo tin của phiên soraflow. Thêm luật thumbnail, hook và headline; giọng mặc định 1,3 lần. Làm 5 video ngày 06/11 |
| 06/11, 15:40 đến 17:36 | Anh yêu cầu lịch 21:00 và 06:00, xuất ra máy trước, rồi một trang để duyệt, rồi nút Duyệt và Đã đăng. Phiên tạo lịch làm video, trang Dark Brain duyệt video và lịch xử lý nút |
| 06/11 tối đến 07/11 sáng | Lượt 21:00 kẹt; phiên tạo lại lịch ở chế độ Auto và chạy bù trong phiên darkbrain-daily. Lượt 06:00 tự chạy, ra 1 video |
| 07/11 | Nghiên cứu 14 kiểu dựng mới từ clip mẫu, thêm vào vòng luân phiên, chạy lượt thử 6 kiểu. 16:56 dừng theo lời anh; 16:57 tắt lịch làm video |
| 08/11 | Phiên mở lại dưới một tài khoản claude.ai khác. Làm lại trang ở link mới, tạo lại lịch xử lý nút, làm 5 video ngày 08/11 và 4 video thử kiểu dựng mới; lúc 18:41 vẫn còn 4 video đang kiểm hoặc sửa |

Workflow script dạng hằng ngày chỉ được lưu vào repo từ 06/11. Trước đó, phiên darkbrain-daily viết mỗi đợt một Workflow script riêng (22 script trong `e806b10d-.../workflows/scripts/`). Thư mục kết quả có 48 lần chạy Workflow đã kết thúc, gọi tổng cộng 650 agent con, cộng dồn khoảng 37,8 giờ chạy; 8 lần bị dừng giữa chừng. Các lượt còn chạy chiều 08/11 chưa có file kết quả nên chưa nằm trong các số này.

## Những lỗi nào đã xảy ra, và mỗi lỗi để lại dấu vết gì?

Lỗi đầu tiên là lịch chạy khi không ai ngồi trước máy nhưng vẫn chờ xin quyền. Lịch làm video tạo lúc 15:44 ngày 06/11 không được lưu ở chế độ Auto. Theo thông báo của tool tạo lịch, lý do là lượt đó không chỉ do tin anh gõ khởi động, hoặc còn agent nền đang chạy. Lúc 21:00, phiên của lịch đứng ngay lệnh Bash đầu tiên để chờ duyệt quyền. Hai phiên khác của cùng lịch mở lúc 23:26 và 23:27, cả hai cũng đứng; tôi không rõ hai phiên này do app hay do anh bấm chạy. Anh phát hiện lúc 23:27 và hỏi vì sao lịch không tự chạy. Phiên darkbrain-daily dừng ba phiên đó, xoá lịch, tạo lại ở chế độ Auto với tên `darkbrain-daily-news-2` (tên cũ còn thư mục trên đĩa nên không dùng lại được) và chạy bù trong chính phiên darkbrain-daily. Lần tạo lịch xử lý nút đầu tiên lúc 16:16 bị bộ phân loại an toàn của chế độ Auto chặn; lịch chỉ được tạo lúc 17:36 sau khi anh nhắn "Cho phép tự chạy". Lệnh `run_scheduled_task` để chạy thử ngay cũng bị chặn.

Lỗi thứ hai là hạn mức tuần của gói Claude. Tài khoản đầu chạm hạn mức lúc 21:55 ngày 05/11, hẹn cấp lại 14:00 ngày 11/11; các agent nền bị cắt giữa chừng. Tài khoản thứ hai chạm hạn mức khoảng 19:34 ngày 07/11, hẹn cấp lại 09:00 ngày 13/11. Từ lúc đó, lịch xử lý nút đầu tiên vẫn chạy mỗi 10 phút và thất bại 64 lần liên tiếp, không báo ai.

Lỗi thứ ba là artifact và scheduled task gắn với tài khoản claude.ai. Chiều 08/11 phiên darkbrain-daily mở lại dưới một tài khoản khác. Lệnh mở trang cũ trả "No Artifact ... that the user can see", danh sách artifact rỗng, danh sách lịch rỗng. Phiên phải đăng trang ở link mới `Lsc2J1prjz1qpb2X6uGHhA`, sửa `review-artifact.json` và tạo lịch `darkbrain-review-actions-2`. Trong khoảng 14:12 đến 16:34 ngày 08/11, cả lịch cũ (đang thất bại vì hạn mức) và lịch mới cùng chạy cho hai trang khác nhau. Các lần bấm trên trang cũ ngày 07/11 vẫn được giữ, vì trạng thái Đã duyệt nằm ở thư mục trên đĩa chứ không nằm trong kho `actions`. Kho `actions` của trang mới bắt đầu rỗng.

Lỗi thứ tư là ổ đĩa nhỏ. Ổ 460 GB nhưng thường chỉ còn 13 đến 27 GB trống. Mỗi video để lại 2,3 đến 5 GB file kiểm (wav tách lớp, khung hình, bản sao video). Ngày 05/11, phiên dọn ổ đo được khoảng 17 GB thư mục kiểm của phiên darkbrain-daily. Lượt 06:00 ngày 07/11 chỉ render được 1 video vì ổ còn khoảng 2,6 GB, dưới ngưỡng 5 GB mà luật dựng đặt ra. Sau đó luật dựng và luật kiểm bắt agent chạy `df -h /` trước mỗi lần render và xoá file nặng trước khi trả kết quả.

Lỗi thứ năm là hai bên cùng đăng một trang. Phiên darkbrain-daily và lịch xử lý nút cùng đăng lại trang Dark Brain duyệt video. Tôi đếm 5 lần đăng của phiên darkbrain-daily bị từ chối vì trang đã có bản mới hơn, và một lần lịch làm video bị từ chối vì file video trên trang khác bản phiên đã đọc. Mỗi lần, phiên phải đọc lại trang rồi đăng lần nữa.

Lỗi thứ sáu là duyệt một video chưa đạt kiểm. Ngày 07/11 anh bấm Duyệt video Artex khi file còn đuôi `-chua-dat-kiem`. Script chép đúng file đó vào thư mục video đã duyệt. Sau khi video được sửa và đạt, thư mục có cả bản cũ lẫn bản mới, nên hiện có 9 file MP4 cho 8 video của ngày 07/11. Trang có nhãn "Chưa đạt kiểm" trên thẻ nhưng không chặn nút Duyệt.

Lỗi thứ bảy là hiểu sai yêu cầu của anh. Ngày 05/11 phiên dùng lại tin ngày 03/11 khi anh bảo lấy tin mới. Ngày 06/11 phiên bắt đầu render lại video cũ trong khi anh chỉ muốn thumbnail, hook và headline cho video mới. Ngày 08/11 lượt chạy lấy ba tin tối 07/11 cho video ngày 08/11. Cả ba lần anh phản ứng rất gay gắt; sau mỗi lần, phiên ghi luật mới vào `BRIEF.md`, luật kiểm và memory.

Lỗi thứ tám là khoá bí mật đi qua chat. Lúc 21:30 ngày 05/11, một API key Anthropic được dán thẳng vào phiên darkbrain-daily để dùng khi chạm hạn mức. Phiên không dùng key và không ghi key ra file; ngày 07/11 phiên khuyên thu hồi key. Key vẫn nằm trong file transcript trên đĩa. Tôi không chép key vào báo cáo này và không biết key đã được thu hồi hay chưa.

Ngoài tám lỗi trên còn bốn dấu vết nhỏ hơn. Phiên darkbrain-daily hết context ba lần và phải tóm tắt để chạy tiếp. Khi app bị tắt, các lần chạy Workflow và agent nền bị dừng; ngày 06/11 phiên phải nhắn từng agent con chạy lại, ngày 08/11 phiên cho lượt thử 6 kiểu chạy lại từ bước đang dở và giữ nguyên 5 video đã xong. Speech-to-text nghe sai tên riêng (Vals thành "Valves", Indge thành "Inger") và agent không phân biệt được lỗi do giọng đọc hay do máy nghe. Theo code `review-page.mjs`, khung "Lịch tự làm video" trên trang lấy giờ từ `review-artifact.json` chứ không hỏi lịch có đang bật không, nên trang vẫn hiện lượt 06:00 và 21:00 sắp tới dù lịch đã tắt; tôi chỉ đọc code, chưa mở trang để thấy tận mắt.

## Tốn bao nhiêu, và chạm giới hạn nào?

Phần Claude là phần tốn nhất. App ghi cho phiên darkbrain-daily chi phí quy đổi theo giá API 772,09 USD, với 9,36 triệu token output, 1,47 tỷ token đọc từ cache và 55,4 triệu token ghi cache. 847 transcript agent con cộng lại có 22,0 triệu token output, 3,10 tỷ token đọc từ cache và 130 triệu token ghi cache. Token của agent con lớn hơn số token trong `cost-state` của phiên darkbrain-daily, nên tôi suy luận con số 772 USD chưa gồm agent con. Token output của agent con gấp khoảng 2,3 lần và token đọc cache gấp khoảng 2,1 lần của phiên darkbrain-daily. Vì vậy, nếu tính theo cùng đơn giá, phần agent con quy đổi thêm khoảng gấp đôi 772 USD; đây là ước tính, tôi chưa tính theo bảng giá. Mọi chi phí này trừ vào hạn mức tuần của gói thuê bao, và hai tài khoản đã chạm hạn mức trong bốn ngày.

Phần ElevenLabs tính theo credit tháng. Gói hiện có 57.035 credit mỗi tháng, cấp lại ngày 29/11. Lúc phiên bắt đầu, tin nền ghi còn khoảng 49.600 credit. Sau lượt 21:00 ngày 06/11 còn 26.165; lúc 16:56 ngày 07/11 còn 17.911; lần đọc mới nhất trong transcript còn 13.914. `BRIEF.md` ước 1.500 đến 2.000 credit cho giọng và hiệu ứng của một video; trang Dark Brain duyệt video dùng mức 2.000 để tính số video còn làm được. Mỗi lần thử nhạc khớp hình tốn khoảng 1.000 credit (987 và 1.097 credit trong hai lần đo).

Phần máy gồm ổ đĩa và sức render. Luật dựng bắt mỗi lần render dùng `HF_WORKERS=2` vì nhiều video render cùng lúc; tôi chưa đo mức dùng CPU. Ổ đĩa là giới hạn đã làm hỏng một lượt chạy, như mục lỗi thứ tư.

## Phần nào dùng lại được cho thom house?

Tôi chia theo hai việc của thom house: làm nội dung quảng bá, và chatbot chăm sóc khách trên Zalo cá nhân.

### Cho nội dung quảng bá

Đề xuất thứ nhất là dùng lại khung "luật viết thành file, ba lượt kiểm độc lập, sửa tối đa vài vòng, xuất kèm nhãn chưa đạt". Với thom house, ba góc kiểm nên đổi thành: kỹ thuật (kích thước, âm lượng nếu là video), thương hiệu (màu, font, cách xưng hô đã chốt), và nội dung. Góc nội dung cần thêm danh sách câu y tế bị cấm và câu thay thế ở mục E của `research/01-knowledge-audit.md`. Luật "mọi dữ kiện trên màn hình chỉ lấy từ `script.json`" của Dark Brain đổi thành "mọi giá, thời lượng, bước làm chỉ lấy từ `data/services.json` và `data/business-facts.json`". Điểm yếu: ba lượt kiểm tốn nhiều agent con, và tỉ lệ trượt vòng đầu của Dark Brain cao, nên mỗi bài sẽ tốn hạn mức Claude gấp nhiều lần so với một lần viết.

Đề xuất thứ hai là dùng lại cách "xuất ra máy trước, người duyệt sau, chỉ đăng khi có nút bấm". Bản nháp vào một thư mục theo ngày kèm file liệt kê (như `cho-duyet.txt`), và không có bước nào tự đăng lên Zalo hay Facebook. Điểm yếu: cách này cần người duyệt đều đặn; ở Dark Brain, nút Đã đăng vẫn chưa hoàn tất lần nào vì thiếu một phần mềm trên máy, tức là khâu cuối dễ bị bỏ dở mà không ai thấy.

Đề xuất thứ ba là dùng lại file lưu vòng luân phiên như `rotation.json`: ghi lượt kế tiếp và lịch sử để hai bài liền nhau không trùng dịch vụ, màu nền hay giọng đọc. Lịch sử có trường `run` còn dùng để chặn hai lượt chạy cùng một khung giờ. Điểm yếu: agent đọc và ghi file này, nên khi hai lượt chạy song song vẫn có thể ghi đè nhau; Dark Brain chưa có khoá cho file này.

Nếu thom house làm video ngắn, bộ kit HyperFrames, giọng tiếng Việt ElevenLabs tăng tốc 1,3 lần và bước nghe lại bằng speech-to-text dùng lại được gần như nguyên vẹn. Bước nghe lại đặc biệt có ích cho tên dịch vụ như "Diện chẩn". Điểm yếu: một video tốn khoảng 1.500 đến 2.000 credit ElevenLabs và khoảng 15 đến 17 agent con (đo ở hai lượt chạy), và ổ đĩa phải còn trên 5 GB.

### Cho chatbot chăm sóc khách

Nguyên tắc dùng lại được là cách mô tả một yêu cầu cần người duyệt. Mỗi yêu cầu có id cố định, trạng thái rõ (`pending`, `done`, `failed`, `waiting-<lý do>`), ghi chú cho người đọc và giờ xong. Lệnh ghi kèm số phiên bản để không đè lên thao tác mới hơn. Thao tác không đảo ngược được phải bấm hai lần, và hệ thống chuyển file vào Thùng rác thay vì xoá hẳn. `apps/console` và `apps/server` của thom house có thể áp đúng các nguyên tắc này cho nút duyệt câu trả lời nháp.

Cơ chế không nên dùng lại là để một phiên Claude chạy mỗi 10 phút chỉ để xử lý nút bấm. Ở Dark Brain, cơ chế này làm khách phải chờ tới 10 phút cộng thời gian mở phiên, tốn trung bình 0,54 USD quy đổi mỗi lần dù chỉ 16 trên 213 lần có nút để xử lý, và thất bại im lặng 64 lần khi hết hạn mức. Với thom house, server và console xử lý nút bằng code thường, còn runner chỉ gọi `claude -p` khi có tin khách cần soạn trả lời.

Dark Brain còn cho ba bài học về vận hành mà runner của thom house nên kiểm lại. Bài học đầu: mọi thứ gắn với một tài khoản claude.ai (artifact, scheduled task) mất khi đổi tài khoản; thiết kế hiện tại của thom house chạy console và server trên máy, nên không phụ thuộc vào artifact, và nên giữ như vậy. Bài học thứ hai: một lịch chạy khi không ai nhìn có thể đứng chờ xin quyền hoặc lặp lại lỗi hạn mức mà không báo; runner nên hiện trạng thái `limited` hay `no_account` lên console và ngừng nhận việc, như README của `apps/runner` mô tả. Tôi chưa kiểm cờ quyền mà runner truyền cho `claude -p`, nên chưa xác nhận được runner sẽ không dừng lại chờ duyệt quyền. Bài học thứ ba: file tạm trên đĩa tích lũy nhanh; runner đã có lệnh `forget` và cơ chế cũ hoá session, nhưng chưa ai đo dung lượng thư mục session khi chạy thật.

Cách nhận lệnh qua tin giữa các phiên (phiên soraflow chuyển lời anh) cũng không nên dùng cho chatbot. Cách này hợp với một người chủ ra lệnh cho nhiều phiên, nhưng không có lịch sử duyệt rõ ràng và không ai ngoài anh kiểm được.

## Những gì tôi chưa xác minh

Tôi chưa mở trang Dark Brain duyệt video trong trình duyệt và chưa đọc kho `actions` của trang hiện tại; mọi mô tả về giao diện đến từ code `review-page.mjs` và lời tóm tắt trong transcript. Tôi chưa đọc `DESIGN-VIDEO.vi.md`, `SPEC.md`, các file kiểu dựng trong `kit/styles/` và code dựng video. Tôi không biết lịch xử lý nút đầu tiên (tài khoản cũ) còn chạy sau 16:34 ngày 08/11 hay không; tôi chỉ thấy không có transcript nào của lịch đó sau mốc ấy. Tôi không biết vì sao số credit ElevenLabs trên tài khoản và số credit ghi trong `credits.json` của từng video lệch nhau; chính agent chọn tin cũng ghi là chưa kiểm. Con số chi phí Claude của agent con chỉ là ước tính, như đã nói ở mục chi phí. Tôi chưa đọc nội dung dự án `thomhouse-academy-daily`.

## Nói ngắn gọn nhất

Dark Brain là một dây chuyền làm video tin AI chạy bằng một phiên Claude lâu dài, một Workflow script gọi từ 17 đến 85 agent con cho mỗi lượt, và hai lịch tự chạy của app. Anh duyệt bằng nút trên một trang artifact; mỗi lần bấm được một phiên Claude khác xử lý trong vòng 10 phút. Dây chuyền làm ra video đạt ba lượt kiểm sau nhiều vòng sửa, nhưng tự chạy kém: lịch làm video chỉ tự ra 1 video, lịch xử lý nút phần lớn chạy không có việc, nút Đã đăng chưa xong lần nào, và đổi tài khoản là mất trang và lịch. Thom house nên lấy cách làm (luật thành file, ba lượt kiểm, xuất trước rồi người duyệt, trạng thái rõ cho từng yêu cầu, dữ kiện chỉ từ file nguồn) và để phần xử lý nút bấm cho code thường trong server và console của mình, không giao cho một phiên Claude chạy theo lịch.

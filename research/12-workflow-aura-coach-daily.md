# Phiên aura-coach-daily làm video thế nào, và thom house dùng lại được phần nào

Ngày viết: 08/11/2026. Phạm vi: phiên Claude tên `aura-coach-daily`, thư mục làm việc `~/Projects/aura-coach-studio`, tạo ngày 05/11/2026. Tôi chỉ đọc. Tôi không chạy lệnh nào của studio Aura, không gọi ElevenLabs, không mở trang web mà phiên dùng để anh duyệt video, và không sửa file nào ngoài báo cáo này. Giờ trong báo cáo là giờ Việt Nam.

## Phần anh cần duyệt

Phiên `aura-coach-daily` là một phiên Claude Code trên Claude Desktop, chuyên dựng video dọc ngắn dạy tiếng Anh cho app Aura Coach. Tên phiên có chữ daily nhưng phiên không có lịch chạy. Tôi không tìm thấy scheduled task, crontab hay LaunchAgent nào cho Aura, và transcript không có lượt nào do lịch kích hoạt. Mỗi đợt video bắt đầu khi anh nhắn trong phiên, hoặc khi phiên soraflow (phiên đã khởi động phiên này) chuyển lời anh sang. Từ 05/11 đến 08/11, phiên đã xuất 33 video vào `~/Downloads/aura-coach-resources/daily/`, mỗi video gồm một bản xem trước MP4 và một ảnh thumbnail.

Phiên làm việc theo ba lớp. Lớp thứ nhất do chính phiên làm: chọn topic và các giá trị khác theo vòng luân phiên, viết kịch bản, thu giọng bằng ElevenLabs. Lớp thứ hai là các agent chạy song song qua công cụ Workflow (công cụ chạy nhiều agent theo một script): mỗi agent dựng hình, trộn âm và render một video. Lớp thứ ba là anh: anh xem bản xem trước gửi trong chat, rồi bấm nút "Duyệt" hoặc "Đã đăng" trên một trang web claude.ai mà phiên lập ra. Trong báo cáo này tôi gọi trang đó là trang web duyệt video. Bước đưa video lên Google Drive sau khi anh bấm "Đã đăng" chưa chạy lần nào: tới lần đọc cuối ngày 07/11, chưa video nào được bấm "Đã đăng", và máy chưa cài Google Drive for desktop.

Với thom house, tôi đề xuất dùng lại bốn phần:

1. Cách ghi trạng thái duyệt thành vài giá trị rõ ràng (chờ duyệt, đã duyệt, đã đăng), có nút hoàn tác và có kiểm phiên bản khi ghi. thom house nên giữ trạng thái này trong server và console của mình, không đặt trong trang claude.ai. Lý do: từ 08/11 phiên Aura chạy bằng một tài khoản claude.ai khác và không mở được trang web duyệt video nữa.
2. Cách ghi luật của chủ doanh nghiệp thành file nhớ, mỗi luật có ngày, lý do và cách áp. Danh sách "Never claim" của Aura (không nêu giá, không hứa tính năng) tương ứng với danh sách câu y tế bị cấm trong `research/01-knowledge-audit.md`.
3. Kiểm bản nháp theo từng góc riêng (dữ kiện, giọng, định dạng) trước khi gửi, nhưng chỉ một lượt kiểm tự động rồi đưa người duyệt. Aura từng giữ video lại qua tới ba vòng kiểm và sửa tự động; anh phản đối vì việc đó tốn thời gian và tốn credit.
4. Bộ công cụ dựng video của Aura, nếu sau này thom house muốn làm video ngắn giới thiệu dịch vụ: giọng Việt do người nghe rồi chọn, đọc lại bằng nhận dạng giọng nói, nhạc nền tổng hợp bằng code, quét chữ chồng nhau, thẻ thumbnail riêng.

Tôi đề xuất không dùng ba phần: workflow nhiều agent trong đường trả lời khách, đường tải file lên Drive qua Chrome (chỉ nhận file dưới 10 MB), và cách để nút anh bấm nằm chờ tới khi một phiên Claude đang mở đọc tới.

Có hai rủi ro chung máy và chung tài khoản mà anh nên biết trước khi bật bot. Thứ nhất, bot thom house chạy trên cùng chiếc Mac với các studio video. Lúc 18:31 ngày 08/11, phiên Aura đo được load average khoảng 520, với mười trình duyệt headless chiếm gần 3 core và Dark Brain đang chạy ffmpeg. Thứ hai, tôi suy luận rằng tài khoản Claude ưu tiên số 1 trong pool của bot có thể trùng với tài khoản mà phiên Aura đang dùng. Căn cứ: pool đăng ký tài khoản mặc định của máy dưới nhãn `ultra-anlnt` trong `~/.thomhouse-bot/accounts.json`, còn bản tóm tắt ngày 08/11 trong transcript Aura ghi phiên đang chạy bằng một tài khoản cùng tiền tố tên đó. Nếu suy luận đúng, một đợt dựng video lớn có thể làm tài khoản chạm giới hạn dùng hằng tuần. Ngày 05/11, phiên Aura đã chạm giới hạn này lúc khoảng 21:55 và dừng tới sáng hôm sau. Tôi chưa kiểm phiên Claude Desktop dùng đăng nhập nào, nên anh cần chạy `python3 scripts/runner/claude_pool.py status` và đối chiếu với tài khoản đang mở trong Claude Desktop.

Còn một việc an toàn. Ngày 05/11 lúc 21:30, anh dán một API key Claude vào phiên Aura. Phiên từ chối dùng khóa và khuyên anh thu hồi. Khóa đó vẫn nằm nguyên văn trong file transcript của phiên. Nếu anh chưa thu hồi khóa, anh nên thu hồi trong trang quản lý API key của Anthropic.

## Tôi đã đọc và chạy những gì

Tôi xác nhận transcript đúng của phiên bằng nội dung, không chỉ bằng tên file. File `~/.claude/projects/-Users-luuphuc-Projects-aura-coach-studio/3ed9851e-4788-44bc-a2bd-40f2523a8c6f.jsonl` dài 44 MB và 5.880 dòng. File `custom-title.json` cùng thư mục ghi tên `aura-coach-daily`. Mọi dòng có `cwd` đều nằm trong `~/Projects/aura-coach-studio`. Dòng đầu ghi lúc 14:17 ngày 05/11 và dòng cuối ghi lúc 18:32 ngày 08/11.

Tôi đọc transcript bằng các script `python3 -I` ngắn đặt trong scratchpad, không mở cả file. Các script đếm loại dòng và tên công cụ, lọc 41 tin nhắn do anh gõ (bỏ system-reminder và thông báo của agent), lọc 5 tin nhắn từ phiên khác, liệt kê mọi lệnh gọi Workflow, Agent, SendUserFile, Artifact và ArtifactData, rồi trích 91 đoạn trả lời dài của phiên. Tôi đọc toàn văn hai bản tóm tắt mà phiên tự viết khi hết ngữ cảnh (07/11 11:34 và 08/11 16:18).

Trong repo `~/Projects/aura-coach-studio`, tôi đọc `CLAUDE.md`, `AGENTS.md`, `docs/darkbrain-flow-notes.md`, phần đầu `docs/aura-coach-daily-brief.md`, `kit/BRIEF.md`, `kit/VERIFY.md`, `data/rotation.json`, `data/voices.json`, mẫu `data/review.json`, `tools/board_add.py`, `tools/board_docs.py` và phần script của `out/review-board.html`. Tôi đọc bảy file memory của phiên, các script workflow trong `3ed9851e-.../workflows/scripts/` (đọc kỹ `aura-fix-until-pass` và `aura-style-videos`), 17 file kết quả workflow `wf_*.json`, và ghi chú chung `side-session-notes/local_af322bac-.../aura-coach-daily-status.md`.

Tôi đã đo bằng lệnh: số file trong từng thư mục xuất (`ls`), tổng credit ElevenLabs ghi trong các file `credits.json` (script cộng trường `billed`), số file transcript agent trong từng thư mục workflow, và danh sách `~/.claude/scheduled-tasks/`. Để so sánh, tôi đọc phần đầu `~/.claude/scheduled-tasks/darkbrain-review-actions-2/SKILL.md`. Trong dự án thom house, tôi đọc `apps/runner/README.md`, phần đầu `scripts/runner/claude_pool.py` và chỉ nhãn tài khoản trong `~/.thomhouse-bot/accounts.json`.

Tôi chưa đọc 1,7 GB transcript của các agent con, chỉ đếm file. Tôi không đọc trực tiếp repo `~/Projects/aura-coach-ai`. Theo transcript, phiên Aura chỉ đọc repo đó bằng `git show origin/master:...` (dữ liệu ngữ pháp A1, A2, `topic_constants.dart`, `app_typography.dart`, `app_vi.arb`) và chép ảnh mascot từ `.work/exports/2026-10-29/icons/cloudinary/originals/`.

## Aura Coach là gì, và phiên làm ra sản phẩm gì

Aura Coach là app điện thoại giúp người Việt viết tiếng Anh tự nhiên. App có năm mode: Scenario Coach, Story Mode, Grammar Coach, Vocab Hub và Shadowing. App dùng hệ thiết kế chất liệu clay, có bốn giao diện (Farm, School, Space, Shape; ba giao diện đầu có bản ngày và đêm, Space chỉ có đêm), một quả cầu Aura làm mascot và một bộ avatar con vật. App có 16 topic, từ Du lịch tới Bất động sản.

Sản phẩm của phiên là video dọc 1080x1920, 30 khung hình mỗi giây, dài 40 đến 70 giây. Brief ban đầu có bốn loại video mỗi ngày: đoán từ, điền chỗ trống, phản xạ tình huống và Shadowing. Từ 06/11, anh đổi sang luân phiên sáu thứ cho mỗi video: topic, giọng tiếng Anh, trình độ, giao diện, kiểu dựng và tính năng của mode. Video dựng bằng HyperFrames 0.8.208, một công cụ dựng video từ HTML, CSS và timeline GSAP rồi chụp từng khung hình. Bộ máy dựng được chép từ studio Dark Brain, nơi phiên `darkbrain-daily` làm video tin tức AI mỗi ngày.

Đến 18:31 ngày 08/11, kết quả đo được là 33 video đã xuất (7 video thư mục 05/11, 4 video thư mục 06/11, 22 video thư mục 07/11). Thư mục `out/` có 35 bản xem trước; hai bản dư là hai video anh bỏ vì trùng. Danh sách kiểu dựng luân phiên trong `data/rotation.json` có 31 kiểu (2 kiểu bắt buộc mỗi bộ là giấy cắt và Vox, cộng 29 kiểu trong `free_pool`). Mười video kiểu mới đang tạm dừng theo lời anh. Video "Nature Clues" kiểu tranh tường vẫn đang dựng.

## Một đợt video bắt đầu thế nào

Phiên được phiên soraflow khởi động lúc 14:17 ngày 05/11. Tin nhắn đầu là một brief dài bằng tiếng Anh: chép bộ máy Dark Brain, đọc brief Aura trong `docs/`, làm bộ bốn video ngày đầu, và các luật về credit trả phí, Drive và thư mục không được ghi. Brief cũng chỉ một thư mục ghi chú chung cho nhóm phiên ở `~/Library/Application Support/Claude/side-session-notes/local_af322bac-.../`. Phiên ghi một file trạng thái vào đó lúc 14:38 ngày 05/11 rồi không cập nhật nữa.

Sau tin nhắn đầu, mọi đợt việc đến từ hai nguồn:

- Tin nhắn của anh. Tôi đếm được 41 tin nhắn do anh gõ. Tám tin trong số đó hỏi trạng thái ("status như nào rồi" và các biến thể). Nhiều tin kèm video mẫu `.MOV` trong `~/Downloads/` để chỉ kiểu dựng.
- Tin nhắn từ phiên soraflow: bốn tin, vào 14:39 ngày 05/11 (bốn điểm sửa brief), 08:58 ngày 06/11 (tiếp tục việc dở sau khi tài khoản cũ chạm giới hạn), 09:24 ngày 06/11 (luật hook, headline, thumbnail) và 09:55 ngày 06/11 (tiếp tục việc dở sau khi app bị tắt).

Thư mục `~/.claude/scheduled-tasks/` có bốn task của Dark Brain và năm task của elder-soul, không có task nào của Aura hay thom house. Trong transcript, các công cụ lập lịch chỉ xuất hiện trong danh sách công cụ, không có lệnh gọi nào.

## Một video đi qua những bước nào

Các bước dưới đây lấy từ mục "One video" trong `CLAUDE.md`, từ `kit/BRIEF.md` và từ các lệnh thật trong transcript. Bước 1 đến 4 thường do phiên tự làm. Bước 5 đến 11 do một agent dựng làm. Bước 12 đến 15 do phiên làm sau khi agent báo xong.

| Bước | Lệnh hoặc công cụ | Việc làm | Dịch vụ ngoài |
|---|---|---|---|
| 1. Chọn giá trị luân phiên | đọc `data/rotation.json`, `data/topics.json`, `data/review.json` | Chọn topic, giọng, trình độ, giao diện, kiểu dựng và tính năng chưa dùng gần đây; từ 07/11 còn đối chiếu để không trùng tiêu đề hay kiểu tiêu đề | không |
| 2. Tạo thư mục video | `node kit/setup.mjs <slug>` | Chép font, mascot, GSAP, `aura.css`, `aura.js` vào `formats/<slug>/` để render không cần mạng | không |
| 3. Viết kịch bản | ghi `formats/<slug>/script.json` | Câu đọc kèm ngôn ngữ và IPA giọng Mỹ, mode, topic, trình độ, giao diện, kiểu dựng, giọng, mascot, tiêu đề thumbnail | không |
| 4. Thu giọng và đọc lại | `node kit/voice.mjs <slug> && node kit/verify.mjs <slug>` | Gọi ElevenLabs lấy giọng kèm mốc thời gian từng chữ; lưu theo mã băm nên chạy lại không tốn credit; nhận dạng giọng nói đọc lại và tính tỉ lệ sai ký tự | ElevenLabs TTS và STT |
| 5. Dựng hình | agent viết `index.html`, `src/*.js`, `storyboard.md` | Dựng theo `kit/BRIEF.md` và hướng dẫn kiểu dựng (skill trong `soraflow/.claude/skills/` hoặc `kit/styles/<kiểu>/STYLE.md`) | image-studio `codex_image` nếu cần ảnh (ít khi dùng) |
| 6. Nhạc nền | `node kit/bed.mjs <slug> <giây> <giao diện>` | Tổng hợp nhạc bằng code, không tốn credit | không |
| 7. Hiệu ứng và mix | `node kit/sfx.mjs <slug> && node kit/mix.mjs <slug>` | Tạo hoặc lấy hiệu ứng từ thư viện; ít nhất 6 hiệu ứng khác nhau, mỗi hiệu ứng tối đa 3 lần; mix về -16 LUFS | ElevenLabs sound generation |
| 8. Kiểm trang | `npm run check` và snapshot | Agent đọc ít nhất 12 khung hình chụp, phóng to chữ để soát màu, font, dấu, IPA | không |
| 9. Quét chồng chữ | `node kit/scan.mjs <slug>` | Tua từng khung hình bằng trình duyệt headless, báo mọi khung hình có vật chạm chữ; phải về 0 | không |
| 10. Render | `HF_WORKERS=2 node kit/render.mjs <slug>` | Ra `out/<slug>/<slug>.mp4` và bản `-xem-truoc.mp4`; dừng nếu ổ đĩa còn dưới 5 GB | không |
| 11. Thumbnail | `node kit/thumbcard.mjs <slug>` | Thẻ riêng có tiêu đề rất to, dòng trình độ, chip mode và topic, mascot | không |
| 12. Xuất file | chép vào `~/Downloads/aura-coach-resources/daily/<ngày>/` | Bản xem trước và thumbnail | không |
| 13. Đưa lên trang web duyệt video | `tools/board_add.py`, Artifact `asset: true`, `tools/board_docs.py`, ArtifactData `set` | Ghi vào `data/review.json`, tạo bản 720p, tải bản 720p lên kho file của trang, ghi một bản ghi trạng thái "chờ duyệt" | claude.ai Artifact |
| 14. Gửi anh xem | SendUserFile | Gửi bản xem trước và thumbnail, chú thích loại, kiểu dựng, topic | Claude Desktop |
| 15. Ghi nhật ký | sửa `data/rotation.json`, `data/topics.json` | Ghi giá trị đã dùng để vòng luân phiên sau tránh trùng | không |

Từ 05/11 tới trưa 06/11 còn một bước nữa nằm giữa bước 11 và bước 14: workflow `aura-fix-until-pass`. Workflow này cho ba agent kiểm độc lập chạy song song, mỗi agent một góc nhìn theo `kit/VERIFY.md`: kỹ thuật (định dạng, độ to, quét chồng chữ), thương hiệu và tay nghề (ít nhất 24 khung hình), nội dung (tiếng Anh, IPA, nghĩa tiếng Việt, luật của anh). Mỗi agent trả PASS hoặc FAIL kèm lỗi. Nếu có FAIL, một agent sửa đúng các lỗi đó rồi render lại; tối đa ba vòng sửa. Video đạt đủ ba góc nhìn thì workflow ghi file `out/<slug>/PASSED.json`, và một tiến trình Monitor của phiên thấy file đó rồi gửi video cho anh. Lúc 12:00 ngày 06/11, anh phản đối việc giữ video lại sau các vòng kiểm, nên từ đó phiên bỏ bước này. `CLAUDE.md` nay ghi rõ không chạy vòng kiểm độc lập trừ khi anh yêu cầu.

## Phiên điều phối các agent thế nào

Phiên gọi công cụ Workflow 20 lần và gọi trực tiếp 10 agent. Các thư mục workflow chứa 298 file transcript agent; cộng 10 agent gọi trực tiếp thành 308 agent trong khoảng 3,5 ngày. Bảng sau lấy từ các file `wf_*.json`; giờ là giờ workflow kết thúc hoặc bị dừng.

| Workflow | Kết thúc | Trạng thái | Số agent | Thời gian chạy |
|---|---|---|---|---|
| `aura-fix-until-pass` (video Shadowing 05/11) | 05/11 17:28 | xong | 7 | 70 phút |
| `aura-build-and-check-b1b2` lần 1 | 05/11 17:45 | phiên dừng để thêm luật IPA và trình độ | 3 | 3 phút |
| `aura-fix-until-pass` cho ba video còn lại của bộ A1-A2 | 05/11 17:53–17:54 | phiên dừng vì video phải thêm IPA | 15, 7 và 11 | 99–125 phút |
| `aura-build-and-check-b1b2` lần 2 | 05/11 21:58 | xong | 48 | 252 phút |
| `aura-a1-ipa-level-upgrade` | 05/11 22:00 | file ghi xong, nhưng sáng 06/11 hai video am/is/are và Shadowing còn sửa dở vì tài khoản chạm giới hạn | 64 | 245 phút |
| `aura-resume-seven` | 06/11 09:24 | phiên dừng để thêm luật hook, headline, thumbnail | 15 | 24 phút |
| `aura-hook-headline-thumb-seven` và lần chạy tiếp | 06/11 11:56–12:01 | phiên dừng sau khi anh phản đối | 7 và 3 | không có file kết quả cho lần đầu |
| `aura-build-dot-journey` | 06/11 18:04 | phiên dừng vì anh sửa nội dung | 1 | 3 phút |
| `aura-build-set-0711` | 06/11 18:22 | xong | 4 | 147 phút |
| `aura-build-two-0711b` | 06/11 18:32 | xong | 2 | 155 phút |
| `aura-build-draw-guess` | 06/11 19:02 | xong | 1 | 57 phút |
| `aura-build-readings-and-lessons-0711` | 07/11 11:07 | xong | 8 | 180 phút |
| `aura-build-natural-doctor` | 07/11 13:02 | xong | 1 | 89 phút |
| `aura-style-lab` | 07/11 14:00 | xong | 68 | 87 phút |
| `aura-style-videos` | 07/11 16:57 | tạm dừng theo lời anh, 6 trên 17 video xong | 17 | 174 phút |
| `aura-finish-mural` | chưa xong lúc 18:31 ngày 08/11 | đang chạy | 1 | từ 15:23 |

Mỗi agent dựng nhận một prompt dài có đủ việc được giao: slug, kiểu dựng, mode, tính năng, topic, trình độ, giao diện, giọng, giới hạn credit, các luật không được phá và độ dài câu trả lời tối đa (80 đến 250 từ). Workflow `aura-style-lab` cho mỗi kiểu dựng mới một agent nghiên cứu, viết hướng dẫn `kit/styles/<kiểu>/STYLE.md` và dựng một khung hình mẫu, rồi một agent khác soi khung đó và agent đầu sửa một lượt.

Khi 17 agent dựng cùng lúc, máy bị nghẽn. Ngày 07/11, phiên thêm hai khóa vào kit. `kit/render.mjs` giữ khóa thư mục `out/.render-lock`, nên mỗi lần chỉ một video render; khóa có pid để gỡ khi tiến trình chết, và chờ tối đa 2 giờ. `kit/scan.mjs` giữ một trong ba khe `out/.scan-slot-1..3`, nên tối đa ba video quét chồng chữ cùng lúc.

Phiên theo dõi tiến độ bằng công cụ Monitor chạy một script shell chờ file mới (`PASSED.json`, `render.json`, file xuất mới). Mỗi lần Monitor chỉ chạy 30 phút nên phiên phải bật lại nhiều lần. Khi một video xong giữa lúc workflow còn chạy, phiên dùng các script nhỏ trong scratchpad (`prep.sh`, `fin.sh`) để đưa video đó lên trang web duyệt video ngay, không chờ cả lô.

## Anh duyệt ở những bước nào, và trạng thái duyệt đi qua đâu

Anh duyệt ở sáu bước:

1. Chọn giọng bằng tai. Ngày 05/11, anh chê giọng Việt Tâm Nguyễn, giọng mà phiên chọn theo số đo nhận dạng giọng nói. Phiên thu cùng một câu bằng Nhật Phong và Lam Vy, gửi hai file và hỏi anh bằng AskUserQuestion. Anh chọn Lam Vy. Từ đó luật ghi: giọng mới phải để anh nghe thử rồi chọn.
2. Xem bản xem trước trong chat. Phiên gửi 25 lần SendUserFile, mỗi lần kèm chú thích loại, kiểu dựng, topic. Từ 06/11, luật là gửi ngay khi render xong.
3. Duyệt xuất file. Chiều 06/11, từ 13:32 tới 15:48, phiên chỉ chép video vào thư mục xuất khi anh nhắn chốt hoặc duyệt export. Từ 15:48 ngày 06/11, anh đổi luật thành "Cứ làm rồi export vào local", nên phiên xuất ngay và để anh duyệt trên trang.
4. Nút trên trang web duyệt video (từ 16:17 ngày 06/11). Video chờ duyệt có nút "Duyệt". Video đã duyệt có nút "Đã đăng" và nút "Bỏ duyệt" để hoàn tác.
5. Gọi dịch vụ trả phí. Google Flow phải có báo giá chạy thử (`dry_run`) và lời đồng ý rõ của anh trước mỗi lần gọi; phiên không gọi Flow lần nào. ElevenLabs không cần duyệt từng lần, nhưng phiên phải báo credit theo video.
6. Sửa video đã xong và commit. Phiên không được sửa video đã render khi anh chưa yêu cầu, và không được commit khi anh chưa bảo.

Trạng thái duyệt đi qua các bước sau:

1. Khi một video xuất xong, `tools/board_add.py` thêm một dòng vào `data/review.json` với `status: "cho-duyet"` và tạo bản 720p trong `out/review720/`.
2. Phiên tải bản 720p lên kho file của trang web duyệt video (Artifact với `asset: true`) và nhận một đường dẫn `/_blob/<id>`.
3. `tools/board_docs.py` tạo một file JSON cho video, gồm tiêu đề, mode, tính năng, topic, trình độ, giao diện, kiểu dựng, trạng thái, thư mục và ảnh thumbnail nhỏ dạng data URI. Phiên ghi file đó vào collection `videos` của cơ sở dữ liệu trang qua ArtifactData (`set` hoặc `batch`, có `if_version` để không ghi đè thay đổi của anh). Mã bản ghi là slug.
4. Trang (`out/review-board.html`, đã đăng ở https://claude.ai/artifact/P8UatURxseWKp2bj49FH15) nghe thay đổi của collection bằng `onSnapshot` và vẽ lại danh sách.
5. Khi anh bấm "Duyệt", trang ghi `status: "da-duyet"` và `approved_at`. Khi anh bấm "Đã đăng", trang ghi `status: "da-dang"`, `drive_state: "cho-xu-ly"` và `posted_at`. Nút "Bỏ duyệt" ghi lại `status: "cho-duyet"`.
6. Mỗi lần phiên làm việc, phiên phải truy vấn các bản ghi có `status == "da-dang"` và `drive_state == "cho-xu-ly"`. Với mỗi bản ghi, phiên định đưa file lên Drive vào `aura-coach/daily/<ngày>/`, chuyển bản trên máy vào Thùng rác (không xóa hẳn), rồi ghi `drive_state: "xong"` và `drive_url`. File trên 10 MB không đi qua Chrome được thì ghi `drive_state: "keo-tay"` để anh tự kéo. Khi máy có `~/Library/CloudStorage/GoogleDrive-*/My Drive`, phiên chỉ cần chuyển file vào thư mục đó.

Bước 6 chưa chạy lần nào. Phiên đọc cơ sở dữ liệu của trang nhiều lần từ 06/11 tới sáng 07/11, và bản tóm tắt lúc 11:34 ngày 07/11 ghi chưa có yêu cầu "Đã đăng" nào. Từ 08/11, phiên không đọc được trang nữa. Lúc tôi viết báo cáo, `~/Library/CloudStorage/` chỉ có thư mục của MacDroid, chưa có Google Drive.

Thiết kế này có ba điểm yếu. Thứ nhất, nút anh bấm chỉ được xử lý khi phiên Aura đang mở và tự nhớ truy vấn. Dark Brain giải việc này bằng scheduled task `darkbrain-review-actions-2` chạy mỗi 10 phút, còn Aura không có task tương tự. Thứ hai, trạng thái anh bấm trên trang không chảy ngược về `data/review.json`; file local chỉ giữ trạng thái lúc phiên ghi lên. Thứ ba, trang thuộc về một tài khoản claude.ai. Từ 08/11, phiên chạy bằng tài khoản khác, ArtifactData trả lỗi không tìm thấy, và phiên không cập nhật được ảnh thumbnail mới của bốn video ngày 05/11 lên trang.

## Video xuất ra những đâu

| Nơi | Nội dung | Số đo lúc viết báo cáo |
|---|---|---|
| `formats/<slug>/` | Mã nguồn từng video: `script.json`, `index.html`, giọng, hiệu ứng, `mix.wav`, `storyboard.md`, `credits.json` | 43 thư mục |
| `out/<slug>/` | MP4 đầy đủ, bản `-xem-truoc.mp4`, `render.json`, thumbnail, `description.vi.txt`, `description.en.txt` | 35 bản xem trước |
| `out/review720/` | Bản 720p để phát trên trang web duyệt video | 35 file |
| `~/Downloads/aura-coach-resources/daily/<ngày>/` | Bản xem trước và thumbnail anh dùng để đăng | 33 MP4 và 33 PNG, tổng 390 MB |
| Trang web duyệt video trên claude.ai | Danh sách video, trạng thái, bản 720p phát được | Không mở được từ tài khoản hiện tại của phiên |
| Chat với anh | 25 lần gửi bản xem trước và thumbnail | đếm trong transcript |
| Google Drive `aura-coach/daily/<ngày>/` | Bản để đăng, chỉ sau khi anh bấm "Đã đăng" | chưa có file nào |

Phiên không đăng video lên mạng xã hội nào. Anh tự đăng từ thư mục xuất.

## Thời gian thực tế của bốn ngày

| Thời điểm | Việc |
|---|---|
| 05/11 14:17 | Phiên soraflow khởi động phiên với brief đầy đủ |
| 05/11 14:18–14:38 | Một agent lọc lời anh trong transcript Dark Brain; phiên chép kit, viết `docs/darkbrain-flow-notes.md`, thu giọng bốn video, giao bốn agent dựng |
| 05/11 15:48–16:18 | Bốn video render xong và vào vòng kiểm ba góc nhìn |
| 05/11 17:30 | Video đầu tiên được gửi anh (Shadowing, đạt sau một vòng sửa) |
| 05/11 17:31–19:33 | Anh đổi giọng Việt, giao thêm ba video B1-B2, thêm luật IPA, luật trình độ, luật tên mode và 16 topic |
| 05/11 khoảng 21:55 | Tài khoản Claude cũ chạm giới hạn dùng hằng tuần; các workflow bị cắt |
| 06/11 08:58 | Phiên soraflow nhắn tiếp tục việc dở; phiên đã chạy bằng tài khoản khác |
| 06/11 11:56–12:01 | Anh phản đối việc sửa lại video cũ và việc không gửi bản xem trước; phiên dừng mọi vòng kiểm |
| 06/11 13:32–19:17 | Xuất file local, mẫu reading challenge, sáu quy luật luân phiên, trang web duyệt video có nút và trình phát |
| 07/11 08:03–13:08 | Bốn video reading theo mẫu và bốn video bài học; anh bỏ hai video trùng; phiên làm hai video thay |
| 07/11 12:31–16:57 | Nghiên cứu 17 kiểu dựng mới, dựng 6 video, rồi tạm dừng theo lời anh |
| 08/11 14:28–15:22 | Kiểm lại file xuất, làm bốn thẻ thumbnail cho video 05/11, thống kê kiểu dựng, nhận yêu cầu video tranh tường |
| 08/11 18:31 | Video tranh tường vẫn kẹt ở bước quét chồng chữ khoảng 80 phút vì máy quá tải |

Một video mất khoảng 1 đến 3 giờ từ lúc giao agent dựng tới lúc render xong. Hai workflow dựng một video chạy 57 và 89 phút; các workflow dựng 2 đến 8 video song song chạy 147 đến 180 phút. Khi còn bước kiểm, workflow kiểm và sửa một video chạy thêm 70 đến 125 phút.

## Phiên liên lạc với các phiên khác thế nào

Phiên soraflow là phiên khởi động. Tin nhắn liên phiên đến từ hai mã phiên soraflow: `local_af322bac-...` ngày 05/11 và `local_3a3d3dce-...` ngày 06/11, sau khi đổi tài khoản. Từ 08/11, phần hướng dẫn hệ thống ghi phiên khởi động là `local_0fa1d364-a787-48a6-a35b-b7aacfe5e547`. Theo hướng dẫn đó, phần tóm tắt cuối lượt và 400 ký tự đầu của câu trả lời cuối được tự động chuyển về phiên khởi động; phiên chỉ dùng SendMessage khi bị chặn và cần hỏi. Trong cả transcript, phiên Aura không gọi SendMessage lần nào. Vì vậy liên lạc với soraflow là một chiều: soraflow chuyển luật và lệnh tiếp tục việc dở sang, còn Aura báo lại qua cơ chế tự chuyển và qua file ghi chú chung.

Phiên `darkbrain-daily` không nhắn gì với phiên Aura, và phiên Aura cũng không nhắn gì cho `darkbrain-daily`. Quan hệ giữa hai phiên nằm ở file: phiên Aura đọc mà không sửa `~/Projects/darkbrain-studio/news-video` và transcript Dark Brain (qua một agent), rồi chép kit. Luật `CLAUDE.md` cấm ghi vào `darkbrain-studio`. Hai phiên còn dùng chung khóa ElevenLabs ở `~/.config/cartoon-studio/elevenlabs_api_key` và dùng chung CPU của máy. Ngày 05/11 lúc 19:34, phiên gọi ListAgents một lần và thấy `darkbrain-daily` đang bận; phiên không làm gì thêm với kết quả đó.

Phiên `thomhouse-academy-daily` chỉ xuất hiện trong ghi chú trạng thái phiên liên kết ngày 08/11 (đang chạy) và trong lệnh `ps` đo tải máy lúc 18:31, khi các tiến trình có chữ thomhouse chiếm khoảng 4% CPU. Không có tin nhắn nào giữa hai phiên.

## Những lỗi đã gặp

| Lỗi | Hậu quả | Cách phiên xử lý hoặc luật mới |
|---|---|---|
| Tài khoản cũ chạm giới hạn dùng hằng tuần lúc khoảng 21:55 ngày 05/11 | Các workflow bị cắt giữa chừng; phiên đứng tới sáng | Phiên soraflow chuyển phiên sang tài khoản khác; phiên kiểm trạng thái trên đĩa rồi chạy nốt phần dở |
| Phiên áp luật hook, headline, thumbnail do soraflow chuyển sang cho cả bảy video đã render | Bốn bản render cũ trong `out/` bị ghi đè; anh phản đối gay gắt | Luật mới chỉ áp cho video chưa làm; hỏi anh trước khi sửa video đã render; sao lưu trước khi ghi đè; luật do phiên khác chuyển sang không phải lời anh về phạm vi |
| Video bị giữ lại qua tới ba vòng kiểm và sửa tự động | Tốn thời gian và credit; anh không thấy video | Gửi bản xem trước ngay khi render; bỏ vòng kiểm trừ khi anh yêu cầu |
| Chọn giọng Việt theo số đo nhận dạng giọng nói | Anh chê giọng | Thu thử hai giọng anh từng duyệt để anh nghe rồi chọn |
| Video reading challenge làm quá cầu kỳ | Anh yêu cầu làm đúng hình thức video mẫu | Ghi mẫu chữ chạy đơn giản vào memory |
| Lấy chủ đề của video mẫu làm nội dung | Anh sửa: chỉ lấy kiểu dựng, nội dung vẫn là bài học | Luật "theo styles này" chỉ chép kiểu dựng |
| Hai video trùng tiêu đề hoặc trùng dạng | Anh bỏ hai video | Trước khi làm video, đối chiếu `data/review.json` và `data/topics.json` |
| Quota tạo ảnh Codex hết tới 15:50 ngày 06/11 | Năm lần gọi ảnh bị từ chối | Agent vẽ hình giấy cắt bằng code |
| Agent dựng kết thúc lượt khi bước quét còn chạy nền | Video luật không render | Gọi một agent mới hoàn thành phần còn lại, kèm lệnh cấm chạy nền |
| 17 agent dựng cùng lúc | Máy nghẽn, render tranh nhau | Khóa render một video một lúc, ba khe quét |
| Hai file hiệu ứng thư viện thật ra là một | Một tiếng click vang 5 lần, quá mức 3 lần | Bỏ file trùng; bộ trộn đếm theo nội dung âm thanh |
| zsh báo lỗi glob và chỉ số mảng | Tiến trình theo dõi chết, vài lệnh `rm` hỏng | Viết lại script theo dõi bằng bash |
| Đổi tài khoản claude.ai ngày 08/11 | Không đọc hay ghi được trang web duyệt video | Báo anh; chờ anh đăng nhập lại tài khoản tạo trang |
| Máy quá tải ngày 08/11 (load average khoảng 520) | Bước quét chồng chữ của video tranh tường kẹt khoảng 80 phút | Chưa có cách xử lý; agent vẫn chạy |
| Chép nguyên văn chữ của một kênh TikTok cho video reading | Có rủi ro bản quyền | Phiên báo anh lúc 13:36 ngày 06/11 và đề nghị viết lại câu nối; các video sau vẫn giữ chữ của video mẫu theo yêu cầu |

## Chi phí và giới hạn

Claude. Bản ghi `cost-state` cuối trong transcript ghi tổng 1.408,02 USD quy theo giá API, gần như toàn bộ cho Opus 5.5: 12,88 triệu token đầu ra, 6,82 triệu token suy nghĩ và 2,16 tỷ token đọc từ cache. Phiên chạy bằng subscription, không trả theo token; con số này cho biết khối lượng việc, không phải hóa đơn. Bằng chứng phiên chạy bằng subscription là tin nhắn soraflow ngày 06/11 nói tài khoản cũ chạm giới hạn dùng hằng tuần.

ElevenLabs. Tổng trường `billed` trong 35 file `credits.json` là 8.002 credit (tôi cộng bằng script). Mỗi thư mục video tốn từ 43 credit (video chỉ có nhạc) tới 528 credit (video có nhiều câu đọc và hiệu ứng). Con số này chưa gồm lượt thử giọng (176 credit ngày 05/11) và các lần thử giọng Việt. Theo phiên, ngày 07/11 tài khoản còn 17.911 trên 57.035 credit, làm mới ngày 29/11. Khóa này dùng chung với Dark Brain, nên số dư giảm vì cả hai studio. Phiên đã báo anh rằng số dư không đủ cho 4 video mỗi ngày tới cuối tháng nếu không nâng gói. Lô 17 kiểu mới bị giới hạn dưới 800 ký tự lời đọc và tối đa 60 credit hiệu ứng mỗi video.

Tạo ảnh. image-studio `codex_image` dùng quota của gói Codex, khoảng 3 phút một ảnh, mỗi lần một ảnh. Quota đã hết một lần ngày 06/11.

Máy. Render cần ít nhất 5 GB ổ trống. Từ 07/11, mỗi lần chỉ một video render và tối đa ba video quét chồng chữ. Kiểu dựng dùng WebGL chạy qua trình giả lập phần mềm, nên mỗi khung hình chụp rất chậm khi máy bận.

Drive và Chrome. Công cụ tải file của Chrome chỉ nhận file dưới 10 MB. Ngày 06/11, 6 trên 12 video đã xuất nặng 11 đến 18 MB. Phiên không được nén lại video để lọt giới hạn.

## thom house dùng lại được gì

Tôi chia theo hai việc: chăm sóc khách (bot trả lời trên Zalo cá nhân) và nội dung (video hoặc bài giới thiệu dịch vụ, nếu anh làm sau này). Mỗi mục nêu phần Aura đã có, cách áp cho thom house, và điểm yếu.

### Chăm sóc khách

Trạng thái duyệt thành vài giá trị rõ ràng. Aura dùng `cho-duyet`, `da-duyet`, `da-dang`, `dang-lam`, thêm `drive_state` cho bước sau khi đăng, nút hoàn tác và `if_version` khi ghi. Với thom house, mỗi bản nháp câu trả lời có thể đi qua các trạng thái tương tự (chờ duyệt, đã duyệt, đã gửi, gửi lỗi), có nút sửa và nút hoàn tác trước khi gửi. Trạng thái phải nằm trong cơ sở dữ liệu của server thom house và hiện trên console, không nằm trong trang claude.ai, vì trang Aura mất quyền truy cập khi đổi tài khoản. Điểm yếu: thêm trạng thái thì nhân viên phải bấm thêm, nên chỉ tách trạng thái khi mỗi trạng thái dẫn tới một việc khác nhau.

Nút bấm phải được xử lý ngay. Ở Aura, nút "Đã đăng" chờ tới khi phiên đang mở tự truy vấn; ở Dark Brain, một scheduled task chạy mỗi 10 phút. Bot thom house cần nhanh hơn cả hai: khi nhân viên bấm duyệt, server phải tự đưa tin vào hàng gửi, không phụ thuộc phiên Claude nào. Điểm yếu: đường gửi tự động cần kill switch để dừng ngay khi có sự cố.

Luật của chủ doanh nghiệp ghi thành file nhớ có cấu trúc. Mỗi file memory của Aura có tên, mô tả, lời anh kèm ngày, mục "Why" và mục "How to apply". Với thom house, các luật như cách xưng hô, câu y tế bị cấm, giờ mở cửa hay chính sách hủy lịch nên được ghi theo cùng mẫu, kèm nguồn và ngày chủ doanh nghiệp duyệt. Aura còn có một luật đáng giữ: luật do một phiên khác chuyển sang không phải lời chủ về phạm vi áp dụng. Điểm yếu: file nhớ chỉ có tác dụng khi prompt của runner thật sự nạp file đó, nên phải có test kiểm prompt có đủ luật.

Kiểm bản nháp theo từng góc riêng, chỉ một lượt. Ba góc nhìn của Aura (kỹ thuật, thương hiệu, nội dung) tương ứng với ba việc kiểm một câu trả lời: dữ kiện có khớp `data/services.json` và `data/business-facts.json` không, giọng và cách xưng hô có đúng không, định dạng có hợp Zalo không. Nên làm phần kiểm được bằng code (giá, tên dịch vụ, câu cấm) trong server, còn phần cần đọc hiểu để nhân viên duyệt. Bài học của Aura là không xếp nhiều vòng kiểm tự động trước khi người thấy kết quả. Điểm yếu: một lượt kiểm sẽ bỏ sót lỗi mà vòng kiểm thứ hai có thể bắt.

Danh sách điều không được nói. Mục "Never claim" trong `kit/BRIEF.md` của Aura cấm nêu giá, hứa tải app, hứa tính năng chưa có. thom house cần một danh sách tương tự cho câu chữa bệnh, giảm u, ngừa đột quỵ và các lời hứa tác dụng đã liệt kê trong `research/01-knowledge-audit.md`, rồi kiểm danh sách đó trong code trước khi gửi.

Tách tài khoản và tài nguyên máy. Aura cho thấy một phiên dựng video có thể dùng hết giới hạn tuần của một tài khoản và làm CPU quá tải. Với thom house, tôi đề xuất bot dùng một tài khoản riêng không dùng cho studio video, hoặc ít nhất đặt tài khoản dùng chung ở ưu tiên thấp trong pool. Studio video nên render ngoài giờ khách hay nhắn. Điểm yếu: thêm một tài khoản subscription thì tốn thêm tiền gói.

### Nội dung

Bộ công cụ dựng video ngắn. Nếu thom house muốn video giới thiệu dịch vụ hay quy trình, có thể chép `kit/` của Aura (setup, voice, verify, sfx, bed, mix, scan, render, thumbcard) và thay lớp thương hiệu bằng màu, font và hình của thom house, đúng như Aura đã làm khi chép từ Dark Brain. Giọng Việt phải để chủ doanh nghiệp nghe thử rồi chọn. Điểm yếu: ở Aura, mỗi video tốn từ 43 đến 528 credit ElevenLabs và 1 đến 3 giờ máy, và lời dịch vụ phải qua danh sách câu y tế bị cấm trước khi thu giọng.

Nhật ký luân phiên. `data/rotation.json` và `data/topics.json` ghi mỗi video đã dùng topic, giọng, trình độ, giao diện, kiểu dựng nào. thom house có thể ghi tương tự cho bài đăng: dịch vụ nào, ưu đãi nào, mẫu nào, để không lặp. Điểm yếu: nhật ký chỉ đúng khi mọi bài đều được ghi vào, kể cả bài anh tự làm.

Định dạng đơn giản trước. Anh chọn mẫu reading challenge chữ chạy đơn giản thay cho bản nhiều thẻ, chip, IPA. Với thom house, video quy trình liệu trình hay bảng giá có thể bắt đầu bằng dạng chữ và hình đơn giản rồi mới thêm kiểu dựng cầu kỳ.

Không chép nội dung của người khác. Aura giữ nguyên chữ của một kênh TikTok cho bốn video reading; phiên đã báo rủi ro bản quyền. thom house không nên chép câu chữ, ảnh hay video của spa khác.

## Câu hỏi còn mở

- Tài khoản Claude của bot thom house có trùng với tài khoản phiên Aura và các phiên Claude Desktop đang dùng không. Anh cần chạy `python3 scripts/runner/claude_pool.py status` và đối chiếu với tài khoản đang đăng nhập trong Claude Desktop.
- API key Claude anh dán vào phiên Aura ngày 05/11 đã được thu hồi chưa.
- Phiên Aura còn chờ anh trả lời một câu từ 07/11: có thêm nghĩa tiếng Việt cho ba video đoán từ cũ không. Câu này không ảnh hưởng thom house; tôi ghi lại để anh biết phiên đó còn việc treo.

## Nói ngắn gọn nhất

Phiên `aura-coach-daily` không chạy theo lịch: mỗi đợt video bắt đầu từ tin nhắn của anh hoặc của phiên soraflow, phiên viết kịch bản và thu giọng, các agent dựng và render, rồi anh xem bản xem trước và bấm duyệt trên một trang claude.ai. Trong 3,5 ngày, phiên xuất 33 video, dùng khoảng 308 agent, tốn khối lượng tương đương 1.408 USD giá API và khoảng 8.000 credit ElevenLabs, chưa đưa video nào lên Drive. thom house nên lấy cách ghi trạng thái duyệt, cách ghi luật của chủ, cách kiểm bản nháp một lượt và danh sách điều không được nói, nhưng giữ trạng thái duyệt trong server của mình và xử lý nút bấm ngay. Trước khi bật bot, anh cần tách tài khoản Claude và giờ render của các studio video khỏi bot, vì Aura đã cho thấy một đợt dựng lớn có thể làm tài khoản chạm giới hạn tuần và làm máy quá tải.

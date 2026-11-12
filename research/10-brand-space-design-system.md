# thom house: không gian studio, giọng chị Thơm và hệ nhận diện thương hiệu

Ngày viết: 2026-11-08. Người đọc chính: anh, trước khi quyết định chatbot được nói gì về không gian studio và trước khi chọn màu, font cho các trang của chatbot.

## Phần anh cần duyệt

thom house chưa có design system chính thức ở dạng file riêng hay artifact trên claude.ai. Design system là bộ quy định chung về màu, font, logo, khoảng cách và giọng văn, để mọi ấn phẩm trông như của cùng một thương hiệu. Nguồn đầy đủ nhất tôi tìm được là trang landing page `/Users/luuphuc/Projects/thomhouse-academy-daily/source/landing-page.html`. Trang này ghi toàn bộ màu, font, khoảng cách và nhịp chuyển động thành biến CSS. Bộ công cụ làm video của dự án Thomhouse Academy đã chép lại các biến đó. Logo chỉ có một bản vẽ lại dạng SVG nằm trong trang landing page, chưa có file logo gốc.

Mười hai ảnh không gian chỉ chụp tầng trệt: quầy lễ tân, góc sofa chờ, kệ tường, cầu thang và mặt tiền kính nhìn ra đường. Không ảnh nào chụp phòng làm dịch vụ, giường, phòng tắm, chỗ để xe hay mặt tiền nhìn từ ngoài vào. Vì vậy, chatbot chưa có căn cứ để trả lời khách về phòng riêng, giường hay chỗ gửi xe.

File ghi âm giọng chị Thơm dài 31,04 giây (đo bằng `ffprobe`). Tôi không chép lời được, vì máy này chưa cài công cụ chuyển giọng nói thành chữ nào chạy local. Hai script có sẵn trong các dự án khác đều gửi âm thanh lên dịch vụ trả tiền ElevenLabs, nên tôi không dùng.

Thư mục Drive tổng quan không đổi so với bản sao ngày 07/11: cả 32 file có cùng ID, tên, dung lượng và ngày sửa. Drive chỉ còn hai file chưa có trong bản sao là `.claude/settings.local.json` (293 byte) và `.DS_Store` (14.340 byte). Tôi chưa tải hai file này, vì việc tải file cần anh đồng ý trực tiếp trong chat. Vì vậy, thư mục `sources/drive-extra/` chưa được tạo.

Anh cần quyết bốn việc:

1. Bảng đặt trên quầy và bàn chờ in mật khẩu wifi, tên chủ tài khoản và số tài khoản Techcombank kèm mã QR chuyển khoản. Tôi đề xuất chatbot không tự gửi số tài khoản; khi khách hỏi chuyển khoản, chatbot chuyển cho nhân viên. Điểm yếu: khách chờ lâu hơn một chút. Lý do đề xuất: một số tài khoản do bot gửi, nếu sai hoặc bị kẻ gian giả mạo, sẽ gây mất tiền thật.
2. Thời lượng Gói Mụn 5 in 1 đang lệch giữa ba nguồn. Ảnh menu trên điện thoại trong IMG_7874.jpg ghi 90–120 phút. Văn bản chép menu ngày 16/05 ghi 90 phút. Trang landing page ghi 60–90 phút. `data/services.json` đang ghi 90 phút. Chủ studio cần xác nhận con số đúng.
3. Có tải `.claude/settings.local.json` về để đọc không. Theo tên file và dung lượng, tôi suy luận đây là file cấu hình quyền của Claude Code trên máy người soạn tài liệu, không chứa kiến thức kinh doanh. Tôi đề xuất không tải.
4. Có thêm vào `data/business-facts.json` các dữ kiện về không gian mà ảnh cho thấy hay không, ví dụ có tủ khóa gửi đồ và tầng trên dành cho nail, thư giãn và chăm sóc tóc. Tôi đề xuất thêm với trạng thái riêng, ghi rõ là thấy trong ảnh và chưa được chủ studio xác nhận.

## Thuật ngữ dùng trong báo cáo

| Thuật ngữ | Nghĩa trong báo cáo này |
|---|---|
| bản sao Drive | thư mục `sources/drive/` trong dự án này, chép từ thư mục Drive tổng quan `1RCyvhe6w1wd2edzyXBFI0f7v6DSPNrOv` ngày 2026-11-07 |
| trang landing page | file `/Users/luuphuc/Projects/thomhouse-academy-daily/source/landing-page.html`, tiêu đề `thom house healing studio`, 1.682 dòng |
| token | tên đặt cho một giá trị thiết kế, ví dụ token `--kim` là màu vàng kim `#cfae7b` |
| sắc | cách trang landing page gọi màu chủ đạo của từng menu, ví dụ Sắc ngọc trai là màu của menu chăm sóc da |
| bộ ảnh menu | các ảnh menu trong `sources/drive-resources/thomhouse-menu/`, chép ngày 2026-11-08 |

## Mười hai ảnh không gian cho thấy gì?

Studio ở tầng trệt dùng một tông sáng và mềm. Tường và trần trát vữa vân mây màu kem xám, nhiều mảng tường bo cong. Sàn lát gạch terrazzo trắng có hạt. Đồ gỗ màu óc chó sẫm xuất hiện ở tủ khóa và tay vịn cầu thang. Trong 12 ảnh, mảng màu đậm nổi bật nhất là bức tường màu nghệ, giống đất nung, ở chân cầu thang. Cây xanh đặt khắp nơi, chủ yếu là trầu bà lá xẻ (monstera) và lan ý. Mặt tiền là vách kính kéo hết chiều cao, che bằng rèm voan trắng.

Tôi đo màu trung bình của một ô vuông 60 đến 200 điểm ảnh trên ảnh gốc, bằng `sips` và một script Python ngắn. Các mã dưới đây phụ thuộc ánh sáng lúc chụp và cân bằng trắng của điện thoại, nên chỉ để tham khảo, không phải mã sơn.

| Vật liệu | Ảnh | Màu trung bình đo được |
|---|---|---|
| Tường vữa vân mây cạnh quầy lễ tân | IMG_7516.jpg | `#D2D1C8` |
| Tường vữa cạnh kệ âm tường, dưới đèn vàng | IMG_7493.jpg | `#BFC5B8` |
| Mảng tường màu nghệ ở chân cầu thang | IMG_7545.jpg | `#BB7B3F` |
| Mặt tủ khóa gỗ sẫm | IMG_7545.jpg | `#7B5833` |
| Mảng tường nhám màu xám trong khung vòm | IMG_7518.jpg | `#888378` |
| Tấm gỗ sáng khắc chữ THOM HOUSE | IMG_7864.jpg | `#A2784F` |

Bảng sau tả từng ảnh. Cột chữ in chỉ ghi chữ tôi đọc được trên ảnh.

| Ảnh | Kích thước | Nội dung | Chữ in trong ảnh |
|---|---|---|---|
| IMG_7493.jpg | 3024×3024, vuông | Góc tường cạnh cửa kính: ba hốc kệ âm tường có đèn LED vàng, đặt tượng gốm trắng hình vòm, hai thú nhỏ, cây thông mini, chậu cây nhỏ và lư đốt nến; bên dưới là tủ ba ngăn màu trắng, hộp cầu dao điện và chậu cây vạn niên thanh | Không có chữ đọc được |
| IMG_7516.jpg | 3024×4032, dọc | Quầy lễ tân bo cong ốp vữa trắng, mặt quầy đá sáng; bảng chữ gắn tường có đèn hắt; đèn thả trắng hình đám mây; hốc dưới quầy đặt hoa, chén và đồ thờ nhỏ. Phía sau là tủ khóa gỗ, bậc thềm lên một hành lang có vòm và kệ sách, giá vẽ dựng bảng hướng dẫn | `THOM HOUSE` trên tường; bảng đỏ ghi «NỘI QUY phòng cháy và chữa cháy» |
| IMG_7518.jpg | 3024×4032, dọc | Góc chờ: sofa cong bọc vải bouclé màu kem, gối vuông, bàn tròn trắng chân tiện, chậu cây gốm xám bóng, bảng wifi khung gỗ; sau lưng sofa là mảng tường nhám màu xám trong khung vòm; bên phải là monstera và rèm voan | Bảng khung gỗ ghi `THOM HOUSE`, `WIFI`, tên và mật khẩu wifi, logo Techcombank, mã QR, tên chủ tài khoản và số tài khoản. Tôi không chép mật khẩu, tên và số tài khoản vào báo cáo |
| IMG_7530.jpg | 2696×3832, dọc | Toàn cảnh tầng trệt từ trong nhìn ra mặt tiền kính: đèn âm trần, rèm voan, bình nước uống, sofa, quầy lễ tân, ghế xoay văn phòng; tiền cảnh là bồn cây lan ý | Không có chữ đọc được |
| IMG_7545.jpg | 2921×3895, dọc | Chân cầu thang: tường màu nghệ cắt thành vòm lượn sóng, tay vịn gỗ, lan can sắt uốn, bậc ốp đá vân; dưới gầm cầu thang là tiểu cảnh monstera, lan ý, sỏi trắng và gốc cây khô; hai bình chữa cháy màu đỏ. Bên trái là tủ khóa gỗ có chìa gắn thẻ màu. Phía trong là hành lang trắng có vòm, kệ sản phẩm và một máy màu đen, có vẻ là máy lọc không khí | Chữ dán tường cạnh cầu thang đi lên: «Nail» và «Relax and Hair care» |
| IMG_7560.jpg | 3024×4032, dọc | Góc tường cong có đèn âm hình tam giác, cây thông nhỏ trong bao bố phủ bông giả tuyết, công tắc điện, mép ghế mây | Không có chữ |
| IMG_7861.jpg | 4032×3024, ngang | Cận bảng chữ gắn tường: chữ in hoa không chân, mặt chữ tối, đèn LED phía sau hắt quầng vàng ra tường. Trên quầy có chậu cây rủ, bảng wifi và quả dứa gốm trắng lá vàng | `THOM HOUSE` |
| IMG_7864.jpg | 3024×4032, dọc | Bàn tròn trắng, chậu cây gốm xám, tấm gỗ chữ nhật có đinh tán ở một đầu; nền là sofa kem và monstera | `THOM HOUSE` khắc trên gỗ, kiểu chữ có chân |
| IMG_7874.jpg | 3024×4032, dọc | Một người mặc bộ satin xanh nhạt, tay cầm ly thủy tinh đựng trà và điện thoại đang mở ảnh menu, nền xanh xám sẫm, chữ tím nhạt | «GÓI MỤN 5 IN 1», «MỤN SIGNATURE», «Thời gian: 90-120 phút», «599.000 VND» và sáu bước của gói |
| IMG_7882.jpg | 3840×2160, ngang 16:9 | Toàn cảnh tầng trệt nhìn ra mặt tiền: vách kính lớn, rèm voan, sofa, bàn tròn, cây xanh, bình nước, kệ âm tường có đèn, tủ trắng, quầy lễ tân, ghế xoay. Ở góc trên bên phải rèm có một thiết bị nhỏ, có vẻ là camera an ninh | Qua kính thấy biển hiệu một cửa hàng bên kia đường. Tôi không dùng biển hiệu đó để suy ra vị trí |
| IMG_7890.jpg | 3024×4032, dọc | Cùng góc chụp với IMG_7864.jpg, chỉnh màu ấm và tối hơn, có hạt nhiễu | `THOM HOUSE` khắc trên gỗ |
| IMG_7891.jpg | 3315×2486, ngang | Hai người ngồi trên sofa, ảnh không thấy mặt. Một người mặc áo thun đen in chữ trắng, cầm điện thoại. Người kia mặc váy satin xanh nhạt | `THOM HOUSE` trên áo thun đen |

Các ảnh cho thấy thêm hai chi tiết về cách viết tên. Mọi bảng hiệu và đồ vật trong ảnh đều in chữ hoa `THOM HOUSE`: bảng chữ trên tường, bảng wifi, tấm gỗ và áo thun. Tài liệu thương hiệu trên Drive lại quy định viết thường `thom house` và cấm cách viết `Thom House` (`sources/drive/documentation/06-brand-voice-identity.md` dòng 18–20). Chữ in hoa toàn bộ là một kiểu trình bày, khác với cách viết hoa chữ đầu mà tài liệu cấm. Vì vậy, tôi đề xuất chatbot vẫn viết `thom house` như tài liệu quy định.

### Khách có thể hỏi gì, và ảnh trả lời được đến đâu?

Phần này tách dữ kiện thấy trực tiếp trong ảnh khỏi suy luận của tôi.

| Câu khách hay hỏi | Ảnh cho thấy gì | Mức chắc chắn |
|---|---|---|
| Studio có phòng riêng không, giường thế nào? | Không ảnh nào chụp phòng làm dịch vụ hay giường | Chưa có dữ kiện |
| Có chỗ để xe không? | Không ảnh nào chụp lối vào hay vỉa hè. `data/business-facts.json` cũng ghi `parking` là `missing` | Chưa có dữ kiện |
| Lối vào trông thế nào? | Mặt tiền là vách kính kéo hết chiều cao, che rèm voan trắng, nhìn thẳng ra đường (IMG_7530.jpg, IMG_7882.jpg) | Thấy trực tiếp trong ảnh, chụp từ bên trong |
| Có chỗ gửi đồ không? | Có tủ khóa gỗ nhiều ngăn, mỗi ngăn có chìa gắn thẻ màu (IMG_7516.jpg, IMG_7545.jpg) | Thấy trực tiếp trong ảnh |
| Nail, thư giãn và chăm sóc tóc ở đâu? | Chữ «Nail» và «Relax and Hair care» dán cạnh cầu thang đi lên (IMG_7545.jpg) | Suy luận: các dịch vụ này ở tầng trên. Căn cứ là vị trí chữ cạnh cầu thang |
| Studio có làm nail không? | Có chữ «Nail» trên tường. `data/services.json` không có dịch vụ nail nào | Chữ trên tường là dữ kiện; studio còn làm nail hay không thì chưa có nguồn |
| Có wifi không? | Có bảng wifi trên quầy và bàn chờ | Thấy trực tiếp trong ảnh |
| Có nhận chuyển khoản không? | Bảng trên quầy có mã QR và số tài khoản Techcombank | Thấy trực tiếp trong ảnh. `payment_methods` trong `data/business-facts.json` đang là `missing` |
| Ngồi chờ ở đâu, có nước uống không? | Có sofa, bàn tròn và bình nước uống ở tầng trệt; một ảnh có người cầm ly trà (IMG_7874.jpg) | Sofa và bình nước thấy trực tiếp. Việc studio mời trà là suy luận từ một ảnh |
| Có an toàn không? | Có hai bình chữa cháy, bảng nội quy phòng cháy chữa cháy và một thiết bị có vẻ là camera | Bình chữa cháy và bảng nội quy thấy trực tiếp; camera là suy luận |

Theo đánh giá bằng mắt của tôi, bộ ảnh có chỉnh màu và ánh sáng, chụp vào ban ngày, có đồ trang trí Giáng sinh (cây thông nhỏ có bông giả tuyết). Ảnh không mang ngày chụp: `sips -g creation` trả về `<nil>` cho cả 12 ảnh, và phần EXIF của IMG_7493.jpg và IMG_7882.jpg không có chuỗi ngày giờ nào. Vì vậy, tôi không biết ảnh chụp năm nào và không gian hiện nay còn như vậy không.

## Giọng chị Thơm trong file ghi âm nói gì?

Tôi chưa biết, vì tôi không chép lời được. File `sources/drive-resources/voice-chi-Thom.m4a` dài 31,04 giây, mã hóa AAC, một kênh, 48 kHz, khoảng 69 kbps. Các số này lấy từ lệnh `ffprobe -show_entries format=duration,bit_rate:stream=codec_name,sample_rate,channels`.

Tôi đã kiểm các công cụ chuyển giọng nói thành chữ có thể đã cài sẵn:

- `which whisper whisper-cli whisper-cpp mlx_whisper` không tìm thấy lệnh nào.
- `python3 -c "import whisper"`, `faster_whisper`, `mlx_whisper`, `whisperx`, `vosk` và `speech_recognition` đều báo không có module.
- `ffmpeg -filters` không có bộ lọc `whisper`. Không có file model `ggml-*.bin` trong thư mục nhà. `pipx list` chỉ có `poetry`.
- Bốn script có chức năng chép lời: `kit/verify.mjs` ở cả `~/Projects/thomhouse-academy-daily` và `~/Projects/aura-coach-studio`, cùng `tools/audition.mjs` và `tools/audition-vi.mjs` của `aura-coach-studio`. Cả bốn đều gọi `/v1/speech-to-text` của ElevenLabs. Script loại này gửi file âm thanh lên máy chủ ElevenLabs và dùng gói ElevenLabs của anh, nên tôi không chạy.

Muốn chép lời mà không gửi âm thanh ra ngoài, anh có hai cách. Cách thứ nhất là cài một công cụ chạy local, ví dụ `whisper.cpp` hoặc `mlx-whisper`, rồi tải một model nhận được tiếng Việt. Việc cài và tải model cần anh cho phép, vì đó là cài thêm phần mềm vào máy. Điểm yếu là model cỡ lớn nặng vài GB và có thể nghe sai tên dịch vụ. Cách thứ hai là anh nghe 31 giây rồi gõ lại; cách này nhanh nhất với một file ngắn.

Dự án Thomhouse Academy đã dùng file ghi âm này. Thư mục `/Users/luuphuc/Projects/thomhouse-academy-daily/voice/` có bản đã làm sạch `thom-sample-clean.wav` dài 26,26 giây (đo bằng `ffprobe`) và file `clone-result.txt`. Theo `docs/owner-decisions-2026-11-08.md` dòng 11 của dự án đó, giọng chị Thơm đã được clone trên ElevenLabs với tên `Thơm - Thomhouse`. Tôi tìm các chữ `voice-chi`, `thom-sample`, `giọng chị` và `clone` trong dự án đó, và không thấy file nào chép lại lời trong bản ghi âm. Vì vậy, chatbot hiện chưa dùng được nội dung của file ghi âm.

## Design system của thom house nằm ở đâu?

### Tôi đã tìm ở những nơi nào?

Tôi tìm theo danh sách được giao, chỉ đọc, không sửa gì.

| Nơi tìm | Kết quả |
|---|---|
| Artifact trên claude.ai | Lệnh `list` với `scope: types` cho thấy có loại Design System. Lệnh `list` với `type: Design System` không trả về artifact nào. Cả tài khoản chỉ có hai artifact, và cả hai đều không nói về thom house |
| `~/Projects/open-design` | Thư mục `design-systems/` có 154 design system, không design system nào mang tên thom house. Tìm chữ `thom house` hoặc `thomhouse` trong file `.md`, `.json`, `.ts`, `.tsx`, `.css`, `.html` không thấy |
| `~/Projects/darkbrain-studio` | Có design system riêng của Dark Brain (`design-system/tokens.json`, `tokens.css`). Tìm chữ thom house không thấy |
| `~/Projects/aura-coach-studio` | Tìm chữ thom house hoặc token `nuoc-950` không thấy |
| `~/Projects/truc-brain` | Tìm chữ thom house không thấy |
| `~/Projects/thomhouse-analytics` | Chỉ có `AGENTS.md` với một dòng tiêu đề |
| `~/Projects/thomhouse-academy-daily` | Có trang landing page, bộ công cụ video `kit/src/th.css` và `kit/src/th.js`, font đã tải về và hai báo cáo thương hiệu `docs/thomhouse-deep-dive.md`, `docs/thomhouse-academy-daily-brief.md` |
| Bản sao Drive | `documentation/06-brand-voice-identity.md` §5 tả nhận diện thị giác bằng lời; `knowledge-base/00-brand-essence.md` và `01-tone-voice.md` ghi quy tắc viết tên, slogan và kiểu chữ trên menu. Không file nào ghi mã màu hay tên font cụ thể |
| Bộ ảnh menu | Có một khuôn trình bày thống nhất, tả ở mục dưới |

Comment ở đầu khối CSS của trang landing page ghi rằng token màu được sinh từ design system. Tôi không tìm thấy design system đó ở bất kỳ nơi nào kể trên. Trang landing page mở đầu bằng đoạn mã runtime của artifact claude.ai. Từ dấu hiệu đó, tôi suy luận trang này từng được lưu từ một artifact; artifact đó không có trong danh sách artifact mà tài khoản này mở được.

### Màu và token cụ thể là gì?

Toàn bộ token nằm ở dòng 12 của trang landing page. Trang có hai giao diện: Đêm (nền tối, mặc định) và Ngày (nền sáng màu ngọc trai). Tên token là tiếng Việt không dấu: `nuoc` là nước, `anh` là ánh sáng, `muc` là mực, `kim` là vàng kim, `thach-anh` là thạch anh hồng, `dao` là màu đào, `son-mong` là sơn mài đỏ.

| Nhóm | Token và mã màu |
|---|---|
| Nền tối | `--nuoc-950` `#13120e`, `--nuoc-900` `#1c1a15`, `--nuoc-850` `#26231d`, `--nuoc-800` `#2f2b21`, `--nuoc-700` `#3c362c`, `--nuoc-500` `#6b6150` |
| Nền sáng | `--anh-50` `#faf7f2`, `--anh-100` `#f2ece4`, `--anh-200` `#e4dbcf` |
| Chữ trên nền sáng | `--muc-900` `#1f1c17`, `--muc-600` `#5a5146`, `--muc-500` `#6b6257` |
| Chữ phụ trên nền tối | `#cdc3b6` và `#a89e90` |
| Màu nhấn | `--kim` `#cfae7b` trên nền tối, `--kim-ink` `#7d5f31` trên nền sáng, `--thach-anh` `#e8c3bd` (màu đặc trưng, dùng cho viền focus), `--dao` `#d9a592`, `--son-mong` `#7a2a2e` |
| Menu thư giãn, Sắc trà đường nâu | nền `#7a6250`, sẫm `#2b221b`, sáng `#e6c7a8`, chữ `#6a5242` |
| Menu khỏe, Sắc ngải cứu | nền `#6e7150`, sẫm `#1f2117`, sáng `#cfd1a8`, chữ `#585b3c` |
| Menu phụ nữ, Sắc thạch anh hồng | nền `#8b5b5a`, sẫm `#2a1c1d`, sáng `#ecc4be`, chữ `#7d4f4e` |
| Menu da, Sắc ngọc trai | nền `#a8968a`, sẫm `#2a2522`, sáng `#efe5dc`, chữ `#6b5d53` |
| Menu tóc, Sắc bồ kết | nền `#a7844c`, sẫm `#2b2215`, sáng `#e8d09f`, chữ `#7a5a26` |
| Khoảng cách | `--space-1` đến `--space-10`: 4, 8, 12, 16, 24, 32, 48, 56, 88, 160 px |
| Bo góc | `--radius-xs` 4 px, `--radius-sm` 10 px, `--radius-md` 16 px, `--radius-lg` 28 px, `--radius-pill` 999 px |
| Đường cong chuyển động | `--ease-out` `cubic-bezier(0.16, 1, 0.3, 1)`, `--ease-mask` `cubic-bezier(0.625, 0.05, 0, 1)`, `--ease-io` `cubic-bezier(0.65, 0, 0.35, 1)` |
| Lớp phủ | hạt nhiễu SVG `--grain` với độ đậm `--grain-o` 0,05; kính mờ `--glass-blur` 18 px |

Trang landing page ghi chữ trên ba sắc thư giãn, khỏe và phụ nữ là màu sáng `#faf7f2`, còn chữ trên sắc da và sắc tóc là màu tối `#13120e`. Báo cáo `docs/thomhouse-deep-dive.md` của dự án Academy đã tính tỉ lệ tương phản theo chuẩn WCAG (chuẩn dễ đọc của web, chữ nhỏ cần tỉ lệ từ 4,5 trở lên). Theo báo cáo đó, chữ sáng trên nền Sắc ngọc trai chỉ đạt 2,66. Tôi không tính lại các tỉ lệ này.

Màu trên web và màu trên menu in chưa khớp nhau. Báo cáo Academy đo màu xuất hiện nhiều nhất trên ảnh menu in: menu da là `#927c6c`, menu khỏe là `#756150`, menu tóc là `#a6834e`, menu triệt lông là `#ddd5cb`. Tài liệu `06-brand-voice-identity.md` §5.1 lại tả menu da là xám pha xanh ô liu nhạt. Như vậy, menu da có ba cách tả màu khác nhau. Ảnh không gian thật cũng không dùng các sắc này: tường kem xám, sàn terrazzo, gỗ sẫm và mảng tường màu nghệ (mục ảnh ở trên).

### Font nào?

Trang landing page tải bốn font từ Google Fonts:

- Cormorant Garamond, nét 300–600 và nghiêng, cho tiêu đề (`--font-display`).
- Montserrat, nét 300–700, cho chữ thường, nhãn và giá (`--font-body`); font dự phòng là Be Vietnam Pro.
- Ms Madi, chữ viết tay, cho lời mang tính cá nhân (`--font-script`).
- Sacramento, chữ viết tay, cho dòng «welcome to» ở màn chào (`--font-cover`).

Báo cáo Academy ghi Sacramento không có dấu tiếng Việt, ba font còn lại có. Dự án Academy đã tải sẵn file font về `/Users/luuphuc/Projects/thomhouse-academy-daily/assets/fonts/`: Cormorant Garamond (400 đến 700, kèm nghiêng), Montserrat (Regular đến ExtraBold) và Be Vietnam Pro (400 đến 700), kèm giấy phép OFL.

Font tiêu đề trên menu in là một font serif nét tương phản cao, khác Cormorant Garamond. Tôi chưa nhận ra tên font này, và báo cáo Academy cũng ghi chưa nhận ra. Tài liệu Drive chỉ tả là serif lớn, giống Cormorant hoặc Playfair Display (`06-brand-voice-identity.md` §5.2).

### Logo trông thế nào?

Chưa có file logo gốc. Bản logo dạng số mà tôi tìm được chỉ có khối SVG `wm-sym` ở dòng 518 của trang landing page, khung `0 0 7049 1175`, gồm một đường path. Kiểu tọa độ `scale(0.1, -0.1)` cho thấy đây là bản vẽ lại tự động từ ảnh bitmap (suy luận). Tôi đã chuyển khối này thành ảnh PNG bằng `rsvg-convert` để xem. Logo là chữ thường `thom house`, kiểu chữ không chân, nét rất đậm, đầu nét tròn. Cùng kiểu chữ đậm này xuất hiện trong dòng «Made by thomhouse team» trên bộ ảnh menu.

Ngoài đời, thương hiệu xuất hiện ở bốn dạng khác:

- bảng chữ trên tường lễ tân: in hoa `THOM HOUSE`, không chân, nét mảnh, có đèn hắt (IMG_7516.jpg, IMG_7861.jpg);
- tấm gỗ trên bàn chờ: in hoa, kiểu chữ có chân (IMG_7864.jpg);
- áo thun đen: in hoa, chữ trắng không chân, nét đậm (IMG_7891.jpg);
- bảng wifi: in hoa, không chân (IMG_7518.jpg).

### Khuôn trình bày của menu in ra sao?

Tôi xem bốn trang: trang 1 menu da, trang 2 menu khỏe, trang 1 menu triệt lông và trang 14 menu tóc. Bốn trang dùng chung một khuôn:

- Viền ngoài một màu nâu, ảnh bo góc ở giữa.
- Góc trên bên phải ghi «thom house healing studio -Since 2019». Menu da ghi «thom house facial studio -Since 2019».
- Mép trái có slogan in dọc: «Beauty is the harmony of body and soul.»
- Tên dịch vụ hoặc tên menu dùng font serif lớn, chữ thường.
- Dòng «Made by thomhouse team», trong đó chữ `thomhouse` in đậm.
- Đáy trang có biểu tượng ghim vị trí và địa chỉ «72 đường số 37, phường Tân Hưng quận 7».
- Trang 2 menu khỏe ghi thêm «Fanpage: Thơm House» in dọc ở mép phải.
- Trang 14 menu tóc dùng thẻ bo góc nền nâu trong, hình bàn tay vẽ bằng nét trắng mảnh, tiêu đề in hoa đậm không chân, thời lượng và giá in nghiêng.

Trang 14 menu tóc ghi năm lựa chọn thêm kèm giá: Detox da đầu, Massage mặt, Massage tay, Massage cổ vai gáy, Massage chân. `data/services.json` hiện không có năm lựa chọn này. Việc chép lại bộ ảnh menu nằm ngoài phần việc của báo cáo này, nên tôi chỉ ghi lại điểm thiếu.

### Giọng văn và quy tắc thương hiệu ghi ở đâu?

Các quy tắc chữ nghĩa nằm trong bản sao Drive và đã được rà ở `research/01-knowledge-audit.md`. Phần liên quan đến nhận diện gồm:

- Tên đầy đủ `thom house healing studio`, viết thường, không dấu; `Thơm House` chỉ dùng cho Fanpage và lời cá nhân (`knowledge-base/00-brand-essence.md` dòng 24–34, `documentation/06-brand-voice-identity.md` dòng 9–20).
- Slogan «Beauty is the harmony of body and soul.» kèm bản dịch «Vẻ đẹp là sự hòa hợp giữa cơ thể và tâm hồn.» (`00-brand-essence.md` §2).
- Tông hình ảnh tả bằng lời: nâu trầm, ánh sáng dịu, khăn ấm, nến, tinh dầu (`00-brand-essence.md` §3).
- Năm emoji được phép theo từng mảng (`06-brand-voice-identity.md` §5.4). Bộ quy định video của Academy lại cấm emoji trong video (`docs/thomhouse-academy-daily-brief.md` §3.2). Chatbot theo quy định nào là việc của bước soạn giọng chatbot, tôi không quyết ở đây.

Trang landing page còn ghi một số dữ kiện không có nguồn từ chủ studio, ví dụ «Giờ đón khách Từ 9h sáng» và đường dẫn `beacons.ai/thomhouseq7`. Tôi không biết ai viết trang này và lấy số liệu từ đâu. Vì vậy, tôi đề xuất chatbot không lấy dữ kiện kinh doanh từ trang landing page; chỉ dùng trang này làm nguồn màu và font.

### Video và mẫu trình bày đã có gì?

Dự án Thomhouse Academy dựng video 16:9 bằng HyperFrames và GSAP. `kit/src/th.css` chép token từ trang landing page (dòng 23–36) và khai báo font local. `kit/src/th.js` chứa bảng màu, hàm chạy phụ đề và các hàm vẽ nền giấy, hạt nhiễu, viền nỉ, dải lượn sóng. Thư mục `formats/` có sáu video ngày 08/11 về da, mỗi video có bản `src/th.css` riêng. Thư mục `out/` có thư mục kết quả của hai video đầu; thư mục của video thứ nhất có file mp4 và ảnh thumbnail.

Dự án chatbot này chưa dùng hệ màu thương hiệu. Console nhân viên dùng bảng màu riêng: nền `#f7f5f2`, màu nhấn nâu `#6b4f3a`, font hệ thống (`apps/console/src/styles.css` dòng 1–40). Console chỉ nhân viên dùng, nên việc chưa theo thương hiệu không ảnh hưởng khách.

## Thư mục Drive tổng quan có gì mới từ ngày 07/11?

Không có file mới. Tôi tải trang thư mục gốc và năm thư mục con bằng `curl -sL -A Mozilla/5.0`, rồi đọc danh sách file trong biến `window['_DRIVE_ivd']` bằng một script Python ngắn. Danh sách gồm 4 thư mục con và 5 file ở thư mục gốc, 14 file trong `documentation`, 3 file và thư mục `02-services` (6 file) trong `knowledge-base`, 5 file trong `raw-content`, 1 file trong `.claude`.

So với `sources/drive-index.md`, 32 file trong bản sao có cùng ID và tên. Dung lượng trên Drive bằng đúng dung lượng file local ở cả 32 file. Ngày sửa trên Drive bằng ngày ghi trong `drive-index.md`. File sửa gần nhất vẫn là `documentation/06-brand-voice-identity.md`, ngày 2026-11-03. Các thư mục con đều mang ngày sửa 2026-11-01.

Hai file trên Drive chưa có trong bản sao:

| File | Drive ID | Dung lượng | Ngày sửa trên Drive |
|---|---|---|---|
| `.claude/settings.local.json` | `1dUrxIAmd95091DI_hdv2dahlosTYsfBG` | 293 byte | 2026-07-26 |
| `.DS_Store` | `1DoSXVJy4tLJ2OreW6ctrZAk3vA9IBiEL` | 14.340 byte | 2026-11-01 |

Tôi không tải hai file này. Theo quy tắc an toàn tôi phải theo, việc tải file cần anh đồng ý trực tiếp trong chat, và yêu cầu của workflow không thay được sự đồng ý đó. Dự án Academy đã có một bản `.DS_Store` cùng dung lượng 14.340 byte (`/Users/luuphuc/Projects/thomhouse-academy-daily/source/#1-thomhouse-overview/.DS_Store`). Tôi đọc tên file trong bản đó: chỉ có bốn thư mục `.claude`, `documentation`, `knowledge-base`, `raw-content`, không có tên file lạ. Nếu anh muốn đọc `settings.local.json`, link tải là `https://drive.usercontent.google.com/download?id=1dUrxIAmd95091DI_hdv2dahlosTYsfBG&export=download&confirm=t`.

## Những phát hiện này ảnh hưởng tới chatbot ra sao?

Chatbot đã đọc được giá và quy trình, nhưng chưa có câu trả lời cho các câu hỏi về không gian. Tôi đề xuất năm việc, xếp theo mức ảnh hưởng tới khách.

1. Khi khách hỏi phòng riêng, giường, phòng tắm hay chỗ để xe, chatbot nói chưa có thông tin và chuyển cho nhân viên. Bộ ảnh không chụp phòng, giường, phòng tắm hay chỗ để xe. Điểm yếu: đây là câu hỏi phổ biến của khách spa, nên nhân viên sẽ phải trả lời nhiều lần cho tới khi chủ studio bổ sung dữ kiện.
2. Chatbot được nói các dữ kiện thấy trực tiếp trong ảnh: mặt tiền kính, có sofa chờ và nước uống, có tủ khóa gửi đồ, có wifi. Với tầng trên, chatbot chỉ nên nói có khu nail, thư giãn và chăm sóc tóc theo chữ trên tường, chưa nên khẳng định studio đang làm nail. Điểm yếu: ảnh không có ngày chụp, nên không gian có thể đã đổi.
3. Chatbot không gửi mật khẩu wifi qua Zalo và không gửi số tài khoản. Khách xem mật khẩu trên bảng tại studio; số tài khoản do nhân viên gửi. Điểm yếu đã nêu ở phần anh cần duyệt: khách chờ lâu hơn.
4. Chatbot viết tên thương hiệu là `thom house`, theo tài liệu Drive, dù bảng hiệu ngoài đời in hoa.
5. Nếu sau này chatbot có trang web cho khách, ví dụ trang đặt lịch, tôi đề xuất dùng token của trang landing page và font Cormorant Garamond với Montserrat. Điểm yếu: hệ màu này chưa được chủ studio duyệt, và màu web lệch với màu menu in và màu không gian thật.

## Tôi đã chạy và đọc gì?

- Xem cả 12 ảnh trong `sources/drive-resources/thomhouse-space/` sau khi thu nhỏ còn cạnh dài 1.400 điểm ảnh bằng `sips -Z 1400`. Cắt và phóng to bảng wifi (IMG_7518.jpg), màn hình điện thoại (IMG_7874.jpg), giá vẽ cạnh tủ khóa (IMG_7516.jpg) và khung cửa kính (IMG_7882.jpg) bằng `sips -c`. Đo màu trung bình bằng `sips` thu ảnh cắt về 1×1 điểm ảnh rồi đọc file BMP bằng `python3 -I`.
- Chạy `ffprobe` trên `voice-chi-Thom.m4a` và `thom-sample-clean.wav`; chạy `which`, các lệnh `python3 -I -c "import ..."`, `ffmpeg -filters`, `pipx list`, `uv tool list` và `find` tìm model whisper.
- Tìm chữ thom house, thomhouse và token `nuoc-950` trong sáu dự án được giao bằng `grep`, giới hạn theo loại file với các dự án lớn.
- Đọc dòng 2–120, 740–770, 820–870 và 1060–1100 của trang landing page, cùng các dòng `grep` tìm được về font, logo và slogan; xuất khối SVG `wm-sym` ra file và chuyển sang PNG bằng `rsvg-convert` trong thư mục scratchpad.
- Đọc `docs/thomhouse-deep-dive.md` (dòng 138–184, 236–271), `docs/thomhouse-academy-daily-brief.md` (dòng 85–180), `kit/src/th.css` và phần đầu `kit/src/th.js` của dự án Academy.
- Đọc `documentation/06-brand-voice-identity.md` (dòng 1–30, 180–215), `knowledge-base/00-brand-essence.md` (dòng 20–60, 185–195) và `knowledge-base/01-tone-voice.md` (dòng 115–130) trong bản sao Drive; đọc phần đầu `research/01-knowledge-audit.md`; tra `data/services.json` và `data/business-facts.json` bằng `grep` và `python3 -I`.
- Xem bốn trang menu (menu da trang 1, menu khỏe trang 2, menu triệt lông trang 1, menu tóc trang 14) sau khi thu nhỏ.
- Gọi Artifact `list` với `scope: types`, với `type: Design System` và với `scope: all`.
- Tải sáu trang thư mục Drive về scratchpad bằng `curl` và đọc danh sách file bằng `python3 -I`; đọc tên file trong bản `.DS_Store` của dự án Academy.

Tôi không sửa file nào ngoài báo cáo này, không gửi tin Zalo, không chạy lệnh `zalo-agent` nào và không tải file nào từ Drive.

## Nói ngắn gọn nhất

thom house chưa có design system chính thức. Nguồn màu và font đầy đủ nhất là trang landing page trong dự án Thomhouse Academy, với nền tối `#13120e`, nền sáng `#f2ece4`, vàng kim `#cfae7b`, năm sắc cho năm menu, font Cormorant Garamond cho tiêu đề và Montserrat cho chữ thường. Logo chỉ có một bản vẽ lại dạng SVG, còn bảng hiệu ngoài đời in hoa `THOM HOUSE`. Mười hai ảnh không gian chỉ chụp tầng trệt: quầy lễ tân, sofa chờ, tủ khóa, cầu thang có chữ «Nail» và «Relax and Hair care», mặt tiền kính. Ảnh không cho biết gì về phòng, giường hay chỗ để xe, nên chatbot phải chuyển các câu hỏi đó cho nhân viên. File ghi âm chị Thơm dài 31,04 giây chưa được chép lời, vì máy chưa có công cụ chạy local. Thư mục Drive không có file mới; hai file chưa có trong bản sao là file cấu hình và file hệ thống của máy Mac, và tôi chưa tải. Anh cần quyết bốn việc: chatbot có được gửi số tài khoản không, thời lượng đúng của Gói Mụn 5 in 1, có ghi các dữ kiện không gian thấy trong ảnh vào `data/business-facts.json` không, và có tải file `.claude/settings.local.json` về đọc không.

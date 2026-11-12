# Repo GitHub cho bot Zalo cá nhân: có repo nào nên thay stack hiện tại không?

Ngày rà: 2026-11-08. Tôi chỉ đọc mã nguồn và tài liệu. Tôi không cài thư viện, không chạy mã của repo nào, không đăng nhập Zalo và không gửi tin nào.

## Phần anh cần duyệt

Không repo nào nên thay stack hiện tại, kể cả `aizaloapp/zalo-flow`. Trong báo cáo này, stack hiện tại là năm phần đang chạy trên máy Mac: listener `zalo-agent listen`, server chạy bằng `wrangler dev --local`, runner gọi `claude -p`, bridge gửi tin đã duyệt và console cho nhân viên. Phần giữ đăng nhập Zalo, nhận và gửi tin là engine `@ardennguyen/zalo-agent-cli` 2.5.9.

`zalo-flow` là một app hoàn chỉnh: giữ phiên Zalo cá nhân, có giao diện chat, CRM, chiến dịch gửi tin và AI tự trả lời. Tôi không đề xuất dùng `zalo-flow`, vì ba lý do.

Thứ nhất, `zalo-flow` thiếu đúng các phần anh đã chốt cho chatbot thom house. Server của `zalo-flow` không có hàng chờ để nhân viên duyệt câu trả lời trước khi gửi. Server cũng không gửi tin xin đồng ý, không gọi được `claude -p` và không có bước kiểm câu trả lời theo bảng giá.

Thứ hai, đọc mã, tôi thấy `zalo-flow` có lỗ hổng cho phép người khác gửi tin bằng tài khoản Zalo của anh. Hai đường webhook `/api/webhook/generic` và `/api/webhook/chatwoot` gửi tin ra Zalo mà không kiểm token, kể cả khi anh đã đặt `ADMIN_API_TOKEN`. Hai cách cài theo README đều ghi `HOST=0.0.0.0` và để trống `ADMIN_API_TOKEN`. Với cấu hình đó, theo suy luận từ mã, mọi máy cùng mạng Wi-Fi đọc được toàn bộ hội thoại và gửi tin thay anh. Tôi chưa chạy để thử.

Thứ ba, `zalo-flow` mới hai tháng tuổi, một người viết, dùng `zca-js` 2.1.2 cũ hơn engine hiện tại. Lệnh lint trong `package.json` chỉ in ra dòng chữ báo đã qua, không kiểm gì.

Đề xuất của tôi: giữ stack hiện tại và chỉ lấy vài ý tưởng từ các repo (danh sách ở mục cuối). Repo `cuongdev/hermes-zalo-plugin` (giấy phép MIT) là phương án dự phòng cho riêng phần engine, nếu engine hiện tại gặp lỗi khi chạy với Zalo thật.

Điểm yếu của đề xuất này: stack hiện tại chưa gửi tin nào qua Zalo thật, nên tôi đang so một hệ thống chưa thử thật với các repo tôi cũng chưa chạy. Mọi repo trong báo cáo, kể cả engine hiện tại, đều dựa vào `zca-js` không chính thức, nên rủi ro tài khoản Zalo bị khóa không đổi dù anh chọn repo nào. Giữ stack hiện tại cũng có nghĩa là tôi tiếp tục tự bảo trì server, runner, bridge và console, thay vì nhận một app làm sẵn.

Anh không cần quyết gì ngay. Nếu anh vẫn muốn thử `zalo-flow`, mục "Nếu vẫn muốn thử zalo-flow thì cần làm gì?" ghi các bước giảm rủi ro tối thiểu.

## Tôi đã tìm và đọc những gì?

Tôi chạy `gh search repos --topic zalo-bot --sort updated --limit 60` với các trường tên, mô tả, ngày cập nhật, số sao, giấy phép, ngôn ngữ và trạng thái lưu trữ. Topic `zalo-bot` chỉ có 26 repo. Tôi chạy thêm cùng lệnh cho các topic `zalo` (60 repo, đã chạm giới hạn 60), `zca-js` (15), `zalo-api` (7), `zalo-personal` (2) và `zalo-chatbot` (2). Tôi tải README của khoảng 40 repo qua `gh api repos/<repo>/readme` và lọc theo từ khóa để biết repo dùng lớp Zalo nào. Phân loại các repo không clone chỉ dựa trên README.

Tôi clone nông (`git clone --depth 1`, tắt git hook) năm repo vào `sources/repos/`:

| Thư mục | Commit đã đọc | Ngày commit cuối |
|---|---|---|
| `aizaloapp-zalo-flow` | `0a0e985c3a1cd8a212f542f7fd958fe3d608837c` | 2026-10-26 |
| `vuhai2002-zalo-agent` | `4346f295e9dbd787a427993ddf3b083ebb57cf15` | 2026-10-25 |
| `cuongdev-hermes-zalo-plugin` | `f7d30ed787a9bf97fbcf4b309bc86f7b5cf1012d` | 2026-10-09 |
| `monas-team-zaloclaw` | `4c493a9aac70ced8525d1ea24ee3063e3623f923` | 2026-10-26 |
| `babyvibe-deplao-builder` | `2162f077d49f3b990121717fe6596fb3f0941e2f` | 2026-11-06 |

Bản `deplao-builder` được clone thêm cờ `--filter=blob:limit=2m`, nên các file lớn hơn 2 MB (chủ yếu ảnh và tài nguyên) không có trong thư mục. Số commit và người đóng góp lấy từ `gh api`. Phiên bản `zca-js` lấy từ `registry.npmjs.org`. Tôi đọc bằng `grep`, `sed` và `wc`, không chạy test của repo nào. Các con số "test đều qua" trong README là lời của tác giả, tôi chưa kiểm.

## Topic zalo-bot có những repo nào?

Mỗi repo bot Zalo nói chuyện với Zalo qua một hay nhiều lớp dưới đây. Lớp quyết định bot dùng được loại tài khoản nào, nên tôi chia repo theo lớp trước.

Lớp thứ nhất là `zca-js`, thư viện không chính thức dựng lại giao thức của Zalo Web. Lớp này điều khiển tài khoản Zalo cá nhân đăng nhập bằng mã QR, và tài khoản có thể bị khóa. Engine hiện tại dùng lớp này.

Lớp thứ hai là Zalo Bot Platform, API chính thức để tạo tài khoản bot. Chủ bot tạo bot trong mini app Zalo Bot Creator, tên bot phải bắt đầu bằng chữ "Bot", và khách phải nhắn vào tài khoản bot đó. README của `vuhai2002/zalo-agent` ghi rằng Zalo Bot Platform khác Zalo OA, không có rủi ro khóa tài khoản, chỉ gửi được chữ thường và không gửi được file. Vì khách phải nhắn vào một tài khoản bot riêng chứ không nhắn vào Zalo cá nhân của studio, lớp này nằm ngoài hướng anh đã chọn. Tôi chỉ ghi lại để anh biết lớp này tồn tại.

Lớp thứ ba là tự động hóa trình duyệt: chèn script vào Zalo Web hoặc Zalo PC.

Lớp thứ tư là API chính thức của Zalo OA, lớp mà anh đã bỏ ngày 2026-11-08. Trong topic `zalo-bot`, không repo nào chỉ dùng OA; `zalo-flow` và `TheOwlOps/ChannelHub` có thêm một nhánh OA bên cạnh tài khoản cá nhân.

| Lớp Zalo | Số repo | Repo |
|---|---|---|
| Tài khoản cá nhân qua `zca-js` hoặc API nội bộ | 9 | `aizaloapp/zalo-flow`, `vuhai2002/zalo-agent` (có cả Zalo Bot Platform), `monas-team/zaloclaw`, `quangminh1212/Hermes_Zalo`, `alden-project/alden-bot`, `TheOwlOps/ChannelHub` (có cả OA), `TriTue2011/zalo_bot`, `minhhoasqtt-prog/app-zalo-marketing`, `ElectroHeavenVN/ZepLaoSharp` |
| Zalo Bot Platform | 16 | `HUY1602/Bot-chat-Zalo`, `tidusvn05/zalo-bot`, `hecigo/n8n-nodes-zalo-platform`, `greennode-samples/sample-zalo-restaurant`, `luank3/go-zalo-bot-api`, `KaiyoDev/zalo-bot-js`, `NightOwl-VN/zalobot-sdk-php`, `NightOwl-VN/zalobot-sdk`, `hvduong2k5/zalo-bot-java-sdk`, `trongnguyenbinh/zalo-bot-mcp`, `thenoppy12/java-zalo-bot`, `zylos-ai/zylos-zalo`, `Dyu-36/ScreenPilot`, `minhdevtry/AI-Teacher-Assistant-Agent`, `maingocanh1702/my-money-went-bot`, `ductrong-grb/zalo-group-bot-nodejs` |
| Script chèn vào Zalo Web hoặc Zalo PC | 1 | `ElectroHeavenVN/Zalo-F12` |

Ở các topic liên quan, có thêm năm repo đáng ghi lại. `cuongdev/hermes-zalo-plugin` và `babyvibe/deplao-builder` được rà kỹ ở mục sau. `RFS-ADRENO/zca-js` là chính thư viện `zca-js` (718 sao, MIT); bản mới nhất trên npm là 2.2.0, phát hành ngày 2026-09-09. `ChickenAI/zalo-node` là node n8n cho Zalo cá nhân (153 sao), lần push cuối ngày 2026-04-07. `dennyducnguyen/penai` (topic `zalo`) và `minhhoasqtt-prog/app-zalo-marketing` (topic `zalo-bot`) có những phần gần với chatbot thom house, nên tôi đọc README và giấy phép của hai repo này ở mục "Hai repo gần mục tiêu nhưng không clone".

Một repo có dấu hiệu đáng ngờ: `zainkalkhan/zalo-personal`. README của repo này giới thiệu công cụ đăng nhập Zalo cá nhân, nhưng mọi nút tải đều trỏ tới cùng một file zip nằm trong thư mục `ribbed/` của repo. Repo không có giấy phép và gắn các topic không liên quan như `hacktoberfest`, `awk`, `scp`. Kiểu repo này giống các repo mồi để phát tán file độc hại. Tôi không tải file zip đó và chưa kết luận chắc.

## zalo-flow là gì?

`zalo-flow` là app Node.js chạy một server Express ở port 3000. Server giữ phiên Zalo cá nhân qua `zca-js`, lưu hội thoại vào SQLite (module `node:sqlite` có sẵn trong Node) và phục vụ một trang web có giao diện chat, CRM và cài đặt AI. Repo có bản cài `.exe` cho Windows, Docker và một extension Chrome. Trang chủ của dự án là `aizalo.com`. README còn dẫn tới một API trên RapidAPI và các skill trên ClawHub của cùng nhóm.

| Mục | Giá trị |
|---|---|
| Phiên bản | 1.5.0; bản phát hành `v1.5.0` ngày 2026-10-04 |
| Ngày tạo repo | 2026-09-03 |
| Commit | 160, toàn bộ của tài khoản `aizaloapp` |
| Sao, fork | 18 sao, 10 fork |
| Thư viện Zalo | `zca-js` 2.1.2, khóa cứng trong `package.json`; bản này phát hành ngày 2026-03-17 |
| Mã nguồn | `src/`: 42 file, 16.081 dòng. `public/app.js`: 10.686 dòng. `test/`: 17 file, 5.067 dòng |
| Dependency khai báo | 8 gói: `axios`, `dotenv`, `express`, `image-size`, `multer`, `qrcode`, `qrcode-terminal`, `zca-js` |

Các tính năng tôi thấy trong mã:

- Nhiều tài khoản Zalo trong một tiến trình (`src/utils/account-manager.js`).
- AI tự trả lời, gom các tin khách gửi liên tiếp trước khi gọi model, khóa mỗi hội thoại chỉ một lượt soạn tại một thời điểm, và tự chuyển sang nhà cung cấp dự phòng khi gặp lỗi 429 hay 5xx (`src/adapters/ai-agent.js`, 1.551 dòng).
- Nhà cung cấp model: Gemini, OpenAI, DeepSeek, Groq, OpenRouter, Ollama và Z.AI. Không có Anthropic và không có `claude -p`.
- Kho tri thức dạng Markdown, tìm theo BM25 (`src/services/second-brain/`). BM25 là cách xếp hạng đoạn văn theo số lần từ khóa xuất hiện.
- Đồng bộ hai chiều với Chatwoot, chuyển tin vào sang một webhook ngoài (n8n, Dify) và nhận lệnh gửi tin từ webhook đó.
- Chiến dịch gửi tin hàng loạt, tin hẹn giờ, tin mẫu có spintax (`src/routes/campaigns.js`, `src/utils/spintax.js`). Spintax là cách sinh nhiều biến thể của cùng một câu để mỗi người nhận một bản hơi khác.
- Extension Chrome chạy trên `chat.zalo.me`, gọi `POST /api/ai/suggest` để lấy ba gợi ý trả lời và chèn gợi ý được chọn vào ô soạn tin của Zalo Web.
- Một nhánh Zalo OA (`src/routes/oa-routes.js`, `src/utils/oa-token-manager.js`).
- Nút cập nhật một lần bấm, sao lưu, theo dõi RAM và tự khởi động lại.

## zalo-flow có những phần chatbot thom house cần không?

Chỉ có một phần: nhân viên tiếp quản khi chủ tài khoản tự gõ. `zalo-flow` bật `selfListen: true` (`src/zalo-client.js` dòng 106), nên nhận được cả tin chủ tài khoản gửi từ điện thoại. Khi tin của chính tài khoản không trùng với tin bot vừa gửi trong 30 giây gần nhất và chưa có `msgId` trong SQLite, `zalo-flow` coi đó là người thật gõ và dừng bot ở hội thoại đó. Thời gian dừng mặc định là 15 phút (`adminCooldownMinutes`, `src/adapters/ai-agent.js` dòng 235). Stack hiện tại dừng 12 giờ và đã nhận ra tin của chính bot bằng mã tin rồi mới tới nội dung.

Các phần còn lại không có:

- Duyệt trước khi gửi: server của `zalo-flow` không có hàng chờ duyệt. Khi bật AI, câu model viết ra được gửi thẳng cho khách sau thời gian gom tin (mặc định 3 giây). Trong mã, tôi chỉ thấy extension gợi ý trên Zalo Web cho người chọn câu AI soạn trước khi gửi; nhân viên chọn một gợi ý rồi tự bấm gửi.
- Tin xin đồng ý: tôi tìm `consent`, `đồng ý`, `opt-out`, `privacy` trong `src/` và không thấy kết quả nào.
- Soạn bằng `claude -p`: không có. Muốn dùng phải tự viết một lớp giả API kiểu OpenAI bọc `claude -p`, vì `zalo-flow` cho đổi base URL của nhà cung cấp `openai`.
- Trả lời theo bảng giá có bước kiểm: kho tri thức chỉ đưa đoạn văn vào prompt. Không có bước nào so con số trong câu trả lời với `data/services.json` như checker của stack hiện tại.

Có thêm một điểm, tôi suy luận từ hai repo khác chứ chưa thử: extension gợi ý cần mở Zalo Web, trong khi `zca-js` của chính `zalo-flow` cũng đang giữ một phiên Zalo Web. README của `vuhai2002/zalo-agent` ghi rằng mở Zalo Web trên trình duyệt sẽ đẩy listener của bot ra. Mã engine hiện tại (`src/core/daemon-channel.js`) cũng ghi rằng Zalo chỉ cho một phiên web mỗi tài khoản. Nếu đúng như vậy, dùng extension sẽ làm listener của `zalo-flow` rớt và kết nối lại liên tục.

## zalo-flow có vấn đề bảo mật nào?

Tôi không thấy mã bị làm rối, không thấy `eval`, và không thấy server gửi dữ liệu về `aizalo.com`. Các host bên ngoài trong mã là API của các nhà cung cấp model, Chatwoot, Zalo và `api.github.com` (để kiểm phiên bản mới). Tôi thấy năm vấn đề, xếp từ nặng tới nhẹ. Tất cả là suy luận từ đọc mã, tôi chưa chạy để thử.

**1. Hai đường webhook gửi tin Zalo mà không cần token.** `src/index.js` dòng 574–582 đăng ký `POST /api/webhook/chatwoot` và `POST /api/webhook/generic` mà không gắn `requireAuth`. Bộ chặn CSRF (`src/middleware/auth.js` dòng 47–48) bỏ qua mọi đường có chữ `/webhook`. Đường `/api/webhook/generic` nhận `threadId` và `message`, rồi gọi thẳng `zaloClient.sendMessage` (`src/adapters/generic-webhook.js`). Hai đường này luôn bật, kể cả khi anh không cấu hình Chatwoot hay webhook ngoài.

Hệ quả là bất kỳ ai gửi được request tới port 3000 cũng gửi được tin tới bất kỳ ai bằng tài khoản Zalo của anh. Server còn đọc dạng form (`express.urlencoded`, `src/index.js` dòng 56). Vì vậy, một trang web anh mở trong trình duyệt có thể tự gửi một form tới `http://127.0.0.1:3000/api/webhook/generic` mà không cần JavaScript đọc được kết quả. Các bản Chrome mới có thể chặn hoặc hỏi quyền khi một trang công khai gọi tới địa chỉ local. Tôi chưa kiểm hành vi đó trên trình duyệt của anh.

**2. Cấu hình mặc định mở server ra cả mạng LAN mà không có mật khẩu.** File `.env.example` dòng 7 và 13 ghi `HOST=0.0.0.0` và `ADMIN_API_TOKEN=` để trống. Lệnh `npm run init` (`bin/cli.js` dòng 104–106) cũng ghi đúng hai giá trị đó. Khi `ADMIN_API_TOKEN` trống, hàm `requireAuth` cho mọi request đi qua (`src/middleware/auth.js`). Bản Docker đặt `HOST=0.0.0.0` và publish port `3000:3000` ra máy chủ. Câu cảnh báo khi thiếu token bị tắt riêng trong Docker (`src/index.js` dòng 86). Vì vậy, nếu làm đúng README, mọi máy cùng mạng Wi-Fi đọc được toàn bộ hội thoại, xem mã QR đăng nhập và gửi tin thay anh.

**3. CORS chấp nhận mọi origin có chữ `localhost`.** `src/index.js` dòng 64 trả header cho phép đọc với mọi origin chứa chuỗi `localhost`, ví dụ một tên miền như `localhost.ten-mien-la.com`. Các route `GET` không qua bộ chặn CSRF. Khi chưa đặt token, một trang trên tên miền như vậy có thể đọc danh sách hội thoại và luồng tin mới qua trình duyệt của anh.

**4. Mã hóa phiên Zalo có khóa dự phòng công khai.** `src/utils/session-store.js` dòng 15 và `src/utils/ai-crypto.js` dòng 6 dùng chuỗi `zalo-flow-default-secret-key-32` làm khóa khi `SESSION_SECRET` trống. Khóa được tạo bằng một lần SHA-256 không có salt, và dữ liệu mã hóa bằng AES-CBC không kèm mã xác thực. Lệnh `npm run init` có tạo `SESSION_SECRET` ngẫu nhiên, nhưng người chép `.env.example` mà không sửa sẽ dùng chuỗi mẫu ghi sẵn trong file.

**5. Nút cập nhật chạy mã mới nhất trên nhánh `main`.** `POST /api/system/update` (`src/routes/updater.js` dòng 202) chạy `bin/standalone-updater.mjs`. Script này chạy `git stash`, `git pull origin main`, `npm install --omit=dev` rồi khởi động lại server (dòng 96 và 117). Việc này chỉ xảy ra khi có người bấm nút, không tự chạy. Token còn được nhận qua query string (`?token=`) và so bằng `!==`, nên token có thể lọt vào log và lịch sử trình duyệt.

## Chất lượng mã của zalo-flow thế nào?

Mã dễ đọc và có comment tiếng Việt; test dùng script Node tự viết. Có bốn dấu hiệu cho thấy mã chưa được kiểm kỹ:

- Lệnh `lint` trong `package.json` dòng 20 chỉ là `node -e "console.log('✅ Lint check passed')"`, tức là không kiểm gì.
- `src/index.js` nhập gói `ws` nhưng `package.json` không khai báo gói này; gói chỉ có mặt vì là dependency của `zca-js`.
- Nhiều file rất dài: `src/utils/local-store.js` 2.635 dòng, `src/zalo-client.js` 1.586 dòng, `public/app.js` 10.686 dòng.
- Repo chứa cả website marketing (132 file trong `website/`), script đẩy trang lên Google và Bing, và các file làm việc của AI agent (`AGENTS.md`, `SOUL.md`, `MEMORY.md`, `.agents/`). Đây là dấu hiệu, chưa phải bằng chứng, rằng phần lớn mã do AI agent viết và một người duyệt.

## Giấy phép của zalo-flow cho phép gì?

File `LICENSE` là MIT kèm Commons Clause v1.0. Commons Clause cấm "Sell", tức là bán cho bên thứ ba một sản phẩm hay dịch vụ mà giá trị chủ yếu đến từ phần mềm này, kể cả dịch vụ hosting, gói thuê bao hay tư vấn. File thêm một câu riêng: các quyền khác được giữ cho việc dùng phi thương mại, nghiên cứu và thử nghiệm cá nhân. `DISCLAIMER.md` ghi dự án chỉ dành cho nghiên cứu và học tập, và khuyên doanh nghiệp dùng Zalo OA.

Với cách dùng local, phi thương mại mà anh đã chọn, giấy phép này cho phép chạy và sửa. Câu thêm về "phi thương mại" không định nghĩa rõ việc một studio dùng app để trả lời khách của chính mình có tính là phi thương mại hay không. Engine hiện tại cũng vướng câu hỏi này, và file NOTICE của engine còn ghi rõ hơn: dùng trong hoạt động kinh doanh của một công ty không thuộc phạm vi CC BY-NC-SA 4.0 cấp phép (đã dẫn trong `research/04-zalo-repos-audit.md`). Bốn repo MIT trong báo cáo này không có giới hạn đó. Tôi không phải luật sư.

## Nếu vẫn muốn thử zalo-flow thì cần làm gì?

Nếu anh vẫn muốn chạy thử `zalo-flow`, tôi đề nghị bốn việc trước khi đăng nhập Zalo:

1. Đặt `HOST=127.0.0.1` và một `ADMIN_API_TOKEN` ngẫu nhiên dài trong `.env`, không dùng Docker.
2. Sửa mã để hai route `/api/webhook/*` cũng gọi `requireAuth`, hoặc xóa hai route đó.
3. Đặt `SESSION_SECRET` ngẫu nhiên, không dùng chuỗi mẫu.
4. Không bật AI tự trả lời. Chỉ dùng extension gợi ý, chấp nhận rủi ro listener bị đẩy ra như mục trên.

Làm xong bốn việc đó, `zalo-flow` vẫn chưa có tin xin đồng ý, `claude -p` hay bước kiểm theo bảng giá. Vì vậy, kể cả sau khi vá, `zalo-flow` chỉ là một công cụ chat thử, chưa thay được stack hiện tại.

## Bốn repo còn lại thế nào?

### vuhai2002/zalo-agent: agent AI làm trợ lý cá nhân, không có bước duyệt

Repo này là một agent AI tự hosting sống trong Zalo cá nhân, hoặc trong tài khoản Zalo Bot Platform. Giấy phép MIT. Repo được tạo ngày 2026-07-25, có 365 commit của một tác giả, 13 sao, phiên bản 0.4.0. Phần mã TypeScript không tính test khoảng 49.200 dòng (đếm trên `src/` và `web/src/`), kèm 262 file test. README ghi 2.657 test, tôi chưa chạy.

Agent có 15 công cụ (tìm web, đọc URL, tìm trong kho tài liệu, nhớ thông tin, tạo ảnh, tạo file Word và Excel, đặt lịch, tải video TikTok), có client MCP để nối server MCP bên ngoài, và có dashboard ở `127.0.0.1:3900` với mật khẩu băm bằng scrypt. Cookie Zalo và secret được mã hóa bằng AES-256-GCM. `zca-js` khóa ở bản 2.2.0. Nhà cung cấp model là endpoint kiểu OpenAI, API Anthropic hoặc API Google, gọi qua Vercel AI SDK. README tự nhận dự án cố ý không làm gửi tin hàng loạt.

Repo này không hợp với chatbot thom house vì bốn điểm. Bot trả lời thẳng, không có bước duyệt. `src/zalo/zalo-client.ts` dòng 12 đặt `selfListen: false`, nên bot không biết khi chủ tài khoản tự gõ; nhân viên chỉ tắt được bot theo từng hội thoại trên dashboard. Repo không có tin xin đồng ý. Bộ công cụ đọc web, gửi file và tạo tài liệu là quá rộng cho một bot trả lời khách, vì mỗi công cụ là thêm một đường để người lạ thử chèn lệnh vào prompt.

Repo này đáng đọc để học cách làm: chuyển Markdown sang định dạng chữ của Zalo theo giới hạn byte, tự gửi lại dạng chữ thường khi Zalo từ chối tin có định dạng, và bọc nội dung lấy từ ngoài trong thẻ có mã ngẫu nhiên tạo cho từng lần gọi. Giấy phép MIT cho phép chép mã, miễn là giữ thông báo bản quyền.

### cuongdev/hermes-zalo-plugin: cầu nối nhỏ, hợp làm engine dự phòng

Repo này là một tiến trình Node chạy liên tục, giữ một phiên Zalo cá nhân qua `zca-js`, đẩy tin vào qua Server-Sent Events (`GET /events`) và nhận lệnh gửi qua REST (`POST /send` và các route khác). Repo viết cho Hermes Agent, nhưng giao thức HTTP đủ chung để bridge của stack hiện tại gọi tới. Giấy phép MIT. Repo được tạo ngày 2026-06-04, có 43 commit, 49 sao, phiên bản 1.0.12, commit cuối ngày 2026-10-09. Phần JavaScript chính khoảng 2.400 dòng (`server.js` 701, `zaloClient.js` 1.185, `markdownToZalo.js` 312, `permissions.js` 151, `paths.js` 77), kèm adapter Python 1.414 dòng cho Hermes.

Điểm tốt khi đọc mã: server mặc định chỉ nghe ở `127.0.0.1` (`server.js` dòng 25), chỉ đọc body JSON nên không bị form từ trang web khác gọi tới, có token tùy chọn `ZALO_PLUGIN_TOKEN`, và chia 145 hàm của `zca-js` thành năm nhóm quyền (đọc, gửi, tương tác, quản lý, phá hủy); mặc định chỉ bật ba nhóm đầu. Khi đặt `ZALO_SELF_LISTEN=1`, server chuyển cả tin của chính tài khoản, nên server của stack hiện tại vẫn nhận ra được lúc chủ tài khoản tự gõ. Script `postinstall` chỉ tạo symlink cho lệnh CLI khi cài toàn cục.

Điểm yếu: một tác giả, ít commit. `package-lock.json` khóa `zca-js` 2.1.2, cũ hơn bản 2.2.0 có bản vá mà engine hiện tại dùng. Token mặc định không có, nên mọi tiến trình trên máy gửi tin được. Đổi sang repo này nghĩa là viết lại phần listener và phần gửi tin của bridge, rồi thử lại từ đầu với Zalo thật.

Repo này chỉ đáng cân nhắc trong một trường hợp: engine hiện tại gặp lỗi khi chạy với Zalo thật, ví dụ Zalo phản ứng xấu với việc mỗi lệnh `zalo-agent msg send` tự đăng nhập lại qua HTTP (đã ghi là chưa kiểm trong `docs/chay-local-zalo-ca-nhan.md`). Khi đó, một tiến trình giữ phiên Zalo suốt thời gian chạy như repo này là hướng thay ít tốn công nhất.

### monas-team/zaloclaw: plugin kênh Zalo cho OpenClaw

Repo này là plugin để gateway OpenClaw (một nền tảng agent AI cá nhân) nói chuyện qua Zalo cá nhân. Giấy phép MIT, phiên bản 2.5.11, 133 commit (83 của tác giả chính, 21 của Copilot), 24 sao, commit cuối ngày 2026-10-26. Mã TypeScript trong `src/` khoảng 8.300 dòng. Repo có commit sẵn file đã build `dist/index.js` (6.164 dòng); tôi chưa so file này với mã nguồn.

Plugin không chạy được một mình: phần soạn câu trả lời là của OpenClaw, nên dùng repo này nghĩa là thay cả runner bằng OpenClaw. Plugin bỏ qua tin của chính tài khoản (`src/channel/monitor.ts` dòng 1555), nên không có nhân viên tiếp quản. Plugin không có bước duyệt và không có tin xin đồng ý. Chính sách `pairing` chỉ duyệt người gửi, không duyệt từng câu trả lời.

Vấn đề bảo mật đáng ghi: công cụ `zaloclaw` mà agent gọi được có hành động `self-update`. Hành động này chạy `git pull origin main`, `npm install` và `npm run build` (`src/tools/tool.ts` dòng 484–499). Trong mã plugin, tôi không thấy bước kiểm ai yêu cầu cập nhật. Nếu OpenClaw không tự chặn, một tin nhắn lừa được model sẽ khiến máy tải và chạy mã mới. Tôi chưa đọc mã OpenClaw để biết OpenClaw có chặn hay không.

### babyvibe/deplao-builder: app desktop CRM rất lớn, có gửi dữ liệu về máy chủ riêng

Repo này là app Electron quản lý nhiều tài khoản Zalo, Facebook và Telegram cá nhân, kèm CRM, chiến dịch gửi tin, workflow kéo thả, POS và ERP. Mã nguồn dùng giấy phép MIT. Phiên bản 26.11.0, 142 commit, 267 sao, 160 fork, commit cuối ngày 2026-11-06. Phần TypeScript trong `src/` và `electron/` khoảng 323.000 dòng.

App có phần gợi ý câu trả lời bằng AI để nhân viên chọn (`src/services/ai/AIAssistantService.ts`), gọi được Claude qua API key. Đây là dạng duyệt trước khi gửi gần với yêu cầu của anh nhất trong năm repo. Tuy vậy, tôi không đề xuất repo này vì ba điểm:

- Bản build production tự gửi UID của các tài khoản Zalo, Facebook, Telegram đang dùng và một mã máy lên `https://deplaoapp.com/api/tracking/page`, mỗi ngày một lần. Comment trong file ghi mục đích là gia hạn tính năng premium (`src/services/tracking/TrackingService.ts`). `electron/main.ts` dòng 1690 bật dịch vụ này khi app khởi động. Tôi không thấy tùy chọn nào để tắt; `TrackingService` chỉ bỏ qua bản build dev.
- Tính năng quét thành viên nhóm ẩn gửi cookie và IMEI Zalo lên `deplaoapp.com`. Tính năng này mặc định tắt và hỏi đồng ý trước, nhưng phần xử lý phía máy chủ không công khai.
- Workflow build cho macOS biên dịch JavaScript sang bytecode V8 bằng `bytenode` (`.github/workflows/build-macos.yml`), nên bản cài phát hành không đối chiếu được với mã nguồn. Ngoài ra, app tự kiểm bản cập nhật mỗi 4 giờ qua `electron-updater` (tự tải đang tắt), và có sẵn các gói mở đường hầm ra Internet (`@ngrok/ngrok`, `cloudflared`, `localtunnel`).

Thay stack hiện tại bằng một app CRM 323.000 dòng có gửi dữ liệu ra ngoài là đổi một hệ thống nhỏ anh kiểm được lấy một hệ thống lớn anh không kiểm được.

## Hai repo gần mục tiêu nhưng không clone

`dennyducnguyen/penai` là nền tảng agent cho doanh nghiệp, cài trên VPS. README ghi PenAI có hộp thư Zalo cá nhân cho nhiều nhân viên, tự dừng AI khi nhân viên trả lời, có thẻ duyệt có nút bấm, và đăng nhập được gói Claude Pro/Max qua Claude Code. Đây là repo có nhiều phần giống chatbot thom house nhất. Tuy vậy, giấy phép riêng của PenAI (đọc qua `gh api repos/dennyducnguyen/penai/license`) ghi rằng dùng phần mềm để chăm sóc khách hàng trong hoạt động kinh doanh thực tế phải có văn bản cho phép của tác giả. Repo cài bằng lệnh `curl ... | sudo bash` lên VPS, không chạy local trên Mac, và có 0 sao.

`minhhoasqtt-prog/app-zalo-marketing` (MIT) là app Windows dùng `zalo-agent-cli` của PhucMPham để kết bạn theo danh sách số điện thoại và đưa khách vào nhóm. App có bot AI soạn nháp để người duyệt bấm gửi, nhưng bot đó chạy trên Zalo Bot Platform và mặc định dùng DeepSeek. Mục đích chính của app là marketing hàng loạt, khác với việc trả lời khách nhắn vào.

## Mỗi repo thay được phần nào của stack hiện tại?

Bảng dưới so năm repo đã clone với stack hiện tại. Ô "chưa kiểm" nghĩa là tôi không tìm thấy hoặc không đọc tới phần mã đó.

| Yêu cầu | Stack hiện tại | `zalo-flow` | `vuhai2002/zalo-agent` | `hermes-zalo-plugin` | `zaloclaw` | `deplao-builder` |
|---|---|---|---|---|---|---|
| Lớp Zalo | `zca-js` 2.2.0 có bản vá, qua engine | `zca-js` 2.1.2 | `zca-js` 2.2.0, thêm Zalo Bot Platform | `zca-js` 2.1.2 theo lockfile | `zca-js` từ 2.1.2 trở lên | `zca-js` từ 2.2.0 trở lên |
| Soạn bằng `claude -p` trên subscription | Có | Không; dùng API key của Gemini, OpenAI, DeepSeek và các bên khác | Không; dùng API key, có API Anthropic | Không có phần soạn; Hermes Agent soạn | Không có phần soạn; OpenClaw soạn | Không; dùng API key, có API Claude |
| Nhân viên duyệt từng câu trước khi gửi | Có, chế độ `approve_each` | Không ở server; extension chỉ gợi ý trên Zalo Web | Không | Không có phần này | Không | Có gợi ý để nhân viên chọn trong app |
| Tin xin đồng ý | Có | Không tìm thấy | Không tìm thấy | Không có phần này | Không tìm thấy | Chưa kiểm |
| Trả lời theo bảng giá, có bước kiểm con số | Có, theo `data/services.json` | Có kho tri thức, không có bước kiểm | Có kho tài liệu, không có bước kiểm | Không có phần này | Không có phần này | Chưa kiểm |
| Nhân viên tiếp quản khi chủ tự gõ | Có, dừng bot 12 giờ | Có, dừng bot 15 phút | Không; chỉ tắt bot theo hội thoại trên dashboard | Làm được nếu đặt `ZALO_SELF_LISTEN=1` | Không | Chưa kiểm |
| Giấy phép | Engine theo CC BY-NC-SA 4.0 | MIT kèm Commons Clause | MIT | MIT | MIT | MIT; bản cài phát hành là bytecode |
| Vấn đề bảo mật nặng nhất tôi thấy | Chưa gửi tin nào qua Zalo thật | Webhook gửi tin không cần token; mặc định mở ra LAN | Không thấy vấn đề nặng khi đọc lướt | Token mặc định không có | Agent gọi được hành động tự cập nhật | Tự gửi UID Zalo và mã máy về máy chủ riêng |
| Nếu dùng thì thay phần nào | Không áp dụng | Cả bot | Cả bot | Chỉ engine | Engine và runner, cần thêm OpenClaw | Cả app |

## Những ý tưởng nào đáng lấy?

Năm ý tưởng sau là đề xuất, chưa phải việc đã làm. Repo MIT cho phép chép mã kèm thông báo bản quyền. Với `zalo-flow`, tôi chỉ đề xuất lấy cách làm, không chép mã, vì giấy phép có điều kiện phi thương mại chưa rõ ranh giới.

1. Bỏ qua tin hệ thống về kết bạn. `zalo-flow` có biểu thức lọc các câu như "đã trở thành bạn bè" để bot không trả lời (`src/adapters/ai-agent.js` dòng 324). Listener của stack hiện tại chỉ chuyển sự kiện `message` từ người dùng, nhưng tôi chưa biết Zalo có gửi câu hệ thống này dưới dạng tin nhắn hay không. Nếu có, server sẽ gửi tin xin đồng ý cho một người vừa kết bạn mà chưa nhắn gì. Việc nên làm là xem log của listener trong lần thử đầu với Zalo thật.
2. Báo trước cho nhân viên dùng console: không mở Zalo Web trên trình duyệt khi bot đang chạy. Lý do là Zalo chỉ cho một phiên web mỗi tài khoản, theo README của `vuhai2002/zalo-agent` và comment trong mã engine hiện tại. Nên ghi điều này vào `docs/chay-local-zalo-ca-nhan.md` sau khi thử thật.
3. Chuyển Markdown sang định dạng chữ của Zalo và tự gửi lại dạng chữ thường khi Zalo từ chối, theo `vuhai2002/zalo-agent` (MIT). Việc này chỉ cần khi anh muốn tin trả lời có chữ đậm hay danh sách; hiện runner gửi chữ thường.
4. Chia quyền theo nhóm hành động như `permissions.js` của `hermes-zalo-plugin` (MIT): bridge chỉ được gọi lệnh gửi tin, không gọi được lệnh xóa, chặn hay quản lý nhóm. Bridge hiện tại chỉ dùng lệnh `msg send` để gửi tin, nên ý này chỉ cần nếu sau này đổi engine.
5. Viết test kiểm địa chỉ server nghe, theo `src/config/dashboard-host-binding.test.ts` của `vuhai2002/zalo-agent`. Test này bảo đảm dashboard không vô tình nghe ở `0.0.0.0`, đúng loại lỗi `zalo-flow` đang mắc.

Stack hiện tại đã có các phần mà `zalo-flow` quảng cáo là điểm mạnh: gom tin khách gửi liên tiếp (server chờ 10 giây), bỏ bản nháp cũ khi khách gửi thêm tin trong lúc runner đang soạn (trạng thái `superseded` trong `apps/server/src/conversation-do.ts`), giới hạn tốc độ gửi và nhận ra tin của chính bot.

## Nói ngắn gọn nhất

Trong các repo tôi tìm được qua sáu topic GitHub, không repo nào làm sẵn đúng thứ anh cần: bot trả lời khách trên Zalo cá nhân, soạn bằng `claude -p`, có nhân viên duyệt, có tin xin đồng ý và kiểm câu trả lời theo bảng giá. `zalo-flow` là app chat và CRM hoàn chỉnh nhưng tự gửi câu trả lời không qua duyệt. Theo những gì tôi đọc trong mã, `zalo-flow` còn cho phép người cùng mạng, và có thể cả một trang web anh mở, gửi tin bằng tài khoản của anh. Các repo khác hoặc là trợ lý cá nhân không có bước duyệt, hoặc chỉ là cầu nối, hoặc là app CRM lớn có gửi dữ liệu ra ngoài. Vì vậy, tôi đề nghị giữ stack hiện tại, lấy vài ý tưởng nhỏ, và chỉ xem `hermes-zalo-plugin` là phương án thay engine nếu engine hiện tại hỏng khi chạy với Zalo thật.

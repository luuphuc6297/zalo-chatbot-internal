# Rà soát ba repo Zalo: có dùng được cho chatbot thom house không?

Ngày rà: 2026-11-07. Cách rà: đọc tĩnh mã nguồn ở ba bản clone trong `sources/repos/`, không cài thư viện, không chạy mã của repo, không đăng nhập Zalo. Tài liệu Zalo được tải bằng `curl` từ trang tài liệu chính thức `docs.zaloplatforms.com` cùng ngày. Không có phép thử nào trên một OA thật.

## Phần anh cần duyệt

Không repo nào trong ba repo dùng được nguyên trạng làm phần nối chatbot với Zalo OA của thom house. Lý do chính có ba.

Thứ nhất, toàn bộ công cụ MCP (Model Context Protocol, giao thức để Claude Desktop hay Claude Code gọi công cụ bên ngoài) trong cả ba repo chỉ điều khiển tài khoản Zalo cá nhân qua thư viện không chính thức `zca-js`. Không có công cụ MCP nào gọi API chính thức của OA. Phần OA chỉ có ở dạng lệnh dòng lệnh (`zalo-agent oa ...`).

Thứ hai, phần OA trong cả hai bản `zalo-agent-cli` có lỗi ở đúng các chức năng chatbot cần nhất. Bước kiểm chữ ký webhook tính sai công thức so với tài liệu Zalo, nên nếu bật kiểm chữ ký thì theo suy luận từ mã, mọi sự kiện thật sẽ bị từ chối. Token không tự làm mới. Sự kiện không được lưu trước khi trả lời Zalo và không được lọc trùng. Hai loại tin `transaction` và `promotion` mà repo hỗ trợ đã bị Zalo dừng từ 01/03/2026.

Thứ ba, hai repo của tác giả Arden (`ardennguyen/zalo-mcp` và `ardennguyen/zalo-agent-cli`) dùng giấy phép CC BY-NC-SA 4.0. Giấy phép này không cho dùng vào hoạt động kinh doanh của một công ty nếu chưa xin giấy phép thương mại riêng. Repo gốc `PhucMPham/zalo-agent-cli` dùng giấy phép MIT, được dùng thương mại.

Đề xuất của tôi: tự viết một bộ nối OA nhỏ, khoảng 1.200–1.400 dòng mã chính và khoảng 600 dòng test (ước tính). Mã OAuth, gửi tin tư vấn và upload của repo PhucMPham được lấy lại có sửa, kèm thông báo MIT. Mã của Arden chỉ dùng để tham khảo cách làm, không chép. Điểm yếu của đề xuất: phải tự viết và tự kiểm trên OA thật, và các kết luận "sai" ở trên mới là kết luận từ đọc mã đối chiếu tài liệu, chưa chạy trên OA thật.

Anh cần quyết một việc: có bỏ hẳn hướng "Claude Desktop cộng Zalo MCP làm app desktop" hay không. Tôi đề xuất bỏ, vì hướng đó không gắn được với OA và dựa vào tài khoản cá nhân có rủi ro bị khóa (chi tiết ở mục cuối).

## Ba repo là gì, bản nào được rà?

| Repo | Commit đầy đủ | Phiên bản | Giấy phép | Ngày commit cuối |
|---|---|---|---|---|
| `ardennguyen/zalo-mcp` | `89e209c219be09c08995fd2b5330ea1f4cd2d287` | 2.0.9 | CC BY-NC-SA 4.0 | 2026-11-06 |
| `ardennguyen/zalo-agent-cli` (gọi tắt là bản Arden) | `f867f0e992bea50d082c34cbe0637f209ee3a3c1` | 2.5.9 | CC BY-NC-SA 4.0 | 2026-10-29 |
| `PhucMPham/zalo-agent-cli` (gọi tắt là bản PhucMPham) | `ce630eeda49329a2089aa471eb8c450ddfbc84b1` | 1.7.0 | MIT | 2026-08-26 |

Bản `zalo-mcp` chỉ là trình khởi chạy mỏng, khoảng 240 dòng trong `mcp-server.js`. Trình này gọi `zalo-agent mcp start` của bản Arden và chuyển tiếp mọi lệnh khác sang bản Arden. Tệp `package.json` khai báo `"@ardennguyen/zalo-agent-cli": "^2.5.0"`, còn `package-lock.json` khóa ở 2.5.9. Registry npm ghi `gitHead` của 2.5.9 là `f867f0e…` và của `zalo-mcp` 2.0.9 là `89e209c…` (đã gọi `registry.npmjs.org`, ngày 2026-11-07). Bản Arden là bản phái sinh từ bản PhucMPham, theo mục 4 của tệp NOTICE.

Gói npm `zalo-agent-cli` của PhucMPham có `latest` là 1.6.2, cập nhật lần cuối 2026-03-27. Bản 1.7.0 ở commit `ce630ee` chưa thấy trên npm.

Hai bản clone của `zalo-agent-cli` là clone nông (shallow clone, chỉ tải một phần lịch sử git), nên ngày commit cuối của từng tệp chỉ đáng tin ở mức gần đúng.

Bản Arden lớn hơn nhiều: khoảng 90.000 dòng tính cả test và tài liệu, 135 tệp test, có ESLint, CI và một bản vá 1.445 dòng cho `zca-js` 2.2.0. Bản PhucMPham có khoảng 22.000 dòng và 15 tệp test, kèm một trang giới thiệu React trong `src/app/` không liên quan tới bot. `zalo-mcp` có một tệp test cho trình khởi chạy.

## Phần nào là API chính thức, phần nào là tự động hóa tài khoản cá nhân?

Hai bản `zalo-agent-cli` có hai đường tách biệt. Đường thứ nhất là API chính thức của OA, nằm trong `src/core/oa-client.js` và các lệnh `src/commands/oa*.js`. Mã này gọi thẳng `openapi.zalo.me` bằng `fetch` và không phụ thuộc `zca-js`. Đường thứ hai là tài khoản Zalo cá nhân, đăng nhập bằng mã QR, chạy qua `zca-js`. `zca-js` là thư viện dựng lại giao thức Zalo Web bằng cách dịch ngược, không do Zalo cung cấp. Đường thứ hai gồm `src/core/zalo-client.js`, các lệnh `msg`, `friend`, `group`, `reminder`, `auto-reply`, `listen` và toàn bộ máy chủ MCP.

Tôi kiểm bằng `grep -rln "oa-client" src`. Ở bản Arden, chỉ `src/commands/oa.js` và `src/commands/oa-init.js` nhập `oa-client`. Ở bản PhucMPham, ngoài hai tệp đó chỉ có thêm tệp test. Không tệp nào trong `src/mcp/` nhập `oa-client`.

| Bản | Số công cụ MCP | Công cụ | Nền phía sau |
|---|---|---|---|
| Arden 2.5.9 | 25 | `zalo_get_messages`, `zalo_send_message`, `zalo_list_threads`, `zalo_search_threads`, `zalo_mark_read`, `zalo_get_history`, `zalo_view_media`, `zalo_react`, `zalo_undo`, `zalo_get_group_members`, `zalo_list_conversations`, `zalo_coverage`, `zalo_sync`, `zalo_sync_status`, `zalo_search_messages`, `zalo_lookup_user`, `zalo_forward_message`, `zalo_delete_message`, `zalo_reminder`, `zalo_note`, `zalo_poll`, `zalo_wait_for_message`, `zalo_label`, `zalo_friend`, `zalo_group` | `zca-js`, tài khoản cá nhân |
| PhucMPham 1.7.0 | 8 | `zalo_get_messages`, `zalo_send_message`, `zalo_list_threads`, `zalo_search_threads`, `zalo_mark_read`, `zalo_get_history`, `zalo_search_history`, `zalo_view_media` | `zca-js`, tài khoản cá nhân |
| `zalo-mcp` 2.0.9 | 25 (của bản Arden) | như bản Arden | `zca-js`, tài khoản cá nhân |

README của `zalo-mcp` ở dòng 7 nói gói này tự động hóa "Zalo Personal & Official Account". Câu đó đúng với phần dòng lệnh, nhưng không đúng với phần MCP.

Lệnh `reminder` và `auto-reply` ở cả hai bản đều gọi `getApi()` của `zca-js`, tức là đặt nhắc hẹn hay trả lời tự động trên tài khoản cá nhân. Hai lệnh này không phải luồng chăm sóc khách hàng của OA.

## OA client làm được gì, và gọi có đúng endpoint không?

Cả hai bản có cùng một bộ hàm: gửi tin văn bản, ảnh, file, danh sách; xem trạng thái tin; xem hồ sơ OA; xem, liệt kê và cập nhật người quan tâm; quản lý nhãn; upload ảnh và file; xem danh sách hội thoại và lịch sử chat; cập nhật menu; bài viết; cửa hàng. Cả hai bản không có hàm gửi ZBS Template Message. ZBS Template Message là loại tin theo mẫu đã được Zalo duyệt, và theo tài liệu Zalo hiện là đường gửi tin giao dịch và tin hậu mãi.

Bảng dưới so endpoint trong mã với tài liệu Zalo tải ngày 2026-11-07.

| Việc | Tài liệu Zalo | Bản Arden | Bản PhucMPham |
|---|---|---|---|
| Gửi tin tư vấn | `v3.0/oa/message/cs` | đúng | đúng |
| Gửi tin giao dịch (`transaction`) | trang tài liệu ghi dịch vụ dừng từ 01/03/2026 | vẫn cho chọn | vẫn cho chọn |
| Gửi tin truyền thông cá nhân (`promotion`) | trang tài liệu ghi dịch vụ dừng từ 01/03/2026 | vẫn cho chọn | vẫn cho chọn |
| Gửi ZBS Template qua UID | `v3.0/oa/message/template` | không có | không có |
| Upload ảnh | `v2.0/oa/upload/image` | gọi `v3.0/oa/upload/image`, lệch tài liệu | gọi `v2.0`, đúng, có test |
| Chi tiết người dùng | `v3.0/oa/user/detail?data={"user_id":...}` | đúng dạng `data=` | gọi `?user_id=`, lệch tài liệu |

Nguồn của bảng: trang "Gửi tin Tư vấn dạng văn bản", "Gửi tin giao dịch", "Gửi tin Truyền thông cá nhân", "API gửi tin qua UID", "Upload hình ảnh" và "Truy xuất chi tiết người dùng" trên `docs.zaloplatforms.com`. Hai trang tin giao dịch và tin truyền thông cùng ghi rằng dịch vụ "Tin UID Giao dịch (165 vnd) và UID Truyền thông cá nhân sẽ được dừng cung cấp từ 01/03/2026". Hai trang này dẫn tới thông báo V251209 trên `developers.zalo.me`. Trang thông báo đó render bằng JavaScript, nên tôi chỉ đọc được tiêu đề và đoạn mô tả. Hai ô "lệch tài liệu" là suy luận từ việc so mã với tài liệu, chưa gọi thử API.

Trang tin tư vấn còn ghi hai mốc liên quan. Từ 1/1/2026, tin tư vấn trong 48 giờ sau tương tác cuối được miễn phí không giới hạn. Sau 1/3/2026, phản hồi của API không còn trả hai trường `remain` và `total`. Cả hai bản không đọc hai trường này.

## Kiểm chữ ký webhook có đúng không?

Không đúng, ở cả hai bản. Mã và tài liệu tính chữ ký theo hai cách khác nhau.

Webhook là địa chỉ HTTP mà Zalo gọi tới mỗi khi có sự kiện, ví dụ khách nhắn tin cho OA. Zalo ký mỗi lần gọi bằng một mã băm trong header để bên nhận biết đúng là Zalo gửi. Trang "Sự kiện người dùng gửi tin nhắn" (`docs.zaloplatforms.com/docs/OA/webhook/tin-nhan/su-kien-nguoi-dung-gui-tin-nhan`) ghi công thức như sau:

```
X-ZEvent-Signature: mac = sha256(appId + data + timeStamp + OAsecretKey), với data là chuỗi json trả về dưới đây.
```

Theo tài liệu, chữ ký là SHA-256 thường của một chuỗi ghép bốn phần: app id, thân request, timestamp và khóa bí mật của OA. Khóa bí mật là một phần của chuỗi được băm, không phải khóa của HMAC.

Mã của bản Arden, `src/commands/oa-listen.js` dòng 119–123 ([permalink](https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/commands/oa-listen.js#L119-L123)):

```js
function verifyMac(body, mac, secretKey) {
    const calculated = createHmac("sha256", secretKey).update(body).digest("hex");
    if (mac.length !== calculated.length) return false;
    return timingSafeEqual(Buffer.from(mac), Buffer.from(calculated));
}
```

Bản PhucMPham có đúng hàm này ở `src/commands/oa-listen.js` dòng 32–36 ([permalink](https://github.com/PhucMPham/zalo-agent-cli/blob/ce630eeda49329a2089aa471eb8c450ddfbc84b1/src/commands/oa-listen.js#L32-L36)).

Mã tính HMAC-SHA256 với khóa là secret và dữ liệu chỉ là thân request. Mã không ghép app id và timestamp vào. Hai cách tính cho ra hai giá trị khác nhau với cùng một request. Vì vậy, khi người dùng truyền `--secret`, tôi suy luận rằng mọi sự kiện thật sẽ bị trả 401. Khi người dùng không truyền `--secret` hoặc dùng `--no-verify`, listener nhận mọi request và không kiểm nguồn gửi. Tôi chưa thử với một OA thật. Tài liệu cũng không nói rõ ba chi tiết: chữ ký là hex chữ thường hay chữ hoa, `timeStamp` có phải trường `timestamp` trong thân request hay không, và header có tiền tố `mac=` hay không. Phép thử đầu tiên khi dựng bộ nối mới là so công thức với một request thật.

Hàm `verifyMac` còn so độ dài chuỗi trước khi gọi `timingSafeEqual`. Cách làm này đúng về an toàn, vì `timingSafeEqual` báo lỗi khi hai buffer khác độ dài.

Bản Arden có một hàm khác cũng tên là chữ ký: `X-Zalo-Signature` trong `src/core/webhook-outbox.js` dòng 46–57. Hàm này không kiểm sự kiện từ Zalo. Hàm này ký sự kiện của tài khoản cá nhân mà bản Arden chuyển tiếp sang một webhook khác do người dùng tự dựng.

## Listener có lưu sự kiện, lọc trùng và trả lời Zalo đúng hạn không?

Tài liệu "Giới thiệu về Webhook" yêu cầu bên nhận trả HTTP 200 trong tối đa 2 giây. Nếu không, Zalo gửi lại sự kiện sau 30 giây, 5 phút, 15 phút, 30 phút và 1 giờ, kèm header `num_retry`. Nếu webhook vẫn không trả lời đúng hạn trong khoảng thời gian đó, Zalo vô hiệu hóa webhook và ứng dụng phải xin lại quyền nhận sự kiện.

Bản Arden trả 200 trước, ở dòng 212, rồi mới in sự kiện ra stdout. Bản Arden đọc `num_retry` ở dòng 113–116, nhưng chỉ để in dòng "redelivery". Sự kiện không được ghi vào đĩa, nên nếu tiến trình chết ngay sau khi trả 200 thì sự kiện mất. Sự kiện gửi lại cũng không bị lọc trùng theo `msg_id`. Danh sách 57 tên sự kiện trong bản Arden (dòng 24–92) đầy đủ hơn bản PhucMPham. Bản PhucMPham còn giữ ba tên mà chính bản Arden ghi là Zalo không gửi, trong đó có `user_click_link`.

Bản PhucMPham in sự kiện trước, rồi mới trả 200 ở dòng 158. Bản này cũng không lưu và không lọc trùng.

Bản Arden có một hàng đợi bền trên SQLite (`src/core/webhook-outbox.js`). Hàng đợi này giao "ít nhất một lần", theo thứ tự, có dead-letter. Hàng đợi chỉ dùng cho sự kiện của tài khoản cá nhân, không dùng cho webhook OA. Thiết kế này đáng tham khảo khi tự viết, nhưng không được chép mã vì giấy phép.

## Token có tự làm mới, và có bị tranh chấp refresh token không?

Tài liệu "Xác thực và ủy quyền cho Ứng dụng" ghi access token hiệu lực 25 giờ. Refresh token hiệu lực 3 tháng và "chỉ được sử dụng một lần". Sau khi làm mới thành công, refresh token cũ bị vô hiệu và access token cũ hết hiệu lực ngay.

Cả hai bản chỉ làm mới khi người dùng gõ `zalo-agent oa refresh` (Arden `src/commands/oa.js` dòng 181–210; PhucMPham dòng 160–189). Không tệp nào gọi `refreshAccessToken` tự động, và mã không kiểm `expiresIn` trước khi gọi API. Một bot chạy liên tục sẽ ngừng gửi được tin sau khoảng 25 giờ, trừ khi có tiến trình lên lịch bên ngoài.

Lệnh `oa refresh` đọc refresh token ngoài khóa, gọi Zalo, rồi mới ghi kết quả dưới khóa tệp (bản Arden). Nếu hai tiến trình cùng làm mới, một tiến trình sẽ dùng refresh token đã bị vô hiệu. Nếu một tiến trình ghi đè sau tiến trình kia, tệp có thể giữ token cũ. Bản PhucMPham không có khóa tệp. Đây là suy luận từ mã. Bộ nối mới chỉ được cho một tiến trình làm mới token tại một thời điểm: tiến trình đó làm mới dưới khóa, và ghi token mới trước khi tiến trình khác đọc.

Luồng đăng nhập OAuth của cả hai bản không gửi `code_verifier` và `code_challenge` (PKCE), và cũng không gửi `state`. Tài liệu Zalo chỉ bắt buộc `code_verifier` "nếu ở bước 2 có thiết lập code challenge", nên luồng này vẫn chạy được, nhưng kém an toàn hơn cách tài liệu khuyên. Trang callback ghép thẳng `error_description` lấy từ URL vào HTML mà không escape (Arden `oa.js` dòng 118–120; PhucMPham dòng 97–99).

## Token và secret được cất ở đâu, có bị lộ trong log không?

Token OA, refresh token và app secret key được lưu dạng văn bản thường trong `~/.zalo-agent/oa-credentials.json`, với quyền tệp 0600. Bản Arden ghi tệp theo kiểu nguyên tử dưới khóa tệp (`src/utils/atomic-file.js` dòng 59). Bản PhucMPham dùng `writeFileSync` với `mode: 0o600`. Cookie của tài khoản cá nhân nằm ở `~/.zalo-agent-cli/credentials/cred_<id>.json`, cũng ở quyền 0600. Không bản nào dùng Keychain của macOS.

App secret và OA secret được truyền qua cờ dòng lệnh (`--secret`). Giá trị đó hiện trong danh sách tiến trình và lịch sử shell. Trình khởi chạy `zalo-mcp` che `--auth`, `--client-secret`, `--webhook-secret` khi ghi log (`mcp-server.js` dòng 208–215), nhưng không che `--secret` của các lệnh `oa`, vì các lệnh này đi qua đường chuyển tiếp không ghi log. Listener in nội dung tin nhắn của khách ra terminal. Nội dung đó là dữ liệu cá nhân, cần tính tới khi lưu log.

Trình khởi chạy `zalo-mcp` tự chạy `npm install` khi không tìm thấy bản Arden (`mcp-server.js` dòng 110–121). Mỗi lần cài lại, máy có thể kéo một phiên bản mới trong khoảng `^2.5.0` nếu không có lockfile đi kèm.

## Giấy phép buộc gì?

Hai repo của Arden dùng CC BY-NC-SA 4.0. Tệp NOTICE của bản Arden (dòng 16–19) và của `zalo-mcp` cùng ghi rằng dùng thương mại không được cấp phép, ví dụ dùng "in a company's business operations". Muốn dùng thương mại phải mở issue để xin giấy phép riêng. Khi chia sẻ bản sửa, bản sửa phải giữ CC BY-NC-SA. Phần mã gốc từ PhucMPham và bản `zca-js` đã vá vẫn theo MIT, và các bản Arden từ 2.0.0 trở về trước (với `zalo-mcp` là 1.0.16 trở về trước) vẫn là MIT. Tôi không phải luật sư. Với một spa đang kinh doanh, cách đọc an toàn là không chạy và không chép mã Arden khi chưa có giấy phép thương mại.

Bản PhucMPham dùng MIT. Người dùng được dùng, sửa và bán, với điều kiện giữ câu bản quyền và nội dung giấy phép trong mọi bản sao. Tệp `LICENSE` ghi "Copyright (c) 2026" mà không có tên người giữ bản quyền. Khi chép mã, nên ghi thêm nguồn `PhucMPham/zalo-agent-cli` tại commit `ce630ee`. `zca-js` cũng dùng MIT, nhưng giấy phép của thư viện không xử lý được rủi ro điều khoản dịch vụ của Zalo.

## Từng thành phần nên dùng thế nào?

| Thành phần | Kết luận | Lý do |
|---|---|---|
| `zalo-mcp` (trình khởi chạy) | Tránh | Chỉ chạy MCP tài khoản cá nhân; giấy phép không cho dùng thương mại |
| Công cụ MCP bản Arden (`src/mcp/*`) | Tránh | Chỉ dùng `zca-js`; giấy phép không cho dùng thương mại |
| Công cụ MCP bản PhucMPham (`src/mcp/*`) | Tránh | Chỉ dùng `zca-js`; rủi ro khóa tài khoản |
| `oa-client.js` bản PhucMPham: OAuth, `sendText`/`sendImage`/`sendList` kiểu `cs`, upload `v2.0`, nhãn | Dùng lại có sửa | MIT. Cần bỏ `transaction` và `promotion`, sửa `user/detail` sang `data=`, thêm ZBS Template, tự làm mới token, thêm PKCE và `state` |
| `upload-helpers.js` bản PhucMPham | Dùng lại có sửa | MIT, 82 dòng. Cần đối chiếu lại giới hạn kích thước với tài liệu |
| `oa-listen.js` (cả hai bản) | Chỉ tham khảo | Công thức chữ ký sai, không lưu, không lọc trùng. Danh sách sự kiện của bản Arden dùng làm tham khảo |
| `oa-client.js` bản Arden | Chỉ tham khảo | Giấy phép không cho dùng thương mại; upload gọi `v3.0` lệch tài liệu |
| `webhook-outbox.js`, `atomic-file.js` bản Arden | Chỉ tham khảo thiết kế | Ý tưởng hàng đợi bền và ghi nguyên tử tốt, nhưng mã theo giấy phép NC |
| Lệnh `reminder`, `auto-reply` (cả hai bản) | Tránh | Chạy trên tài khoản cá nhân, không phải luồng OA |

## Nếu dùng "Claude Desktop cộng Zalo MCP" làm app desktop thì sao?

Hướng này là: cài `zalo-mcp` vào Claude Desktop hoặc Claude Code, rồi để Claude đọc và trả lời tin nhắn Zalo. Tôi không đề xuất hướng này, vì bốn lý do.

Lý do thứ nhất: hướng này không gắn được với OA. Mọi công cụ MCP chỉ nói chuyện với tài khoản cá nhân. Muốn dùng OA, Claude phải gọi lệnh `zalo-agent oa msg text` qua shell. Trong khi đó, tin khách gửi vào OA chỉ được listener in ra terminal và không đi vào MCP, nên Claude không có đường nào để nhận tin của OA.

Lý do thứ hai: nếu dùng tài khoản cá nhân thì có rủi ro bị khóa. Tệp `DISCLAIMER.md` của cả hai bản cảnh báo tài khoản có thể bị khóa vĩnh viễn, và `zca-js` có thể hỏng bất cứ lúc nào khi Zalo đổi giao thức. Tôi chưa đọc được văn bản Thỏa thuận sử dụng của Zalo, vì trang điều khoản chuyển hướng sang trang đăng nhập. Vì vậy, điều khoản cụ thể về phần mềm tự động là chưa xác minh. Tài khoản cá nhân cũng không có các quyền của OA như tin tư vấn, ZBS Template, nhãn và gói dịch vụ.

Lý do thứ ba: bot chỉ chạy khi máy Mac bật, Claude Desktop mở và có một phiên hội thoại đang chạy. MCP là cơ chế Claude chủ động gọi công cụ. MCP không phải dịch vụ nhận webhook chạy liên tục. Công cụ `zalo_wait_for_message` của bản Arden chỉ chờ được trong một phiên đang mở. Máy ngủ, mất mạng hay phiên hết ngữ cảnh đều làm bot ngừng trả lời. Với webhook OA, Zalo đòi trả lời trong 2 giây và sẽ vô hiệu hóa webhook nếu bên nhận không trả lời kịp nhiều lần. Một máy Mac để bàn khó đáp ứng yêu cầu này ổn định.

Lý do thứ tư: chưa rõ gói thuê bao Claude có được dùng để chạy một bot phục vụ khách hàng hay không. Câu hỏi này thuộc phần nghiên cứu về Anthropic (nhận định A2). Ở phần này, tôi chỉ ghi rằng hướng "Claude Desktop làm bot" chạy toàn bộ tin nhắn của khách qua phiên đăng nhập thuê bao, nên phải có kết luận của phần Anthropic trước khi dùng.

## Bộ nối OA tối thiểu cần những phần nào?

Bộ nối OA là phần mã nằm giữa Zalo và chatbot. Phần này nhận sự kiện, gửi tin và giữ token. Bảng dưới là ước tính số dòng, chưa phải số đo.

| Mô-đun | Việc | Ước tính số dòng |
|---|---|---|
| `oauth` | Đăng nhập OAuth v4 có PKCE và `state`; lưu token vào Keychain hoặc DB đã mã hóa; làm mới chủ động trước khi hết 25 giờ; chỉ một tiến trình làm mới tại một thời điểm | 200 |
| `webhook-receiver` | Đọc thân request dạng byte gốc; kiểm `X-ZEvent-Signature` theo công thức tài liệu; kiểm độ lệch timestamp; ghi sự kiện vào DB rồi mới trả 200, trong vòng 2 giây | 150 |
| `event-store` | Bảng sự kiện có khóa duy nhất theo `app_id`, `event_name`, `msg_id` để lọc bản gửi lại; hàng đợi việc trong DB | 200 |
| `send-client` | Gửi tin tư vấn (văn bản, ảnh, danh sách); upload `v2.0`; ZBS Template qua `v3.0/oa/message/template`; xử lý lỗi `-32` (vượt giới hạn tốc độ) và các mã lỗi khác | 250 |
| `send-policy` | Trước khi gửi, kiểm khách còn trong 7 ngày kể từ tương tác cuối, có quá 48 giờ không (tính phí), có còn quan tâm OA không, và khung giờ gửi theo loại tin; kiểm cờ tắt gửi ngay trước lúc gửi | 120 |
| `outbox` | Hàng gửi đi có khóa chống gửi trùng (idempotency key), thử lại có giới hạn, ghi kết quả | 150 |
| `user-sync` | `user/detail`, `user/getlist`, gắn nhãn | 100 |
| `config-logging` | Đọc cấu hình, che secret và nội dung tin trong log | 80 |
| Test | Test chữ ký với mẫu thật, test lọc trùng, test tranh chấp refresh token, test chính sách gửi | 600 |

Tổng ước tính là 1.250 dòng mã chính và 600 dòng test. Điểm yếu của ước tính: tôi chưa thấy request webhook thật, nên phần chữ ký và cấu trúc sự kiện có thể cần sửa sau lần thử đầu. Tôi chưa ước tính giao diện macOS cho nhân viên, vì phần đó thuộc phần kiến trúc.

## Kết luận cho từng nhận định của báo cáo trước

| ID | Kết luận | Căn cứ |
|---|---|---|
| R1 | Đúng | `zalo-mcp/package-lock.json` dòng 22–23 khóa 2.5.9; npm ghi `gitHead` 2.5.9 là `f867f0e…` và `zalo-mcp` 2.0.9 là `89e209c…`. `package.json` chỉ khai báo khoảng `^2.5.0` |
| R2 | Đúng | Bản Arden có `oa-client.js` và lệnh `oa`; 25 công cụ MCP đều dùng API `zca-js`; không tệp nào trong `src/mcp/` nhập `oa-client` |
| R3 | Đúng | `NOTICE` dòng 16–19: "Commercial use is not licensed"; muốn dùng thương mại phải xin giấy phép riêng qua issue |
| R4 | Đúng, cần ghi thêm | Phiên bản 1.7.0, MIT, OA client tách khỏi `zca-js`, 8 công cụ MCP dùng tài khoản cá nhân. Bản 1.7.0 chưa có trên npm, `latest` là 1.6.2 |
| R5 | Đúng | `reminder.js` và `auto-reply.js` của cả hai bản gọi `getApi()` của `zca-js` |
| R6 | Đúng ở mức mã | Cả hai bản dùng `createHmac("sha256", secretKey).update(body)`; tài liệu ghi `sha256(appId + data + timeStamp + OAsecretKey)`. Chưa thử trên OA thật |
| R7 | Đúng một phần | Webhook OA không lưu, không lọc trùng, token không tự làm mới, không kiểm quyền gửi. Bản Arden có hàng đợi bền, nhưng chỉ cho tài khoản cá nhân. Đường gửi `transaction`/`promotion` có ở cả hai bản, không riêng PhucMPham. Không bản nào có ZBS Template |
| R8 | Đúng một phần | Tài liệu ghi dịch vụ "Tin UID Giao dịch" và "UID Truyền thông cá nhân" dừng từ 01/03/2026. Tôi không tìm thấy thông báo nào về đổi định dạng UID |

## Nguồn

Mọi trang dưới đây được truy cập ngày 2026-11-07.

- Webhook: https://docs.zaloplatforms.com/docs/OA/webhook/tong-quan
- Sự kiện người dùng gửi tin, kèm công thức chữ ký: https://docs.zaloplatforms.com/docs/OA/webhook/tin-nhan/su-kien-nguoi-dung-gui-tin-nhan
- Xác thực và ủy quyền: https://docs.zaloplatforms.com/docs/OA/bat-dau/xac-thuc-va-uy-quyen-cho-ung-dung-new
- Tổng quan tin nhắn: https://docs.zaloplatforms.com/docs/OA/tin-nhan/tong-quan
- Tin tư vấn: https://docs.zaloplatforms.com/docs/OA/tin-nhan/tin-tu-van/gui-tin-tu-van-dang-van-ban và https://docs.zaloplatforms.com/docs/OA/tin-nhan/tin-tu-van/dieu-kien-gui-tin-tu-van
- Tin giao dịch (thông báo dừng): https://docs.zaloplatforms.com/docs/OA/tin-nhan/tin-giao-dich/gui-tin-giao-dich
- Tin truyền thông cá nhân (thông báo dừng): https://docs.zaloplatforms.com/docs/OA/tin-nhan/tin-truyen-thong/gui-tin-truyen-thong-ca-nhan
- ZBS Template qua UID: https://docs.zaloplatforms.com/docs/ZBS/gui-tin-template-qua-uid/api-gui-tin-qua-uid
- Upload ảnh: https://docs.zaloplatforms.com/docs/OA/tin-nhan/quan-ly-tin-nhan/upload-hinh-anh
- Chi tiết người dùng: https://docs.zaloplatforms.com/docs/OA/quan-ly/quan-ly-thong-tin-nguoi-dung/truy-xuat-chi-tiet-nguoi-dung
- Giới hạn tốc độ: https://docs.zaloplatforms.com/docs/OA/phu-luc/gioi-han-toc-do-api
- Thông báo V251209 (chỉ đọc được tiêu đề và mô tả): https://developers.zalo.me/changelog/thong-bao-ra-mat-zbs-template-message-va-lo-trinh-chuyen-doi-7814
- Registry npm: https://registry.npmjs.org/@ardennguyen/zalo-agent-cli/2.5.9, https://registry.npmjs.org/@ardennguyen/zalo-mcp, https://registry.npmjs.org/zalo-agent-cli

Permalink mã đã dẫn:

- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/commands/oa-listen.js#L119-L123
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/commands/oa-listen.js#L210-L213
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/commands/oa.js#L181-L210
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/core/oa-client.js#L135-L153
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/core/oa-client.js#L298-L312
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/src/core/webhook-outbox.js#L1-L22
- https://github.com/ardennguyen/zalo-agent-cli/blob/f867f0e992bea50d082c34cbe0637f209ee3a3c1/NOTICE#L13-L19
- https://github.com/ardennguyen/zalo-mcp/blob/89e209c219be09c08995fd2b5330ea1f4cd2d287/mcp-server.js#L205-L215
- https://github.com/ardennguyen/zalo-mcp/blob/89e209c219be09c08995fd2b5330ea1f4cd2d287/package-lock.json#L22-L23
- https://github.com/PhucMPham/zalo-agent-cli/blob/ce630eeda49329a2089aa471eb8c450ddfbc84b1/src/commands/oa-listen.js#L32-L36
- https://github.com/PhucMPham/zalo-agent-cli/blob/ce630eeda49329a2089aa471eb8c450ddfbc84b1/src/commands/oa-listen.js#L150-L159
- https://github.com/PhucMPham/zalo-agent-cli/blob/ce630eeda49329a2089aa471eb8c450ddfbc84b1/src/core/oa-client.js#L141-L160
- https://github.com/PhucMPham/zalo-agent-cli/blob/ce630eeda49329a2089aa471eb8c450ddfbc84b1/src/core/oa-client.js#L232-L236

## Nói ngắn gọn nhất

Cả ba repo đều gói phần chạy được trên Zalo vào tài khoản cá nhân qua một thư viện không chính thức. Phần OA thì có, nhưng chỉ ở dạng lệnh rời: công thức chữ ký webhook sai, token không tự làm mới, sự kiện không được lưu, và hai loại tin đã bị Zalo dừng vẫn còn trong mã. Mã của Arden lại không được dùng cho việc kinh doanh nếu chưa xin phép. Vì vậy, cách hợp lý là tự viết một bộ nối OA nhỏ chạy trên một máy chủ luôn bật, lấy lại vài hàm MIT của PhucMPham có sửa, và chỉ học cách làm từ mã của Arden. Hướng "Claude Desktop cộng Zalo MCP" không nhận được tin của OA và phụ thuộc vào việc máy Mac luôn mở, nên tôi đề xuất bỏ hướng này.

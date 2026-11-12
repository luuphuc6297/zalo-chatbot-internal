# thom house — Business Knowledge Base

> Repository tổng hợp **toàn bộ thông tin doanh nghiệp thom house healing studio**, được xây dựng để chatbot có thể hiểu doanh nghiệp ở mức triết lý, không chỉ ở mức dữ liệu.
>
> *"Beauty is the harmony of body and soul."* — thom house

---

## Mục đích

Xây dựng một bộ tài liệu **"đủ sâu để chatbot trả lời như người trong nhà"** — bao gồm:

- **Bản sắc thương hiệu** (brand essence): doanh nghiệp là ai, từ năm nào, định vị thế nào.
- **Tone of voice & writing style:** cách viết, từ vựng đặc trưng, cấu trúc câu chữ.
- **Catalogue dịch vụ:** mô tả từng liệu trình kèm cảm xúc, đối tượng, giá.
- **Cấu trúc giá & quy luật khung giờ.**
- *(Sẽ bổ sung)* Customer personas, combo, chương trình thành viên…

---

## Cấu trúc thư mục

```
thomhouse-analytics/
│
├── README.md                          ← Bạn đang đọc
├── _intake-log.md                     ← Lịch sử các đợt upload tài liệu
│
├── documentation/                     ⭐ Documentation chiến lược (13 chương)
│   ├── README.md                      ← Index 13 chương
│   ├── 01-brand-story.md              ← Câu chuyện thương hiệu
│   ├── 02-core-values.md              ← 6 giá trị cốt lõi
│   ├── 03-service-philosophy.md       ← Triết lý dịch vụ (3 cội rễ, 5 mặt định vị)
│   ├── 04-service-culture-mindset.md  ← Văn hóa & tư duy làm dịch vụ
│   ├── 05-customer-personas.md        ← 5 chân dung khách hàng
│   ├── 06-brand-voice-identity.md     ← Tone of voice + visual identity
│   ├── 07-customer-journey.md         ← Hành trình khách 5 giai đoạn
│   ├── 08-positioning-differentiation.md ← Định vị thị trường & USP
│   ├── 09-knowledge-foundations.md    ← YHCT + Dược liệu Việt + Công nghệ (tổng quan)
│   ├── 10-services-deep-dive.md       ← Nguyên lý + matrix so sánh + FAQ tư vấn
│   ├── 11-deep-knowledge-techniques-herbs.md ⭐ Chuyên sâu YHCT/Diện Chẩn + FAQ 25 câu
│   ├── 12-chatbot-response-formatting.md ⭐ Format câu trả lời + template 20 Q&A + bảng giá 23 dịch vụ
│   └── 13-critical-chatbot-fixes.md 🚨 URGENT — Blacklist từ y khoa CẤM + 8 anti-patterns + 5 ví dụ sửa
│
├── knowledge-base/                    ← Dữ liệu nguồn chi tiết từng menu (operational)
│   ├── 00-brand-essence.md            ← DNA thương hiệu (đọc đầu tiên)
│   ├── 01-tone-voice.md               ← Phong cách ngôn ngữ thom house
│   ├── 02-services/
│   │   ├── README.md                  ← Index 5 menu, hướng dẫn chatbot chọn menu
│   │   ├── relaxation-menu.md         ← Menu thư giãn (4 dịch vụ)
│   │   ├── health-menu.md             ← Menu khỏe (6 dịch vụ YHCT)
│   │   ├── women-health-menu.md       ← Menu phụ nữ (5 dịch vụ, có Signature)
│   │   ├── skincare-menu.md           ← Menu da (5 dịch vụ skincare, có Signature)
│   │   └── hair-care-menu.md          ← Menu tóc (3 dịch vụ dược liệu Việt)
│   └── 03-pricing-structure.md        ← Quy luật giá + khung giờ
│
└── raw-content/                       ← Văn bản gốc trích từ ảnh menu
    ├── batch-01-relaxation-menu.md
    ├── batch-02-health-menu.md
    ├── batch-03-women-health-menu.md
    ├── batch-04-skincare-menu.md
    └── batch-05-hair-care-menu.md
```

### Khác biệt giữa `documentation/` và `knowledge-base/`

- **`documentation/`** = **synthesis chiến lược** — câu chuyện, triết lý, văn hóa, personas, USP, FAQ. Đọc theo thứ tự 01 → 10.
- **`knowledge-base/`** = **dữ liệu nguồn chi tiết** — từng menu, từng dịch vụ, từng giá tiền. Tra cứu theo nhu cầu.

---

## Trạng thái hiện tại (cập nhật 2026-05-16)

✅ **Batch 01 — Menu giúp bạn thư giãn (9 slides, 4 dịch vụ)** đã xử lý.
✅ **Batch 02 — Menu giúp bạn khỏe (19 slides, 6 dịch vụ YHCT)** đã xử lý.
✅ **Batch 03 — Menu chăm sóc sức khỏe phụ nữ (7 slides, 5 dịch vụ + manifesto founder)** đã xử lý.
✅ **Batch 04 — Menu chăm sóc da (5 slides, 5 dịch vụ skincare hiện đại)** đã xử lý.
✅ **Batch 05 — Menu chăm sóc tóc (9 slides, 3 dịch vụ dược liệu Việt)** đã xử lý — mở rộng định vị thom house thành **3 cội rễ** (Đông y YHCT + Dân gian Việt + Công nghệ hiện đại).

**Tổng:** 23 dịch vụ × 5 menu × 5 mảng triết lý (Soul rest / Body care / Sacred care / Modern beauty tech / Vietnamese herbal heritage).
**Signature:** 2 (Yoni Retreat, Mụn 5 in 1).
**Giá dao động:** 139,000 – 3,500,000 VNĐ.

⏳ Chị Luu sẽ upload thêm các menu khác (có thể là facial cao cấp, gói liệu trình theo buổi, menu nam giới, chương trình thành viên...).

### Chi tiết cần xác nhận với chị Luu
- Địa chỉ chuẩn: **Tân Hưng** (đa số) vs **Tân Kiểng** (1 slide trong batch 03).
- Cách viết tên thương hiệu: **thomhouse** (thường) vs **Thơm House** (hoa, có dấu).
- "Theo thời gian khuyến mại" trong Mụn 5 in 1 cụ thể là gì.
- "Whitetox" là sản phẩm gì.
- Cover slide "DA MỤN" — có phải là 1 sub-cover trong menu chăm sóc da rộng hơn?
- **"Nan tóc"** vs **"Nang tóc"** — typo hay chính tả riêng (batch 05).
- **"Xã phục hồi"** vs **"Xả phục hồi"** — typo hay chính tả riêng (batch 05).

Xem chi tiết tại [`_intake-log.md`](_intake-log.md).

---

## Hướng dẫn đọc file (cho chatbot và con người)

**Nếu bạn là chatbot và cần trả lời khách hàng:**
1. Đọc trước `knowledge-base/00-brand-essence.md` để biết thom house là ai.
2. Đọc `knowledge-base/01-tone-voice.md` để biết cách nói thế nào.
3. Tra dịch vụ + giá trong `knowledge-base/02-services/` và `03-pricing-structure.md`.
4. Khi không chắc chắn → **không tự bịa**, hỏi lại hoặc trả lời trung tính.

**Nếu bạn (chị Luu / team) muốn cập nhật:**
- Upload menu mới → để em tạo `raw-content/batch-NN-*.md` mới + bổ sung knowledge base.
- Sửa giá → cập nhật trực tiếp ở `02-services/` và `03-pricing-structure.md`, ghi chú vào `_intake-log.md`.

---

## Thông tin liên hệ doanh nghiệp

- **Tên:** thom house healing studio
- **Từ năm:** 2019
- **Địa chỉ:** 72 đường số 37, phường Tân Hưng, quận 7, TP. Hồ Chí Minh
- **Slogan:** *"Beauty is the harmony of body and soul."*

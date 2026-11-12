"""Build data/services.json from hand-curated records and verify every price/duration
against the cited source line (raw-content menu transcription = canonical source).

Usage: python3 -I scripts/build_services.py <project_root>
Exit code 1 if any variant cannot be traced to its cited line.
"""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
drive = root / "sources" / "drive"
R1 = "sources/drive/raw-content/batch-01-relaxation-menu.md"
R2 = "sources/drive/raw-content/batch-02-health-menu.md"
R3 = "sources/drive/raw-content/batch-03-women-health-menu.md"
R4 = "sources/drive/raw-content/batch-04-skincare-menu.md"
R5 = "sources/drive/raw-content/batch-05-hair-care-menu.md"
KBP = "sources/drive/knowledge-base/03-pricing-structure.md"
D12 = "sources/drive/documentation/12-chatbot-response-formatting.md"
D13 = "sources/drive/documentation/13-critical-chatbot-fixes.md"
D11 = "sources/drive/documentation/11-deep-knowledge-techniques-herbs.md"
D10 = "sources/drive/documentation/10-services-deep-dive.md"
D09 = "sources/drive/documentation/09-knowledge-foundations.md"
KBW = "sources/drive/knowledge-base/02-services/women-health-menu.md"

DAY, NIGHT, ALLDAY = "09:00-20:30", "after_20:30", "09:00-24:00"


def v(d, p, tw, note, src_line, src=None):
    return {"duration_min": d, "price_vnd": p, "time_window": tw, "condition_note": note,
            "source": {"path": src, "line": src_line}}


NIGHT_NOTE = "Menu ghi 'Sau 20h30'; giờ kết thúc không ghi trên menu (giờ mở cửa chưa xác nhận)."
FIXED_NOTE = "Một mức giá, menu không chia khung giờ."

S = []

def add(**kw):
    kw.setdefault("is_signature", False)
    kw.setdefault("who_should_avoid_or_consult", [])
    kw.setdefault("flagged_claims", [])
    kw.setdefault("conflicts", [])
    kw.setdefault("ingredients_or_devices", [])
    kw["status"] = "draft_unapproved"
    for var in kw["variants"]:
        var["source"]["path"] = var["source"]["path"] or kw["_raw"]
    kw["sources"] = [{"path": kw["_raw"], "line": l} for l in kw.pop("_raw_lines")] + kw.pop("_more_sources", [])
    kw.pop("_raw")
    S.append(kw)

# ---------------- relaxation ----------------
add(id="mo-vai-nang-mat", group="relaxation",
    name_vi="Mở Vai – Nâng Mặt (Vai Cổ Thông Sáng Mặt Tự Nhiên)",
    short_description_vi="Liệu trình massage thả lỏng vùng vai cổ, kết hợp chăm sóc gương mặt, 60 phút.",
    _raw=R1, _raw_lines=[27, 43, 52, 54, 55],
    variants=[v(60, 350000, DAY, None, 54), v(60, 389000, "after_20:30", NIGHT_NOTE, 55)],
    process_steps_vi=[],
    notes_vi="Menu không có slide quy trình cho dịch vụ này; chỉ có đoạn giới thiệu (batch-01 dòng 27-39).",
    _more_sources=[{"path": KBP, "line": 11}, {"path": KBP, "line": 12}, {"path": D12, "line": 601}, {"path": D13, "line": 243}],
    conflicts=[
        {"field": "name_vi", "values": [
            {"value": "Mở Vai – Nâng Mặt", "path": R1, "line": 27},
            {"value": "Vai Cổ Thông Sáng Mặt Tự Nhiên", "path": R1, "line": 43}],
         "note": "Slide giới thiệu và slide giá dùng hai tên khác nhau; tài liệu 13 coi 'Mở Vai – Nâng Mặt' là tên đúng (13:279)."},
        {"field": "process_steps_vi", "values": [
            {"value": "Có bước diện chẩn mặt (cốt lõi)", "path": D11, "line": 140},
            {"value": "Có bước diện chẩn mặt", "path": D09, "line": 32},
            {"value": "Menu không ghi quy trình", "path": R1, "line": 43}],
         "note": "Tài liệu tổng hợp gán bước diện chẩn cho dịch vụ này, menu gốc không có."}])

add(id="massage-chan", group="relaxation", name_vi="Massage chân",
    short_description_vi="Massage chân với tinh dầu ấm và khăn ấm, 30 hoặc 45 phút.",
    _raw=R1, _raw_lines=[59, 65, 71, 80, 81],
    variants=[v(30, 199000, ALLDAY, "Menu ghi một khung 9h – 24h, giá không đổi theo giờ.", 80),
              v(45, 250000, ALLDAY, "Menu ghi một khung 9h – 24h, giá không đổi theo giờ.", 81)],
    process_steps_vi=[],
    notes_vi="Không có slide quy trình; mô tả: thao tác nhẹ, tinh dầu ấm, khăn êm (batch-01 dòng 65).",
    ingredients_or_devices=["tinh dầu ấm (loại tinh dầu không ghi)", "khăn ấm"],
    _more_sources=[{"path": KBP, "line": 13}, {"path": KBP, "line": 14}, {"path": D12, "line": 599}, {"path": D13, "line": 241}])

add(id="massage-co-vai-gay", group="relaxation", name_vi="Massage cổ, vai, gáy",
    short_description_vi="Massage vùng cổ, vai, gáy với tinh dầu ấm, 30 hoặc 60 phút.",
    _raw=R1, _raw_lines=[85, 91, 99, 109, 110, 111, 112],
    variants=[v(30, 199000, DAY, None, 109), v(60, 399000, DAY, None, 110),
              v(30, 239000, NIGHT, NIGHT_NOTE, 111), v(60, 449000, NIGHT, NIGHT_NOTE, 112)],
    process_steps_vi=[], notes_vi="Không có slide quy trình (batch-01 dòng 85-112).",
    ingredients_or_devices=["tinh dầu ấm (loại không ghi)"],
    _more_sources=[{"path": KBP, "line": l} for l in (15, 16, 17, 18)] + [{"path": D12, "line": 600}, {"path": D13, "line": 242}])

add(id="massage-body-thu-gian", group="relaxation", name_vi="Massage body thư giãn",
    short_description_vi="Massage toàn thân thư giãn với tinh dầu ấm, kết thúc bằng nước ấm và trà đường nâu, 60 hoặc 75 phút.",
    _raw=R1, _raw_lines=[116, 122, 124, 132, 142, 143, 144, 145],
    variants=[v(60, 429000, DAY, None, 142), v(75, 499000, DAY, None, 143),
              v(60, 499000, NIGHT, NIGHT_NOTE, 144), v(75, 569000, NIGHT, NIGHT_NOTE, 145)],
    process_steps_vi=[], notes_vi="Không có slide quy trình; đoạn giới thiệu nhắc tinh dầu ấm, làn nước ấm, trà đường nâu (batch-01 dòng 122-124).",
    ingredients_or_devices=["tinh dầu ấm (loại không ghi)", "trà đường nâu"],
    _more_sources=[{"path": KBP, "line": l} for l in (19, 20, 21, 22)] + [{"path": D12, "line": 602}, {"path": D13, "line": 244}])

# ---------------- health ----------------
add(id="dien-chan-ngua-dot-quy", group="health", name_vi="Diện chẩn ngừa đột quỵ",
    short_description_vi="Liệu trình 180 phút gồm diện chẩn mặt, ấn huyệt, hơ ngải, trục hàn, massage toàn thân và chải dịch bằng dụng cụ.",
    _raw=R2, _raw_lines=[20, 24, 31, 53, 63],
    variants=[v(180, 2990000, None, FIXED_NOTE, 63)],
    process_steps_vi=["Diện chẩn mặt – ấn huyệt xoá tắt nghẽn mạch máu.", "Khai thông phần đầu, cổ, ngực, bụng.",
                      "Chải, day, hơ ngải bộ huyệt chống đột quỵ trước & sau.", "Trục Hàn khí tích tụ ở các cơ, khớp, ổ bụng.",
                      "Massage cân bằng âm dương toàn thân.", "Chải dịch bằng dụng cụ chuyên dụng cho toàn thân",
                      "Thải độc và phong tán hàn ra bàn chân", "Vỗ hạch bạch huyết, hơ ngải dẫn lửa làm ấm cơ thể."],
    ingredients_or_devices=["ngải cứu (hơ ngải)", "dụng cụ chải dịch chuyên dụng (loại không ghi)"],
    flagged_claims=[
        {"text": "Tên dịch vụ: Diện chẩn ngừa đột quỵ", "reason": "Tên hàm ý phòng ngừa một bệnh nguy hiểm; chưa có căn cứ được nêu.", "path": R2, "line": 56},
        {"text": "ấn huyệt xoá tắt nghẽn mạch máu", "reason": "Khẳng định tác động lên mạch máu, không kiểm chứng được.", "path": R2, "line": 24},
        {"text": "bộ huyệt chống đột quỵ", "reason": "Claim phòng bệnh.", "path": R2, "line": 26},
        {"text": "khu vực ảnh hưởng trực tiếp đến tuần hoàn máu não", "reason": "Claim sinh lý không kiểm chứng.", "path": R2, "line": 43},
        {"text": "Phòng ngừa đột quỵ chủ động cho người 40+", "reason": "Tài liệu tổng hợp thêm đối tượng và claim không có trên menu.", "path": D12, "line": 404},
        {"text": "gia đình có tiền sử đột quỵ", "reason": "Nhắm người có nguy cơ bệnh; cần chuyển bác sĩ thay vì bán dịch vụ.", "path": D10, "line": 62}],
    _more_sources=[{"path": KBP, "line": 35}, {"path": D12, "line": 613}, {"path": D13, "line": 233}])

SHARED6 = ["Massage chân cơ bản, kiểm tra điểm đau", "Massage lưng cơ bản. Đã thông cơ bó vai, cổ.", "Bấm huyệt vai cổ",
           "Chăm sóc từng bên tay-đầu-cổ", "Lăn dụng cụ, hơ ngải cứu", "Massage, diện chẩn mặt dụng cụ đồng ứng vai cổ."]

add(id="giai-moi-dung-lau", group="health", name_vi="Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch",
    short_description_vi="Liệu trình 60 phút tập trung vùng chân, kết hợp ấn huyệt, massage và hơi ấm ngải cứu cho người đứng hoặc đi lại nhiều.",
    _raw=R2, _raw_lines=[69, 90, 100, 112],
    variants=[v(60, 599000, None, FIXED_NOTE, 112)],
    process_steps_vi=SHARED6,
    notes_vi="Quy trình 6 bước trùng nguyên văn với Thiếu máu não (batch-02 dòng 127).",
    ingredients_or_devices=["ngải cứu", "thảo dược (loại không ghi)", "dụng cụ lăn (loại không ghi)"],
    flagged_claims=[{"text": "chăm sóc chân giãn tĩnh mạch", "reason": "Tên dịch vụ gắn với một bệnh lý tĩnh mạch; khách giãn tĩnh mạch cần được khuyên khám bác sĩ.", "path": R2, "line": 84},
                    {"text": "hỗ trợ chăm sóc giãn tĩnh mạch nhẹ", "reason": "Tài liệu tổng hợp tự phân độ bệnh (nhẹ/nặng), chatbot không đánh giá được.", "path": D09, "line": 389}],
    who_should_avoid_or_consult=[{"text": "Khách giãn tĩnh mạch nặng nên khám bác sĩ", "source_type": "derived_doc_unapproved", "path": D09, "line": 389}],
    conflicts=[{"field": "name_vi", "values": [{"value": "Giải mỏi đứng lâu – chăm sóc chân giãn tĩnh mạch", "path": R2, "line": 100},
                                              {"value": "Giải mỏi đứng lâu / Chăm sóc chân giãn tĩnh mạch", "path": R2, "line": 69}],
                "note": "Khác dấu nối, cùng một dịch vụ."}],
    _more_sources=[{"path": KBP, "line": 30}, {"path": D12, "line": 608}, {"path": D13, "line": 228}])

add(id="thieu-mau-nao", group="health", name_vi="Thiếu máu não – tê tay, căng thẳng khó ngủ",
    short_description_vi="Liệu trình 60 phút chăm sóc vai, cổ, tay, đầu bằng giải cơ sâu và ấn huyệt; menu gọi là chăm sóc vai cổ chuyên sâu.",
    _raw=R2, _raw_lines=[116, 127, 133, 147, 153, 166],
    variants=[v(60, 599000, None, FIXED_NOTE, 166)],
    process_steps_vi=SHARED6,
    notes_vi="Quy trình 6 bước trùng nguyên văn với Giải mỏi đứng lâu (batch-02 dòng 127).",
    ingredients_or_devices=["ngải cứu", "dụng cụ lăn (loại không ghi)"],
    flagged_claims=[{"text": "Tên dịch vụ: Thiếu máu não – tê tay, căng thẳng khó ngủ", "reason": "Tên dùng chẩn đoán y khoa; tê tay kéo dài có thể là dấu hiệu bệnh cần khám.", "path": R2, "line": 153},
                    {"text": "liên quan trực tiếp đến tuần hoàn và thần kinh", "reason": "Claim sinh lý không kiểm chứng.", "path": R2, "line": 147}],
    _more_sources=[{"path": KBP, "line": 31}, {"path": D12, "line": 609}, {"path": D13, "line": 229}])

add(id="dau-that-lung-moi-goi", group="health", name_vi="Đau thắt lưng mỏi gối",
    short_description_vi="Liệu trình 60 phút chăm sóc chân, lưng, vùng thắt lưng và đầu bằng ấn huyệt, massage và làm ấm theo quan niệm Đông y.",
    _raw=R2, _raw_lines=[170, 174, 194, 196, 206, 216],
    variants=[v(60, 599000, None, FIXED_NOTE, 216)],
    process_steps_vi=["Ấn huyệt chân bổ khí thận, massage chân thải dịch phù nề.", "Massage lưng cơ bản, giải các nhóm cơ thắt eo, cơ mông, cơ hông",
                      "Bấm những bộ nguyệt chăm sóc thận", "Massage, diện chẩn mặt bộ bổ thận.", "Khai thông đầu, ấn huyệt tay."],
    flagged_claims=[{"text": "giảm đau mỏi rõ rệt", "reason": "Claim hiệu quả không có căn cứ.", "path": R2, "line": 194},
                    {"text": "chính khí của thận đang suy yếu", "reason": "Diễn giải triệu chứng (tóc bạc, đầu nóng) thành bệnh của tạng; chatbot không nên chẩn đoán.", "path": R2, "line": 190}],
    conflicts=[{"field": "process_steps_vi", "values": [{"value": "Bấm những bộ nguyệt chăm sóc thận", "path": R2, "line": 176}],
                "note": "'nguyệt' nhiều khả năng là lỗi gõ của 'huyệt'; giữ nguyên văn, cần chủ doanh nghiệp xác nhận."}],
    _more_sources=[{"path": KBP, "line": 32}, {"path": D12, "line": 610}, {"path": D13, "line": 230}])

add(id="detox-mui-co-the", group="health", name_vi="Detox mùi cơ thể",
    short_description_vi="Liệu trình 90 phút gồm massage toàn thân, chải dịch bằng dụng cụ, vỗ vùng hạch bạch huyết, massage mặt và hơ ngải.",
    _raw=R2, _raw_lines=[220, 224, 242, 244, 248, 264],
    variants=[v(90, 1190000, None, FIXED_NOTE, 264)],
    process_steps_vi=["Ứng dụng massage cân bằng âm dương", "Thải dịch bằng dụng cụ chuyên dụng cho toàn thân", "Vỗ hạch bạch huyết toàn thân",
                      "Massage mặt – Khai thông đầu, vai cổ", "Hơ ngải huyệt đạo làm ấm lại cơ thể"],
    ingredients_or_devices=["tinh dầu dược liệu (loại không ghi)", "ngải cứu", "dụng cụ thải dịch (loại không ghi)"],
    flagged_claims=[{"text": "độc tố dễ tích tụ và thoát ra qua mồ hôi, từ đó gây mùi cơ thể", "reason": "Giải thích cơ chế 'thải độc' không có căn cứ; mùi cơ thể kéo dài có thể có nguyên nhân bệnh lý.", "path": R2, "line": 244},
                    {"text": "làm sạch từ bên trong", "reason": "Claim detox không kiểm chứng.", "path": R2, "line": 248}],
    conflicts=[{"field": "ingredients_or_devices", "values": [{"value": "muối biển và trà xanh (chatbot tự bịa)", "path": D13, "line": 297}],
                "note": "Tài liệu 13 ghi đây là thông tin bịa, menu không có."}],
    _more_sources=[{"path": KBP, "line": 33}, {"path": D12, "line": 611}, {"path": D13, "line": 231}])

add(id="thai-han-giai-cam", group="health", name_vi="Thải hàn giải cảm",
    short_description_vi="Liệu trình 90 phút gồm giải cơ vùng lưng, giác hơi không nhiệt theo yêu cầu, diện chẩn và massage mặt, hơ ngải; có hướng dẫn tự giữ ấm tại nhà.",
    _raw=R2, _raw_lines=[268, 273, 290, 298, 306, 316],
    variants=[v(90, 1200000, None, FIXED_NOTE, 316)],
    process_steps_vi=["Giải cơ sâu vùng lưng, vai cổ, phong tán hàn vùng lưng", "Giác hơi không nhiệt (theo nhu cầu khách hàng)", "Thải dịch bụng",
                      "Diện chẩn mặt – Massage mặt – Khai thông đầu", "Bày hàn qua lòng bàn chân", "Hơ ngải dẫn lửa làm ấm lại cơ thể sau trục hàn"],
    ingredients_or_devices=["cốc giác hơi (không nhiệt)", "ngải cứu"],
    flagged_claims=[{"text": "từng nhiễm hàn suốt nhiều năm và đã chăm sóc dứt điểm", "reason": "Lời chứng cá nhân dễ bị hiểu là cam kết khỏi hẳn; tài liệu 12 dùng lại để bán dịch vụ.", "path": R2, "line": 290},
                    {"text": "Có thể hơi mệt nhẹ 1-2 ngày là bình thường (cơ thể đang đẩy độc tố)", "reason": "Mẫu tin chăm sóc sau buổi coi phản ứng là bình thường bằng giải thích 'đẩy độc tố'.", "path": "sources/drive/documentation/07-customer-journey.md", "line": 203}],
    who_should_avoid_or_consult=[{"text": "Người dùng thuốc chống đông: không giác hơi mạnh", "source_type": "derived_doc_unapproved", "path": D11, "line": 1298}],
    _more_sources=[{"path": KBP, "line": 34}, {"path": D12, "line": 612}, {"path": D13, "line": 232}])

# ---------------- women ----------------
add(id="cham-soc-dau-bung-kinh", group="women", name_vi="Chăm sóc đau bụng kinh, rối loạn kinh nguyệt",
    short_description_vi="Liệu trình 60 phút gồm massage lưng, ấn huyệt vùng lưng và bụng, massage mặt, hơ ngải.",
    _raw=R3, _raw_lines=[50, 60, 70, 71],
    variants=[v(60, 599000, None, FIXED_NOTE + " Ảnh menu ghi '599.000 VNĐ' (dấu chấm).", 71)],
    process_steps_vi=["Massage giảm phù nề", "Massage lưng lưu thông máu", "Đả thông bát liu vùng lưng", "Ấn huyệt lưng, bụng gây đau bụng kinh",
                      "Massage mặt, diện chẩn mặt bằng dụng cụ", "Khai thông đầu.", "Hơ ngải, ấn huyệt tay"],
    ingredients_or_devices=["ngải cứu", "dụng cụ diện chẩn (loại không ghi)"],
    flagged_claims=[{"text": "Tên dịch vụ: ... rối loạn kinh nguyệt", "reason": "Dùng tên rối loạn phụ khoa; đau bụng kinh dữ dội cần khuyên khám phụ khoa.", "path": R3, "line": 55}],
    conflicts=[{"field": "process_steps_vi", "values": [{"value": "Ấn huyệt lưng, bụng gây đau bụng kinh", "path": R3, "line": 65}],
                "note": "Câu nguyên văn tối nghĩa ('gây đau bụng kinh'); không tự sửa, cần chủ doanh nghiệp xác nhận."}],
    _more_sources=[{"path": KBP, "line": 46}, {"path": D12, "line": 620}, {"path": D13, "line": 216}])

add(id="se-khit-lam-hong-yoni", group="women", name_vi="Se khít làm hồng yoni",
    short_description_vi="Liệu trình chăm sóc vùng kín 45 phút gồm vệ sinh, ủ, massage và ấn huyệt, thoa serum, hơ ngải, massage mặt.",
    _raw=R3, _raw_lines=[77, 84, 96, 98, 99],
    variants=[v(45, 2500000, None, FIXED_NOTE, 98)],
    process_steps_vi=["Khai thông tắt nghẽn vùng bẹn", "Vệ sinh cô bé", "Ủ làm mềm cô bé", "Massage, ấn huyệt se khít", "Ủ làm hồng cô bé",
                      "Thoa serum giảm viêm nhiễm", "Hơ ngải", "Massage mặt, diện chẩn mặt, khai thông đầu"],
    ingredients_or_devices=["serum (loại không ghi)", "ngải cứu"],
    flagged_claims=[{"text": "Đồng thời hỗ trợ chữa sa tử cung", "reason": "Claim chữa bệnh phụ khoa; trái với danh sách từ cấm của tài liệu 13.", "path": R3, "line": 96},
                    {"text": "Giảm thâm, giảm viêm nhiễm", "reason": "Claim tác động lên nhiễm trùng phụ khoa.", "path": R3, "line": 96},
                    {"text": "Thon gọn môi bé sau một lộ trình ngắn hạn", "reason": "Claim thay đổi giải phẫu không kiểm chứng.", "path": R3, "line": 96},
                    {"text": "Thoa serum giảm viêm nhiễm", "reason": "Sản phẩm thoa vùng kín không rõ thành phần, kèm claim kháng viêm.", "path": R3, "line": 91}],
    who_should_avoid_or_consult=[
        {"text": "Dưới 2-3 tháng sau sinh: tài liệu khuyên chưa làm", "source_type": "derived_doc_unapproved", "path": D11, "line": 1247},
        {"text": "Đang mang thai: tài liệu ghi toàn menu phụ nữ không phù hợp", "source_type": "derived_doc_unapproved", "path": D11, "line": 1231}],
    _more_sources=[{"path": KBP, "line": 48}, {"path": D12, "line": 622}, {"path": D13, "line": 217}])

add(id="yoni-retreat", group="women", name_vi="Yoni Retreat", is_signature=True,
    short_description_vi="Dịch vụ Signature 100 phút chăm sóc bốn vùng: lưng, mặt, bụng và vùng kín; kèm tặng Nắn chỉnh thu hẹp sàn chậu.",
    _raw=R3, _raw_lines=[103, 111, 113, 114, 117, 121, 131],
    variants=[v(100, 3500000, None, FIXED_NOTE + " Kèm tặng Nắn chỉnh thu hẹp sàn chậu (menu ghi 'Tặng nắn chỉnh sàn chậu').", 114)],
    process_steps_vi=[],
    notes_vi="Menu không liệt kê bước; chỉ liệt kê 4 vùng chăm sóc: Chăm sóc lưng, Mặt, Bụng, Cô bé (batch-03 dòng 121-128).",
    flagged_claims=[{"text": "Tử cung bị sa trễ sau khi sanh thường ... lâu hồi phục", "reason": "Gắn dịch vụ với sa tử cung và rối loạn tình dục sau sinh.", "path": R3, "line": 117},
                    {"text": "Cảm giác hơi căng nhẹ vùng bụng dưới là bình thường", "reason": "Mẫu tin sau buổi coi triệu chứng vùng bụng là bình thường.", "path": "sources/drive/documentation/07-customer-journey.md", "line": 220},
                    {"text": "dịch vụ đắt nhất hiện có ... (chỉ sau Diện chẩn ngừa đột quỵ 2.99M)", "reason": "Câu xếp hạng sai và tự mâu thuẫn (3,5 triệu > 2,99 triệu).", "path": KBW, "line": 150}],
    who_should_avoid_or_consult=[
        {"text": "Dưới 2-3 tháng sau sinh: tài liệu khuyên chưa làm", "source_type": "derived_doc_unapproved", "path": D11, "line": 1247},
        {"text": "Đang mang thai: tài liệu ghi toàn menu phụ nữ không phù hợp", "source_type": "derived_doc_unapproved", "path": D11, "line": 1231}],
    conflicts=[{"field": "price_rank", "values": [
        {"value": "đắt thứ 2 toàn studio (sau 2.99M)", "path": KBP, "line": 55},
        {"value": "đắt thứ 2 toàn studio", "path": "sources/drive/_intake-log.md", "line": 81},
        {"value": "đắt nhất hiện có (chỉ sau 2.99M)", "path": KBW, "line": 150},
        {"value": "đắt nhất, trọn vẹn nhất", "path": "sources/drive/documentation/05-customer-personas.md", "line": 212}],
        "note": "Theo giá menu, 3.500.000đ là giá cao nhất trong 23 dịch vụ; các câu 'đắt thứ 2' sai."}],
    _more_sources=[{"path": KBP, "line": 49}, {"path": D12, "line": 623}, {"path": D13, "line": 218}])

add(id="nan-chinh-thu-hep-san-chau", group="women", name_vi="Nắn chỉnh thu hẹp sàn chậu",
    short_description_vi="Thao tác nắn chỉnh vùng xương chậu 10 phút, menu ghi dành cho phụ nữ sau sinh và người có xương chậu rộng hoặc lệch.",
    _raw=R3, _raw_lines=[137, 147, 149, 151, 152],
    variants=[v(10, 500000, None, FIXED_NOTE, 152)],
    process_steps_vi=[], notes_vi="Menu không ghi các bước.",
    flagged_claims=[{"text": "hỗ trợ nâng cao các bệnh lý sa tử cung, viêm nhiễm, khí hư", "reason": "Claim tác động lên bệnh phụ khoa.", "path": R3, "line": 149},
                    {"text": "Sa tử cung nặng (độ 3-4) ... dịch vụ chỉ hỗ trợ độ nhẹ", "reason": "Ngầm khẳng định dịch vụ hỗ trợ sa tử cung độ nhẹ; chatbot không phân độ được.", "path": D11, "line": 1271}],
    who_should_avoid_or_consult=[
        {"text": "Dưới 2-3 tháng sau sinh: tài liệu khuyên chưa làm", "source_type": "derived_doc_unapproved", "path": D11, "line": 1247},
        {"text": "Đang mang thai: không phù hợp", "source_type": "derived_doc_unapproved", "path": D11, "line": 1231}],
    conflicts=[{"field": "price_per_minute_rank", "values": [
        {"value": "giá/phút cao nhất toàn studio (50.000đ/phút)", "path": KBP, "line": 255},
        {"value": "giá/phút cao nhất menu", "path": KBW, "line": 170},
        {"value": "đắt thứ nhì theo giá/phút", "path": KBW, "line": 157}],
        "note": "Theo giá menu, Se khít làm hồng yoni có giá/phút cao hơn (2.500.000/45 ≈ 55.556đ)."}],
    _more_sources=[{"path": KBP, "line": 45}, {"path": D12, "line": 619}, {"path": D13, "line": 219}])

add(id="tieu-u-thong-kinh-nguc", group="women", name_vi="Tiêu u – Thông kinh ngực",
    short_description_vi="Liệu trình 60 phút chăm sóc vùng đầu, cổ, nách, ngực và tay bằng massage, chải dụng cụ, đắp na, cứu ngải.",
    _raw=R3, _raw_lines=[158, 167, 168, 171, 173, 177, 179],
    variants=[v(60, 650000, None, FIXED_NOTE, 167)],
    process_steps_vi=["Khai thông tắt nghẽn vùng đầu, masage mặt", "Massage cổ, day ấn các ổ bạch huyết ở nách giúp thải dịch dơ",
                      "Massage bầu ngực, giải các tắt nghẽn có nguy cơ gây tức, lối ngực và ung thư vú", "Chải dụng cụ vào các khe rãnh sườn",
                      "Đắp na chăm sóc vùng da ngực sậm màu (không dành cho khách nhiễm hàn)", "Cứu ngải các huyệt đạo chính vùng trung tâm lồng ngực",
                      "Massage tay thư giãn"],
    ingredients_or_devices=["na (đắp; thành phần không ghi)", "ngải cứu", "dụng cụ chải (loại không ghi)"],
    flagged_claims=[{"text": "Tên dịch vụ: Tiêu u", "reason": "Tên hàm ý làm tiêu khối u.", "path": R3, "line": 161},
                    {"text": "Giảm u hạch, tuyến giáp ở cổ, ngực", "reason": "Claim điều trị khối u và bệnh tuyến giáp.", "path": R3, "line": 171},
                    {"text": "Điều khí lưu thông máu từ tim đến cơ thể. Chăm sóc phổi", "reason": "Claim tác động tim, phổi.", "path": R3, "line": 171},
                    {"text": "tắt nghẽn có nguy cơ gây ... ung thư vú", "reason": "Gắn dịch vụ với phòng ngừa ung thư vú.", "path": R3, "line": 177},
                    {"text": "Hỗ trợ giảm u hạch, tuyến giáp ở cổ ngực", "reason": "Chính mẫu 'đã sửa' trong tài liệu 13 lặp lại claim y khoa.", "path": D13, "line": 455}],
    who_should_avoid_or_consult=[
        {"text": "Bước đắp na không dành cho khách nhiễm hàn", "source_type": "menu", "path": R3, "line": 179},
        {"text": "Có hạch hoặc khối u: khám bác sĩ chuyên khoa trước", "source_type": "derived_doc_unapproved", "path": D11, "line": 1264},
        {"text": "Đang/đã điều trị ung thư: hỏi bác sĩ", "source_type": "derived_doc_unapproved", "path": D11, "line": 1265}],
    conflicts=[{"field": "address_on_slide", "values": [{"value": "phường Tân Kiểng quận 7", "path": R3, "line": 164}],
                "note": "Slide của dịch vụ này ghi Tân Kiểng; các slide khác ghi Tân Hưng."}],
    _more_sources=[{"path": KBP, "line": 47}, {"path": D12, "line": 621}, {"path": D13, "line": 220}])

# ---------------- skin ----------------
add(id="goi-mun-chuyen-sau", group="skin", name_vi="Gói Mụn Chuyên Sâu",
    short_description_vi="Gói chăm sóc da mụn 75 phút: làm sạch bã nhờn, lấy mụn, mặt nạ và điện di gel dịu da, xịt tế bào gốc.",
    _raw=R4, _raw_lines=[35, 40, 41, 44, 46],
    variants=[v(75, 389000, None, FIXED_NOTE, 41)],
    process_steps_vi=["Detox bã nhờn", "Lấy mụn", "Mặt nạ dịu da", "Điện di gel dịu da", "Xịt tế bào gốc"],
    ingredients_or_devices=["máy điện di (gel)", "xịt 'tế bào gốc' (sản phẩm không ghi tên)"],
    flagged_claims=[{"text": "Xịt tế bào gốc", "reason": "Thuật ngữ sản phẩm không rõ bản chất; không được giải thích là tế bào gốc người.", "path": R4, "line": 52}],
    who_should_avoid_or_consult=[{"text": "Da đang viêm nhiễm cấp; người dùng isotretinoin: hỏi trước", "source_type": "derived_doc_unapproved", "path": D11, "line": 1297}],
    _more_sources=[{"path": KBP, "line": 64}, {"path": D12, "line": 630}, {"path": D13, "line": 253}])

add(id="goi-mun-5-in-1", group="skin", name_vi="Gói Mụn 5 in 1", is_signature=True,
    short_description_vi="Gói Signature chăm sóc da mụn 90 phút: làm sạch, làm mềm còi mụn, lấy nhân mụn, mặt nạ, thoa hoạt chất, ánh sáng xanh SHR khi có khuyến mại.",
    _raw=R4, _raw_lines=[58, 65, 68, 70, 71, 73, 80],
    variants=[v(90, 599000, None, FIXED_NOTE, 71)],
    process_steps_vi=["Làm sạch sừng chết và bã nhờn với whitetox", "Massage kem mỡ làm mềm còi mụn", "Lấy sạch nhân mụn", "Đắp mặt nạ chuyên dụng kháng viêm",
                      "Thoa hoạt chất giảm viêm đỏ se còi mụn", "Bắn ánh sáng xanh SHR phục hồi da nhanh chóng (theo thời gian khuyến mại)"],
    ingredients_or_devices=["whitetox (bản chất chưa xác nhận)", "kem mỡ", "mặt nạ kháng viêm (loại không ghi)", "máy ánh sáng xanh 'SHR' (loại máy chưa xác nhận)"],
    flagged_claims=[{"text": "Khô còi mụn nhanh chóng", "reason": "Claim tốc độ hiệu quả.", "path": R4, "line": 68},
                    {"text": "SHR phục hồi da nhanh chóng (theo thời gian khuyến mại)", "reason": "Không rõ máy; bước chỉ có khi khuyến mại nhưng điều kiện chưa xác nhận.", "path": R4, "line": 80},
                    {"text": "SHR là ánh sáng LED non-thermal, an toàn cho phần lớn loại da", "reason": "Tài liệu tổng hợp khẳng định thông số máy không có trên menu.", "path": D11, "line": 1367}],
    who_should_avoid_or_consult=[{"text": "Đang dùng isotretinoin hoặc thuốc nhạy cảm ánh sáng: báo trước", "source_type": "derived_doc_unapproved", "path": D11, "line": 1297},
                                 {"text": "Mang thai: hỏi KTV về bước SHR", "source_type": "derived_doc_unapproved", "path": D11, "line": 1233}],
    conflicts=[{"field": "ingredients_or_devices.SHR", "values": [
        {"value": "Smart Hair Removal / Selective High-frequency Radiation", "path": R4, "line": 166},
        {"value": "Suppressed Hair Removal hoặc LED blue light", "path": D09, "line": 264},
        {"value": "Selective Hair Removal hoặc Super Hair Removal (IPL)", "path": D11, "line": 916},
        {"value": "ánh sáng LED non-thermal", "path": D11, "line": 1367}],
        "note": "Ba tài liệu đưa ra nhiều cách diễn giải khác nhau, không cách nào có nguồn; menu chỉ ghi 'ánh sáng xanh SHR'."},
       {"field": "ingredients_or_devices.whitetox", "values": [
        {"value": "Có thể là hỗn hợp AHA, BHA, PHA, vitamin C, niacinamide (đoán)", "path": D11, "line": 1052},
        {"value": "sản phẩm/hoạt chất cụ thể, chatbot không tự bịa định nghĩa", "path": R4, "line": 85}],
        "note": "Thành phần chưa được xác nhận; tài liệu 11 tự đoán."}],
    _more_sources=[{"path": KBP, "line": 65}, {"path": D12, "line": 631}, {"path": D13, "line": 254}])

add(id="cham-soc-da-kich-ung", group="skin", name_vi="Chăm sóc da kích ứng",
    short_description_vi="Gói 90 phút cho da kích ứng: massage, ủ tinh chất dịu da, mặt nạ vi sinh, điện di búa lạnh.",
    _raw=R4, _raw_lines=[89, 95, 96, 98],
    variants=[v(90, 599000, None, FIXED_NOTE, 96)],
    process_steps_vi=["Massage tinh thể nước", "Ủ tinh chất dịu da", "Massage với thanh xịt tế bào gốc", "Đắp nạ vi sinh", "Điện di búa lạnh"],
    ingredients_or_devices=["'tinh thể nước' (bản chất chưa xác nhận)", "tinh chất dịu da (loại không ghi)", "xịt 'tế bào gốc'", "mặt nạ vi sinh", "máy điện di búa lạnh"],
    conflicts=[{"field": "process_steps_vi", "values": [{"value": "Đắp nạ vi sinh", "path": R4, "line": 103}],
                "note": "'nạ' có thể là 'mặt nạ' hoặc 'na'; giữ nguyên văn."}],
    _more_sources=[{"path": KBP, "line": 66}, {"path": D12, "line": 632}, {"path": D13, "line": 255}])

add(id="xoa-tham-quang-mat-co-ban", group="skin", name_vi="Xóa thâm quầng mắt – Gói cơ bản",
    short_description_vi="Gói 60 phút massage và ấn huyệt vùng mắt.",
    _raw=R4, _raw_lines=[114, 122, 127, 128, 131],
    variants=[v(60, 329000, None, FIXED_NOTE, 128)],
    process_steps_vi=["Massage ấn huyệt dẫn lưu (menu chỉ có câu mô tả, không chia bước)"],
    flagged_claims=[{"text": "giảm ngay tình trạng thâm đen, ứ tụ bọng mắt", "reason": "Claim hiệu quả tức thì.", "path": R4, "line": 131}],
    _more_sources=[{"path": KBP, "line": 63}, {"path": D12, "line": 629}, {"path": D13, "line": 252}])

add(id="xoa-tham-quang-mat-dien-xung-truong", group="skin", name_vi="Xóa thâm quầng mắt – Gói công nghệ điện xung trường",
    short_description_vi="Gói 90 phút massage ấn huyệt vùng mắt kết hợp máy plasma và điện xung trường để đưa tinh chất vào da.",
    _raw=R4, _raw_lines=[133, 138, 139, 142],
    variants=[v(90, 629000, None, FIXED_NOTE, 139)],
    process_steps_vi=["Massage ấn huyệt mắt kết hợp với plasma đưa tinh chất xuống da bằng công nghệ điện xung trường (menu chỉ có câu mô tả)"],
    ingredients_or_devices=["máy plasma (loại chưa xác nhận)", "máy điện xung trường (loại chưa xác nhận)", "tinh chất (loại không ghi)"],
    flagged_claims=[{"text": "hiệu quả gấp 20 lần điện di ion bình thường", "reason": "Con số hiệu quả không có nguồn; tài liệu 09/11 yêu cầu chatbot dẫn lại nguyên văn.", "path": R4, "line": 142},
                    {"text": "plasma lạnh, an toàn cho da, kích thích collagen, khử khuẩn", "reason": "Tài liệu tổng hợp khẳng định loại máy và tác dụng không có trên menu.", "path": D12, "line": 334}],
    who_should_avoid_or_consult=[{"text": "Mang thai, có kim loại cấy ghép, dùng thuốc nhạy cảm ánh sáng: thận trọng", "source_type": "derived_doc_unapproved", "path": D12, "line": 345}],
    _more_sources=[{"path": KBP, "line": 67}, {"path": D12, "line": 633}, {"path": D13, "line": 256}])

# ---------------- hair ----------------
add(id="detox-da-dau", group="hair", name_vi="Detox da đầu",
    short_description_vi="Gói gội và làm sạch da đầu 40 phút với muối dược liệu, hà thủ ô, bồ kết; kèm ấn huyệt mặt và massage tay.",
    _raw=R5, _raw_lines=[31, 41, 42, 44, 69, 75, 76],
    variants=[v(40, 139000, DAY, None, 41), v(40, 159000, NIGHT, NIGHT_NOTE, 42)],
    process_steps_vi=["Chải đầu bằng dụng cụ", "Ấn huyệt mặt", "Detox da đầu với muối dược liệu, massage đầu", "Gội sạch với hà thủ ô, bồ kết 2 lần",
                      "Massage 2 tay", "Xã phục hồi", "Sấy tóc, xịt bưởi"],
    ingredients_or_devices=["muối dược liệu", "hà thủ ô", "bồ kết", "xịt bưởi"],
    flagged_claims=[{"text": "gội đầu rất muộn... sẽ rất dễ bệnh đấy", "reason": "Câu dọa bệnh không có căn cứ.", "path": R5, "line": 54}],
    who_should_avoid_or_consult=[{"text": "Dị ứng bưởi, bồ kết, hà thủ ô: hỏi trước", "source_type": "derived_doc_unapproved", "path": D11, "line": 1281}],
    conflicts=[{"field": "process_steps_vi", "values": [{"value": "Xã phục hồi", "path": R5, "line": 78}, {"value": "Xả phục hồi", "path": D12, "line": 483}],
                "note": "Menu ghi 'Xã'; chờ xác nhận chính tả."}],
    _more_sources=[{"path": KBP, "line": 82}, {"path": KBP, "line": 83}, {"path": D12, "line": 639}, {"path": D13, "line": 264}])

add(id="goi-dau-thu-gian", group="hair", name_vi="Gội đầu thư giãn",
    short_description_vi="Gói gội đầu 50 phút với hà thủ ô, bồ kết; kèm ủ dược liệu vùng tóc thưa, ấn huyệt mặt, giãn cơ vai cổ.",
    _raw=R5, _raw_lines=[83, 93, 94, 96, 118, 123, 126],
    variants=[v(50, 199000, DAY, None, 93), v(50, 229000, NIGHT, NIGHT_NOTE, 94)],
    process_steps_vi=["Chải đầu bằng dụng cụ", "Ủ dược liệu khu vực tóc thưa mỏng", "Ấn huyệt mặt", "Giãn cơ vai cổ thư giãn",
                      "Gội sạch với hà thủ ô, bồ kết 2 lần", "Xã phục hồi", "Massage 2 tay", "Sấy tóc, xịt bưởi"],
    ingredients_or_devices=["dược liệu ủ tóc (loại không ghi)", "hà thủ ô", "bồ kết", "xịt bưởi"],
    flagged_claims=[{"text": "dễ nhiễm lạnh lại hay sinh bệnh", "reason": "Câu dọa bệnh không có căn cứ.", "path": R5, "line": 104}],
    _more_sources=[{"path": KBP, "line": 84}, {"path": KBP, "line": 85}, {"path": D12, "line": 640}, {"path": D13, "line": 265}])

add(id="cham-soc-nan-toc", group="hair", name_vi="Chăm sóc nan tóc",
    short_description_vi="Gói chăm sóc tóc và da đầu 70 phút: ủ dược liệu, muối thảo dược, gội thảo dược, hà thủ ô, bồ kết, massage mặt, vai cổ, tay.",
    _raw=R5, _raw_lines=[135, 141, 142, 152, 157, 160],
    variants=[v(70, 349000, None, "Menu ghi một giá, không chia khung giờ.", 141)],
    process_steps_vi=["Chải đầu bằng dụng cụ", "Ủ dược liệu kích mọc tóc", "Massage mặt, ấn huyệt mặt", "Massage vai cổ", "Sử dụng muối thảo dược giảm rụng",
                      "Gội nước thảo dược khu vực cần chăm sóc", "Gội sạch với hà thủ ô, bồ kết", "Massage tay thư giãn", "Xã phục hồi", "Sấy tóc - Xịt bưởi"],
    ingredients_or_devices=["dược liệu ủ (loại không ghi)", "muối thảo dược", "nước thảo dược", "hà thủ ô", "bồ kết", "xịt bưởi"],
    flagged_claims=[{"text": "Ủ dược liệu kích mọc tóc / muối thảo dược giảm rụng", "reason": "Claim mọc tóc, giảm rụng không có căn cứ.", "path": R5, "line": 157},
                    {"text": "Phù hợp: rụng tóc nhiều, mẹ sau sinh", "reason": "Tài liệu 12/13 thêm đối tượng sau sinh không có trên menu.", "path": D12, "line": 124}],
    conflicts=[{"field": "name_vi", "values": [{"value": "Chăm sóc nan tóc", "path": R5, "line": 139}, {"value": "nang tóc (đề xuất sửa)", "path": R5, "line": 147}],
                "note": "Chờ xác nhận chính tả."},
               {"field": "menu_membership", "values": [{"value": "Liệt kê trong '5 dịch vụ' menu phụ nữ", "path": D12, "line": 170}],
                "note": "Mẫu Q4 của tài liệu 12 xếp dịch vụ tóc này vào menu phụ nữ và bỏ Tiêu u; trái với ánh xạ menu ở 13:210-220."}],
    _more_sources=[{"path": KBP, "line": 86}, {"path": D12, "line": 641}, {"path": D13, "line": 266}])

# ---------------- verify ----------------
def vnd_variants(p):
    a = f"{p:,}"
    return {a, a.replace(",", ".")}

errors = []
cache = {}
for s in S:
    for var in s["variants"]:
        path, line = var["source"]["path"], var["source"]["line"]
        lines = cache.setdefault(path, (root / path).read_text(encoding="utf-8").splitlines())
        text = lines[line - 1]
        if not any(x in text for x in vnd_variants(var["price_vnd"])):
            errors.append(f"{s['id']}: price {var['price_vnd']} not on {path}:{line} -> {text!r}")
        # duration may be on the same row (relaxation tables) or nearby lines (other menus)
        window = " ".join(lines[max(0, line - 6): line + 5])
        if not re.search(rf"\b{var['duration_min']}\s*phút", window):
            errors.append(f"{s['id']}: duration {var['duration_min']} not near {path}:{line}")
    for src in s["sources"] + [f for f in s["flagged_claims"]] + s["who_should_avoid_or_consult"]:
        p = root / src["path"]
        n = len(cache.setdefault(src["path"], p.read_text(encoding="utf-8").splitlines()))
        if not (1 <= src["line"] <= n):
            errors.append(f"{s['id']}: bad line ref {src}")

out = {
    "schema_note": "Dữ liệu nháp, chưa được chủ doanh nghiệp duyệt. Giá lấy từ raw-content (văn bản chép từ ảnh menu, ngày 2026-05-16). Mỗi variant có source path:line. flagged_claims là câu cần duyệt trước khi chatbot dùng.",
    "generated_by": "scripts/build_services.py",
    "generated_on": "2026-11-07",
    "counts": {"services": len(S), "variants": sum(len(s["variants"]) for s in S),
               "by_group": {g: sum(1 for s in S if s["group"] == g) for g in ("relaxation", "health", "women", "skin", "hair")}},
    "services": S,
}
(root / "data").mkdir(exist_ok=True)
(root / "data" / "services.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out["counts"], ensure_ascii=False))
if errors:
    print("\n".join(errors)); sys.exit(1)
print("all variants traced to cited lines")

"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from collections import defaultdict
from math import ulp

from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    check = "label_format"
    settings = cfg[check]
    class_count = len(ds.classes)
    # Tính bốn mép bằng số thực có thể làm lệch kết quả tại đúng ngưỡng.
    overflow_limit = settings["overflow_tol"] + ulp(1.0)
    issues = []

    for label_file in ds.label_files():
        stem = label_file.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        image_size = ds.image_size(stem)
        boxes_by_class = defaultdict(list)
        for line_no, text in lines:
            try:
                class_id, cx, cy, width, height = parse_yolo_line(text)
            except (ValueError, OverflowError) as exc:
                issues.append(Issue(check, ERROR, "BAD_FORMAT", stem, str(exc), line=line_no))
                continue

            if not 0 <= class_id < class_count:
                message = f"ID lớp {class_id} nằm ngoài khoảng 0–{class_count - 1}"
                issues.append(Issue(check, ERROR, "BAD_CLASS_ID", stem, message, line=line_no))
                continue

            if width <= 0 or height <= 0:
                message = "chiều rộng hoặc chiều cao của box không dương"
                issues.append(Issue(check, ERROR, "BOX_ZERO", stem, message, line=line_no))
                continue

            left, right = cx - width / 2, cx + width / 2
            top, bottom = cy - height / 2, cy + height / 2
            overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if overflow > overflow_limit:
                issues.append(Issue(
                    check, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4g}",
                    line=line_no, extra={"overflow": overflow},
                ))

            box = (cx, cy, width, height)
            previous_boxes = boxes_by_class[class_id]
            if any(iou_xywh(box, previous) > settings["dup_box_iou"] for previous in previous_boxes):
                message = "box trùng với một box cùng lớp ở dòng trước"
                issues.append(Issue(check, ERROR, "DUP_BOX", stem, message, line=line_no))
            previous_boxes.append(box)

            if image_size is not None:
                image_width, image_height = image_size
                shortest_side = min(width * image_width, height * image_height)
                if shortest_side < settings["min_box_px"]:
                    message = f"cạnh ngắn của box chỉ có {shortest_side:.1f} px"
                    issues.append(Issue(check, WARN, "BOX_TINY", stem, message, line=line_no))

            area = width * height
            if area > settings["max_box_frac"]:
                message = f"box chiếm {area:.1%} diện tích ảnh"
                issues.append(Issue(check, WARN, "BOX_HUGE", stem, message, line=line_no))

    return issues

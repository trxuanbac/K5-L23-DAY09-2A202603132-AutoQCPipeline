"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from ..common import ERROR, ROOT, parse_yolo_line


DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_IMAGE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _change(image, action, before, after, line=None):
    return dict(image=image, line=line, action=action, before=before, after=after)


def _write_text(path, text):
    # Ghi xong file tạm rồi thay file đích trong cùng thư mục.
    temp_file = NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False)
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            temp_file.write(text)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _clip_line(text):
    try:
        class_id, cx, cy, width, height = parse_yolo_line(text)
    except (ValueError, OverflowError):
        return ""

    left, right = cx - width / 2, cx + width / 2
    top, bottom = cy - height / 2, cy + height / 2
    clipped_left, clipped_right = max(0.0, left), min(1.0, right)
    clipped_top, clipped_bottom = max(0.0, top), min(1.0, bottom)
    clipped_width = clipped_right - clipped_left
    clipped_height = clipped_bottom - clipped_top
    if clipped_width <= 0 or clipped_height <= 0:
        return ""
    if (left, top, right, bottom) == (clipped_left, clipped_top, clipped_right, clipped_bottom):
        return text

    clipped_cx = clipped_left + clipped_width / 2
    clipped_cy = clipped_top + clipped_height / 2
    return f"{class_id} {clipped_cx:.12g} {clipped_cy:.12g} {clipped_width:.12g} {clipped_height:.12g}"


def _fix_label_file(path, actions):
    with path.open(encoding="utf-8", errors="replace", newline="") as label_file:
        original_lines = label_file.read().splitlines(keepends=True)

    fixed_lines = []
    changes = []
    for line_no, original in enumerate(original_lines, 1):
        action = actions.get(line_no)
        if action is None:
            fixed_lines.append(original)
            continue

        before = original.splitlines()[0]
        if action == "drop_line":
            after = ""
        else:
            after = _clip_line(before)
            if after == before:
                fixed_lines.append(original)
                continue
            if not after:
                action = "drop_line"

        if after:
            fixed_lines.append(after + original[len(before):])
        changes.append(_change(path.stem, action, before, after, line=line_no))

    if changes:
        _write_text(path, "".join(fixed_lines))
    return changes


def _rename_classes(path, classes):
    settings = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    settings = settings or {}
    before = settings.get("names")
    after = list(classes) if isinstance(before, list) else dict(enumerate(classes))
    if before == after:
        return []

    settings["names"] = after
    _write_text(path, yaml.safe_dump(settings, allow_unicode=True, sort_keys=False))
    return [_change(path.name, "rename_classes", str(before), str(after))]


def fix(ds, issues, cfg):
    if ds.root.resolve().is_relative_to((ROOT / "data").resolve()):
        raise ValueError("autofix cần thư mục làm việc chứa bản sao của dữ liệu")

    removals = set()
    missing_labels = set()
    line_actions = defaultdict(dict)
    rename_classes = False
    for issue in issues:
        if issue.severity != ERROR:
            continue
        code, stem, line_no = issue.code, issue.image, issue.line
        if code in REMOVE_IMAGE_CODES or code.startswith("DUP_IMAGE_"):
            removals.add(stem)
        elif code == "MISSING_LABEL_FILE":
            missing_labels.add(stem)
        elif code == "BAD_CLASS_NAME":
            rename_classes = True
        elif line_no is not None:
            if code in DROP_LINE_CODES:
                line_actions[stem][line_no] = "drop_line"
            elif code == "BOX_OUT_OF_IMAGE":
                line_actions[stem].setdefault(line_no, "clip_box")

    image_paths = defaultdict(list)
    for path in ds.image_files():
        image_paths[path.stem].append(path)
    label_paths = {path.stem: path for path in ds.label_files()}

    changes = []
    for stem in sorted(removals):
        paths = image_paths.pop(stem, [])
        label_path = label_paths.pop(stem, None)
        if label_path is not None:
            paths.append(label_path)
        if paths:
            for path in paths:
                path.unlink(missing_ok=True)
            changes.append(_change(stem, "remove_image", ", ".join(path.name for path in paths), ""))

    for stem in sorted(line_actions.keys() & label_paths.keys()):
        changes.extend(_fix_label_file(label_paths[stem], line_actions[stem]))

    if rename_classes:
        changes.extend(_rename_classes(ds.yaml_path, cfg["classes"]))

    for stem in sorted((missing_labels & image_paths.keys()) - label_paths.keys()):
        changes.append(_change(stem, "needs_label", "(không có file)", "chuyển người gán"))

    return changes

# Báo cáo Day 09 — Trần Xuân Bắc, 2A202603132

## 1. Kết luận trước

**Hold.** Pipeline nhận 224 ảnh, loại 19 ở cửa vào và xuất bản nháp `clean_v1` với 205 ảnh. Sau khi mô phỏng duyệt 80 ảnh, số lỗi bắt buộc về 0. Còn **64/205 ảnh** có cảnh báo chưa duyệt (31,22%), vượt ngưỡng Hold 10%. [Tóm tắt lần chạy](reports/08_summary.json) · [Manifest bản nháp](export/clean_v1/manifest.json)

## 2. Lỗi và phân việc

V1 ghi 55 lỗi bắt buộc và 400 cảnh báo. Cửa vào quét 224 ảnh. Các kiểm tra nhãn chạy trên 205 ảnh được giữ, mỗi ảnh có thể phát sinh nhiều dòng cờ. [Danh sách v1](reports/02_error_list_v1.csv)

| Mã và số cờ | Ảnh hoặc phạm vi liên quan | Ai xử lý và vì sao |
|---|---|---|
| `BAD_SIZE` 3, `CORRUPT_IMAGE` 2 | 3/224, 2/224 | Máy loại ảnh nhỏ hoặc hỏng. |
| `DUP_IMAGE_EXACT` 8, `DUP_IMAGE_NEAR` 2, `LEAK_TEST` 4 | 8/224, 2/224, 4/224 | Máy loại ảnh trùng và ảnh trùng với tập tham chiếu. |
| `BAD_FORMAT` 3, `BAD_CLASS_ID` 6, `BOX_ZERO` 4, `DUP_BOX` 7 | 3/205, 6/205, 4/205, 7/205 | Máy xoá dòng sai định dạng, sai ID, box rỗng hoặc box trùng. |
| `BOX_OUT_OF_IMAGE` 8 | 8/205 | Máy cắt box theo biên ảnh. |
| `BAD_CLASS_NAME` 2 | 1/1 file cấu hình | Máy chuẩn hóa thứ tự và tên lớp. |
| `MISSING_LABEL_FILE` 6 | 6/205 | Người gán nhãn cho ảnh thiếu file. |
| `BOX_TINY` 6, `BOX_HUGE` 3, `EMPTY_LABEL` 12 | 4/205, 3/205, 12/205 | Người kiểm tra kích thước box và phân biệt ảnh nền với ảnh thiếu nhãn. |
| `CLASS_RARE` 4 | 1/1 lô, 4 ID lạ | Máy thống kê. Bốn cờ biến mất sau khi xoá các dòng có ID sai. |
| `POSSIBLE_MISSING` 267, `POSSIBLE_WRONG_CLASS` 23 | 97/205, 22/205 | Người xác nhận thiếu vật hoặc nhầm lớp. |
| `POSSIBLE_LOOSE_BOX` 60, `POSSIBLE_FALSE_POS` 25 | 46/205, 24/205 | Người xác nhận box lỏng hoặc thừa. |

Máy xoá 20 dòng, cắt 8 box, cập nhật tên lớp một lần và chuyển 6 ảnh thiếu file cho người gán. Hàng đợi cộng trọng số theo mã cờ và độ tin cậy. `img_0160` đứng đầu với 109.727 điểm do tích lũy cờ nghi thiếu nhãn và sai lớp. Trong 80/149 ảnh đã duyệt, 74 ảnh có cờ ngữ nghĩa, bao phủ **301/374 cờ ngữ nghĩa** ở v2. Sáu ảnh thiếu file đều đã được xử lý. [Log sửa](reports/03_fixes.csv) · [Hàng đợi](reports/05_review_queue.csv) · [Log duyệt](reports/06_review_log.csv)


## 3. Calibration (2 ngưỡng)

Precision và recall được đo trên 39 ảnh `calib`, theo [báo cáo sweep](calibration/calibration_report.md).

| Tham số | Khởi đầu → đã chọn | Mã lỗi | Precision / recall trước → sau |
|---|---|---|---|
| `duplicates.phash_dist` | `2` → `4` | `DUP_IMAGE_EXACT` | 1.00 / 1.00 → 1.00 / 1.00 |
| `duplicates.phash_dist` | `2` → `4` | `DUP_IMAGE_NEAR` | 1.00 / 0.50 → 1.00 / 0.67 |
| `second_opinion.conf` | `0.25` → `0.10` | `POSSIBLE_WRONG_CLASS` | 0.56 / 0.83 → 0.56 / 0.83 |
| `second_opinion.conf` | `0.25` → `0.10` | `POSSIBLE_MISSING` | 0.50 / 1.00 → 0.40 / 1.00 |
| `second_opinion.conf` | `0.25` → `0.10` | `POSSIBLE_LOOSE_BOX` | 0.29 / 0.40 → 0.38 / 0.60 |
| `second_opinion.conf` | `0.25` → `0.10` | `POSSIBLE_FALSE_POS` | 0.36 / 1.00 → 0.36 / 1.00 |

Trong các ngưỡng pHash đã thử, `4` là mức thấp nhất bắt được 4/6 cặp gần trùng, tăng từ 3/6 ở ngưỡng `2`. Cả bốn cờ khớp manifest. Ngưỡng `16` bắt được 5/6 nhưng cho phép khoảng cách Hamming lớn hơn. Vì ảnh bị loại tự động và `calib` chỉ có sáu ca gần trùng, chọn `4` để hạn chế rủi ro loại nhầm.

Hạ `conf` xuống `0.10` giúp bắt 3/5 ca box lỏng, tăng từ 2/5. Cả hai ngưỡng đều bắt đủ 8/8 ca thiếu nhãn, nhưng số cảnh báo thiếu nhãn ngoài manifest tăng từ 8 lên 12. Trên `raw`, hàng đợi tăng từ 145 lên 149 ảnh với ngân sách duyệt 80 ảnh. Cảnh báo nhãn nghi thừa dùng ngưỡng `fp_conf` riêng nên có cùng kết quả ở hai mức `conf`.

Mức tăng recall gần trùng trên `calib` tương ứng với một ca. Trên `raw`, cửa vào giữ 205/224 ảnh ở cả hai cấu hình. Hai cặp bị cờ gần trùng là `img_0042`–`img_0076` và `img_0037`–`img_0143`, đều có khoảng cách pHash bằng 0. Khi đưa mỗi ảnh về 160 × 160 pixel, sai khác RGB trung bình của hai cặp lần lượt là 1.52/255 và 2.21/255. Kết quả này kiểm chứng các cặp sát nhau nhất, còn độ tin cậy với ảnh `raw` có khoảng cách sát ngưỡng `4` vẫn chưa rõ.

## 4. Kiểm chứng cửa chặn và điểm mù

```bash
python -m pipeline.run --budget 0 --work work/gate_budget0/run \
  --reports work/gate_budget0/reports --export-dir work/gate_budget0/export
```

Ca này trả mã thoát `20` và kết luận **Rework** vì còn 6/205 ảnh thiếu file nhãn. Tóm tắt lần chạy ghi `exported = null`, xác nhận gate chặn bước xuất `clean_v1`.

Ba mẫu đối chiếu trên nhãn gốc gồm `img_0020` dòng 3 có ID lớp `93`, `img_0030` dòng 9 tràn 2,30% chiều rộng ảnh ở mép trái và `img_0050` dòng 1 có chiều rộng box bằng 0. [Danh sách v1](reports/02_error_list_v1.csv)

- **Nhầm lớp khi nhiều box chồng lên nhau.** `calib_009` có box `truck` bị đổi thành `bus`. Dự đoán `car` khớp box này với IoU 0.964, đồng thời khớp nhãn `car` khác với IoU 0.950. Quy tắc ưu tiên ứng viên cùng lớp nên bỏ sót ca nhầm này, đạt 5/6 ca sai lớp.
- **Box lỏng khi model bỏ qua vật.** Danh sách dự đoán của `calib_006` rỗng nên checker thiếu ứng viên để so IoU với box đã bị nới 1,48 lần. Recall của cảnh báo box lỏng là 3/5. [Bảng calibration](calibration/calibration_report.md)

## 5. Train raw vs clean

Chưa chạy. Lần nộp này tập trung kiểm chứng pipeline và hoàn thành phần lõi.

## 6. Quyết định và ghi chú AI

Giữ quyết định **Hold**. Với lô 205 ảnh và 0 lỗi bắt buộc, cần xử lý cảnh báo trên ít nhất 44 trong 64 ảnh còn lại để còn tối đa 20/205 ảnh (9,76%), dưới ngưỡng 10%. Sau lượt duyệt bổ sung cần chạy lại QC để xác nhận cả hai điều kiện. [Tóm tắt lần chạy](reports/08_summary.json)

- Prompt chính gồm traceback `NotImplementedError` và yêu cầu triển khai lần lượt các module theo `GUIDE.md`. Đặc tả dùng nhãn YOLO và cache dự đoán làm đầu vào, áp dụng các quy tắc trong docstring, trả lỗi có số dòng hoặc log sửa và thao tác trên bản sao dữ liệu.
- Kiểm chứng bằng 79 test, đối chiếu các lỗi chèn trên `calib` và kiểm tra kết quả ở hai ngân sách duyệt 0 và 80.
- AI từng gọi `clean_v1` là “bản xuất chính thức” khi gate kết luận Hold. Đối chiếu manifest và sửa mô tả thành bản nháp Hold.

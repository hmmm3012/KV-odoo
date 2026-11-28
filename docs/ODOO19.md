# Quy ước Odoo 19 — Kiến Việt

Áp dụng cho mọi thay đổi trong `custom/` trên nhánh `19.0-upgrade`. Chi tiết an toàn môi trường nằm ở `docs/SAFETY.md`.

## Model và field đã đổi so với Odoo 18

- **Hợp đồng:** `hr.contract` và `hr.contract.history` đã gộp vào `hr.version` (module `hr`). Mọi tính năng số HĐ / PDF / domain phòng ban phải inherit `hr.version`, không tạo lại model `hr.contract`.
- **Giới tính nhân viên:** field `hr.employee.gender` đổi thành `sex` (lưu trên `hr.version`). Không ghi `employee.gender`.
  - Parser CCCD (`custom/hr_employee_kv/models/id_card_qr.py`, `custom/hr_employee_kv/models/id_card_ocr.py`) vẫn được trả khóa dict nội bộ `"gender"`. `_id_card_fields()` trong `custom/hr_employee_kv/models/models.py` phải map sang `"sex"` trước khi `write`/`create`.
  - Giấy giới thiệu đọc `employee.sex` rồi chuyển thành khóa template `"gender"` — đó là dữ liệu template, không phải field Odoo.
- **Ràng buộc SQL:** dùng `models.Constraint`, không khai báo `_sql_constraints`.
- **Controller JSON:** `type="jsonrpc"`. Không dùng `type="json"` (đã đổi từ Odoo 17/19). Các route `/attendance/api/*` và kiosk hiện đã đúng `jsonrpc`.

## View, menu, assets

- Inherit view bằng XPath rõ ràng, không copy cả form gốc.
- Mọi view kế thừa phải chạy `scripts/xpath_check.py` (Giai đoạn 2) trên đúng stack 73 module đang cài, gồm cả `hr_holidays`, `calendar`, `hr_skills`, `contacts`, `mail`, `web`. Không giả định còn `hr_timesheet` (xpath nút Timesheet đã gây lỗi khi gỡ module — đã vá trong `fcc68a87e0a`).
- Menu gốc Thảo luận và Lịch đang ẩn trong `custom/hr_employee_kv/views/hide_unused_menus.xml`.
- OWL/JS backend đăng ký trong manifest (ví dụ `custom/hr_employee_kv/__manifest__.py`) → `web.assets_backend`. Widget CCCD: `kv_id_card_autofill`.

## Dịch thuật

- File dịch hiện có: `custom/hr_attendance_portal/i18n/vi.po`, `custom/hr_employee_kv/i18n/vi.po`. Hai module kia chưa có thư mục i18n.
- Odoo 19 lưu bản dịch field trên cột `jsonb` (ví dụ `res_groups.name`), không còn bảng `ir_translation`.
- Chuỗi UI mới phải có bản tiếng Việt. Không commit dữ liệu nhân sự thật vào file dịch hay test.

## Test

- Unit test Odoo: `TransactionCase` / `HttpCase` trong thư mục `tests/` của module (ví dụ `custom/hr_employee_kv/tests/`).
- `kv_hr_contract` hiện chưa có test trong repo — xem `feature_list.json` mục `contract-001`.
- Không chạy `--test-enable -u` trên DB `odoo_19_test` (DB tay của anh Minh). Dùng DB tạm (Giai đoạn 2).

## Lệnh nhớ

```text
# Nền (không nâng cấp, không đụng production)
./init.sh

# Đầy đủ theo module, trên DB tạm: đóng gói ở Giai đoạn 2
```

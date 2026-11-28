# QUALITY.md — chấm 4 module custom (28/11/2026)

Thang 1–5. Đây là đánh giá tại ngày khảo sát, không phải điểm tự chấm của phiên viết code.

| Module | Model/domain | Views/JS | Quyền | Test | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| `hr_attendance_portal` | 4 | 4 | 4 | 2 | Nhiều test sẵn có nhưng verify runtime còn 5 fail + 23 error / 130 trên Odoo 19. Cần chiến dịch sửa riêng. |
| `hr_employee_kv` | 4 | 4 | 4 | 4 | 24 unit test xanh (2026-11-28), gồm menu/i18n và CCCD. OCR tiếng Việt vẫn có hạn chế đã biết (mất dấu, chưa HEIC). |
| `hr_department_access` | 3 | 4 | 3 | 3 | Static xanh. 1 error: tạo `hr.version` khi user bị giới hạn phòng ban (record rule lúc create employee). |
| `kv_hr_contract` | 4 | 4 | 4 | 4 | 7 unit test xanh cho số HĐ. `create_pdf` vẫn 500 khi thiếu date (`strftime` trên False). |

Lớp ngang:

- View inherit: xpath_check 18 view, 0 lỗi trên stack 73 module.
- i18n: `hr_attendance_portal` và `hr_employee_kv` có `vi.po`; hai module kia chưa có thư mục i18n.
- An toàn môi trường: harness không đụng production; DB tạm tách khỏi `odoo_19_test`.

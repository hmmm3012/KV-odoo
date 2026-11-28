# hr_attendance_portal

Cổng `/attendance` (mã NV + PIN), GPS/Wi-Fi, kiosk, workplaces, audit. Port Odoo 19.

- Nhóm `hr_attendance_portal.group_hr_attendance_site_captain` = Department Captain / **Đội trưởng bộ phận** (chỉ đọc trong phòng được ủy quyền).
- Route JSON phải `type="jsonrpc"`. Public route chỉ `sudo()` sau khi đã kiểm PIN/session, và chỉ cho đúng nhân viên đó.
- Đã gỡ `hr_timesheet`: không inherit nút/timesheet còn lại của module đó.
- Test: 9 file trong `custom/hr_attendance_portal/tests/` (ví dụ `custom/hr_attendance_portal/tests/test_attendance_api.py`). Lệnh verify đầy đủ sẽ có ở Giai đoạn 2.
- README.md trong module vẫn còn câu mở đầu "Odoo 18" — khi sửa docs, cập nhật cho khớp 19.

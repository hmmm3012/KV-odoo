# kv_hr_contract

Số hợp đồng `HD.YYYY.NNN` trên `hr.version`. PDF `/contracts/pdf/<int:contract_id>` (`auth="user"`).

- Không tạo lại model `hr.contract`. Inherit `hr.version`.
- Đổi lương / version cùng hợp đồng: giữ số cũ. Gia hạn (đổi `contract_date_start`): cấp số mới.
- Hiện **0 file test** trong module. Unit test là mục `contract-001` (Giai đoạn 3). Bản shell rollback ngoài repo không hard-code số thứ tự phụ thuộc DB tay.
- Font PDF lấy từ `utils/font` (compose mount `/opt/utils`).

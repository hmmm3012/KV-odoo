# hr_employee_kv

Mã nhân viên, CCCD, badge, giấy giới thiệu, ẩn menu thừa, override tiếng Việt.

- Nút **Tự nhập thông tin** (`kv_id_card_autofill`): upload ảnh không tự chạy QR/OCR. Bấm nút mới đọc (QR trước, OCR sau). Chạy được trên form chưa lưu.
- Parser được trả `"gender"` trong dict; `_id_card_fields()` map sang `sex` trước khi ghi nhân viên. Không ghi field `gender`.
- Ẩn menu Thảo luận/Lịch trong `views/hide_unused_menus.xml`. Không gỡ module `mail` hay `calendar`.
- Test: `tests/test_id_card_qr.py`, `test_id_card_ocr.py`, `test_badge.py`, `test_intro_letter_templates.py`.
- Không commit ảnh CCCD thật.

# Sprint contract — việc đụng giao diện / OWL

Dùng bản hợp đồng ngắn này *trước khi* sửa view, JS, menu, hoặc quyền hiện trên form. Không thay `feature_list.json`.

1. **Hành vi người dùng thấy:** một câu, đo được (ví dụ: "Nút Tự nhập thông tin nằm dưới hai ảnh CCCD và chỉ chạy khi bấm").
2. **Phạm vi file:** liệt kê module/view/JS sẽ đụng. Ngoài danh sách thì không sửa.
3. **Cổng kiểm chứng:** tối thiểu `./scripts/agent-verify.sh <module>`; nếu đụng HTML/JS công cộng thì thêm `./scripts/e2e-smoke.sh` và/hoặc test `get_views`.
4. **Không làm:** không đụng production, staging 18, `odoo_19_test`, không cài Playwright/browser trên server công ty trừ khi anh Minh yêu cầu rõ.
5. **Xong khi:** lệnh kiểm chứng đã chạy, evidence ghi vào `feature_list.json` / `PROGRESS.md`, evaluator chấm riêng theo `docs/evaluator-rubric.md`.

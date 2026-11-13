# Giao diện demo Controlled RAG — Nhóm 11

Frontend local tối giản để trình bày project Data-Centric Security for RAG. Giao diện sử dụng các module hiện có trong `app/`; không thay thế policy engine, authentication, vector search, LLM hay Output DLP.

## Chức năng

- Đăng nhập bằng `username + password + TOTP` qua `app.auth.authenticate()`.
- Tổng quan: database, Ollama, phạm vi tài liệu được phép theo PDP.
- Hỏi đáp: gọi `app.controlled_rag.answer_internal_query()` với `top_k=3`; context DLP được backend suy ra sau khi xác thực token. Entry point `answer_query()` vẫn dành cho benchmark và giữ `SHARE_SUMMARY`.
- Hiển thị tài liệu nguồn đã được phép và trace kiểm soát theo `request_id`.
- Danh mục tài liệu chỉ hiển thị những tài liệu PDP trả về `ALLOW` cho người đang đăng nhập.
- Audit log chỉ hiển thị sự kiện của người dùng hiện tại; không hiển thị `query_text`.
- Kết quả WP6/WP7/WP8/Benchmark được đọc từ các file JSON/CSV sẵn có trong `results/`.

## 1. Điều kiện

- Python 3.11+ và dependencies của project.
- PostgreSQL/pgvector đang chạy; database Demo riêng tên `baomatdulieu_demo` đã được provision.
- Ollama đang chạy và có hai model `qwen2.5:3b`, `nomic-embed-text`.
- Tài khoản demo đã tồn tại trong bảng `users`, có `password_hash` bcrypt hợp lệ và `mfa_secret`.
- Migration audit `database/init/05_audit.sql` đã được áp dụng vào database ứng dụng; module Controlled RAG cần các cột `request_id`, `stage`, `rule_id` và `release_context`.
- Corpus Demo được copy từ `baomatdulieu_benchmark` bằng `scripts/setup_demo_database.py`. Runtime Demo không chạy embedding generation và không ghi vào database benchmark.

## 2. Cài đặt / khởi động trên Windows PowerShell

Mở PowerShell tại thư mục gốc project:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\scripts\load_demo_env.ps1
python .\demo_server.py
```

Mở trình duyệt tại:

```text
http://127.0.0.1:8765
```

Giữ cửa sổ PowerShell đang chạy server trong suốt buổi demo. Nhấn `Ctrl+C` để dừng.

`load_demo_env.ps1` chỉ nạp các biến PostgreSQL và `SECRET_KEY` cần cho giao diện; không yêu cầu `SEED_DEMO_PASSWORD` và không in giá trị bí mật. Có thể chạy nhanh bằng `powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1`.

## 3. Tài khoản và MFA

Dùng tài khoản fixture được cấp trong database, ví dụ `nv_dev`, `mgr_tech`, `mgr_sales`, `partner_01` hoặc `ceo_boss`. Mật khẩu là mật khẩu demo đã dùng khi provision; mã TOTP được tạo trong ứng dụng Authenticator tương ứng.

Tài khoản Demo được lưu riêng trong `baomatdulieu_demo`. Sau khi tạo database, chạy `python .\\scripts\\seed_demo_users.py` để tạo 5 tài khoản và MFA riêng. Script hỏi mật khẩu an toàn (không echo) và chỉ xuất TOTP secrets/URI một lần. Nó từ chối thay đổi tài khoản đang tồn tại, trừ khi dùng `--rotate` có chủ đích. Không chạy `scripts/seed_users.py` để provision Demo.

## 4. Luồng demo gợi ý trước giảng viên

1. Đăng nhập bằng `nv_dev` và TOTP.
2. Mở **Tổng quan** để chỉ ra role, department, clearance và số tài liệu được phép.
3. Mở **Tài liệu được phép** để minh họa danh sách đã lọc qua PDP.
4. Hỏi: `Mã nguồn hệ thống RAG` hoặc `policy_engine.py` bằng `nv_dev` — tài liệu #6 thuộc Nội bộ/Kỹ thuật nên được phép truy cập và không bị che trong `INTERNAL_ASSISTANT`.
5. Hỏi: `Kế hoạch sáp nhập với công ty XYZ là gì?` bằng `nv_dev` — tài liệu Tối mật phải bị loại ở ABAC; không được đưa nội dung bị từ chối vào prompt.
6. Thử `policy_engine.py` bằng tài khoản `partner_01` — phiên đối tác dùng `SHARE_SUMMARY`, đồng thời quyền ABAC vẫn giới hạn tài liệu; không được xem nội dung tài liệu nội bộ.
7. Mở **Nhật ký kiểm soát** để xem context, quyết định `retrieval` và `output_dlp` của từng request.
8. Mở **Kết quả thực nghiệm** để xem các số liệu WP6, Answer Leakage, Prompt Injection, Ablation và Benchmark đã lưu.

## 5. Nguyên tắc an toàn và phạm vi

- Server chỉ bind vào `127.0.0.1`; không mở ra mạng LAN hoặc Internet.
- Không có chế độ bypass đăng nhập, không giả lập tài khoản, không cho browser tự chọn `release_context`.
- Release context được backend suy ra từ role của user đã xác thực: `INTERNAL_ASSISTANT` cho Nhân viên/Manager/Ban lãnh đạo; `SHARE_SUMMARY` cho Đối tác và mọi role không xác định (fail closed). Browser không được gửi hoặc tự chọn release context.
- Token được giữ trong `sessionStorage` của tab và hết hạn theo cơ chế token hiện có (1 giờ).
- Không ghi password, OTP, token hoặc raw answer vào console server.
- Giao diện chỉ đọc; không có chức năng upload/xóa/sửa tài liệu hoặc chạy script thực nghiệm từ trình duyệt.
- Đây là giao diện demo local cho môi trường lab, không phải chứng nhận bảo mật production.

## 6. Xử lý lỗi thường gặp

- **Không kết nối PostgreSQL:** kiểm tra Docker `docker compose ps`, `POSTGRES_PORT`, `POSTGRES_DB` và chạy lại `scripts/load_demo_env.ps1` trong cùng terminal.
- **Chưa có model Ollama:** chạy `ollama list`; nếu thiếu, pull model theo README project.
- **Sai username/password/TOTP:** kiểm tra tài khoản fixture, mật khẩu dùng khi seed và thời gian đồng bộ trên ứng dụng Authenticator.
- **Không có tài liệu nguồn:** kiểm tra bảng `documents`, `chunks`, embedding và quyền của người dùng; frontend không tự tạo dữ liệu.
- **Lỗi audit column/request_id:** với volume PostgreSQL cũ, init scripts không tự chạy lại. Kiểm tra và áp dụng `database/init/05_audit.sql` vào đúng database `baomatdulieu` nếu migration chưa được chạy.
- **Câu trả lời bị BLOCK:** xem Security Trace và Audit Log; đây có thể là quyết định fail-closed của pipeline, không nên sửa thành ALLOW chỉ để demo.

## 7. Chạy kiểm thử trên Windows PowerShell

Các test unit không cần PostgreSQL. Các test trong `tests/test_policy.py` cần database ứng dụng `baomatdulieu`; `tests/test_retrieval_postgres_integration.py` cần database benchmark `baomatdulieu_benchmark`.

Để chạy đầy đủ các test tích hợp, nạp cấu hình từ `.env` trong cùng cửa sổ PowerShell trước khi gọi pytest:

```powershell
.\scripts\load_demo_env.ps1
python -m py_compile .\app\controlled_rag.py .\demo_server.py
python -m pytest -q
```

Nếu chưa nạp `POSTGRES_USER` và `POSTGRES_PASSWORD`, các fixture database sẽ được đánh dấu `SKIPPED` thay vì báo lỗi setup. Nếu đã nạp credentials mà PostgreSQL không kết nối được hoặc thiếu database/fixture, test tích hợp vẫn báo lỗi để không che giấu vấn đề môi trường.


## 8. Database Demo quy mô lớn

Giữ nguyên ba database theo đúng vai trò:

- `baomatdulieu`: database ứng dụng và các test policy hiện có.
- `baomatdulieu_benchmark`: nguồn benchmark, không để Demo ghi dữ liệu vào đây.
- `baomatdulieu_demo`: bản corpus dành riêng cho UI, có users/MFA và audit riêng.

Sau khi benchmark đã có 16.000 documents, 48.000 chunks và real embeddings:

~~~powershell
. .\scripts\load_demo_env.ps1
python .\scripts\setup_demo_database.py
python .\scripts\seed_demo_users.py
~~~

User PostgreSQL cần quyền CREATEDB để script tự tạo database. Nếu không có quyền đó, tạo database rỗng `baomatdulieu_demo` bằng tài khoản quản trị rồi chạy lại script. Script kiểm tra đúng nguồn/đích, chỉ copy documents/chunks/embeddings theo batch, tạo HNSW index và không copy benchmark users, MFA, audit, query cases hoặc kết quả thí nghiệm. Không có thao tác DROP/TRUNCATE.

Sau đó chạy `.scriptsstart_demo.ps1`. Demo server và `answer_internal_query()` đều bị pin vào `baomatdulieu_demo`. Danh mục tài liệu được tìm kiếm/phân trang ở backend (50 tài liệu/trang, tối đa 100) để tránh đẩy toàn bộ 16.000 dòng vào trình duyệt.

Các test policy hiện có vẫn dùng `baomatdulieu`; retrieval integration tests vẫn chỉ đọc `baomatdulieu_benchmark`; Demo runtime dùng `baomatdulieu_demo`.

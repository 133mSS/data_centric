-- ============================================================
-- 03_seed_chunks.sql
-- Seed chunks cho kiểm thử Access-Controlled Retrieval
-- ============================================================

INSERT INTO chunks (document_id, content)
VALUES
(
    1,
    'Công ty ABC Tech ra mắt sản phẩm mới vào quý 3/2026, hỗ trợ tích hợp AI cho doanh nghiệp vừa và nhỏ.'
),
(
    2,
    'Nhân viên gửi đơn qua hệ thống HR trước 3 ngày làm việc, quản lý trực tiếp phê duyệt trong 24 giờ.'
),
(
    3,
    'Bảng đánh giá hiệu suất quý 3/2026 của phòng Kỹ thuật: 12/20 nhân viên đạt mức Xuất sắc, 2 nhân viên nằm trong danh sách cảnh báo hiệu suất thấp.'
),
(
    4,
    'Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất tháng 12/2026, mức định giá thương lượng là 45 triệu USD.'
),
(
    5,
    'ABC Tech ký hợp đồng cung cấp 5.000 máy chủ với Nhà cung cấp A trong năm 2027, tổng giá trị hợp đồng là 2,8 triệu USD.'
),
(
    6,
    'Module policy_engine.py chịu trách nhiệm kiểm tra nhãn dữ liệu và quyền truy cập của người dùng trước khi chunk được đưa vào prompt.'
),
(
    7,
    'Hệ thống quản lý nhân sự sẽ được bảo trì từ 22:00 đến 23:30 ngày 15/10/2026.'
),
(
    8,
    'ABC Tech tuyển thực tập sinh Data Engineering, làm việc tại Hà Nội, yêu cầu kiến thức SQL và Python.'
);
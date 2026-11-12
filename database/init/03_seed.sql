-- ============================================================
-- 03_SEED.sql
-- Phase 2 - Synthetic Data
-- ============================================================

BEGIN;

-- ============================================================
-- 1. DOCUMENTS
-- ============================================================

INSERT INTO documents
    (title, content, classification, department)
VALUES

-- #1
(
    'Thông báo ra mắt sản phẩm',
    'Công ty ABC Tech ra mắt sản phẩm mới vào quý 3/2026, hỗ trợ tích hợp AI cho doanh nghiệp vừa và nhỏ.',
    'Công khai',
    NULL
),

-- #2
(
    'Quy trình xin nghỉ phép',
    'Nhân viên gửi đơn qua hệ thống HR trước 3 ngày làm việc, quản lý trực tiếp phê duyệt trong 24 giờ.',
    'Nội bộ',
    NULL
),

-- #3
(
    'Đánh giá hiệu suất phòng Kỹ thuật',
    'Bảng đánh giá hiệu suất quý 3/2026 của phòng Kỹ thuật: 12/20 nhân viên đạt mức Xuất sắc, 2 nhân viên nằm trong danh sách cảnh báo hiệu suất thấp.',
    'Mật',
    'Kỹ thuật'
),

-- #4
(
    'Kế hoạch sáp nhập',
    'Kế hoạch sáp nhập với công ty XYZ dự kiến hoàn tất tháng 12/2026, mức định giá thương lượng là 45 triệu USD.',
    'Tối mật',
    'Toàn công ty'
),

-- #5
(
    'Hợp đồng nhà cung cấp',
    'ABC Tech ký hợp đồng cung cấp 5.000 máy chủ với Nhà cung cấp A trong năm 2027, tổng giá trị hợp đồng là 2,8 triệu USD.',
    'Mật',
    'Kinh doanh'
),

-- #6
(
    'Mã nguồn hệ thống RAG',
    'Module policy_engine.py chịu trách nhiệm kiểm tra nhãn dữ liệu và quyền truy cập của người dùng trước khi chunk được đưa vào prompt.',
    'Nội bộ',
    'Kỹ thuật'
),

-- #7
(
    'Thông báo bảo trì',
    'Hệ thống quản lý nhân sự sẽ được bảo trì từ 22:00 đến 23:30 ngày 15/10/2026.',
    'Nội bộ',
    NULL
),

-- #8
(
    'Thông tin tuyển dụng',
    'ABC Tech tuyển thực tập sinh Data Engineering, làm việc tại Hà Nội, yêu cầu kiến thức SQL và Python.',
    'Công khai',
    NULL
);

UPDATE documents SET protection_profile = CASE id
    WHEN 1 THEN 'PUBLIC'
    WHEN 2 THEN 'GENERAL_INTERNAL'
    WHEN 3 THEN 'PERFORMANCE_SENSITIVE'
    WHEN 4 THEN 'CORPORATE_SECRET'
    WHEN 5 THEN 'COMMERCIAL_SECRET'
    WHEN 6 THEN 'TECHNICAL_SENSITIVE'
    WHEN 7 THEN 'MAINTENANCE_NOTICE'
    WHEN 8 THEN 'PUBLIC_RECRUITMENT'
    ELSE protection_profile
END
WHERE id BETWEEN 1 AND 8;


-- ============================================================
-- 2. USERS
-- ============================================================

INSERT INTO users
    (username, password_hash, role, department)
VALUES

(
    'nv_dev',
    'placeholder',
    'Nhân viên',
    'Kỹ thuật'
),

(
    'mgr_tech',
    'placeholder',
    'Manager',
    'Kỹ thuật'
),

(
    'mgr_sales',
    'placeholder',
    'Manager',
    'Kinh doanh'
),

(
    'ceo_boss',
    'placeholder',
    'Ban lãnh đạo',
    'Toàn công ty'
),

(
    'partner_01',
    'placeholder',
    'Đối tác',
    NULL
);

COMMIT;
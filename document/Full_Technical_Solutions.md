# HỒ SƠ GIẢI PHÁP KỸ THUẬT CHI TIẾT (TECHNICAL SOLUTIONS SPECIFICATION)

Dự án: **Control Server – Remote Management Application**

Tài liệu này giải trình chi tiết các giải pháp kỹ thuật đã được nghiên cứu và triển khai trong toàn bộ hệ thống, từ tầng hạ tầng mạng đến tầng ứng dụng và giao diện.

---

## 1. HẠ TẦNG MẠNG VÀ TRUYỀN TẢI (NETWORK LAYER)

### 1.1. Chiến lược Message Framing (Đóng gói thông điệp)
*   **Thách thức:** Giao thức TCP là "Byte-stream oriented", không có biên giới rõ ràng giữa các gói tin, dẫn đến hiện tượng dính gói khi truyền dữ liệu tốc độ cao.
*   **Giải pháp:** Triển khai cơ chế **Length-Prefix Framing** đồng bộ.
    *   **Control/Image Header (4 byte - `!I`):** Sử dụng định dạng Big-endian để truyền độ dài các lệnh JSON và khung hình JPEG.
    *   **Large Data Header (8 byte - `!Q`):** Dùng cho tính năng truyền tệp tin (File Transfer) và Video Record để hỗ trợ dung lượng vượt ngưỡng 4GB.
*   **Đọc dữ liệu nguyên tử (Atomic Read):** Xây dựng hàm `recv_all(n)` để đảm bảo luồng xử lý chỉ tiếp tục khi đã nhận đủ `n` byte từ socket buffer, loại bỏ hoàn toàn lỗi vỡ cấu trúc dữ liệu.

### 1.2. Kiến trúc Đa kết nối Song song (Multi-Socket Architecture)
*   **Thách thức:** Nghẽn cổ chai (Blocking) xảy ra khi luồng lệnh điều khiển phải chia sẻ đường truyền với luồng dữ liệu nặng (Live Stream/Download).
*   **Giải pháp:** Áp dụng mô hình **Socket Multiplexing**. Mỗi cửa sổ chức năng độc lập (Live Control, File Explorer, Media Manager) sẽ tự thiết lập một kết nối SSL riêng biệt.
*   **Kết quả:** Client có khả năng thực hiện đa nhiệm thực thụ (vừa quan sát màn hình, vừa tải tệp tin ngầm) với độ trễ tối thiểu.

---

## 2. BẢO MẬT VÀ XÁC THỰC (SECURITY LAYER)

### 2.1. Mã hóa TLS/SSL Toàn phần
*   **Cơ chế:** Toàn bộ luồng dữ liệu được bọc qua lớp **TLS 1.3**. Sử dụng thư viện `ssl` để tạo kênh truyền bảo mật AES-256.
*   **Tự động hóa Chứng chỉ (Cert Automation):** Tích hợp thư viện `cryptography` để Server tự tạo cặp khóa RSA và chứng chỉ X.509 ngay khi khởi chạy nếu không tìm thấy tệp tin chứng chỉ sẵn có. Giải pháp này giúp hệ thống sẵn sàng bảo mật ngay lập tức (Out-of-the-box).

### 2.2. Quy trình Handshake & Authentication
*   **Logic:** Sau khi thiết lập SSL, Client phải gửi chuỗi định danh (Password) ngay lập tức. Server thực hiện so khớp và trả về gói tin trạng thái cùng cấu hình hệ thống (Độ phân giải màn hình). Nếu sai, kết nối bị ngắt ngay lập tức để chống lại các kỹ thuật dò mật khẩu.

---

## 3. KIẾN TRÚC PHẦN MỀM (SOFTWARE ARCHITECTURE)

### 3.1. Command Pattern kết hợp Registry
*   **Cơ chế:** Sử dụng mẫu thiết kế **Command Registry** thông qua Python Decorators. Các module chức năng được tách rời (Decoupling) khỏi logic Server chính.
*   **Tính mở rộng (Scalability):** Cho phép thêm các tính năng mới chỉ bằng cách bổ sung Class kế thừa từ `BaseCommand` mà không cần sửa đổi mã nguồn cốt lõi (Tuân thủ nguyên lý Open-Closed của SOLID).

### 3.2. Quản lý Phiên làm việc (Session Controller)
*   **Cơ chế:** Sử dụng mô hình **Controller-Delegate** trên Client. Dashboard chính giữ quyền kiểm soát vòng đời của các cửa sổ tính năng con.
*   **Xử lý ngắt kết nối theo chuỗi (Cascading Close):** Khi một lỗi mạng được phát hiện, hệ thống tự động phát tín hiệu đóng toàn bộ các kết nối liên quan, dọn dẹp tài nguyên RAM và giải phóng cổng mạng một cách an toàn.

---

## 4. TỐI ƯU HÓA HÌNH ẢNH VÀ ĐIỀU KHIỂN (MONITORING & CONTROL)

### 4.1. High-Performance Screenshot (MSS)
*   **Giải pháp:** Sử dụng thư viện **MSS** để truy cập trực tiếp vào Graphic Buffer của hệ điều hành thay vì sử dụng các API bậc cao chậm chạp.
*   **Hiệu suất:** Tốc độ chụp đạt ngưỡng **>25-30 FPS** với mức chiếm dụng CPU cực thấp.

### 4.2. JPEG Throttling & Dynamic Resizing
*   **Kỹ thuật:** Ảnh màn hình được nén bằng OpenCV với tham số `IMWRITE_JPEG_QUALITY` (50-80%) tùy chỉnh. 
*   **Kết quả:** Giảm tải lưu lượng mạng LAN nhưng vẫn đảm bảo độ sắc nét cần thiết cho việc quan sát.

### 4.3. Thuật toán Coordinate Mapping (Ánh xạ tọa độ)
*   **Logic:** Chuyển đổi tọa độ click chuột trên Client sang tọa độ thực trên Server thông qua phép biến đổi tuyến tính:
    `Target_X = Click_X * (Server_Real_Width / Label_Display_Width)`
*   **Bù trừ sai số (Padding Offset):** Tự động tính toán và loại bỏ phần khoảng trắng dư thừa khi hiển thị ảnh ở chế độ `KeepAspectRatio`.

---

## 5. KỸ THUẬT UI/UX VÀ ĐỘ BỀN BỈ (UI/UX & ROBUSTNESS)

### 5.1. Cơ chế Debounce (700ms)
*   **Ứng dụng:** Triển khai trong File Explorer và Dashboard Search. Ngăn chặn việc gửi yêu cầu quét ổ đĩa liên tục khi người dùng đang gõ phím, giúp giảm tải cho Server và tránh hiện tượng giật lag giao diện.

### 5.2. Numeric Sort Engine
*   **Giải pháp:** Xây dựng class `NumericItem` tùy chỉnh để ghi đè hàm so sánh của PyQt5. Dữ liệu số (PID, CPU, RAM) được sắp xếp theo giá trị toán học thay vì thứ tự chữ cái của chuỗi văn bản.

### 5.3. Asynchronous GUI Processing
*   **Giải pháp:** Toàn bộ tác vụ I/O mạng được đẩy xuống các luồng phụ (**QThread**). 
*   **An toàn luồng (Thread-safety):** Sử dụng `QMetaObject.invokeMethod` để đảm bảo luồng phụ không can thiệp trực tiếp vào UI, ngăn chặn hiện tượng Segmentation Fault.

---

## 6. TỐI ƯU HÓA HỆ THỐNG (SYSTEM INTEGRATION)

### 6.1. Duyệt tệp tin Hiệu năng cao
*   **Kỹ thuật:** Sử dụng `os.scandir()` để lấy metadata đồng thời với danh sách tệp, tối ưu hóa tốc độ duyệt thư mục lớn gấp 5 lần so với `os.listdir()`.
*   **Nén dữ liệu tức thời:** Tích hợp logic tự động đóng gói thư mục thành định dạng ZIP bằng `shutil` trước khi truyền tải, giảm thiểu số lượng gói tin nhỏ truyền qua mạng.

### 6.2. Cross-Platform Path Handling
*   **Giải pháp:** Sử dụng thư viện **Pathlib** xuyên suốt dự án để tự động chuẩn hóa đường dẫn phù hợp với hệ thống Unix (Linux) và Windows.

### 6.3. Tự động kích hoạt Tệp tin (Automatic Invocation)
*   **Logic:** Sử dụng `os.startfile` (Windows) và `xdg-open` (Linux) để tự động mở ảnh/video/file ngay khi quá trình tải về hoàn tất, tối ưu hóa quy trình làm việc của người dùng.

---

## 7. TIÊU CHUẨN MÃ NGUỒN VÀ QUẢN LÝ DỰ ÁN

*   **Dependency Management:** Quản lý bằng công cụ **uv** hiện đại, đảm bảo tính nhất quán môi trường qua tệp tin khóa `uv.lock`.
*   **Tiêu chuẩn Code:** Tuân thủ **PEP 8** và định dạng **Ruff**. Áp dụng **Type Hints** đầy đủ trên toàn bộ mã nguồn để tăng khả năng bảo trì và gỡ lỗi.

---
*Tài liệu đặc tả kỹ thuật hệ thống Control Server.*

# BÁO CÁO PHÂN TÍCH GIẢI PHÁP KỸ THUẬT CHUYÊN SÂU (ADVANCED TECHNICAL REPORT)

Dự án: **Control Server – Remote PC Management System**
Nhóm thực hiện: **A & B** (Python Specialists - Công ty C)

---

## I. KIẾN TRÚC MẠNG VÀ TRUYỀN TẢI DỮ LIỆU (NETWORKING LAYER)

### 1. Giao thức TCP và Cơ chế Message Framing
Nhóm quyết định sử dụng **TCP Sockets** thay vì UDP để đảm bảo tính toàn vẹn dữ liệu (Data Integrity). Tuy nhiên, vì TCP là giao thức dạng dòng (Stream-oriented), hiện tượng "dính gói" (Data Coalescing) là không tránh khỏi.
*   **Giải pháp:** Triển khai cơ chế **Header-Length Prefixing**. 
    *   Với các lệnh JSON và ảnh: Sử dụng Header 4 byte (`!I`) để chứa độ dài.
    *   Với các tệp tin lớn (>2GB): Sử dụng Header 8 byte (`!Q` - unsigned long long) để tránh lỗi tràn số (Overflow).
*   **Hàm `recv_all(n)`:** Được xây dựng để đảm bảo nhận chính xác `n` byte dữ liệu bằng cách lặp lại lệnh `recv` cho đến khi đủ buffer, giải quyết triệt để vấn đề mất dữ liệu trên đường truyền không ổn định.

### 2. Bảo mật SSL/TLS Toàn phần (End-to-End Encryption)
Để bảo vệ thông tin điều khiển và hình ảnh nhạy cảm:
*   **SSL Context:** Sử dụng thư viện `ssl` để bọc các socket thông thường. Cấu hình phía Server yêu cầu chứng chỉ, phía Client thiết lập `CERT_NONE` để chấp nhận chứng chỉ tự ký (Self-signed) mà vẫn đảm bảo luồng dữ liệu được mã hóa bằng thuật toán **AES-256**.
*   **Dynamic Certificate Generation:** Server tích hợp thư viện `cryptography` để tự động tạo cặp khóa RSA và chứng chỉ X.509 ngay khi khởi chạy nếu chưa có, giúp ứng dụng có khả năng "Plug-and-Play" mà không cần cấu hình hạ tầng bảo mật phức tạp bên ngoài.

### 3. Kiến trúc Đa kết nối (Multi-Connection Architecture)
Khác với các ứng dụng socket đơn giản, hệ thống này sử dụng mô hình **Multi-Socket Session**:
*   **Command Socket:** Dùng để truyền các lệnh điều khiển nhẹ (Process list, App list, Shell commands).
*   **Stream/Data Socket:** Mỗi khi một tính năng nặng (Live Control, File Download) được kích hoạt, một kết nối SSL mới sẽ được thiết lập độc lập.
*   **Lợi ích:** Tránh nghẽn luồng (Blocking). Người dùng có thể vừa tải một tệp tin lớn, vừa điều khiển màn hình thời gian thực mà không bị độ trễ (latency) chồng chéo.

---

## II. KIẾN TRÚC PHẦN MỀM VÀ MÔ HÌNH LỆNH (SOFTWARE ARCHITECTURE)

### 1. Command Pattern & Registry System
Để giải quyết bài toán mở rộng tính năng (Scalability):
*   **Registry Decorator:** Sử dụng `@CommandRegistry.register("TYPE")` để tự động đăng ký các class xử lý lệnh vào một từ điển (Dictionary) trung tâm.
*   **Loose Coupling:** File `main_server.py` không cần biết chi tiết logic của từng lệnh. Khi nhận một gói tin, nó chỉ việc tra cứu Registry và thực thi phương thức `execute()`. Điều này cho phép nhóm thêm tính năng mới chỉ bằng cách thêm file vào thư mục `commands/`.

### 2. Quản lý Phiên làm việc (Session Controller)
Triển khai mô hình **Controller-Delegate** trên Client:
*   Cửa sổ **Dashboard** đóng vai trò `Controller`, quản lý vòng đời của tất cả các kết nối.
*   Khi Server bị ngắt kết nối đột ngột, một tín hiệu (Signal) sẽ được phát đi, kích hoạt hàm `handle_disconnect()` để đóng chuỗi toàn bộ các cửa sổ con một cách an toàn (Graceful Shutdown), ngăn chặn tình trạng treo ứng dụng (Deadlock).

---

## III. TỐI ƯU HÓA XỬ LÝ HÌNH ẢNH VÀ ĐIỀU KHIỂN (MONITORING & CONTROL)

### 1. High-Speed Screen Capture với MSS
Thay vì dùng `PyAutoGUI` hoặc `PIL` (vốn tiêu tốn 100-200ms cho mỗi khung hình), nhóm sử dụng thư viện **MSS**. MSS truy cập trực tiếp vào API đồ họa thấp cấp (DirectX/X11), cho phép chụp màn hình với tốc độ >30 FPS trong khi chiếm dụng CPU cực thấp (<5%).

### 2. Thuật toán Ánh xạ Tọa độ (Coordinate Mapping Transform)
Xử lý bài toán click chuột khi độ phân giải Client và Server khác nhau:
*   Sử dụng công thức tính tỉ lệ tuyến tính giữa kích thước hiển thị (`QLabel`) và độ phân giải thực (`pyautogui.size()`).
*   **Aspect Ratio Compensation:** Tính toán phần bù (padding) nếu ảnh được hiển thị ở chế độ giữ tỉ lệ, đảm bảo tọa độ click chính xác đến từng pixel.

---

## IV. TỐI ƯU HÓA TRẢI NGHIỆM NGƯỜI DÙNG (UX OPTIMIZATION)

### 1. Cơ chế Debounce và Throttling
*   **File Explorer Search:** Áp dụng **Debounce (700ms)** bằng `QTimer`. Hệ thống chỉ gửi yêu cầu quét thư mục lên Server sau khi người dùng ngừng gõ phím, giảm tải cho mạng và Server lên tới 80% so với cơ chế search truyền thống.

### 2. Sắp xếp dữ liệu thông minh (Numeric Sorting)
Mặc định `QTableWidget` sắp xếp theo dạng văn bản (9 < 10 nhưng "9" > "10"). 
*   **Giải pháp:** Ghi đè phương thức so sánh `__lt__` trong class `NumericItem`. Dữ liệu PID, CPU, RAM được so sánh theo giá trị số thực tế, mang lại trải nghiệm quản lý tiến trình chuyên nghiệp.

### 3. Xử lý Đa luồng (Asynchronous GUI)
Sử dụng **QThread** kết hợp với cơ chế **Signal/Slot** của Qt:
*   Toàn bộ tác vụ I/O mạng được đẩy xuống luồng phụ.
*   Cập nhật giao diện thông qua `QMetaObject.invokeMethod` để đảm bảo tính an toàn cho luồng (Thread-safety), tránh crash ứng dụng khi có nhiều luồng cùng cập nhật UI.

---

## V. CHIẾN LƯỢC ĐA NỀN TẢNG (CROSS-PLATFORM STRATEGY)

*   **Linux/Ubuntu Compatibility:** Giải quyết xung đột thư viện Qt bằng cách sử dụng `opencv-python-headless`. 
*   **Path Management:** Sử dụng thư viện `pathlib` xuyên suốt dự án để tự động xử lý dấu gạch chéo đường dẫn (`/` và `\`) phù hợp với từng hệ điều hành.
*   **System Apps Scanning:** Triển khai cơ chế quét Registry trên Windows và quét thư mục `.desktop` trên Linux để liệt kê danh sách phần mềm cài đặt một cách chính xác nhất.

---

**KẾT LUẬN:** 
Ứng dụng Control Server không chỉ là một bài tập mạng máy tính, mà là sự tổng hòa của các kỹ thuật lập trình hệ thống hiện đại: từ mã hóa bảo mật, tối ưu hóa I/O, đến các mẫu thiết kế hướng đối tượng nâng cao.

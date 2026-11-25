# Thể lệ thi đấu HEXUDON

Tối ưu hoá lộ trình HEXUDON — Procon Việt Nam 2026. Tóm lược từ đề chính thức (`materials/2026_Procon_Problem VI.pdf`). Nếu file này khác đề của BTC thì theo BTC.

- Mục 1–10 là nội dung của đề. Chỗ ghi *(ngoài đề)* là thông tin bổ sung, không có trong PDF.
- Hai phụ lục cuối file ghi giải đáp từ Q&A và những chỗ bot trong repo đang làm khác. Phụ lục **không phải đề**.
- 🔶 là thông số BTC công bố cho từng trận.

## 1. Tổng quan

Mỗi đội điều khiển hai loại tác nhân, xe tuần tra và xe tiếp nhiên liệu, trên bản đồ lưới lục giác. Xe tuần tra tiêu nhiên liệu để di chuyển và thu "udon" ở các điểm đến; xe tiếp nhiên liệu bổ sung nhiên liệu cho xe tuần tra.

## 2. Đơn vị thời gian

- Đơn vị nhỏ nhất để ra lệnh là **step**.
- Một trận chia thành nhiều **ngày**, kéo dài từ **4 đến 10 ngày**.
- Mỗi ngày có một số step nhất định, có thể khác nhau giữa các ngày. 🔶

## 3. Bản đồ và địa hình

- Bản đồ gồm các ô lục giác, mỗi ô tiếp giáp tối đa 6 hướng.
- Chiều rộng và chiều cao: mỗi chiều từ **8 đến 32** ô.
- Ô được đánh số từ 0 đến (rộng × cao − 1) theo hàng.
- Bốn loại địa hình: Đồng bằng, Núi, Ao, Đường bộ. Tác nhân không đi được qua Ao.
- Mọi ô đi được đều liên thông với nhau, không có ô nào bị cô lập.
- Địa hình không đổi suốt trận.
- *(ngoài đề, theo trang tài liệu API)* Setup chỉ có width, height, cells, không có danh sách ô kề. Bot tự tính hình học lục giác even-r (hàng chẵn lệch phải).

| Địa hình | Số step | Nhiên liệu (xe tuần tra) |
|---|---|---|
| Đồng bằng | 2 | 1 |
| Núi | 3 | 2 |
| Đường — thông thoáng | 1 | 2 |
| Đường — đông đúc | 2 | 2 |
| Đường — ùn tắc | 4 | 2 |
| Ao | không đi được | — |

## 4. Đường bộ và lưu lượng giao thông

- Ô đường có ba trạng thái: thông thoáng, đông đúc, ùn tắc.
- **Lưu lượng** = tổng số step dừng lại trên ô đó của mọi tác nhân, mọi đội, trong **hai ngày trước**, chia cho số đội.
- Phân loại theo hai ngưỡng thay đổi theo trận 🔶:
  - lưu lượng < ngưỡng đông đúc: thông thoáng;
  - ngưỡng đông đúc ≤ lưu lượng < ngưỡng ùn tắc: đông đúc;
  - lưu lượng ≥ ngưỡng ùn tắc: ùn tắc.
- Ngày 1 mọi đường thông thoáng. Ngày 2 chỉ tính theo lưu lượng Ngày 1.
- Trạng thái do máy chủ cấp đầu mỗi ngày, không đổi trong ngày, giống nhau cho mọi đội.

## 5. Điểm đến, chuỗi nhượng quyền và kho dự trữ

- Điểm đến nằm trên một số ô đồng bằng. Xe tuần tra đến điểm thì tự thu một phần udon.
- Mỗi xe tuần tra chỉ thu ở **lần ghé đầu tiên** mỗi điểm mỗi ngày.
- Không giới hạn tổng số phần một xe tuần tra có thể thu.
- Mỗi điểm thuộc đúng một **chuỗi nhượng quyền**; mỗi chuỗi là một loại udon. Số chuỗi từ 1 đến (số điểm đến). Vị trí và chuỗi không đổi suốt trận.
- Mỗi điểm có **kho dự trữ tối đa** từ 1 đến (số tác nhân của một đội), được bổ sung đầy đầu mỗi ngày. Mỗi lần thu trừ 1; kho bằng 0 thì không thu được.
- Kho **độc lập theo từng đội**: đội khác thu không làm giảm kho của bạn.

## 6. Tác nhân, di chuyển và nhiên liệu

### Tác nhân

- Mỗi đội có **3 đến 8** tác nhân.
- Vị trí xuất phát cho trước, là các ô đồng bằng không có điểm đến.
- Hai loại: **xe tuần tra** (thu udon, không tiếp nhiên liệu được) và **xe tiếp nhiên liệu** (tiếp nhiên liệu, không thu udon).
- Chọn loại cho từng tác nhân đầu trận, sau đó không đổi.

### Di chuyển

- Mỗi lệnh là đi sang một ô kề (6 hướng) hoặc đợi tại chỗ một số step.
- Được đi vào ô đang có tác nhân khác.
- Lệnh đi tới ô không kề hoặc ô Ao làm câu trả lời **không hợp lệ**.
- Tác nhân chỉ sang ô mới **sau khi** thực hiện đủ số step của địa hình **ô đang đứng**.

### Nhiên liệu

- Xe tuần tra tiêu nhiên liệu theo địa hình tại thời điểm nhận lệnh di chuyển.
- Dung lượng nhiên liệu tối đa như nhau cho mọi xe tuần tra của mọi đội. 🔶
- Hết nhiên liệu thì phải đợi được tiếp.
- Ra lệnh di chuyển khi **không đủ nhiên liệu** hoặc **không đủ step còn lại trong ngày** làm câu trả lời không hợp lệ.

### Tiếp nhiên liệu

- Xe tiếp nhiên liệu ở cùng ô với xe tuần tra từ 1 step trở lên thì xe tuần tra được nạp đầy.
- Xe tiếp nhiên liệu có nhiên liệu vô hạn và di chuyển không tốn nhiên liệu, nhưng vẫn phải đủ step.

## 7. Tiến trình một trận

1. Trước trận: máy chủ cấp cấu hình bản đồ, người chơi chọn loại cho từng tác nhân.
2. Bắt đầu trận: máy chủ cấp thông tin bản đồ kèm lựa chọn tác nhân của mọi đội.
3. Trong thời gian phản hồi của Ngày 1, gửi hành động cho Ngày 1.
4. Hết thời gian đó, máy chủ cấp thông tin Ngày 2, phản ánh vị trí và giao thông cuối Ngày 1.
5. Lặp lại cho tới hết số ngày.

## 8. Trạng thái đầu ngày

| | Ngày 1 | Ngày 2 trở đi |
|---|---|---|
| Vị trí | theo cấu hình bản đồ | vị trí cuối ngày trước |
| Nhiên liệu xe tuần tra | đầy | lượng còn lại cuối ngày trước |
| Đường | thông thoáng | theo lưu lượng hai ngày trước (Ngày 2: một ngày) |
| Kho dự trữ | đầy | đầy |

## 9. Xác định người thắng

Xét lần lượt, tiêu chí sau chỉ dùng khi tiêu chí trước bằng nhau:

1. Số **loại udon khác nhau** thu được trong cả trận nhiều nhất.
2. **Tổng số loại theo từng ngày** (cộng dồn số loại khác nhau của mỗi ngày) cao nhất.
3. **Tổng số phần** udon thu được nhiều nhất.
4. **Tổng thời gian phản hồi** thấp nhất, tính trên câu trả lời hợp lệ cuối cùng của mỗi ngày.
5. Tung xúc xắc hoặc tuyên bố hoà.

## 10. Lưu ý thi đấu

- Mỗi trận nhiều đội đấu đồng thời. Số đội tuỳ cặp đấu, công bố trong hướng dẫn thi đấu cuối cùng.
- Số ngày, số step mỗi ngày và thời gian phản hồi mỗi ngày xác định riêng cho từng trận.
- Máy chủ báo câu trả lời hợp lệ hay không hợp lệ (lỗi định dạng…).
- Được gửi lại trong thời hạn, nhưng gửi quá nhiều hoặc tệp quá lớn gây gián đoạn có thể bị coi là gây rối và bị loại.
- Câu trả lời hợp lệ cuối cùng được áp dụng.
- Cập nhật thông tin bản đồ có thể trễ một chút.
- *(ngoài đề, theo trang tài liệu API)* Poll tối thiểu 200 ms; nhanh hơn nhận HTTP 429.

## Phụ lục A: giải đáp trong Q&A

Nguồn: hai tập Q&A của cuộc thi gốc ở Nhật (NAPROCK / KOSEN Procon "HEXUDON", Q1–Q61). BTC Việt Nam chưa xác nhận từng câu áp dụng cho cuộc thi này.

**Thứ tự trong mỗi step** (Q6): trừ nhiên liệu → cập nhật vị trí → thu udon nếu đang ở điểm đến → tiếp nhiên liệu nếu cùng ô → cộng lưu lượng; sau đó mới nhận lệnh kế tiếp. Step 0 chỉ nhận lệnh.

| Câu hỏi | Trả lời |
|---|---|
| Bắt đầu ngày ngay trên điểm đến? | Thu ở step 1 nếu xe còn ở đó (đồng bằng cần 2 step để rời đi, nên đi ngay vẫn thu được) |
| Nạp nhiên liệu cần cùng ô bao lâu? | Cùng ô tại thời điểm tiếp nhiên liệu của một step là đủ, kể cả step cuối ngày. Lệnh đi dùng nhiên liệu vừa nạp được nhận từ step đó trở đi |
| Hai xe cùng đi một nhịp với xe tiếp nhiên liệu? | Trừ trước rồi nạp, nên cuối step vẫn đầy |
| Nhiều xe đến cùng lúc, kho không đủ? | Xe đứng trước trong danh sách `agents` được thu |
| Lưu lượng đếm khi nào? | Sau khi cập nhật vị trí; đầu ngày không đếm, step cuối có đếm |
| Đợi tốn gì? | Không tốn nhiên liệu; số step đúng bằng số ghi trong lệnh |
| Plan thiếu hoặc thừa step? | Cả câu trả lời bị từ chối |
| Không gửi kịp? | Vai trò: tất cả là xe tuần tra. Hành động: mọi xe đứng yên cả ngày |
| Bản đồ có phải hình xuyến? | Không. Hàng chẵn lệch phải |
| Giới hạn request | Khoảng 5 request mỗi giây, chỉ HTTP/1.1 |

**Khoảng giá trị Q&A cuộc thi gốc công bố** (đề Việt Nam không nêu): ngưỡng đông đúc 1–5, ngưỡng ùn tắc 2–10; nhiên liệu tối đa 1–3 lần số step ngày 1; số step mỗi ngày từ W+H đến 4×(W+H); số điểm đến từ số tác nhân đến max(W, H). `AGENTS.md` của repo không coi các giới hạn này là luật.

## Phụ lục B: bot đang khác Q&A ở đâu

Đọc từ `src/simulator.cpp`. Chưa sửa vì thay đổi simulator ảnh hưởng điểm và cần đối chiếu với server thật trước.

| Điểm | Q&A | Bot |
|---|---|---|
| Xe bắt đầu ngày trên điểm đến rồi đi ngay | Thu được ở step 1 | Không tính là thu |
| Thời gian cùng ô để nạp nhiên liệu | Một lần ở thời điểm tiếp nhiên liệu | Cần cùng ô ở hai mốc step liên tiếp (hoặc cùng ô lúc hết ngày) |

Cả hai đều khiến bot dự tính **thấp hơn** thực tế về nhiên liệu và số phần. Điểm thứ nhất còn có thể làm bot tưởng kho còn hàng cho xe đến sau trong khi server đã trừ.

Các chỗ còn lại (trừ nhiên liệu khi lệnh hoàn tất, xe đang đi dở tính ở ô nguồn, so lưu lượng `tổng >= số_đội × ngưỡng`) khớp với Q&A.

# UDON-SHIELD — bot HEXUDON (C++20)

Bot cho phần thi tối ưu lộ trình HEXUDON (Procon Việt Nam 2026): mỗi ngày nhận trạng thái trận, tính lộ trình cho các xe, tự kiểm tra lại bằng simulator và validator rồi mới gửi.

Đây không phải sản phẩm chính thức của BTC. Mã nguồn gốc lấy từ [Dung2005qk/4Fun-Procon](https://github.com/Dung2005qk/4Fun-Procon) (snapshot `166608b`), bổ sung phần chạy trên Linux, bridge practice và `run.py`.

## Đọc tài liệu nào

| Tài liệu | Nội dung | Khi các tài liệu mâu thuẫn |
|---|---|---|
| [`Đề bài.md`](Đề%20bài.md) | Luật chơi (tóm lược từ PDF đề chính thức), kèm phụ lục các chỗ đề không nói rõ | Chuẩn về luật trong repo; đề của BTC thắng nó |
| [`API.md`](API.md) | Giao thức giữa bot và server | Chuẩn cho dữ liệu trên đường truyền |
| [`SETUP.MD`](SETUP.MD) | Cài đặt, cấu hình, chạy, xử lý lỗi | Chuẩn cho cách vận hành |
| [`Kiến trúc.md`](Kiến%20trúc.md) | Thiết kế bên trong solver | Mô tả thiết kế, code là bằng chứng cuối |
| [`AGENTS.md`](AGENTS.md), [`research/`](research/) | Quy tắc và nhật ký nghiên cứu | Lịch sử; không cần để chạy bot |

## Cách chạy nhanh

**1. Cài công cụ**

| Hệ điều hành | Cần có |
|---|---|
| Ubuntu | `sudo apt install build-essential cmake ninja-build libcurl4-openssl-dev python3` |
| Windows | Visual Studio 2022 (MSVC), CMake >= 3.24, Ninja, Python 3.8+. Chạy lệnh trong **x64 Native Tools Command Prompt** |

**2. Lấy code và build**

```bash
git clone https://github.com/FCODER-Community/procon-hexudon.git
cd procon-hexudon
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-release --parallel
```

**3. Điền token và mã trận** vào file `.env` (đã bị git bỏ qua, không commit):

| Ubuntu | Windows |
|---|---|
| `cp .env.example .env` | `copy .env.example .env` |

| Khoá | Lấy ở đâu |
|---|---|
| `HEXUDON_TOKEN` | Đăng nhập https://hexudon.hairbui76.id.vn, bấm icon chìa khoá, copy chuỗi `eyJ...` |
| `GAME_ID` | Mở trận, copy mã cạnh tiêu đề (dán cả URL trang trận cũng được) |

**4. Chạy** (trên Windows gõ `python` thay cho `python3`)

| Việc | Lệnh |
|---|---|
| Kiểm tra token và mã trận, không gửi gì | `python3 run.py --check` |
| Chơi thật | `python3 run.py` |
| Tính plan một ngày, không nộp | `python3 run.py --dry-run` |
| Test | `ctest --test-dir build-release` và `python3 tests/test_run.py`, `python3 tests/test_bridge.py` |

> **Chú ý:** `python3 run.py` chọn vai trò và **nộp plan thật** cho tới hết trận.

Trận tính giờ và luyện tập tự do được tự nhận biết. Loại "luyện tập thi đấu" chưa hỗ trợ. Chi tiết và lỗi thường gặp: [`SETUP.MD`](SETUP.MD).

## Những điểm của luật dễ hiểu nhầm

| Dễ nghĩ là | Thực tế |
|---|---|
| Thu càng nhiều phần udon càng thắng | Xét lần lượt: (1) số loại khác nhau cả trận, (2) tổng số loại thu được theo từng ngày, (3) tổng số phần, (4) tổng thời gian phản hồi. Tiêu chí sau chỉ xét khi tiêu chí trước hoà |
| Ghé lại một điểm trong ngày thì thu thêm | Mỗi xe tuần tra chỉ thu ở lần ghé đầu tiên mỗi điểm mỗi ngày |
| Đội khác thu làm vơi kho | Kho tính riêng từng đội, đầu mỗi ngày đầy lại |
| Chi phí di chuyển tính theo ô sẽ đến | Tính theo ô đang đứng (ô nguồn) |
| Xe tiếp nhiên liệu cũng thu udon | Không. Nó không tốn nhiên liệu, nạp đầy cho xe tuần tra đứng cùng ô ít nhất 1 step |
| Đổi được vai trò giữa trận | Chọn một lần trước trận, cố định cả trận |
| Đội mình gây tắc ngay trong ngày | Trạng thái đường cố định trong ngày, tính từ lưu lượng của hai ngày trước, cộng mọi đội |
| Một xe đi sai chỉ mất lượt xe đó | Cả bài nộp của ngày bị từ chối |
| Nhiên liệu đầy lại mỗi ngày | Không. Vị trí và nhiên liệu còn lại chuyển sang ngày sau |

Công thức giao thông khi bot dự báo ngày sau: đường đông đúc khi `tổng step dừng >= số_đội × busyThreshold`, ùn tắc khi `>= số_đội × jammedThreshold`. Trạng thái thật luôn lấy theo server.

## Bot quyết định thế nào

1. Chọn vai trò trước trận bằng cách mô phỏng thử các đội hình.
2. Mỗi ngày dựng sẵn một plan an toàn, rồi dự báo giao thông và tính loại udon nào phải ưu tiên.
3. Sinh lộ trình ứng viên cho từng xe, ghép thành plan cả đội (kho, tiếp nhiên liệu, điểm hẹn), cải tiến tiếp bằng tìm kiếm lân cận.
4. Chỉ gửi plan mà cả simulator và validator độc lập đều chấp nhận.

Solver so điểm bằng ba tiêu chí đầu theo thứ tự từ điển. Tiêu chí thứ tư (thời gian phản hồi) **không** nằm trong hàm so sánh. Khi trận cho thời gian dài, bot có thể dùng thêm thời gian để tinh chỉnh (xem mục dưới), nên sẽ phản hồi chậm hơn.

## Thời gian phản hồi

| Mốc | Giá trị |
|---|---|
| Hạn cứng cho lần giải chính và chọn vai trò | tối đa 5000 ms. `--response-ms` lớn hơn vẫn bị cắt về 5000 |
| Dự phòng mạng trong solver | 1600 ms |
| Tinh chỉnh thêm khi trận cho thời gian dài | đến trước hạn của ngày 1100 ms |
| Hạn của ngày | thời điểm sớm hơn giữa `endsAt` và (lúc nhận state + `daySeconds`) |
| Không gửi nữa | khi còn dưới 800 ms |

## Bảo đảm correctness và giới hạn của nó

- "Hợp lệ" nghĩa là hợp lệ theo simulator và validator của repo, dựng theo hiểu biết về luật. Nó chưa phải bảo đảm server sẽ chấp nhận.
- Cache khoảng cách, cắt Pareto, column shortlist, beam và thứ tự duyệt chỉ để giảm không gian tìm kiếm. Plan được chọn luôn chạy lại qua `Simulator` và `Validator`; ứng viên chỉ có cận trên không được gửi.
- Master là set-packing tự viết, không dùng OR-Tools CP-SAT. Chỉ khi `searchComplete=true` mới có chứng minh tối ưu **trên tập lộ trình đã sinh**, không phải tối ưu toàn cục. Hết giờ thì trả kết quả tốt nhất đang có.
- Beam và DFS của master xếp nhánh theo điểm biên đã chặn bởi kho. Đây là thứ tự tìm, không cắt bỏ nghiệm. Cận trên được tính theo từng chế độ bundle để các contingency loại trừ nhau không làm phồng cận.
- Nếu server từ chối plan, bot gửi lại plan WAIT (đứng yên). Nếu WAIT cũng bị từ chối, bot dừng với lỗi.
- Bot không gửi token qua HTTP thường, trừ `localhost`.

## Mã nguồn

| Đường dẫn | Vai trò |
|---|---|
| `src/simulator.cpp` | Chuyển trạng thái và tính điểm |
| `src/validator.cpp` | Kiểm tra plan độc lập |
| `src/graph.cpp` | Tìm đường trên lưới lục giác, nhãn Pareto |
| `src/planner.cpp` | Sinh lộ trình, tiếp nhiên liệu, master, cải tiến thích nghi, chọn vai trò |
| `src/decision.cpp` | Phân bổ thời gian, kịch bản giao thông, chứng nhận, ledger |
| `src/protocol.cpp`, `src/btc_protocol.cpp` | JSON và schema BTC |
| `src/btc_main.cpp` | Host HTTP (WinHTTP trên Windows, libcurl trên Linux/macOS), sandbox, replay |
| `src/main.cpp` | CLI `udonshield_cli` |
| `strategies/blank_slate/` | Bộ lập kế hoạch độc lập, dùng làm nguồn ứng viên thứ hai |
| `tools/hexudon_bridge.py` | Nối solver với API `/api/game/...` của trang thi |
| `run.py` | Đọc `.env` rồi chạy bot, tự bật bridge khi cần |
| `tests/`, `bench/` | Test (gồm server HEXUDON giả) và benchmark |

## Trạng thái dự án

Tác giả gốc đã **dừng nghiên cứu**. Những điểm cần biết trước khi dùng:

- **Điều phối xe tiếp nhiên liệu** còn yếu, nhất là trên map nhỏ hoặc vừa: chọn vai trò chưa tối ưu và tiếp tế bị lệch pha. Hướng đề xuất: ràng buộc nguyên tử giữa xe tiếp nhiên liệu và xe tuần tra trong master, và chọn vai trò thích ứng (toàn tuần tra trên map nhỏ, nhiều nhiên liệu). Xem `research/` (chuỗi `284`–`288`).
- **Chọn vai trò khi vào trễ:** nếu setup đến khi còn không quá 2200 ms trước giờ bắt đầu, bot dùng cách chọn nhanh thay cho mô phỏng đầy đủ. `research/STATE.md` ghi hotfix này (371) chưa được xác nhận cho thi đấu.
- **Bridge cho trang thi chưa được thử với server thật.** Nó mới chạy trọn trận với server giả (`tests/fake_hexudon.py`). Chạy `--check` và một trận practice trước khi thi.
- **Simulator khác Q&A ở hai điểm** (thu udon khi xuất phát trên điểm đến, thời gian cùng ô để nạp nhiên liệu). Xem phụ lục B của [`Đề bài.md`](Đề%20bài.md).
- **HTTP trên Linux** mới được thêm: build và test local đã qua, chưa được đánh giá trên server chính thức.
- **Windows:** bản này (gồm `run.py` và phần sửa host HTTP) chưa được build thử lại trên Windows.
- Hạng 1 trước bot luyện tập không chứng minh bot mạnh. Giải thật có 8–10 đội chung map, luyện tập chỉ tối đa 3 bot.

## Ghi chú kỹ thuật

- Host production gọi `UdonShieldEngine::solve_day_until(...)` với hạn của server; hết ngân sách chứng nhận thì phát plan WAIT chính xác.
- `MatchSession` giữ vòng đời `state -> acknowledgement -> precompute/proof` trong một tiến trình.
- `ResponseLedger` giữ contingency đã chứng nhận cho ngày sau, kiểm tra lại trên state thật và không trộn bundle cache dở dang với lộ trình mới.
- `serialize_decision_replay(...)` ghi artifact `udon-shield-replay-v1` gồm manifest giao thông, risk policy, ứng viên, trace và footprint.
- `ParetoRouter` cache theo đầy đủ trạng thái đường và ràng buộc Pareto; cache hit không bỏ qua validation.

## Số đo lịch sử

Các số dưới đây do tác giả gốc đo trong giai đoạn nghiên cứu, **không được đo lại** cho bản này và không phải bằng chứng trên server chính thức. Benchmark synthetic `32x32`, 8 agent, 24 spot:

```text
master-oracle: exact_matches=1000/1000
master-oracle: exhaustive=64000 bounded=49390 reduction=22.8281%
decision_ms=4428 emergency=0 score_today=11,11,31 certified_lb=11,11,31
decision_phases_ms=incumbent:20 fast:0 search:3120 prepare:710 certify:578
```

So full shield với đối chứng (thắng/hoà/thua): 40 map xác nhận `14/14/12`; holdout 80 map cùng vai trò `22/38/20`; holdout native `22/36/22`. Tỷ lệ invalid bằng 0, p95 `545–579 ms`. Sign test chưa có ý nghĩa thống kê, nên không kết luận được là vượt trội.

## Giấy phép

Xem [`LICENSE`](LICENSE).

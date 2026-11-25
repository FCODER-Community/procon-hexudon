# SETUP — chạy bot UDON-SHIELD

Trang thi: `https://hexudon.hairbui76.id.vn` (tài liệu API ở `/docs`).

## 1. Yêu cầu

- CMake >= 3.24, Ninja, compiler C++20
- Python 3.8+ (chỉ dùng thư viện chuẩn)
- Tài khoản đội trên trang thi

Ubuntu (g++ 11+ hoặc clang 14+):

```bash
sudo apt install build-essential cmake ninja-build libcurl4-openssl-dev python3
```

Windows: Visual Studio 2022 (MSVC), CMake, Ninja, Python. Mở **x64 Native Tools Command Prompt** để Ninja thấy MSVC. HTTP dùng WinHTTP, không cần libcurl.

## 2. Build

```bash
git clone https://github.com/FCODER-Community/procon-hexudon.git
cd procon-hexudon
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-release --parallel
ctest --test-dir build-release --output-on-failure
```

Nếu CMake in `libcurl not found: udonshield_btc http mode disabled`, cài `libcurl4-openssl-dev` rồi chạy lại bước cấu hình.

## 3. Cấu hình `.env`

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

| Khoá | Bắt buộc | Ý nghĩa |
|---|---|---|
| `HEXUDON_TOKEN` | Có | Trên web bấm icon chìa khoá, copy chuỗi bắt đầu bằng `eyJ`. Token **có hạn**, hết hạn thì lấy lại. Để trống thì `run.py` lấy biến môi trường cùng tên |
| `GAME_ID` | Có | Mã trận (nút copy cạnh tiêu đề trang trận), `mã:team_id`, hoặc cả URL trang trận |
| `MODE` | Không | `active` hoặc `practice`, khi bot nhận biết sai |
| `URL` | Không | Đổi server. Phải là HTTPS, trừ `localhost` |
| `RESPONSE_MS` | Không | Mặc định `5000`; lớn hơn vẫn bị cắt về 5000 |
| `MATCH_ID` | Không | Chỉ cho server giao thức `/api/v1/matches`; xem mục 6 |

`.env` chứa token dạng plaintext và đã bị git bỏ qua. Không gửi file này cho người khác.

## 4. Chạy

```bash
python3 run.py --check     # 1. kiểm tra token + mã trận, không gửi gì
python3 run.py             # 2. chơi thật
python3 run.py --dry-run   # hoặc: tính plan một ngày, không nộp
```

Trên Windows gõ `python` thay cho `python3`. `--submit` vẫn được chấp nhận và giống chạy không tham số.

> **`python3 run.py` chơi thật ngay:** chọn vai trò (trận tính giờ không đổi lại được) và nộp plan mọi ngày cho tới hết trận.

### 4.1. Loại trận

Bot hỏi server để biết mã đó là loại nào:

| Loại trên web | Bot gửi `game_id` | Nộp plan qua | Hạn mỗi ngày |
|---|---|---|---|
| Thi đấu tính giờ (Active, gồm trận thử nếu cấu hình kiểu này) | mã trận | `/api/game/actions` | theo server |
| Luyện tập (Practice) | `mã:team_id` (team_id đọc từ token) | `/api/game/practice/actions` | không giới hạn; bot tự lấy tối thiểu 10 giây |
| Luyện tập thi đấu (competitive practice) | — | — | **Chưa hỗ trợ**, bot dừng và báo |

### 4.2. Điều cần biết

- Trận tính giờ: chạy bot **trước giờ bắt đầu**. Bot chờ mở chọn vai trò, gửi vai trò, rồi chờ trận bắt đầu. Không gửi kịp thì server cho mọi xe là xe tuần tra.
- Vào muộn (đã qua giai đoạn chọn vai trò): bot lấy vai trò đang có trên server và chơi tiếp từ ngày hiện tại.
- Practice đã chơi xong: bấm reset trên web rồi chạy lại.
- Tắt bot giữa trận: chạy lại đúng lệnh cũ, bot đọc replay để tiếp tục.
- Mock/Practice trên trang chủ là nhóm trận; mỗi trận bên trong có mã riêng. `--check` cho biết mã bạn dán thuộc loại nào.

## 5. Replay

File JSONL trong `artifacts/btc/`, ghi setup, vai trò, state, plan, ACK, kết quả. Không chứa token.

```bash
./build-release/udonshield_btc replay-check --replay artifacts/btc/<mã>.jsonl
```

Khi bắt đầu lại từ ngày 0, replay cũ được đổi tên thành `.bak-<thời gian>`. Plan của dry-run nằm trong `artifacts/practice-plans/`.

## 6. Cách chạy khác

### Server giao thức `/api/v1/matches` (`MATCH_ID`)

Solver nói chuyện trực tiếp, không qua bridge (xem `API.md`). Điền `MATCH_ID`, để trống `GAME_ID`, và `URL` nếu không phải `https://procon.ptit.edu.vn`. Chạy `python3 run.py` là gửi thật; không có `--check` và `--dry-run`.

### Chạy tay bridge và solver

Terminal 1 (bridge giữ token thật):

```bash
read -rs HEXUDON_TOKEN && export HEXUDON_TOKEN
python3 tools/hexudon_bridge.py --game-id '<mã>' --port 18081 --replay artifacts/btc/game.jsonl
```

Terminal 2 (solver chỉ dùng secret cục bộ `local`):

```bash
HEXUDON_TOKEN=local ./build-release/udonshield_btc http \
  --match game --url http://127.0.0.1:18081 --response-ms 5000 \
  --replay artifacts/btc/game.jsonl
```

`--replay` của hai lệnh **phải cùng một file**.

### Không cần mạng

```bash
python3 tests/test_bridge.py                       # kiểm tra bridge với server giả
python3 tests/fake_hexudon.py 18900                # server giả để chơi thử, in ra token giả
./build-release/udonshield_btc sandbox --response-ms 5000 --replay artifacts/btc/sandbox.jsonl
```

Chơi thử với server giả: điền `.env` bằng token giả được in ra, `GAME_ID=q-practice` (hoặc `q-active`), `URL=http://127.0.0.1:18900`, rồi `python3 run.py`. Mỗi lần chơi xong phải khởi động lại server giả.

CLI cho từng bước:

```bash
./build-release/udonshield_cli roles config.json [beam-width]
./build-release/udonshield_cli plan config.json state-day-1.json 5000
./build-release/udonshield_cli plan config.json state.json ledger.json 5000   # từ ngày 2
./build-release/udonshield_cli validate config.json state.json plan.json
./build-release/udonshield_cli advance-ledger config.json ledger.json state.json plan.json
./build-release/udonshield_cli session config.json
```

Trên Windows, file chạy có đuôi `.exe`.

## 7. Lỗi thường gặp

| Thông báo | Cách xử lý |
|---|---|
| `Token đã hết hạn lúc ...` | Lấy token mới (icon chìa khoá), thay trong `.env` |
| `HTTP 401` | Token sai hoặc hết hạn |
| `HTTP 403` | Đội không có quyền với trận này |
| `HTTP 404` | Sai mã trận, hoặc đội không nằm trong trận. Thử `MODE=practice` hoặc `MODE=active` |
| `Trận đã kết thúc` | Practice: reset trên web |
| `Trận đang chờ chọn vai trò nên chưa dry-run được` | Chạy không kèm `--dry-run` |
| `roles REJECTED` | Giai đoạn chọn vai trò đã đóng; chạy lại, bot lấy vai trò trên server |
| `day N REJECTED` | Server từ chối plan; bot gửi lại plan đứng yên. Giữ replay và log để tìm nguyên nhân |
| `Chưa build bot` | Làm mục 2 |
| `refusing to send the token over a non-HTTPS upstream` | `URL` phải là HTTPS |

## 8. An toàn

- Không ghi token vào file được git track, tham số dòng lệnh, log hay ảnh chụp màn hình.
- Đổi mật khẩu mặc định của tài khoản đội ngay sau lần đăng nhập đầu.
- Thư mục `materials/` (slide, đề, Q&A) bị git bỏ qua vì tài liệu có thể chứa thông tin đăng nhập.
- Lỡ commit token thì thu hồi; xoá file không đủ vì lịch sử git vẫn giữ.

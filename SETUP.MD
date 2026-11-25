# SETUP — chạy bot UDON-SHIELD trên HEXUDON

Hướng dẫn build và cho bot chơi trên trang HEXUDON. Có 2 đường:

| Chế độ | Server | Dùng khi |
|---|---|---|
| **A. BTC / HTTP trực tiếp** | `https://procon.ptit.edu.vn` (hoặc mirror luyện tập) | Có match id `m-xxxx` theo contract BTC |
| **B. Practice qua bridge** | `https://hexudon.hairbui76.id.vn` (API `/api/game/...`) | Chơi game luyện tập tự do trên trang hexudon |

Sandbox offline (không cần mạng/token) ở mục 5.

## 1. Yêu cầu

- CMake >= 3.24, Ninja, compiler C++20 (g++ 11+ hoặc clang 14+)
- Linux/macOS: `libcurl` dev để bật HTTP mode
- Python 3.8+ (chỉ cần cho chế độ B, bridge chỉ dùng stdlib)
- Token đội lấy từ trang HEXUDON (dạng `bot-...`)

```bash
sudo apt install build-essential cmake ninja-build libcurl4-openssl-dev python3
```

Windows: Visual Studio 2022 (MSVC) + CMake + Ninja. HTTP dùng WinHTTP, không cần libcurl.

## 2. Build

```bash
cmake -S . -B build-release -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-release --parallel
ctest --test-dir build-release --output-on-failure
```

Nếu CMake in `libcurl not found: udonshield_btc http mode disabled` thì cài `libcurl4-openssl-dev` rồi cấu hình lại. Thiếu libcurl thì `udonshield_btc http` không chạy được.

## 3. Token

Cách nhanh (Windows và Ubuntu): copy `.env.example` thành `.env`, điền token và mã trận, chạy `python3 run.py` (Windows: `python run.py`). `run.py` thay cho các bước thủ công ở mục 4A và 4B. `.env` chứa token dạng plaintext và đã bị git bỏ qua.

Cách thủ công: bot chỉ đọc token từ biến môi trường `HEXUDON_TOKEN`. Không đưa vào tham số dòng lệnh, source, replay hay file docs.

```bash
# Linux/macOS
read -rs HEXUDON_TOKEN && export HEXUDON_TOKEN
# ... chạy bot ...
unset HEXUDON_TOKEN
```

```powershell
# Windows
$env:HEXUDON_TOKEN = '<token nhập cục bộ>'
# ... chạy bot ...
Remove-Item Env:HEXUDON_TOKEN
```

## 4A. Chế độ A — HTTP trực tiếp (contract BTC)

```bash
mkdir -p artifacts/btc
./build-release/udonshield_btc http \
  --match m-0000 \
  --url https://procon.ptit.edu.vn \
  --response-ms 5000 \
  --replay artifacts/btc/m-0000.jsonl
```

- `--match`: match id lấy từ trang. Bắt buộc.
- `--url`: mặc định `https://procon.ptit.edu.vn`.
- `--response-ms 5000`: hard deadline mỗi ngày. Runtime tự giữ dư cho mạng, và không gửi nếu cửa sổ còn dưới ~800 ms.
- `--replay`: ghi log JSONL (không chứa header xác thực), dùng để audit bằng `replay-check`.
- `/setup`, `/state`, `/assignment` có thể trả `425` trước khi trận mở. Poll tối thiểu `200 ms` (mặc định `--poll-ms 220`).

Kiểm tra replay sau trận:

```bash
./build-release/udonshield_btc replay-check --replay artifacts/btc/m-0000.jsonl
```

## 4B. Chế độ B — practice trên hexudon qua bridge

Bridge `tools/practice_bridge.py` dịch contract BTC (`/api/v1/matches/{id}/...`) sang API practice của hexudon (`/api/game/...`). Solver nói chuyện với bridge ở localhost, bridge giữ token và gọi upstream bằng HTTPS.

1. Tạo game practice trên trang hexudon, copy `game-id` (dạng `d7471f1d-...:89`, có hậu tố `:team`).
2. Export token (mục 3).
3. Chạy bridge, mặc định **dry-run**: chỉ ghi plan ngày đầu ra đĩa, không gửi gì lên server.

```bash
python3 tools/practice_bridge.py \
  --game-id '<game-id>:<team>' \
  --port 18081
```

4. Terminal khác, chạy solver trỏ về bridge. Solver xác thực với bridge bằng secret cục bộ, mặc định `local` (khớp `--local-token`):

```bash
HEXUDON_TOKEN=local ./build-release/udonshield_btc http \
  --match practice \
  --url http://127.0.0.1:18081 \
  --response-ms 5000 \
  --replay artifacts/btc/practice.jsonl
```

5. Xem plan trong `artifacts/practice-plans/`. Ổn thì chạy lại bridge với `--submit` để gửi thật lên server. Khi chạy thật, đổi sang file `--replay` khác với lần dry-run, để solver không coi ACK giả của dry-run là đã nộp.

Tham số bridge hay dùng:

- `--submit`: POST plan thật. Mỗi ngày chỉ gửi một lần, resend nhận ACK cache.
- `--initial-agents p1,p2,...`: vị trí ngày 0 nếu game đã qua ngày 0.
- `--select-roles 1,1,1,0,0`: chọn role (`0`=patrol, `1`=tanker). **POST một lần, không đảo ngược**, cần `--submit`. Mặc định bridge đọc role từ server, không đổi.
- `--seed-replay <file>`: ghi role của server vào replay để solver dùng đúng role.
- `--upstream`: mặc định `https://hexudon.hairbui76.id.vn`.
- `--cache`, `--plan-dir`, `--timeout`: đường dẫn cache, thư mục plan, timeout (giây).

Bridge từ chối gửi token qua upstream không phải HTTPS (trừ localhost).

## 5. Sandbox offline

stdin/stdout JSON Lines, log ra stderr, không cần mạng hay token:

```bash
./build-release/udonshield_btc sandbox --response-ms 5000 --replay artifacts/btc/sandbox.jsonl
```

Chạy từng bước bằng CLI:

```bash
./build-release/udonshield_cli roles config.json
./build-release/udonshield_cli plan config.json state-day-1.json 5000
./build-release/udonshield_cli validate config.json state.json plan.json
```

## 6. Lỗi thường gặp

| Lỗi | Xử lý |
|---|---|
| `HEXUDON_TOKEN is not set` | Export token, mục 3 |
| HTTP `425` | Trận chưa mở, đợi |
| HTTP `429` / `E_RATE_LIMIT` | Poll nhanh hơn `200 ms`, tăng `--poll-ms` |
| HTTP `403` từ upstream | Cloudflare chặn User-Agent mặc định. Bridge đã đặt UA riêng; kiểm tra lại token/URL |
| `libcurl not found` | `sudo apt install libcurl4-openssl-dev`, cấu hình lại CMake |
| `E_NOT_ADJACENT`, `E_POND`, `E_STEP_OVERFLOW`, `E_NO_FUEL`, `E_BAD_FORMAT` | Plan bị server từ chối. Bot gửi lại WAIT; xem replay để tìm nguyên nhân. Một agent sai làm cả submission bị từ chối |
| ACK lệch ngày | Runtime fail-closed, không cộng score. Xem replay |

## 7. Lưu ý

- Không ghi token vào file nào được git track. Chỉ để trong `.env` (đã bị git bỏ qua).
- Luyện tập BTC chỉ cho tối đa 3 bot/trận; giải chính thức có 8-10 đội cùng map, nên điểm practice chỉ là proxy.
- Số liệu p99/deadline trong README chưa phải bằng chứng production trên server chính thức.

# Tài liệu API trận đấu

Bot chạy được với hai giao thức. Đây là ghi chép của repo, không phải đặc tả chính thức: nếu khác trang tài liệu của BTC thì theo BTC và sửa lại file này.

| Giao thức | Dùng ở | Cách bot nối |
|---|---|---|
| **A. HEXUDON game API** (`/api/game/...`) | `https://hexudon.hairbui76.id.vn` — trang thi | `GAME_ID`, qua `tools/hexudon_bridge.py` |
| **B. Match API** (`/api/v1/matches/{id}/...`) | server theo giao thức này (mặc định `https://procon.ptit.edu.vn`) | `MATCH_ID`, solver nối trực tiếp |

Không lưu token thật trong repository. Header: `Authorization: Bearer <token>`.

## A. HEXUDON game API

Nguồn: `/openapi.json` và web client công khai của trang (đọc ngày 2026-11-26), cùng tài liệu format của BTC. **Dạng phản hồi chưa được đối chiếu với một trận thật bằng token đội**; spec không khai schema phản hồi.

Token là JWT lấy trên web (icon chìa khoá), có hạn dùng. Trường `id` trong token là team id.

### Loại trận

`GET /manager/api/question/{mã}` trả `question_data` (chuỗi JSON) có `is_practice`, `no_reset`.

| `is_practice` | `no_reset` | Loại | `game_id` | Đường nộp |
|---|---|---|---|---|
| false | — | Tính giờ | `mã` | `POST /api/game/actions` |
| true | false | Luyện tập | `mã:team_id` | `POST /api/game/practice/actions` |
| true | true | Luyện tập thi đấu | `mã` | `POST /api/game/competitive/actions` (**bot chưa hỗ trợ**) |

### Lời gọi bot dùng

| Lời gọi | Ghi chú |
|---|---|
| `GET /api/game/state?game_id=` | `status` = `selecting_agents`, `in_progress`, `finished`; `day`; `selection_opens_in`; `day_deadline_in` |
| `GET /api/game/config?game_id=` | Cấu hình trận (định dạng bên dưới), gồm vị trí xuất phát `agents` |
| `POST /api/game/agent-types` | `{"game_id": ..., "types": [0,1,0]}` |
| `GET /api/game/day?game_id=` | Thông tin đầu ngày |
| `POST .../actions` | `{"game_id": ..., "day": 0, "actions": [[2,2,-5], ...]}` |
| `GET /api/game/result`, `GET /api/game/practice/score` | Kết quả |
| `POST /api/game/practice/reset` | Chơi lại practice (bot không tự gọi) |

Theo spec, trước khi trận mở, `/api/game/board` trả 409 cho đội.

### Định dạng dữ liệu (theo tài liệu format)

**Config:** `startsAt` (UNIX giây), `daySeconds[]`, `daySteps[]` (số phần tử = số ngày), `map{width,height,cells}` với `cells` là mảng theo hàng, `spots[]{brand,pos,stocks}`, `agents[]` (vị trí xuất phát), `fuelLimits`, `players`, `busyThreshold`, `jammedThreshold`.

**Day:** `endsAt` (UNIX giây), `day` (từ 0), `agents[]{kind,pos,fuel}` (`kind` 0 = tuần tra, 1 = tiếp nhiên liệu), `others[]{id,agents[]}`, `traffics[]{pos,status}` (0 thông thoáng, 1 đông đúc, 2 ùn tắc).

**Vai trò:** mảng `0`/`1`, đúng số xe. Không gửi kịp thì mọi xe là xe tuần tra.

**Plan:** mảng-của-mảng, mỗi xe một mảng theo thứ tự trong config. `0..5` là hướng, `-N` là đợi `N` step. **Tổng số step của mỗi xe phải đúng bằng `daySteps`** — thiếu hay thừa đều bị từ chối, và một xe sai thì cả bài bị từ chối. Không gửi kịp thì mọi xe đứng yên cả ngày.

**Tần suất:** BTC đề nghị khoảng 5 request mỗi giây, chỉ HTTP/1.1.

## B. Match API

| Lời gọi | Ghi chú |
|---|---|
| `GET /api/v1/matches/{id}/setup` | Cấu hình trận |
| `POST /api/v1/matches/{id}/assignment` | Mảng vai trò |
| `GET /api/v1/matches/{id}/start` | Đợi trận bắt đầu |
| `GET /api/v1/matches/{id}/state` | Trạng thái đầu ngày |
| `POST /api/v1/matches/{id}/actions` | Plan. Mất ACK thì gửi lại đúng body cũ |
| `GET /api/v1/matches/{id}/result` | Kết quả |

Bridge ở giao thức A đóng vai server của giao thức B cho solver.

- Đường không có trong `traffics` được coi là thông thoáng. Nhiên liệu đối thủ bị ẩn thì bot giả định đầy.
- `action_result.day` bắt đầu từ 1, phải bằng `state.day + 1`. ACK chấp nhận nhưng lệch ngày: bot dừng. ACK từ chối và lệch ngày: bot coi server đã cho đứng yên ngày đó.
- Mã `425`, `429`, `5xx` được thử lại; `404`, `409` trên `/state` thì kiểm tra `/result`; mã khác thì dừng.
- WebSocket (`/ws/v1/matches/{id}`) chưa hỗ trợ. Sandbox stdin/stdout JSON Lines được hỗ trợ.

## Bản đồ và chi phí

- `pos = row * width + col`, đánh số từ 0. Lưới lục giác even-r (hàng chẵn lệch phải), không phải hình xuyến.
- `cells`: `0` đồng bằng, `1` đường, `2` núi, `3` ao.
- Hướng theo chiều kim đồng hồ từ trên-trái: `0` trên-trái, `1` trên-phải, `2` phải, `3` dưới-phải, `4` dưới-trái, `5` trái.

Chi phí tính theo **ô nguồn**; "fuel" chỉ áp dụng cho xe tuần tra; đợi không tốn fuel.

| Ô đang đứng | Step | Fuel |
|---|---|---|
| Đồng bằng | 2 | 1 |
| Núi | 3 | 2 |
| Đường thông thoáng | 1 | 2 |
| Đường đông đúc | 2 | 2 |
| Đường ùn tắc | 4 | 2 |
| Ao | không đi được | — |

## Thời hạn trong solver

- `endsAt` được hiểu là giây hoặc mili giây epoch. Hạn của ngày = sớm hơn giữa `endsAt` và (lúc nhận state + `daySeconds[day]`).
- Solver chừa 1600 ms dự phòng mạng, ngừng tinh chỉnh 1100 ms trước hạn, không gửi khi còn dưới 800 ms. Lần giải chính tối đa 5000 ms.
- Các con số này là mức an toàn rút ra từ quan sát, chưa được đo p99 trên server chính thức. Trận có `daySeconds` rất ngắn cần chạy thử trước.

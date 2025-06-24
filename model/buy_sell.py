import asyncio, json, collections, os, time
import yaml
import torch
import numpy as np
from websockets import connect
from models.tlob import TLOB
from datetime import datetime
import requests, hmac, hashlib

# ─── 설정 ──────────────────────────────────────────────────────────
CONFIG_PATH       = "../outputs/2025-06-20/19-28-14/.hydra/config20.yaml"
CKPT_PATH         = "../data/checkpoints/TLOB/LOBSTER_['INTC']_seq_size_128_horizon_10_seed_1/model.pt"
MEAN_PATH         = None
STD_PATH          = None
SYMBOL            = "BTCUSDT"
LEVEL             = 50
WS_URI            = "wss://stream.bybit.com/v5/public/linear"
THRESHOLD         = 0.85
WINDOW_SEC        = 3.0
COUNT_REQ         = 3
MIN_PRICE_DIFF    = 50
signal_buf        = collections.deque()
last_action_price = None        # 마지막 주문이 실제 체결된 가격 기준
last_trade_price  = None        # 실시간 체결가 저장

# Bybit Demo Trading V5 REST 설정
API_KEY     = None
API_SECRET  = None
BASE_URL    = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"

# 서명 생성 함수
def _sign_v5(timestamp: str, payload: str) -> str:
    msg = timestamp + API_KEY + RECV_WINDOW + payload
    return hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()

# 잔고 조회
def get_wallet_balance(coin="USDT", accountType="UNIFIED"):
    path = "/v5/account/wallet-balance"
    url = BASE_URL + path
    ts = str(int(time.time()*1000))
    param_str = f"accountType={accountType}&coin={coin}"
    sig = _sign_v5(ts, param_str)
    headers = {
        "X-BAPI-API-KEY":     API_KEY,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "X-BAPI-SIGN":        sig,
        "Content-Type":       "application/json"
    }
    params = {"accountType": accountType, "coin": coin}
    resp = requests.get(url, headers=headers, params=params)
    return resp.json()

# 롱 포지션 수량 조회
def get_long_position_qty(symbol=SYMBOL, accountType="UNIFIED"):
    path = "/v5/position/list"
    url = BASE_URL + path
    ts = str(int(time.time()*1000))
    param_str = f"accountType={accountType}&category=linear&symbol={symbol}"
    sig = _sign_v5(ts, param_str)
    headers = {
        "X-BAPI-API-KEY":     API_KEY,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "X-BAPI-SIGN":        sig,
        "Content-Type":       "application/json"
    }
    params = {"accountType": accountType, "category": "linear", "symbol": symbol}
    resp = requests.get(url, headers=headers, params=params).json()
    for item in resp.get("result", {}).get("list", []):
        if item.get("side") == "Buy":
            return float(item.get("size", 0))
    return 0.0

# 시장가 주문
def place_market_order(symbol="BTCUSDT", qty=0.01, side="Buy", reduce_only=False):
    path = "/v5/order/create"
    url = BASE_URL + path
    ts = str(int(time.time()*1000))
    body = {
        "category":    "linear",
        "symbol":      symbol,
        "side":        side,
        "orderType":   "Market",
        "qty":         str(qty),
        "timeInForce": "GoodTillCancel",
        "reduceOnly":  reduce_only
    }
    body_json = json.dumps(body)
    sig = _sign_v5(ts, body_json)
    headers = {
        "X-BAPI-API-KEY":     API_KEY,
        "X-BAPI-TIMESTAMP":   ts,
        "X-BAPI-RECV-WINDOW": RECV_WINDOW,
        "X-BAPI-SIGN":        sig,
        "Content-Type":       "application/json"
    }
    resp = requests.post(url, headers=headers, data=body_json)
    return resp.json()

# ───────────────────────────────────────────────────────────────────

def load_cfg(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

# 모델 초기화 및 정규화 설정
cfg = load_cfg(CONFIG_PATH)
hp  = cfg["model"]["hyperparameters_fixed"]
model = TLOB(
    seq_size     = hp["seq_size"],
    hidden_dim   = hp["hidden_dim"],
    num_layers   = hp["num_layers"],
    num_heads    = hp["num_heads"],
    is_sin_emb   = hp["is_sin_emb"],
    dataset_type = "LOBSTER",
    num_features = 46
)
sd = torch.load(CKPT_PATH, map_location="cpu")
model.load_state_dict(sd)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device).eval()

normalize = None
if MEAN_PATH and STD_PATH:
    mean = np.load(MEAN_PATH)
    std  = np.load(STD_PATH)
    normalize = (mean, std)

# 실시간 버퍼
lob_buf = collections.deque(maxlen=hp["seq_size"])
msg_buf = collections.deque(maxlen=hp["seq_size"])

# WebSocket 구독
async def _ws_stream(topic_prefix, arg, buffer, is_trade=False):
    async with connect(WS_URI) as ws:
        subscribe_arg = f"{topic_prefix}.{arg}"
        await ws.send(json.dumps({"op": "subscribe", "args": [subscribe_arg]}))
        async for raw in ws:
            msg = json.loads(raw)
            if not msg.get("topic", "").startswith(subscribe_arg):
                continue
            data = msg.get("data", {})
            if not is_trade:
                asks = [(float(p), float(q)) for p, q in data.get("a", [])[:10]]
                bids = [(float(p), float(q)) for p, q in data.get("b", [])[:10]]
                asks += [(0.0, 0.0)] * (10 - len(asks))
                bids += [(0.0, 0.0)] * (10 - len(bids))
                snap = [v for pair in asks for v in pair] + [v for pair in bids for v in pair]
                buffer.append(snap)
            else:
                tr = data
                if isinstance(tr, list) and tr:
                    t = tr[0]
                    global last_trade_price
                    last_trade_price = float(t.get("p", 0))  # 최근 체결가 저장
                    ts_evt    = t.get("T", 0) / 1000.0 % 86400.0
                    evt_type  = 2
                    oid       = t.get("ts", 0)
                    size      = float(t.get("v", 0))
                    direction = 1.0 if t.get("S") == "Buy" else 0.0
                    buffer.append([ts_evt, evt_type, oid, size, last_trade_price, direction])

async def ws_orderbook():
    return await _ws_stream("orderbook", f"{LEVEL}.{SYMBOL}", lob_buf)

async def ws_trade():
    return await _ws_stream("publicTrade", SYMBOL, msg_buf, is_trade=True)

# 추론 및 주문 루프
async def inference_loop():
    CONSEC_N = 3
    CUMUL_M  = 5
    global last_action_price, last_trade_price
    while True:
        if len(lob_buf) == hp["seq_size"] and len(msg_buf) == hp["seq_size"]:
            lob_arr  = np.stack(lob_buf).astype(np.float32)
            msg_arr  = np.stack(msg_buf).astype(np.float32)
            combined = np.concatenate([lob_arr, msg_arr], axis=1)
            if normalize:
                combined = (combined - normalize[0]) / normalize[1]
            x = torch.from_numpy(combined).unsqueeze(0).to(device)
            with torch.no_grad():
                logits = model(x)
                probs  = torch.softmax(logits, dim=-1).squeeze().cpu().numpy()
                pred   = int(probs.argmax())

            # 예측 신호 수신
            if pred != 1 and probs[pred] > THRESHOLD:
                action = "Buy" if pred == 0 else "Sell"

                # 1) 신호 버퍼 갱신
                now_ts = time.time()
                signal_buf.append((now_ts, action))
                while signal_buf and now_ts - signal_buf[0][0] > WINDOW_SEC:
                    signal_buf.popleft()

                # 2) 연속/누적 개수 계산
                consec = 0
                for _, a in reversed(signal_buf):
                    if a == action:
                        consec += 1
                    else:
                        break
                total = sum(1 for _, a in signal_buf if a == action)

                # 3) 신호 조건 만족 시에만 가격 차이 체크 및 주문
                if consec >= CONSEC_N or total >= CUMUL_M:
                    # 가격 차이 필터링
                    if last_action_price is not None:
                        diff = abs(last_trade_price - last_action_price)
                        if diff < MIN_PRICE_DIFF:
                            #print(f"Skipped {action}: price diff {diff:.4f} < {MIN_PRICE_DIFF}")
                            await asyncio.sleep(0.1)
                            continue

                    # 실제 주문 실행
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{now}] ▶ Execute {action} (consec:{consec}, total:{total})")
                    long_qty = get_long_position_qty()
                    if action == "Sell" and long_qty > 0:
                        resp = place_market_order(SYMBOL, long_qty, "Sell", reduce_only=True)
                    else:
                        resp = place_market_order(SYMBOL, 0.01,action, reduce_only=False)
                    print(f"[{now}] Order response: {resp}")

                    # 주문 후 초기화
                    last_action_price = last_trade_price
                    signal_buf.clear()

            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(0.01)

# 메인 실행
async def main():
    bal = get_wallet_balance()
    print("✅ Demo Trading 잔고 조회 결과:", bal)
    await asyncio.gather(
        ws_orderbook(),
        ws_trade(),
        inference_loop()
    )

if __name__ == "__main__":
    print("▶ 실시간 LOB+TRADE 결합 및 TLOB 추론 시작 (Bybit Demo REST 주문 포함)")
    asyncio.run(main())

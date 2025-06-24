"""
BINANCE → LOBSTER 스타일 수집기 (event / time / volume 3-모드 지원)

파일명 예)
BINANCE_2025-05-29_34200000_57600000_message.csv
BINANCE_2025-05-29_34200000_57600000_orderbook.csv
"""

import asyncio, json, csv, os, requests, websockets
from datetime import datetime, timedelta, timezone

# ────────── [ 사용자 설정 ] ──────────
SYMBOL   = "BTCUSDT"
DAYS     = 5                      # 수집 기간(일)

MODE               = "time"      # "event" | "time" | "volume"
EVENT_INTERVAL     = 10           # MODE="event" : N 번째 체결마다
SAMPLING_MS        = 250          # MODE="time"  : 고정 간격(ms)
VOLUME_THRESHOLD   = 500          # MODE="volume": 누적 체결 수량

LEVEL     = 10                    # depth 레벨(10/20)
STOCK     = "BINANCE"
SUFFIX    = "34200000_57600000"
SAVE_DIR  = "D:/programming/finance ai/data"
# ───────────────────────────────────

KST      = timezone(timedelta(hours=9))
START_TIME = datetime.now(KST)
END_TIME = START_TIME + timedelta(days=DAYS)
os.makedirs(SAVE_DIR, exist_ok=True)

# ───── 파일 관리 ─────
current_date = START_TIME.date()
msg_rows, lob_rows = [], []

def fname(date_str, typ):
    return os.path.join(SAVE_DIR, f"{STOCK}_{date_str}_{SUFFIX}_{typ}.csv")

def dump_pair(force_date=None):
    global current_date
    if not msg_rows: return
    
    # 날짜 결정
    target_date = force_date or current_date
    date_str = target_date.strftime("%Y-%m-%d")
    
    # 날짜 변경 시 current_date 업데이트
    if force_date and force_date != current_date:
        current_date = force_date
    
    with open(fname(date_str,"message"),"w",newline="") as f:
        csv.writer(f).writerows(msg_rows)
    with open(fname(date_str,"orderbook"),"w",newline="") as f:
        csv.writer(f).writerows(lob_rows)
    print(f"[{date_str}] 파일 저장 완료 ({len(msg_rows)} rows)")
    msg_rows.clear(); lob_rows.clear()

# ───── 글로벌 상태 ─────
current_lob  = None                # 40-열 스냅
event_cnt    = 0
volume_cum   = 0.0
last_trade   = None
last_trade_lock = asyncio.Lock()   # 동기화를 위한 락
collecting   = True

# ───── depth 핸들러 ─────
async def depth_handler():
    global current_lob, collecting
    url = f"wss://stream.binance.com:9443/ws/{SYMBOL.lower()}@depth{LEVEL}@100ms"
    
    retry_delay = 1  # 초기 재시도 대기 시간 (초)
    max_retry_delay = 30  # 최대 재시도 대기 시간 (초)
    
    while collecting:
        try:
            print(f"[DEPTH] 웹소켓 연결 시도: {url}")
            async with websockets.connect(url) as ws:
                print(f"[DEPTH] 웹소켓 연결 성공")
                retry_delay = 1  # 연결 성공 시 대기 시간 리셋
                
                async for m in ws:
                    if not collecting: 
                        print(f"[DEPTH] 수집 종료 신호로 연결 종료")
                        break
                    
                    d = json.loads(m)

                    # ① diff 업데이트 포맷
                    if "b" in d and "a" in d:
                        bids_lst = d["b"]; asks_lst = d["a"]
                    # ② 스냅샷 포맷
                    elif "bids" in d and "asks" in d:
                        bids_lst = d["bids"]; asks_lst = d["asks"]
                    else:
                        continue

                    bids = sorted([(float(p), float(q)) for p,q in bids_lst], reverse=True)
                    asks = sorted([(float(p), float(q)) for p,q in asks_lst])
                    bids = bids[:LEVEL] + [(0.0,0.0)]*max(0,LEVEL-len(bids))
                    asks = asks[:LEVEL] + [(0.0,0.0)]*max(0,LEVEL-len(asks))
                    snap = []
                    for i in range(LEVEL):
                        a = asks[i]; b = bids[i]
                        snap += [a[0], a[1], b[0], b[1]]
                    current_lob = snap
                    
        except websockets.exceptions.ConnectionClosed as e:
            if collecting:
                print(f"[DEPTH] 연결이 종료됨: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # 점진적 증가
            else:
                print(f"[DEPTH] 정상 종료")
                break
        except websockets.exceptions.WebSocketException as e:
            if collecting:
                print(f"[DEPTH] 웹소켓 오류: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            else:
                print(f"[DEPTH] 정상 종료")
                break
        except Exception as e:
            if collecting:
                print(f"[DEPTH] 예상치 못한 오류: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            else:
                print(f"[DEPTH] 정상 종료")
                break
    
    print(f"[DEPTH] 핸들러 종료")

# ───── trade 핸들러 ─────
async def trade_handler():
    global event_cnt, volume_cum, last_trade, collecting
    url = f"wss://stream.binance.com:9443/ws/{SYMBOL.lower()}@trade"
    
    retry_delay = 1  # 초기 재시도 대기 시간 (초)
    max_retry_delay = 30  # 최대 재시도 대기 시간 (초)
    
    while collecting:
        try:
            print(f"[TRADE] 웹소켓 연결 시도: {url}")
            async with websockets.connect(url) as ws:
                print(f"[TRADE] 웹소켓 연결 성공")
                retry_delay = 1  # 연결 성공 시 대기 시간 리셋
                
                async for m in ws:
                    if not collecting: 
                        print(f"[TRADE] 수집 종료 신호로 연결 종료")
                        break
                    
                    t = json.loads(m)
                    
                    # 수집 종료 조건 검사
                    trade_time = datetime.fromtimestamp(t['T']/1000, tz=KST)
                    if trade_time >= END_TIME:
                        print(f"[TRADE] 수집 기간 종료: {trade_time}")
                        collecting = False
                        break
                    
                    async with last_trade_lock:
                        last_trade = t
                        event_cnt += 1
                        volume_cum += float(t["q"])
                        
        except websockets.exceptions.ConnectionClosed as e:
            if collecting:
                print(f"[TRADE] 연결이 종료됨: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # 점진적 증가
            else:
                print(f"[TRADE] 정상 종료")
                break
        except websockets.exceptions.WebSocketException as e:
            if collecting:
                print(f"[TRADE] 웹소켓 오류: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            else:
                print(f"[TRADE] 정상 종료")
                break
        except Exception as e:
            if collecting:
                print(f"[TRADE] 예상치 못한 오류: {e}. {retry_delay}초 후 재연결 시도…")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            else:
                print(f"[TRADE] 정상 종료")
                break
    
    print(f"[TRADE] 핸들러 종료")

# ───── 샘플 1줄 저장 ─────
def emit_sample(trade):
    global current_date
    if current_lob is None: return
    
    ts_ms = trade["T"]
    et = datetime.fromtimestamp(ts_ms/1000, tz=KST)
    trade_date = et.date()
    
    # 날짜 변경 감지 (한국시간 자정 기준)
    if trade_date != current_date:
        if msg_rows:  # 기존 데이터가 있으면 저장
            dump_pair(current_date)
        current_date = trade_date
    
    midnight = datetime(et.year, et.month, et.day, tzinfo=KST)
    t_sec = (et - midnight).total_seconds()

    price = float(trade["p"]); qty = float(trade["q"])
    direc = 0 if trade["m"] else 1
    msg_rows.append([f"{t_sec:.6f}", 4, trade["t"], f"{qty:.8f}", f"{price:.8f}", direc])
    lob_rows.append(current_lob.copy())

# ───── 모드별 샘플러 ─────
async def sampler_event():
    global event_cnt
    while collecting and datetime.now(KST) < END_TIME:
        await asyncio.sleep(0.01)
        if event_cnt >= EVENT_INTERVAL and last_trade:
            async with last_trade_lock:
                if last_trade:
                    emit_sample(last_trade)
                    event_cnt = 0

async def sampler_time():
    while collecting and datetime.now(KST) < END_TIME:
        await asyncio.sleep(SAMPLING_MS/1000)
        async with last_trade_lock:
            if last_trade: 
                emit_sample(last_trade)

async def sampler_volume():
    global volume_cum
    while collecting and datetime.now(KST) < END_TIME:
        await asyncio.sleep(0.01)
        if volume_cum >= VOLUME_THRESHOLD and last_trade:
            async with last_trade_lock:
                if last_trade:
                    emit_sample(last_trade)
                    volume_cum = 0.0

def get_sampler():
    return {"event": sampler_event,
            "time":  sampler_time,
            "volume":sampler_volume}[MODE]

# ───── 메인 실행 ─────
async def main():
    try:
        await asyncio.gather(
            depth_handler(),
            trade_handler(),
            get_sampler()()
        )
    except Exception as e:
        print(f"메인 실행 오류: {e}")
    finally:
        global collecting
        collecting = False

if __name__ == "__main__":
    try:
        print(f"[START] SYMBOL={SYMBOL}  MODE={MODE}  DAYS={DAYS}")
        print(f"[START] 수집 기간: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')} ~ {END_TIME.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[START] 파일 분할: 한국시간 자정마다 새 파일 생성")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("사용자에 의해 중단됨")
    finally:
        collecting = False
        dump_pair()
        print("[END] 수집 완료")
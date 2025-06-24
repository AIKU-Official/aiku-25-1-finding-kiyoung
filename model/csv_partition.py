import pandas as pd
import numpy as np

# 원본 CSV 경로
csv_path = "data/trades_lob_train.csv"
df = pd.read_csv(csv_path)

# BUY_SELL_FLAG → direction (1: buy, -1: sell)
def map_direction(flag):
    return flag.map({True: 1, False: 0})  # 혹시 'Buy'/'Sell'이면 적절히 수정

# TYPE → event_type (임의 매핑, 수정 필요할 수 있음)
def map_event_type(type_col):
    return type_col.map({'LIMIT_ORDER': 1, 'ORDER_CANCELLED': 3, 'ORDER_EXECUTED': 4})

# time 컬럼 생성 (초 단위로 증가하는 값, 임의 생성)
def generate_time_column(n):
    return np.linspace(34200000, 57600000, n, dtype=int)

# message 데이터프레임 생성
message_df = pd.DataFrame({
    "time": generate_time_column(len(df)),
    "event_type": map_event_type(df["TYPE"]),
    "order_id": df["ORDER_ID"],
    "size": df["SIZE"],
    "price": (np.floor(df["PRICE"])).astype(int),
    "direction": map_direction(df["BUY_SELL_FLAG"])
})


# orderbook 데이터프레임 생성
orderbook_columns = {}
for i in range(1, 11):
    orderbook_columns[f"sell{i}"] = df[f"ask_price_{i}"]
    orderbook_columns[f"vsell{i}"] = df[f"ask_size_{i}"]
    orderbook_columns[f"buy{i}"] = df[f"bid_price_{i}"]
    orderbook_columns[f"vbuy{i}"] = df[f"bid_size_{i}"]

orderbook_df = pd.DataFrame(orderbook_columns)


from datetime import datetime, timedelta

# 시작 날짜와 저장할 일 수
start_date = datetime(2015, 1, 2)
num_days = 2 #17  # 원하는 일 수

base_path = "D:/my_tlob/data/INTC/INTC_2015-01-02_2015-01-30(example)"         #INTC_2015-01-02_2015-01-30

for i in range(num_days):
    current_date = start_date + timedelta(days=i)
    date_str = current_date.strftime("%Y-%m-%d")

    message_df.to_csv(f"{base_path}/{date_str}34200000_57600000message.csv", index=False, header=None)
    orderbook_df.to_csv(f"{base_path}/{date_str}34200000_57600000orderbook.csv", index=False, header=None)


print("LOBSTER 형식으로 변환 완료!")
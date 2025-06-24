'''
from datasets import load_dataset

print("Dataset loaded successfully!")
dataset = load_dataset("LeonardoBerti/TRADES-LOB")

# train split을 CSV로 저장
dataset["train"].to_csv("D:/TLOB/data/trades_lob_train.csv")
print("CSV file saved to data/trades_lob_train.csv")
'''

import numpy as np

# 파일 로딩
data = np.load("D:\TLOB\data\INTC\\train.npy")

# 전체 shape 확인 (행: 시점, 열: 피처)
print("Data shape:", data.shape)

# 마지막 열 5개 값 보기
print("Sample of last 5 columns at first row:", data[0, -7:])

# 전체 열별 고유값 요약 (특히 마지막 몇 개 열)
for i in range(1, 7):
    col_idx = -i
    unique_vals = np.unique(data[:, col_idx])
    print(f"Column {col_idx}: min={data[:, col_idx].min()}, max={data[:, col_idx].max()}, unique count={len(unique_vals)}")
    print(f"    Example values: {unique_vals[:10]}")

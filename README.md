# 기영이를 찾아서

📢 2025년 겨울학기 [AIKU](https://github.com/AIKU-Official) 활동으로 진행한 프로젝트입니다

## 소개

기영이를 찾아서는 주식 주가 지표를 통해 ai 모델이 자동적으로 투자 및 수익 확보가 가능하게 만드는 것을 목표로 한 프로젝트입니다. 노동 임금만으로는 부를 창출하기 어려운 현대사회에서 금융 자본을 자동으로 증식시킬 수 있는 ai 모델 개발은 많은 사람들에게 수요를 창출할 것입니다.

## 방법론

누적 가격 정보 데이터를 바탕으로 가격 변동 추이 (상승, 하락, 유지) 예측

모델  
" TLOB: A Novel Transformer Model with Dual Attention for Stock Price Trend Prediction with Limit Order Book Data " 논문의 TLOB 모델을 사용
[git link](https://github.com/LeonardoBerti00/TLOB)

데이터 수집  
- binance api의 lob 데이터 호출 api를 통해 실시간 수집  
- 자동화 코드를 통해 10일치 훈련 데이터 수집 (collector/col.py 참조)
- 주가 데이터의 lob 호출 api가 찾기 어려워 비트코인 lob 데이터로 변경

모델 학습  
- 수집한 비트코인 데이터도 주식 데이터와 동일하게 작동하는지 검증
- 기존 논문와 퍼포먼스 비교 및 개선점 도출

모의투자 연결
- 추론 코드와 예측값을 통한 매수 매도 시그널 결정 (buy_sell.py 참조)
- bybit api의 모의투자 api를 연결해 실시간 데이터에 적용

## 환경 설정

1. repository 클론
2. 가상 환경 설정 및 활성화
```sh
python -m venv env
```
```sh
env\Scripts\activate
```
3. 다운로드 requirements.txt
```sh
pip install -r requirements.txt
```

## 사용 방법

1. training 명령어
```sh
python main.py +model=tlob +dataset=lobster hydra.job.chdir=False
```

- 아래 경로의 파일 형태로 10일 이상 lob 데이터 필요
- LOBSTER  
directory : ../data  
folder name : "data/{stock_name}/{stock_name}_{year}-{start_month}-{start_day}_{year}-{end_month}-{end_day}"  
file name : "{year}-{month}-{day}_34200000_57600000_{type}"
- over 1h for training in GPU environment (NVIDIA 4060TI)


2. inference 명령어
```sh
python buy_sell.py
```
- 코드 내부 진입 후 사용자의 bybit api key 변경

## 예시 결과

### 모델 학습 결과  
dataset : 6.10 ~ 6.19  
tlob training result (experiment 1)  

1. result for test set

| Test metric  |  score  |
|--------------|---------|
|accuracy      |      0.8573 |
|f1_score      |      0.7881 |
|precision     |      0.8559 |
|recall        |      0.7441 |
|test_loss     |      0.3938 |

baseline performance from paper
### 사진 @@@@@@@@@@@@

2. result for each signal

| trend |  Precision  |  recall	 | f1-score  | support  |
|-------|-------------|----------|-----------|----------|
|0 | 0.8479	| 0.6443  |  0.7322  |   54901
|1 | 0.8582	| 0.9623  |  0.9073  |  225891
|2 | 0.8617	| 0.6258  |  0.7251  |   51863

3. confusion matrix for each signal

| | Predicted 0 (상승) | Predicted 1 (유지) | Predicted 2 (하락) |
|-------|-------------|----------|-----------|
|Actual 0 (상승)       |      42766         |    20134          |    2018|
|Actual 1 (유지)       |       7232        |    188261         |     7315|
|Actual 2 (하락)        |      2177      |       20180         |    42906|




### 모의투자 api 연결

### (사진) !!!!!!!!!!!!!!!

결과분석
- 실제 주가 예측에서는 가격 하락 예측을 잘 하지 못하는 것으로 나타남
- 훈련 데이터의 다양성 부족으로 overfitting 되었을 것이라 추측됨


## 팀원
  | 팀원                            | 역할                                       |
| ----------------------------- | ---------------------------------------- |
| [조규호](https://github.com/Jokyo0612) | team leader, data collection, model fine-tuning, documentation   |
| [박경빈](https://github.com/bbakk) | data collection, API-based web crawling, data pipline design |
| [백승현](https://github.com/snghyeon100) | model analysis, paper reseach, investment api integration |
| [유성흠]() | data collection, paper research, report compilation support |

# 미국 성장주 스크리너 MVP v3

## v3 추가 기능
- 현금 소진 기간(runway) 추정: 현금 / 최근 최대 4개 분기의 평균 분기 영업현금 소진액
- 발행주식 수 YoY 변화율
- 주식기반보상(SBC)/매출 비율
- 희석과 현금 위험을 점수에 반영
- 위험 플래그와 CSV 출력

## 설치 및 실행
Python 3.10 이상 권장:
```bash
pip install -r requirements.txt
```
SEC User-Agent:
```powershell
$env:SEC_USER_AGENT="Personal Research contact you@example.com"
```
```bash
# macOS/Linux
export SEC_USER_AGENT="Personal Research contact you@example.com"
```
실행:
```bash
streamlit run app.py
```

## 중요한 데이터 한계
- SEC XBRL 표준 태그만 사용하므로 주식기반보상, 발행주식 수, 현금이 일부 회사에서 누락될 수 있습니다.
- SBC/매출은 해당 분기 값끼리 비교하는 근사치이며, 기업별 공시 태그와 누적 현금흐름 표시 차이 때문에 오류가 발생할 수 있습니다.
- 현금 소진 기간은 과거 현금흐름이 미래에도 이어진다고 가정하는 단순 추정입니다. 분기별 변동성이 큰 회사에는 적합하지 않을 수 있습니다.
- 주식 수 비교는 관측값 간 비교이며, 분할·역분할·자사주 매입 등 기업행위를 완전히 조정하지 않습니다.
- 현재 한 번의 실행에서 분석하는 종목 수는 제한되며, 결과는 전체 시장 순위가 아닙니다.
- 시장 데이터는 yfinance 비공식 인터페이스입니다.
- 자동 점수는 매수/매도 추천이 아닙니다. 투자 전 원문 공시와 최신 데이터를 검증해야 합니다.

## 점수 구성(개략)
매출 성장 최대 20, 성장 가속도 15, 영업이익률 10, 영업손익 개선 10, 현금·현금흐름·runway 20, 희석/SBC 10, 시가총액·거래대금 10. 결측 데이터는 안전하다고 간주하지 않고 점수 및 경고로 처리합니다.

공식 SEC API 안내: https://www.sec.gov/edgar/sec-api-documentation


## v4: 품질검사 및 검증 프레임워크
- 단위 테스트(`test_screener.py`) 추가
- 연환산 매출 대비 시가총액 배수(P/S 근사치) 추가
- 점수 상한, 결측 데이터 처리, SIC 필터, 분기 기간 필터를 자동 테스트
- `backtest.py`에 point-in-time CSV 평가 뼈대 추가

테스트 실행:
```bash
python -m unittest test_screener.py -v
```

### 백테스트 입력 CSV 형식
`backtest.py`는 다음 열이 있는 **과거 시점 기준 데이터**를 입력으로 받습니다.
- `date`: 포트폴리오 구성 기준일
- `ticker`: 티커
- `score`: 해당 기준일 당시 계산된 점수
- `forward_return_pct`: 이후 측정 기간 수익률(%)

주의: 오늘의 재무 데이터를 과거 날짜에 붙이면 미래정보 편향이 생깁니다. 실제 백테스트에는 해당 날짜에 이미 공개된 SEC 공시만 사용해야 하며, 상장폐지 종목과 거래비용도 포함해야 합니다. 현재 `backtest.py`는 평가 뼈대이며, 실제 과거 공시 수집/생존편향 제거는 아직 구현하지 않았습니다.

점수 배점은 최대 100점 체계로 조정했지만, P/S는 시가총액을 최근 분기 매출의 4배로 나눈 근사치입니다. 계절성이 강한 기업이나 매출 변동이 큰 기업에는 왜곡될 수 있습니다.


## v5: 백테스트 평가기 강화
- 리밸런싱 날짜별 점수 상위 비중(top fraction) 동일가중 코호트 구성
- 수익률에서 단순 거래비용 가정(bps)을 차감한 순수익률 계산
- 벤치마크 수익률 열이 있으면 초과수익률 계산
- 누적 복리수익률, 코호트 승률, 최대 낙폭, 날짜별 결과 CSV와 선택 종목 CSV 저장
- `test_backtest.py` 테스트 추가
- `backtest_template_synthetic.csv`는 **테스트용 가상 데이터**이며 실제 수익률이 아님

### 백테스트 실행
```bash
python -m unittest test_screener.py test_backtest.py -v
python backtest.py backtest_template_synthetic.csv --top-fraction 0.20 --cost-bps 20 --out-prefix demo
```
입력 CSV 필수 열: `date,ticker,score,forward_return_pct`. `benchmark_return_pct`는 선택 열입니다. 벤치마크는 해당 날짜의 포트폴리오 수익률과 **동일한 기간**으로 맞춰야 합니다.

**중요:** 거래비용은 매 리밸런싱마다 적용하는 단순 가정이며 실제 회전율·스프레드 기반 계산이 아닙니다. 여러 날짜의 forward return 기간이 서로 겹치면 누적 복리수익률과 최대 낙폭은 실제 연속 투자 경로를 의미하지 않을 수 있습니다. 이 버전도 과거 시점 SEC 공시를 자동 재구성하지 않으며, 상장폐지 종목/생존편향을 자동 보정하지 않습니다. 따라서 샘플 CSV 결과를 투자 성과로 해석하면 안 됩니다.

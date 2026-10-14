import streamlit as st
import pandas as pd
from screener import run_screen

st.set_page_config(page_title="US Growth Stock Screener v5", page_icon="📈", layout="wide")
st.title("미국 성장주 발굴 시스템 · MVP v5")
st.caption("성장성 + 현금 소진 + 주식 희석 + 데이터 품질 점검")

with st.sidebar:
    st.header("분석 설정")
    scan_limit = st.number_input("분석 최대 기업 수", min_value=5, max_value=1500, value=50, step=25)
    min_market_cap = st.number_input("최소 시가총액 ($M)", min_value=0, value=300, step=50)
    min_adv = st.number_input("최소 20일 평균 거래대금 ($M)", min_value=0, value=2, step=1)
    min_growth = st.slider("매출 YoY 최소 성장률 (%)", -50, 200, 15)
    min_score = st.slider("최소 점수", 0, 100, 35)
    run_button = st.button("스크리닝 실행", type="primary", use_container_width=True)
    st.caption("SEC_USER_AGENT 환경변수가 필요합니다. 시장 데이터는 yfinance 기반으로 누락될 수 있습니다.")

st.markdown("""
### v3 분석 모듈
- **성장성:** 최근 분기 매출 YoY 및 성장 가속도
- **현금 여력:** 현금 잔액, 영업현금흐름, 추정 현금 소진 기간
- **희석 위험:** 발행주식 수 변화, 주식기반보상(SBC) 비중
- **경고 플래그:** 성장률 계산 불가, 현금 소진, 희석, 데이터 누락
""")

if run_button:
    with st.spinner("SEC 공시와 시장 데이터를 분석하고 있습니다."):
        try:
            df, errors, meta = run_screen(
                scan_limit=int(scan_limit),
                min_market_cap_m=float(min_market_cap),
                min_adv_m=float(min_adv),
                min_revenue_growth_pct=float(min_growth),
                min_score=int(min_score),
            )
            st.session_state["df"] = df
            st.session_state["errors"] = errors
            st.session_state["meta"] = meta
        except Exception as e:
            st.error(str(e))
            st.info("SEC_USER_AGENT 환경변수와 네트워크 연결을 확인하세요.")

if "df" in st.session_state:
    df, errors, meta = st.session_state["df"], st.session_state["errors"], st.session_state["meta"]
    a,b,c,d = st.columns(4)
    a.metric("유니버스 후보", f"{meta['universe_count']:,}")
    b.metric("분석 시도", f"{meta['scanned']:,}")
    c.metric("결과 종목", f"{len(df):,}")
    d.metric("수집 오류", f"{len(errors):,}")
    if meta["limited"]:
        st.warning("분석 건수 제한이 적용되어 있습니다. 결과는 전체 시장 순위가 아닙니다.")
    cols = ["ticker","name","score","revenue_growth_yoy_pct","revenue_acceleration_pp",
            "cash_runway_months","shares_outstanding_yoy_pct","sbc_to_revenue_pct","price_to_sales_annualized",
            "market_cap_m","avg_dollar_volume_20d_m","risk_flags","filing_url"]
    cols = [x for x in cols if x in df.columns]
    st.subheader("성장주 후보 목록")
    st.dataframe(df[cols], use_container_width=True, hide_index=True,
        column_config={"filing_url": st.column_config.LinkColumn("SEC 공시", display_text="열기")})
    st.download_button("CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                       "us_growth_candidates_v3.csv", "text/csv")
    if len(df):
        ticker = st.selectbox("상세 분석 종목", df["ticker"].tolist())
        row = df[df["ticker"] == ticker].iloc[0]
        st.subheader(f"{ticker} · {row['name']}")
        left, right = st.columns(2)
        with left:
            st.markdown("**핵심 재무 지표**")
            for k in ["score","revenue_growth_yoy_pct","revenue_acceleration_pp","operating_margin_pct",
                      "cash_and_equivalents_m","operating_cash_flow_m","cash_runway_months",
                      "shares_outstanding_yoy_pct","sbc_to_revenue_pct","price_to_sales_annualized"]:
                if k in row.index: st.write(f"**{k}**: {row[k]}")
        with right:
            st.markdown("**위험 플래그**")
            st.write(row.get("risk_flags","—"))
            st.markdown(f"[최신 SEC 정기보고서]({row.get('filing_url','https://www.sec.gov/edgar/search/')})")
    if errors:
        with st.expander("수집 오류"):
            st.write(errors)
else:
    st.info("왼쪽 설정을 확인하고 스크리닝을 실행하세요.")

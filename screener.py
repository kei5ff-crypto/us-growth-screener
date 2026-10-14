import os, time, json, re, hashlib
from pathlib import Path
import requests
import pandas as pd

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_BASE = "https://data.sec.gov"
CACHE_DIR = Path("cache_sec")
CACHE_DIR.mkdir(exist_ok=True)
FINANCIAL_SIC_RANGES = [(6000,6799)]
REAL_ESTATE_SIC_RANGES = [(6500,6599),(6798,6799)]

def _session():
    ua=os.getenv("SEC_USER_AGENT","").strip()
    if not ua or "@" not in ua:
        raise RuntimeError("SEC_USER_AGENT 환경변수를 설정하세요. 예: Personal Research contact you@example.com")
    s=requests.Session(); s.headers.update({"User-Agent":ua,"Accept-Encoding":"gzip, deflate"})
    return s

def _cache_path(url): return CACHE_DIR/(hashlib.sha256(url.encode()).hexdigest()+".json")

def _get_json(session,url,max_age_hours=24,tries=4):
    p=_cache_path(url)
    if p.exists() and time.time()-p.stat().st_mtime < max_age_hours*3600:
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    for i in range(tries):
        try:
            r=session.get(url,timeout=30)
            if r.status_code==429 or r.status_code>=500:
                time.sleep(1.5*(i+1)); continue
            r.raise_for_status(); data=r.json()
            p.write_text(json.dumps(data),encoding="utf-8")
            time.sleep(.12); return data
        except Exception:
            if i==tries-1: raise
            time.sleep(1.5*(i+1))
    raise RuntimeError("SEC API 재시도 초과")

def load_universe(session):
    r=session.get(SEC_TICKERS_URL,timeout=30); r.raise_for_status()
    payload=r.json()
    df=pd.DataFrame(payload.get("data",[]),columns=payload.get("fields",[]))
    df.columns=[str(c).lower() for c in df.columns]
    if not {"cik","name","ticker","exchange"}.issubset(df.columns):
        raise RuntimeError(f"SEC 티커 파일 구조가 예상과 다릅니다: {list(df.columns)}")
    df["cik"]=pd.to_numeric(df["cik"],errors="coerce"); df=df.dropna(subset=["cik"]).copy(); df["cik"]=df["cik"].astype(int)
    df["ticker"]=df["ticker"].astype(str).str.upper().str.strip()
    df["exchange"]=df["exchange"].fillna("").astype(str).str.upper()
    bad=re.compile(r"(\.WS$|\.WT$|\.U$|\.RT$|\.PR[A-Z]?$|[-/]P$|^TEST$)")
    df=df[~df["ticker"].str.contains(bad,na=False)]
    df=df[df["exchange"].isin(["NASDAQ","NYSE","NYSE AMERICAN","NYSE ARCA","CBOE"])]
    return df.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)

def _in_ranges(sic,ranges):
    try: n=int(sic); return any(a<=n<=b for a,b in ranges)
    except Exception: return False

def _duration_facts(cf,tags,units=("USD",)):
    facts=cf.get("facts",{})
    for taxonomy in ("us-gaap","ifrs-full"):
        tax=facts.get(taxonomy,{})
        for tag in tags:
            item=tax.get(tag)
            if not item: continue
            for unit in units:
                vals=[]
                for e in item.get("units",{}).get(unit,[]):
                    if e.get("form") not in ("10-Q","10-K","20-F","40-F") or not e.get("end"): continue
                    start=e.get("start")
                    if start:
                        try:
                            days=(pd.Timestamp(e["end"])-pd.Timestamp(start)).days
                            if not 45<=days<=120: continue
                        except Exception: continue
                    vals.append({"end":e["end"],"filed":e.get("filed",""),"val":e.get("val"),"start":start,"form":e.get("form")})
                if vals:
                    d=pd.DataFrame(vals).sort_values(["end","filed"]).drop_duplicates("end",keep="last")
                    d["val"]=pd.to_numeric(d["val"],errors="coerce")
                    return d.dropna(subset=["val"]).sort_values("end").reset_index(drop=True)
    return pd.DataFrame()

def _instant_series(cf,tags,units=("USD",)):
    facts=cf.get("facts",{})
    for taxonomy in ("us-gaap","ifrs-full"):
        for tag in tags:
            item=facts.get(taxonomy,{}).get(tag)
            if not item: continue
            vals=[]
            for unit in units:
                vals += [e for e in item.get("units",{}).get(unit,[]) if e.get("end") and e.get("form") in ("10-Q","10-K","20-F","40-F")]
            if vals:
                d=pd.DataFrame(vals).sort_values(["end","filed"]).drop_duplicates("end",keep="last")
                d["val"]=pd.to_numeric(d["val"],errors="coerce")
                return d.dropna(subset=["val"]).sort_values("end").reset_index(drop=True)
    return pd.DataFrame()

def _latest(cf,tags):
    d=_instant_series(cf,tags)
    return float(d.iloc[-1]["val"]) if not d.empty else None

def _market(ticker):
    try:
        import yfinance as yf
        t=yf.Ticker(ticker); info=t.get_info(); hist=t.history(period="1mo",auto_adjust=False)
        mc=info.get("marketCap"); adv=None; price=None
        if hist is not None and not hist.empty:
            adv=float((hist["Close"]*hist["Volume"]).tail(20).mean()/1e6); price=float(hist["Close"].iloc[-1])
        return {"market_cap_m":float(mc)/1e6 if mc else None,"avg_dollar_volume_20d_m":adv,"price":price}
    except Exception:
        return {"market_cap_m":None,"avg_dollar_volume_20d_m":None,"price":None}

def _score(growth,accel,margin,op_improve,cash,ocf,runway,share_change,sbc_ratio,mc,adv,price_to_sales=None):
    growth_pts=0 if growth is None else max(0,min(20,growth/40*20))
    accel_pts=0 if accel is None else max(0,min(15,(accel+10)/30*15))
    margin_pts=0 if margin is None else max(0,min(10,(margin+20)/4))
    op_pts=10 if op_improve is True else (3 if op_improve is False else 0)
    cash_pts=0
    if cash is not None and cash>0: cash_pts+=5
    if ocf is not None and ocf>0: cash_pts+=5
    if runway is not None:
        cash_pts += 10 if runway>=24 else (7 if runway>=12 else (3 if runway>=6 else 0))
    dilution_pts=10
    if share_change is None: dilution_pts=3
    elif share_change>10: dilution_pts=0
    elif share_change>5: dilution_pts=3
    elif share_change>2: dilution_pts=6
    if sbc_ratio is None: dilution_pts=max(0,dilution_pts-3)
    elif sbc_ratio>20: dilution_pts=max(0,dilution_pts-7)
    elif sbc_ratio>10: dilution_pts=max(0,dilution_pts-4)
    liq_pts=(5 if mc is not None and mc>=300 else 0)+(5 if adv is not None and adv>=2 else 0)
    # Rough price-to-sales proxy (market cap / latest quarterly revenue annualized).
    # This is not EV/Sales and should be interpreted cautiously for seasonal companies.
    val_pts=0 if price_to_sales is None else (5 if price_to_sales<=5 else (3 if price_to_sales<=10 else (1 if price_to_sales<=20 else 0)))
    return round(min(100,growth_pts+accel_pts+margin_pts+op_pts+cash_pts+dilution_pts+liq_pts+val_pts),1)

def analyze(row,session):
    cik=int(row["cik"]); ticker=row["ticker"]; name=row["name"]
    sub=_get_json(session,f"{SEC_BASE}/submissions/CIK{cik:010d}.json")
    sic=sub.get("sic")
    cf=_get_json(session,f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json")
    rev=_duration_facts(cf,["RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet","Revenues","RevenueFromContractWithCustomerIncludingAssessedTax"])
    op=_duration_facts(cf,["OperatingIncomeLoss"])
    ocf=_duration_facts(cf,["NetCashProvidedByUsedInOperatingActivities"])
    sbc=_duration_facts(cf,["ShareBasedCompensation"])
    shares=_instant_series(cf,["EntityCommonStockSharesOutstanding"],units=("shares",))
    cash=_latest(cf,["CashAndCashEquivalentsAtCarryingValue","CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"])
    market=_market(ticker)
    growth=accel=margin=None; op_improve=None; latest_rev=latest_ocf=None; runway=None; share_change=sbc_ratio=None
    if len(rev):
        latest_rev=float(rev.iloc[-1]["val"])
        if len(rev)>=5 and float(rev.iloc[-5]["val"])>0:
            growth=(latest_rev/float(rev.iloc[-5]["val"])-1)*100
        if len(rev)>=6 and float(rev.iloc[-6]["val"])>0 and len(rev)>=5 and float(rev.iloc[-5]["val"])>0:
            prior_growth=(float(rev.iloc[-2]["val"])/float(rev.iloc[-6]["val"])-1)*100
            if growth is not None: accel=growth-prior_growth
    if len(op) and latest_rev and latest_rev>0:
        margin=float(op.iloc[-1]["val"])/latest_rev*100
        if len(op)>=5: op_improve=float(op.iloc[-1]["val"])>float(op.iloc[-5]["val"])
    if len(ocf): latest_ocf=float(ocf.iloc[-1]["val"])
    # Runway estimate uses latest cash / average quarterly negative operating cash flow over up to 4 quarters.
    if cash is not None and len(ocf):
        recent_ocf=ocf.tail(4)["val"].astype(float)
        burn=max(0.0,-float(recent_ocf.mean()))
        if burn>0: runway=cash/burn*3.0
        elif cash>0 and latest_ocf is not None and latest_ocf>=0: runway=999.0
    if len(shares)>=5:
        now=float(shares.iloc[-1]["val"]); prior=float(shares.iloc[-5]["val"])
        if prior>0: share_change=(now/prior-1)*100
    if len(sbc) and latest_rev and latest_rev>0:
        sbc_ratio=float(sbc.iloc[-1]["val"])/latest_rev*100
    score=_score(growth,accel,margin,op_improve,cash,latest_ocf,runway,share_change,sbc_ratio,
                 market["market_cap_m"],market["avg_dollar_volume_20d_m"])
    risks=[]
    if growth is None: risks.append("매출 YoY 계산 불가")
    if accel is None: risks.append("성장 가속도 데이터 부족")
    if cash is None: risks.append("현금 데이터 누락")
    if runway is not None and runway<12: risks.append("현금 소진 기간 12개월 미만 추정")
    if latest_ocf is not None and latest_ocf<0: risks.append("최근 분기 영업현금흐름 적자")
    if share_change is not None and share_change>5: risks.append("발행주식 수 YoY 5% 초과 증가")
    if sbc_ratio is not None and sbc_ratio>10: risks.append("SBC/매출 10% 초과")
    if market["market_cap_m"] is None: risks.append("시가총액 데이터 누락")
    if market["avg_dollar_volume_20d_m"] is None: risks.append("거래대금 데이터 누락")
    recent=sub.get("filings",{}).get("recent",{})
    filing_url=f"https://www.sec.gov/edgar/search/#/ciks={cik}"
    candidates=[]
    for i,form in enumerate(recent.get("form",[])):
        dates=recent.get("filingDate",[]); accns=recent.get("accessionNumber",[]); docs=recent.get("primaryDocument",[])
        if form in ("10-Q","10-K","20-F","40-F") and i<len(dates) and i<len(accns) and i<len(docs):
            candidates.append((dates[i],accns[i],docs[i]))
    if candidates:
        _,accn,doc=sorted(candidates,reverse=True)[0]
        filing_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-','')}/{doc}"
    return {"ticker":ticker,"name":name,"sic":sic,"score":score,
        "revenue_growth_yoy_pct":round(growth,2) if growth is not None else None,
        "revenue_acceleration_pp":round(accel,2) if accel is not None else None,
        "latest_revenue_m":round(latest_rev/1e6,2) if latest_rev is not None else None,
        "operating_margin_pct":round(margin,2) if margin is not None else None,
        "cash_and_equivalents_m":round(cash/1e6,2) if cash is not None else None,
        "operating_cash_flow_m":round(latest_ocf/1e6,2) if latest_ocf is not None else None,
        "cash_runway_months":round(runway,1) if runway is not None else None,
        "shares_outstanding_yoy_pct":round(share_change,2) if share_change is not None else None,
        "price_to_sales_annualized":round(price_to_sales,2) if price_to_sales is not None else None,
        "sbc_to_revenue_pct":round(sbc_ratio,2) if sbc_ratio is not None else None,
        "market_cap_m":market["market_cap_m"],"avg_dollar_volume_20d_m":market["avg_dollar_volume_20d_m"],
        "price":market["price"],"risk_flags":"; ".join(risks) if risks else "주요 자동 플래그 없음",
        "filing_url":filing_url}

def run_screen(scan_limit=50,min_market_cap_m=300,min_adv_m=2,min_revenue_growth_pct=15,min_score=35):
    session=_session(); universe=load_universe(session); universe_count=len(universe)
    candidates=universe.head(int(scan_limit)).copy()
    results=[]; errors=[]
    for _,row in candidates.iterrows():
        try:
            item=analyze(row,session)
            if _in_ranges(item.get("sic"),FINANCIAL_SIC_RANGES+REAL_ESTATE_SIC_RANGES): continue
            mc,adv,growth=item["market_cap_m"],item["avg_dollar_volume_20d_m"],item["revenue_growth_yoy_pct"]
            if mc is not None and mc<min_market_cap_m: continue
            if adv is not None and adv<min_adv_m: continue
            if growth is not None and growth<min_revenue_growth_pct: continue
            if item["score"]<min_score: continue
            results.append(item)
        except Exception as e: errors.append(f"{row.get('ticker','?')}: {str(e)[:200]}")
    df=pd.DataFrame(results)
    if not df.empty: df=df.sort_values(["score","revenue_growth_yoy_pct"],ascending=False,na_position="last").reset_index(drop=True)
    return df,errors,{"universe_count":universe_count,"scanned":len(candidates),"limited":len(candidates)<universe_count}

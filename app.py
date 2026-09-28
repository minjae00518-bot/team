import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import re
from datetime import datetime, timedelta
from collections import Counter

# 페이지 설정
st.set_page_config(
    page_title="5조 - 급식 데이터 비교 분석 앱",
    page_icon="🍱",
    layout="wide"
)

# ---------------------------------------------------------
# API Key (필요시 입력)
# ---------------------------------------------------------
NEIS_KEY = ""

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_school_info(school_name):
    """학교 기본 정보 조회"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {"Type": "json", "SCHUL_NM": school_name}
    if NEIS_KEY:
        params["KEY"] = NEIS_KEY
    try:
        res = requests.get(url, params=params, timeout=10).json()
        if "schoolInfo" in res:
            return res["schoolInfo"][1]["row"]
    except Exception:
        pass
    return []

def fetch_meal_single_request(ofcdc_code, school_code, from_ymd, to_ymd):
    """단일 급식 API 요청"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": ofcdc_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",  # 중식
        "MLSV_FROM_YMD": from_ymd,
        "MLSV_TO_YMD": to_ymd,
        "pSize": 1000
    }
    if NEIS_KEY:
        params["KEY"] = NEIS_KEY
    try:
        res = requests.get(url, params=params, timeout=10).json()
        if "mealServiceDietInfo" in res:
            return res["mealServiceDietInfo"][1]["row"]
    except Exception:
        pass
    return []

@st.cache_data(ttl=3600)
def fetch_full_year_meals(ofcdc_code, school_code, start_ymd, end_ymd):
    """월별 분할 호출로 전체 데이터 확보"""
    if NEIS_KEY:
        return fetch_meal_single_request(ofcdc_code, school_code, start_ymd, end_ymd)
    
    all_rows = []
    start_dt = datetime.strptime(start_ymd, "%Y%m%d")
    end_dt = datetime.strptime(end_ymd, "%Y%m%d")
    
    curr = start_dt
    while curr <= end_dt:
        m_start = curr.strftime("%Y%m01")
        if curr.month == 12:
            next_m = datetime(curr.year + 1, 1, 1)
        else:
            next_m = datetime(curr.year, curr.month + 1, 1)
        
        m_end_dt = next_m - timedelta(days=1)
        if m_end_dt > end_dt:
            m_end_dt = end_dt
        m_end = m_end_dt.strftime("%Y%m%d")
        
        rows = fetch_meal_single_request(ofcdc_code, school_code, m_start, m_end)
        if rows:
            all_rows.extend(rows)
            
        curr = next_m
        
    return all_rows

def clean_menu_item(item):
    """괄호 안 알레르기/원산지/영양표시 제거 및 특수문자 정제"""
    if not item:
        return ""
    item = re.sub(r'\(.*?\)', '', item)
    item = re.sub(r'[*.:@#$%\^&;`~]', '', item)
    item = re.sub(r'\s+', ' ', item).strip()
    return item

def parse_calories(cal_str):
    """칼로리 수치 추출 및 비정상 수치 필터링"""
    if not cal_str:
        return None
    match = re.search(r'[\d.]+', str(cal_str))
    if match:
        val = float(match.group())
        if 200 <= val <= 2000:
            return val
    return None

# ---------------------------------------------------------
# UI 레이아웃
# ---------------------------------------------------------
st.title("🍱 학교 급식 데이터 비교 분석")
st.caption("5조 프로젝트 - NEIS 급식 API 데이터 기반 시각화")

st.sidebar.header("⚙️ 분석 설정")

year_option = st.sidebar.selectbox("조회 대상 학년도", ["2025학년도 (2025.03 ~)", "2024학년도 (2024.03 ~ 2025.02)"])
if "2025" in year_option:
    start_date = "20250301"
    end_date = datetime.now().strftime("%Y%m%d")
else:
    start_date = "20240301"
    end_date = "20250228"

real_schools = [
    "송탄고등학교",
    "효명고등학교",
    "라온고등학교",
    "평택고등학교",
    "신한고등학교",
    "비전고등학교"
]

selected_schools = st.sidebar.multiselect(
    "비교할 학교를 선택하세요 (기본: 송탄고등학교 포함):",
    options=real_schools,
    default=["송탄고등학교", "효명고등학교", "라온고등학교"]
)

filter_basic = st.sidebar.checkbox("Top 5 분석 시 기본 반찬(밥/김치류) 제외하기", value=True)
basic_keywords = ["김치", "밥", "깍두기", "쌀밥", "현미밥", "잡곡밥", "알타리"]

if len(selected_schools) < 3:
    st.warning("⚠️ 정확한 비교 분석을 위해 최소 3개 이상의 학교를 선택해 주세요!")

# ---------------------------------------------------------
# 데이터 수집 및 처리
# ---------------------------------------------------------
if selected_schools:
    all_meals = []
    all_menus = {}

    with st.spinner("데이터 분석 중..."):
        for school_name in selected_schools:
            info = fetch_school_info(school_name)
            if not info:
                st.error(f"'{school_name}' 정보를 NEIS에서 찾지 못했습니다.")
                continue
            
            ofcdc_code = info[0]["ATPT_OFCDC_SC_CODE"]
            school_code = info[0]["SD_SCHUL_CODE"]
            
            meal_rows = fetch_full_year_meals(ofcdc_code, school_code, start_date, end_date)
            school_menu_list = []
            
            for row in meal_rows:
                cal_val = parse_calories(row.get("CAL_INFO", ""))
                ymd = row.get("MLSV_YMD", "")
                year_month = f"{ymd[:4]}-{ymd[4:6]}" if len(ymd) == 8 else "미상"
                
                if cal_val:
                    all_meals.append({
                        "학교명": school_name,
                        "날짜": ymd,
                        "연월": year_month,
                        "칼로리": cal_val
                    })
                
                raw_ddish = row.get("DDISH_NM", "")
                if raw_ddish:
                    items = raw_ddish.split("<br/>")
                    for item in items:
                        cleaned = clean_menu_item(item)
                        if len(cleaned) > 1:
                            if filter_basic and any(k in cleaned for k in basic_keywords):
                                continue
                            school_menu_list.append(cleaned)
            
            all_menus[school_name] = school_menu_list

    df_meals = pd.DataFrame(all_meals)

    if not df_meals.empty:
        # ---------------------------------------------------------
        # 1. 평균 칼로리 지표
        # ---------------------------------------------------------
        st.subheader("📊 학교별 평균 칼로리 요약")
        avg_cal_df = df_meals.groupby("학교명")["칼로리"].mean().round(1).reset_index()
        avg_cal_df.columns = ["학교명", "평균 칼로리(kcal)"]

        cols = st.columns(len(selected_schools))
        for idx, school in enumerate(selected_schools):
            s_df = df_meals[df_meals["학교명"] == school]
            if not s_df.empty:
                val = round(s_df["칼로리"].mean(), 1)
                cols[idx % len(cols)].metric(
                    label=f"🏫 {school}",
                    value=f"{val} kcal"
                )

        st.markdown("---")

        # ---------------------------------------------------------
        # 2. Plotly 시각화
        # ---------------------------------------------------------
        st.subheader("📈 칼로리 시각화 분석")
        tab1, tab2 = st.tabs(["월별 평균 칼로리 추이 (선 그래프)", "전체 기간 평균 칼로리 비교 (막대 그래프)"])

        with tab1:
            monthly_avg = df_meals.groupby(["학교명", "연월"])["칼로리"].mean().round(1).reset_index()
            fig_line = px.line(
                monthly_avg,
                x="연월",
                y="칼로리",
                color="학교명",
                markers=True,
                title="월별 평균 칼로리 변화 추이",
                labels={"연월": "조회 월", "칼로리": "평균 칼로리 (kcal)"}
            )
            fig_line.update_layout(hovermode="x unified")
            st.plotly_chart(fig_line, use_container_width=True)

        with tab2:
            fig_bar = px.bar(
                avg_cal_df,
                x="학교명",
                y="평균 칼로리(kcal)",
                color="학교명",
                text="평균 칼로리(kcal)",
                title="전체 기간 평균 칼로리 비교",
                labels={"평균 칼로리(kcal)": "평균 칼로리 (kcal)"}
            )
            fig_bar.update_traces(texttemplate='%{text} kcal', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # 3. Top 5 메뉴 분석
        # ---------------------------------------------------------
        st.subheader("🏆 학교별 가장 많이 나온 메뉴 Top 5")
        menu_cols = st.columns(len(selected_schools))
        
        for idx, school in enumerate(selected_schools):
            with menu_cols[idx % len(menu_cols)]:
                st.markdown(f"#### 🏫 {school}")
                m_list = all_menus.get(school, [])
                if m_list:
                    top5 = Counter(m_list).most_common(5)
                    df_top5 = pd.DataFrame(top5, columns=["메뉴명", "등장 횟수"])
                    df_top5.index = range(1, len(df_top5) + 1)
                    st.dataframe(df_top5, use_container_width=True)
                else:
                    st.info("메뉴 데이터가 없습니다.")

    else:
        st.error("급식 데이터를 불러올 수 없습니다. 기간 및 학교 선택을 확인해 주세요.")

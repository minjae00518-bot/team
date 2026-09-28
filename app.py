import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import re
from datetime import datetime
from collections import Counter

# Page Configuration
st.set_page_config(
    page_title="5조 - 학교 급식 데이터 분석",
    page_icon="🍱",
    layout="wide"
)

# ---------------------------------------------------------
# API Helper Functions (Cached for better performance)
# ---------------------------------------------------------
NEIS_KEY = "" # API 키 없이도 하루 기본 제한 내 요청 가능 (필요 시 부여받은 키 입력)

@st.cache_data(ttl=3600)
def fetch_school_info(school_name):
    """학교 이름을 검색하여 교육청 코드와 학교 코드를 가져오는 함수"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {
        "Type": "json",
        "SCHUL_NM": school_name
    }
    if NEIS_KEY:
        params["KEY"] = NEIS_KEY

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "schoolInfo" in data:
            rows = data["schoolInfo"][1]["row"]
            return rows
    except Exception as e:
        st.error(f"학교 정보 조회 중 오류가 발생했습니다: {e}")
    return []

@st.cache_data(ttl=3600)
def fetch_meal_data(ofcdc_code, school_code, from_ymd, to_ymd):
    """특정 학교의 중식 데이터를 가져오는 함수"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": ofcdc_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",  # 2: 중식
        "MLSV_FROM_YMD": from_ymd,
        "MLSV_TO_YMD": to_ymd,
        "pSize": 1000
    }
    if NEIS_KEY:
        params["KEY"] = NEIS_KEY

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if "mealServiceDietInfo" in data:
            return data["mealServiceDietInfo"][1]["row"]
    except Exception as e:
        st.error(f"급식 데이터 조회 중 오류가 발생했습니다: {e}")
    return []

def clean_menu_item(item):
    """메뉴명에서 괄호 안 알레르기 번호 및 특수문자 제거"""
    # 괄호 안 알레르기 번호 제거 (예: (1.2.5.6) -> "")
    item = re.sub(r'\(.*?\)', '', item)
    # 수식어/공백 정리
    item = re.sub(r'\s+', ' ', item).strip()
    return item

def parse_calories(cal_str):
    """'685.2 Kcal' 형태의 문자열에서 실수 숫자만 추출"""
    if not cal_str:
        return None
    match = re.search(r'[\d.]+', str(cal_str))
    return float(match.group()) if match else None

# ---------------------------------------------------------
# Streamlit UI Layout
# ---------------------------------------------------------
st.title("🍱 우리 학교 vs 근처 학교 급식 데이터 비교 분석")
st.caption("2025년 3월부터 현재까지의 중식 데이터를 바탕으로 칼로리와 인기 메뉴를 분석합니다.")

# 사이드바 - 기본 학교 및 학교 추가 검색
st.sidebar.header("🔍 학교 선택 및 검색")

# 기본 비교 대상 목록
default_preset_schools = [
    "송탄고등학교",
    "효명고등학교",
    "태법고등학교",
    "평택고등학교",
    "신한고등학교"
]

# 새로 검색해서 추가할 학교
search_query = st.sidebar.text_input("목록에 없는 학교 검색 (예: 은혜고등학교)", "")
if search_query:
    searched_results = fetch_school_info(search_query)
    if searched_results:
        for r in searched_results:
            nm = r["SCHUL_NM"]
            if nm not in default_preset_schools:
                default_preset_schools.append(nm)
        st.sidebar.success(f"검색 결과가 선택 목록에 추가되었습니다!")
    else:
        st.sidebar.warning("검색 결과가 없습니다.")

# [필수 요구사항 1] 멀티 셀렉트 (송탄고등학교 기본값)
selected_schools = st.sidebar.multiselect(
    "비교할 학교를 3개 이상 선택하세요:",
    options=default_preset_schools,
    default=["송탄고등학교", "효명고등학교", "평택고등학교"]
)

if len(selected_schools) < 3:
    st.warning("⚠️ 정확한 비교 분석을 위해 최소 3개 이상의 학교를 선택해 주세요!")

# 데이터 조회 기간 설정 (2025년 3월 1일 ~ 오늘)
start_date = "20250301"
end_date = datetime.now().strftime("%Y%m%d")

# ---------------------------------------------------------
# Data Fetching & Processing
# ---------------------------------------------------------
if selected_schools:
    all_meals = []
    all_menus = {}

    with st.spinner("NEIS API에서 급식 데이터를 불러오는 중입니다..."):
        for school_name in selected_schools:
            school_info = fetch_school_info(school_name)
            if not school_info:
                st.error(f"'{school_name}'의 정보를 찾지 못했습니다.")
                continue
            
            # 검색 결과 중 첫번째 학교 사용
            info = school_info[0]
            ofcdc_code = info["ATPT_OFCDC_SC_CODE"]
            school_code = info["SD_SCHUL_CODE"]
            
            meal_rows = fetch_meal_data(ofcdc_code, school_code, start_date, end_date)
            
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
                
                # 메뉴 처리
                raw_ddish = row.get("DDISH_NM", "")
                if raw_ddish:
                    items = raw_ddish.split("<br/>")
                    for item in items:
                        cleaned = clean_menu_item(item)
                        if cleaned and len(cleaned) > 1:  # 단어 길이 2 이상만 수집
                            school_menu_list.append(cleaned)
            
            all_menus[school_name] = school_menu_list

    df_meals = pd.DataFrame(all_meals)

    if not df_meals.empty:
        # ---------------------------------------------------------
        # Section 1: 요약 메트릭
        # ---------------------------------------------------------
        st.subheader("📊 1년간 급식 평균 칼로리 요약")
        avg_cal_by_school = df_meals.groupby("학교명")["칼로리"].mean().round(1).reset_index()
        avg_cal_by_school.columns = ["학교명", "평균 칼로리(kcal)"]

        cols = st.columns(len(selected_schools))
        for idx, school in enumerate(selected_schools):
            school_cal = avg_cal_by_school[avg_cal_by_school["학교명"] == school]
            if not school_cal.empty:
                val = school_cal["평균 칼로리(kcal)"].values[0]
                cols[idx % len(cols)].metric(label=school, value=f"{val} kcal")

        st.markdown("---")

        # ---------------------------------------------------------
        # Section 2: [필수 요구사항 3] Plotly 그래프 시각화
        # ---------------------------------------------------------
        tab1, tab2 = st.tabs(["📈 월별 평균 칼로리 추이", "📊 전체 기간 평균 칼로리 비교"])

        with tab1:
            st.markdown("### 학교별 월별 평균 칼로리 변화 추이")
            monthly_avg = df_meals.groupby(["학교명", "연월"])["칼로리"].mean().round(1).reset_index()
            
            fig_line = px.line(
                monthly_avg,
                x="연월",
                y="칼로리",
                color="학교명",
                markers=True,
                title="2025년 3월 이후 월별 평균 칼로리 변화",
                labels={"연월": "조회 월", "칼로리": "평균 칼로리 (kcal)"}
            )
            fig_line.update_layout(hovermode="x unified")
            st.plotly_chart(fig_line, use_container_width=True)

        with tab2:
            st.markdown("### 학교별 전체 기간 평균 칼로리 비교")
            fig_bar = px.bar(
                avg_cal_by_school,
                x="학교명",
                y="평균 칼로리(kcal)",
                color="학교명",
                text="평균 칼로리(kcal)",
                title="선택한 학교들의 전체 기간 평균 칼로리 비교",
                labels={"평균 칼로리(kcal)": "평균 칼로리 (kcal)"}
            )
            fig_bar.update_traces(texttemplate='%{text} kcal', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # ---------------------------------------------------------
        # Section 3: [필수 요구사항 4] 학교별 가장 많이 나온 메뉴 Top 5
        # ---------------------------------------------------------
        st.subheader("🏆 학교별 1년간 가장 많이 나온 메뉴 (Top 5)")
        st.caption("알레르기 정보 번호(예: 1.2.5)를 제거한 후 메뉴별 등판 횟수를 집계했습니다.")

        menu_cols = st.columns(len(selected_schools))
        for idx, school in enumerate(selected_schools):
            with menu_cols[idx % len(menu_cols)]:
                st.markdown(f"#### 🏫 {school}")
                menus = all_menus.get(school, [])
                if menus:
                    counter = Counter(menus)
                    top5 = counter.most_common(5)
                    df_top5 = pd.DataFrame(top5, columns=["메뉴명", "등장 횟수"])
                    df_top5.index = range(1, len(df_top5) + 1)
                    st.dataframe(df_top5, use_container_width=True)
                else:
                    st.info("메뉴 정보가 없습니다.")

    else:
        st.error("해당 기간의 급식 데이터를 불러오지 못했습니다.")

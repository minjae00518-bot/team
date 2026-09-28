import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import re
from datetime import datetime
from collections import Counter

st.set_page_config(page_title="5조 - 학교 급식 데이터 분석", page_icon="🍱", layout="wide")

# ---------------------------------------------------------
# [중요] NEIS API 키 설정
# open.neis.go.kr 에서 무료 발급받은 인증키를 아래에 넣으세요.
# 인증키가 없으면 API 제약으로 인해 최근 5일치 데이터만 조회됩니다.
# ---------------------------------------------------------
NEIS_KEY = ""  # 예: "7d11d4f9fde146f29d72b4d314ba3c27"

@st.cache_data(ttl=3600)
def fetch_school_info(school_name):
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

@st.cache_data(ttl=3600)
def fetch_meal_data(ofcdc_code, school_code, from_ymd, to_ymd):
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

def clean_menu_item(item):
    """알레르기 번호, 특수문자, 원산지 표기 등 제거"""
    item = re.sub(r'\(.*?\)', '', item)  # 괄호 안 알레르기 번호 제거
    item = re.sub(r'[*.:@#]', '', item)  # 특수문자 제거
    item = re.sub(r'\s+', ' ', item).strip()
    return item

def parse_calories(cal_str):
    if not cal_str:
        return None
    match = re.search(r'[\d.]+', str(cal_str))
    if match:
        val = float(match.group())
        return val if val > 100 else None  # 100kcal 이하 비정상 데이터 제외
    return None

# UI 구성
st.title("🍱 우리 학교 vs 근처 학교 급식 데이터 비교 분석")

if not NEIS_KEY:
    st.warning("⚠️ **NEIS API 인증키가 설정되지 않았습니다.** 인증키 없이 조회 시 API 제약에 따라 **학교당 최근 5일치 데이터만 조회**되어 통계가 불정확할 수 있습니다.")

st.sidebar.header("🔍 학교 선택")
default_preset_schools = ["송탄고등학교", "효명고등학교", "태법고등학교", "평택고등학교", "신한고등학교"]

selected_schools = st.sidebar.multiselect(
    "비교할 학교를 선택하세요 (최소 3개 권장):",
    options=default_preset_schools,
    default=["송탄고등학교", "효명고등학교", "평택고등학교"]
)

# 기본 반찬 제외 옵션 (밥, 김치 제외 기능)
filter_basic_side = st.sidebar.checkbox("자주 나오는 기본 반찬(밥/김치류) 제외하고 메뉴 분석", value=True)
basic_keywords = ["김치", "밥", "깍두기", "쌀밥", "현미밥", "잡곡밥"]

start_date = "20250301"
end_date = datetime.now().strftime("%Y%m%d")

if selected_schools:
    all_meals = []
    all_menus = {}

    with st.spinner("데이터를 분석하는 중입니다..."):
        for school_name in selected_schools:
            info = fetch_school_info(school_name)
            if not info:
                continue
            
            ofcdc_code = info[0]["ATPT_OFCDC_SC_CODE"]
            school_code = info[0]["SD_SCHUL_CODE"]
            
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
                
                raw_ddish = row.get("DDISH_NM", "")
                if raw_ddish:
                    items = raw_ddish.split("<br/>")
                    for item in items:
                        cleaned = clean_menu_item(item)
                        if len(cleaned) > 1:
                            # 기본 반찬 제외 옵션 적용
                            if filter_basic_side and any(k in cleaned for k in basic_keywords):
                                continue
                            school_menu_list.append(cleaned)
            
            all_menus[school_name] = school_menu_list

    df_meals = pd.DataFrame(all_meals)

    if not df_meals.empty:
        # 1. 수집된 데이터 건수 확인
        st.info(f"💡 총 **{len(df_meals)}일치** 급식 데이터를 기반으로 분석했습니다.")

        # 2. 평균 칼로리 요약
        st.subheader("📊 학교별 평균 칼로리")
        avg_cal_by_school = df_meals.groupby("학교명")["칼로리"].mean().round(1).reset_index()
        avg_cal_by_school.columns = ["학교명", "평균 칼로리(kcal)"]

        cols = st.columns(len(selected_schools))
        for idx, school in enumerate(selected_schools):
            school_df = df_meals[df_meals["학교명"] == school]
            if not school_df.empty:
                val = round(school_df["칼로리"].mean(), 1)
                cnt = len(school_df)
                cols[idx % len(cols)].metric(label=school, value=f"{val} kcal", delta=f"총 {cnt}일 데이터")

        st.markdown("---")

        # 3. Plotly 그래프
        tab1, tab2 = st.tabs(["📈 월별 평균 칼로리 추이", "📊 전체 기간 평균 비교"])

        with tab1:
            monthly_avg = df_meals.groupby(["학교명", "연월"])["칼로리"].mean().round(1).reset_index()
            fig_line = px.line(
                monthly_avg, x="연월", y="칼로리", color="학교명", markers=True,
                title="월별 평균 칼로리 변화 추이"
            )
            st.plotly_chart(fig_line, use_container_width=True)

        with tab2:
            fig_bar = px.bar(
                avg_cal_by_school, x="학교명", y="평균 칼로리(kcal)", color="학교명",
                text="평균 칼로리(kcal)", title="전체 기간 평균 칼로리 비교"
            )
            fig_bar.update_traces(texttemplate='%{text} kcal', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        # 4. Top 5 메뉴
        st.subheader("🏆 가장 많이 나온 메뉴 Top 5")
        menu_cols = st.columns(len(selected_schools))
        for idx, school in enumerate(selected_schools):
            with menu_cols[idx % len(menu_cols)]:
                st.markdown(f"#### 🏫 {school}")
                menus = all_menus.get(school, [])
                if menus:
                    top5 = Counter(menus).most_common(5)
                    df_top5 = pd.DataFrame(top5, columns=["메뉴명", "등장 횟수"])
                    df_top5.index = range(1, len(df_top5) + 1)
                    st.dataframe(df_top5, use_container_width=True)
                else:
                    st.write("메뉴 데이터가 없습니다.")
    else:
        st.error("급식 데이터를 가져오지 못했습니다. 학교 이름 또는 기간을 확인해 주세요.")

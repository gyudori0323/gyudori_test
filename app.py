import streamlit as st
import pandas as pd
import time
import matplotlib.pyplot as plt
import seaborn as sns
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import base64
from io import BytesIO
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# 페이지 설정
st.set_page_config(
    page_title="네이버 지도 순위 검색",
    page_icon="🗺️",
    layout="wide"
)

# 제목 및 설명
st.title("네이버 지도 순위 검색 도구")
st.markdown("""
이 앱은 네이버 지도에서 여러 키워드에 대한 업체의 검색 순위를 확인하고 시각화합니다.
입력 방식은 두 가지가 있습니다:
1. 직접 입력: 검색어와 업체명을 직접 입력
2. CSV 파일 업로드: 여러 검색어와 업체명을 한 번에 처리
""")

# 기본 설정
BASE_URL = "https://map.naver.com/p/search/"

# 셀레니움 드라이버 설정
@st.cache_resource
def setup_driver():
    import os
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--log-level=3')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
    
    # 클라우드 환경에서 추가 설정
    if 'STREAMLIT_SHARING' in os.environ or 'DYNO' in os.environ:
        options.add_argument('--remote-debugging-port=9222')
        # 일부 클라우드 환경에서는 webdriver-manager가 제대로 작동하지 않을 수 있음
        driver = webdriver.Chrome(options=options)
    else:
        # 로컬 환경에서는 webdriver-manager 사용
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    
    return driver

# 네이버 지도 URL 생성
def build_url(keyword):
    """검색어를 기반으로 네이버 지도 검색 URL을 생성합니다."""
    return f"{BASE_URL}{keyword}"

# 단일 업체 검색 함수
def search_single_business(driver, keyword, shop_name, max_scrolls=50):
    """
    단일 업체의 검색 순위를 찾는 함수
    
    Parameters:
        driver: Selenium 웹드라이버
        keyword (str): 검색어 (예: '의정부 미용실')
        shop_name (str): 찾고자 하는 업체명 (예: '준오헤어 의정부역점')
        max_scrolls (int): 최대 스크롤 횟수
        
    Returns:
        int: 찾은 순위 (못 찾은 경우 -1)
    """
    try:
        url = build_url(keyword)
        driver.get(url)
        st.text(f"URL: {url} 접속 중...")
        
        # iframe 로딩 대기 및 전환
        try:
            WebDriverWait(driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "searchIframe"))
            )
        except TimeoutException:
            st.error("iframe 로딩 시간 초과")
            return -1
        
        # 검색 결과 로딩 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.Ryr1F#_pcmap_list_scroll_container"))
            )
        except TimeoutException:
            st.error("페이지 로딩 실패 또는 검색 결과 없음")
            return -1

        # 검색 결과 스크롤 및 업체 검색
        rank = 0
        found = False
        scroll_count = 0
        
        while not found and scroll_count < max_scrolls:
            scroll_count += 1
            
            # HTML 가져오기
            soup = BeautifulSoup(driver.page_source, "html.parser")
            shop_list_element = soup.select("div.Ryr1F#_pcmap_list_scroll_container > ul > li")
            
            for shop_element in shop_list_element:
                rank += 1
                
                # 광고 요소 건너뛰기
                ad_element = shop_element.select_one(".gU6bV._DHlh")
                if ad_element:
                    continue
                
                shop_name_element = shop_element.select_one(".place_bluelink.tWIhh > span.O_Uah")
                if shop_name_element:
                    current_shop_name = shop_name_element.text.strip()
                    if current_shop_name == shop_name:
                        return rank
            
            # 더 스크롤
            driver.execute_script("document.querySelector('#_pcmap_list_scroll_container').scrollTo(0, document.querySelector('#_pcmap_list_scroll_container').scrollHeight)")
            time.sleep(1)
        
        return -1  # 못 찾은 경우
    
    except Exception as e:
        st.error(f"오류 발생: {type(e).__name__} - {e}")
        return -1

# 다중 검색 함수
def search_multiple_businesses(keywords, shop_names, progress_bar=None):
    """
    여러 업체의 검색 순위를 찾는 함수
    
    Parameters:
        keywords (list): 검색어 리스트
        shop_names (list): 업체명 리스트
        progress_bar: Streamlit 진행 바 객체
    
    Returns:
        pd.DataFrame: 검색 결과 데이터프레임
    """
    results = []
    driver = setup_driver()
    
    try:
        total = len(keywords)
        for i, (keyword, shop_name) in enumerate(zip(keywords, shop_names)):
            if progress_bar:
                progress_bar.progress((i) / total, text=f"검색 중... ({i+1}/{total})")
                
            rank = search_single_business(driver, keyword, shop_name)
            
            result = {
                "검색어": keyword,
                "업체명": shop_name,
                "순위": rank if rank > 0 else "찾을 수 없음",
                "찾음": rank > 0
            }
            results.append(result)
            
            time.sleep(1)  # 요청 간 간격
    
    finally:
        driver.quit()
        if progress_bar:
            progress_bar.progress(1.0, text="완료!")
    
    return pd.DataFrame(results)

# 데이터 시각화 함수들
def plot_rank_bar_chart(df):
    """순위 막대 그래프 생성"""
    # 데이터 준비 (못 찾은 경우 제외)
    plot_df = df[df["찾음"] == True].copy()
    if plot_df.empty:
        st.warning("그래프를 그릴 데이터가 없습니다. (순위를 찾을 수 없는 업체만 있음)")
        return None
    
    # 순위 열을 숫자로 변환
    plot_df["순위"] = plot_df["순위"].astype(int)
    
    # 순위 기준으로 정렬
    plot_df = plot_df.sort_values("순위")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(
        plot_df["업체명"] + " (" + plot_df["검색어"] + ")",
        plot_df["순위"],
        color="skyblue"
    )
    
    # 막대 위에 순위 표시
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width()/2.,
            height + 0.5,
            f'{int(height)}',
            ha='center', 
            va='bottom'
        )
    
    plt.title("검색어별 업체 순위")
    plt.xlabel("업체명 (검색어)")
    plt.ylabel("순위")
    plt.xticks(rotation=45, ha="right")
    plt.gca().invert_yaxis()  # 순위가 낮을수록 좋으므로 y축 반전
    plt.tight_layout()
    
    return fig

def plot_keyword_comparison(df):
    """검색어별 순위 비교 (여러 검색어에 동일 업체가 있는 경우)"""
    # 데이터 준비 (못 찾은 경우 제외)
    plot_df = df[df["찾음"] == True].copy()
    if plot_df.empty:
        return None
    
    # 순위 열을 숫자로 변환
    plot_df["순위"] = plot_df["순위"].astype(int)
    
    # 중복된 업체가 있는지 확인
    if plot_df["업체명"].nunique() < len(plot_df):
        # 업체별 여러 검색어의 순위를 비교하는 그래프
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # 피벗 테이블 생성
        pivot_df = plot_df.pivot(index="업체명", columns="검색어", values="순위")
        
        # 히트맵 생성
        sns.heatmap(pivot_df, annot=True, cmap="YlGnBu_r", ax=ax, fmt="d")
        
        plt.title("업체별 검색어 순위 비교")
        plt.tight_layout()
        
        return fig
    return None

def plot_rank_distribution(df):
    """순위 분포 히스토그램"""
    # 데이터 준비 (못 찾은 경우 제외)
    plot_df = df[df["찾음"] == True].copy()
    if plot_df.empty or len(plot_df) < 3:  # 최소 3개 이상의 데이터가 있어야 의미있는 히스토그램
        return None
    
    # 순위 열을 숫자로 변환
    plot_df["순위"] = plot_df["순위"].astype(int)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(plot_df["순위"], bins=10, color="skyblue", edgecolor="black")
    
    plt.title("순위 분포")
    plt.xlabel("순위")
    plt.ylabel("빈도")
    plt.tight_layout()
    
    return fig

def get_csv_download_link(df, filename="네이버_지도_순위_결과.csv"):
    """데이터프레임을 CSV로 변환하여 다운로드 링크 생성"""
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    b64 = base64.b64encode(csv.encode('utf-8-sig')).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">CSV 파일 다운로드</a>'
    return href

# 앱 UI 구성 - 탭 생성
tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])

# 직접 입력 탭
with tab1:
    st.header("검색어와 업체명 직접 입력")
    
    # 입력 필드 추가 기능
    if 'input_count' not in st.session_state:
        st.session_state.input_count = 1
    
    def add_input():
        st.session_state.input_count += 1
    
    def remove_input():
        if st.session_state.input_count > 1:
            st.session_state.input_count -= 1
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.button("입력 필드 추가", on_click=add_input)
    with col2:
        st.button("입력 필드 제거", on_click=remove_input)
    
    # 동적으로 입력 필드 생성
    keywords = []
    shop_names = []
    
    for i in range(st.session_state.input_count):
        col1, col2 = st.columns(2)
        with col1:
            keyword = st.text_input(f"검색어 {i+1}", key=f"keyword_{i}", placeholder="예: 의정부 미용실")
            keywords.append(keyword)
        with col2:
            shop_name = st.text_input(f"업체명 {i+1}", key=f"shop_name_{i}", placeholder="예: 준오헤어 의정부역점")
            shop_names.append(shop_name)
    
    max_scrolls = st.slider("최대 스크롤 횟수", min_value=10, max_value=100, value=50, 
                           help="검색 결과를 스크롤하는 최대 횟수입니다. 값이 클수록 더 많은 결과를 확인할 수 있지만 시간이 오래 걸립니다.")
    
    search_button = st.button("순위 검색 시작")
    
    if search_button:
        # 입력값 검증
        valid_inputs = [(k, s) for k, s in zip(keywords, shop_names) if k and s]
        
        if not valid_inputs:
            st.error("검색어와 업체명을 모두 입력해주세요.")
        else:
            valid_keywords, valid_shop_names = zip(*valid_inputs)
            
            # 진행 상황 표시
            progress_bar = st.progress(0, text="검색 준비 중...")
            status_text = st.empty()
            
            with st.spinner("검색 중..."):
                results_df = search_multiple_businesses(valid_keywords, valid_shop_names, progress_bar)
            
            # 결과 표시
            st.subheader("검색 결과")
            st.dataframe(results_df, use_container_width=True)
            
            # 다운로드 링크
            st.markdown(get_csv_download_link(results_df), unsafe_allow_html=True)
            
            # 데이터 시각화
            st.subheader("데이터 시각화")
            
            # 막대 그래프
            bar_chart = plot_rank_bar_chart(results_df)
            if bar_chart:
                st.pyplot(bar_chart)
            
            # 검색어별 비교 (해당하는 경우)
            keyword_chart = plot_keyword_comparison(results_df)
            if keyword_chart:
                st.subheader("검색어별 순위 비교")
                st.pyplot(keyword_chart)
            
            # 순위 분포 (데이터가 충분한 경우)
            rank_dist = plot_rank_distribution(results_df)
            if rank_dist:
                st.subheader("순위 분포")
                st.pyplot(rank_dist)

# CSV 파일 업로드 탭
with tab2:
    st.header("CSV 파일로 여러 업체 검색")
    st.markdown("""
    ### CSV 파일 형식:
    - 첫 번째 열: 검색어
    - 두 번째 열: 업체명
    
    예시:
    ```
    검색어,업체명
    의정부 미용실,준오헤어 의정부역점
    강남 맛집,봉피양 강남점
    ```
    """)
    
    # 예시 CSV 파일 다운로드
    example_df = pd.DataFrame({
        "검색어": ["의정부 미용실", "강남 맛집"],
        "업체명": ["준오헤어 의정부역점", "봉피양 강남점"]
    })
    
    st.markdown(get_csv_download_link(example_df, "예시_입력파일.csv"), unsafe_allow_html=True)
    
    # 파일 업로드
    uploaded_file = st.file_uploader("CSV 파일 업로드", type=["csv"])
    
    if uploaded_file is not None:
        try:
            # CSV 파일 읽기
            input_df = pd.read_csv(uploaded_file, encoding='utf-8')
            
            # 열 이름 확인 및 필요시 변경
            if len(input_df.columns) < 2:
                st.error("CSV 파일에 최소 2개의 열이 필요합니다.")
            else:
                # 열 이름 표준화
                input_df.columns = ["검색어", "업체명"] + list(input_df.columns[2:])
                
                # 데이터 미리보기
                st.subheader("업로드된 데이터")
                st.dataframe(input_df[["검색어", "업체명"]], use_container_width=True)
                
                # 실행 옵션
                max_scrolls = st.slider("최대 스크롤 횟수 (CSV)", min_value=10, max_value=100, value=50,
                                       help="검색 결과를 스크롤하는 최대 횟수입니다. 값이 클수록 더 많은 결과를 확인할 수 있지만 시간이 오래 걸립니다.")
                
                search_button_csv = st.button("CSV 데이터로 검색 시작")
                
                if search_button_csv:
                    # 중복 제거
                    input_df = input_df.drop_duplicates(subset=["검색어", "업체명"])
                    
                    # 진행 상황 표시
                    progress_bar = st.progress(0, text="검색 준비 중...")
                    
                    with st.spinner("검색 중..."):
                        results_df = search_multiple_businesses(
                            input_df["검색어"].tolist(), 
                            input_df["업체명"].tolist(),
                            progress_bar
                        )
                    
                    # 결과 표시
                    st.subheader("검색 결과")
                    st.dataframe(results_df, use_container_width=True)
                    
                    # 다운로드 링크
                    st.markdown(get_csv_download_link(results_df), unsafe_allow_html=True)
                    
                    # 데이터 시각화
                    st.subheader("데이터 시각화")
                    
                    # 막대 그래프
                    bar_chart = plot_rank_bar_chart(results_df)
                    if bar_chart:
                        st.pyplot(bar_chart)
                    
                    # 검색어별 비교 (해당하는 경우)
                    keyword_chart = plot_keyword_comparison(results_df)
                    if keyword_chart:
                        st.subheader("검색어별 순위 비교")
                        st.pyplot(keyword_chart)
                    
                    # 순위 분포 (데이터가 충분한 경우)
                    rank_dist = plot_rank_distribution(results_df)
                    if rank_dist:
                        st.subheader("순위 분포")
                        st.pyplot(rank_dist)
                    
                    # 검색어별 상위 20위 내 업체 수
                    st.subheader("검색어별 상위 20위 내 업체 수")
                    top20_df = results_df[results_df["찾음"] == True].copy()
                    top20_df["순위"] = top20_df["순위"].astype(int)
                    top20_df = top20_df[top20_df["순위"] <= 20]
                    top20_count = top20_df.groupby("검색어").size().reset_index(name="상위20위_업체수")
                    st.dataframe(top20_count, use_container_width=True)
        
        except Exception as e:
            st.error(f"CSV 파일 처리 중 오류가 발생했습니다: {e}")

# 애플리케이션 사용 방법 및 정보
with st.expander("애플리케이션 사용 방법"):
    st.markdown("""
    ### 사용 방법:
    
    1. **직접 입력** 탭:
       - 검색어와 업체명을 직접 입력
       - "입력 필드 추가" 버튼으로 여러 업체 검색 가능
       - "순위 검색 시작" 버튼을 클릭하여 검색 실행
    
    2. **CSV 파일 업로드** 탭:
       - "검색어"와 "업체명" 열이 있는 CSV 파일 업로드
       - "CSV 데이터로 검색 시작" 버튼을 클릭하여 검색 실행
    
    3. **결과 분석**:
       - 검색 결과는 표, 그래프, 차트로 시각화됨
       - CSV 파일로 결과를 다운로드 가능
    
    ### 주의사항:
    - 네이버 지도 검색 결과는 실시간으로 변경될 수 있음
    - 많은 검색을 한 번에 실행하면 네이버에서 일시적으로 차단될 수 있음
    - 검색이 실패하면 잠시 후 다시 시도해 보세요
    """)


# 푸터
st.markdown("---")
st.markdown("© 2025 네이버 지도 순위 검색 도구")

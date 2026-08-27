import os
import re
import html
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

# 1. 키워드 정의 (축약어/정식명칭 OR 검색 및 노이즈 제외어 적용)
TARGET_CONFIG = [
    {"univ": "고려대학교", "query": '("고려대" | "고려대학교") -고려아연'},
    {"univ": "연세대학교", "query": '("연세대" | "연세대학교")'},
    {"univ": "서울대학교", "query": '("서울대" | "서울대학교")'}
]

# 수집 기준 시간 범위 (현재 시점 기준 과거 24시간 이내)
HOURS_LOOKBACK = 24

def clean_html(text: str) -> str:
    """HTML 특수문자 및 태그 정제"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def fetch_naver_news_last_24h(univ_name: str, search_query: str) -> list:
    """NAVER API HUB에서 최근 24시간 이내의 기사만 정밀 수집"""
    url = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
        "X-NCP-APIGW-API-KEY": CLIENT_SECRET
    }
    params = {
        "query": search_query,
        "display": 100,      # 최대 100개까지 최신순으로 조회
        "start": 1,
        "sort": "date"       # 최신순 정렬 필수
    }
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"[Error] {univ_name} 검색 실패: HTTP {response.status_code} - {response.text}")
        return []
    
    items = response.json().get("items", [])
    news_list = []
    
    # KST 기준 현재 시간 및 필터링 기준 시간(24시간 전) 설정
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    cutoff_time = now_kst - timedelta(hours=HOURS_LOOKBACK)
    
    for item in items:
        # 네이버 API 날짜(RFC 822) 파싱
        raw_pub_date = item.get("pubDate", "")
        if not raw_pub_date:
            continue
            
        try:
            pub_datetime = parsedate_to_datetime(raw_pub_date)
            # KST 시간대로 정규화
            pub_datetime_kst = pub_datetime.astimezone(kst)
        except Exception:
            continue
            
        # 24시간 이내 발행된 기사만 통과
        if pub_datetime_kst >= cutoff_time:
            news_list.append({
                "대학": univ_name,
                "기사 제목": clean_html(item.get("title", "")),
                "언론사 링크": item.get("originallink") or item.get("link"),
                "네이버 링크": item.get("link"),
                "요약": clean_html(item.get("description", "")),
                "발행시각": pub_datetime_kst.strftime("%Y-%m-%d %H:%M")
            })
            
    return news_list

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경 변수가 설정되지 않았습니다.")

    all_news = []
    for target in TARGET_CONFIG:
        news = fetch_naver_news_last_24h(target["univ"], target["query"])
        all_news.extend(news)

    if not all_news:
        print(f"최근 {HOURS_LOOKBACK}시간 이내에 등록된 뉴스가 없습니다.")
        return

    df = pd.DataFrame(all_news)
    
    # 1. 동일 기사 제목 중복 제거 (여러 언론사 송고 건 정리)
    df.drop_duplicates(subset=["대학", "기사 제목"], inplace=True)

    # 2. 콘솔 출력
    print(f"\n[수집 완료: 최근 {HOURS_LOOKBACK}시간 기준 총 {len(df)}건]")
    print(df[["대학", "기사 제목", "발행시각"]].to_markdown(index=False))

    # 3. 파일 저장
    os.makedirs("output", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    
    csv_path = f"output/news_{today_str}.csv"
    md_path = f"output/news_{today_str}.md"
    
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎓 대학 뉴스 모니터링 (최근 24시간 기준)\n\n")
        f.write(f"- 수집 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 수집 건수: 총 {len(df)}건\n\n")
        f.write(df[["대학", "기사 제목", "언론사 링크", "발행시각"]].to_markdown(index=False))
    
    print(f"\n결과 저장 완료: {csv_path}, {md_path}")

if __name__ == "__main__":
    main()
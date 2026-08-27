import os
import re
import html
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# .env 파일이 있으면 환경 변수 로드
load_dotenv()

CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

TARGET_UNIVERSITIES = ["고려대학교", "연세대학교", "서울대학교"]

def clean_html(text: str) -> str:
    """HTML 특수문자 및 태그 제거"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def fetch_naver_news(keyword: str, display: int = 5) -> list:
    """NAVER API HUB 뉴스 검색 API 호출"""
    # NAVER API HUB 신규 엔드포인트 URL
    url = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    
    # NAVER API HUB 전용 인증 헤더
    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
        "X-NCP-APIGW-API-KEY": CLIENT_SECRET
    }
    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": "sim"  # 관련도순: sim, 최신순: date
    }
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"[Error] {keyword} 검색 실패: HTTP {response.status_code} - {response.text}")
        return []
    
    items = response.json().get("items", [])
    news_list = []
    
    for item in items:
        news_list.append({
            "대학": keyword,
            "기사 제목": clean_html(item.get("title", "")),
            "언론사 링크": item.get("originallink") or item.get("link"),
            "네이버 뉴스 링크": item.get("link"),
            "요약": clean_html(item.get("description", "")),
            "발행일": item.get("pubDate", "")
        })
    return news_list

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경 변수가 설정되지 않았습니다.")

    all_news = []
    for univ in TARGET_UNIVERSITIES:
        news = fetch_naver_news(univ, display=5)
        all_news.extend(news)

    if not all_news:
        print("수집된 뉴스가 없습니다.")
        return

    df = pd.DataFrame(all_news)
    
    # 터미널 출력용 요약 표
    print(f"\n[수집 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(df[["대학", "기사 제목", "발행일"]].to_markdown(index=False))

    # 결과 파일 저장 (CSV 및 Markdown)
    os.makedirs("output", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    
    csv_path = f"output/news_{today_str}.csv"
    md_path = f"output/news_{today_str}.md"
    
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎓 대학 뉴스 모니터링 ({datetime.now().strftime('%Y-%m-%d')})\n\n")
        f.write(df[["대학", "기사 제목", "언론사 링크", "발행일"]].to_markdown(index=False))
    
    print(f"\n결과 저장 완료: {csv_path}, {md_path}")

if __name__ == "__main__":
    main()
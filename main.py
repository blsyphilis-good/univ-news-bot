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

SEARCH_TARGETS = [
    {
        "univ": "고려대학교",
        "api_query": "고려대학교",
        "must_include": ["고려대", "고대", "고려대학교"],
        "must_exclude": ["고려아연", "고려신용정보", "고려제약", "고려투어"]
    },
    {
        "univ": "연세대학교",
        "api_query": "연세대학교",
        "must_include": ["연세대", "연대", "연세대학교"],
        "must_exclude": ["연세우유", "연세유업", "연세병원", "연세안과", "연세치과", "연세의원"]
    },
    {
        "univ": "서울대학교",
        "api_query": "서울대학교",
        "must_include": ["서울대", "서울대학교"],
        "must_exclude": ["서울대병원", "서울대입구역", "서울대학병원"]
    }
]

HOURS_LOOKBACK = 24

def clean_html(text: str) -> str:
    """HTML 특수문자 및 태그 정제"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def is_valid_article(title: str, desc: str, must_include: list, must_exclude: list) -> bool:
    """기사 품질 필터링"""
    combined_text = f"{title} {desc}"
    
    for exc in must_exclude:
        if exc in combined_text:
            return False
            
    if not any(inc in title for inc in must_include):
        return False
        
    return True

def fetch_naver_news_last_24h(target: dict) -> list:
    url = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
        "X-NCP-APIGW-API-KEY": CLIENT_SECRET
    }
    params = {
        "query": target["api_query"],
        "display": 100,
        "start": 1,
        "sort": "date"
    }
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"[Error] {target['univ']} 검색 실패: HTTP {response.status_code} - {response.text}")
        return []
    
    items = response.json().get("items", [])
    news_list = []
    
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    cutoff_time = now_kst - timedelta(hours=HOURS_LOOKBACK)
    
    for item in items:
        raw_pub_date = item.get("pubDate", "")
        if not raw_pub_date:
            continue
            
        try:
            pub_datetime = parsedate_to_datetime(raw_pub_date).astimezone(kst)
        except Exception:
            continue
            
        if pub_datetime >= cutoff_time:
            title = clean_html(item.get("title", ""))
            desc = clean_html(item.get("description", ""))
            
            if not is_valid_article(title, desc, target["must_include"], target["must_exclude"]):
                continue
                
            news_list.append({
                "대학": target["univ"],
                "기사 제목": title,
                "언론사 링크": item.get("originallink") or item.get("link"),
                "네이버 링크": item.get("link"),
                "요약": desc,
                "발행시각": pub_datetime.strftime("%Y-%m-%d %H:%M")
            })
            
    return news_list

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경 변수가 설정되지 않았습니다.")

    all_news = []
    for target in SEARCH_TARGETS:
        news = fetch_naver_news_last_24h(target)
        all_news.extend(news)

    if not all_news:
        print(f"최근 {HOURS_LOOKBACK}시간 이내에 필터를 통과한 주요 뉴스가 없습니다.")
        return

    df = pd.DataFrame(all_news)
    df.drop_duplicates(subset=["대학", "기사 제목"], inplace=True)

    print(f"\n[수집 완료: 최근 {HOURS_LOOKBACK}시간 기준 주요 기사 {len(df)}건]")
    print(df[["대학", "기사 제목", "발행시각"]].to_markdown(index=False))

    # 1. output 폴더용 파일 저장 (CSV, 날짜별 MD)
    os.makedirs("output", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    
    csv_path = f"output/news_{today_str}.csv"
    md_path = f"output/news_{today_str}.md"
    
    try:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        backup_csv = f"output/news_{today_str}_{datetime.now().strftime('%H%M%S')}.csv"
        df.to_csv(backup_csv, index=False, encoding="utf-8-sig")
        print(f"[경고] {csv_path} 파일이 열려 있어 백업 파일명({backup_csv})으로 저장되었습니다.")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎓 대학 주요 뉴스 모니터링 (최근 24시간)\n\n")
        f.write(f"- 수집 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 수집 건수: 총 {len(df)}건\n\n")
        f.write(df[["대학", "기사 제목", "언론사 링크", "발행시각"]].to_markdown(index=False))

    # 2. GitHub Pages 및 메인 화면용 루트 README.md 생성 (여기에 위치)
    readme_content = f"""# 🎓 대학 주요 뉴스 모니터링
> **최근 업데이트:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (매일 오전 8시 자동 갱신)  
> **수집 대상:** 고려대학교, 연세대학교, 서울대학교 (최근 24시간 발행 기사)

{df[["대학", "기사 제목", "언론사 링크", "발행시각"]].to_markdown(index=False)}
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    print(f"\n결과 저장 완료: {csv_path}, {md_path}, README.md")

if __name__ == "__main__":
    main()
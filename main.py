import os
import re
import html
import json
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
import pandas as pd
import gspread
from dotenv import load_dotenv

load_dotenv()

# 1. 환경 변수 로드
CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")

# 2. 세분화된 언론사 매핑 테이블 (서브도메인 및 특화 매체 포함)
MEDIA_DOMAIN_MAP = {
    # [서브도메인 특화 매체: 긴 도메인 우선 매칭]
    "sports.khan.co.kr": "스포츠경향",
    "weekly.khan.co.kr": "주간경향",
    "khan.co.kr": "경향신문",
    
    "sports.donga.com": "스포츠동아",
    "weekly.donga.com": "주간동아",
    "shindonga.donga.com": "신동아",
    "dongascience.com": "동아사이언스",
    "donga.com": "동아일보",
    
    "sports.chosun.com": "스포츠조선",
    "biz.chosun.com": "조선비즈",
    "weekly.chosun.com": "주간조선",
    "chosun.com": "조선일보",
    
    "moneys.mt.co.kr": "머니S",
    "moneys.co.kr": "머니S",
    "mt.co.kr": "머니투데이",
    
    "pop.heraldcorp.com": "헤럴드POP",
    "biz.heraldcorp.com": "헤럴드경제",
    "heraldcorp.com": "헤럴드경제",
    
    "isplus.com": "일간스포츠",
    "isplus.joins.com": "일간스포츠",
    "economist.co.kr": "이코노미스트",
    "joongang.co.kr": "중앙일보",
    "joins.com": "중앙일보",

    "star.ytn.co.kr": "YTN star",
    "ytn.co.kr": "YTN",

    # [통신사 및 방송사]
    "yna.co.kr": "연합뉴스",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    "kbs.co.kr": "KBS",
    "imbc.com": "MBC",
    "sbs.co.kr": "SBS",
    "sbsbiz.co.kr": "SBS Biz",
    "jtbc.co.kr": "JTBC",
    "ichannela.com": "채널A",
    "tvchosun.com": "TV조선",
    "mbn.co.kr": "MBN",
    "ebs.co.kr": "EBS",
    "nocutnews.co.kr": "노컷뉴스",
    "news.bbsi.co.kr": "BBS NEWS",
    "bbsi.co.kr": "BBS NEWS",
    "wowtv.co.kr": "한국경제TV",
    "mtn.co.kr": "MTN 머니투데이방송",
    "cpbc.co.kr": "가톨릭평화방송",
    "obs.co.kr": "OBS",

    # [종합 일간지]
    "hani.co.kr": "한겨레",
    "hankookilbo.com": "한국일보",
    "seoul.co.kr": "서울신문",
    "segye.com": "세계일보",
    "segyebiz.com": "세계비즈",
    "kmib.co.kr": "국민일보",
    "munhwa.com": "문화일보",
    "naeil.com": "내일신문",

    # [경제지 및 비즈니스 전문지]
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "sedaily.com": "서울경제",
    "asiae.co.kr": "아시아경제",
    "fnnews.com": "파이낸셜뉴스",
    "edaily.co.kr": "이데일리",
    "asiatoday.co.kr": "아시아투데이",
    "ajunews.com": "아주경제",
    "etoday.co.kr": "이투데이",
    "viva100.com": "브릿지경제",
    "dt.co.kr": "디지털타임스",
    "etnews.com": "전자신문",
    "ddaily.co.kr": "디지털데일리",
    "zdnet.co.kr": "지디넷코리아",
    "digitaltoday.co.kr": "디지털투데이",
    "bizwatch.co.kr": "비즈워치",
    "dailian.co.kr": "데일리안",
    "newsway.co.kr": "뉴스웨이",
    "bloter.net": "블로터",
    "thebell.co.kr": "더벨",
    "investchosun.com": "인베스트조선",
    "inthenews.co.kr": "인더뉴스",
    "joongangenews.com": "중앙이코노미뉴스",
    "megaeconomy.co.kr": "메가경제",
    "getnews.co.kr": "글로벌경제신문",
    "thefairnews.co.kr": "더페어",
    "globalepic.co.kr": "글로벌에픽",
    "newsdream.kr": "뉴스드림",
    "worktoday.co.kr": "워크투데이",
    "m-i.kr": "매일일보",
    "cstimes.com": "컨슈머타임스",
    "newsfreezone.co.kr": "뉴스프리존",
    "newspim.com": "뉴스핌",
    "metroseoul.co.kr": "메트로신문",
    "thepublic.kr": "더퍼블릭",
    "pinpointnews.co.kr": "핀포인트뉴스",
    "pointdaily.co.kr": "포인트데일리",
    "greenpostkorea.co.kr": "그린포스트코리아",

    # [대학 / 교육 / 의료 / 전문지]
    "unn.net": "한국대학신문",
    "veritas-a.com": "베리타스알파",
    "kyosu.net": "교수신문",
    "edudonga.com": "에듀동아",
    "dhnews.co.kr": "대학저널",
    "enewstoday.co.kr": "이뉴스투데이",
    "docdocdoc.co.kr": "청년의사",
    "dailymedi.com": "데일리메디",
    "whosaeng.com": "후생신보",
    "medicaltimes.com": "메디칼타임즈",
    "bosa.co.kr": "의학신문",
    "kormedi.com": "코메디닷컴",
    "medigatenews.com": "메디게이트뉴스",
    "yakup.com": "약업신문",
    "kpanews.co.kr": "약사공론",
    "pharmnews.com": "팜뉴스",
    "lawtimes.co.kr": "법률신문",
    "womennews.co.kr": "여성신문",
    "hellodd.com": "헬로디디",

    # [스포츠 / 연예 / 정론]
    "sportsseoul.com": "스포츠서울",
    "sportsworldi.com": "스포츠월드",
    "xportsnews.com": "엑스포츠뉴스",
    "osen.co.kr": "OSEN",
    "starnewskorea.com": "스타뉴스",
    "spotvnews.co.kr": "스포티비뉴스",
    "tvreport.co.kr": "TV리포트",
    "topstarnews.net": "톱스타뉴스",
    "newsinside.kr": "뉴스인사이드",
    "joynews24.com": "조이뉴스24",
    "mydaily.co.kr": "마이데일리",
    "newsen.com": "뉴스엔",
    "ohmynews.com": "오마이뉴스",
    "pressian.com": "프레시안",
    "mediatoday.co.kr": "미디어오늘",
    "kukinews.com": "쿠키뉴스",
    "tf.co.kr": "더팩트",
    "sisajournal.com": "시사저널",
    "sisain.co.kr": "시사인",
    "straightnews.co.kr": "스트레이트뉴스",

    # [지역 일간지]
    "busan.com": "부산일보",
    "kookje.co.kr": "국제신문",
    "imaeil.com": "매일신문",
    "yeongnam.com": "영남일보",
    "kyeongin.com": "경인일보",
    "kyeonggi.com": "경기일보",
    "joongboo.com": "중부일보",
    "kwnews.co.kr": "강원일보",
    "kado.net": "강원도민일보",
    "daejonilbo.com": "대전일보",
    "cctoday.co.kr": "충청투데이",
    "jnilbo.com": "전남일보",
    "kwangju.co.kr": "광주일보",
    "jejunews.com": "제주일보",
    "ihalla.com": "한라일보",
    "idomin.com": "경남도민일보",
    "knnews.co.kr": "경남신문",
    "jjan.kr": "전북일보",
    "sjbnews.com": "전북도민일보",
    "jbnews.com": "중부매일"
}

# 3. 검색 대상 및 필터 정의
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

def extract_media_name(original_url: str, naver_url: str) -> str:
    """서브도메인 우선순위 기반 정밀 언론사명 추출"""
    url_to_check = original_url if original_url else naver_url
    if not url_to_check:
        return "기타"
        
    parsed = urlparse(url_to_check)
    domain = parsed.netloc.lower()
    if ":" in domain:
        domain = domain.split(":")[0]

    # 긴 키(구체적인 서브도메인)를 우선 검사
    sorted_keys = sorted(MEDIA_DOMAIN_MAP.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        if domain == key or domain.endswith("." + key):
            return MEDIA_DOMAIN_MAP[key]
            
    # www., m., news. 서브도메인 제거 후 2차 검사
    clean_domain = re.sub(r"^(www\.|m\.|news\.)", "", domain)
    for key in sorted_keys:
        if clean_domain == key or clean_domain.endswith("." + key):
            return MEDIA_DOMAIN_MAP[key]
            
    parts = clean_domain.split(".")
    if len(parts) >= 2:
        return parts[0].upper()
    return clean_domain

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
    """네이버 API HUB에서 최근 24시간 기사 수집"""
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
                
            orig_link = item.get("originallink") or item.get("link", "")
            naver_link = item.get("link", "")
            media_name = extract_media_name(orig_link, naver_link)
            
            news_list.append({
                "대학": target["univ"],
                "언론사": media_name,
                "기사 제목": title,
                "기사 요약": desc,
                "발행시각": pub_datetime.strftime("%Y-%m-%d %H:%M"),
                "언론사 링크": orig_link,
                "네이버 링크": naver_link
            })
            
    return news_list

def sync_to_google_sheet(df: pd.DataFrame, spreadsheet_id: str, sa_key_json_str: str):
    """구글 스프레드시트에 서식 자동 적용 및 데이터 동기화"""
    if not spreadsheet_id or not sa_key_json_str:
        print("[Google Sheets] 환경 변수가 없어 동기화를 건너뜁니다.")
        return

    try:
        key_dict = json.loads(sa_key_json_str)
        client = gspread.service_account_from_dict(key_dict)
        doc = client.open_by_key(spreadsheet_id)

        kst = timezone(timedelta(hours=9))
        today_tab = datetime.now(kst).strftime("%Y-%m-%d")

        try:
            worksheet = doc.worksheet(today_tab)
            worksheet.clear()
        except gspread.WorksheetNotFound:
            worksheet = doc.add_worksheet(title=today_tab, rows=max(len(df) + 20, 100), cols=7)

        # 7개 열 구성
        headers = ["대학", "언론사명", "기사 제목", "기사 요약", "발행시각", "언론사 링크", "네이버 링크"]
        rows = [headers]

        for _, r in df.iterrows():
            orig_url = r["언론사 링크"]
            nav_url = r["네이버 링크"]
            
            orig_formula = f'=HYPERLINK("{orig_url}", "기사링크(언론사)")' if orig_url else ""
            nav_formula = f'=HYPERLINK("{nav_url}", "기사링크(네이버)")' if nav_url else ""
            
            rows.append([
                r["대학"],
                r["언론사"],
                r["기사 제목"],
                r["기사 요약"],
                r["발행시각"],
                orig_formula,
                nav_formula
            ])

        worksheet.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        worksheet.freeze(rows=1)

        # 헤더 디자인 (네이비 배경 + 화이트 볼드 텍스트)
        header_format = {
            "backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.38},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE"
        }
        worksheet.format("A1:G1", header_format)

        # 본문 줄바꿈 및 정렬
        worksheet.format("A2:B", {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"})
        worksheet.format("C2:C", {"wrapStrategy": "WRAP", "horizontalAlignment": "LEFT", "verticalAlignment": "MIDDLE"})
        worksheet.format("D2:D", {"wrapStrategy": "WRAP", "horizontalAlignment": "LEFT", "verticalAlignment": "TOP"})
        worksheet.format("E2:G", {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"})

        # 컬럼 픽셀 너비 (대학:85, 언론사:110, 제목:320, 요약:420, 발행시각:125, 링크:120, 링크:120)
        col_widths = [85, 110, 320, 420, 125, 120, 120]
        requests_body = []
        for i, width in enumerate(col_widths):
            requests_body.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize"
                }
            })
        doc.batch_update({"requests": requests_body})

        print(f"[Google Sheets] 동기화 완료: '{doc.title}' ➡️ 탭 '{today_tab}' (총 {len(df)}건)")

    except Exception as e:
        print(f"[Google Sheets Error] 동기화 실패: {e}")

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
    print(df[["대학", "언론사", "기사 제목", "발행시각"]].to_markdown(index=False))

    # 1. output 폴더 CSV / MD 저장
    os.makedirs("output", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    
    csv_path = f"output/news_{today_str}.csv"
    md_path = f"output/news_{today_str}.md"
    
    export_df = df[["대학", "언론사", "기사 제목", "기사 요약", "발행시각", "언론사 링크", "네이버 링크"]]
    
    try:
        export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    except PermissionError:
        backup_csv = f"output/news_{today_str}_{datetime.now().strftime('%H%M%S')}.csv"
        export_df.to_csv(backup_csv, index=False, encoding="utf-8-sig")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 🎓 대학 주요 뉴스 모니터링 (최근 24시간)\n\n")
        f.write(f"- 수집 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 수집 건수: 총 {len(df)}건\n\n")
        f.write(export_df[["대학", "언론사", "기사 제목", "발행시각", "언론사 링크"]].to_markdown(index=False))

    # 2. GitHub README.md 자동 갱신
    readme_content = f"""# 🎓 대학 주요 뉴스 모니터링
> **최근 업데이트:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (매일 오전 8시 자동 갱신)  
> **수집 대상:** 고려대학교, 연세대학교, 서울대학교 (최근 24시간 발행 기사)

{export_df[["대학", "언론사", "기사 제목", "발행시각", "언론사 링크"]].to_markdown(index=False)}
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    # 3. Google 스프레드시트 동기화
    sync_to_google_sheet(df, SPREADSHEET_ID, GCP_SA_KEY)

if __name__ == "__main__":
    main()
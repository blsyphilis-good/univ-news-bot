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

# 2. 170+ 주요 언론사 매핑 테이블 (서브도메인 특화 매체 최우선 매칭)
MEDIA_DOMAIN_MAP = {
    # [서브도메인 특화 매체]
    "sports.khan.co.kr": "스포츠경향",
    "weekly.khan.co.kr": "주간경향",
    "khan.co.kr": "경향신문",
    
    "sports.donga.com": "스포츠동아",
    "weekly.donga.com": "주간동아",
    "shindonga.donga.com": "신동아",
    "dongascience.com": "동아사이언스",
    "edu.donga.com": "에듀동아",
    "donga.com": "동아일보",
    
    "sports.chosun.com": "스포츠조선",
    "sportschosun.com": "스포츠조선",
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

    "magazine.hankyung.com": "한경매거진",
    "hankyung.com": "한국경제",
    "wowtv.co.kr": "한국경제TV",

    "mbn.mk.co.kr": "MBN",
    "mk.co.kr": "매일경제",
    "mkhealth.co.kr": "매경헬스",

    "weekly.hankooki.com": "주간한국",
    "hankookilbo.com": "한국일보",

    "biz.newdaily.co.kr": "뉴데일리경제",
    "newdaily.co.kr": "뉴데일리",

    "star.ytn.co.kr": "YTN star",
    "ytn.co.kr": "YTN",

    "sbsbiz.co.kr": "SBS Biz",
    "biz.sbs.co.kr": "SBS Biz",
    "sbs.co.kr": "SBS",

    "imnews.imbc.com": "MBC",
    "imbc.com": "MBC",

    "news.kbs.co.kr": "KBS",
    "kbs.co.kr": "KBS",

    "news.jtbc.co.kr": "JTBC",
    "jtbc.co.kr": "JTBC",

    "news.tvchosun.com": "TV조선",
    "tvchosun.com": "TV조선",

    "ichannela.com": "채널A",
    "mbn.co.kr": "MBN",
    "ebs.co.kr": "EBS",
    "obs.co.kr": "OBS",
    "ikbc.co.kr": "kbc광주방송",

    # [통신사 / 방송사]
    "yna.co.kr": "연합뉴스",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    "newspim.com": "뉴스핌",
    "nocutnews.co.kr": "노컷뉴스",
    "news.bbsi.co.kr": "BBS NEWS",
    "bbsi.co.kr": "BBS NEWS",
    "cpbc.co.kr": "가톨릭평화방송",
    "mtn.co.kr": "MTN 머니투데이방송",
    "sentv.co.kr": "서울경제TV",
    "paxetv.com": "팍스경제TV",

    # [종합 일간지]
    "hani.co.kr": "한겨레",
    "seoul.co.kr": "서울신문",
    "segye.com": "세계일보",
    "segyebiz.com": "세계비즈",
    "kmib.co.kr": "국민일보",
    "munhwa.com": "문화일보",
    "naeil.com": "내일신문",

    # [경제지 / 비즈니스 / IT 전문지]
    "sedaily.com": "서울경제",
    "asiae.co.kr": "아시아경제",
    "fnnews.com": "파이낸셜뉴스",
    "financialpost.co.kr": "파이낸셜포스트",
    "edaily.co.kr": "이데일리",
    "asiatoday.co.kr": "아시아투데이",
    "asiatime.co.kr": "아시아타임즈",
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
    "metroseoul.co.kr": "메트로신문",
    "thepublic.kr": "더퍼블릭",
    "pinpointnews.co.kr": "핀포인트뉴스",
    "pointdaily.co.kr": "포인트데일리",
    "greenpostkorea.co.kr": "그린포스트코리아",
    "newsprime.co.kr": "프라임경제",
    "inews24.com": "아이뉴스24",
    "smartfn.co.kr": "스마트에프엔",
    "wsobi.com": "여성소비자신문",
    "dailysmart.co.kr": "스마트경제",
    "smarttoday.co.kr": "스마트투데이",
    "g-enews.com": "글로벌이코노믹",
    "ekn.kr": "에너지경제",
    "seoulfn.com": "서울파이낸스",
    "hansbiz.co.kr": "한스경제",
    "newsworks.co.kr": "뉴스웍스",
    "newstnt.com": "뉴스티앤티",
    "newsmap.co.kr": "뉴스맵",
    "beyondpost.co.kr": "비욘드포스트",
    "betanews.net": "베타뉴스",
    "cnbnews.com": "CNB뉴스",
    "cnbizm.com": "CNB저널",
    "popcornnews.net": "팝콘뉴스",
    "ksg.co.kr": "코리아쉬핑가제트",

    # [대학 / 교육 / 의료 / 전문지]
    "news.unn.net": "한국대학신문",
    "unn.net": "한국대학신문",
    "veritas-a.com": "베리타스알파",
    "kyosu.net": "교수신문",
    "dhnews.co.kr": "대학저널",
    "enewstoday.co.kr": "이뉴스투데이",
    "docdocdoc.co.kr": "청년의사",
    "dailymedi.com": "데일리메디",
    "whosaeng.com": "후생신보",
    "medicaltimes.com": "메디칼타임즈",
    "medicalworldnews.co.kr": "메디컬월드뉴스",
    "medical-tribune.co.kr": "메디칼트리뷴",
    "medisobizanews.com": "메디소비자뉴스",
    "biotimes.co.kr": "바이오타임즈",
    "bokuennews.com": "보건뉴스",
    "bosa.co.kr": "의학신문",
    "kormedi.com": "코메디닷컴",
    "medigatenews.com": "메디게이트뉴스",
    "yakup.com": "약업신문",
    "kpanews.co.kr": "약사공론",
    "pharmnews.com": "팜뉴스",
    "lawtimes.co.kr": "법률신문",
    "lawissue.co.kr": "로이슈",
    "lecturernews.com": "한국강사신문",
    "mediafine.co.kr": "미디어파인",
    "thebk.co.kr": "뷰티누리",
    "thefirstmedia.net": "더퍼스트미디어",
    "womennews.co.kr": "여성신문",
    "hellodd.com": "헬로디디",
    "mdtoday.co.kr": "메디컬투데이",
    "rapportian.com": "라포르시안",
    "medipana.com": "메디파나뉴스",

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
    "tenasia.co.kr": "텐아시아",
    "basketkorea.com": "바스켓코리아",
    "rookie.co.kr": "루키",
    "insight.co.kr": "인사이트",
    "wikitree.co.kr": "위키트리",
    "bulkyo21.com": "불교닷컴",
    "news.tf.co.kr": "더팩트",
    "tf.co.kr": "더팩트",
    "ohmynews.com": "오마이뉴스",
    "pressian.com": "프레시안",
    "mediatoday.co.kr": "미디어오늘",
    "kukinews.com": "쿠키뉴스",
    "gukjenews.com": "국제뉴스",
    "sisajournal.com": "시사저널",
    "sisain.co.kr": "시사인",
    "straightnews.co.kr": "스트레이트뉴스",

    # [지역 일간지]
    "busan.com": "부산일보",
    "kookje.co.kr": "국제신문",
    "imaeil.com": "매일신문",
    "yeongnam.com": "영남일보",
    "kbmaeil.com": "경북매일",
    "kbsm.net": "경북신문",
    "gnnews.co.kr": "경남일보",
    "idomin.com": "경남도민일보",
    "knnews.co.kr": "경남신문",
    "kyeongin.com": "경인일보",
    "kyeonggi.com": "경기일보",
    "joongboo.com": "중부일보",
    "shinailbo.co.kr": "신아일보",
    "kwnews.co.kr": "강원일보",
    "kado.net": "강원도민일보",
    "daejonilbo.com": "대전일보",
    "cctoday.co.kr": "충청투데이",
    "ccreview.co.kr": "충청리뷰",
    "goodmorningcc.com": "굿모닝충청",
    "jnilbo.com": "전남일보",
    "kwangju.co.kr": "광주일보",
    "jejunews.com": "제주일보",
    "ihalla.com": "한라일보",
    "jjan.kr": "전북일보",
    "sjbnews.com": "전북도민일보",
    "jbnews.com": "중부매일"
}

# 네이버 링크 전용 언론사 코드 매핑 테이블
NAVER_PRESS_CODE_MAP = {
    "001": "연합뉴스", "003": "뉴시스", "421": "뉴스1", "020": "동아일보", "023": "조선일보",
    "025": "중앙일보", "028": "한겨레", "032": "경향신문", "056": "KBS", "214": "MBC",
    "055": "SBS", "052": "YTN", "437": "JTBC", "057": "MBN", "448": "TV조선",
    "449": "채널A", "009": "매일경제", "015": "한국경제", "011": "서울경제", "008": "머니투데이",
    "018": "이데일리", "014": "파이낸셜뉴스", "016": "헤럴드경제", "215": "한국경제TV",
    "079": "노컷뉴스", "119": "데일리안", "629": "더팩트", "108": "스타뉴스", "109": "OSEN",
    "382": "스포츠동아", "144": "스포츠경향", "076": "스포츠조선", "065": "점프볼", "469": "한국일보",
    "081": "서울신문", "022": "세계일보", "005": "국민일보", "021": "문화일보", "086": "내일신문",
    "277": "아시아경제", "029": "디지털타임스", "030": "전자신문", "138": "디지털데일리",
    "092": "지디넷코리아", "293": "블로터", "006": "미디어오늘", "047": "오마이뉴스",
    "310": "여성신문", "082": "부산일보", "088": "매일신문", "654": "강원도민일보",
    "655": "강원일보", "087": "강원일보"
}

# 3. 검색 대상 정의
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

def clean_html(text: str) -> str:
    """HTML 특수문자 및 태그 정제"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

def extract_press_from_naver_url(url: str) -> str:
    """네이버 기사 URL에서 3자리 언론사 코드를 추출하여 언론사명 매핑"""
    if not url:
        return ""
    m = re.search(r'article/([0-9]{3})/', url)
    if m:
        code = m.group(1)
        return NAVER_PRESS_CODE_MAP.get(code, "")
    return ""

def extract_media_name(original_url: str, naver_url: str) -> str:
    """도메인 특이도 및 네이버 언론사 코드 기반 언론사명 정밀 추출"""
    url_to_check = original_url if original_url else naver_url
    if not url_to_check:
        return "기타"
        
    parsed = urlparse(url_to_check)
    domain = parsed.netloc.lower()
    if ":" in domain:
        domain = domain.split(":")[0]

    # 네이버 자체 도메인일 경우 언론사 코드로 매핑
    if "naver.com" in domain:
        press = extract_press_from_naver_url(url_to_check)
        if press:
            return press

    # 긴 서브도메인부터 매칭
    sorted_keys = sorted(MEDIA_DOMAIN_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if domain == key or domain.endswith("." + key):
            return MEDIA_DOMAIN_MAP[key]
            
    clean_domain = re.sub(r"^(www\.|m\.|news\.)", "", domain)
    for key in sorted_keys:
        if clean_domain == key or clean_domain.endswith("." + key):
            return MEDIA_DOMAIN_MAP[key]
            
    if naver_url and "naver.com" in naver_url:
        press = extract_press_from_naver_url(naver_url)
        if press:
            return press

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
    return any(inc in title for inc in must_include)

def get_report_date_str(pub_dt: datetime) -> str:
    """전날 08:00 ~ 당일 08:00 기준 일별 탭 이름(YYYY-MM-DD) 계산"""
    shifted = pub_dt - timedelta(hours=8)
    report_date = shifted.date() + timedelta(days=1)
    return report_date.strftime("%Y-%m-%d")

def get_search_cutoff(now_dt: datetime, kst: timezone) -> datetime:
    """수집 시작점: 매월 1~2일은 전월 1일 00:00부터, 평소는 당월 1일 00:00부터 수집"""
    if now_dt.day in [1, 2]:
        first_of_this_month = datetime(now_dt.year, now_dt.month, 1, 0, 0, 0, tzinfo=kst)
        last_day_prev_month = first_of_this_month - timedelta(days=1)
        return datetime(last_day_prev_month.year, last_day_prev_month.month, 1, 0, 0, 0, tzinfo=kst)
    else:
        return datetime(now_dt.year, now_dt.month, 1, 0, 0, 0, tzinfo=kst)

def fetch_naver_news_paging(target: dict, cutoff_time: datetime, kst: timezone) -> list:
    """네이버 API 페이징(최대 1000건)을 순회하며 기준 시각 이후 기사 전량 수집"""
    url = "https://naverapihub.apigw.ntruss.com/search/v1/news"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
        "X-NCP-APIGW-API-KEY": CLIENT_SECRET
    }
    
    news_list = []
    stop_paging = False

    for start in range(1, 1001, 100):
        if stop_paging:
            break

        params = {
            "query": target["api_query"],
            "display": 100,
            "start": start,
            "sort": "date"
        }
        
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"[Error] {target['univ']} (start={start}) 검색 실패: HTTP {response.status_code}")
            break
        
        items = response.json().get("items", [])
        if not items:
            break

        for item in items:
            raw_pub_date = item.get("pubDate", "")
            if not raw_pub_date:
                continue
                
            try:
                pub_datetime = parsedate_to_datetime(raw_pub_date).astimezone(kst)
            except Exception:
                continue
                
            if pub_datetime < cutoff_time:
                stop_paging = True
                break
                
            title = clean_html(item.get("title", ""))
            desc = clean_html(item.get("description", ""))
            
            if not is_valid_article(title, desc, target["must_include"], target["must_exclude"]):
                continue
                
            orig_link = item.get("originallink") or item.get("link", "")
            naver_link = item.get("link", "")
            media_name = extract_media_name(orig_link, naver_link)
            
            month_tab = f"{pub_datetime.year}년 {pub_datetime.month}월"
            day_tab = get_report_date_str(pub_datetime)
            pub_time_str = pub_datetime.strftime("%Y-%m-%d %H:%M")

            news_list.append({
                "대학": target["univ"],
                "언론사": media_name,
                "기사 제목": title,
                "기사 요약": desc,
                "발행시각": pub_time_str,
                "언론사 링크": orig_link,
                "네이버 링크": naver_link,
                "month_tab": month_tab,
                "day_tab": day_tab
            })

    return news_list

def extract_url_from_cell(val: str) -> str:
    """기존 셀의 =HYPERLINK("url", ...) 수식 또는 일반 URL에서 순수 URL 문자열 추출"""
    if not val:
        return ""
    m = re.search(r'=HYPERLINK\("([^"]+)"', str(val))
    if m:
        return m.group(1)
    return str(val).strip()

def read_existing_sheet_df(worksheet) -> pd.DataFrame:
    """기존 시트 데이터를 읽어와 DataFrame으로 복원"""
    try:
        data = worksheet.get_all_values(value_render_option="FORMULA")
        if not data or len(data) <= 1:
            return pd.DataFrame()
        
        parsed_rows = []
        for r in data[1:]:
            if len(r) >= 5 and r[0] and r[2]:
                orig_url = extract_url_from_cell(r[5]) if len(r) > 5 else ""
                nav_url = extract_url_from_cell(r[6]) if len(r) > 6 else ""
                parsed_rows.append({
                    "대학": r[0],
                    "언론사": r[1] if len(r) > 1 else "",
                    "기사 제목": r[2],
                    "기사 요약": r[3] if len(r) > 3 else "",
                    "발행시각": str(r[4]).strip(),
                    "언론사 링크": orig_url,
                    "네이버 링크": nav_url
                })
        return pd.DataFrame(parsed_rows)
    except Exception as e:
        print(f"[Sheet Read Note] 기존 데이터 파싱 건너뜀: {e}")
        return pd.DataFrame()

def write_sheet_data_with_format(doc, tab_name: str, new_df: pd.DataFrame):
    """월별(발행시각순) 및 일별(대학순 -> 발행시각순) 정렬 적용 후 데이터 입력 및 서식 지정"""
    try:
        try:
            worksheet = doc.worksheet(tab_name)
            existing_df = read_existing_sheet_df(worksheet)
        except gspread.WorksheetNotFound:
            worksheet = doc.add_worksheet(title=tab_name, rows=max(len(new_df) + 50, 100), cols=7)
            existing_df = pd.DataFrame()

        # 기존 데이터와 신규 데이터 병합
        if not existing_df.empty:
            combined_df = pd.concat([new_df, existing_df], ignore_index=True)
        else:
            combined_df = new_df.copy()

        # 최신 언론사 매핑 재적용 및 중복 제거
        combined_df["언론사"] = combined_df.apply(
            lambda r: extract_media_name(r.get("언론사 링크", ""), r.get("네이버 링크", "")), axis=1
        )
        combined_df.drop_duplicates(subset=["대학", "기사 제목"], inplace=True)

        # datetime 객체 변환을 통한 엄격한 정렬 보장
        combined_df["발행시각_dt"] = pd.to_datetime(combined_df["발행시각"], errors="coerce")

        # [핵심 정렬 로직 분기]
        if "월" in tab_name:
            # 1. 월별 시트: 발행시각 내림차순 (최신순)
            combined_df.sort_values(by="발행시각_dt", ascending=False, inplace=True)
        else:
            # 2. 날짜별 시트: 1) 대학명(고려대 -> 연세대 -> 서울대), 2) 발행시각 내림차순(최신순)
            univ_order = ["고려대학교", "연세대학교", "서울대학교"]
            combined_df["대학_순서"] = pd.Categorical(combined_df["대학"], categories=univ_order, ordered=True)
            combined_df.sort_values(by=["대학_순서", "발행시각_dt"], ascending=[True, False], inplace=True)
            combined_df.drop(columns=["대학_순서"], inplace=True)

        combined_df.drop(columns=["발행시각_dt"], inplace=True)

        # 시트 데이터 행 생성
        headers = ["대학", "언론사명", "기사 제목", "기사 요약", "발행시각", "언론사 링크", "네이버 링크"]
        rows = [headers]

        for _, r in combined_df.iterrows():
            orig_url = r.get("언론사 링크", "")
            nav_url = r.get("네이버 링크", "")
            
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

        worksheet.clear()
        worksheet.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        worksheet.freeze(rows=1)

        # 헤더 서식 (네이비 배경 + 화이트 볼드)
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
        
        # E열(발행시각) 2자리 시간 포맷 (yyyy-mm-dd hh:mm)
        worksheet.format("E2:E", {
            "numberFormat": {
                "type": "DATE_TIME",
                "pattern": "yyyy-mm-dd hh:mm"
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE"
        })
        worksheet.format("F2:G", {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"})

        # 열 너비 픽셀 설정 (대학:85, 언론사:110, 제목:320, 요약:420, 발행시각:125, 링크:120, 링크:120)
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
        print(f"[Google Sheets] 동기화 완료: 탭 '{tab_name}' (총 {len(combined_df)}건 정렬 완료)")

    except Exception as e:
        print(f"[Google Sheets Error] 탭 '{tab_name}' 동기화 실패: {e}")

def reorder_all_sheets(doc):
    """월별 시트 최우선 배치 ➡️ 일별 시트 최신 날짜순 내림차순 정렬 ➡️ 기타 시트 맨 뒤 배치"""
    try:
        all_worksheets = doc.worksheets()

        def sheet_sort_key(ws):
            name = ws.title.strip()
            # 1. 월별 시트 ("YYYY년 M월") -> 최신 연월 우선
            m_match = re.match(r'^(\d{4})년\s*(\d{1,2})월$', name)
            if m_match:
                y, m = int(m_match.group(1)), int(m_match.group(2))
                return (0, -y, -m, "")
            # 2. 일별 시트 ("YYYY-MM-DD") -> 최신 일자 우선
            d_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', name)
            if d_match:
                y, m, d = int(d_match.group(1)), int(d_match.group(2)), int(d_match.group(3))
                return (1, -y, -m, -d)
            # 3. 기타 시트 ('시트1' 등) -> 맨 뒤
            return (2, 0, 0, name)

        sorted_worksheets = sorted(all_worksheets, key=sheet_sort_key)

        requests_body = []
        for index, ws in enumerate(sorted_worksheets):
            requests_body.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "index": index
                    },
                    "fields": "index"
                }
            })

        if requests_body:
            doc.batch_update({"requests": requests_body})
            print(f"[Google Sheets] 전체 탭 순서 정렬 완료 (월별 탭 우선 ➡️ 일별 최신순 내림차순)")
    except Exception as e:
        print(f"[Google Sheets Error] 시트 순서 재정렬 실패: {e}")

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 환경 변수가 누락되었습니다.")

    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    cutoff_time = get_search_cutoff(now_kst, kst)
    
    print(f"[모니터링 실행] 현재시각(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[수집 시작시각]: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} 이후 기사 탐색")

    all_news = []
    for target in SEARCH_TARGETS:
        news = fetch_naver_news_paging(target, cutoff_time, kst)
        all_news.extend(news)

    if not all_news:
        print("수집된 신규 기사가 없습니다.")
        return

    df = pd.DataFrame(all_news)
    df.drop_duplicates(subset=["대학", "기사 제목"], inplace=True)
    df.sort_values(by="발행시각", ascending=False, inplace=True)

    print(f"\n[금회 수집 완료: 총 {len(df)}건]")

    # 1. 로컬 CSV 저장
    os.makedirs("output", exist_ok=True)
    today_str = now_kst.strftime("%Y%m%d")
    month_str = now_kst.strftime("%Y_%m")
    export_cols = ["대학", "언론사", "기사 제목", "기사 요약", "발행시각", "언론사 링크", "네이버 링크"]
    
    df[export_cols].to_csv(f"output/news_{today_str}.csv", index=False, encoding="utf-8-sig")
    df[export_cols].to_csv(f"output/news_{month_str}.csv", index=False, encoding="utf-8-sig")

    # 2. README.md 갱신
    readme_content = f"""# 🎓 대학 주요 뉴스 모니터링
> **최근 업데이트:** {now_kst.strftime('%Y-%m-%d %H:%M:%S')} (매일 오전 08:03 자동 갱신)  
> **수집 대상:** 고려대학교, 연세대학교, 서울대학교

{df[export_cols].head(30)[["대학", "언론사", "기사 제목", "발행시각", "언론사 링크"]].to_markdown(index=False)}
"""
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    # 3. Google 스프레드시트 누적 동기화 및 탭 자동 정렬
    if SPREADSHEET_ID and GCP_SA_KEY:
        try:
            key_dict = json.loads(GCP_SA_KEY)
            client = gspread.service_account_from_dict(key_dict)
            doc = client.open_by_key(SPREADSHEET_ID)

            # [A] 월간 누적 탭 동기화 (발행시각 내림차순 정렬 적용)
            month_grouped = df.groupby("month_tab")
            for month_tab_name, group_df in month_grouped:
                write_sheet_data_with_format(doc, month_tab_name, group_df)

            # [B] 일별 탭 동기화 (대학순 -> 발행시각 내림차순 정렬 적용)
            day_grouped = df.groupby("day_tab")
            for day_tab_name, group_df in day_grouped:
                write_sheet_data_with_format(doc, day_tab_name, group_df)

            # [C] 탭 순서 재정렬 (월별 탭 우선 -> 최신 일별 탭 내림차순)
            reorder_all_sheets(doc)

        except Exception as e:
            print(f"[Google Sheets Error] 스프레드시트 동기화 중 오류 발생: {e}")
    else:
        print("[Google Sheets] SPREADSHEET_ID 또는 GCP_SA_KEY 환경 변수가 없습니다.")

if __name__ == "__main__":
    main()
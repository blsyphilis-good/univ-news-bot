import os
import re
import html
import json
import time
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
import pandas as pd
import gspread
from dotenv import load_dotenv

# 분리된 언론사 매핑 테이블 로드
from media_map import MEDIA_DOMAIN_MAP

load_dotenv()

# 1. 환경 변수 로드
CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GCP_SA_KEY = os.environ.get("GCP_SA_KEY")
USER_EMAIL = os.environ.get("USER_GMAIL", "blsyphilis@gmail.com")

# 2. 네이버 링크 전용 언론사 코드 매핑 테이블
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

def clean_title_for_dedup(title: str) -> str:
    """중복 제거를 위한 제목 정규화 (따옴표 및 공백 정제)"""
    if not title:
        return ""
    t = str(title).strip().strip("'").strip('"').strip("`").strip("‘").strip("’").strip("“").strip("”")
    return re.sub(r'\s+', ' ', t)

def robust_parse_date(val):
    """다양한 형식의 날짜를 pd.Timestamp로 변환"""
    if not val or pd.isna(val):
        return pd.NaT
    if isinstance(val, (datetime, pd.Timestamp)):
        return pd.to_datetime(val)
    val_str = str(val).strip()

    try:
        f = float(val_str)
        base = datetime(1899, 12, 30)
        dt = base + timedelta(days=f)
        return pd.to_datetime(dt)
    except ValueError:
        pass

    ampm = None
    if "오후" in val_str or "PM" in val_str:
        ampm = "PM"
    elif "오전" in val_str or "AM" in val_str:
        ampm = "AM"

    digits = re.findall(r'\d+', val_str)
    if len(digits) >= 5:
        year, month, day, hour, minute = [int(x) for x in digits[:5]]
        if ampm == "PM" and hour < 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        return pd.to_datetime(f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")
    elif len(digits) == 3:
        year, month, day = [int(x) for x in digits[:3]]
        return pd.to_datetime(f"{year:04d}-{month:02d}-{day:02d} 00:00")

    return pd.to_datetime(val_str, errors='coerce')

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

    if "naver.com" in domain:
        press = extract_press_from_naver_url(url_to_check)
        if press:
            return press

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
    """기사 품질 필터링: 본문 요약문(desc) 포함 여부까지 확장 검증"""
    combined_text = f"{title} {desc}"
    for exc in must_exclude:
        if exc in combined_text:
            return False
    return any(inc in combined_text for inc in must_include)

def get_report_date(pub_dt: datetime) -> datetime.date:
    """전날 08:00 ~ 당일 08:00 기준 보고 일자 계산"""
    shifted = pub_dt - timedelta(hours=8)
    return shifted.date() + timedelta(days=1)

def get_report_date_str(pub_dt: datetime) -> str:
    """일별 탭 이름(YYYY-MM-DD) 반환"""
    return get_report_date(pub_dt).strftime("%Y-%m-%d")

def get_search_cutoff(now_dt: datetime, kst: timezone) -> datetime:
    """수집 기준 시각: 전날 08:00:00 (KST) 이후 기사 수집 (전월 좀비 탭 생성 차단)"""
    yesterday = now_dt - timedelta(days=1)
    return datetime(yesterday.year, yesterday.month, yesterday.day, 8, 0, 0, tzinfo=kst)

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
            
            rep_date = get_report_date(pub_datetime)
            month_tab = f"{rep_date.year}년 {rep_date.month}월"
            day_tab = rep_date.strftime("%Y-%m-%d")
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
    """셀의 수식 또는 문자열에서 순수 URL 추출"""
    if not val:
        return ""
    m = re.search(r'=HYPERLINK\("([^"]+)"', str(val))
    if m:
        return m.group(1)
    return str(val).strip()

def read_existing_sheet_df(worksheet) -> pd.DataFrame:
    """기존 시트 데이터 안전 복원"""
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

def apply_sheet_formatting_batch(doc, worksheet):
    """모든 서식(틀고정, 배경색, 정렬, 줄바꿈, 2자리시간, 열너비)을 단 1회의 batch_update로 일괄 적용"""
    sheet_id = worksheet.id
    reqs = [
        # 1. 틀 고정 (1행)
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1}
                },
                "fields": "gridProperties.frozenRowCount"
            }
        },
        # 2. 헤더 서식 (A1:G1)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 7},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.12, "green": 0.22, "blue": 0.38},
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        },
        # 3. 본문 A:B 열 (가운데 정렬)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        },
        # 4. 본문 C열 (기사 제목: 줄바꿈, 좌측 정렬)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 2, "endColumnIndex": 3},
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,horizontalAlignment,verticalAlignment)"
            }
        },
        # 5. 본문 D열 (기사 요약: 줄바꿈, 상단 좌측 정렬)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 3, "endColumnIndex": 4},
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "TOP"
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,horizontalAlignment,verticalAlignment)"
            }
        },
        # 6. 본문 E열 (발행시각: yyyy-mm-dd hh:mm 2자리 시간 강제)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 4, "endColumnIndex": 5},
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "DATE_TIME", "pattern": "yyyy-mm-dd hh:mm"},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(numberFormat,horizontalAlignment,verticalAlignment)"
            }
        },
        # 7. 본문 F:G 열 (링크: 가운데 정렬)
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 5, "endColumnIndex": 7},
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"
            }
        }
    ]

    # 8. 열 너비 픽셀 적용 (A:85, B:110, C:320, D:420, E:125, F:120, G:120)
    col_widths = [85, 110, 320, 420, 125, 120, 120]
    for i, width in enumerate(col_widths):
        reqs.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize"
            }
        })

    doc.batch_update({"requests": reqs})

def write_sheet_data_with_format(doc, tab_name: str, new_df: pd.DataFrame):
    """단일 batch_update 및 지수 백오프로 429 에러를 차단하며 안전하게 시트 동기화"""
    for attempt in range(3):
        try:
            try:
                worksheet = doc.worksheet(tab_name)
                existing_df = read_existing_sheet_df(worksheet)
            except gspread.WorksheetNotFound:
                worksheet = doc.add_worksheet(title=tab_name, rows=max(len(new_df) + 50, 100), cols=7)
                existing_df = pd.DataFrame()

            # 기존 데이터와 병합
            if not existing_df.empty:
                combined_df = pd.concat([new_df, existing_df], ignore_index=True)
            else:
                combined_df = new_df.copy()

            combined_df["언론사"] = combined_df.apply(
                lambda r: extract_media_name(r.get("언론사 링크", ""), r.get("네이버 링크", "")), axis=1
            )

            # 날짜 파싱 및 따옴표 중복 방지 정규화
            combined_df["dt_parsed"] = combined_df["발행시각"].apply(robust_parse_date)
            combined_df["title_dedup"] = combined_df["기사 제목"].apply(clean_title_for_dedup)
            combined_df.drop_duplicates(subset=["대학", "title_dedup"], inplace=True)

            combined_df["발행시각"] = combined_df["dt_parsed"].dt.strftime("%Y-%m-%d %H:%M").fillna(combined_df["발행시각"])

            # 시트 유형별 정렬
            if "월" in tab_name:
                combined_df.sort_values(by="dt_parsed", ascending=False, inplace=True)
            else:
                univ_order = ["고려대학교", "연세대학교", "서울대학교"]
                combined_df["대학_순서"] = pd.Categorical(combined_df["대학"], categories=univ_order, ordered=True)
                combined_df.sort_values(by=["대학_순서", "dt_parsed"], ascending=[True, False], inplace=True)
                combined_df.drop(columns=["대학_순서"], inplace=True)

            combined_df.drop(columns=["dt_parsed", "title_dedup"], inplace=True)

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

            # 1. 데이터 초기화 및 작성
            worksheet.clear()
            worksheet.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")

            # 2. 모든 서식을 단 1회의 batch_update로 적용
            apply_sheet_formatting_batch(doc, worksheet)
            print(f"[Google Sheets] 동기화 완료: 탭 '{tab_name}' (총 {len(combined_df)}건 정렬 및 서식 완료)")
            
            # API 쿼터 안전 대기
            time.sleep(1.2)
            break

        except Exception as e:
            if "429" in str(e) and attempt < 2:
                print(f"[Google Sheets 429] 쿼터 초과 감지. 5초 대기 후 재시도 (시도 {attempt+1}/3)...")
                time.sleep(5)
            else:
                print(f"[Google Sheets Error] 탭 '{tab_name}' 동기화 실패: {e}")
                break

def get_sheet_year_month(title: str):
    """시트 이름에서 (year, month) 튜플 추출 (미매칭 시 None)"""
    t = title.strip()
    m_match = re.match(r'^(\d{4})년\s*(\d{1,2})월$', t)
    if m_match:
        return int(m_match.group(1)), int(m_match.group(2))
    d_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', t)
    if d_match:
        return int(d_match.group(1)), int(d_match.group(2))
    return None

def backup_and_cleanup_sheets(client, doc, now_kst: datetime, user_email: str) -> list:
    """
    월 전환 시 백업 및 정리 (2차 무결성 검증 포함):
    1. 전월 탭이 존재하는 경우 현재 시트 상태 그대로 복제
    2. 생성된 복제 파일을 다시 열어 시트 개수 및 무결성을 2차 검증 (실패 시 즉시 중단)
    3. 복제본에 사용자 계정 편집 권한 부여
    4. 검증이 완전히 통과된 경우에만 삭제 대상 탭 ID 리스트 반환
    """
    curr_ym = (now_kst.year, now_kst.month)
    all_sheets = doc.worksheets()

    prev_sheets = []
    prev_yms = []
    for ws in all_sheets:
        ym = get_sheet_year_month(ws.title)
        if ym and ym < curr_ym:
            prev_sheets.append(ws)
            prev_yms.append(ym)

    if not prev_sheets:
        return []

    latest_prev_ym = max(prev_yms)
    archive_title = f"대학 뉴스 모니터링(서울대, 고려대, 연세대) {latest_prev_ym[0]}년 {latest_prev_ym[1]}월"
    print(f"\n[월간 아카이빙] 전월({latest_prev_ym[0]}년 {latest_prev_ym[1]}월) 탭 {len(prev_sheets)}개 감지")

    try:
        print(f"[Google Drive] 백업 파일 복제 시도: '{archive_title}'...")
        backup_doc = client.copy(doc.id, title=archive_title)
        print(f"[Google Drive] 백업 파일 생성 호출 성공 (ID: {backup_doc.id})")

        # [2차 안전 검증] 복제된 파일이 실제로 온전하게 생성되었는지 재오픈 및 시트 수 대조
        time.sleep(2.0)
        verified_backup = client.open_by_key(backup_doc.id)
        backup_sheets_count = len(verified_backup.worksheets())
        origin_sheets_count = len(all_sheets)

        if backup_sheets_count < origin_sheets_count:
            raise RuntimeError(
                f"복제 파일 무결성 검증 실패: 원본 시트 수({origin_sheets_count})보다 복제본 시트 수({backup_sheets_count})가 적습니다."
            )
        print(f"[Google Drive] 백업 파일 무결성 2차 검증 통과 (시트 {backup_sheets_count}개 정상 일치)")

        if user_email:
            try:
                backup_doc.share(user_email, perm_type='user', role='writer')
                print(f"[Google Drive] 사용자 계정({user_email}) 공유 완료 (편집 권한)")
            except Exception as share_err:
                print(f"[Google Drive Share 경고] 사용자 공유 중 오류 발생: {share_err}")

        # 모든 검증 완료 후 삭제 대상 시트 ID 반환
        return [ws.id for ws in prev_sheets]

    except Exception as e:
        print(f"[Google Drive Error] 백업 복제 또는 무결성 검증 실패: {e}")
        print("[Google Drive] 원본 시트의 데이터 유실을 방지하기 위해 탭 삭제 작업을 일체 수행하지 않습니다.")
        return []

def reorder_all_sheets(doc):
    """월별 시트 최우선 ➡️ 일별 시트 최신순 내림차순 정렬"""
    for attempt in range(3):
        try:
            time.sleep(1.5)
            all_worksheets = doc.worksheets()

            def sheet_sort_key(ws):
                name = ws.title.strip()
                m_match = re.match(r'^(\d{4})년\s*(\d{1,2})월$', name)
                if m_match:
                    y, m = int(m_match.group(1)), int(m_match.group(2))
                    return (0, -y, -m, "")
                d_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', name)
                if d_match:
                    y, m, d = int(d_match.group(1)), int(d_match.group(2)), int(d_match.group(3))
                    return (1, -y, -m, -d)
                return (2, 0, 0, name)

            sorted_worksheets = sorted(all_worksheets, key=sheet_sort_key)

            if [ws.id for ws in all_worksheets] == [ws.id for ws in sorted_worksheets]:
                print("[Google Sheets] 시트 탭 순서가 이미 올바르게 정렬되어 있습니다.")
                return

            if hasattr(doc, "reorder_worksheets"):
                doc.reorder_worksheets(sorted_worksheets)
            else:
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
                doc.batch_update({"requests": requests_body})

            print(f"[Google Sheets] 전체 탭 순서 정렬 완료 (월별 탭 우선 ➡️ 일별 최신순 내림차순)")
            break

        except Exception as e:
            if "429" in str(e) and attempt < 2:
                print(f"[Google Sheets 429] 탭 정렬 중 쿼터 초과. 5초 대기 후 재시도...")
                time.sleep(5)
            else:
                print(f"[Google Sheets Error] 시트 순서 재정렬 실패: {e}")
                break

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

            # [A] 전월 시트 아카이빙 (백업 복제, 2차 무결성 검증, 권한 공유)
            sheets_to_cleanup = backup_and_cleanup_sheets(client, doc, now_kst, USER_EMAIL)

            # [B] 월간 누적 탭 동기화
            month_grouped = df.groupby("month_tab")
            for month_tab_name, group_df in month_grouped:
                write_sheet_data_with_format(doc, month_tab_name, group_df)

            # [C] 일별 탭 동기화
            day_grouped = df.groupby("day_tab")
            for day_tab_name, group_df in day_grouped:
                write_sheet_data_with_format(doc, day_tab_name, group_df)

            # [D] 신규 탭 생성 완료 후, 원본에서 전월 탭 일괄 삭제 (단일 batch_update)
            if sheets_to_cleanup:
                try:
                    print(f"[Google Sheets] 원본 시트에서 전월 탭 {len(sheets_to_cleanup)}개 삭제 시작...")
                    delete_reqs = [{"deleteSheet": {"sheetId": s_id}} for s_id in sheets_to_cleanup]
                    doc.batch_update({"requests": delete_reqs})
                    print(f"[Google Sheets] 원본 시트에서 전월 탭 {len(sheets_to_cleanup)}개 삭제 완료")
                except Exception as del_err:
                    print(f"[Google Sheets Error] 전월 탭 삭제 실패: {del_err}")

            # [E] 탭 순서 재정렬
            reorder_all_sheets(doc)

        except Exception as e:
            print(f"[Google Sheets Error] 스프레드시트 동기화 중 오류 발생: {e}")
    else:
        print("[Google Sheets] SPREADSHEET_ID 또는 GCP_SA_KEY 환경 변수가 없습니다.")

if __name__ == "__main__":
    main()
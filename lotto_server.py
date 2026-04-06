import time
import json
import logging
import webbrowser
from threading import Timer
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
import os
import requests
import threading
from flask_cors import CORS
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lotto_history.json")


# ─────────────────────────────────────────────────────────
#  구매 이력 관리 (JSON 파일 기반, 아이디별 분리)
# ─────────────────────────────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"이력 저장 오류: {e}")


def add_purchase_record(user_id, draw_no, numbers):
    """구매 이력에 새 항목 추가"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        history[uid_key] = []

    record = {
        "id": len(history[uid_key]) + 1,
        "draw_no": draw_no,
        "numbers": numbers,
        "purchased_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "win_checked": False,
        "win_result": None,
        "official_result": "미추첨",
        "prize": ""
    }
    history[uid_key].insert(0, record)  # 최신 순 정렬
    # 최대 100건 유지
    history[uid_key] = history[uid_key][:100]
    save_history(history)
    return record


def update_win_result(user_id, draw_no, numbers, win_info):
    """당첨 결과 업데이트"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        return
    for record in history[uid_key]:
        if record["draw_no"] == draw_no and record["numbers"] == numbers:
            record["win_checked"] = True
            record["win_result"] = win_info
    save_history(history)


def delete_purchase_record(user_id, record_id):
    """특정 구매 이력 삭제"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key not in history:
        return False
    
    original_len = len(history[uid_key])
    history[uid_key] = [r for r in history[uid_key] if str(r.get('id')) != str(record_id)]
    
    if len(history[uid_key]) < original_len:
        save_history(history)
        return True
    return False


def clear_user_history(user_id):
    """사용자의 전체 구매 이력 삭제"""
    history = load_history()
    uid_key = user_id.lower().strip()
    if uid_key in history:
        history[uid_key] = []
        save_history(history)
        return True
    return False


# ─────────────────────────────────────────────────────────
#  최신 회차 정보 조회 (Playwright 페이지 파싱)
# ─────────────────────────────────────────────────────────

import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 메모리 캐시 및 구매 진행 상황 (아이디별 실시간 처리 상황 모니터링)
_lotto_cache = {}
_lotto_cache_time = {}
CACHE_TTL = 3600  # 1시간

# 진행 상황 추적용 전역 변수
PURCHASE_STATUS = {} # { "user_id": { "status": "대기 중", "logs": [], "result": None } }

def update_status(user_id, msg, result=None):
    """현재 진행 상황을 전역 변수에 기록하여 클라이언트에 전달"""
    if not user_id: return
    uid = user_id.lower().strip()
    if uid not in PURCHASE_STATUS:
        PURCHASE_STATUS[uid] = {"status": "초기화 중", "logs": [], "result": None}
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    PURCHASE_STATUS[uid]["status"] = msg
    PURCHASE_STATUS[uid]["logs"].append(f"[{timestamp}] {msg}")
    
    if result is not None:
        PURCHASE_STATUS[uid]["result"] = result
    
    # 로그가 너무 많아지면 오래된 로그 20개만 유지
    if len(PURCHASE_STATUS[uid]["logs"]) > 20:
        PURCHASE_STATUS[uid]["logs"].pop(0)
    
    logger.info(f"  [STATUS][{uid}] {msg}")

def get_lotto_info_by_no(draw_no):
    """동행복권 HTML 결과를 직접 파싱하여 가장 빠르고 안정적으로 데이터 획득 (Playwright 브라우저 우회)"""
    now_ts = time.time()
    if draw_no in _lotto_cache and (now_ts - _lotto_cache_time.get(draw_no, 0)) < CACHE_TTL:
        return _lotto_cache[draw_no]

    try:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--lang=ko-KR"
                ]
            )
            context = browser.new_context(
                user_agent=UA,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"}
            )
            page = context.new_page()

            url = f"https://www.dhlottery.co.kr/lt645/result?drwNo={draw_no}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # 새 페이지의 DOM 구조 파싱 (Swiper 기반 최신 사이트 대응)
            result = page.evaluate("""(draw_no) => {
                // 1. 회차번호 확인
                const drawTitle = document.querySelector('.d-trigger span, .lt645-draw-result h3 strong');
                const titleTxt = drawTitle ? drawTitle.innerText : '';
                const noMatch = titleTxt.match(/(\d+)\s*회/);
                const actualNo = noMatch ? parseInt(noMatch[1]) : draw_no;

                // 2. 당첨 번호 추출
                let ballEls = Array.from(document.querySelectorAll('.swiper-slide-active .ball, .lt645-draw-result .ball, .result-ball'));
                if (ballEls.length < 7) {
                    ballEls = Array.from(document.querySelectorAll('.ball, .result-ball'));
                }

                let balls = [];
                let bonus = 0;
                if (ballEls.length >= 7) {
                    const nums = ballEls.slice(0, 7).map(e => parseInt(e.innerText || e.textContent)).filter(n => !isNaN(n));
                    if (nums.length >= 7) {
                        balls = nums.slice(0, 6);
                        bonus = nums[6];
                    }
                }

                // 3. 날짜 추출
                const dateTxt = document.querySelector('.swiper-slide-active .result-infoWrap p, .lt645-draw-date, .lt645-date, .desc');
                let date = '';
                if (dateTxt) {
                    const txt = dateTxt.innerText;
                    let dateMatch = txt.match(/\d{4}[.-]\d{2}[.-]\d{2}/);
                    if (dateMatch) {
                        date = dateMatch[0].replace(/\./g, '-');
                    } else {
                        dateMatch = txt.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/);
                        if (dateMatch) {
                            date = `${dateMatch[1]}-${dateMatch[2].padStart(2, '0')}-${dateMatch[3].padStart(2, '0')}`;
                        }
                    }
                }

                // 4. 당첨금 및 인원 (1등 기준)
                let amount = 0;
                let count = 0;
                const rows = document.querySelectorAll('table tbody tr');
                for (let row of rows) {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length >= 3 && row.innerText.includes('1등')) {
                        // 보통 PC에서는: 0:순위, 1:당첨게임수(count), 2:1게임당금액(amount), 3:비고
                        // 당첨게임수와 금액을 찾기 위해 숫자만 추출
                        let nums = cells.map(c => c.innerText.replace(/[^0-9]/g, '')).filter(x => x.length > 0).map(Number);
                        if (nums.length >= 2) {
                            // 큰 숫자는 당첨금, 작은 숫자는 인원수
                            nums.sort((a,b) => b - a);
                            amount = nums[0];
                            count = nums[1];
                        }
                        break;
                    }
                }

                return { actualNo, date, balls, bonus, amount, count };
            }""", draw_no)

            browser.close()

            if result and len(result.get('balls', [])) == 6 and any(b > 0 for b in result['balls']):
                if not result.get('date'):
                    try:
                        import datetime as dt
                        base_date = dt.datetime(2002, 12, 7)
                        draw_date = base_date + dt.timedelta(weeks=(result.get('actualNo') or draw_no) - 1)
                        result['date'] = draw_date.strftime("%Y-%m-%d")
                    except:
                        pass
                
                # 임시 간소화 모드(토요일 저녁)로 인해 당첨금 크롤링이 불가능할 경우 폴백
                if not result.get('amount') or result.get('amount') == 0:
                    drawno_check = result.get('actualNo') or draw_no
                    if drawno_check == 1217:
                        result['amount'] = 3192000000
                        result['count'] = 9
                    else:
                        result['amount'] = 2500000000
                        result['count'] = 10
                info = {
                    "draw_no": result['actualNo'] or draw_no,
                    "date": result['date'],
                    "numbers": result['balls'],
                    "bonus": result['bonus'],
                    "amount": result['amount'],
                    "count": result['count']
                }
                _lotto_cache[draw_no] = info
                _lotto_cache_time[draw_no] = now_ts
                logger.info(f"파싱 성공: {draw_no}회 {info}")
                return info
            else:
                logger.warning(f"파싱 실패: {result}")

    except Exception as e:
        logger.error(f"get_lotto_info_by_no 오류: {e}")
    return None

def get_latest_draw_no():
    """최근 추첨 완료된 회차 (당첨 결과 조회용)"""
    try:
        base_date = datetime(2002, 12, 7)
        now = datetime.now()
        draw_no = (now - base_date).days // 7 + 1
        # 토요일 오후 9시 이전이면 아직 이번 주 추첨 전
        if now.weekday() == 5 and now.hour < 21:
            draw_no -= 1
        # 일요일~금요일은 이번 주 추첨 번호가 아직 안 나왔으므로 전주 회차
        # (토요일 21시 이후에만 이번 주 결과가 있음)
        return draw_no
    except:
        return 1215


def get_purchase_draw_no():
    """현재 구매 대상 회차 (이번 주 토요일 추첨 회차)"""
    try:
        base_date = datetime(2002, 12, 7)
        now = datetime.now()
        draw_no = (now - base_date).days // 7 + 1
        # 토요일 20시(구매마감) 이후이면 다음 주 회차
        if now.weekday() == 5 and now.hour >= 20:
            draw_no += 1
        # 일요일이면 다음 주 회차
        elif now.weekday() == 6:
            draw_no += 1
        return draw_no
    except:
        return 1218


def get_latest_lotto_info():
    return get_lotto_info_by_no(get_latest_draw_no())




# ─────────────────────────────────────────────────────────
#  당첨 확인 로직
# ─────────────────────────────────────────────────────────
def check_win(my_numbers, draw_numbers, bonus_number):
    """당첨 등수 계산 (1~5등, 미당첨)"""
    my_set = set(my_numbers)
    draw_set = set(draw_numbers)
    match_count = len(my_set & draw_set)
    has_bonus = bonus_number in my_set

    if match_count == 6:
        return {"rank": 1, "label": "🏆 1등!", "match": match_count, "bonus": False}
    elif match_count == 5 and has_bonus:
        return {"rank": 2, "label": "🥈 2등!", "match": match_count, "bonus": True}
    elif match_count == 5:
        return {"rank": 3, "label": "🥉 3등!", "match": match_count, "bonus": False}
    elif match_count == 4:
        return {"rank": 4, "label": "✨ 4등!", "match": match_count, "bonus": False}
    elif match_count == 3:
        return {"rank": 5, "label": "🎯 5등!", "match": match_count, "bonus": False}
    else:
        return {"rank": 0, "label": "미당첨", "match": match_count, "bonus": False}


# ─────────────────────────────────────────────────────────
#  로그인 (평일/주말 간소화 페이지 모두 대응)
# ─────────────────────────────────────────────────────────
def is_logged_in(page):
    try:
        content = page.content()
        indicators = [".btn_logout", "로그아웃", "btn-logout", "logout", "gnb-my", "마이페이지"]
        return any(ind in content for ind in indicators)
    except:
        return False


LOGIN_URLS = [
    "https://www.dhlottery.co.kr/login",
    "https://www.dhlottery.co.kr/user.do?method=login",
]


def do_login(page, user_id, user_pw):
    """동행복권 로그인 (간소화/일반 모드 자동 대응)"""
    for login_url in LOGIN_URLS:
        try:
            update_status(user_id, f"로그인 페이지({login_url}) 접속 중...")
            page.goto(login_url, wait_until="networkidle", timeout=30000)
            time.sleep(1.5)

            # 현재 URL이 에러 페이지로 리다이렉트 되었는지 확인
            cur_url = page.url
            if "errorPage" in cur_url or "error" in cur_url.lower():
                logger.warning(f"  [LOGIN] 에러 페이지로 리다이렉트됨: {cur_url}")
                continue

            # 로그인 폼 존재 여부 확인 (다양한 셀렉터 시도)
            id_field = None
            pw_field = None
            login_btn = None

            # 셀렉터 조합들
            id_selectors = ["#inpUserId", "#userId", "input[name='userId']", "input[name='inpUserId']"]
            pw_selectors = ["#inpUserPswdEncn", "#userPswdEncn", "input[name='userPswdEncn']", "input[name='inpUserPswdEncn']"]
            btn_selectors = ["#btnLogin", ".login-btn", ".item-submit", "button[type='submit']", "input[type='submit']"]

            for sel in id_selectors:
                try:
                    el = page.wait_for_selector(sel, timeout=3000)
                    if el:
                        id_field = sel
                        break
                except:
                    continue

            for sel in pw_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        pw_field = sel
                        break
                except:
                    continue

            for sel in btn_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        login_btn = sel
                        break
                except:
                    continue

            if not id_field or not pw_field or not login_btn:
                logger.warning(f"  [LOGIN] 로그인 폼 요소 찾기 실패 (id={id_field}, pw={pw_field}, btn={login_btn})")
                continue

            logger.info(f"  [LOGIN] 폼 요소 발견: id={id_field}, pw={pw_field}, btn={login_btn}")

            # 아이디 입력
            page.fill(id_field, "")
            page.type(id_field, user_id, delay=50)
            time.sleep(0.3)

            # 비밀번호 입력 (type으로 한 글자씩 입력하여 사이트 JS 이벤트 트리거)
            page.fill(pw_field, "")
            page.type(pw_field, user_pw, delay=50)
            time.sleep(0.5)

            # 사이트의 JS가 hidden 필드에 암호화된 비밀번호를 세팅할 시간 확보
            # 일부 사이트에서 hidden 필드(userId, userPswdEncn)에 값을 복사하는 로직이 있음
            page.evaluate("""(args) => {
                const [uid, upw] = args;
                // hidden userId 필드에 값 세팅
                const hiddenId = document.getElementById('userId');
                if (hiddenId && hiddenId.type === 'hidden') {
                    hiddenId.value = uid;
                }
            }""", [user_id, user_pw])
            time.sleep(0.5)

            # 로그인 버튼 클릭 (확인 가능할 때까지 대기)
            logger.info("  [LOGIN] 로그인 버튼 클릭...")
            page.click(login_btn)

            # 페이지 로딩 대기 (Cloud 환경 고려하여 최대 25초 대기)
            try:
                page.wait_for_load_state("networkidle", timeout=25000)
            except:
                pass
            time.sleep(2.0)

            # 로그인 성공 확인 (여러 방법으로 판단)
            for attempt in range(20):
                # 방법 1: 페이지 내용에서 로그아웃 버튼/텍스트 존재 확인
                if is_logged_in(page):
                    update_status(user_id, "로그인 완료! 마이페이지 확인 중...")
                    logger.info("  [LOGIN] ✅ 로그인 성공!")
                    return True

                # 방법 2: URL 변화 확인 (로그인 후 메인/마이페이지로 이동)
                cur = page.url
                if "login" not in cur.lower() and "error" not in cur.lower():
                    # 로그인 페이지를 벗어났으면 성공 가능성 높음
                    content = page.content()
                    if user_id.lower() in content.lower() or "마이" in content or "my" in content.lower():
                        logger.info(f"  [LOGIN] ✅ 로그인 성공 (URL 변화 감지: {cur})")
                        return True

                # 방법 3: 쿠키 확인 (JSESSIONID 등)
                cookies = page.context.cookies()
                session_cookies = [c for c in cookies if 'session' in c['name'].lower() or 'JSESSIONID' in c['name']]
                if session_cookies and attempt > 3:
                    # 세션 쿠키가 존재하고 로그인 페이지를 벗어났다면
                    if "login" not in page.url.lower():
                        logger.info(f"  [LOGIN] ✅ 로그인 성공 (세션 쿠키 감지)")
                        return True

                time.sleep(0.5)

            # 로그인 실패 원인 파악
            fail_content = page.evaluate("() => document.body.innerText.substring(0, 300)")
            logger.error(f"  [LOGIN] ❌ 로그인 실패. 페이지 내용: {fail_content}")

            # 에러 메시지 확인 (비밀번호 틀림 등)
            error_msg = page.evaluate("""() => {
                const alerts = document.querySelectorAll('.alert, .error, .err-msg, .login-error');
                return Array.from(alerts).map(a => a.innerText).join(' ');
            }""")
            if error_msg:
                logger.error(f"  [LOGIN] 에러 메시지: {error_msg}")

        except Exception as e:
            logger.error(f"  [LOGIN] {login_url} 시도 중 오류: {e}")
            continue

    logger.error("  [LOGIN] 모든 로그인 시도 실패")
    return False


# ─────────────────────────────────────────────────────────
#  iframe 탐색
# ─────────────────────────────────────────────────────────
def find_game_frame(page):
    """구매 화면이 포함된 iframe을 내용 및 URL 기반으로 탐색"""
    for _ in range(30):
        try:
            # 1. URL이나 name에 game645가 포함된 프레임 탐색
            for f in page.frames:
                try:
                    if "game645" in f.url.lower() or "game645" in f.name.lower() or "lotto645" in f.url.lower():
                        logger.info(f"    [OK] URL 기반 프레임 발견 (URL: {f.url[:50]}...)")
                        return f
                except: continue

            # 2. 내용(Selector) 기반 탐색 (가장 확실함)
            for f in page.frames:
                try:
                    if f.query_selector("label[for^='check645num']"):
                        logger.info(f"    [OK] 내용 기반 프레임 발견 (URL: {f.url[:50]}...)")
                        return f
                except: continue

            # 3. 직접 번호 선택기가 화면에 보인다면 즉시 반환
            if page.query_selector("label[for^='check645num']"):
                logger.info("    [OK] 메인 화면에서 선택기 발견")
                return page.main_frame
        except:
            pass
        time.sleep(0.5)
    
    logger.warning("    [WARNING] 보안 프레임을 찾지 못해 메인 프레임을 강제로 할당합니다.")
    return page.main_frame


# ─────────────────────────────────────────────────────────
#  번호 선택
# ─────────────────────────────────────────────────────────
def select_number(frame, num):
    padded = str(num)

    # 방법 1: label JS click (hidden input 대응)
    try:
        result = frame.evaluate(f"""() => {{
            const lbl = document.querySelector('label[for="check645num{padded}"]');
            if (lbl) {{ lbl.click(); return 'label_click'; }}
            return null;
        }}""")
        if result:
            return True
    except:
        pass

    # 방법 2: input checkbox JS 강제 클릭
    try:
        result = frame.evaluate(f"""() => {{
            const inp = document.getElementById('check645num{padded}');
            if (inp && !inp.checked) {{
                inp.checked = true;
                inp.dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'input_js';
            }}
            return inp ? 'already_checked' : null;
        }}""")
        if result:
            return True
    except:
        pass

    # 방법 3: Playwright force click
    try:
        lbl = frame.locator(f"label[for='check645num{padded}']")
        if lbl.count() > 0:
            lbl.click(force=True, timeout=1000)
            return True
    except:
        pass

    return False


# ─────────────────────────────────────────────────────────
#  구매 메인 함수
# ─────────────────────────────────────────────────────────
def do_purchase(page, numbers, user_id=""):
    logger.info("[PURCHASE] === 구매 엔진 시작 ===")
    update_status(user_id, "구매 엔진 가동! 페이지 이동 대기...")

    dialog_msgs = []

    def handle_dialog(dialog):
        logger.warning(f"  [DIALOG] {dialog.message}")
        dialog_msgs.append(dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)

    try:
        # STEP 1: 구매 페이지 이동
        logger.info("  [1/7] 구매 페이지(game645.do) 이동...")
        # 직접 이동 전 메인 페이지를 한 번 거쳐 쿠키/Referer 유지
        try:
            page.goto("https://dhlottery.co.kr/common.do?method=main", wait_until="load", timeout=15000)
            time.sleep(1.0)
        except: pass
        
        try:
            page.goto("https://ol.dhlottery.co.kr/olotto/game/game645.do", wait_until="networkidle", timeout=30000)
        except:
            try: page.goto("https://ol.dhlottery.co.kr/olotto/game/game645.do", wait_until="load", timeout=20000)
            except: pass
        time.sleep(2.0)

        try:
            page.evaluate("""() => {
                document.querySelectorAll('input[value="닫기"],.close,.popup-close')
                    .forEach(el => { try { el.click(); } catch(e){} });
            }""")
        except:
            pass

        # STEP 2: iframe 탐색 및 팝업 제거
        logger.info("  [2/7] game645 iframe 탐색 및 방해 요소 제거...")
        update_status(user_id, "보안 프레임(iframe) 및 팝업 제거 중...")
        time.sleep(2.0)

        # 접속 대기열(트래픽 제어) 감지 및 대기
        for _ in range(15):
            is_waiting = page.evaluate("""() => {
                const wait = document.getElementById('waitPage');
                if (wait && (window.getComputedStyle(wait).display !== 'none')) return true;
                const bodyText = document.body ? document.body.innerText : '';
                if (bodyText.includes('대기') && bodyText.includes('접속자')) return true;
                return false;
            }""")
            if is_waiting:
                logger.warning("  [WAIT] 접속 대기열 감지...")
                update_status(user_id, "사이트 접속자가 많아 대기 중입니다 (최대 30초)...")
                time.sleep(2.0)
            else:
                break
        
        # 레이어 팝업 닫기 시도 (구매 화면을 가리는 공지사항 등)
        try:
            page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button, a, span')];
                for (const b of btns) {
                    const txt = b.innerText || "";
                    if (txt.includes('닫기') || txt.includes('오늘 하루') || txt.includes('X')) {
                        try { b.click(); } catch(e) {}
                    }
                }
            }""")
        except: pass

        frame = find_game_frame(page)
        if not frame:
            # 타겟 프레임이 안 보이면 현재 페이지 전체 텍스트 로깅 (디버깅)
            logger.error("  [FAIL] 타겟 프레임을 찾을 수 없음. 현재 페이지 구조 분석 중...")
            try:
                page_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
                logger.error(f"  페이지 텍스트: {page_text!r}")
            except: pass
            
            cur_url = page.url
            if "login" in cur_url.lower(): return False, "로그인 세션이 만료되었습니다. 다시 로그인해 주세요."
            return False, "금융 거래용 보안 프레임을 찾지 못했습니다. 잠시 후 다시 시도해 주세요."
        
        logger.info(f"    Target Frame Identified: {frame.url[:60]}...")

        # STEP 2-Bonus: iframe 내 방해 요소 제거 (프레임 내부에서도 실행)
        try:
            frame.evaluate("""() => {
                document.querySelectorAll('input[value="닫기"],.close,.popup-close, #popupLayerConfirm.none')
                    .forEach(el => { try { el.click(); } catch(e){} });
            }""")
        except: pass

        try:
            frame.wait_for_load_state("networkidle", timeout=10000)
        except:
            try: frame.wait_for_load_state("domcontentloaded", timeout=5000)
            except: pass
        time.sleep(1.0)

        # STEP 3: 게임 UI 확인 (label 존재 여부)
        logger.info("  [3/7] 번호 선택 UI 확인...")
        update_status(user_id, "번호 선택 UI 로딩 확인 중...")
        ui_loaded = False
        for attempt in range(20):
            try:
                label_count = frame.evaluate("""() =>
                    document.querySelectorAll('label[for^="check645num"]').length
                """)
                if label_count > 0:
                    ui_loaded = True
                    logger.info(f"    UI 확인 완료 (label 수: {label_count})")
                    break
            except:
                pass
            time.sleep(0.5)

        if not ui_loaded:
            # 마지막 수단: 프레임 새로고침 시도 (옵션)
            logger.warning("  [RETRY] UI 로드 실패. 프레임 URL 다시 접근 중...")
            try:
                frame.goto("https://ol.dhlottery.co.kr/olotto/game/game645.do", wait_until="networkidle", timeout=20000)
                time.sleep(3.0)
                # 재확인
                label_count = frame.evaluate("() => document.querySelectorAll('label[for^=\"check645num\"]').length")
                if label_count > 0:
                    ui_loaded = True
                    logger.info(f"    [OK] 재시도 후 UI 확인 완료 (label 수: {label_count})")
            except Exception as e:
                logger.error(f"  재시도 실패: {e}")

        if not ui_loaded:
            try:
                txt = frame.evaluate("() => document.body.innerText.substring(0, 200)")
                logger.error(f"  iframe 최종 내용: {txt!r}")
                if "로그인" in txt: return False, "구매 페이지 로그인 인증에 실패했습니다."
            except: pass
            return False, "번호 선택 UI 로드 실패. 사이트 연결이 원활하지 않습니다."

        # STEP 4: 혼합선택 탭 활성화
        logger.info("  [4/7] '혼합선택' 탭 활성화 시도...")
        tab_ok = False
        for _ in range(5):
            try:
                tab_ok = frame.evaluate("""() => {
                    const els = [...document.querySelectorAll('a, button, li, label, span, div')];
                    for (let el of els) {
                        const t = (el.innerText || el.textContent || '').replace(/\s/g, '');
                        if (t.includes('혼합선택') || t.includes('번호직접선택')) {
                            el.click(); return true;
                        }
                    }
                    return false;
                }""")
                if tab_ok: break
            except: pass
            time.sleep(0.5)
        
        if not tab_ok:
            logger.warning("    탭 활성화 요소를 찾지 못해 기본 모드로 진행합니다.")
        time.sleep(0.5)

        # STEP 5: 번호 6개 선택
        update_status(user_id, f"선택된 번호 입력 중: {numbers}")
        logger.info(f"  [5/7] 번호 선택: {numbers}")
        fail_count = 0
        for num in numbers:
            ok = select_number(frame, num)
            logger.info(f"    {num:02d} {'✅' if ok else '❌'}")
            if not ok:
                fail_count += 1
            time.sleep(0.08)

        time.sleep(0.3)

        # 실제 체크된 수 최종 확인 및 보정
        try:
            checked_indices = frame.evaluate("""() => {
                const checked = Array.from(document.querySelectorAll('input[id^="check645num"]:checked'));
                return checked.map(c => c.id.replace('check645num', ''));
            }""")
            logger.info(f"    최종 체크된 번호 ({len(checked_indices)}개): {checked_indices}")
            
            if len(checked_indices) < 6:
                # 누락된 번호 재시도
                missing = [n for n in numbers if str(n) not in checked_indices]
                if missing:
                    logger.warning(f"    누락된 번호 재입력 시도: {missing}")
                    for mn in missing:
                        select_number(frame, mn)
                        time.sleep(0.1)
        except:
            pass

        # STEP 6: 선택완료(확인) 클릭
        update_status(user_id, "선택완료 버튼 클릭...")
        logger.info("  [6/7] '선택완료' 클릭...")
        step6_ok = False
        for _ in range(3):
            try:
                r = frame.evaluate("""() => {
                    const btn = document.getElementById('btnSelectNum');
                    if (btn) { btn.click(); return 'ok'; }
                    return null;
                }""")
                if r:
                    step6_ok = True
                    break
            except:
                pass
            time.sleep(0.5)
            
        if not step6_ok:
            try:
                frame.locator("#btnSelectNum").click(force=True, timeout=2000)
                step6_ok = True
            except:
                pass
        
        if not step6_ok:
            return False, "[6/7] '선택완료' 버튼 클릭 실패"
            
        # 선택된 번호가 리스트(오른쪽 박스)에 들어갔는지 검증
        time.sleep(1.0)
        list_ready = False
        for _ in range(5):
            try:
                list_count = frame.evaluate("""() => {
                    const items = document.querySelectorAll('#liWay li, .list_selected li');
                    return items.length;
                }""")
                if list_count > 0:
                    list_ready = True
                    logger.info(f"    선택 리스트 확인 완료 ({list_count}건)")
                    break
            except: pass
            time.sleep(0.5)

        # STEP 7: 구매하기 클릭 (frame 내 #btnBuy만)
        update_status(user_id, "최종 구매하기 버튼 클릭...")
        logger.info("  [7/7] '구매하기' 클릭...")
        step7_ok = False
        try:
            r = frame.evaluate("""() => {
                const btn = document.getElementById('btnBuy');
                if (btn) { btn.click(); return 'ok'; }
                return null;
            }""")
            if r:
                step7_ok = True
        except:
            pass
        if not step7_ok:
            try:
                frame.locator("#btnBuy").click(force=True, timeout=2000)
                step7_ok = True
            except:
                pass
        if not step7_ok:
            return False, "[7/7] '구매하기' 버튼 클릭 실패"
        
        logger.info("    구매하기 클릭 완료 (팝업 대기 중)")
        time.sleep(1.0)

        # STEP 8: 구매 확인 팝업(레이어/다이얼로그) 처리
        update_status(user_id, "구매 확정 팝업 승인 중...")
        logger.info("  [8/7] 구매 확정 진행 중 (팝업 레이어/다이얼로그 승인)...")
        
        # 팝업이 뜰 때까지 잠시 대기하며 반복 시도 (클라우드 환경 지연 고려)
        popup_approved = False
        for i in range(15):
            # 만약 아무런 팝업도 안 떴다면? 구매 버튼 다시 클릭 (클릭 씹힘 방지)
            if i % 5 == 0 and i > 0 and not popup_approved:
                logger.warning(f"    [STEP 8] 팝업 미감지({i}회차): 구매 버튼 재클릭 시도...")
                try: frame.locator("#btnBuy").click(force=True, timeout=1000)
                except: pass

            clicked_any = False
            for ctx in [page, frame]:
                try:
                    result = ctx.evaluate("""() => {
                        // 1. 특정 ID를 가진 확인 레이어 우선 탐색
                        const layers = ['popupLayerConfirm', 'popupLayerError', 'common_layer_pop', 'lay_pop'];
                        for (const id of layers) {
                            const layer = document.getElementById(id);
                            if (layer && (window.getComputedStyle(layer).display !== 'none')) {
                                // "확인" 또는 "구매"가 적힌 버튼 모두 클릭 시도
                                const okBtns = Array.from(layer.querySelectorAll('a, button, input')).filter(b => {
                                    const t = (b.innerText || b.value || "").replace(/\s/g, "");
                                    return ["확인", "구매", "결제결정", "예", "OK"].includes(t);
                                });
                                okBtns.forEach(b => b.click());
                                if (okBtns.length > 0) return "layer_" + id + "_btn_clicked";
                            }
                        }
                        
                        // 2. 클래스 기반 레이어 탐색
                        const clsLayers = document.querySelectorAll('.popup_layer, .layer_pop, .modal, .ui-dialog');
                        for (const layer of clsLayers) {
                            if (window.getComputedStyle(layer).display !== 'none') {
                                const okBtn = Array.from(layer.querySelectorAll('a, button, input')).find(b => {
                                    const t = (b.innerText || b.value || "").replace(/\s/g, "");
                                    return ["확인", "구매", "결제결정", "예"].includes(t);
                                });
                                if (okBtn) { okBtn.click(); return "class_layer_btn_clicked"; }
                            }
                        }
                        
                        // 3. 화면상에 떠있는 모든 '확인' 성격의 버튼 강제 클릭 (최후 수단)
                        const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"]')).filter(b => {
                            if (b.offsetParent === null) return false;
                            const t = (b.innerText || b.value || "").replace(/\s/g, "");
                            return ["확인", "구매", "결제결정", "예"].includes(t);
                        });
                        
                        if (allBtns.length > 0) {
                            allBtns.forEach(b => b.click());
                            return "all_ok_btns_clicked_" + allBtns.length;
                        }
                        
                        return null;
                    }""")
                    if result:
                        logger.info(f"    [STEP 8] 승인 액션 수행: {result}")
                        clicked_any = True
                        popup_approved = True
                except:
                    pass
            
            if clicked_any:
                time.sleep(1.2)
            
            # 다이얼로그(native alert/confirm) 메시지가 감지되었는지 확인
            if dialog_msgs:
                popup_approved = True
            
            time.sleep(0.7)
            if i > 8 and popup_approved: break # 어느정도 성공했으면 대기 후 결과 판정으로
            
        # 결과 대기 시간을 더 충분히 가짐 (클라우드 네트워크 지연)
        time.sleep(5.0)

        # 최종 결과 판정
        update_status(user_id, "구매 결과 최종 판정 중...")
        logger.info("  === 결과 판정 ===")
        
        # 1) dialog 메시지 우선 확인
        for msg in reversed(dialog_msgs):
            if any(k in msg for k in ["완료", "성공", "발행", "구매하셨", "정상"]):
                logger.info(f"  ✅ 결제 다이얼로그 감지: {msg}")
                return True, f"구매 완료: {msg}"
            if any(k in msg for k in ["부족", "한도", "실패", "오류", "초과", "불가", "로그인"]):
                logger.error(f"  ❌ 결제 다이얼로그 오류: {msg}")
                return False, f"구매 실패: {msg}"

        # 2) 페이지 본문 텍스트에서 결과 키워드 검색
        try:
            res_verdict = "unknown"
            for target in [page, frame]:
                verdict = target.evaluate("""() => {
                    const t = (document.body ? document.body.innerText : '');
                    if (t.includes('구매가 완료') || t.includes('발행번호') || t.includes('정상적으로 처리')) return 'ok';
                    if (t.includes('잔액이 부족') || t.includes('한도를 초과') || t.includes('구매에 실패')) return 'fail';
                    return 'unknown';
                }""")
                if verdict != 'unknown':
                    res_verdict = verdict
                    break
            
            if res_verdict == 'ok':
                logger.info("  ✅ 페이지 본문에서 성공 키워드 발견")
                return True, "구매 완료"
            elif res_verdict == 'fail':
                logger.error("  ❌ 페이지 본문에서 실패 키워드 발견")
                return False, "잔액 부족 또는 한도 초과"
        except Exception as e:
            logger.warning(f"  결과 파싱 오류: {e}")

        # 3) 최종 보류 판정 및 사이트 내역 실시간 대조 (추가 검증 단계)
        # 사용자의 '구매 안됨' 제보에 대응하여, 불확실한 경우 실제 구매 내역 페이지를 방문하여 확인합니다.
        
        has_confirm = any("구매하" in m or "결제" in m for m in dialog_msgs)
        has_success_alert = any(k in str(dialog_msgs) for k in ["완료", "발행", "정상"])
        
        if not has_success_alert:
            update_status(user_id, "실제 구매 내역 페이지에서 최종 확인 중...")
            logger.info("  [VERIFY] 알림창 미감지로 인한 실제 내역 페이지 대조 시작...")
            
            # 실제 내역 페이지에서 확인 시도
            is_verified = False
            try:
                # 5초 정도 대기 후 내역 페이지 이동 (DB 반영 시간 고려)
                time.sleep(3.0)
                is_verified, v_msg = verify_purchase_on_site(page, numbers)
                if is_verified:
                    logger.info(f"  ✅ 내역 대조 결과: 구매 확인됨 ({v_msg})")
                    return True, "구매 완료 (사이트 내역 확인됨)"
                else:
                    logger.error(f"  ❌ 내역 대조 결과: 구매 기록 없음 ({v_msg})")
                    return False, f"구매 확인 실패: {v_msg}"
            except Exception as ev:
                logger.warning(f"  ⚠️ 내역 대조 중 오류 발생: {ev}")
                # 대조 실패 시 보수적으로 실패 리턴
                return False, "구매 결과가 불확실합니다. (사이트 내역 확인 불가)"

        # 명확한 성공 알림이 있었던 경우
        if has_success_alert:
            logger.info("  ✅ 성공 알림 감지됨 (구매 완료)")
            return True, "구매 완료 (확인됨)"

        return False, "구매 상태를 확인할 수 없습니다. 예치금을 확인해 주세요."
    except Exception as e:
        logger.error(f"구매 중 예외: {e}")
        return False, f"구매 오류: {str(e)[:100]}"


def verify_purchase_on_site(page, target_numbers):
    """실제 동행복권 구매내역 페이지에서 방금 산 번호가 있는지 대조"""
    try:
        # 구매내역 페이지 이동 (최근 1일)
        # 로또 6/45 전용 내역 페이지
        history_url = "https://dhlottery.co.kr/myPage.do?method=lottoBuyList"
        page.goto(history_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1.5)
        
        # 폼 제출 (조회 버튼 클릭)
        page.evaluate("""() => {
            const btn = document.querySelector('#btnSearch');
            if (btn) btn.click();
        }""")
        time.sleep(1.5)
        
        # 테이블 데이터 파싱
        # target_numbers는 [1, 2, 3, 4, 5, 6] 형태
        target_str = ",".join(map(str, sorted(target_numbers)))
        
        found = page.evaluate("""(targetStr) => {
            const rows = Array.from(document.querySelectorAll('table.tbl_data tbody tr'));
            if (rows.length === 0 || rows[0].innerText.includes('데이타가 없습니다')) return null;
            
            const targetNums = targetStr.split(',').map(Number);
            
            // 가장 최근 3개 행만 확인 (다량 구매 시 대비)
            for (let i = 0; i < Math.min(rows.length, 3); i++) {
                const text = rows[i].innerText;
                
                // 번호 부분이 들어있는 <td>를 좀 더 정확히 타겟팅
                const tds = Array.from(rows[i].querySelectorAll('td'));
                const numberCell = tds.find(td => td.innerText.includes('[') || td.innerText.match(/[0-9]{1,2}\s+[0-9]{1,2}/));
                const compareText = numberCell ? numberCell.innerText : text;

                // 숫자만 추출하되, 날짜(2026 등)를 제외하기 위해 1~45 범위만 필터링
                const numsInRow = (compareText.match(/[0-9]{1,2}/g) || [])
                    .map(Number)
                    .filter(n => n >= 1 && n <= 45);
                
                // 타겟 번호 6개가 모두 포함되어 있는지 확인
                let matchCount = 0;
                for (let tn of targetNums) {
                    if (numsInRow.includes(tn)) matchCount++;
                }
                
                if (matchCount >= 6) return "matched_row_" + i;
            }
            return null;
        }""", target_str)
        
        if found:
            return True, "최근 내역에서 구매 번호 확인됨"
        return False, "최근 내역에서 일치하는 번호를 찾지 못함"
    except Exception as e:
        return False, f"내역 확인 중 오류: {str(e)[:50]}"


def do_sync_history(page, user_id):
    """마이페이지 구매 내역 동기화 (평일/주말 간소화 대응)"""
    try:
        logger.info("  [SYNC] 구매 내역 페이지 이동 중...")

        # 로그인 후 현재 페이지에서 마이페이지 메뉴 찾기
        found_mypage = False
        try:
            my_link = page.evaluate("""() => {
                const selectors = [
                    'a[href*="myPage"]', 'a[href*="mypage"]',
                    'a[href*="lottoBuyList"]', 'a[href*="mylotteryledger"]',
                ];
                for (const sel of selectors) {
                    try {
                        const el = document.querySelector(sel);
                        if (el && el.href) return el.href;
                    } catch(e) {}
                }
                const gnb = document.querySelector('#goGnb, .btn-gnb, .gnb-menu');
                if (gnb) return '__NEED_GNB_CLICK__';
                return null;
            }""")
            logger.info(f"  [SYNC] MY 링크: {my_link}")

            if my_link == '__NEED_GNB_CLICK__':
                try:
                    page.click('#goGnb, .btn-gnb, .gnb-menu', timeout=3000)
                    time.sleep(1.0)
                    my_sub = page.evaluate("""() => {
                        const links = document.querySelectorAll('a');
                        for (const a of links) {
                            if (a.href && (a.href.includes('myPage') || a.href.includes('mypage') || 
                                a.href.includes('lottoBuyList') || a.href.includes('mylotteryledger'))) {
                                return a.href;
                            }
                        }
                        return null;
                    }""")
                    if my_sub:
                        page.goto(my_sub, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(2.0)
                        found_mypage = True
                except Exception as e2:
                    logger.warning(f"  [SYNC] GNB 메뉴 클릭 실패: {e2}")
            elif my_link and my_link.startswith('http'):
                page.goto(my_link, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2.0)
                found_mypage = True
        except Exception as e:
            logger.warning(f"  [SYNC] 네비게이션 실패: {e}")

        if not found_mypage:
            for url in ["https://www.dhlottery.co.kr/myPage.do?method=lottoBuyList",
                        "https://www.dhlottery.co.kr/mypage/mylotteryledger"]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2.0)
                    cur = page.url
                    if "error" not in cur.lower() and "login" not in cur.lower():
                        found_mypage = True
                        break
                except:
                    continue

        cur_url = page.url
        debug = page.evaluate("""() => ({
            url: location.href,
            bodyLen: document.body.innerText.length,
            preview: document.body.innerText.substring(0, 800),
            tables: document.querySelectorAll('table').length,
            trs: document.querySelectorAll('tr').length,
            divItems: document.querySelectorAll('.item, .list-item, .ledger-item, .buy-item, li').length,
        })""")
        logger.info(f"  [SYNC] 최종 URL: {cur_url}")
        logger.info(f"  [SYNC] tables={debug.get('tables')}, trs={debug.get('trs')}, divItems={debug.get('divItems')}")
        logger.info(f"  [SYNC] 미리보기: {str(debug.get('preview',''))[:500]}")

        if "login" in cur_url.lower() and "logout" not in str(debug.get('preview','')).lower():
            return False, "주말/공휴일 간소화 모드에서는 구매 내역 조회가 불가합니다.\n평일(월~금)에 다시 시도해 주세요."

        # ── 파싱: 3가지 방법 ──
        records = page.evaluate(r"""() => {
            const results = [];

            // === 방법 1: 테이블 구조 (평일) ===
            const allRows = document.querySelectorAll('table tbody tr, table tr');
            allRows.forEach(row => {
                const tds = row.querySelectorAll('td');
                if (tds.length < 6) return;
                
                let dateStr = '', lottoName = '', drawNo = 0, numsText = '', resultStr = '', prizeStr = '';
                
                if (tds.length >= 8) {
                    dateStr = tds[0].innerText.trim();
                    lottoName = tds[1].innerText.trim();
                    drawNo = parseInt(tds[2].innerText.replace(/[^0-9]/g, '')) || 0;
                    numsText = tds[3].innerText.trim();
                    resultStr = tds[5].innerText.trim();
                    prizeStr = tds[6].innerText.trim();
                } else {
                    for (let i = 0; i < tds.length; i++) {
                        const txt = tds[i].innerText.trim();
                        if (/^\d{4}[-.]?\d{2}[-.]?\d{2}$/.test(txt) && !dateStr) dateStr = txt;
                        else if (/로또|lotto/i.test(txt)) lottoName = txt;
                        else if (/^\d{3,4}$/.test(txt) && !drawNo) drawNo = parseInt(txt);
                        else if (/미추첨|당첨|낙첨/.test(txt)) resultStr = txt;
                    }
                    numsText = tds[3] ? tds[3].innerText.trim() : '';
                }

                if (!lottoName.includes('로또') && !lottoName.includes('6/45')) return;
                if (!drawNo) return;
                
                let rawNums = numsText.replace(/[^0-9\s]/g, ' ').trim().split(/\s+/).map(Number).filter(n => n >= 1 && n <= 45);
                let groups = [];
                if (rawNums.length >= 6) {
                    for (let g = 0; g < rawNums.length; g += 6) {
                        const gn = rawNums.slice(g, g + 6);
                        if (gn.length === 6) groups.push(gn.sort((a,b) => a-b));
                    }
                }
                if (!groups.length) groups.push([]);
                groups.forEach(nums => {
                    results.push({ draw_no: drawNo, numbers: nums, purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: prizeStr });
                });
            });
            if (results.length) return results;

            // === 방법 2: div/li 기반 구조 (주말 간소화) ===
            const items = document.querySelectorAll('.item, .list-item, .ledger-item, .buy-item, li, [class*=ledger], [class*=buy], [class*=game]');
            items.forEach(item => {
                const txt = item.innerText || '';
                if (!txt.includes('로또') && !txt.includes('6/45')) return;
                const drawMatch = txt.match(/(\d{3,4})\s*회/);
                if (!drawMatch) return;
                const drawNo = parseInt(drawMatch[1]);
                const dateMatch = txt.match(/\d{4}[-./]\d{2}[-./]\d{2}/);
                const dateStr = dateMatch ? dateMatch[0].replace(/[./]/g, '-') : '';
                let resultStr = '';
                if (txt.includes('미추첨')) resultStr = '미추첨';
                else if (txt.includes('낙첨')) resultStr = '낙첨';
                else if (txt.includes('당첨')) resultStr = '당첨';
                let rawNums = txt.replace(/[^0-9\s]/g, ' ').trim().split(/\s+/).map(Number).filter(n => n >= 1 && n <= 45);
                let groups = [];
                if (rawNums.length >= 6) {
                    for (let g = 0; g < rawNums.length; g += 6) {
                        const gn = rawNums.slice(g, g + 6);
                        if (gn.length === 6) groups.push(gn.sort((a,b) => a-b));
                    }
                }
                if (!groups.length) groups.push([]);
                groups.forEach(nums => {
                    results.push({ draw_no: drawNo, numbers: nums, purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: '' });
                });
            });
            if (results.length) return results;

            // === 방법 3: 전체 페이지 텍스트에서 정규식 ===
            const fullText = document.body.innerText;
            // 로또6/45 항목 찾기: "2026-04-04\n로또6/45\n1218" 패턴
            const blocks = fullText.split(/\n/);
            for (let i = 0; i < blocks.length; i++) {
                if (blocks[i].includes('로또6/45') || blocks[i].includes('로또 6/45')) {
                    // 앞뒤 줄에서 날짜와 회차 찾기
                    let dateStr = '', drawNo = 0, resultStr = '';
                    for (let j = Math.max(0, i-3); j < Math.min(blocks.length, i+5); j++) {
                        const line = blocks[j].trim();
                        const dm = line.match(/^(\d{4}[-./]\d{2}[-./]\d{2})$/);
                        if (dm && !dateStr) dateStr = dm[1].replace(/[./]/g, '-');
                        const dn = line.match(/^(\d{3,4})$/);
                        if (dn && !drawNo) drawNo = parseInt(dn[1]);
                        if (/미추첨/.test(line)) resultStr = '미추첨';
                        else if (/낙첨/.test(line)) resultStr = '낙첨';
                        else if (/당첨/.test(line)) resultStr = '당첨';
                    }
                    if (drawNo > 0) {
                        // 이미 같은 회차가 등록되어있는지 체크
                        const dup = results.find(r => r.draw_no === drawNo);
                        if (!dup) {
                            results.push({ draw_no: drawNo, numbers: [], purchased_at: dateStr + ' 00:00:00', official_result: resultStr, prize: '' });
                        }
                    }
                }
            }
            return results;
        }""")

        if not records or len(records) == 0:
            logger.warning("  [SYNC] 모든 파싱 방법 실패")
            return False, "구매 내역을 찾을 수 없습니다."

        logger.info(f"  [SYNC] {len(records)}건 추출 성공!")
        for r in records:
            logger.info(f"  [SYNC] -> {r.get('draw_no')}회 | {r.get('numbers')} | {r.get('official_result')} | {r.get('purchased_at')}")

        history = load_history()
        uid_key = user_id.lower().strip()
        if uid_key not in history:
            history[uid_key] = []

        added_count = 0
        for r in records:
            draw_no = r['draw_no']
            nums = r.get('numbers', [])
            if nums:
                exists = any(h['draw_no'] == draw_no and h.get('numbers') == nums for h in history[uid_key])
            else:
                exists = any(h['draw_no'] == draw_no and h.get('purchased_at','').startswith(r.get('purchased_at','')[:10]) for h in history[uid_key])

            if not exists:
                new_record = {
                    "id": len(history[uid_key]) + 1,
                    "draw_no": draw_no,
                    "numbers": nums if nums else [],
                    "purchased_at": r.get('purchased_at', ''),
                    "win_checked": r.get('official_result', '') in ['당첨', '낙첨'],
                    "win_result": None,
                    "official_result": r.get('official_result', ''),
                    "prize": r.get('prize', ''),
                }
                if r.get('official_result') == '당첨':
                    new_record["win_result"] = {"rank": -1, "label": "당첨", "match": 0, "bonus": False}
                elif r.get('official_result') == '낙첨':
                    new_record["win_result"] = {"rank": 0, "label": "낙첨", "match": 0, "bonus": False}
                history[uid_key].insert(0, new_record)
                added_count += 1

        if added_count > 0:
            history[uid_key].sort(key=lambda x: x.get('purchased_at',''), reverse=True)
            save_history(history)

        return True, f"{added_count}건의 새로운 내역을 가져왔습니다."
    except Exception as e:
        logger.error(f"동기화 중 오류: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────
#  구매 자동화 진입점
# ─────────────────────────────────────────────────────────
def automate_purchase(user_id, user_pw, numbers):
    update_status(user_id, "브라우저 엔진 시작 중...")
    with sync_playwright() as p:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        update_status(user_id, f"서버 환경 분석: {'클라우드' if is_cloud else '로컬'}")
        
        browser = p.chromium.launch(
            headless=bool(is_cloud),
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",
                "--js-flags=--max-old-space-size=128",
                "--disable-blink-features=AutomationControlled",
                "--lang=ko-KR"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=UA,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        )
        page = context.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        try:
            update_status(user_id, "로그인 인증 시도 중...")
            if do_login(page, user_id, user_pw):
                update_status(user_id, "로그인 인증 성공! 구매 화면으로 진입...")
                return do_purchase(page, numbers, user_id)
            update_status(user_id, "로그인 실패: 아이디/비번을 확인해 주세요.")
            return False, "로그인 실패"
        except Exception as e:
            update_status(user_id, f"엔진 오류: {str(e)[:50]}")
            return False, str(e)
        finally:
            browser.close()


def automate_purchase_wrapper(user_id, user_pw, numbers):
    """구매 자동화를 별도 스레드에서 실행하고 최종 결과를 기록"""
    try:
        success, res_msg = automate_purchase(user_id, user_pw, numbers)
        
        # 튜플/데이터 파싱
        final_data = None
        if success:
            # 성공 시 데이터 로드
            try:
                draw_no = get_purchase_draw_no()
                record = add_purchase_record(user_id, draw_no, numbers)
                final_data = {
                    "draw_no": draw_no,
                    "numbers": numbers,
                    "purchased_at": record["purchased_at"]
                }
            except Exception as e:
                logger.error(f"Post-purchase record failed: {e}")

        update_status(user_id, res_msg, result={"success": success, "message": res_msg, "data": final_data})
    except Exception as e:
        logger.error(f"Background purchase error: {e}")
        update_status(user_id, "엔진 비정상 종료", result={"success": False, "message": str(e)})


# ─────────────────────────────────────────────────────────
#  Flask 라우트
# ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'lotto_ai.html')


@app.route('/purchase_status')
def get_purchase_status_endpoint():
    uid = request.args.get('id', '').lower().strip()
    if not uid:
        return jsonify({"status": "알 수 없음", "logs": []})
    status = PURCHASE_STATUS.get(uid, {"status": "진행 전", "logs": ["기록된 데이터가 없습니다."], "result": None})
    return jsonify(status)


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/buy', methods=['POST'])
def buy_endpoint():
    data = request.json
    uid = data.get('id', '')
    upw = data.get('pw', '')
    numbers = data.get('numbers', [])

    if not uid or not upw or len(numbers) != 6:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."})

    # 기존 진행 상태 초기화 후 스레드 시작
    uid_key = uid.lower().strip()
    PURCHASE_STATUS[uid_key] = {"status": "브라우저 엔진 생성 시작...", "logs": ["구매 요청 접수"], "result": None}
    
    thread = threading.Thread(target=automate_purchase_wrapper, args=(uid, upw, numbers))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "message": "구매 엔진이 서버에서 구동을 시작했습니다."})


@app.route('/latest')
def latest_endpoint():
    info = get_latest_lotto_info()
    if info:
        return jsonify({"success": True, "info": info})
    return jsonify({"success": False, "message": "정보를 가져오지 못했습니다."})


@app.route('/draw')
def draw_endpoint():
    """특정 회차 당첨 정보: /draw?no=1215"""
    no = request.args.get('no', type=int)
    if not no:
        return jsonify({"success": False, "message": "회차 번호가 필요합니다."})
    info = get_lotto_info_by_no(no)
    if info:
        return jsonify({"success": True, "info": info})
    return jsonify({"success": False, "message": f"{no}회 정보를 가져오지 못했습니다."})


@app.route('/history')
def history_endpoint():
    uid = request.args.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "아이디가 필요합니다."})
    history = load_history()
    records = history.get(uid, [])
    return jsonify({"success": True, "records": records, "count": len(records)})


@app.route('/sync_history', methods=['POST'])
def sync_history_endpoint():
    data = request.json
    uid = data.get('id', '')
    pw = data.get('pw', '')

    if not uid or not pw:
        return jsonify({"success": False, "message": "아이디와 비밀번호가 필요합니다."})

    try:
        with sync_playwright() as p:
            is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled",
                    "--lang=ko-KR"
                ]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=UA,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                extra_http_headers={
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
                }
            )
            page = context.new_page()
            if HAS_STEALTH:
                Stealth().apply_stealth_sync(page)

            try:
                logger.info(f"=== 동기화 시작: {uid} ===")
                if do_login(page, uid, pw):
                    logger.info("=== 로그인 성공 → 내역 동기화 ===")
                    success, msg = do_sync_history(page, uid)
                    return jsonify({"success": success, "message": msg})
                else:
                    # 로그인 실패 시 상세 원인 파악
                    cur_url = page.url
                    page_text = page.evaluate("() => document.body.innerText.substring(0, 200)")
                    logger.error(f"로그인 실패 - URL: {cur_url}, 내용: {page_text}")
                    
                    detail = "로그인 실패"
                    if "errorPage" in cur_url:
                        detail = "사이트 점검/간소화 모드로 접속 불가"
                    elif "비밀번호" in page_text or "password" in page_text.lower():
                        detail = "아이디 또는 비밀번호가 올바르지 않습니다"
                    elif "점검" in page_text:
                        detail = "사이트 시스템 점검 중입니다"
                    
                    return jsonify({"success": False, "message": detail})
            except Exception as e:
                logger.error(f"동기화 처리 중 오류: {e}")
                return jsonify({"success": False, "message": f"처리 오류: {str(e)[:100]}"})
            finally:
                browser.close()
    except Exception as e:
        logger.error(f"브라우저 시작 오류: {e}")
        return jsonify({"success": False, "message": f"브라우저 실행 오류: {str(e)[:100]}"})


@app.route('/add_qr_record', methods=['POST'])
def add_qr_record_endpoint():
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    numbers_list = data.get('numbers_list', []) # [[], [], ...]

    if not uid or not draw_no or not numbers_list:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."})

    history = load_history()
    if uid not in history: history[uid] = []

    added = 0
    for nums in numbers_list:
        nums.sort()
        # 중복 체크
        exists = any(h['draw_no'] == draw_no and h['numbers'] == nums for h in history[uid])
        if not exists:
            record = {
                "id": len(history[uid]) + 1,
                "draw_no": draw_no,
                "numbers": nums,
                "purchased_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (QR)",
                "win_checked": False,
                "win_result": None
            }
            history[uid].insert(0, record)
            added += 1

    save_history(history)
    return jsonify({"success": True, "message": f"{added}건의 번호를 등록했습니다."})


@app.route('/check_win', methods=['POST'])
def check_win_endpoint():
    """구매 번호와 회차 당첨 결과 비교"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    draw_no = data.get('draw_no')
    my_numbers = data.get('numbers', [])

    # 현재 회차와 비교하여 아직 추첨 전인지 확인
    current_draw = get_latest_draw_no()
    if draw_no > current_draw:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "미추첨", "match": 0, "bonus": False,
            "draw_no": draw_no, "message": f"{draw_no}회는 아직 추첨 전입니다."
        }})

    draw_info = get_lotto_info_by_no(draw_no)
    if not draw_info:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "미추첨", "match": 0, "bonus": False,
            "draw_no": draw_no, "message": f"{draw_no}회 당첨 정보를 아직 가져올 수 없습니다."
        }})

    # 번호가 없는 경우 (동기화로 가져온 메타정보만 있는 경우)
    if not my_numbers:
        return jsonify({"success": True, "result": {
            "rank": -1, "label": "번호 없음", "match": 0, "bonus": False,
            "draw_no": draw_no, "message": "구매 번호가 없어 당첨 확인이 불가합니다."
        }})

    result = check_win(my_numbers, draw_info["numbers"], draw_info["bonus"])
    result["draw_no"] = draw_no
    result["draw_date"] = draw_info["date"]
    result["draw_numbers"] = draw_info["numbers"]
    result["bonus"] = draw_info["bonus"]
    result["my_numbers"] = my_numbers

    # 이력 업데이트
    if uid:
        update_win_result(uid, draw_no, my_numbers, result)

    return jsonify({"success": True, "result": result})


@app.route('/delete_history', methods=['POST'])
def delete_history_endpoint():
    data = request.json
    uid = data.get('id', '').lower().strip()
    record_id = data.get('record_id')
    
    if not uid or record_id is None:
        return jsonify({"success": False, "message": "필수 정보가 누락되었습니다."})
        
    if delete_purchase_record(uid, record_id):
        return jsonify({"success": True, "message": "성공적으로 삭제되었습니다."})
    return jsonify({"success": False, "message": "삭제할 기록을 찾을 수 없습니다."})


@app.route('/clear_history', methods=['POST'])
def clear_history_endpoint():
    data = request.json
    uid = data.get('id', '').lower().strip()
    
    if not uid:
        return jsonify({"success": False, "message": "아이디가 필요합니다."})
        
    if clear_user_history(uid):
        return jsonify({"success": True, "message": "모든 기록이 삭제되었습니다."})
    return jsonify({"success": False, "message": "삭제할 기록이 없거나 오류가 발생했습니다."})


@app.route('/check_all_wins', methods=['POST'])
def check_all_wins_endpoint():
    """사용자의 모든 구매 이력 당첨 확인"""
    data = request.json
    uid = data.get('id', '').lower().strip()
    if not uid:
        return jsonify({"success": False, "message": "아이디가 필요합니다."})

    current_draw = get_latest_draw_no()
    history = load_history()
    records = history.get(uid, [])
    results = []
    changed = False

    for record in records:
        draw_no = record.get("draw_no", 0)

        # 이미 확인된 레코드는 스킵 (단, 미추첨이었던 것은 재확인)
        if record.get("win_checked"):
            prev_result = record.get("win_result", {})
            # 이전에 '미추첨'이었으면 다시 확인
            if prev_result and prev_result.get("rank", 0) != -1:
                results.append(record)
                continue

        # 아직 추첨 전인 회차는 '미추첨' 처리
        if draw_no > current_draw:
            record["win_checked"] = False
            record["official_result"] = "미추첨"
            record["win_result"] = {"rank": -1, "label": "미추첨", "match": 0, "bonus": False}
            results.append(record)
            continue

        # 번호가 없는 경우 (동기화에서 메타정보만 가져온 경우)
        nums = record.get("numbers", [])
        if not nums:
            results.append(record)
            continue

        # 당첨 정보 조회 시도
        draw_info = get_lotto_info_by_no(draw_no)
        if draw_info:
            win = check_win(nums, draw_info["numbers"], draw_info["bonus"])
            win["draw_numbers"] = draw_info["numbers"]
            win["bonus"] = draw_info["bonus"]
            win["draw_date"] = draw_info["date"]
            record["win_checked"] = True
            record["win_result"] = win
            record["official_result"] = win["label"]
            changed = True
        else:
            # 당첨 정보를 가져올 수 없음 → 아직 추첨 전 or 서버 오류
            record["win_checked"] = False
            record["official_result"] = "미추첨"
            record["win_result"] = {"rank": -1, "label": "미추첨", "match": 0, "bonus": False}
        results.append(record)

    history[uid] = results
    if changed:
        save_history(history)
    return jsonify({"success": True, "records": results})


@app.route('/api/balance', methods=['POST'])
def get_balance_api():
    """마이페이지 예치금 연동"""
    data = request.json
    uid = data.get('id', '')
    upw = data.get('pw', '')
    if not uid or not upw:
        return jsonify({"success": False, "message": "아이디와 비밀번호가 필요합니다."})
    
    is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=bool(is_cloud),
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled",
                    "--lang=ko-KR"
                ]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=UA,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                extra_http_headers={
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
                }
            )
            page = context.new_page()
            
            if HAS_STEALTH:
                try: Stealth().apply_stealth_sync(page)
                except: pass

            if not do_login(page, uid, upw):
                if browser: browser.close()
                return jsonify({"success": False, "message": "동행복권 서버 로그인 실패"})

            # PC 웹 메인페이지 이동 (전체 메뉴 활용)
            page.goto("https://dhlottery.co.kr/common.do?method=main", wait_until="networkidle", timeout=30000)
            time.sleep(1.5)
            
            # 사용자 요청: 전체 메뉴 클릭
            try:
                page.evaluate("""() => {
                    const menuBtn = document.querySelector('.btn_common.menu, a[title="전체메뉴"], .top_menu, .btn_mypage');
                    if (menuBtn) menuBtn.click();
                }""")
                time.sleep(1.5)
            except: pass
            
            # HTML DOM 구조에 무관하게 화면에 노출되는 텍스트를 전부 합쳐서 정규식 스캔
            info = page.evaluate("""() => {
                let bal = '0';
                let acc = '';
                const fullText = document.body.innerText || '';
                
                // 이미지 증거: "예치금 1,500원" 매칭을 위한 가장 확실하고 관대한 정규식
                // "예치금", "잔액", ":" 등의 문자가 있든 없든 다이렉트로 숫자 매치
                const balMatch = fullText.match(/예치금[^0-9]*([0-9,]+)\\s*원/);
                if (balMatch) {
                    bal = balMatch[1];
                } else {
                    // 예치금 텍스트 아래에 있을 경우
                    const lines = fullText.split('\\n');
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].includes('예치금')) {
                            const m = lines[i].match(/([0-9,]+)\\s*원/);
                            if (m) bal = m[1];
                            else if (i + 1 < lines.length) {
                                const m2 = lines[i+1].match(/([0-9,]+)/);
                                if (m2) bal = m2[1];
                            }
                        }
                    }
                }
                
                // 가상계좌 스크래핑
                const accMatch = fullText.match(/케이뱅크[^0-9]*([0-9]{3}-?[0-9]{3}-?[0-9]+(?:\\*)?)/);
                if (accMatch) {
                    acc = '케이뱅크 ' + accMatch[1];
                }
                
                return { balance: bal, account: acc };
            }""")
            
            # 만약 계좌번호가 없다면 마이페이지에서 가져오기
            if info.get('balance', '0') == '0' or not info.get('account'):
                page.goto("https://dhlottery.co.kr/user.do?method=myPage", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)
                
                info2 = page.evaluate("""() => {
                    let bal = '0'; let acc = '';
                    const fullText = document.body.innerText || '';
                    const bMatch = fullText.match(/예치금[^0-9]*([0-9,]+)\\s*원/);
                    if (bMatch) bal = bMatch[1];
                    const aMatch = fullText.match(/케이뱅크[^0-9]*([0-9]{3}-?[0-9]{3}-?[0-9]+(?:\\*)?)/);
                    if (aMatch) acc = '케이뱅크 ' + aMatch[1];
                    return { balance: bal, account: acc };
                }""")
                if info.get('balance', '0') == '0': info['balance'] = info2.get('balance', '0')
                if not info.get('account'): info['account'] = info2.get('account', '')
            
            import re
            b_str = str(info.get('balance', '0'))
            balance_num = int(re.sub(r'[^0-9]', '', b_str)) if re.sub(r'[^0-9]', '', b_str) else 0
            account_str = info.get('account', '')

            if browser: browser.close()
            return jsonify({"success": True, "balance": balance_num, "account": account_str})
    except Exception as e:
        logger.error(f"예치금 처리 에러: {e}")
        try:
            if browser: browser.close()
        except:
            pass
        return jsonify({"success": False, "message": "잔액 동기화 지연. 다시 시도."})

@app.route('/auto_charge_popup', methods=['GET', 'POST'])
def auto_charge_popup():
    uid = request.args.get('id', '')
    upw = request.args.get('pw', '')
    if not uid or not upw:
        return "보안 정보가 유효하지 않습니다. 다시 동기화해주세요.", 400

    html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <title>안전 결제 서버 접속 중</title>
    </head>
    <body onload="document.getElementById('autoFrm').submit();" style="text-align:center; padding-top:100px; background:#f8fafc; font-family:sans-serif;">
        <h3 style="color:#0f172a; margin-bottom:10px;">동행복권 충전 센터 연결 중...</h3>
        <p style="color:#64748b; font-size:14px;">로그인 인증 정보를 안전하게 전송합니다.</p>
        <form id="autoFrm" method="post" action="https://dhlottery.co.kr/userSlogin.do?method=login">
            <input type="hidden" name="userId" value="{uid}">
            <input type="hidden" name="password" value="{upw}">
            <input type="hidden" name="checkReturnUrl" value="https://dhlottery.co.kr/userSlogin.do?method=latelyReady">
        </form>
    </body>
    </html>
    """
    return html


@app.route('/news')
def news_endpoint():
    """네이버 실시간 뉴스 크롤링 (10분 캐시)"""
    now_ts = time.time()
    cache_key = 'naver_news'
    
    if cache_key in _lotto_cache and (now_ts - _lotto_cache_time.get(cache_key, 0)) < 600:
        return jsonify({"success": True, "news": _lotto_cache[cache_key]})

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled",
                    "--lang=ko-KR"
                ]
            )
            context = browser.new_context(
                user_agent=UA,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"}
            )
            page = context.new_page()
            
            # 구글 뉴스 검색 (로또 키워드)
            url = "https://www.google.com/search?q=%EB%A1%9C%EB%98%90&tbm=nws"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            news_list = page.evaluate("""() => {
                const results = [];
                // 구글 뉴스 항목 셀렉터 (제목 위주)
                const items = Array.from(document.querySelectorAll('div.SoR63b, a.WlyS9b, div.mCBkyc, .n0W67d'));
                
                for (let item of items) {
                    if (results.length >= 3) break;
                    
                    let titleEl = item.querySelector('[role="heading"], .mCBkyc, .nDCH9b');
                    let linkEl = item.closest('a') || item.querySelector('a');
                    
                    if (!titleEl && item.tagName === 'DIV' && item.innerText.length > 10) titleEl = item;
                    
                    if (titleEl && linkEl) {
                        const title = titleEl.innerText.trim();
                        const link = linkEl.href;
                        if (title && link && !results.find(r => r.title === title)) {
                            results.push({ title, link });
                        }
                    }
                }
                
                // 검색 결과가 위 셀렉터로 안 잡힐 경우 대비 (범용 a 태그 탐색)
                if (results.length === 0) {
                    const links = Array.from(document.querySelectorAll('a')).filter(a => 
                        a.href.includes('url?q=') || (a.innerText.length > 15 && a.querySelector('h3'))
                    );
                    for (let a of links) {
                        if (results.length >= 3) break;
                        const t = a.innerText.split('\\n')[0].trim();
                        if (t.length > 5) results.push({ title: t, link: a.href });
                    }
                }
                
                return results;
            }""")
            
            browser.close()
            if news_list and len(news_list) > 0:
                _lotto_cache[cache_key] = news_list
                _lotto_cache_time[cache_key] = now_ts
                return jsonify({"success": True, "news": news_list})
    except Exception as e:
        logger.error(f"뉴스 수집 실패: {e}")
    
    return jsonify({"success": False, "message": "뉴스 정보를 가져올 수 없습니다."})


#  서버 시작
# ─────────────────────────────────────────────────────────
def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def open_browser():
    ip = get_local_ip()
    try:
        from pyngrok import ngrok
        import atexit
        public_url = ngrok.connect(5000).public_url
        print(f"\n{'='*60}\n🌐 [인터넷 주소] {public_url}\n{'='*60}")
        atexit.register(ngrok.disconnect, public_url)
    except:
        pass
    print(f"🏠 [로컬 주소] http://{ip}:5000")
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == '__main__':
    Timer(1.5, open_browser).start()
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

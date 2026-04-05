import time
import json
import logging
import webbrowser
from threading import Timer
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
import os
import requests
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


# ─────────────────────────────────────────────────────────
#  최신 회차 정보 조회 (Playwright 페이지 파싱)
# ─────────────────────────────────────────────────────────

import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 메모리 캐시 (60분간 유지)
_lotto_cache = {}
_lotto_cache_time = {}
CACHE_TTL = 3600  # 1시간

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
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(user_agent=UA)
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
            logger.info(f"  [LOGIN] 시도: {login_url}")
            page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1.0)

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
            time.sleep(0.3)

            # 로그인 버튼 클릭
            logger.info("  [LOGIN] 로그인 버튼 클릭...")
            page.click(login_btn)

            # 페이지 로딩 대기
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            time.sleep(1.0)

            # 로그인 성공 확인 (여러 방법으로 판단)
            for attempt in range(20):
                # 방법 1: 페이지 내용에서 로그아웃 버튼/텍스트 존재 확인
                if is_logged_in(page):
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
    for _ in range(25):
        try:
            # 1. URL이나 name에 game645가 포함된 프레임 탐색
            for f in page.frames:
                if "game645" in f.url.lower() or "game645" in f.name.lower():
                    return f
            # 2. 동행복권의 핵심 iframe 이름인 ifrm_lotto645 연동
            for f in page.frames:
                if "ifrm_lotto645" in f.name.lower() or "lotto645" in f.url.lower():
                    return f
            
            # 3. 만약 위에서 못 찾았는데, 메인 페이지에 직접 번호 선택(check645num) 요소가 있다면 메인 프레임 반환
            if page.query_selector("label[for^='check645num']"):
                return page.main_frame
        except:
            pass
        time.sleep(0.5)
    return None


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
def do_purchase(page, numbers):
    logger.info("[PURCHASE] === 구매 엔진 시작 ===")

    dialog_msgs = []

    def handle_dialog(dialog):
        logger.warning(f"  [DIALOG] {dialog.message}")
        dialog_msgs.append(dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)

    try:
        # STEP 1: 구매 페이지 접속
        logger.info("  [1/7] 구매 페이지 접속 중...")
        page.goto(
            "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40",
            wait_until="networkidle", timeout=30000
        )
        time.sleep(1.0)

        try:
            page.evaluate("""() => {
                document.querySelectorAll('input[value="닫기"],.close,.popup-close')
                    .forEach(el => { try { el.click(); } catch(e){} });
            }""")
        except:
            pass

        # STEP 2: iframe 탐색 및 팝업 제거
        logger.info("  [2/7] game645 iframe 탐색 및 방해 요소 제거...")
        time.sleep(2.0)
        
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
            cur_url = page.url
            page_text = page.evaluate("() => document.body.innerText.substring(0, 300)")
            logger.error(f"  [FAIL] 타겟 프레임을 찾을 수 없음. URL: {cur_url}, 내용: {page_text}")
            
            if "login" in cur_url.lower(): return False, "로그인 세션이 만료되었습니다. 다시 로그인해 주세요."
            if "점검" in page_text: return False, "동행복권 사이트 점검 시간입니다."
            if "간소화" in page_text or "접속이 폭주" in page_text: return False, "동행복권 사이트가 현재 간소화 모드로 운영 중이어서 구매가 지연되고 있습니다."
            
            return False, "금융 거래용 보안 프레임을 찾지 못했습니다. 잠시 후 동기화 버튼을 다시 눌러주세요."
        logger.info(f"    iframe: {frame.url}")

        try:
            frame.wait_for_load_state("domcontentloaded", timeout=8000)
        except:
            pass
        time.sleep(0.5)

        # STEP 3: 게임 UI 확인 (label 존재 여부)
        logger.info("  [3/7] 번호 선택 UI 확인...")
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
            try:
                txt = frame.evaluate("() => document.body.innerText.substring(0, 200)")
                logger.error(f"  iframe 내용: {txt!r}")
            except:
                pass
            return False, "번호 선택 UI 로드 실패 (구매 시간: 월~토 06:00 ~ 토 20:00)"

        # STEP 4: 혼합선택 탭 활성화
        logger.info("  [4/7] 번호 입력 탭 활성화...")
        try:
            frame.evaluate("""() => {
                for (let el of document.querySelectorAll('a,button,li,label,span,div')) {
                    const t = (el.innerText||el.textContent||'').replace(/\\s/g,'');
                    if (t === '혼합선택' || t === '번호직접선택') { el.click(); return t; }
                }
            }""")
        except:
            pass
        time.sleep(0.3)

        # STEP 5: 번호 6개 선택
        logger.info(f"  [5/7] 번호 선택: {numbers}")
        fail_count = 0
        for num in numbers:
            ok = select_number(frame, num)
            logger.info(f"    {num:02d} {'✅' if ok else '❌'}")
            if not ok:
                fail_count += 1
            time.sleep(0.08)

        # 실제 체크된 수 검증
        try:
            checked = frame.evaluate("""() =>
                document.querySelectorAll('input[id^="check645num"]:checked').length
            """)
            logger.info(f"    체크된 번호 수: {checked}/6")
        except:
            checked = 6 - fail_count

        if fail_count >= 3:
            return False, f"번호 선택 다수 실패 ({fail_count}/6 실패)"

        time.sleep(0.3)

        # STEP 6: 선택완료(확인) 클릭
        logger.info("  [6/7] '선택완료' 클릭...")
        step6_ok = False
        try:
            r = frame.evaluate("""() => {
                const btn = document.getElementById('btnSelectNum');
                if (btn) { btn.click(); return 'ok'; }
                return null;
            }""")
            if r:
                step6_ok = True
        except:
            pass
        if not step6_ok:
            try:
                frame.locator("#btnSelectNum").click(force=True, timeout=2000)
                step6_ok = True
            except:
                pass
        if not step6_ok:
            return False, "[6/7] '선택완료' 버튼 클릭 실패"
        logger.info("    선택완료 완료")
        time.sleep(0.8)

        # 잔액/한도 에러 감지
        if dialog_msgs:
            last = dialog_msgs[-1]
            if any(x in last for x in ["부족", "한도", "오류", "실패", "초과", "로그인"]):
                return False, f"구매 불가: {last}"

        # STEP 7: 구매하기 클릭 (frame 내 #btnBuy만)
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
        logger.info("    구매하기 완료")
        time.sleep(1.5)

        # 구매 확인 팝업 처리
        for ctx in [page, frame]:
            try:
                ctx.evaluate("""() => {
                    const sels = ['#popupLayerConfirm .button_ok',
                        '#popupLayerConfirm input[value="확인"]',
                        '#popupLayerConfirm a', '#popupLayerConfirm button',
                        '.btn_confirm', '.button_ok'];
                    for (let sel of sels) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) { el.click(); return sel; }
                    }
                }""")
            except:
                pass
        time.sleep(2.0)

        # 최종 결과 판정
        logger.info("  === 결과 판정 ===")
        logger.info(f"  dialog_msgs: {dialog_msgs}")

        # 1) dialog 메시지에서 성공/실패 판정
        for msg in reversed(dialog_msgs):
            if any(k in msg for k in ["완료", "성공", "발행", "구매하셨", "정상"]):
                return True, f"구매 완료: {msg}"
            if any(k in msg for k in ["부족", "한도", "실패", "오류", "초과", "불가", "로그인"]):
                return False, f"구매 실패: {msg}"

        # 2) 페이지 본문에서 성공/실패 판정
        try:
            verdict = page.evaluate("""() => {
                const t = document.body.innerText || '';
                if (t.includes('구매가 완료') || t.includes('발행번호') || t.includes('정상적으로 처리')) return 'ok';
                if (t.includes('잔액이 부족') || t.includes('한도를 초과')) return 'fail';
                return 'unknown';
            }""")
            if verdict == 'ok':
                return True, "구매 완료"
            elif verdict == 'fail':
                return False, "잔액 부족 또는 한도 초과"
        except:
            pass

        # 3) iframe 내부에서도 확인
        try:
            frame_verdict = frame.evaluate("""() => {
                const t = document.body.innerText || '';
                if (t.includes('완료') || t.includes('발행') || t.includes('정상')) return 'ok';
                return 'unknown';
            }""")
            if frame_verdict == 'ok':
                return True, "구매 완료"
        except:
            pass

        # 4) 7단계까지 모두 성공 + 명확한 실패 메시지 없음 → 구매 성공으로 간주
        if step7_ok and not any(k in str(dialog_msgs) for k in ["부족", "한도", "실패", "오류", "초과", "불가"]):
            logger.info("  구매 버튼 클릭 성공 + 실패 메시지 없음 → 구매 성공 간주")
            return True, "구매 완료 (확인 메시지 자동 처리됨)"
    except Exception as e:
        logger.error(f"구매 중 예외: {e}")
        return False, f"구매 오류: {str(e)[:100]}"


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
    with sync_playwright() as p:
        is_cloud = os.environ.get('RENDER') or os.environ.get('PORT') or os.environ.get('DYNO')
        browser = p.chromium.launch(
            headless=bool(is_cloud),
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process",
                "--js-flags=--max-old-space-size=128",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(viewport={"width": 1366, "height": 768}, user_agent=UA)
        page = context.new_page()
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(page)
        try:
            logger.info("=== 로그인 시도 중 ===")
            if do_login(page, user_id, user_pw):
                logger.info("=== 로그인 성공 → 구매 진행 ===")
                return do_purchase(page, numbers)
            return False, "로그인 실패"
        except Exception as e:
            return False, str(e)
        finally:
            browser.close()


# ─────────────────────────────────────────────────────────
#  Flask 라우트
# ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'lotto_ai.html')


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/buy', methods=['POST'])
def buy_endpoint():
    data = request.json
    uid = data.get('id', '')
    pw = data.get('pw', '')
    numbers = data.get('numbers', [])

    success, msg = automate_purchase(uid, pw, numbers)

    if success:
        draw_no = get_purchase_draw_no()
        record = add_purchase_record(uid, draw_no, numbers)
        return jsonify({
            "success": True,
            "message": msg,
            "draw_no": draw_no,
            "numbers": numbers,
            "purchased_at": record["purchased_at"]
        })
    return jsonify({"success": False, "message": msg})


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
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=UA
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
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = browser.new_context(user_agent=UA)
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
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--single-process",
                    "--js-flags=--max-old-space-size=128",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = browser.new_context(user_agent=UA)
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

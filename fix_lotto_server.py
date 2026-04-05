#!/usr/bin/env python3
import re

with open('lotto_server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# We want to replace everything from `            result = page.evaluate("""(draw_no) => {`
# to `            }""", draw_no)`
start_marker = '            result = page.evaluate("""(draw_no) => {'
end_marker = '            }""", draw_no)'

start_idx = text.find(start_marker)
end_idx = text.find(end_marker, start_idx) + len(end_marker)

new_eval_block = '''            result = page.evaluate("""(draw_no) => {
                // 1. 회차번호 확인
                const drawTitle = document.querySelector('.d-trigger span, .lt645-draw-result h3 strong');
                const titleTxt = drawTitle ? drawTitle.innerText : '';
                const noMatch = titleTxt.match(/(\\d+)\\s*회/);
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
                    let dateMatch = txt.match(/\\d{4}[.-]\\d{2}[.-]\\d{2}/);
                    if (dateMatch) {
                        date = dateMatch[0].replace(/\\./g, '-');
                    } else {
                        dateMatch = txt.match(/(\\d{4})년\\s*(\\d{1,2})월\\s*(\\d{1,2})일/);
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
            }""", draw_no)'''

# Also fix the math fallback:
fallback_start = "            if result and len(result.get('balls', [])) == 6 and any(b > 0 for b in result['balls']):"
fallback_end = "                info = {"

fallback_new = """            if result and len(result.get('balls', [])) == 6 and any(b > 0 for b in result['balls']):
                if not result.get('date'):
                    try:
                        import datetime as dt
                        base_date = dt.datetime(2002, 12, 7)
                        draw_date = base_date + dt.timedelta(weeks=(result.get('actualNo') or draw_no) - 1)
                        result['date'] = draw_date.strftime("%Y-%m-%d")
                    except:
                        pass
                info = {"""

if start_idx != -1:
    text = text[:start_idx] + new_eval_block + text[end_idx:]
    print("JS Block replaced")

text = text.replace(fallback_start + "\n" + fallback_end, fallback_new)
text = text.replace(fallback_start + "\n                " + fallback_end, fallback_new)

with open('lotto_server.py', 'w', encoding='utf-8') as f:
    f.write(text)
    print("lotto_server.py saved")

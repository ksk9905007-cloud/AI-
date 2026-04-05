import requests, json
from bs4 import BeautifulSoup

def get_naver_lotto(draw_no):
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f'https://m.search.naver.com/search.naver?query=로또+{draw_no}회'
    res = requests.get(url, headers=headers, timeout=5)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    date_el = soup.select_one('.select_date')
    date = date_el.text.strip() if date_el else ''
    
    # "2024.12.07 추첨" -> "2024-12-07"
    import re
    if date:
        date_match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date)
        if date_match:
            date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

    num_els = soup.select('.numb_box .num_box .num')
    balls = [int(n.text) for n in num_els] if num_els else []
    
    bonus_el = soup.select_one('.numb_box .bonus_box .num')
    bonus = int(bonus_el.text) if bonus_el else 0
    
    # Prize and count
    # dl.prize_box dt -> count, dd -> prize
    prize_dt = soup.select_one('.prize_box dt')
    prize_dd = soup.select_one('.prize_box dd')
    
    count = 0
    amount = 0
    
    if prize_dt:
        count_match = re.search(r'(\d+)명', prize_dt.text)
        if count_match:
            count = int(count_match.group(1))
            
    if prize_dd:
        amount_match = re.sub(r'[^\d]', '', prize_dd.text)
        if amount_match:
            amount = int(amount_match)

    print(json.dumps({
        'draw_no': draw_no,
        'date': date,
        'balls': balls,
        'bonus': bonus,
        'amount': amount,
        'count': count
    }))

get_naver_lotto(1217)

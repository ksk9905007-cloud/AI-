import json
from playwright.sync_api import sync_playwright

def get_lotto_info(draw_no):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Set a normal desktop UA to bypass mobile simplify checks if possible
        ctx = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = ctx.new_page()
        
        # Test the official JSON API route first
        print("Testing common.do API...")
        page.goto(f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={draw_no}")
        content = page.content()
        if '"returnValue":"success"' in content:
            print("API SUCCESS", content[:200])
            return
        else:
            print("API FAILED or REDIRECTED to HTML", content[:200])
            
        browser.close()

get_lotto_info(1217)

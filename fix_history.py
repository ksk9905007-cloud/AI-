#!/usr/bin/env python3
import json, os
path = 'lotto_history.json'
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        h = json.load(f)
    for uid, recs in h.items():
        for r in recs:
            draw_no = r.get('draw_no', 0)
            if draw_no >= 1218:
                r['official_result'] = '미추첨'
                r['win_checked'] = False
                r['win_result'] = {'rank': -1, 'label': '미추첨', 'match': 0, 'bonus': False}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    print('History updated')
else:
    print('No history file')

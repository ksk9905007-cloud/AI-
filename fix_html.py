#!/usr/bin/env python3
"""Fix renderHistory in lotto_ai.html"""

with open('lotto_ai.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: winBadge assignment missing after "const cls = rank > 0 ..." on the win_checked branch
old_badge = """            } else if (r.win_checked && winResult.label) {
                const cls = rank > 0 ? `win-${rank}` : 'win-0';
            } else if (r.official_result) {
                const isWin = r.official_result.includes('당첨');
                const cls = isWin ? 'win-1' : 'win-0';
                winBadge = `<span class="win-badge ${cls}">${r.official_result}</span>`;
            } else {
                winBadge = `<span class="win-badge win-none">미확인</span>`;
            }"""

new_badge = """            } else if (r.win_checked && winResult.label) {
                const cls = rank > 0 ? `win-${rank}` : 'win-0';
                winBadge = `<span class="win-badge ${cls}">${winResult.label}</span>`;
            } else if (officialResult.includes('당첨') && !officialResult.includes('미')) {
                winBadge = `<span class="win-badge win-1">당첨</span>`;
            } else if (officialResult === '낙첨') {
                winBadge = `<span class="win-badge win-0">낙첨</span>`;
            } else {
                winBadge = `<span class="win-badge win-none">미확인</span>`;
            }"""

if old_badge in content:
    content = content.replace(old_badge, new_badge)
    print("OK: winBadge assignment fixed")
else:
    print("WARN: badge pattern not found (may already be fixed)")

# Fix 2: Replace the return template with null-safe and smart check button
old_return = """            return `
                <tr class="history-item">
                    <td><b>${r.draw_no}회</b></td>
                    <td><div style="display:flex;gap:3px;flex-wrap:wrap;">${balls}</div></td>
                    <td style="font-size:.75rem;color:var(--muted);">${r.purchased_at.substring(0,10)}</td>
                    <td>${winBadge}</td>
                    <td><button class="check-btn" onclick="checkSingleWin(${r.draw_no},'${JSON.stringify(r.numbers).replace(/"/g,"'")}')">${ 확인}</button></td>
                </tr>
            `;"""

# Try alternative patterns (the file might have different formatting)
old_return_alt = """            return `
                <tr class="history-item">
                    <td><b>${r.draw_no}회</b></td>
                    <td><div style="display:flex;gap:3px;flex-wrap:wrap;">${balls}</div></td>
                    <td style="font-size:.75rem;color:var(--muted);">${r.purchased_at.substring(0,10)}</td>
                    <td>${winBadge}</td>"""

new_return_section = """            const hasNums = r.numbers && r.numbers.length > 0;
            const isUndrawn = officialResult === '미추첨' || rank === -1;
            const checkBtn = (!hasNums || isUndrawn)
                ? `<button class="check-btn" disabled style="opacity:0.4;">${isUndrawn ? '대기' : '확인'}</button>`
                : `<button class="check-btn" onclick="checkSingleWin(${r.draw_no},'${JSON.stringify(r.numbers).replace(/"/g,"'")}')">확인</button>`;
            return `
                <tr class="history-item">
                    <td><b>${r.draw_no}회</b></td>
                    <td><div style="display:flex;gap:3px;flex-wrap:wrap;">${balls}</div></td>
                    <td style="font-size:.75rem;color:var(--muted);">${(r.purchased_at||'').substring(0,10)}</td>
                    <td>${winBadge}</td>
                    <td>${checkBtn}</td>
                </tr>
            `;"""

if old_return in content:
    content = content.replace(old_return, new_return_section)
    print("OK: return template replaced (exact match)")
elif old_return_alt in content:
    # Replace from the start of old_return_alt to end of the return block
    idx = content.index(old_return_alt)
    # Find the end: look for `;\n        }).join`
    end_marker = "        }).join('');"
    end_idx = content.index(end_marker, idx)
    old_section = content[idx:end_idx]
    content = content[:idx] + new_return_section + "\n" + content[end_idx:]
    print("OK: return template replaced (partial match)")
else:
    print("WARN: return template not found")

# Fix 3: filterHistory null-safe
old_filter = "r.numbers.some(n => String(n) === q) ||"
new_filter = "(r.numbers||[]).some(n => String(n) === q) ||"
if old_filter in content:
    content = content.replace(old_filter, new_filter, 1)
    print("OK: filterHistory null-safe fix")

old_filter2 = "r.purchased_at.includes(q)"
new_filter2 = "(r.purchased_at||'').includes(q)"
if old_filter2 in content:
    content = content.replace(old_filter2, new_filter2, 1)
    print("OK: filterHistory purchased_at null-safe fix")

with open('lotto_ai.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("File saved.")

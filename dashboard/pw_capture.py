import json, sys, time, re
from playwright.sync_api import sync_playwright

token = open('/tmp/session_token').read().strip()
CONV_ID = "28cc90b5-46b5-47b0-8ceb-f19c19273c9f"

p = sync_playwright().start()
b = p.chromium.launch(headless=True)
pg = b.new_page(viewport={'width':1400,'height':1000})
pg.add_init_script(f"localStorage.setItem('dashboard_token', '{token}');")

sse_responses = []  # (url, response)
pg.on('response', lambda r: sse_responses.append(r) if '/api/chat/conversations/' in r.url and '/messages' in r.url else None)

pg.goto(f'http://localhost:3399/v2/chat/{CONV_ID}', wait_until='domcontentloaded')
pg.wait_for_timeout(1500)

# Select deepseek as main model (first select)
selects = pg.query_selector_all('select')
print("selects found:", len(selects))
if selects:
    selects[0].select_option('llamacpp-deepseek-v4-flash-q2')
    pg.wait_for_timeout(600)

# Confirm project-files MCP on
body = pg.text_content('body')
print("Project Files ON:", 'Project FilesON' in body or 'Project Files ON' in body)

# Type message
msg = ("Write a single file at path 'debug-big.txt' using the write_file tool. "
       "The content must be a long story, at least 150,000 characters. "
       "Generate the entire story and write it all in ONE write_file call.")
ta = pg.query_selector('textarea')
ta.fill(msg)
pg.wait_for_timeout(300)
ta.press('Enter')
print("sent message at", time.strftime('%H:%M:%S'))

# Poll UI, screenshot periodically
start = time.time()
seen_tool = False
seen_result = False
for i in range(120):
    pg.wait_for_timeout(1000)
    body = pg.text_content('body')
    if 'assembling' in body:
        print(f"[{i}s] assembling call… visible")
    if 'debug-big' in body or 'Created debug-big' in body or 'Wrote debug-big' in body:
        seen_tool = True
        print(f"[{i}s] tool event visible: ", re.findall(r'(Created|Wrote) debug-big[^\n]{0,40}', body))
    if 'Stop' in body:
        pass
    # detect completion: run done -> Stop gone & a final assistant bubble
    if i % 10 == 5:
        pg.screenshot(path=f'/tmp/pw_{i:03d}.png')
    # completion heuristic: no Stop button and we saw a result
    if seen_tool:
        # check if Stop still present
        stop_btn = pg.query_selector('button:has-text("Stop")')
        if not stop_btn:
            print(f"[{i}s] run completed (Stop gone)")
            pg.screenshot(path='/tmp/pw_final.png')
            break
    if time.time() - start > 120:
        print("TIMEOUT")
        break

print("elapsed:", round(time.time()-start,1))
pg.screenshot(path='/tmp/pw_final.png')

# Read SSE bodies
print("\n=== SSE responses ===")
for r in sse_responses:
    print("URL:", r.url[:120], "status:", r.status)
    try:
        body_txt = r.body().decode('utf-8', errors='replace')
        frames = [l for l in body_txt.split('\n') if l.startswith('data: ')]
        print("  frames:", len(frames))
        for l in frames:
            d = l[6:]
            if d == '[DONE]':
                continue
            try:
                ev = json.loads(d)
                t = ev.get('type')
                if t in ('tool_call','tool_call_pending','tool_result','tool_progress','tool_calls'):
                    msg = ev.get('message','')[:60] if 'message' in ev else ''
                    print(f"    {t}: name={ev.get('name') or ev.get('tool_name')} msg={msg!r}")
            except Exception:
                pass
    except Exception as e:
        print("  read err:", e)

b.close(); p.stop()

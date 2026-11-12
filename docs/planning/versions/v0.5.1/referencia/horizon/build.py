import json, base64, html, glob, os
D = json.load(open('data.json'))
R = '/home/danieldev/.claude/projects/-home-danieldev-orion-agent/6af64db2-9f0d-42f2-9935-ab188801641c/tool-results/'
def img(name):
    b = base64.b64encode(open(R + name, 'rb').read()).decode()
    return f'data:image/png;base64,{b}'
before_splash = img('mcp-tui-mcp-blob-1794440212367-idp5wx.png')
before_menu = img('mcp-tui-mcp-blob-1794440219360-iefi5a.png')
GL = set('❯●✔✖▼⠋›·↑↓−…×▲')
def term(key, label):
    out = []
    for ln in D[key]:
        s = ''
        for t, fg, bold, bg in ln:
            st = f'color:{fg};' + ('font-weight:700;' if bold else '') + (f'background:{bg};' if bg else '')
            body = ''.join(f'<i>{html.escape(c)}</i>' if c in GL else html.escape(c) for c in t)
            s += f'<span style="{st}">{body}</span>'
        out.append(f'<div class="ln">{s or "&nbsp;"}</div>')
    return f'<figure class="term" aria-label="{label}"><div class="bar"><b></b><b></b><b></b><span>{label}</span></div><div class="scr">{"".join(out)}</div></figure>'
page = open('template.html').read()
for k in D: page = page.replace('{{' + k + '}}', term(k, k))
page = page.replace('{{before_splash}}', before_splash).replace('{{before_menu}}', before_menu)
open('page.html', 'w').write(page)
print(len(page))
